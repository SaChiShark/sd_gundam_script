"""Main entry point for SD Gundam automation routines."""
import argparse
import sys
from typing import Dict, Type

from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.state_machine import StateMachine
from core.vision import Vision
from tasks.base import BaseTask
from tasks.daily_login import DailyLoginTask
from tasks.personal_base import PersonalBaseRequestTask
from tasks.daily_cultivation import DailyCultivationTask
from tasks.warship_cruise import WarshipCruiseTask


REGISTERED_TASKS: Dict[str, Type[BaseTask]] = {
    "daily_login": DailyLoginTask,
    "personal_base": PersonalBaseRequestTask,
    "base": PersonalBaseRequestTask,
    "daily_cultivation": DailyCultivationTask,
    "cultivation": DailyCultivationTask,
    "upgrade": DailyCultivationTask,
    "warship_cruise": WarshipCruiseTask,
    "warship": WarshipCruiseTask,
    "cruise": WarshipCruiseTask,
}



def setup_logger(log_level: str = "INFO") -> None:
    """Configure Loguru logger formatting."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True
    )
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="SD Gundam G Generation ETERNAL Automation Runner")
    parser.add_argument("--task", type=str, default="personal_base", help="Task to execute (e.g. personal_base)")
    parser.add_argument("--all", action="store_true", help="Execute all enabled daily tasks")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    setup_logger()
    logger.info("Initializing SD Gundam Automation Runner...")

    config = AppConfig.load_from_file(args.config)
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)

    if args.task:
        task_name = args.task.lower()
        if task_name not in REGISTERED_TASKS:
            logger.error(f"Unknown task '{task_name}'. Available tasks: {list(REGISTERED_TASKS.keys())}")
            sys.exit(1)

        task_cls = REGISTERED_TASKS[task_name]
        task_instance = task_cls(device, vision, fsm)
        success = task_instance.execute()

        if success:
            logger.success(f"Task '{task_name}' finished successfully!")
        else:
            logger.error(f"Task '{task_name}' finished with failures.")
            sys.exit(1)


if __name__ == "__main__":
    main()
