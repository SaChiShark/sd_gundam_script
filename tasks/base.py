"""Abstract Base Task module for all automation routines."""
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger

from core.device import Device
from core.state_machine import StateMachine, NavigationCoords
from core.vision import Vision


class BaseTask(ABC):
    """Abstract base class that all concrete game tasks inherit from."""

    name: str = "base_task"

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None
    ):
        self.device = device
        self.vision = vision or Vision()
        self.fsm = fsm or StateMachine(self.device, self.vision)

    def pre_check(self) -> bool:
        """Verify preconditions before running (e.g. ensure we are on Home screen)."""
        logger.info(f"[{self.name}] Running pre-check...")
        frame = self.device.screencap()
        if not self.fsm.is_home_screen(frame):
            logger.warning(f"[{self.name}] Not on Home screen. Navigating to Home...")
            return self.fsm.navigate_to_home()
        return True

    @abstractmethod
    def run(self) -> bool:
        """Execute the task workflow."""
        pass

    def post_check(self) -> bool:
        """Verify postconditions (e.g. return to Home screen)."""
        logger.info(f"[{self.name}] Running post-check: Returning to Home screen...")
        frame = self.device.screencap()
        if self.fsm and self.fsm.is_home_screen(frame):
            logger.info(f"[{self.name}] Already on Home screen.")
            return True

        if self.fsm:
            return self.fsm.navigate_to_home()

        # Fallback if fsm is not attached: tap bottom navigation Home tab
        home_coords = NavigationCoords.BOTTOM_NAV["home"]
        self.device.tap(home_coords[0], home_coords[1])
        self.device.random_sleep(2.5, 3.5)

        frame = self.device.screencap()
        return self.fsm.is_home_screen(frame) if self.fsm else True

    def execute(self) -> bool:
        """Template method orchestrating the full task lifecycle."""
        logger.info(f"=== Starting Task: {self.name} ===")
        try:
            if not self.pre_check():
                logger.error(f"[{self.name}] Pre-check failed.")
                return False

            success = self.run()
            if success:
                logger.success(f"[{self.name}] Task executed successfully.")
            else:
                logger.warning(f"[{self.name}] Task completed with warnings/incomplete.")

            self.post_check()
            return success
        except Exception as e:
            logger.exception(f"[{self.name}] Unexpected error occurred: {e}")
            self.post_check()
            return False
