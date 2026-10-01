"""Standardized Page Management and Exception Handling Engine for SD Gundam."""
import json
import os
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger
from rapidocr_onnxruntime import RapidOCR

from core.device import Device
from core.vision import Vision


class PageType(Enum):
    """Recognized standardized game page types."""
    UNKNOWN = "unknown"                       # 未知/未定義頁面 (觸發例外求助)
    HOME = "home"                             # 主畫面
    DATE_RESET = "date_reset"                 # 換日彈窗 (「日期已改變。將返回主畫面。」)
    LOGIN_BONUS = "login_bonus"               # 每日簽到/活動登入獎勵 (帶「略過」或「TAP TO NEXT」)
    MODAL_INFO = "modal_info"                 # 資訊/道具詳情 (帶中央下方「關閉」按鈕)
    MODAL_CONFIRM = "modal_confirm"           # 確認彈窗 (帶「確定」與「取消」)
    COMM_ERROR = "comm_error"                 # 網路/通訊錯誤 (帶「重試」按鈕)
    TITLE_SCREEN = "title_screen"             # 遊戲啟動標題頁面 (帶「TOUCH TO START」)
    ITEM_ACQUIRED = "item_acquired"           # 結算/獲得道具視窗 (帶「OK」按鈕)
    PERSONAL_BASE = "personal_base"           # 個人基地主畫面
    CHARACTER_REQUESTS = "character_requests" # 角色要求 (總覽/詳情)


