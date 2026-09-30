# Contributing Guidelines & Git Standards

感謝您參與本專案的開發！為了維護程式碼品質與跨代理人/跨開發者協作效率，請遵循以下規範。

---

## 1. Git Commit 規則 (Conventional Commits 1.0.0)

本專案全面強制遵守 [Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/) 規範。

### 1.1 Commit Message 格式

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### 1.2 類型 (Type)

| Type | 說明 | 範例 |
| :--- | :--- | :--- |
| **feat** | 新功能或新任務模組 | `feat(tasks): 實作每日信箱一鍵領取` |
| **fix** | 修復 Bug 或適配畫面判定 | `fix(vision): 修正低解析度下模板比對失敗問題` |
| **docs** | 文件異動 | `docs: 更新夜神模擬器 ADB 連接埠設定說明` |
| **style** | 代碼格式調整 (不影響程式邏輯) | `style(core): 符合 flake8 縮排規範` |
| **refactor** | 重構 (非新功能也非修復 Bug) | `refactor(device): 重構截圖二進位管道` |
| **perf** | 效能優化 (如加快截圖或識別) | `perf(vision): 導入灰階預處理加速模板匹配` |
| **test** | 新增或修復測試案例 | `test(vision): 新增合成圖像模板匹配單元測試` |
| **chore** | 雜項事務 (構建工具、依賴更新) | `chore(deps): 升級 rapidocr-onnxruntime 至最新版` |

### 1.3 作用域 (Scope)

建議的作用域：
- `core`: 核心自動化模組
- `device`: ADB 裝置連接與輸入模擬
- `vision`: 影像識別、模板匹配、OCR
- `state`: 狀態機與畫面導航
- `tasks`: 具體遊戲任務模組
- `tools`: 開發者輔助工具 (Inspector、ADB Finder)
- `assets`: 模板圖檔、按鈕素材
- `config`: 設定檔與驗證

### 1.4 Commit 規範要求
1. **Subject**：簡潔描述，結尾不加句號，動詞開頭。
2. **Body**（可選）：若有複雜設計決策或重要背景，於 Body 中詳細說明「Why」而非僅僅「What」。
3. **重大變更 (Breaking Changes)**：若有破壞性重構，於 Footer 標註 `BREAKING CHANGE: <說明>` 或在 Type 後加 `!`（例如 `feat(core)!: 重新設計設備通信接口`）。

---

## 2. 分支管理策略 (Branching Strategy)

- `main`: 穩定發布分支，任何時候都應保持可用狀態。
- `feature/<name>`: 新任務或大型功能開發分支（例如 `feature/daily-sweep`）。
- `fix/<issue>`: 缺陷修復分支（例如 `fix/nox-port-connection`）。

---

## 3. 程式碼規範 (Code Standards)

1. **Python 版本**：Python 3.10+。
2. **靜態型別**：所有公開函式與類別方法必須加上 Type Hints（型別標註）。
3. **日誌輸出**：嚴禁使用 `print()`，全面使用 `loguru.logger`，便於格式化與除錯等級控制。
4. **命名規則**：
   - 模組與檔案名：小寫加底線（`snake_case.py`）
   - 類別名稱：大駝峰（`PascalCase`）
   - 函式與變數：小寫加底線（`snake_case`）
   - 常數：全大寫加底線（`UPPER_SNAKE_CASE`）
5. **例外處理**：避免空的 `except:`，應捕捉具體例外型別並記錄關鍵資訊。
