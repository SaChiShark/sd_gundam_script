"""Daily Login & App Startup Task for SD Gundam G Generation ETERNAL."""
import time
from typing import Optional

from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.state_machine import GameState, StateMachine
from core.vision import Vision
from tasks.base import BaseTask


class DailyLoginTask(BaseTask):
    """
    Task to ensure the game is launched, progress past the Title Screen (TAP TO START),
    intercept and clear all startup announcements, login bonuses, and popups,
    and reliably converge on the main Home screen.
    """

    name: str = "daily_login"

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
        config: Optional[AppConfig] = None
    ):
        super().__init__(device, vision, fsm)
        self.config = config or AppConfig()
        self.package_name = self.config.game.package_name
        self.activity_name = self.config.game.activity_name or "com.unity3d.player.UnityPlayerActivity"

    def pre_check(self) -> bool:
        """
        Verify if the app is already launched and focused in the foreground.
        If not, start the game application.
        """
        logger.info(f"[{self.name}] Pre-check: Verifying game process status...")

        if not self.device.is_app_running(self.package_name) or not self.device.is_app_foreground(self.package_name):
            logger.info(f"[{self.name}] App not running in foreground. Launching {self.package_name}...")
            self.device.launch_app(self.package_name, self.activity_name)
            self.device.random_sleep(4.0, 6.0)
        else:
            logger.info(f"[{self.name}] App {self.package_name} is already running in foreground.")

        return True

    def run(self) -> bool:
        """
        Execute startup sequence: Title screen -> Popups / Login Rewards -> Home Screen.
        """
        logger.info(f"[{self.name}] Starting startup and login progression...")

        # Step 1: Check if already on Home screen
        frame = self.device.screencap()
        if self.fsm.is_home_screen(frame):
            logger.success(f"[{self.name}] Already arrived at Home screen! No navigation needed.")
            return True

        # Step 2: Use StateMachine to autonomously navigate past title screen and popups
        logger.info(f"[{self.name}] Navigating past startup screens to Home...")
        reached_home = self.fsm.navigate_to_home(timeout=120.0)

        if not reached_home:
            logger.error(f"[{self.name}] Failed to reach Home screen within timeout.")
            return False

        # Step 3: Clear any lingering popups on Home screen (e.g. delayed daily announcements)
        self._clear_lingering_home_popups()

        logger.success(f"[{self.name}] Successfully completed launch and arrived at Home screen.")
        return True

    def _clear_lingering_home_popups(self, max_passes: int = 3) -> None:
        """Clear any residual modal popups that may appear after reaching Home screen."""
        logger.info(f"[{self.name}] Checking for lingering home popups...")
        for p in range(max_passes):
            frame = self.device.screencap()

            # If clean Home screen with no modal overlay
            if self.fsm.is_home_screen(frame):
                # Ensure no modal dimming or close buttons
                has_close = False
                for tmpl in ["assets/buttons/btn_close_gray.png", "assets/buttons/btn_close_blue.png", "assets/buttons/btn_modal_ok.png"]:
                    if btn := self.vision.match_template(frame, tmpl, threshold=0.80):
                        logger.info(f"[{self.name}] Detected lingering popup ({tmpl}). Dismissing...")
                        self.device.tap_rect(btn.rect)
                        self.device.random_sleep(1.2, 1.8)
                        has_close = True
                        break
                if not has_close:
                    logger.debug(f"[{self.name}] Home screen is clean.")
                    break
            else:
                # Intercept close buttons
                for tmpl in ["assets/buttons/btn_close_gray.png", "assets/buttons/btn_close_blue.png", "assets/buttons/btn_modal_ok.png"]:
                    if btn := self.vision.match_template(frame, tmpl, threshold=0.80):
                        logger.info(f"[{self.name}] Dismissing modal via {tmpl}...")
                        self.device.tap_rect(btn.rect)
                        self.device.random_sleep(1.2, 1.8)
                        break

    def post_check(self) -> bool:
        """Final verification that we are settled on the Home screen."""
        frame = self.device.screencap()
        is_home = self.fsm.is_home_screen(frame)
        if is_home:
            logger.success(f"[{self.name}] Post-check passed: Verified on Home screen.")
        else:
            logger.warning(f"[{self.name}] Post-check: Not confirmed on Home screen.")
        return is_home