class PageManager:
    """
    Standardized Page Classifier and Exception Handling Dispatcher.
    
    Ensures all state transitions, popups, day-resets, and unexpected screens
    are classified deterministically and handled via dedicated handlers,
    falling back to structured user-consultation on unknowns.
    """

    UNKNOWN_DIR: str = "captures/unknown_pages"
    UNKNOWN_LOG: str = "captures/unknown_pages/unknown_pages_log.json"

    def __init__(self, device: Device, vision: Optional[Vision] = None):
        self.device = device
        self.vision = vision or Vision()
        self.ocr = RapidOCR()
        os.makedirs(self.UNKNOWN_DIR, exist_ok=True)

    def _extract_all_text(self, frame: np.ndarray) -> List[Tuple[str, Tuple[int, int], float]]:
        """Run RapidOCR and extract (text, (center_x, center_y), confidence)."""
        res, _ = self.ocr(frame)
        items: List[Tuple[str, Tuple[int, int], float]] = []
        if not res:
            return items
        for box, text, score in res:
            cx = int((box[0][0] + box[2][0]) / 2)
            cy = int((box[0][1] + box[2][1]) / 2)
            items.append((text.strip(), (cx, cy), float(score)))
        return items

    def classify(self, frame: np.ndarray) -> Tuple[PageType, Dict[str, Any]]:
        """
        Deterministically classify current screen using anchors and OCR keywords.
        Returns (PageType, metadata_dict).
        """
        metadata: Dict[str, Any] = {}

        # 1. Check for Home screen via core anchors
        try:
            sortie_roi = frame[580:930, 1250:1920]
            if self.vision.match_template(sortie_roi, "assets/anchors/home_sortie.png", threshold=0.80):
                return PageType.HOME, {"reason": "Matched home_sortie anchor"}
        except (FileNotFoundError, ValueError):
            pass

        # 2. Extract OCR texts for popup/screen classification
        ocr_items = self._extract_all_text(frame)
        all_texts = [item[0] for item in ocr_items]
        combined_text = " ".join(all_texts)
        metadata["ocr_items"] = ocr_items
        metadata["combined_text"] = combined_text

        # 3. Check for Date Reset (換日彈窗)
        if any(kw in combined_text for kw in ["日期已改變", "更新資料", "將返回主畫面", "前往主畫面"]):
            for text, center, _ in ocr_items:
                if "前往主畫面" in text or "主畫面" in text:
                    metadata["btn_home_center"] = center
            return PageType.DATE_RESET, metadata

        # 4. Check for Login Bonus / Daily Sign-in (登入獎勵)
        if any(kw in combined_text for kw in ["LOGIN BONUS", "登入獎勵", "TAP TO NEXT", "送達的配給品"]):
            for text, center, _ in ocr_items:
                if "略過" in text:
                    metadata["skip_btn_center"] = center
            return PageType.LOGIN_BONUS, metadata

        # 5. Check for Title Screen (TOUCH TO START)
        if any(kw in combined_text for kw in ["TOUCH TO START", "TOUCHTOSTART", "資料同步"]):
            return PageType.TITLE_SCREEN, metadata

        # 6. Check for Item Acquired / Skip Result (獲得/結算彈窗)
        if any(kw in combined_text for kw in ["SKIP RESULT", "獲得", "PLAYER RANK EXP"]):
            for text, center, _ in ocr_items:
                if text == "OK":
                    metadata["ok_btn_center"] = center
            return PageType.ITEM_ACQUIRED, metadata

        # 7. Check for Modal Info / Announcement (公告 / 道具詳情 / 資訊彈窗)
        if any(kw in combined_text for kw in ["公告", "道具詳情", "要求資訊", "持有數量"]):
            # Try OCR close button first
            for text, center, _ in ocr_items:
                if "關閉" in text:
                    metadata["close_btn_center"] = center
            # Try template matching for close buttons
            if "close_btn_center" not in metadata:
                for tmpl in ["assets/buttons/btn_close_gray.png", "assets/buttons/btn_close_blue.png"]:
                    try:
                        if match := self.vision.match_template(frame, tmpl, threshold=0.78):
                            metadata["close_btn_center"] = match.center
                            break
                    except (FileNotFoundError, ValueError):
                        pass
            # Positional fallback based on popup type
            if "close_btn_center" not in metadata:
                if "公告" in combined_text:
                    metadata["close_btn_center"] = (960, 915)
                else:
                    metadata["close_btn_center"] = (960, 785)

            return PageType.MODAL_INFO, metadata

        # 8. Check for Modal Confirm (二度確認彈窗)
        if any(kw in combined_text for kw in ["是否確定", "確認執行", "消耗AP"]):
            for text, center, _ in ocr_items:
                if "確定" in text or "執行" in text:
                    metadata["confirm_btn_center"] = center
            return PageType.MODAL_CONFIRM, metadata

        # 9. Check for Communication Error (連線錯誤)
        if any(kw in combined_text for kw in ["通訊錯誤", "連線中斷", "重試", "返回標題"]):
            return PageType.COMM_ERROR, metadata

        # 10. Check for Character Requests (角色要求 總覽或詳情)
        if any("角色要求" in item[0] and item[1][1] < 200 for item in ocr_items):
            return PageType.CHARACTER_REQUESTS, metadata

        # 11. Check for Personal Base (個人基地主頁)
        if any(kw in combined_text for kw in ["出現中要求", "巡視", "房間設定", "出沒中的單位"]):
            return PageType.PERSONAL_BASE, metadata

        # Unrecognized screen
        return PageType.UNKNOWN, metadata

    # -------------------------------------------------------------------------
    # Dedicated Page Handlers
    # -------------------------------------------------------------------------

    def handle_date_reset(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle date change reset popup."""
        logger.info("[PageHandler] 處理換日彈窗：點擊『前往主畫面』...")
        center = metadata.get("btn_home_center", (960, 785))
        self.device.tap(center[0], center[1])
        self.device.random_sleep(3.0, 4.0)
        return True

    def handle_login_bonus(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle login bonus and daily rewards."""
        logger.info("[PageHandler] 處理登入獎勵視窗...")
        if "skip_btn_center" in metadata:
            sx, sy = metadata["skip_btn_center"]
            logger.info(f"[PageHandler] 點擊『略過』按鈕 ({sx}, {sy})...")
            self.device.tap(sx, sy)
        else:
            # Check if top-right skip is present by fallback coordinates
            logger.info("[PageHandler] 點擊右上『略過』(1850, 60) 與畫面中央 (960, 940)...")
            self.device.tap(1850, 60)
            self.device.random_sleep(1.0, 1.5)
            self.device.tap(960, 940)
        self.device.random_sleep(2.0, 2.5)
        return True

    def handle_item_acquired(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle item acquisition / sweep result modal."""
        logger.info("[PageHandler] 處理結算/道具獲得彈窗：點擊『OK』...")
        center = metadata.get("ok_btn_center", (1665, 910))
        self.device.tap(center[0], center[1])
        self.device.random_sleep(1.5, 2.0)
        return True

    def handle_modal_info(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle information / item detail popup."""
        logger.info("[PageHandler] 處理資訊彈窗：點擊中央『關閉』...")
        center = metadata.get("close_btn_center", (960, 785))
        self.device.tap(center[0], center[1])
        self.device.random_sleep(1.5, 2.0)
        return True

    def handle_modal_confirm(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle confirmation modal."""
        logger.info("[PageHandler] 處理確認彈窗：點擊『確定』...")
        center = metadata.get("confirm_btn_center", (1150, 785))
        self.device.tap(center[0], center[1])
        self.device.random_sleep(2.0, 2.5)
        return True

    def handle_comm_error(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle communication error."""
        logger.warning("[PageHandler] 處理通訊錯誤：點擊『重試』...")
        self.device.tap(1150, 785)
        self.device.random_sleep(3.0, 4.0)
        return True

    def handle_title_screen(self, frame: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """Handle title screen entrance."""
        logger.info("[PageHandler] 處理遊戲標題畫面：點擊中央進入...")
        self.device.tap(960, 750)
        self.device.random_sleep(3.0, 4.5)
        return True

    def handle_unknown_page(self, frame: np.ndarray, metadata: Dict[str, Any]) -> None:
        """
        Human-in-the-loop Exception Handling.
        Safely records screenshot, logs OCR data, alerts the terminal,
        and requests user instruction. Never clicks blindly.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_filename = f"unknown_page_{timestamp}.png"
        img_path = os.path.join(self.UNKNOWN_DIR, img_filename)
        cv2.imwrite(img_path, frame)

        ocr_summary = [item[0] for item in metadata.get("ocr_items", [])]

        # Append to json log
        log_entry = {
            "timestamp": timestamp,
            "image_path": img_path,
            "ocr_texts": ocr_summary,
        }
        try:
            entries = []
            if os.path.exists(self.UNKNOWN_LOG):
                with open(self.UNKNOWN_LOG, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            entries.append(log_entry)
            with open(self.UNKNOWN_LOG, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to record unknown page log: {e}")

        # Terminal Alarm Banner
        alert_box = f"""
================================================================================
🛑【PageManager 例外攔截】遇到未定義的遊戲頁面！
- 截圖存檔：{img_path}
- 識別文字：{ocr_summary[:8]}
👉 系統已安全暫停操作，未進行任何盲點嘗試。
👉 請向使用者請教：此頁面的標準處理方式為何？（例如：點擊特定座標、略過、或按返回鍵）
================================================================================
"""
        logger.warning(alert_box)

    # -------------------------------------------------------------------------
    # Unified Dispatcher
    # -------------------------------------------------------------------------

    def resolve_page(
        self,
        frame: Optional[np.ndarray] = None,
        max_attempts: int = 3,
    ) -> Tuple[PageType, bool]:
        """
        Classify and resolve current page using dedicated handlers.
        Returns (PageType, success).
        """
        for attempt in range(1, max_attempts + 1):
            if frame is None or attempt > 1:
                frame = self.device.screencap()

            page_type, metadata = self.classify(frame)
            logger.info(f"[PageManager] 當前畫面判定為: [{page_type.value}] (Attempt {attempt}/{max_attempts})")

            if page_type == PageType.HOME:
                return PageType.HOME, True

            elif page_type == PageType.DATE_RESET:
                self.handle_date_reset(frame, metadata)

            elif page_type == PageType.LOGIN_BONUS:
                self.handle_login_bonus(frame, metadata)

            elif page_type == PageType.ITEM_ACQUIRED:
                self.handle_item_acquired(frame, metadata)

            elif page_type == PageType.MODAL_INFO:
                self.handle_modal_info(frame, metadata)

            elif page_type == PageType.MODAL_CONFIRM:
                self.handle_modal_confirm(frame, metadata)

            elif page_type == PageType.COMM_ERROR:
                self.handle_comm_error(frame, metadata)

            elif page_type == PageType.TITLE_SCREEN:
                self.handle_title_screen(frame, metadata)

            elif page_type == PageType.UNKNOWN:
                self.handle_unknown_page(frame, metadata)
                return PageType.UNKNOWN, False

            # Check if resolved to Home
            check_frame = self.device.screencap()
            new_type, _ = self.classify(check_frame)
            if new_type == PageType.HOME:
                logger.success("[PageManager] 畫面已成功收斂至 Home 主頁面。")
                return PageType.HOME, True

        return page_type, False
