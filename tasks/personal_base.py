"""Personal Base Character Requests Automation Task."""
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.state_machine import StateMachine
from core.vision import Vision
from tasks.base import BaseTask


class PersonalBaseRequestTask(BaseTask):
    """
    Task to navigate to Personal Base (個人基地), open Character Requests (角色要求),
    inspect all daily character request slots (3 slots per day), accept unaccepted requests,
    skip dialogues, claim completed rewards, and safely return to Home.
    """

    name: str = "personal_base"

    # Screen coordinates for the 3 daily character slots on 1920x1080
    SLOT_COORDINATES: List[Tuple[int, int]] = [
        (220, 400),  # Slot 1 (Left card)
        (500, 400),  # Slot 2 (Middle card)
        (780, 400),  # Slot 3 (Right card)
    ]

    # Weekly reward milestones (5, 10, 15, 20) at bottom bar
    WEEKLY_REWARD_COORDINATES: List[Tuple[int, int]] = [
        (1040, 770),
        (1260, 770),
        (1475, 770),
        (1690, 770),
    ]

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
    ):
        super().__init__(device, vision, fsm)

    def _dismiss_any_popup(self) -> bool:
        """Dismiss modal popups or reward collection dialogs."""
        frame = self.device.screencap()
        dismissed = False

        # Close button (blue modal button)
        if btn_close := self.vision.match_template(frame, "assets/buttons/btn_close_blue.png", threshold=0.80):
            logger.info("Dismissing modal popup via '關閉' button...")
            self.device.tap_rect(btn_close.rect)
            self.device.random_sleep(1.0, 1.5)
            dismissed = True

        return dismissed

    def _enter_personal_base(self, max_attempts: int = 3) -> bool:
        """Navigate to Personal Base screen from Home."""
        logger.info("Navigating to 個人基地 (Personal Base)...")

        for attempt in range(max_attempts):
            frame = self.device.screencap()

            # Dismiss unexpected popups first
            self._dismiss_any_popup()

            # Try template matching nav_base button
            if nav_btn := self.vision.match_template(frame, "assets/buttons/nav_base.png", threshold=0.80):
                logger.info(f"Matched nav_base button at {nav_btn.center}. Tapping...")
                self.device.tap_rect(nav_btn.rect)
            else:
                # Calibrated coordinates in bottom bar for '個人基地'
                logger.info("Tapping bottom bar 個人基地 by calibrated coordinates (1200, 990)...")
                self.device.tap(1200, 990)

            self.device.random_sleep(2.5, 3.5)

            # Check if we see the '角色要求' banner in Base
            base_frame = self.device.screencap()
            if self.vision.match_template(base_frame, "assets/buttons/base_char_request.png", threshold=0.75):
                logger.success("Successfully arrived at 個人基地 screen.")
                return True

        return False

    def _open_character_requests(self) -> bool:
        """Find and open the '角色要求' section in Personal Base."""
        logger.info("Locating '角色要求' entrance banner...")
        frame = self.device.screencap()

        if req_match := self.vision.match_template(frame, "assets/buttons/base_char_request.png", threshold=0.75):
            logger.info(f"Found '角色要求' at {req_match.center}. Tapping...")
            self.device.tap_rect(req_match.rect)
        else:
            logger.info("Tapping '角色要求' by calibrated coordinates (1510, 315)...")
            self.device.tap(1510, 315)

        self.device.random_sleep(2.5, 3.5)
        return True

    def _handle_detail_action(self) -> None:
        """Inspect the action button in the Character Request detail view."""
        frame = self.device.screencap()

        # 1. Check for '承接' (Accept Request)
        if accept_match := self.vision.match_template(frame, "assets/buttons/btn_accept_req.png", threshold=0.80):
            logger.info("Found '承接' button! Tapping to accept request...")
            self.device.tap_rect(accept_match.rect)
            self.device.random_sleep(2.0, 3.0)

            # Check for dialogue skip button ('略過')
            dialog_frame = self.device.screencap()
            if skip_match := self.vision.match_template(dialog_frame, "assets/buttons/btn_dialog_skip.png", threshold=0.80):
                logger.info("Found dialogue '略過' button. Skipping dialogue...")
                self.device.tap_rect(skip_match.rect)
            else:
                logger.info("Using calibrated fallback skip click at (1760, 60)...")
                self.device.tap(1760, 60)
            self.device.random_sleep(1.5, 2.0)
            return

        # 2. Check for '報告' (Report & Claim Completed Request)
        report_match = self.vision.match_template(frame, "assets/buttons/btn_report_orange.png", threshold=0.80)
        if report_match or self._is_orange_action_button(frame):
            logger.info("Found '報告' button! Tapping to claim completed request...")
            if report_match:
                self.device.tap_rect(report_match.rect)
            else:
                self.device.tap(1623, 858)
            self.device.random_sleep(2.5, 3.0)

            # Skip completion dialogue
            logger.info("Skipping completion dialogue...")
            self.device.tap(1760, 60)
            self.device.random_sleep(2.0, 2.5)

            # Dismiss '回報完成' screen
            logger.info("Dismissing '回報完成' screen...")
            self.device.tap(960, 500)
            self.device.random_sleep(2.0, 2.5)

            # Dismiss '領取結果' (OK button)
            logger.info("Dismissing '領取結果' modal...")
            self.device.tap(962, 949)
            self.device.random_sleep(1.5, 2.0)
            return

        # 3. Dismiss any unexpected popup if present
        self._dismiss_any_popup()

    def _is_orange_action_button(self, frame) -> bool:
        """Check if an orange action button is present in the lower right."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        orange_mask = cv2.inRange(hsv, (5, 120, 150), (25, 255, 255))
        # Lower right region
        lr = orange_mask[750:900, 1400:1850]
        return np.sum(lr > 0) > 1000

    def _process_all_slots(self) -> None:
        """Iterate over the 3 daily character slots."""
        for slot_idx, (sx, sy) in enumerate(self.SLOT_COORDINATES, start=1):
            logger.info(f"--- Processing Daily Slot [{slot_idx}/3] at ({sx}, {sy}) ---")
            self.device.tap(sx, sy)
            self.device.random_sleep(2.0, 2.5)

            # Inspect and execute accept/claim in detail panel
            self._handle_detail_action()

            # Return to 3-slot overview via top-left back arrow (60, 50)
            logger.info("Returning to 3-slot overview via back button (60, 50)...")
            self.device.tap(60, 50)
            self.device.random_sleep(1.5, 2.0)

    def _claim_weekly_milestones(self) -> None:
        """Check and tap weekly reward milestones (5, 10, 15, 20 completions)."""
        logger.info("Checking weekly reward milestone progress...")
        for mx, my in self.WEEKLY_REWARD_COORDINATES:
            self.device.tap(mx, my)
            self.device.random_sleep(0.8, 1.2)
            self._dismiss_any_popup()

    def run(self) -> bool:
        """Execute the complete Personal Base character requests workflow."""
        # Step 1: Navigate into Personal Base
        if not self._enter_personal_base():
            logger.error("Failed to enter 個人基地.")
            return False

        # Step 2: Open Character Requests
        if not self._open_character_requests():
            logger.error("Failed to open 角色要求.")
            return False

        # Step 3: Loop through all 3 daily character slots
        self._process_all_slots()

        # Step 4: Claim any weekly milestones
        self._claim_weekly_milestones()

        logger.success("All daily character requests processed successfully!")
        return True
