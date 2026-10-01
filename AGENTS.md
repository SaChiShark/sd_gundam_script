# AGENTS.md - AI Agent Operating Guide

## 1. 核心行為守則 (Core Agent Rules - Mandatory)

1. **執行前規劃 (Pre-Execution Planning)**
   - 進行多步驟操作、代碼重構或模擬器互動前，**必須先呈報清晰計畫**。嚴禁未經確認擅自盲試或在帳號上盲點。
2. **關鍵流程主動請示 (Interactive Consultation & Consult First)**
   - 遇到不熟悉的關卡規則、資源消耗或 UI 流程，**必須先向使用者請教**，嚴禁以實機盲點猜測機制。
   - 即使是正常執行流程（Process），在各關鍵節點（如選擇目標、消耗資源、確認操作前）皆可主動截圖展示並向使用者請示確認，確保每一步完全符合預期。
3. **執行過程即時回報 (Real-Time Transparency)**
   - 執行期間必須即時輸出當前操作細節（UI 狀態、點擊座標、OCR 辨識結果、等待狀態），絕不在背景靜默操作。
4. **未辨識任務安全防護 (Unknown Task Safety Guardrail)**
   - 偵測到未知或未支援任務時：自動截圖存至 `captures/unknown_tasks/`、記錄 Log、發出終端警報並安全返回，絕不盲點。
5. **標準化頁面處理與例外求助 (Standardized Page Management & Exception Handling)**
   - 頁面判斷必須透過標準化分類器與專屬 Handler 處理，**嚴禁各任務各自私下獨立處理**。
   - 狀態機遇到例外或不確定畫面時：自動截圖存至 `captures/unknown_pages/`、記錄 Log，並**主動停下來向使用者請教處理方式**，絕不擅自盲試。

---

## 2. 自動化與防封規範 (Technical Standards)

- **非侵入黑盒 (Black-box Only)**：僅使用 ADB 截圖與模擬點擊，不碰記憶體或封包。
- **擬真與防封 (Anti-Detection)**：點擊必須包含隨機座標偏移，等待時間隨機化，滑動使用曲線軌跡。
- **狀態驅動控制 (State-Driven)**：禁止固定秒數盲睡，所有跳轉必須以 UI 錨點或 OCR 驗證；若卡死超過 30 秒自動退回主畫面。
- **統一頁面管理 (PageManager)**：彈窗、換日、簽到與例外狀態統一由 `core/page_manager.py` 處理，拒絕獨立各搞一套。
- **模組化架構**：任務皆繼承 `BaseTask`，彼此獨立解耦。

---

## 3. 開發與提交標準 (Coding & Commit)

- **語言與記錄**：Python 3.10+、強制型別標註、統一使用 `loguru.logger`（嚴禁 `print()`）。
- **Git Commit**：嚴格遵守 Conventional Commits 格式（如 `feat(tasks): ...`, `fix(vision): ...`, `docs: ...`）。
- **乾淨交付**：測試截圖存於 `captures/temp/` 不納入版本控制，提交前確保無語法錯誤。
