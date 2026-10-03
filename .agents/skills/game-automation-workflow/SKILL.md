---
name: game-automation-workflow
description: >-
  Standard operating workflow and runbook for developing, debugging, asset capturing,
  and testing mobile game automation scripts for SD Gundam and emulator environments.
---

# Mobile Game Automation Workflow

This skill defines the standardized procedure for engineering new daily tasks, capturing UI visual templates, debugging emulator connectivity, and verifying automation stability in this repository.

---

## 0. Mandatory Runtime Environment

All automation development, inspection scripts, and testing **MUST** be executed within the dedicated Conda environment:
- **Conda Environment**: `sd_gundam`
- **Activation Command**: `conda activate sd_gundam`
- **Interpreter Path**: `C:\Users\sharkMeow\miniconda3\envs\sd_gundam\python.exe`
- **Prohibition**: NEVER use the conda `base` environment or arbitrary ad-hoc virtual environments.

---

## 1. Development Lifecycle for a New Daily Task

When adding or updating a game task (e.g., Mailbox, Daily Gacha, Stage Sweep):

### Phase 1: Target Screen Analysis & Asset Capture
1. Launch the emulator (e.g. Nox, MuMu, LDPlayer) and navigate manually to the target screen.
2. Use the visual asset inspector:
   ```bash
   python tools/inspector.py
   ```
   - Crop the essential button/icon anchors (e.g., `btn_claim_all.png`, `icon_mail.png`).
   - Save the asset into the corresponding directory under `assets/` (e.g., `assets/buttons/` or `assets/anchors/`).
   - Note the expected confidence threshold (typically `0.80` - `0.85`).

### Phase 2: State Identification & Anchor Registration
1. Identify the unique visual anchor that proves the screen is loaded.
2. Register the anchor in `core/state_machine.py`:
   - Define the state enum (e.g., `GameState.MAILBOX`).
   - Associate the anchor template or OCR keyword.

### Phase 3: Implement the Task Class
1. Inherit from `BaseTask` in `tasks/<task_name>.py`:
   ```python
   from tasks.base import BaseTask
   
   class DailyMailboxTask(BaseTask):
       name = "daily_mailbox"
       
       def run(self) -> bool:
           # 1. Navigate to Mailbox
           # 2. Verify state via PageManager or vision anchor
           # 3. Locate dynamic target using CV/YOLO:
           #    self.fsm.locate_and_tap_target("btn_claim_all", fallback_anchor=(1600, 900))
           #    OR match = self.vision.match_template(frame, "assets/buttons/btn_claim.png")
           #       if match: self.device.tap_rect(match.rect)
           # 4. Handle confirmation dialog via PageManager
           # 5. Return to Home safely
           ...
   ```
2. **按鈕點擊實作守則 (Button Interaction Guidelines)**：
   - **固定按鈕**：使用 `self.device.tap(x, y)`（自帶高斯隨機擾動與擬真延遲），座標必須引用自 `NavigationCoords`。
   - **動態按鈕**：強制使用 CV（優先 `StateMachine.locate_and_tap_target()` 呼叫 GPU YOLO 模型，次選模板匹配 `Vision.match_template()` + `Device.tap_rect()` 或 OCR 定位）。嚴禁在未辨識的情況下直接點擊裸座標！
   - **未知流程請示守則**：若任務涉及未定義或不確定的操作流程（如不清楚強化或掃蕩規則），**強制規定先向使用者請教具體流程**，絕不允許私自撰寫假邏輯或盲點盲試。
3. Add randomized delay (`self.device.random_sleep(0.5, 1.2)`).

### Phase 4: PageType & PageManager 整合 SOP
若新任務涉及新遊戲畫面或彈窗，必須按以下 4 步標準流程納入集中管理：
1. **宣告類型**：於 `core/page_manager.py` 的 `PageType` Enum 登記新列舉值。
2. **畫面分類**：在 `PageManager.classify()` 增加對應特徵判定（結合視覺錨點、YOLO 與 RapidOCR 關鍵字）。
3. **專屬處置**：編寫專屬 `handle_<page_type>()` 處理常態確認、關閉或跳過。
4. **註冊派遣**：於 `PageManager.resolve_page()` 加入該頁面類型之處理分支。

### Phase 5: Local Verification & Regression Check
1. Run single task verification:
   ```bash
   python main.py --task <task_name>
   # 或透過專屬腳本驗證：
   python scripts/<step_script>.py
   ```
2. Test under edge conditions:
   - What if mail is already claimed (button disabled or greyed out)?
   - What if inventory is full?
   - What if a network loading spinner or resource download appears?

---

## 2. Emulator Connectivity & ADB Troubleshooting

If connection fails or screencap times out:
1. Run the ADB finder utility:
   ```bash
   python tools/adb_finder.py
   ```
2. Common Emulator ADB Ports:
   - **Nox App Player**: `127.0.0.1:62001` (Instance 1: `62025`)
   - **MuMu Player 12**: `127.0.0.1:16384`
   - **LDPlayer 9**: `127.0.0.1:5555`
   - **BlueStacks 5**: `127.0.0.1:5555` (or check bluestacks.conf)
3. Ensure the emulator display resolution is fixed to **1920x1080** (Landscape, 16:9) or **1280x720**.

---

## 3. Commit & Documentation Standards

- Always run `pytest` before committing code changes.
- Ensure all commit messages strictly follow the Conventional Commits specification outlined in `CONTRIBUTING.md`.
