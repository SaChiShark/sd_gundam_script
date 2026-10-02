---
name: yolo-ui-detection
description: >-
  Standard protocol, toolchain, and runtime engine for GPU-accelerated YOLO object detection
  of SD Gundam UI elements on NVIDIA RTX 4070 SUPER. Completely eliminates coordinate guesswork
  and blind clicking, paired with fail-safe manual agent intervention upon exceptions.
---

# YOLO UI Detection & Anti-Blind-Click Skill

This skill defines the engineering standard, runtime integration, and runbook for **deterministic, sub-millisecond game UI element localization** using **YOLO (v8 / v11 / ONNX DirectML)** accelerated by the local **NVIDIA GeForce RTX 4070 SUPER**, replacing mental coordinate guesswork and VLM hallucinations with exact bounding-box geometry.

---

## 1. Core Engineering Motivation

### 🛑 徹底廢除「肉眼心算座標」與「盲點猜測」
手遊自動化中最嚴重的崩潰源自以下連鎖反應：
1. **空間坐標幻覺 (Hallucination)**：AI Agent 僅憑肉眼概估座標（如誤將機體算成空地 `(415, 450)`），導致點擊發送至空白宇宙背景。
2. **粒子動畫偽陽性 (Particle False-Positive)**：以全畫面像素差判定是否點擊成功時，遊戲呼吸燈或背景粒子動畫造成 `diff > 0` 誤判，腳本誤以為成功而盲目推進下一步。
3. **跨關卡佈局漂移 (Layout Drift)**：不同系列（W、SEED、UC 等）的開發樹機體排列不同，寫死座標必定破功。

### 🎯 YOLO 解決方案的技術優勢（RTX 4070 SUPER 實測）
- **超低延遲**：推論耗時僅 **2 ~ 5 毫秒**，完全不卡頓遊戲流程。
- **絕對確定性 (Determinism)**：輸出剛性邊界框 `[x1, y1, x2, y2]` 與置信度，絕無生成式語言模型的文字幻覺。
- **抗光影干擾**：卷積神經網路能精確辨識目標實體邊界，不受半透明底色或星空粒子干擾。

---

## 2. 系統架構與閉環工作流 (Architecture & Workflow)

```mermaid
flowchart TD
    Capture["1. 獲取實機畫面<br>(dev.screencap 1920x1080)"] --> YOLO["2. GPU 加速推論 (YOLOUIDetector)<br>(NVIDIA RTX 4070 SUPER / 3ms)"]
    
    YOLO --> ConfCheck{"置信度 Check<br>Conf >= 0.60 ?"}
    
    ConfCheck -->|是: 成功鎖定目標| Calc["3. 計算邊界框幾何中心 (cx, cy)"]
    Calc --> Tap["4. 發送擬人化點擊<br>(Device.tap + Gaussian Jitter)"]
    Tap --> StateCheck{"5. 閉環驗證 (State Transition Guard)<br>PageManager 狀態是否轉移？"}
    
    StateCheck -->|成功轉移| Next["推進至下一步狀態 ✅"]
    StateCheck -->|未轉移 / 點空| Retry["原地微調重試 (±20px)"]
    
    ConfCheck -->|否: 目標缺失 / 未知畫面| Exception["🚨 觸發安全防護 (AGENTS.md 守則 4 & 5)"]
    Retry -->|重試失敗| Exception
    
    Exception --> Safety["自動存檔截圖至 captures/exceptions/<br>終端蜂鳴警報 / 記錄 Log<br>暫停腳本，等待使用者指示 Agent 介入 🛑"]
```

---

## 3. UI 元素類別定義 (Class Taxonomy)

YOLO 模型針對 SD Gundam 遊戲介面收斂為以下核心類別：

| 類別名稱 (`class_name`) | 說明 | 典型出現位置 | 處理策略 |
|---|---|---|---|
| `btn_accept` | 承接按鈕（藍色） | 角色要求詳情右下 `(1623, 800)` | 點擊中心並略過對話 |
| `btn_challenge` | 挑戰按鈕（藍色） | 進行中要求右下 `(1623, 800)` | 點擊中心直達路線圖 |
| `btn_report` | 報告按鈕（橘色） | 完成要求右下 `(1623, 858)` | 點擊領取獎勵 |
| `btn_deliver` | 交付按鈕（橘色/藍色）| 交付彈窗右下 `(1160, 955)` | 點擊提交機體/資金 |
| `btn_confirm` | 確定 / 執行按鈕 | 各類確認彈窗 `(1148, 996)` | 點擊確認操作 |
| `btn_cancel` | 取消按鈕 | 各類取消操作 `(772, 995)` | 取消操作返回上一層 |
| `btn_skip` | 略過按鈕（右上） | 故事與角色對話 `(1768, 68)` | 跳過劇情與對話 |
| `btn_trash` | 垃圾桶按鈕 | 角色要求詳情右上 `(1752, 182)` | 捨棄任務觸發 |
| `unit_r` | 一階 R 機體實體 | 開發路線圖各分支起始節點 | 點擊本體打開生產介面 |
| `badge_rarity` | 機體階級標籤（R/SR/SSR）| 機體節點下方 | 作為幾何錨點計算 |

