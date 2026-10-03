"""Step 4: Inspect and Complete Cultivation Stages (檢查並完成培育關卡).

Executes daily sweeps across all 4 cultivation categories at highest difficulty (LV6):
1. CAPITAL
2. 單位培育 (Unit EXP / materials)
3. 角色培育 (Character EXP / materials)
4. 支援人員培育 (Support Personnel EXP / materials)

Handles adaptive MAX sweep counts ([>>]) and skips ineligible categories safely.
"""
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
from tasks.daily_cultivation import DailyCultivationTask


def run_step4():
    logger.info("=" * 60)
    logger.info("▶️ [Step 4] 檢查並完成每日強化培育關卡 (DailyCultivationTask)")
    logger.info("=" * 60)

    config = AppConfig.load_from_file("config.yaml")
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)
    task = DailyCultivationTask(device, vision, fsm)

    # 1. 執行前置檢查
    if not task.pre_check():
        logger.error("無法就緒前置狀態（非主畫面且無法返回主畫面）！")
        return False

    # 2. 導航至關卡清單
    logger.info("[Step 4] 前往『關卡』 -> 『強化培育關卡』...")
    if not task.navigate_to_cultivation_stages():
        logger.error("無法進入強化培育關卡！")
        return False

    results = {}

    CAT_KEYS = {
        "CAPITAL": "capital",
        "單位培育": "unit_upgrade",
        "角色培育": "character_upgrade",
        "支援人員培育": "support_upgrade",
    }

    # 3. 逐一巡檢 4 大培育類別
    for idx, cat_name in enumerate(task.CATEGORIES, start=1):
        cat_key = CAT_KEYS.get(cat_name, f"cat_{idx}")
        logger.info(f"--- 巡檢培育類別 [{idx}/{len(task.CATEGORIES)}]: {cat_name} ({cat_key}) ---")

        # 向上微滑保證清單位於最頂端（最高難度 LV6 置頂）
        device.swipe_bezier((450, 450), (450, 750), duration_ms=400)
        device.random_sleep(0.8, 1.2)

        # 點選頂端卡片（最高難度 LV6）
        device.tap(task.TOP_STAGE_CARD[0], task.TOP_STAGE_CARD[1])
        device.random_sleep(1.0, 1.5)

        frame = device.screencap()
        cv2.imwrite(f"captures/temp/step4_cat_{idx}_{cat_key}.png", frame)
        logger.info(f"已記錄 [{cat_name}] 當前關卡狀態截圖: captures/temp/step4_cat_{idx}_{cat_key}.png")

        # 檢查最高難度是否已解鎖且滿三星
        ready, reason = task.check_highest_difficulty_ready(frame)
        if not ready:
            logger.warning(f"⚠️ [{cat_name}] {reason}！最高難度尚未具備略過資格，安全略過該類別。")
            cv2.imwrite(f"captures/temp/cultivation_locked_{cat_key}.png", frame)
            results[cat_name] = {
                "status": "SKIPPED_UNAVAILABLE",
                "difficulty": "LV6 (未具備三星/未解鎖)",
                "reason": reason,
            }
            if idx < len(task.CATEGORIES):
                task.next_category()
            continue

        # 檢查略過按鈕狀態與可用出擊次數
        if task.is_skip_button_enabled(frame):
            logger.info(f"[{cat_name}] 略過功能可用。準備執行動態最大次數 [>>] 略過...")
            task.execute_sweep()
            results[cat_name] = {
                "status": "SWEPT_MAX_SUCCESS",
                "difficulty": "LV6 (最高難度)",
                "reason": "已完成動態最大次數略過",
            }
            logger.success(f"[{cat_name}] 略過完成！")
            after_frame = device.screencap()
            cv2.imwrite(f"captures/temp/step4_cat_{idx}_{cat_key}_done.png", after_frame)
        else:
            logger.info(f"[{cat_name}] 略過按鈕為暗色（今日可出擊次數已為 0/5，已完成）。")
            results[cat_name] = {
                "status": "ALREADY_COMPLETED",
                "difficulty": "LV6 (最高難度)",
                "reason": "今日次數已耗盡 (0/5)",
            }

        # 切換至下一個類別
        if idx < len(task.CATEGORIES):
            task.next_category()

    # 4. 任務完成，乾淨返回主畫面
    logger.info("[Step 4] 巡檢完成，正在安全返回主畫面...")
    fsm.navigate_to_home()
    final_home = device.screencap()
    cv2.imwrite("captures/temp/step4_final_home.png", final_home)
    logger.success("已成功返回主畫面並記錄存檔: captures/temp/step4_final_home.png")

    # 5. 彙整輸出報告
    logger.info("=" * 60)
    logger.info("📋 【Step 4 強化培育關卡 執行總結報告】")
    logger.info("=" * 60)
    for cat_name, info in results.items():
        logger.info(f"• {cat_name:<10}: {info['status']:<20} | 難度: {info['difficulty']} | 詳情: {info['reason']}")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    success = run_step4()
    sys.exit(0 if success else 1)
