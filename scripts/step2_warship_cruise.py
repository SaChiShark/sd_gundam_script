"""Step 2: Collect Warship Cruise Expedition Rewards."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import cv2
from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.vision import Vision
from core.state_machine import StateMachine
from tasks.warship_cruise import WarshipCruiseTask


def run_step2():
    logger.info("=" * 60)
    logger.info("▶️ [Step 2] 前往個人基地並領取戰艦巡航遠征獎勵 (WarshipCruiseTask)")
    logger.info("=" * 60)

    config = AppConfig.load_from_file("config.yaml")
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)

    task = WarshipCruiseTask(device, vision, fsm)
    success = task.run()

    frame = device.screencap()
    cv2.imwrite("captures/temp/step2_warship_cruise.png", frame)

    if success:
        logger.success("🎉 [Step 2 成功] 戰艦巡航獎勵領取完畢並已返回主頁！")
        return True
    else:
        logger.error("❌ [Step 2 失敗] 戰艦巡航流程未順利完成。")
        return False


if __name__ == "__main__":
    success = run_step2()
    sys.exit(0 if success else 1)
