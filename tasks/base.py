"""Abstract Base Task module for all automation routines."""
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger

from core.device import Device
from core.state_machine import StateMachine
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
        # Tap bottom-left Home tab or back key until Home is reached
        self.device.tap(100, 990)
        self.device.random_sleep(1.5, 2.5)

        frame = self.device.screencap()
        if not self.fsm.is_home_screen(frame):
            return self.fsm.navigate_to_home()
        return True

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
