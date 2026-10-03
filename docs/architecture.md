# 軟體架構設計手冊 (Software Architecture)

本文件詳述《SD 鋼彈 G 世代 永恆》自動化日常任務腳本的系統架構與設計哲學。

---

## 1. 設計哲學

1. **黑盒非侵入式 (Non-invasive Black-box)**：
   絕不讀寫遊戲記憶體、不攔截竄改網路封包，只透過模擬玩家視覺（螢幕截圖）與操作（觸控點擊、滑動）進行自動化，杜絕封號風險。
2. **狀態驅動 (State-Driven Navigation)**：
   捨棄脆弱的固定時間延遲（`time.sleep()`），改以畫面特徵錨點（Anchor Point）與狀態機導航，具備高度抗網路波動與畫面載入延遲能力。
3. **人類操作擬真 (Human-like Simulation)**：
   點擊座標採高斯亂數偏移、滑動採貝茲曲線非線性軌跡、操作間隔帶有動態隨機擾動，消除機器人特徵。
4. **模組化任務插拔 (Pluggable Task Pipeline)**：
   所有日常任務（領信箱、抽卡、掃蕩副本、領任務成就）皆繼承自標準介面，可獨立啟用、關閉或排序。

---

## 2. 系統架構圖 (Architecture Diagram)

```mermaid
flowchart TD
    subgraph UI_Scheduler [排程與使用者介面]
        Main["main.py (CLI / 進入點)"]
        Scripts["scripts/ (Step 1~4 獨立步驟執行器)"]
        Config["config.yaml (任務開關與設備設定)"]
    end

    subgraph Task_Layer [任務工作流層 Tasks]
        TaskRunner[TaskRunner]
        DailyLogin[DailyLoginTask]
        WarshipCruise[WarshipCruiseTask]
        CharRequests[PersonalBaseRequestTask]
        DailyCultivation[DailyCultivationTask]
    end

    subgraph State_Layer [狀態與導航層 State & Navigation]
        FSM[GameState Machine (三錨點收斂與導航圖)]
        PageManager[PageManager (集中頁面分類與例外彈窗標準處理)]
        PopupHandler[全域彈窗/下載確認/對話跳過]
    end

    subgraph Vision_Layer [感知與視覺識別層 Vision]
        YOLODetector["YOLOUIDetector (YOLO11n ONNX DirectML / GPU 加速)"]
        TemplateMatch[OpenCV 模板匹配]
        OCR[RapidOCR 文字識別]
        PixelCheck[RGB/BGR 像素通道特徵快速校驗]
    end

    subgraph Device_Layer [設備通信與操作層 Device]
        ADBBridge[ADB 通信與端口自動偵測]
        ScreencapStream[高速二進位截圖傳輸 <100ms]
        HumanInput[擬真隨機點擊與貝茲非線性滑動]
    end

    subgraph Emulator_Layer [執行實體]
        Emulator["Android 模擬器 (1920x1080 橫屏)"]
    end

    Main --> Config & TaskRunner
    Scripts --> Config & Task_Layer
    TaskRunner --> DailyLogin & WarshipCruise & CharRequests & DailyCultivation
    DailyLogin & WarshipCruise & CharRequests & DailyCultivation --> FSM
    FSM --> PageManager & PopupHandler
    FSM --> Vision_Layer
    PageManager --> Vision_Layer
    Vision_Layer --> ScreencapStream
    HumanInput --> ADBBridge
    ScreencapStream & ADBBridge --> Emulator
```

---

## 3. 分層職責詳細說明

### 3.1 設備通信層 (`core/device.py`)
- **ADB 連線管理**：支援自動掃描本機常見模擬器端口（Nox `62001`, MuMu `16384`, LDPlayer `5555`）。
- **高速截圖**：透過 `adb exec-out screencap -p` 建立 Memory Stream，避開磁碟 I/O，截圖耗時壓在 100ms 內。
- **擬真輸入 (Human Input)**：
  - 點擊目標範圍內自動產生邊緣內縮安全區，計算隨機高斯座標偏移。
  - 滑動操作產生隨機控制點之二次/三次貝茲曲線，以階梯式時間插值執行。