---

## 4. 腳本整合規範 (Script Integration Runbook)

### 規則 1：禁止在任務中使用裸座標 (No Raw Coordinates)
所有任務方法（繼承自 `BaseTask`）若需點擊介面元件，**嚴禁硬編碼 (x, y)**，必須透過 `YOLOUIDetector` 或其語意封裝器取得座標：

```python
# ❌ 嚴禁寫法 (盲猜座標)
device.tap(815, 485)

# ✅ 標準規範寫法
from tools.yolo_detector import YOLOUIDetector

detector = YOLOUIDetector()
elements = detector.detect(frame)
target = detector.find_target(frame, target_class="unit_r")

if target:
    cx, cy = target.center
    device.tap(cx, cy)
else:
    # 觸發例外處置
    self.handle_exception(frame, "unit_r not found")
```

### 規則 2：點擊前後閉環驗證 (Closed-Loop Guard)
點擊必須搭配 `PageManager` 驗證狀態是否發生實質轉移，杜絕「連鎖空點」：

```python
# 透過 StateMachine 提供的閉環點擊方法
success = self.fsm.tap_and_wait_transition(
    target_coords=target.center,
    expected_page=PageType.MODAL_CONFIRM,
    timeout=4.0
)
if not success:
    logger.error("點擊未促發預期介面轉移，立即中斷防止失控！")
    return False
```

---

## 5. 例外安全守則與人工 Agent 介入協議 (Human-in-the-Loop Guardrail)

符合 `AGENTS.md` 核心守則第 4 條與第 5 條：

### 🛑 自動觸發條件：
1. 目標類別置信度低於門檻（`< 0.60`）。
2. 連續 2 次點擊後畫面狀態未發生跳轉。
3. `PageManager.classify` 判定為 `UNKNOWN` 頁面。

### 🚨 處置標準程序 (SOP)：
1. **立即鎖定保護**：中斷任何後續 ADB 點擊指令，絕不在未知畫面上盲點。
2. **截圖存證**：自動將完整高解析度畫面存至 `captures/exceptions/exception_YYYYMMDD_HHMMSS.png`。
3. **終端告警**：輸出清晰結構化資訊，包含當前狀態機狀態、已嘗試動作與影像路徑。
4. **交回主控權**：暫停並等待使用者在終端指示 AI Agent 進行手動介入修復：
   > 「發現未知異常畫面，系統已安全停機存檔於 `captures/exceptions/...`。請向使用者請教處理方式或由 Agent 手動確認。」

---

## 6. 資料集建立與 RTX 4070 SUPER 訓練指南

專案已內建全自動工具集，支援一鍵準備與訓練：

### 步驟 1：收集實機樣本
```bash
python tools/dataset_builder.py
```
* 自動掃描 `captures/` 目錄，將候選畫面整理至 `datasets/gundam_ui/raw_to_label/`。

### 步驟 2：標註資料 (Labeling)
* 使用 [Labelme](https://github.com/wkentaro/labelme) 或 [AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 開啟 `raw_to_label/`，依據第 3 節類別框選標籤，輸出成 YOLO 格式存於 `datasets/gundam_ui/labels/train/`。

### 步驟 3：在 RTX 4070 SUPER 上微調訓練
```python
from ultralytics import YOLO

# 載入 YOLOv11-nano 預訓練權重
model = YOLO("yolo11n.pt")

# 利用 RTX 4070 SUPER 進行極速微調 (約需 3 分鐘)
model.train(
    data="datasets/gundam_ui/data.yaml",
    epochs=50,
    imgsz=640,
    batch=16,
    device=0  # 指定 RTX 4070 SUPER
)

# 匯出為 ONNX 格式以供 DirectML 高性能推論
model.export(format="onnx")
```
* 訓練完成後將 `best.onnx` 複製至 `models/yolo11n_ui.onnx`，系統將自動無縫切換為純 GPU 深度學習檢測模式！
