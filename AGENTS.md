# AGENTS.md - AI Agent Operating Guide

## 1. 核心行為守則 (Core Agent Rules - Mandatory)

1. **執行前規劃 (Pre-Execution Planning)**
   - 進行多步驟操作、代碼重構或模擬器互動前，**必須先呈報清晰計畫**。嚴禁未經確認擅自盲試或在帳號上盲點。
2. **開發與操作未知強制請示 (Mandatory User Consultation - Never Assume)**
   - **開發與操作防呆強制規定**：凡遇到開發上不懂、不清楚具體操作步驟、未定義之業務流程（例如未完全實作之特殊委託、強化或出擊關卡），**強制規定必須向使用者請教標準操作流程**，絕不允許私自撰寫假邏輯（如私自 `return True` 假裝成功）或在實機上盲試摸索。
   - 遇到不熟悉的關卡規則、資源消耗或 UI 流程，**必須先向使用者請教**，嚴禁以實機盲點猜測機制。
   - 即使是正常執行流程（Process），在各關鍵節點（如選擇目標、消耗資源、確認操作前）皆可主動截圖展示並向使用者請示確認，確保每一步完全符合預期。
3. **按鈕點擊策略原則 (Button Interaction Policy: Fixed vs CV)**
   - **靜態/固定系統按鈕**：如全域底部導航列（NavBar）、頂部返回鍵（Header Back）等固定幾何版面按鈕，**應盡可能使用校準過之固定常數座標**（定義於 `NavigationCoords`）。
   - **動態按鈕/非固定位置元件**：如各類彈窗按鈕、任務卡片、確認/跳過/執行按鈕、列表項目等，**強制要求使用 CV 方法（優先使用 GPU YOLO 深度學習物件偵測，次選模板匹配或 OCR 語意定位）準確辨認邊界框與幾何中心後才按下**。嚴禁跳過辨識直接點擊猜測之裸座標。
4. **執行過程即時回報 (Real-Time Transparency)**
   - 執行期間必須即時輸出當前操作細節（UI 狀態、點擊座標、OCR / YOLO 辨識結果、等待狀態），絕不在背景靜默操作。
5. **未辨識任務安全防護 (Unknown Task Safety Guardrail)**
   - 偵測到未知或未支援任務時：自動截圖存至 `captures/unknown_tasks/`、記錄 Log、發出終端警報並安全返回，絕不盲點。
6. **標準化頁面處理與例外求助 (Standardized Page Management & Exception Handling)**
   - 頁面判斷必須透過標準化分類器與專屬 Handler 處理，**嚴禁各任務各自私下獨立處理**。
   - 狀態機遇到例外或不確定畫面時：自動截圖存至 `captures/unknown_pages/`、記錄 Log，並**主動停下來向使用者請教處理方式**，絕不擅自盲試。

---

## 2. 自動化與防封規範 (Technical Standards)

- **非侵入黑盒 (Black-box Only)**：僅使用 ADB 截圖與模擬點擊，不碰記憶體或封包。
- **擬真與防封 (Anti-Detection)**：點擊必須包含隨機座標偏移，等待時間隨機化，滑動使用曲線軌跡。
- **狀態驅動控制 (State-Driven)**：禁止固定秒數盲睡，所有跳轉必須以 UI 錨點、YOLO 偵測或 OCR 驗證；若單一導航或狀態轉換卡死超過閾值（常規逾時 20~30 秒）必須觸發安全防護中斷或安全返回主畫面。
- **統一頁面管理 (PageManager)**：彈窗、換日、簽到、資料下載與例外狀態統一由 `core/page_manager.py` 處理，拒絕獨立各搞一套。
- **模組化架構**：任務皆繼承 `BaseTask`，彼此獨立解耦。

---

## 3. 開發與提交標準 (Coding & Commit)

- **語言與記錄**：Python 3.10+、強制型別標註、統一使用 `loguru.logger`（嚴禁 `print()`）。
- **Git Commit**：嚴格遵守 Conventional Commits 格式（如 `feat(tasks): ...`, `fix(vision): ...`, `docs: ...`）。
- **乾淨交付**：測試截圖存於 `captures/temp/` 不納入版本控制，提交前確保無語法錯誤。

---

## 4. Python 運行環境規範 (Mandatory Python & Conda Environment)

- **唯一指定 Conda 環境**：**`sd_gundam`**
  - **環境直譯器路徑**：`C:\Users\sharkMeow\miniconda3\envs\sd_gundam\python.exe`
  - **PowerShell 啟用指令**：`conda activate sd_gundam`
- **嚴格執行鐵律 (Mandatory Rule)**：
  - **嚴禁使用 Conda `base` 環境**。
  - **嚴禁私自建立其他零散虛擬環境**（如隨意建 `.venv` 等）。
  - 所有終端指令、測試套件（`pytest`）、任務腳本執行或排程呼叫，**必須嚴格使用 `sd_gundam` 環境**（或直接調用 `C:\Users\sharkMeow\miniconda3\envs\sd_gundam\python.exe`）。
  - 專案已於 `sd_gundam` 中配置 `onnxruntime-directml`，提供 NVIDIA RTX 4070 SUPER GPU 深度學習推論加速。

