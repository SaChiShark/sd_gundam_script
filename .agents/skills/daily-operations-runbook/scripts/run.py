#!/usr/bin/env python3
"""Unified Daily Operations Runner Script for Antigravity Skill.

Allows direct invocation of individual steps or the full daily pipeline:
  python run.py launch       # Step 1: Launch game to Home
  python run.py cruise       # Step 2: Warship cruise rewards
  python run.py requests     # Step 3: Character requests
  python run.py cultivation  # Step 4: Cultivation stage sweeps
  python run.py all          # Full pipeline (Steps 1 to 4)
  python run.py status       # Check current game & device status
"""
import argparse
import os
import sys

# Locate repository root by walking up until config.yaml is found
cur = os.path.abspath(__file__)
while cur and os.path.dirname(cur) != cur:
    cur = os.path.dirname(cur)
    if os.path.exists(os.path.join(cur, "config.yaml")):
        REPO_ROOT = cur
        break
else:
    REPO_ROOT = os.getcwd()

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import cv2
from loguru import logger

from core.config import AppConfig
from core.device import Device
from core.vision import Vision
from core.state_machine import StateMachine
from core.page_manager import PageType
from tasks.daily_login import DailyLoginTask
from tasks.warship_cruise import WarshipCruiseTask
from tasks.personal_base import PersonalBaseRequestTask
from tasks.daily_cultivation import DailyCultivationTask


def get_environment():
    """Initialize connected device, vision, config, and state machine."""
    config_path = os.path.join(REPO_ROOT, "config.yaml")
    config = AppConfig.load_from_file(config_path)
    device = Device(config.device)
    device.connect()
    vision = Vision()
    fsm = StateMachine(device, vision)
    return config, device, vision, fsm


def op_status(config, device, vision, fsm) -> bool:
    """Inspect current emulator screen and classify game state."""
    logger.info("=" * 60)
    logger.info("🔍 [Status Check] 檢查模擬器畫面與當前遊戲狀態")
    logger.info("=" * 60)
    frame = device.screencap()
    page_type, meta = fsm.page_manager.classify(frame)
    logger.info(f"當前頁面分類: {page_type.name} ({page_type.value})")
    for k, v in meta.items():
        logger.info(f"  - {k}: {v}")

    os.makedirs(os.path.join(REPO_ROOT, "captures", "temp"), exist_ok=True)
    cap_path = os.path.join(REPO_ROOT, "captures", "temp", "status_check.png")
    cv2.imwrite(cap_path, frame)
    logger.info(f"實機截圖已存檔至: {cap_path}")
    return True


def op_launch(config, device, vision, fsm) -> bool:
    """Step 1: Launch game and converge to Home screen."""
    logger.info("=" * 60)
    logger.info("▶️ [Step 1] 啟動遊戲並收斂至主畫面 (DailyLoginTask)")
    logger.info("=" * 60)
    task = DailyLoginTask(device, vision, fsm, config)
    task.pre_check()
    success = task.run()
    if success:
        logger.success("🎉 [Step 1 成功] 遊戲已啟動並成功收斂至主畫面！")
    else:
        logger.error("❌ [Step 1 失敗] 未能成功抵達主畫面。")
    return success


def op_cruise(config, device, vision, fsm) -> bool:
    """Step 2: Collect Warship Cruise expedition rewards with multi-modal check."""
    logger.info("=" * 60)
    logger.info("▶️ [Step 2] 領取戰艦巡航遠征獎勵 (WarshipCruiseTask)")
    logger.info("=" * 60)
    task = WarshipCruiseTask(device, vision, fsm)
    success = task.run()
    if success:
        logger.success("🎉 [Step 2 成功] 戰艦巡航獎勵領取完成並已返回主頁！")
    else:
        logger.error("❌ [Step 2 失敗] 戰艦巡航回收流程異常。")
    return success


def op_requests(config, device, vision, fsm) -> bool:
    """Step 3: Check and claim character requests in Personal Base."""
    logger.info("=" * 60)
    logger.info("▶️ [Step 3] 個人基地角色委託檢查與領取 (PersonalBaseRequestTask)")
    logger.info("=" * 60)
    task = PersonalBaseRequestTask(device, vision, fsm)
    if not task._enter_personal_base():
        logger.error("無法進入個人基地！")
        return False

    if not task._open_character_requests():
        logger.error("無法開啟角色要求！")
        return False

    task._process_all_slots()
    task._claim_weekly_milestones()
    fsm.navigate_to_home()
    logger.success("🎉 [Step 3 成功] 角色要求處理完成並已返回主畫面！")
    return True


def op_cultivation(config, device, vision, fsm) -> bool:
    """Step 4: Execute daily sweeps on highest difficulty cultivation stages."""
    logger.info("=" * 60)
    logger.info("▶️ [Step 4] 強化培育關卡最高難度掃蕩 (DailyCultivationTask)")
    logger.info("=" * 60)
    task = DailyCultivationTask(device, vision, fsm)
    success = task.run()
    if success:
        logger.success("🎉 [Step 4 成功] 強化培育關卡檢查與掃蕩完成！")
    else:
        logger.error("❌ [Step 4 失敗] 強化培育關卡掃蕩流程未順利完成。")
    return success


def op_all(config, device, vision, fsm) -> bool:
    """Execute complete daily routine from Step 1 to Step 4."""
    logger.info("=" * 60)
    logger.info("🚀 [全流程] 執行每日自動化全套管線 (Step 1 -> Step 4)")
    logger.info("=" * 60)

    # Step 1
    if not op_launch(config, device, vision, fsm):
        logger.error("Step 1 啟動失敗，中止後續步驟！")
        return False

    # Step 2
    if not op_cruise(config, device, vision, fsm):
        logger.warning("Step 2 戰艦巡航失敗，嘗試返回主頁推進 Step 3...")
        fsm.navigate_to_home()

    # Step 3
    if not op_requests(config, device, vision, fsm):
        logger.warning("Step 3 角色委託失敗，嘗試返回主頁推進 Step 4...")
        fsm.navigate_to_home()

    # Step 4
    if not op_cultivation(config, device, vision, fsm):
        logger.error("Step 4 強化培育關卡失敗！")
        return False

    logger.success("\n🎉 [全流程成功] 今日日常任務已全數完成！")
    return True


OPERATIONS = {
    "status": op_status,
    "launch": op_launch,
    "step1": op_launch,
    "cruise": op_cruise,
    "warship": op_cruise,
    "step2": op_cruise,
    "requests": op_requests,
    "base": op_requests,
    "step3": op_requests,
    "cultivation": op_cultivation,
    "sweep": op_cultivation,
    "step4": op_cultivation,
    "all": op_all,
}


def main():
    parser = argparse.ArgumentParser(description="SD Gundam Skill Operations Runner")
    parser.add_argument(
        "action",
        choices=list(OPERATIONS.keys()),
        nargs="?",
        default="status",
        help="Action or step to execute (status, launch, cruise, requests, cultivation, all)",
    )
    args = parser.parse_args()

    config, device, vision, fsm = get_environment()
    op_func = OPERATIONS[args.action]
    success = op_func(config, device, vision, fsm)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
