"""Warship Cruise (戰艦巡航) Automation Task."""
import time
from typing import Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.state_machine import StateMachine
from core.vision import Vision
from tasks.base import BaseTask


class WarshipCruiseTask(BaseTask):
    """
    Task to navigate to Personal Base (個人基地), open Warship Cruise (戰艦巡航),
    claim all accumulated expedition rewards (AP, Capital, Unit EXP, Character EXP),
    dismiss reward modals, and safely return to Home screen.
    """

    name: str = "warship_cruise"

    # UI Asset paths
    TPL_BASE_NAV: str = "assets/buttons/nav_base_clean.png"
    TPL_HOME_NAV: str = "assets/buttons/nav_home.png"
    TPL_HOME_SORTIE: str = "assets/anchors/home_sortie.png"
    TPL_BASE_TITLE: str = "assets/anchors/base_title.png"
    TPL_BASE_CRUISE: str = "assets/buttons/base_warship_cruise_clean.png"
    TPL_CRUISE_TITLE: str = "assets/anchors/warship_cruise_title.png"
    TPL_COLLECT_ALL: str = "assets/buttons/btn_warship_collect_all.png"
    TPL_MODAL_OK: str = "assets/buttons/btn_warship_modal_ok.png"

    # Calibrated fallback coordinates (1920x1080)
    COORD_NAV_BASE: Tuple[int, int] = (1240, 1035)
    COORD_CRUISE_BANNER: Tuple[int, int] = (160, 240)
    COORD_COLLECT_ALL: Tuple[int, int] = (1600, 830)
    COORD_MODAL_OK: Tuple[int, int] = (960, 990)
    COORD_NAV_HOME: Tuple[int, int] = (100, 1030)
    COORD_BACK_BTN: Tuple[int, int] = (65, 50)

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
    ) -> None:
        super().__init__(device, vision, fsm)

    def _dismiss_any_popup(self) -> bool:
        """Dismiss unexpected modal popups or confirmation dialogs."""
        frame = self.device.screencap()
        dismissed = False

        if btn_ok := self.vision.match_template(frame, self.TPL_MODAL_OK, threshold=0.80):
            logger.info("Dismissing reward modal via 'OK' button...")
            self.device.tap_rect(btn_ok.rect)
            self.device.random_sleep(1.0, 1.5)
            dismissed = True
        elif btn_close := self.vision.match_template(frame, "assets/buttons/btn_close_blue.png", threshold=0.80):
            logger.info("Dismissing modal popup via '關閉' button...")
            self.device.tap_rect(btn_close.rect)
            self.device.random_sleep(1.0, 1.5)
            dismissed = True

        return dismissed

    def _is_on_cruise_screen(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently located inside the Warship Cruise screen."""
        if frame is None:
            frame = self.device.screencap()
        return bool(self.vision.match_template(frame, self.TPL_CRUISE_TITLE, threshold=0.75))

    def _is_on_base_screen(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if currently located inside the Personal Base screen."""
        if frame is None:
            frame = self.device.screencap()
        return bool(
            self.vision.match_template(frame, self.TPL_BASE_TITLE, threshold=0.75)
            or self.vision.match_template(frame, "assets/buttons/base_char_request.png", threshold=0.75)
            or self.vision.match_template(frame, self.TPL_BASE_CRUISE, threshold=0.75)
        )

    def _enter_warship_cruise(self, max_attempts: int = 3) -> bool:
        """Navigate to Warship Cruise screen from current location."""
        frame = self.device.screencap()

        # Check if already inside Warship Cruise
        if self._is_on_cruise_screen(frame):
            logger.info("Already on Warship Cruise (戰艦巡航) screen.")
            return True

        for attempt in range(max_attempts):
            frame = self.device.screencap()
            self._dismiss_any_popup()

            # If not yet on Base screen, navigate to Personal Base
            if not self._is_on_base_screen(frame):
                logger.info("Navigating to 個人基地 (Personal Base)...")
                if nav_btn := self.vision.match_template(frame, self.TPL_BASE_NAV, threshold=0.75):
                    logger.info(f"Matched nav_base button at {nav_btn.center}. Tapping...")
                    self.device.tap_rect(nav_btn.rect)
                else:
                    logger.info(f"Tapping bottom bar 個人基地 by calibrated coordinates {self.COORD_NAV_BASE}...")
                    self.device.tap(self.COORD_NAV_BASE[0], self.COORD_NAV_BASE[1])

                # Wait for Base screen to load
                base_loaded = False
                for _ in range(5):
                    self.device.random_sleep(1.0, 1.5)
                    check_frame = self.device.screencap()
                    if self._is_on_base_screen(check_frame):
                        base_loaded = True
                        break
                if not base_loaded:
                    logger.warning("Personal Base screen load wait timed out, retrying...")
                    continue

            # Now on Base screen, tap Warship Cruise entrance
            base_frame = self.device.screencap()
            if cruise_banner := self.vision.match_template(base_frame, self.TPL_BASE_CRUISE, threshold=0.75):
                logger.info(f"Found '戰艦巡航' entrance banner at {cruise_banner.center}. Tapping...")
                self.device.tap_rect(cruise_banner.rect)
            else:
                logger.info(f"Tapping '戰艦巡航' banner by calibrated coordinates {self.COORD_CRUISE_BANNER}...")
                self.device.tap(self.COORD_CRUISE_BANNER[0], self.COORD_CRUISE_BANNER[1])

            # Wait for Warship Cruise screen to load
            for _ in range(5):
                self.device.random_sleep(1.0, 1.5)
                if self._is_on_cruise_screen():
                    logger.success("Successfully arrived at 戰艦巡航 screen.")
                    return True

            logger.warning(f"Warship cruise navigation attempt {attempt + 1}/{max_attempts} failed. Retrying...")

        return False

    def is_collect_available(self, frame: np.ndarray) -> bool:
        """
        Check if the '全部回收' button is active and rewards are ready to collect.
        Active button has bright blue color and high template match score (> 0.80).
        Disabled button has dark color and template match score (~0.45).
        """
        match = self.vision.match_template(frame, self.TPL_COLLECT_ALL, threshold=0.80)
        return bool(match)

    def _collect_rewards(self) -> bool:
        """Inspect and claim Warship Cruise rewards if available."""
        logger.info("Checking for Warship Cruise rewards...")
        frame = self.device.screencap()

        if not self._is_on_cruise_screen(frame):
            logger.error("Not on Warship Cruise screen. Cannot collect rewards.")
            return False

        if not self.is_collect_available(frame):
            logger.info("Warship Cruise rewards are not ready to collect (button disabled or already claimed).")
            return True

        logger.info("Rewards available! Tapping '全部回收'...")
        if btn_match := self.vision.match_template(frame, self.TPL_COLLECT_ALL, threshold=0.80):
            self.device.tap_rect(btn_match.rect)
        else:
            self.device.tap(self.COORD_COLLECT_ALL[0], self.COORD_COLLECT_ALL[1])

        self.device.random_sleep(2.0, 3.0)

        # Confirm rewards dialog (回收道具)
        modal_frame = self.device.screencap()
        if ok_match := self.vision.match_template(modal_frame, self.TPL_MODAL_OK, threshold=0.80):
            logger.info(f"Matched 'OK' confirmation button at {ok_match.center}. Tapping...")
            self.device.tap_rect(ok_match.rect)
        else:
            logger.info(f"Tapping 'OK' confirmation button by calibrated coordinates {self.COORD_MODAL_OK}...")
            self.device.tap(self.COORD_MODAL_OK[0], self.COORD_MODAL_OK[1])

        self.device.random_sleep(2.0, 2.5)

        # Verify reward popup dismissed
        after_frame = self.device.screencap()
        if self.vision.match_template(after_frame, self.TPL_MODAL_OK, threshold=0.80):
            logger.warning("Reward modal still present. Tapping OK again...")
            self.device.tap(self.COORD_MODAL_OK[0], self.COORD_MODAL_OK[1])
            self.device.random_sleep(1.5, 2.0)

        logger.success("Warship Cruise rewards claimed successfully!")
        return True

    def _return_to_home(self, max_attempts: int = 3) -> bool:
        """Safely navigate back to the main Home screen."""
        logger.info("Returning to Home screen (主畫面)...")

        for attempt in range(max_attempts):
            frame = self.device.screencap()
            if self.vision.match_template(frame, self.TPL_HOME_SORTIE, threshold=0.70):
                logger.success("Already at Home screen.")
                return True

            # Dismiss any leftover modal
            self._dismiss_any_popup()

            # Tap Home navigation button in bottom bar
            if nav_home := self.vision.match_template(frame, self.TPL_HOME_NAV, threshold=0.80):
                logger.info(f"Matched nav_home at {nav_home.center}. Tapping...")
                self.device.tap_rect(nav_home.rect)
            else:
                logger.info(f"Tapping nav_home at calibrated coordinates {self.COORD_NAV_HOME}...")
                self.device.tap(self.COORD_NAV_HOME[0], self.COORD_NAV_HOME[1])

            self.device.random_sleep(2.5, 3.5)

            home_frame = self.device.screencap()
            if self.vision.match_template(home_frame, self.TPL_HOME_SORTIE, threshold=0.70):
                logger.success("Successfully returned to Home screen.")
                return True

            # If not yet at home, try tapping top-left back button
            logger.info(f"Tapping back button at {self.COORD_BACK_BTN}...")
            self.device.tap(self.COORD_BACK_BTN[0], self.COORD_BACK_BTN[1])
            self.device.random_sleep(1.5, 2.0)

        logger.warning("Could not verify Home screen return via sortie anchor.")
        return False

    def run(self) -> bool:
        """
        Execute full Warship Cruise collection routine:
        1. Navigate to Warship Cruise screen
        2. Claim all available rewards
        3. Return to Home screen
        """
        logger.info("Starting Warship Cruise collection routine...")

        # Step 1: Navigate to Warship Cruise
        if not self._enter_warship_cruise():
            logger.error("Failed to enter Warship Cruise screen.")
            return False

        # Step 2: Collect rewards
        if not self._collect_rewards():
            logger.error("Failed to collect Warship Cruise rewards.")
            return False

        # Step 3: Return to Home
        if not self._return_to_home():
            logger.warning("Failed to confirm return to Home screen.")

        logger.success("Warship Cruise collection routine completed!")
        return True
