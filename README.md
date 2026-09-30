# SD Gundam Script - 《SD 鋼彈 G 世代 永恆》自動化日常任務腳本

[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

本專案是一套專為手遊《SD 鋼彈 G 世代 永恆》（SD Gundam G Generation ETERNAL）設計的現代化、模組化、無侵入式日常任務自動化腳本。

---

## 📖 目錄

- [專案特色](#-專案特色)
- [軟體架構與工程規範](#-軟體架構與工程規範)
- [支援模擬器與環境推薦](#-支援模擬器與環境推薦)
- [快速開始](#-快速開始)
- [日常任務模組規劃](#-日常任務模組規劃)
- [專案結構](#-專案結構)
- [貢獻與協作](#-貢獻與協作)

---

## 🌟 專案特色

1. **無侵入式黑盒架構**：僅依靠 ADB 截圖與觸控操作，不修改內存、不解密封包，極致安全防封。
2. **狀態驅動與自癒導航**：使用畫面錨點（Anchor Points）及有限狀態機（FSM），徹底擺脫脆弱的死板 `time.sleep()` 延遲。
3. **人類操作擬真機制**：
   - 點擊座標高斯隨機偏移（防機械點擊）。
   - 貝茲曲線滑動模擬（防勻速直線軌跡）。
   - 動作間隔動態擾動（防定時心跳檢測）。
4. **全域彈窗攔截器**：自動處理每日簽到、活動公告、斷線重試等突發彈窗，確保流程順暢不卡死。
5. **模組化任務插拔**：各日常任務（信箱、抽卡、體力掃蕩、成就領取）獨立解耦，可於設定檔自由開關。

---

## 📐 軟體架構與工程規範

本專案遵照嚴格的軟體工程規範進行維護：

- **系統架構詳解**：請參閱 [docs/architecture.md](docs/architecture.md)。
- **AI Agent 與協作指引**：請參閱 [AGENTS.md](AGENTS.md) 與 [agent.md](agent.md)。
- **Git Commit 規範**：強制遵循 Conventional Commits 1.0.0，詳見 [CONTRIBUTING.md](CONTRIBUTING.md) 與 [docs/commit_convention.md](docs/commit_convention.md)。
- **自動化開發流程 Skill**：請參見 [.agents/skills/game-automation-workflow/SKILL.md](.agents/skills/game-automation-workflow/SKILL.md)。

---

## 🖥️ 支援模擬器與環境推薦

本腳本透過標準 ADB 通信，推薦使用主流 Android 模擬器：

| 模擬器 | 預設 ADB 端口 | 推薦度 | 備註 |
| :--- | :--- | :---: | :--- |
| **夜神模擬器 (Nox)** | `127.0.0.1:62001` | ⭐⭐⭐⭐ | 經典穩定，支援背景執行 |
| **MuMu 模擬器 12** | `127.0.0.1:16384` | ⭐⭐⭐⭐⭐ | 效能優越、資源佔用低 |
| **雷電模擬器 9 (LDPlayer)** | `127.0.0.1:5555` | ⭐⭐⭐⭐⭐ | 啟動快速、ADB 支援完善 |
| **Google Play 遊戲 PC 版** | 動態端口 | ⭐⭐ | 需透過 Windows API 捕獲或特殊除錯，不可背景最小化 |

> [!TIP]
> 建議將模擬器解析度統一設定為 **1920x1080 (橫屏, 16:9, DPI: 320 或 280)**，以確保模板比對最佳精準度。

---

## 🚀 快速開始

### 1. 建立虛擬環境與安裝依賴

```bash
# 建立 Python 3.10+ 虛擬環境
python -m venv venv

# 啟動虛擬環境 (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 安裝相依套件
pip install -r requirements.txt
```

### 2. 檢測模擬器連線

確保模擬器已開啟並啟動遊戲，執行 ADB 探測工具：

```bash
python tools/adb_finder.py
```

### 3. 採集遊戲按鈕素材 (Inspector)

手動導航至欲自動化的介面，使用檢視器截取目標按鈕或圖標：

```bash
python tools/inspector.py
```

---

## 📋 日常任務模組規劃

- [ ] `daily_login`: 登入獎勵領取與全域彈窗清理
- [ ] `mailbox`: 信箱體力與道具一鍵領取
- [ ] `free_gacha`: 每日免費轉蛋與友情點數抽取
- [ ] `resource_sweep`: 每日資金與素材關卡掃蕩
- [ ] `daily_mission`: 每日任務成就完成進度與獎勵領取
- [ ] `auto_scheduler`: 定時喚醒與體力溢出預警

---

## 📁 專案結構

```text
sd_gundam_script/
├── .agents/skills/          # Antigravity 專案專用技能與操作手冊
├── assets/                  # 視覺辨識資源庫
│   ├── anchors/             # 介面識別特徵圖
│   ├── buttons/             # 點擊按鈕模板圖
│   └── icons/               # 道具與標籤圖示
├── core/                    # 自動化引擎核心
│   ├── device.py            # ADB 連線、截圖與擬真觸控
│   ├── vision.py            # OpenCV 模板匹配與 RapidOCR
│   ├── state_machine.py     # 狀態機與畫面導航邏輯
│   └── config.py            # 設定檔載入器
├── tasks/                   # 具體任務實作
│   └── base.py              # 任務抽象基類
├── tools/                   # 開發與調試輔助工具
│   ├── adb_finder.py        # 模擬器端口自動掃描工具
│   └── inspector.py         # 畫面與座標採集工具
├── docs/                    # 軟體工程架構與 commit 規範手冊
├── tests/                   # 單元測試集
├── AGENTS.md                # AI Agent 開發守則
├── CONTRIBUTING.md          # 貢獻與 Commit 指南
├── requirements.txt         # 依賴套件表
└── README.md                # 專案首頁
```

---

## 🤝 貢獻與協作

歡迎提出 Issue 或 Pull Request！提交程式碼前請務必遵循 [CONTRIBUTING.md](CONTRIBUTING.md) 所規範的 commit 格式與工程標準。
