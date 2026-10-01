"""Finite State Machine and Navigation Engine for SD Gundam."""
import time
from enum import Enum, auto
from typing import Dict, Optional, Tuple

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
    SORTIE_SELECT = auto()          # 出擊關卡選擇畫面
    BATTLE = auto()                 # 戰鬥中
    RESULT = auto()                 # 戰鬥結算


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
