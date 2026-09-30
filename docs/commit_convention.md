# Commit Message 規範詳細手冊

本手冊為本專案版本控制與 Git Commit 的完整實作指引，所有貢獻者與 AI Agent 均須嚴格遵照本手冊規範。

---

## 1. 規範核心理念

- **自解釋性**：只看 commit 標題就能明確知道這次變更的性質與受影響的模組。
- **便於自動生成變更日誌 (Changelog)**：格式規範化以便日後自動提取版本發行紀錄。
- **原子性提交 (Atomic Commits)**：一個 Commit 只做一件事，嚴禁將不相關的重構、修復與新功能雜糅在同一個 Commit。

---

## 2. Commit 訊息結構

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### 2.1 Type（類型）

| 類型 | 說明 | 適用場景範例 |
| :--- | :--- | :--- |
| `feat` | 新增功能 | 新增「每日友情抽卡」任務模組、新增 ADB 端口自動探測器 |
| `fix` | 修復問題 | 修復特定解析度下 OCR 辨識偏差、修復點擊未考慮隨機偏移 |
| `docs` | 文件變更 | 修改 README、更新開發指引、補充 API 註解 |
| `style` | 格式美化 | 調整縮排、移除多餘空白行、修正 lint 格式警告（不改變邏輯） |
| `refactor`| 程式碼重構 | 重構 `vision.py` 匹配演算法提高可讀性、重組目錄結構 |
| `perf` | 效能優化 | 將原生 ADB 截圖改為 `exec-out` 二進位管道加速 10 倍 |
| `test` | 測試相關 | 新增模板比對單元測試、新增 Mock 模擬器設備測試 |
| `chore` | 維護雜項 | 更新 `.gitignore`、升級 `requirements.txt` 依賴套件版本 |

### 2.2 Scope（作用域）

作用域必須使用圓括號包覆，表示該次變更所涉及的主要子系統或資料夾：
- `core`: 通用自動化引擎、排程、基礎狀態機
- `device`: ADB 通信、觸控模擬、截圖傳輸
- `vision`: OpenCV 模板匹配、RapidOCR、影像預處理
- `state`: 狀態導航、畫面判定、彈窗攔截
- `tasks`: 具體遊戲日常任務邏輯
- `tools`: 開發者調試工具 (如 Inspector、ADB 探測工具)
- `assets`: 圖片素材、錨點、按鈕模板
- `config`: 設定檔載入與 Schema 驗證
- `deps`: 專案外部相依套件

### 2.3 Subject（主旨）

- 以簡潔明瞭的文字描述「做了什麼」。
- 繁體中文或英文皆可（繁體中文更直觀，推薦以繁體中文撰寫）。
- 長度建議在 50 字元以內。
- 結尾**不要加句號**。

---

## 3. 正面範例 (Good Examples)

```
feat(tasks): 新增每日免費轉蛋與友情抽卡任務

- 實作 FreeGachaTask 流程
- 支援抽卡完成後的「再抽一次」與關閉判定
- 增加抽卡動畫跳過點擊
```

```
perf(device): 改用 exec-out screencap 二進位串流優化截圖延遲

將原本 adb shell screencap -p 的 1500ms 傳輸延遲降低至 80ms 內。
```

```
fix(vision): 解決高 DPI 縮放導致模板匹配座標偏移問題
```

---

## 4. 負面範例 (Bad Examples)

❌ `update code` (完全無意義的訊息)  
❌ `fix bug` (未指明修復了什麼、哪裡的 Bug)  
❌ `feat: 新增任務且修復了截圖問題並調整了格式` (違反原子性提交原則，應拆分為多個 commit)  
❌ `WIP` (未完成的髒代碼不可直接提交到主分支)  
