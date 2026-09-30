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
    1. TOP_LEFT_LEVEL: 玩家等級圖示與數值 (x: 0, y: 0, w: 400, h: 160)
    2. TOP_RIGHT_STAMINA: 體力/AP條與貨幣欄 (x: 1200, y: 0, w: 720, h: 160)
    3. BOTTOM_RIGHT_SORTIE: 右下角核心「出擊」按鈕 (x: 1450, y: 850, w: 470, h: 230)
    """
    TOP_LEFT_LEVEL: Tuple[int, int, int, int] = (0, 0, 400, 160)
    TOP_RIGHT_STAMINA: Tuple[int, int, int, int] = (1200, 0, 720, 160)
    BOTTOM_RIGHT_SORTIE: Tuple[int, int, int, int] = (1450, 850, 470, 230)


class StateMachine:
    """Tracks game UI state and orchestrates autonomous navigation."""

    def __init__(self, device: Device, vision: Optional[Vision] = None):
        self.device = device
        self.vision = vision or Vision()
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

        Supports weighted multi-anchor voting. If at least 2 anchors or the primary Sortie button
        match with high confidence, Home state is confirmed.
        """
        anchor_hits = 0
        total_checked = 0

        # Anchor 1: 右下角出擊按鈕 (Primary Anchor)
        try:
            sortie_roi = self._crop_roi(frame, HomeAnchorROI.BOTTOM_RIGHT_SORTIE)
            if self.vision.match_template(sortie_roi, "assets/anchors/home_sortie.png", threshold=0.80):
                anchor_hits += 2  # High weight
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
        Autonomous startup pipeline:
        Repeatedly intercepts popups, checks 'Don't show today', closes banners,
        and taps title screen until the Home screen anchors are fully converged.
        """
        logger.info(f"Navigating to Home screen (timeout={timeout}s)...")
        start_time = time.time()
        last_action_time = time.time()

        while time.time() - start_time < timeout:
            frame = self.device.screencap()

            # 1. Check if we have arrived at the Home screen
            if self.is_home_screen(frame):
                logger.success("Convergence reached: Successfully verified Home screen anchors!")
                self.current_state = GameState.HOME
                return True

            action_taken = False

            # 2. Check for "Don't show today" checkbox (優先勾選「今日不再顯示」)
            try:
                if cb := self.vision.match_template(frame, "assets/buttons/checkbox_unchecked.png", threshold=0.85):
                    logger.info("Found 'Don't show today' checkbox. Tapping to check...")
                    self.device.tap_rect(cb.rect)
                    action_taken = True
                    last_action_time = time.time()
            except FileNotFoundError:
                pass

            # 3. Check for Close 'X' buttons
            try:
                if btn_x := self.vision.match_template(frame, "assets/buttons/btn_close_x.png", threshold=0.82):
                    logger.info("Detected popup close button (X). Tapping...")
                    self.device.tap_rect(btn_x.rect)
                    action_taken = True
                    last_action_time = time.time()
            except FileNotFoundError:
                pass

            # 4. Check for Confirmation / Claim buttons (OK, 確定, 領取)
            try:
                if btn_ok := self.vision.match_template(frame, "assets/buttons/btn_confirm.png", threshold=0.82):
                    logger.info("Detected confirm/claim button. Tapping...")
                    self.device.tap_rect(btn_ok.rect)
                    action_taken = True
                    last_action_time = time.time()
            except FileNotFoundError:
                pass

            # 5. Check for Title Screen (TOUCH TO START)
            try:
                if title_anchor := self.vision.match_template(frame, "assets/anchors/title_screen.png", threshold=0.80):
                    logger.info("Detected Title Screen. Tapping center to start...")
                    self.device.tap(960, 750, radius=20)
                    action_taken = True
                    last_action_time = time.time()
            except FileNotFoundError:
                pass

            # 6. Fallback Interception: If no known buttons matched and state has been static for > 3s
            if not action_taken and (time.time() - last_action_time > 3.0):
                logger.debug("No active UI matched for 3s. Sending KEYCODE_BACK to dismiss potential modal...")
                self.device.key_back()
                last_action_time = time.time()

            self.device.random_sleep(0.8, 1.5)

        logger.error(f"Navigation timed out after {timeout}s without reaching Home screen.")
        return False
