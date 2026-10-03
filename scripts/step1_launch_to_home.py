import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.vision import Vision
from core.state_machine import StateMachine
from tasks.daily_login import DailyLoginTask


def run_step1():
    logger.info("=" * 60)
    logger.info("▶️ [Step 1] 啟動遊戲並進入主頁 (DailyLoginTask)")
    logger.info("=" * 60)

    config = AppConfig.load_from_file("config.yaml")
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)

    task = DailyLoginTask(device, vision, fsm, config)
    logger.info("[Step 1] 檢查遊戲進程狀態...")
    task.pre_check()

    logger.info("[Step 1] 推進啟動畫面、公告與簽到彈窗...")
    success = task.run()

    if success:
        logger.success("🎉 [Step 1 成功] 遊戲已成功啟動並抵達主頁 (Home Screen)！")
        frame = device.screencap()
        import cv2
        cv2.imwrite("captures/temp/step1_home.png", frame)
        return True
    else:
        logger.error("❌ [Step 1 失敗] 無法在超時時間內抵達主頁。")
        return False


if __name__ == "__main__":
    success = run_step1()
    sys.exit(0 if success else 1)
