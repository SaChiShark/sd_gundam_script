"""Daily Cultivation (強化培育關卡) Stage Sweep Task."""
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.state_machine import StateMachine
from core.vision import Vision
from tasks.base import BaseTask


class DailyCultivationTask(BaseTask):
    """
    Task to navigate to Stages (關卡) -> Upgrade Stages (強化培育關卡),
    and sweep all 4 daily cultivation categories at their highest difficulty (LV6):
    1. CAPITAL
    2. 單位培育 (Unit EXP / materials)
    3. 角色培育 (Character EXP / materials)
    4. 支援人員培育 (Support Personnel EXP / materials)
    """

    name: str = "daily_cultivation"

    # Supported cultivation categories in cyclical order
    CATEGORIES: List[str] = [
        "CAPITAL",
        "單位培育",
        "角色培育",
        "支援人員培育",
    ]

    # Calibrated coordinates (1920x1080 baseline)
    NAV_STAGE: Tuple[int, int] = (960, 1035)          # Bottom nav bar '關卡'
    NAV_HOME: Tuple[int, int] = (150, 1035)           # Bottom nav bar '主畫面'
    UPGRADE_CARD: Tuple[int, int] = (1205, 800)       # 'UPGRADE STAGES 強化培育關卡' entry card
    CARD_CAPITAL: Tuple[int, int] = (300, 500)        # Card 1 on 4-card overview screen
    NEXT_CATEGORY_BTN: Tuple[int, int] = (1880, 500)  # Next category carousel arrow '>'
    PREV_CATEGORY_BTN: Tuple[int, int] = (20, 500)    # Prev category carousel arrow '<'
    TOP_STAGE_CARD: Tuple[int, int] = (450, 520)      # Top item in stage list (Highest difficulty LV6)
    SKIP_BTN: Tuple[int, int] = (1685, 685)           # Stage detail panel '略過' (Skip) button
    EXECUTE_BTN: Tuple[int, int] = (1148, 790)        # Sweep modal '執行' button
    REWARD_OK_BTN: Tuple[int, int] = (1680, 940)      # Sweep reward modal 'OK' button
    BACK_BTN: Tuple[int, int] = (65, 50)              # Top-left back button '<'

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
    ):
        super().__init__(device, vision, fsm)

    def is_upgrade_screen(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently on any '強化培育關卡' screen (overview or stage list)."""
        if frame is None:
            frame = self.device.screencap()
        # 1. Match anchor template
        try:
            if self.vision.match_template(frame, "assets/anchors/upgrade_stages_title.png", threshold=0.75):
                return True
        except FileNotFoundError:
            pass
        # 2. Check title region pixels fallback
        title_crop = frame[15:80, 110:320]
        gray = cv2.cvtColor(title_crop, cv2.COLOR_BGR2GRAY)
        return int(np.sum(gray > 200)) > 800

    def is_in_stage_list(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently inside a specific category's stage list (Screen B)."""
        if frame is None:
            frame = self.device.screencap()
        # In stage list, the right arrow '>' at (1880, 500) is bright white
        val = int(frame[500, 1880, 0])
        return val > 160

    def pre_check(self) -> bool:
        """Verify preconditions (allow being on Home screen or already inside Upgrade Stages)."""
        logger.info(f"[{self.name}] Running pre-check...")
        frame = self.device.screencap()
        if self.is_upgrade_screen(frame):
            logger.info(f"[{self.name}] Already inside 強化培育關卡.")
            return True
        if not self.fsm.is_home_screen(frame):
            logger.warning(f"[{self.name}] Neither on Home nor Upgrade Stages. Navigating to Home...")
            return self.fsm.navigate_to_home()
        return True

    def navigate_to_cultivation_stages(self, max_attempts: int = 3) -> bool:
        """Navigate from Home to 強化培育關卡 stage list."""
        logger.info("Navigating to 強化培育關卡 (Upgrade Stages)...")
        for attempt in range(1, max_attempts + 1):
            frame = self.device.screencap()

            # If already inside stage list
            if self.is_in_stage_list(frame):
                logger.success("Arrived at category stage list.")
                return True

            # If on 4-card overview screen, enter Card 1 (CAPITAL)
            if self.is_upgrade_screen(frame) and not self.is_in_stage_list(frame):
                logger.info(f"On 4-card overview. Tapping Card 1 (CAPITAL) at {self.CARD_CAPITAL}...")
                self.device.tap(self.CARD_CAPITAL[0], self.CARD_CAPITAL[1])
                self.device.random_sleep(2.5, 3.5)
                continue

            # If on 關卡 menu, check for UPGRADE STAGES card
            if card_match := self.vision.match_template(frame, "assets/buttons/upgrade_stages_card.png", threshold=0.75):
                logger.info(f"Found UPGRADE STAGES card at {card_match.center}. Tapping...")
                self.device.tap_rect(card_match.rect)
                self.device.random_sleep(2.5, 3.5)
                continue

            # Otherwise tap '關卡' on bottom nav bar
            logger.info(f"Attempt {attempt}: Tapping bottom bar '關卡' at {self.NAV_STAGE}...")
            self.device.tap(self.NAV_STAGE[0], self.NAV_STAGE[1])
            self.device.random_sleep(2.5, 3.5)

            # Check if card appears now
            frame = self.device.screencap()
            if self.is_upgrade_screen(frame):
                if self.is_in_stage_list(frame):
                    return True
                self.device.tap(self.CARD_CAPITAL[0], self.CARD_CAPITAL[1])
                self.device.random_sleep(2.5, 3.5)
                continue

            logger.info(f"Tapping UPGRADE STAGES card by calibrated position {self.UPGRADE_CARD}...")
            self.device.tap(self.UPGRADE_CARD[0], self.UPGRADE_CARD[1])
            self.device.random_sleep(2.5, 3.5)

        frame = self.device.screencap()
        return self.is_in_stage_list(frame)

    def is_skip_button_enabled(self, frame: Optional[np.ndarray] = None) -> bool:
        """
        Check if the '略過' (Skip) button is enabled (bright blue) vs disabled (dark).
        Sampling center (1685, 685):
        Enabled: B > 140, R < 100
        Disabled: B < 100
        """
        if frame is None:
            frame = self.device.screencap()
        b = int(frame[685, 1685, 0])
        r = int(frame[685, 1685, 2])
        is_blue = (b > 140) and (r < 100)
        return is_blue

    def check_highest_difficulty_ready(self, frame: Optional[np.ndarray] = None) -> Tuple[bool, str]:
        """
        Check if the highest difficulty (LV6) is unlocked and 3-starred.
        """
        if frame is None:
            frame = self.device.screencap()
        # Top stage area: y: 460 to 570, x: 780 to 920 contains stars and COMPLETE tag
        star_region = frame[460:570, 780:920]
        hsv = cv2.cvtColor(star_region, cv2.COLOR_BGR2HSV)
        # Gold/yellow mask for stars: H in 14-38, S in 80-255, V in 80-255
        gold_mask = cv2.inRange(hsv, (14, 80, 80), (38, 255, 255))
        gold_pixels = int(np.sum(gold_mask > 0))

        if gold_pixels > 200:
            return True, "LV6 is unlocked and 3-starred (COMPLETE)"
        return False, "LV6 does not show 3-star COMPLETE status"


    def execute_sweep(self) -> bool:
        """Execute sweep on currently selected stage."""
        logger.info("Tapping '略過' button...")
        self.device.tap(self.SKIP_BTN[0], self.SKIP_BTN[1])
        self.device.random_sleep(1.2, 1.8)

        # Confirm execute
        modal_frame = self.device.screencap()
        if exec_match := self.vision.match_template(modal_frame, "assets/buttons/btn_skip_execute.png", threshold=0.75):
            logger.info(f"Found '執行' button at {exec_match.center}. Tapping...")
            self.device.tap_rect(exec_match.rect)
        else:
            logger.info(f"Tapping '執行' by calibrated position {self.EXECUTE_BTN}...")
            self.device.tap(self.EXECUTE_BTN[0], self.EXECUTE_BTN[1])

        # Wait for skip battle animation (approx 3.5 - 4.5 seconds)
        logger.info("Waiting for skip animation to conclude...")
        self.device.random_sleep(3.8, 4.8)

        # Dismiss reward modal
        reward_frame = self.device.screencap()
        if ok_match := self.vision.match_template(reward_frame, "assets/buttons/btn_sweep_ok.png", threshold=0.75):
            logger.info(f"Found reward 'OK' button at {ok_match.center}. Tapping...")
            self.device.tap_rect(ok_match.rect)
        else:
            logger.info(f"Tapping reward 'OK' by calibrated position {self.REWARD_OK_BTN}...")
            self.device.tap(self.REWARD_OK_BTN[0], self.REWARD_OK_BTN[1])

        self.device.random_sleep(1.8, 2.4)
        return True

    def next_category(self) -> None:
        """Switch to next cultivation category via right arrow '>'."""
        logger.info(f"Advancing to next category via '>' at {self.NEXT_CATEGORY_BTN}...")
        self.device.tap(self.NEXT_CATEGORY_BTN[0], self.NEXT_CATEGORY_BTN[1])
        self.device.random_sleep(1.8, 2.5)

    def run(self) -> bool:
        """Execute full daily cultivation sweep routine across all categories."""
        if not self.navigate_to_cultivation_stages():
            logger.error("Failed to arrive at 強化培育關卡.")
            return False

        results: Dict[str, str] = {}

        for idx, cat_name in enumerate(self.CATEGORIES, start=1):
            logger.info(f"=== [{idx}/{len(self.CATEGORIES)}] Checking Category: {cat_name} ===")

            # Tap top stage card to ensure highest difficulty (LV6) is focused
            self.device.tap(self.TOP_STAGE_CARD[0], self.TOP_STAGE_CARD[1])
            self.device.random_sleep(1.0, 1.5)

            frame = self.device.screencap()

            # Check if highest difficulty is cleared & ready
            ready, reason = self.check_highest_difficulty_ready(frame)
            if not ready:
                logger.warning(f"[{cat_name}] {reason}! Cannot sweep highest difficulty.")
                results[cat_name] = f"UNAVAILABLE: {reason}"
                if idx < len(self.CATEGORIES):
                    self.next_category()
                continue

            # Check if skip button is enabled (remaining attempts > 0)
            if self.is_skip_button_enabled(frame):
                logger.info(f"[{cat_name}] Skip available. Executing sweep on highest difficulty (LV6)...")
                self.execute_sweep()
                results[cat_name] = "SWEPT_5_TIMES (LV6)"
                logger.success(f"[{cat_name}] Successfully swept!")
            else:
                logger.info(f"[{cat_name}] Skip button disabled (already 0/5 sweeps completed today).")
                results[cat_name] = "ALREADY_COMPLETED (0/5 remaining)"

            # Switch to next category
            if idx < len(self.CATEGORIES):
                self.next_category()

        logger.info(f"Daily Cultivation Summary: {results}")

        # Final post-task: Return to Home
        logger.info("Returning to Home screen...")
        self.device.tap(self.NAV_HOME[0], self.NAV_HOME[1])
        self.device.random_sleep(2.5, 3.5)

        return True
