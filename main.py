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
    "login": DailyLoginTask,
    "launch": DailyLoginTask,
    "step1": DailyLoginTask,
    "warship_cruise": WarshipCruiseTask,
    "warship": WarshipCruiseTask,
    "cruise": WarshipCruiseTask,
    "step2": WarshipCruiseTask,
    "personal_base": PersonalBaseRequestTask,
    "base": PersonalBaseRequestTask,
    "requests": PersonalBaseRequestTask,
    "step3": PersonalBaseRequestTask,
    "daily_cultivation": DailyCultivationTask,
    "cultivation": DailyCultivationTask,
    "upgrade": DailyCultivationTask,
    "sweep": DailyCultivationTask,
    "step4": DailyCultivationTask,
}



def setup_logger(log_level: str = "INFO") -> None:
    """Configure Loguru logger formatting."""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
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
    parser.add_argument("--task", type=str, default=None, help="Task to execute (e.g. step1, cruise, requests, cultivation)")
    parser.add_argument("--all", action="store_true", help="Execute all daily tasks in order (Step 1 -> 4)")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable tap visualization screenshot on every click")
    parser.add_argument("--step", action="store_true", help="Enable interactive step-by-step confirmation before each tap")
    parser.add_argument("--continuous", action="store_true", help="Execute continuously without step-by-step pauses")
    parser.add_argument("--debug-dir", type=str, default=None, help="Directory to save debug tap screenshots")
    args = parser.parse_args()

    setup_logger()
    logger.info("Initializing SD Gundam Automation Runner...")

    config = AppConfig.load_from_file(args.config)
    if args.debug:
        config.device.debug_mode = True
    if args.step:
        config.device.step_by_step = True
        config.device.debug_mode = True
    if args.continuous:
        config.device.step_by_step = False
    if args.debug_dir:
        config.device.debug_dir = args.debug_dir

    if config.device.step_by_step:
        logger.info(f"🕹️ Step-by-step interactive mode ENABLED. Tap screenshots saved to '{config.device.debug_dir}'.")
    elif config.device.debug_mode:
        logger.info(f"📸 Debug visualization mode ENABLED. Tap screenshots saved to '{config.device.debug_dir}'.")

    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)

    if args.all or args.task == "all":
        logger.info("Executing full daily operations pipeline (Step 1 -> Step 4)...")
        tasks_order = [
            ("Step 1: 遊戲啟動與主頁收斂", DailyLoginTask(device, vision, fsm, config)),
            ("Step 2: 戰艦巡航遠征領取", WarshipCruiseTask(device, vision, fsm)),
            ("Step 3: 個人基地角色委託", PersonalBaseRequestTask(device, vision, fsm)),
            ("Step 4: 強化培育關卡最高難度掃蕩", DailyCultivationTask(device, vision, fsm)),
        ]
        overall_success = True
        for name, task in tasks_order:
            logger.info(f"\n>>> 開始執行: {name}")
            task.pre_check()
            ok = task.run()
            if ok:
                logger.success(f"✅ {name} 執行成功！")
            else:
                logger.error(f"❌ {name} 執行失敗！")
                overall_success = False
            fsm.navigate_to_home()
        sys.exit(0 if overall_success else 1)

    task_name = (args.task or "personal_base").lower()
    if task_name not in REGISTERED_TASKS:
        logger.error(f"Unknown task '{task_name}'. Available tasks: {list(REGISTERED_TASKS.keys())}")
        sys.exit(1)

    task_cls = REGISTERED_TASKS[task_name]
    if task_cls == DailyLoginTask:
        task_instance = task_cls(device, vision, fsm, config)
    else:
        task_instance = task_cls(device, vision, fsm)

    success = task_instance.execute()
    if success:
        logger.success(f"Task '{task_name}' finished successfully!")
    else:
        logger.error(f"Task '{task_name}' finished with failures.")
        sys.exit(1)


if __name__ == "__main__":
    main()
