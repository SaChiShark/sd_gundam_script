---
name: game-automation-workflow
description: >-
  Standard operating workflow and runbook for developing, debugging, asset capturing,
  and testing mobile game automation scripts for SD Gundam and emulator environments.
---

# Mobile Game Automation Workflow

This skill defines the standardized procedure for engineering new daily tasks, capturing UI visual templates, debugging emulator connectivity, and verifying automation stability in this repository.

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
           # 2. Verify state
           # 3. Tap claim button with randomized offset
           # 4. Handle confirmation dialog
           # 5. Return to Home
           ...
   ```
2. Wrap all clicks with `self.device.tap_template(...)` or `self.device.tap_randomized(...)`.
3. Add randomized delay (`self.device.random_sleep(0.5, 1.2)`).

### Phase 4: Local Verification & Regression Check
1. Run single task verification:
   ```bash
   python main.py --task daily_mailbox --dry-run
   ```
2. Test under edge conditions:
   - What if mail is already claimed (button disabled or greyed out)?
   - What if inventory is full?
   - What if a network loading spinner appears?

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
