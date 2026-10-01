"""Finite State Machine and Navigation Engine for SD Gundam."""
import time
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.vision import Vision, MatchResult


class GameState(Enum):
    """Recognized high-level game screens."""
    UNKNOWN = auto()
    TITLE_SCREEN = auto()           # 遊戲啟動登入/標題畫面 (TOUCH TO START)
    POPUP_ANNOUNCEMENT = auto()     # 活動公告/營運彈窗
    LOGIN_BONUS = auto()            # 每日登入獎勵簽到
    HOME = auto()                   # 主頁面 (包含三大核心特徵錨點)
    PERSONAL_BASE = auto()          # 個人基地主頁面
    CHARACTER_REQUESTS = auto()     # 角色要求 (總覽/詳情)
    SORTIE_SELECT = auto()          # 出擊關卡選擇畫面
    BATTLE = auto()                 # 戰鬥中
    RESULT = auto()                 # 戰鬥結算


class NavigationCoords:
    """Standard calibrated UI navigation touch targets (1920x1080 baseline)."""
    # Bottom Navigation Bar
    BOTTOM_NAV: Dict[str, Tuple[int, int]] = {
        "home": (198, 1020),
        "enhance": (456, 1020),
        "develop": (714, 1020),
        "stages": (1003, 1020),
        "personal_base": (1292, 1020),
        "gacha": (1549, 1020),
        "menu": (1807, 1020),
    }

    # Top-Left Header Navigation
    BACK_BUTTON: Tuple[int, int] = (65, 55)

    # Personal Base Entrances
    BASE_CHARACTER_REQUESTS_BANNER: Tuple[int, int] = (1510, 315)

    # Character Requests Overview 3-Slot Cards
    CHAR_REQ_SLOT_CARDS: List[Tuple[int, int]] = [
        (220, 400),  # Slot 1
        (500, 400),  # Slot 2
        (780, 400),  # Slot 3
    ]

    # Character Requests Detail Card Navigation Arrows
    CHAR_REQ_ARROW_PREV: Tuple[int, int] = (30, 490)
    CHAR_REQ_ARROW_NEXT: Tuple[int, int] = (1888, 490)


class HomeAnchorROI:
    """
    Standard Regions of Interest (ROI) for Home screen recognition (1920x1080 baseline).
    
    Verified Core Anchors:
    1. TOP_LEFT_LEVEL: 玩家等級圖示 (x: 0, y: 0, w: 300, h: 150)
    2. TOP_RIGHT_STAMINA: 體力/AP膠囊圖示 (x: 1100, y: 0, w: 300, h: 150)
    3. BOTTOM_RIGHT_SORTIE: 右下角核心「出擊」按鈕 (x: 1250, y: 580, w: 670, h: 350)
    """
    TOP_LEFT_LEVEL: Tuple[int, int, int, int] = (0, 0, 300, 150)
    TOP_RIGHT_STAMINA: Tuple[int, int, int, int] = (1100, 0, 300, 150)
    BOTTOM_RIGHT_SORTIE: Tuple[int, int, int, int] = (1250, 580, 670, 350)



from core.page_manager import PageManager, PageType


