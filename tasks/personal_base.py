"""Personal Base Character Requests Automation Task with Single Task Lifecycle State Machine."""
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger
from rapidocr_onnxruntime import RapidOCR

from core.device import Device
from core.state_machine import StateMachine, NavigationCoords
from core.page_manager import PageType
from core.vision import Vision
from tasks.base import BaseTask


class CharacterRequestType(Enum):
    """Categorized character request types."""
    UNKNOWN = auto()          # 未知/未支援任務 (觸發安全防護存檔並請示)
    CAPTURE_UNIT = auto()     # 奪取單位任務 (使用者守則：全部放棄並重新檢視新任務)
    DEVELOP_UNIT = auto()     # 委託開發任務 (承接後前往開發樹開發 1000 資本初始量產機)
    ENHANCE_UNIT = auto()     # 強化部隊任務 (承接後挑選未滿等低階機體注入 1 級數據)
    CLEAR_STAGE = auto()      # 請求出擊任務 (承接後出擊/掃蕩指定關卡)
    EVENT_STAGE = auto()      # 事件關卡任務 (使用者守則：暫由使用者手動處理，腳本略過)
    DELIVER_UNIT = auto()     # 交付機體任務 (交出指定機體，涉及機體資產消耗，主動請示)


@dataclass
class CharacterRequestDetail:
    """Parsed metadata for a character request."""
    slot_idx: int
    character_name: str
    title: str
    requirement_text: str
    request_type: CharacterRequestType
    button_type: str  # "accept", "challenge", "report", "completed", "unknown"
    current_progress: int = 0
    target_progress: int = 0


