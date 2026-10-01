# AGENTS.md - AI Agent Operating Guide

This repository contains the automation suite for mobile game operations, specifically targeted at *SD Gundam G Generation ETERNAL* (and compatible gacha/strategy mobile games) using non-invasive ADB and Computer Vision.

All AI agents (Antigravity, Gemini, etc.) working on this repository MUST strictly follow the principles, coding standards, and engineering rules outlined in this document.

---

## 1. Core Engineering Principles

1. **Pre-Execution Planning (執行前規劃 - Mandatory)**
   - Before performing multi-step actions, code refactors, or live emulator interactions, the AI Agent MUST first present a clear, structured execution plan to the user.
   - Do NOT perform arbitrary, unannounced trial-and-error actions or blind clicks on live accounts. Proceed only after the plan is aligned and confirmed.
2. **Consult User for Game Mechanics (優先詢問使用者遊戲機制 - Mandatory)**
   - Whenever encountering unfamiliar game flows, stage rules, currency/cost mechanics, or UI navigation logic, the AI Agent MUST **first consult the user** to understand the game mechanisms, rather than blindly clicking around or guessing via live trial-and-error on the emulator.
   - The user possesses direct gameplay and domain knowledge. Clarifying game rules upfront prevents unnecessary resource consumption, eliminates risky trial taps, and ensures precise implementation.
3. **Real-Time Operational Transparency (執行過程中即時回報操作)**
   - The AI Agent and automation scripts MUST explicitly output and log what action is currently being executed at every stage (e.g., current UI state, target button, OCR match result, coordinate tapped, waiting status).
   - Never perform actions silently in the background without informing the user what is happening.
4. **Non-Invasive UI Automation (Black-box Only)**
   - Never inject DLLs, read/write game process memory, or decrypt/forge network packets.
   - Rely solely on screen capture (ADB / streaming), computer vision (Template Matching / OCR), and simulated touch inputs (ADB input).
5. **Human-like Simulation & Anti-Detection**
   - **No absolute single-pixel clicks**: Always randomize coordinates within the target UI bounding box (Gaussian or uniform random with safety padding).
   - **No constant sleep timings**: Always introduce random jitter delays (`random.uniform(min, max)`).
   - **Smooth swipe trajectories**: Use Bezier curve interpolation for swipe motions rather than instantaneous linear teleportation.
6. **Resilience & State-Driven Control (No Hardcoded Time Sequences)**
   - Never chain blind clicks using fixed `time.sleep()`. All state transitions must be verified by UI anchors or template/text matching.
   - Implement global popup interceptors (announcements, login rewards, disconnect notices) before task actions.
   - Include auto-recovery: If the script is lost in an unknown state for >30s, iteratively press `BACK` until a known anchor (Home screen) is reached.
7. **Unknown Task Safety Guardrail (未辨識任務安全防護)**
   - If an unrecognized, unseen, or unsupported task requirement is detected during automated workflows, the script MUST:
     1. Automatically capture and save a full screenshot to `captures/unknown_tasks/{timestamp}_{name}.png`.
     2. Record the metadata and raw OCR text to `captures/unknown_tasks/unknown_tasks_log.json`.
     3. Output an alert in the terminal/log to notify the user.
     4. Safely return to the previous screen without blind clicking.
8. **Modularity & Extensibility**
   - Tasks must inherit from `BaseTask` and remain decoupled from one another.
   - New daily routines can be toggled on/off independently via configuration.

---

## 2. Codebase Organization

```
sd_gundam_script/
├── .agents/
│   └── skills/                  # Antigravity project skills & runbooks
├── assets/                      # Visual templates & anchors
│   ├── anchors/                 # Unique screen identification templates
│   ├── buttons/                 # Clickable UI elements (OK, Close, Start)
│   └── icons/                   # Resource & category indicators
├── core/                        # Core automation engine
│   ├── device.py                # ADB connection, screencap, input emulation
│   ├── vision.py                # Template matching, RapidOCR, pixel check
│   ├── state_machine.py         # UI state tracker & navigation graph
│   └── config.py                # Pydantic configuration loader
├── tasks/                       # Concrete task workflows
│   ├── base.py                  # BaseTask abstract class
│   ├── daily_login.py           # Login rewards & popup clearing
│   ├── mailbox.py               # Collect mail / stamina
│   ├── gacha.py                 # Free daily pulls
│   └── sweep.py                 # Daily resource stage sweeps
├── tools/                       # Developer utilities
│   ├── inspector.py             # Template cropper & coordinate inspector
│   └── adb_finder.py            # Auto-detect running emulator ports
├── tests/                       # Unit & integration tests (with mock frame inputs)
├── docs/                        # Architecture & contribution documentation
├── AGENTS.md                    # Agent guidelines (this file)
├── CONTRIBUTING.md              # Git commit & contributor conventions
├── README.md                    # Project documentation
└── requirements.txt             # Project dependencies
```

---

## 3. Python Coding Standards

- **Language Version**: Python 3.10+
- **Type Annotations**: Mandatory on all public functions, methods, and dataclass fields.
- **Logging**: Use `loguru.logger` for all diagnostic and operational outputs. **Do not use `print()`**.
- **Error Handling**: Use custom exception types (e.g., `DeviceConnectionError`, `StateTimeoutError`, `TemplateNotFoundError`). Do not silently swallow exceptions.
- **Docstrings**: Google or Sphinx format for all classes and non-trivial methods.

---

## 4. Git Commit & PR Conventions

Every commit message must strictly comply with **Conventional Commits v1.0.0**:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Allowed Types:
- `feat`: A new feature or task routine (e.g., `feat(tasks): add daily mailbox collection`)
- `fix`: A bug fix (e.g., `fix(vision): handle multi-scale template matching edge case`)
- `docs`: Documentation updates (e.g., `docs: update setup guide for Nox emulator`)
- `style`: Formatting, missing semi-colons, no code logic change
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance (e.g., screencap speedup)
- `test`: Adding missing tests or correcting existing tests
- `chore`: Maintenance, dependency updates, tooling configuration

### Allowed Scopes:
`core`, `device`, `vision`, `state`, `tasks`, `tools`, `assets`, `config`, `deps`.

---

## 5. Verification & Testing Protocol

Before considering any task complete:
1. **Lint & Static Check**: Code must be free of syntax errors and unimported references.
2. **Device / Mock Verification**:
   - If emulator is available: Verify connection via `tools/adb_finder.py`.
   - If emulator is unavailable: Provide mock frames or synthetic image unit tests in `tests/`.
3. **Commit Cleanliness**: Stash or ignore temporary test screenshots in `captures/temp/`.
