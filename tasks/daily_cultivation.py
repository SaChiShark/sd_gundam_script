"""Daily Cultivation (強化培育關卡) Stage Sweep Task."""
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.state_machine import StateMachine, NavigationCoords
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
    NAV_STAGE: Tuple[int, int] = NavigationCoords.BOTTOM_NAV["stages"]  # Bottom nav bar '關卡'
    UPGRADE_CARD: Tuple[int, int] = (1205, 800)       # 'UPGRADE STAGES 強化培育關卡' entry card
    CARD_CAPITAL: Tuple[int, int] = (395, 500)        # Card 1 on 4-card overview screen
    NEXT_CATEGORY_BTN: Tuple[int, int] = (1890, 530)  # Next category carousel arrow '>'
    PREV_CATEGORY_BTN: Tuple[int, int] = (20, 500)    # Prev category carousel arrow '<'
    TOP_STAGE_CARD: Tuple[int, int] = (450, 515)      # Top item in stage list (Highest difficulty LV6)
    BTN_COUNT_MAX: Tuple[int, int] = (1280, 445)      # Sweep modal '[>>]' (Max Count) button
    SKIP_BTN: Tuple[int, int] = (1673, 709)           # Stage detail panel '略過' (Skip) button
    EXECUTE_BTN: Tuple[int, int] = (1148, 850)        # Sweep modal '執行' button center
    REWARD_OK_BTN: Tuple[int, int] = (1680, 915)      # Sweep reward modal 'OK' button
    BACK_BTN: Tuple[int, int] = NavigationCoords.BACK_BUTTON  # Top-left back button '<'

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
    ):
        super().__init__(device, vision, fsm)

    def is_upgrade_screen(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently on any '強化培育關卡' screen (overview or stage list).
        Requires the top header title (y < 120, x < 700) to contain '強化培育' or '培育關卡'.
        """
        if frame is None:
            frame = self.device.screencap()
        ocr_items = self.fsm.page_manager._extract_all_text(frame)
        return any(
            ("強化培育" in t or "培育關卡" in t) and center[1] < 120 and center[0] < 700
            for t, center, _ in ocr_items
        )

    def is_stages_menu(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently on the main Stage Select menu ('關卡' top title)."""
        if frame is None:
            frame = self.device.screencap()
        ocr_items = self.fsm.page_manager._extract_all_text(frame)
        has_stage_title = any(
            t == "關卡" and center[1] < 100 and center[0] < 300
            for t, center, _ in ocr_items
        )
        has_upgrade_card = any(
            ("強化培育" in t or "UPGRADE" in t) and center[1] > 600
            for t, center, _ in ocr_items
        )
        return has_stage_title or has_upgrade_card

    def is_in_stage_list(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently inside a specific category's stage list (Screen B)."""
        if frame is None:
            frame = self.device.screencap()
        if not self.is_upgrade_screen(frame):
            return False
        ocr_items = self.fsm.page_manager._extract_all_text(frame)
        texts = [t[0] for t in ocr_items]
        return any(
            ("出擊準備" in t or "出擎准備" in t or ("略過" in t and any(item[1][0] > 1500 for item in ocr_items if item[0] == "略過")))
            for t in texts
        )

    def pre_check(self) -> bool:
        """Verify preconditions (allow being on Home, Stages menu, or Upgrade Stages)."""
        logger.info(f"[{self.name}] Running pre-check...")
        frame = self.device.screencap()
        from core.page_manager import PageType
        ptype, meta = self.fsm.page_manager.classify(frame)
        if ptype == PageType.ITEM_ACQUIRED:
            logger.info(f"[{self.name}] Dismissing lingering reward popup in pre-check...")
            self.fsm.page_manager.handle_item_acquired(frame, meta)
            frame = self.device.screencap()
        elif ptype == PageType.MODAL_INFO:
            self.fsm.page_manager.handle_modal_info(frame, meta)
            frame = self.device.screencap()

        if self.is_upgrade_screen(frame) or self.is_stages_menu(frame):
            logger.info(f"[{self.name}] Already inside Stages flow.")
            return True
        if not self.fsm.is_home_screen(frame):
            logger.warning(f"[{self.name}] Neither on Home nor Stages. Navigating to Home...")
            return self.fsm.navigate_to_home()
        return True

    def navigate_to_cultivation_stages(self, max_attempts: int = 6) -> bool:
        """Navigate from Home -> Stages Menu -> Upgrade Overview -> Stage List."""
        logger.info("Navigating to 強化培育關卡 (Upgrade Stages)...")
        for attempt in range(1, max_attempts + 1):
            frame = self.device.screencap()

            # 1. If already inside category stage list
            if self.is_in_stage_list(frame):
                logger.success("Arrived at category stage list.")
                return True

            # 2. If on 4-card overview screen, enter Card 1 (CAPITAL)
            if self.is_upgrade_screen(frame) and not self.is_in_stage_list(frame):
                cv2.imwrite("captures/temp/step4_overview_4cards.png", frame)
                logger.info(f"On 4-card overview. Tapping Card 1 (CAPITAL) at {self.CARD_CAPITAL}...")
                self.device.tap(self.CARD_CAPITAL[0], self.CARD_CAPITAL[1])
                self.device.random_sleep(2.5, 3.5)
                continue

            # 3. If on 關卡 menu, tap UPGRADE STAGES card
            if self.is_stages_menu(frame):
                if card_match := self.vision.match_template(frame, "assets/buttons/upgrade_stages_card.png", threshold=0.75):
                    logger.info(f"Found UPGRADE STAGES card at {card_match.center}. Tapping...")
                    self.device.tap_rect(card_match.rect)
                else:
                    logger.info(f"Tapping UPGRADE STAGES card at calibrated position {self.UPGRADE_CARD}...")
                    self.device.tap(self.UPGRADE_CARD[0], self.UPGRADE_CARD[1])
                self.device.random_sleep(2.5, 3.5)
                continue

            # 4. If on Home or other screen, tap bottom bar '關卡'
            logger.info(f"Attempt {attempt}: Tapping bottom bar '關卡' at {self.NAV_STAGE}...")
            self.device.tap(self.NAV_STAGE[0], self.NAV_STAGE[1])
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
        """Execute sweep on currently selected stage with adaptive MAX sweep count."""
        logger.info("Tapping '略過' (Skip) button...")
        cur_frame = self.device.screencap()
        if self.fsm.detector and self.fsm.detector.is_ready():
            if det := self.fsm.detector.find_target(cur_frame, "btn_skip", conf=0.6):
                logger.info(f"YOLO detected 'btn_skip' at {det.center}. Tapping...")
                self.device.tap(det.center[0], det.center[1])
            else:
                self.device.tap(self.SKIP_BTN[0], self.SKIP_BTN[1])
        else:
            self.device.tap(self.SKIP_BTN[0], self.SKIP_BTN[1])
        self.device.random_sleep(1.2, 1.8)

        # Confirm execute modal
        modal_frame = self.device.screencap()

        # Tap [>>] (Max Count) button to ensure maximum count is selected under any daily event limit
        logger.info(f"Tapping '[>>]' (Max Count) button at {self.BTN_COUNT_MAX} to adapt to any sweep limit...")
        self.device.tap(self.BTN_COUNT_MAX[0], self.BTN_COUNT_MAX[1])
        self.device.random_sleep(0.5, 0.8)

        # Tap '執行' button
        modal_frame = self.device.screencap()
        if self.fsm.detector and self.fsm.detector.is_ready() and (det := self.fsm.detector.find_target(modal_frame, "btn_confirm", conf=0.6)):
            logger.info(f"YOLO detected 'btn_confirm' (執行) at {det.center}. Tapping...")
            self.device.tap(det.center[0], det.center[1])
        elif exec_match := self.vision.match_template(modal_frame, "assets/buttons/btn_skip_execute.png", threshold=0.75):
            logger.info(f"Found '執行' button via template at {exec_match.center}. Tapping...")
            self.device.tap_rect(exec_match.rect)
        else:
            logger.info(f"Tapping '執行' by calibrated position {self.EXECUTE_BTN}...")
            self.device.tap(self.EXECUTE_BTN[0], self.EXECUTE_BTN[1])

        # Wait for skip battle animation (approx 3.5 - 4.5 seconds)
        logger.info("Waiting for skip animation to conclude...")
        self.device.random_sleep(3.8, 4.8)

        # Dismiss reward modal
        reward_frame = self.device.screencap()
        page_type, meta = self.fsm.page_manager.classify(reward_frame)
        from core.page_manager import PageType
        if page_type == PageType.ITEM_ACQUIRED:
            logger.info("PageManager detected ITEM_ACQUIRED reward popup. Dismissing...")
            self.fsm.page_manager.handle_item_acquired(reward_frame, meta)
        elif ok_match := self.vision.match_template(reward_frame, "assets/buttons/btn_sweep_ok.png", threshold=0.75):
            logger.info(f"Found reward 'OK' button via template at {ok_match.center}. Tapping...")
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
        cat_keys = {
            "CAPITAL": "capital",
            "單位培育": "unit_upgrade",
            "角色培育": "character_upgrade",
            "支援人員培育": "support_upgrade",
        }

        for idx, cat_name in enumerate(self.CATEGORIES, start=1):
            cat_key = cat_keys.get(cat_name, f"cat_{idx}")
            logger.info(f"=== [{idx}/{len(self.CATEGORIES)}] Checking Category: {cat_name} ({cat_key}) ===")

            # Scroll list to top to ensure highest difficulty (LV6) is at Card 1
            self.device.swipe_bezier((450, 450), (450, 750), duration_ms=400)
            self.device.random_sleep(0.8, 1.2)

            # Tap top stage card to ensure highest difficulty (LV6) is focused
            self.device.tap(self.TOP_STAGE_CARD[0], self.TOP_STAGE_CARD[1])
            self.device.random_sleep(1.0, 1.5)

            frame = self.device.screencap()
            cv2.imwrite(f"captures/temp/step4_cat_{idx}_{cat_key}.png", frame)

            # Check if highest difficulty is cleared & ready
            ready, reason = self.check_highest_difficulty_ready(frame)
            if not ready:
                logger.warning(f"[{cat_name}] {reason}! Cannot sweep highest difficulty.")
                cv2.imwrite(f"captures/temp/cultivation_locked_{cat_key}.png", frame)
                results[cat_name] = f"SKIPPED_UNAVAILABLE: {reason}"
                if idx < len(self.CATEGORIES):
                    self.next_category()
                continue

            # Check if skip button is enabled (remaining attempts > 0)
            if self.is_skip_button_enabled(frame):
                logger.info(f"[{cat_name}] Skip available. Executing sweep on highest difficulty (LV6)...")
                self.execute_sweep()
                results[cat_name] = "SWEPT_MAX_SUCCESS (LV6)"
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
        self.fsm.navigate_to_home()
        return True
