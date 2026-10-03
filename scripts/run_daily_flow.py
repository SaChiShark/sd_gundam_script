import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import time
from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.vision import Vision
from core.state_machine import StateMachine
from tasks.daily_login import DailyLoginTask
from tasks.warship_cruise import WarshipCruiseTask
from tasks.personal_base import PersonalBaseRequestTask


def run_full_flow():
    logger.info("=" * 60)
    logger.info("🚀 啟動自動化流程: 開啟遊戲 -> 進入主頁 -> 領取戰艦巡航 -> 檢查角色任務")
    logger.info("=" * 60)

    # 1. 初始化設備、視覺與狀態機 (包含 GPU YOLOv11 偵測器)
    config = AppConfig.load_from_file("config.yaml")
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)
    logger.info(f"YOLO 偵測器狀態: {'就緒 (RTX 4070 SUPER GPU DirectML)' if fsm.detector and fsm.detector.is_ready() else '未啟用'}")

    # ==========================================
    # Step 1: 開啟遊戲 -> 進入主頁
    # ==========================================
    logger.info("\n>>> [Step 1/3] 執行遊戲啟動與主頁登入 (DailyLoginTask)...")
    login_task = DailyLoginTask(device, vision, fsm, config)
    login_task.pre_check()
    success_home = login_task.run()
    if not success_home:
        logger.error("無法成功進入主頁，終止後續流程！")
        return False
    logger.success("✅ Step 1 完成：已確認抵達遊戲主頁 (Home Screen)")

    # ==========================================
    # Step 2: 領取戰艦巡航
    # ==========================================
    logger.info("\n>>> [Step 2/3] 執行戰艦巡航遠征獎勵回收 (WarshipCruiseTask)...")
    cruise_task = WarshipCruiseTask(device, vision, fsm)
    success_cruise = cruise_task.run()
    if not success_cruise:
        logger.warning("戰艦巡航回收未順利完成，嘗試重回主頁...")
        fsm.navigate_to_home()
    else:
        logger.success("✅ Step 2 完成：戰艦巡航遠征獎勵已順利領取並重回主頁")

    # ==========================================
    # Step 3: 檢查角色任務
    # ==========================================
    logger.info("\n>>> [Step 3/3] 前往個人基地檢查角色要求 (PersonalBaseRequestTask)...")
    char_task = PersonalBaseRequestTask(device, vision, fsm)
    if not char_task._enter_personal_base():
        logger.error("無法進入個人基地！")
        return False

    if not char_task._open_character_requests():
        logger.error("無法開啟角色要求！")
        return False

    logger.info("--- 開始檢視 3 個角色要求卡槽 ---")
    char_task._process_all_slots()

    # 領取週常達成獎勵 (若有累積達標)
    char_task._claim_weekly_milestones()

    logger.info("檢查完成，安全返回主畫面...")
    fsm.navigate_to_home()
    logger.success("\n🎉 全流程執行完畢！所有操作均依據 YOLO/狀態機閉環驗證完成。")
    return True


if __name__ == "__main__":
    run_full_flow()