class StateMachine:
    """Tracks game UI state and orchestrates autonomous navigation."""

    def __init__(self, device: Device, vision: Optional[Vision] = None):
        self.device = device
        self.vision = vision or Vision()
        self.page_manager = PageManager(self.device, self.vision)
        self.current_state = GameState.UNKNOWN

    def _crop_roi(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
        """Extract a bounding box region from the frame for fast targeted matching."""
        x, y, w, h = roi
        return frame[y:y+h, x:x+w]

    def is_home_screen(self, frame: np.ndarray) -> bool:
        """
        Verify if the current frame is the Home screen by testing the 3 user-specified anchors:
        - 畫面右下角: 出擊按鈕 (assets/anchors/home_sortie.png)
        - 畫面左上角: 玩家等級 (assets/anchors/home_level.png)
        - 畫面右上角: 體力條 (assets/anchors/home_stamina.png)
        """
        anchor_hits = 0
        total_checked = 0

        # Anchor 1: 右下角出擊按鈕 (Primary Anchor)
        try:
            sortie_roi = self._crop_roi(frame, HomeAnchorROI.BOTTOM_RIGHT_SORTIE)
            if self.vision.match_template(sortie_roi, "assets/anchors/home_sortie.png", threshold=0.80):
                anchor_hits += 2
            total_checked += 1
        except FileNotFoundError:
            pass

        # Anchor 2: 左上角等級圖示
        try:
            level_roi = self._crop_roi(frame, HomeAnchorROI.TOP_LEFT_LEVEL)
            if self.vision.match_template(level_roi, "assets/anchors/home_level.png", threshold=0.80):
                anchor_hits += 1
            total_checked += 1
        except FileNotFoundError:
            pass

        # Anchor 3: 右上角體力條 (AP)
        try:
            stamina_roi = self._crop_roi(frame, HomeAnchorROI.TOP_RIGHT_STAMINA)
            if self.vision.match_template(stamina_roi, "assets/anchors/home_stamina.png", threshold=0.80):
                anchor_hits += 1
            total_checked += 1
        except FileNotFoundError:
            pass

        if total_checked > 0 and anchor_hits >= 2:
            self.current_state = GameState.HOME
            return True

        return False

    def navigate_to_home(self, timeout: float = 90.0) -> bool:
        """
        Standardized startup and recovery pipeline:
        Delegates all popups, date-resets, login bonuses, and unexpected screens
        to the centralized PageManager until Home screen is verified.
        """
        logger.info(f"Navigating to Home screen via PageManager (timeout={timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            frame = self.device.screencap()

            # 1. Check if we have arrived at the Home screen
            if self.is_home_screen(frame):
                logger.success("Convergence reached: Successfully verified Home screen anchors!")
                self.current_state = GameState.HOME
                return True

            # 2. Delegate to PageManager for standardized classification and resolution
            page_type, success = self.page_manager.resolve_page(frame, max_attempts=1)

            if page_type == PageType.HOME:
                self.current_state = GameState.HOME
                return True

            if page_type == PageType.UNKNOWN:
                logger.warning("[StateMachine] 遇到未辨識頁面，已觸發安全防護並暫停。請向使用者請教。")
                return False

            self.device.random_sleep(1.0, 1.8)

        logger.error(f"Navigation timed out after {timeout}s without reaching Home screen.")
        return False

    def go_back(self, wait_seconds: float = 1.5) -> bool:
        """Tap the standardized top-left back button and resolve potential popups."""
        logger.info(f"[StateMachine] Tapping back button at {NavigationCoords.BACK_BUTTON}...")
        self.device.tap(NavigationCoords.BACK_BUTTON[0], NavigationCoords.BACK_BUTTON[1])
        self.device.random_sleep(wait_seconds, wait_seconds + 0.5)
        frame = self.device.screencap()
        self.page_manager.resolve_page(frame, max_attempts=1)
        return True

    def navigate_to_bottom_tab(
        self,
        tab_name: str,
        expected_page: Optional[PageType] = None,
        timeout: float = 20.0,
    ) -> bool:
        """Navigate to a destination tab on the bottom navigation bar."""
        if tab_name not in NavigationCoords.BOTTOM_NAV:
            logger.error(f"[StateMachine] Invalid bottom tab name: '{tab_name}'")
            return False

        target_coords = NavigationCoords.BOTTOM_NAV[tab_name]
        logger.info(f"[StateMachine] Navigating to bottom tab '{tab_name}' at {target_coords}...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            frame = self.device.screencap()
            ptype, _ = self.page_manager.classify(frame)

            # Resolve intrusive popups if present
            if ptype not in (PageType.HOME, PageType.PERSONAL_BASE, PageType.CHARACTER_REQUESTS):
                self.page_manager.resolve_page(frame, max_attempts=1)
                self.device.random_sleep(1.0, 1.5)
                frame = self.device.screencap()
                ptype, _ = self.page_manager.classify(frame)

            if expected_page and ptype == expected_page:
                logger.success(f"[StateMachine] Reached expected page: {expected_page.name}")
                return True

            self.device.tap(target_coords[0], target_coords[1])
            self.device.random_sleep(2.0, 2.5)

            frame = self.device.screencap()
            ptype, _ = self.page_manager.classify(frame)
            if expected_page is None or ptype == expected_page:
                logger.success(f"[StateMachine] Tab '{tab_name}' tapped, arrived at {ptype.name}.")
                return True

        logger.error(f"[StateMachine] Failed to navigate to bottom tab '{tab_name}' within {timeout}s.")
        return False

    def navigate_to_personal_base(self, timeout: float = 20.0) -> bool:
        """Navigate to Personal Base screen from any state."""
        logger.info("[StateMachine] Navigating to Personal Base (個人基地)...")
        success = self.navigate_to_bottom_tab("personal_base", expected_page=PageType.PERSONAL_BASE, timeout=timeout)
        if success:
            self.current_state = GameState.PERSONAL_BASE
        return success

    def navigate_to_character_requests(self, timeout: float = 20.0) -> bool:
        """Navigate to Character Requests (角色要求) from Home or Personal Base."""
        logger.info("[StateMachine] Navigating to Character Requests (角色要求)...")
        frame = self.device.screencap()
        ptype, _ = self.page_manager.classify(frame)

        if ptype == PageType.CHARACTER_REQUESTS:
            self.current_state = GameState.CHARACTER_REQUESTS
            return True

        if ptype != PageType.PERSONAL_BASE:
            if not self.navigate_to_personal_base(timeout=timeout / 2):
                return False

        logger.info(f"[StateMachine] Tapping 角色要求 banner at {NavigationCoords.BASE_CHARACTER_REQUESTS_BANNER}...")
        self.device.tap(NavigationCoords.BASE_CHARACTER_REQUESTS_BANNER[0], NavigationCoords.BASE_CHARACTER_REQUESTS_BANNER[1])
        self.device.random_sleep(2.5, 3.5)

        frame = self.device.screencap()
        ptype, _ = self.page_manager.classify(frame)
        if ptype == PageType.CHARACTER_REQUESTS:
            logger.success("[StateMachine] Successfully entered Character Requests.")
            self.current_state = GameState.CHARACTER_REQUESTS
            return True

        return ptype == PageType.CHARACTER_REQUESTS

    def select_character_request_slot(self, slot_index: int) -> bool:
        """Tap one of the 3 daily character request cards (1-indexed: 1, 2, or 3)."""
        if not (1 <= slot_index <= 3):
            logger.error(f"[StateMachine] Invalid slot index {slot_index}. Must be 1, 2, or 3.")
            return False

        coords = NavigationCoords.CHAR_REQ_SLOT_CARDS[slot_index - 1]
        logger.info(f"[StateMachine] Selecting Character Request Slot {slot_index} at {coords}...")
        self.device.tap(coords[0], coords[1])
        self.device.random_sleep(1.8, 2.5)
        return True

    def switch_character_request_slot(self, direction: str = "next") -> bool:
        """Switch character request slot in detail view using left/right arrows."""
        if direction.lower() == "next":
            coords = NavigationCoords.CHAR_REQ_ARROW_NEXT
            logger.info(f"[StateMachine] Tapping NEXT card arrow at {coords}...")
        elif direction.lower() == "prev":
            coords = NavigationCoords.CHAR_REQ_ARROW_PREV
            logger.info(f"[StateMachine] Tapping PREV card arrow at {coords}...")
        else:
            logger.error(f"[StateMachine] Invalid switch direction: '{direction}'")
            return False

        self.device.tap(coords[0], coords[1])
        self.device.random_sleep(1.5, 2.0)
        return True

