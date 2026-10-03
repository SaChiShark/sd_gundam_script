"""Step 3: Inspect Character Requests (檢查角色任務) in Personal Base."""
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
from tasks.personal_base import PersonalBaseRequestTask


def run_step3():
    logger.info("=" * 60)
    logger.info("▶️ [Step 3] 前往個人基地並檢查角色任務狀態 (PersonalBaseRequestTask)")
    logger.info("=" * 60)

    config = AppConfig.load_from_file("config.yaml")
    device = Device(config.device)
    device.connect()

    vision = Vision()
    fsm = StateMachine(device, vision)

    task = PersonalBaseRequestTask(device, vision, fsm)

    # 1. 導航進入個人基地
    logger.info("[Step 3] 導航進入個人基地...")
    if not task._enter_personal_base():
        logger.error("無法進入個人基地！")
        return False

    # 2. 開啟角色要求總覽
    logger.info("[Step 3] 開啟『角色要求』總覽...")
    if not task._open_character_requests():
        logger.error("無法開啟角色要求！")
        return False

    # 截圖保存總覽
    overview_frame = device.screencap()
    cv2.imwrite("captures/temp/step3_slots_overview.png", overview_frame)
    logger.success("已保存卡槽總覽截圖至 captures/temp/step3_slots_overview.png")

    # 3. 逐一巡檢 3 個卡槽並彙整詳細狀態
    # 定義 3 個卡槽在總覽畫面的水平區間
    slot_x_ranges = [
        (90, 680),    # Slot 1
        (710, 1280),  # Slot 2
        (1290, 1850), # Slot 3
    ]

    overview_ocr = task.page_manager._extract_all_text(overview_frame)
    slot_reports = []

    for slot_idx in range(1, 4):
        logger.info(f"--- 巡檢卡槽 [{slot_idx}/3] ---")
        x_min, x_max = slot_x_ranges[slot_idx - 1]

        # 檢查總覽畫面上此卡槽區域內是否有冷卻倒數文字
        slot_cd_text = None
        for t, (cx, cy), _ in overview_ocr:
            if x_min <= cx <= x_max and 600 <= cy <= 750:
                if "距離更新" in t or "小時" in t or "還有" in t:
                    slot_cd_text = t
                    break

        if slot_cd_text:
            # 卡槽處於冷卻倒數中（無可接任務），直接由總覽記錄狀態與保存卡槽截圖
            logger.info(f"[Slot {slot_idx}] 卡槽冷卻中: {slot_cd_text}")
            card_crop = overview_frame[130:720, x_min:x_max]
            cv2.imwrite(f"captures/temp/step3_slot_{slot_idx}.png", card_crop)
            slot_reports.append({
                "slot": slot_idx,
                "status": "COOLDOWN",
                "character": "—",
                "title": "冷卻倒數中",
                "requirement": slot_cd_text,
                "button": "—"
            })
        else:
            # 存在有效角色任務，進入詳情頁面檢視
            logger.info(f"[Slot {slot_idx}] 偵測到進行中/可接角色任務，點擊進入詳情...")
            fsm.select_character_request_slot(slot_idx)

            frame = device.screencap()
            cv2.imwrite(f"captures/temp/step3_slot_{slot_idx}.png", frame)

            # 解析任務詳情
            detail = task.parse_current_request(frame, slot_idx=slot_idx)
            # 結合 YOLO 檢測按鈕
            btn_detected = "none"
            if fsm.detector and fsm.detector.is_ready():
                for cls in ["btn_accept", "btn_challenge", "btn_report", "btn_deliver"]:
                    if fsm.detector.find_target(frame, cls, conf=0.55):
                        btn_detected = cls
                        break

            logger.info(
                f"[Slot {slot_idx}] 角色: '{detail.character_name}', "
                f"任務: '{detail.title}', 類型: {detail.request_type.name}, 進度: {detail.current_progress}/{detail.target_progress}, "
                f"按鈕(OCR): '{detail.button_type}', 按鈕(YOLO): '{btn_detected}'"
            )
            slot_reports.append({
                "slot": slot_idx,
                "status": "ACTIVE",
                "character": detail.character_name,
                "title": detail.title,
                "requirement": f"{detail.requirement_text} ({detail.current_progress}/{detail.target_progress})",
                "button": detail.button_type,
                "yolo_button": btn_detected
            })

            # 返回總覽
            fsm.go_back()

    # 4. 檢查週常成就里程碑
    task._claim_weekly_milestones()

    # 5. 安全返回主頁
    logger.info("[Step 3] 巡檢完成，安全返回主畫面...")
    fsm.navigate_to_home()

    # 輸出彙報
    logger.info("=" * 60)
    logger.success("📊 [Step 3 角色任務巡檢報告]")
    for r in slot_reports:
        logger.info(f"Slot {r['slot']}: [{r['status']}] {r['character']} - {r['title']} ({r['requirement']}) | 按鈕: {r.get('button', '—')}")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    success = run_step3()
    sys.exit(0 if success else 1)