### 3.2 感知層 (`core/vision.py` & `tools/yolo_detector.py`)
- **GPU 加速物件偵測 (YOLO11n DirectML)**：
  - 採用 ONNX Runtime DirectML 驅動本機 NVIDIA RTX 4070 SUPER GPU，於次毫秒內完成整頁 UI 元件辨識（`btn_skip`, `btn_confirm`, `btn_trash`, `btn_accept` 等）。
  - 抗動態特效與按鈕呼吸光干擾，徹底杜絕傳統模板比對閾值過高導致的偽陰性（False Negative）。
- **模板比對 (Template Matching)**：
  - 採用 `cv2.TM_CCOEFF_NORMED` 進行正規化相關性係數匹配。
- **文字辨識 (OCR)**：
  - 使用 `rapidocr-onnxruntime`，用於掃蕩剩餘次數、關卡名稱、彈窗文字語意判別。
- **像素通道校驗 (Pixel Check)**：
  - 針對關鍵啟用/禁用按鈕（如全部回收之亮藍 $B>180$ vs 灰暗 $B\approx 111$）進行色彩通道值精準比對。

### 3.3 狀態導航與主頁收斂 (`core/state_machine.py`)
- **主畫面三大核心錨點多數決 (3-Anchor Majority Voting)**：
  1. 畫面右下角：核心「出擊」按鈕 (`home_sortie.png`, ROI: `(1250, 580, 670, 350)`)。
  2. 畫面左上角：玩家等級數值與頭像框 (`home_level.png`, ROI: `(0, 0, 300, 150)`)。
  3. 畫面右上角：AP 體力條與貨幣欄位 (`home_stamina.png`, ROI: `(1100, 0, 300, 150)`)。
- **全自動路徑收斂 (`navigate_to_home()`)**：
  - 若位於二級頁面（基地、培育關卡清單等），優先點擊底欄「主畫面」Tab。
  - 若遇中途彈窗，自動調度 `PageManager` 予以標準化排查。

### 3.4 標準化頁面管理與例外處理 (`core/page_manager.py`)
- **頁面標準分類器 (`classify()`)**：
  - 透過 OCR 關鍵字、版面佈局與特徵錨點將當前畫面統一分類（`HOME`、`DATE_RESET`、`LOGIN_BONUS`、`RESOURCE_DOWNLOAD`、`MODAL_INFO`、`MODAL_CONFIRM`、`ITEM_ACQUIRED`、`DIALOGUE` 等）。
  - 各畫面具備獨立標準 Handler（如 `handle_resource_download`, `handle_item_acquired`, `handle_login_bonus` 等），拒絕各任務各自私下獨立處理。
- **標準化資源更新下載處理 (`handle_resource_download`)**：
  - 依使用者最高指導原則：無論在啟動或任何流程中跳出資料更新/下載彈窗，一律自動點擊「下載」並等待下載完成。
- **未知頁面安全防護 (Unknown Page Guardrail)**：
  - 偵測到未定義或異常頁面（`UNKNOWN`）時，自動儲存截圖至 `captures/unknown_pages/` 並寫入 Log，主動停下向使用者請示，絕不盲點。

### 3.5 任務層 (`tasks/`)
- 統一繼承介面 `BaseTask`（含 `run()`, `pre_check()`, `post_check()`）。
- **多模態驗證機制 (Multi-Modal Verification)**：
  - 杜絕純布林或單一模板門檻誤判。在操作前後均檢驗狀態差（如戰艦巡航累積時間是否歸零、道具數是否重置為 0、主頁 AP 數值是否實質增加）。

### 3.6 執行環境與硬體架構 (`sd_gundam` Conda Environment)
- **專屬 Conda 環境**：`sd_gundam` (Python 3.12.15)
- **直譯器路徑**：`C:\Users\sharkMeow\miniconda3\envs\sd_gundam\python.exe`
- **啟用指令**：`conda activate sd_gundam`
- **環境隔離鐵律**：嚴禁使用 Conda `base` 環境，嚴禁私自建立其他零散虛擬環境。所有開發、測試與任務執行均強制綁定 `sd_gundam`。
- **硬體推論加速**：基於 `onnxruntime-directml`，已啟用 `['DmlExecutionProvider', 'CPUExecutionProvider']`，將 YOLO UI 物件偵測與 RapidOCR 模型直接卸載至本機 **NVIDIA GeForce RTX 4070 SUPER** 運算。