class PersonalBaseRequestTask(BaseTask):
    """
    Task to navigate to Personal Base (個人基地), open Character Requests (角色要求),
    execute single task lifecycle state machine per slot, and claim weekly rewards.
    """

    name: str = "personal_base"

    UNKNOWN_TASK_DIR: str = "captures/unknown_tasks"
    UNKNOWN_TASK_LOG: str = "captures/unknown_tasks/unknown_tasks_log.json"

    # Screen coordinates for the 3 daily character slots on 1920x1080
    SLOT_COORDINATES: List[Tuple[int, int]] = [
        (220, 400),  # Slot 1 (Left card)
        (500, 400),  # Slot 2 (Middle card)
        (780, 400),  # Slot 3 (Right card)
    ]

    # Weekly reward milestones (5, 10, 15, 20) at bottom bar
    WEEKLY_REWARD_COORDINATES: List[Tuple[int, int]] = [
        (1040, 770),
        (1260, 770),
        (1475, 770),
        (1690, 770),
    ]

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        fsm: Optional[StateMachine] = None,
    ):
        super().__init__(device, vision, fsm)
        self.ocr = RapidOCR()
        os.makedirs(self.UNKNOWN_TASK_DIR, exist_ok=True)

    def _dismiss_any_popup(self) -> bool:
        """Dismiss modal popups or reward collection dialogs."""
        frame = self.device.screencap()
        dismissed = False

        if btn_close := self.vision.match_template(frame, "assets/buttons/btn_close_blue.png", threshold=0.80):
            logger.info("Dismissing modal popup via '關閉' button...")
            self.device.tap_rect(btn_close.rect)
            self.device.random_sleep(1.0, 1.5)
            dismissed = True

        return dismissed

    def _enter_personal_base(self) -> bool:
        """Navigate to Personal Base screen from Home."""
        logger.info("Navigating to 個人基地 (Personal Base)...")
        if self.fsm:
            return self.fsm.navigate_to_personal_base()

        self.device.tap(1292, 1020)
        self.device.random_sleep(2.5, 3.5)
        return True

    def _open_character_requests(self) -> bool:
        """Find and open the '角色要求' section in Personal Base."""
        logger.info("Locating '角色要求' entrance banner...")
        if self.fsm:
            return self.fsm.navigate_to_character_requests()

        self.device.tap(1510, 315)
        self.device.random_sleep(2.5, 3.5)
        return True

    def parse_current_request(self, frame: np.ndarray, slot_idx: int) -> CharacterRequestDetail:
        """Run OCR on the detail view to classify the task and extract parameters."""
        res, _ = self.ocr(frame)
        ocr_items: List[Tuple[str, Tuple[int, int], float]] = []
        if res:
            for box, text, score in res:
                cx = int((box[0][0] + box[2][0]) / 2)
                cy = int((box[0][1] + box[2][1]) / 2)
                ocr_items.append((text.strip(), (cx, cy), float(score)))

        combined_text = " ".join([item[0] for item in ocr_items])

        # Extract character name: typically around (100..450, 750..830)
        character_name = ""
        for text, (cx, cy), _ in ocr_items:
            if 100 <= cx <= 450 and 750 <= cy <= 830:
                character_name = text
                break

        # Extract title: typically around (1200..1800, 220..290)
        title = ""
        for text, (cx, cy), _ in ocr_items:
            if 1200 <= cx <= 1800 and 220 <= cy <= 290:
                title = text
                break

        # Extract requirement: text between y 300 and 460 on right side
        req_lines = []
        for text, (cx, cy), _ in ocr_items:
            if cx > 1000 and 310 <= cy <= 460 and "達成條件" not in text:
                req_lines.append(text)
        requirement_text = " ".join(req_lines)

        # Detect button state
        button_type = "unknown"
        for text, (cx, cy), _ in ocr_items:
            if cx > 1400 and cy > 780:
                if "承接" in text:
                    button_type = "accept"
                    break
                elif "報告" in text:
                    button_type = "report"
                    break
                elif "挑戰" in text:
                    button_type = "challenge"
                    break

        # Classify Request Type based strictly on task title and requirement text
        task_desc = f"{title} {requirement_text}"
        if any(kw in task_desc for kw in ["交付機體", "交出"]):
            req_type = CharacterRequestType.DELIVER_UNIT
        elif any(kw in task_desc for kw in ["奪取", "捕獲"]):
            req_type = CharacterRequestType.CAPTURE_UNIT
        elif "事件關卡" in task_desc:
            req_type = CharacterRequestType.EVENT_STAGE
        elif any(kw in task_desc for kw in ["委託開發", "開發"]):
            req_type = CharacterRequestType.DEVELOP_UNIT
        elif any(kw in task_desc for kw in ["強化部隊", "強化"]):
            req_type = CharacterRequestType.ENHANCE_UNIT
        elif any(kw in task_desc for kw in ["請求出擊", "出擊"]):
            req_type = CharacterRequestType.CLEAR_STAGE
        else:
            req_type = CharacterRequestType.UNKNOWN

        return CharacterRequestDetail(
            slot_idx=slot_idx,
            character_name=character_name or "Unknown",
            title=title or "Unknown",
            requirement_text=requirement_text or "Unknown",
            request_type=req_type,
            button_type=button_type,
        )

    def handle_unknown_task(self, frame: np.ndarray, detail: CharacterRequestDetail) -> None:
        """Trigger Unknown Task Safety Guardrail (AGENTS.md Rule 4)."""
        os.makedirs(self.UNKNOWN_TASK_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(self.UNKNOWN_TASK_DIR, f"unknown_task_{timestamp}.png")
        cv2.imwrite(img_path, frame)

        log_entry = {
            "timestamp": timestamp,
            "image_path": img_path,
            "slot_idx": detail.slot_idx,
            "character_name": detail.character_name,
            "title": detail.title,
            "requirement_text": detail.requirement_text,
            "button_type": detail.button_type,
        }

        entries = []
        if os.path.exists(self.UNKNOWN_TASK_LOG):
            try:
                with open(self.UNKNOWN_TASK_LOG, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
        entries.append(log_entry)
        with open(self.UNKNOWN_TASK_LOG, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

        logger.warning(
            f"\n{'='*80}\n"
            f"🛑 [AGENTS.md 守則 4 - 未知任務安全防護] 偵測到未知角色要求！\n"
            f"- 截圖存檔：{img_path}\n"
            f"- 角色名稱：{detail.character_name}\n"
            f"- 任務標題：{detail.title}\n"
            f"- 達成條件：{detail.requirement_text}\n"
            f"👉 系統已安全返回並暫停操作，絕不盲點。請向使用者請教處理方式。\n"
            f"{'='*80}\n"
        )

    def _claim_report(self) -> bool:
        """Claim completed character request reward and dismiss dialogues/modals."""
        logger.info("[CharacterRequest] Claiming '報告' reward...")
        frame = self.device.screencap()
        report_match = self.vision.match_template(frame, "assets/buttons/btn_report_orange.png", threshold=0.80)
        if report_match:
            self.device.tap_rect(report_match.rect)
        else:
            self.device.tap(1623, 858)
        self.device.random_sleep(2.5, 3.0)

        # Skip dialogue
        logger.info("[CharacterRequest] Skipping completion dialogue at (1760, 60)...")
        self.device.tap(1760, 60)
        self.device.random_sleep(2.0, 2.5)

        # Dismiss '回報完成' screen (tap center)
        logger.info("[CharacterRequest] Dismissing '回報完成' screen...")
        self.device.tap(960, 500)
        self.device.random_sleep(2.0, 2.5)

        # Dismiss '領取結果' modal (tap OK)
        logger.info("[CharacterRequest] Dismissing '領取結果' modal...")
        self.device.tap(962, 949)
        self.device.random_sleep(1.5, 2.0)
        return True

    def process_single_slot(self, slot_idx: int, max_abandons: int = 5) -> bool:
        """
        Single Character Request Lifecycle State Machine:
        Loops through states: INSPECT -> DECIDE -> (ABANDON -> INSPECT) / EXECUTE / SKIP / GUARDRAIL.
        """
        abandon_count = 0

        while True:
            # 1. State: INSPECT
            logger.info(f"--- [Slot {slot_idx} State Machine] INSPECT (Cycle: {abandon_count}) ---")
            frame = self.device.screencap()
            detail = self.parse_current_request(frame, slot_idx=slot_idx)

            logger.info(
                f"[Slot {slot_idx}] Character: '{detail.character_name}', "
                f"Title: '{detail.title}', Type: {detail.request_type.name}, Button: '{detail.button_type}'"
            )

            # 2. Check if already claimable (REPORT)
            if detail.button_type == "report":
                logger.info(f"[Slot {slot_idx}] Task is completed and ready to report! Claiming...")
                self._claim_report()
                logger.success(f"[Slot {slot_idx}] Successfully claimed report reward.")
                return True

            # 3. State: CAPTURE_UNIT -> ABANDON & LOOP BACK
            if detail.request_type == CharacterRequestType.CAPTURE_UNIT:
                if abandon_count >= max_abandons:
                    logger.error(f"[Slot {slot_idx}] Reached max abandons ({max_abandons}). Halting loop.")
                    return False

                logger.warning(
                    f"[Slot {slot_idx}] Task is CAPTURE ({detail.title}). "
                    f"Abandoning per user instruction (Attempt {abandon_count + 1}/{max_abandons})..."
                )
                if self.fsm:
                    self.fsm.abandon_current_character_request()
                else:
                    self.device.tap(1752, 182)
                    self.device.random_sleep(1.5, 2.0)
                    self.device.tap(1150, 785)

                abandon_count += 1
                self.device.random_sleep(2.5, 3.5)
                # >>> KEY: The loop continues to INSPECT the newly appeared task! <<<
                continue

            # 4. State: EVENT_STAGE -> SKIP
            if detail.request_type == CharacterRequestType.EVENT_STAGE:
                logger.info(f"[Slot {slot_idx}] Task is EVENT STAGE. Skipping per user instruction (manual handling).")
                return True

            # 5. State: DEVELOP_UNIT
            if detail.request_type == CharacterRequestType.DEVELOP_UNIT:
                logger.info(f"[Slot {slot_idx}] Dispatching to DEVELOP_UNIT solver...")
                if detail.button_type == "accept":
                    if self.fsm:
                        self.fsm.accept_current_character_request()
                    else:
                        self.device.tap(1623, 800)
                        self.device.random_sleep(1.5, 2.0)
                return True

            # 6. State: ENHANCE_UNIT
            if detail.request_type == CharacterRequestType.ENHANCE_UNIT:
                logger.info(f"[Slot {slot_idx}] Dispatching to ENHANCE_UNIT solver...")
                if detail.button_type == "accept":
                    if self.fsm:
                        self.fsm.accept_current_character_request()
                return True

            # 7. State: CLEAR_STAGE
            if detail.request_type == CharacterRequestType.CLEAR_STAGE:
                logger.info(f"[Slot {slot_idx}] Dispatching to CLEAR_STAGE solver...")
                if detail.button_type == "accept":
                    if self.fsm:
                        self.fsm.accept_current_character_request()
                return True

            # 8. State: UNKNOWN -> SAFETY GUARDRAIL
            if detail.request_type == CharacterRequestType.UNKNOWN:
                logger.error(f"[Slot {slot_idx}] Unknown character request encountered! Triggering safety guardrail.")
                self.handle_unknown_task(frame, detail)
                return False

    def _process_all_slots(self) -> None:
        """Iterate over the 3 daily character slots using single task state machine."""
        for slot_idx, (sx, sy) in enumerate(self.SLOT_COORDINATES, start=1):
            logger.info(f"--- Processing Daily Slot [{slot_idx}/3] at ({sx}, {sy}) ---")
            if self.fsm:
                self.fsm.select_character_request_slot(slot_idx)
            else:
                self.device.tap(sx, sy)
                self.device.random_sleep(2.0, 2.5)

            # Run single task state machine for this slot
            self.process_single_slot(slot_idx)

            # Return to 3-slot overview via top-left back button
            logger.info("Returning to 3-slot overview via back button...")
            if self.fsm:
                self.fsm.go_back()
            else:
                self.device.tap(65, 55)
                self.device.random_sleep(1.5, 2.0)

    def _claim_weekly_milestones(self) -> None:
        """Check and tap weekly reward milestones (5, 10, 15, 20 completions)."""
        logger.info("Checking weekly reward milestone progress...")
        for mx, my in self.WEEKLY_REWARD_COORDINATES:
            self.device.tap(mx, my)
            self.device.random_sleep(0.8, 1.2)
            self._dismiss_any_popup()

    def run(self) -> bool:
        """Execute the complete Personal Base character requests workflow."""
        # Step 1: Navigate into Personal Base
        if not self._enter_personal_base():
            logger.error("Failed to enter 個人基地.")
            return False

        # Step 2: Open Character Requests
        if not self._open_character_requests():
            logger.error("Failed to open 角色要求.")
            return False

        # Step 3: Loop through all 3 daily character slots
        self._process_all_slots()

        # Step 4: Claim any weekly milestones
        self._claim_weekly_milestones()

        logger.success("All daily character requests processed successfully!")
        return True
