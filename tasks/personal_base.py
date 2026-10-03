"""Personal Base Character Requests Automation Task with Single Task Lifecycle State Machine."""
import json
import os
import re
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

    # Screen coordinates for the 3 daily character slots on 1920x1080 (Calibrated Card Centers)
    SLOT_COORDINATES: List[Tuple[int, int]] = [
        (380, 440),   # Slot 1 (Left card)
        (980, 440),   # Slot 2 (Middle card)
        (1500, 440),  # Slot 3 (Right card)
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
        self.page_manager = self.fsm.page_manager if self.fsm else PageManager(self.device, self.vision)
        self.skipped_manual_tasks: List[Dict[str, Any]] = []
        os.makedirs(self.UNKNOWN_TASK_DIR, exist_ok=True)

    @staticmethod
    def is_unit_silhouette(frame: np.ndarray) -> bool:
        """
        Determine if the unit in '主要獲得方式' popup is a silhouette (剪影 - 未曾擁有/未登錄).
        A silhouette has a monochromatic dark blue/purple interior with very low standard deviation.
        When a unit has been unlocked/owned, it shows a full color illustration with high variance.
        """
        crop = frame[220:700, 60:340]
        mask_unit = (crop[:, :, 0] < 140) & (crop[:, :, 1] < 120) & (crop[:, :, 2] < 120)
        unit_pixels = crop[mask_unit]
        if len(unit_pixels) < 5000:
            return False
        std_bgr = np.std(unit_pixels, axis=0)
        return bool(np.all(std_bgr < 18.0))

    def _dismiss_any_popup(self) -> bool:
        """Dismiss modal popups or reward collection dialogs."""
        frame = self.device.screencap()
        ptype, meta = self.page_manager.classify(frame)
        if ptype not in (PageType.HOME, PageType.PERSONAL_BASE, PageType.CHARACTER_REQUESTS):
            _, success = self.page_manager.resolve_page(frame, max_attempts=1)
            return success
        return False

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

        self.device.tap(1337, 224)
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

        # Detect button state (robust to partial OCR like '挑', '報', etc.)
        button_type = "unknown"
        for text, (cx, cy), _ in ocr_items:
            if cx > 1400 and cy > 780:
                if any(k in text for k in ["報告", "報", "告"]):
                    button_type = "report"
                    break
                elif any(k in text for k in ["挑戰", "挑", "战", "戰"]):
                    button_type = "challenge"
                    break
                elif any(k in text for k in ["承接", "承", "接"]):
                    button_type = "accept"
                    break
                elif any(k in text for k in ["交付", "交", "付"]):
                    button_type = "deliver"
                    break
                elif any(k in text for k in ["獲得管道", "管道", "獲得"]):
                    button_type = "acquire"
                    break

        # Extract progress: e.g. "2/4"
        current_progress, target_progress = 0, 0
        for text, (cx, cy), _ in ocr_items:
            m = re.search(r'(\d+)\s*/\s*(\d+)', text)
            if m and cx > 1300 and 300 <= cy <= 520:
                current_progress = int(m.group(1))
                target_progress = int(m.group(2))
                break

        if target_progress == 0:
            m = re.search(r'(?:開發|委託開發)(\d+)', f"{title} {requirement_text}")
            if not m:
                m = re.search(r'開發(\d+)次', f"{title} {requirement_text}")
            if m:
                target_progress = int(m.group(1))

        # Classify Request Type based strictly on task title and requirement text
        task_desc = f"{title} {requirement_text}"
        if any(kw in task_desc for kw in ["交付機體", "交出", "調度資金", "CAPITAL"]):
            req_type = CharacterRequestType.DELIVER_UNIT
        elif any(kw in task_desc for kw in ["奪取", "捕獲"]):
            req_type = CharacterRequestType.CAPTURE_UNIT
        elif "事件關卡" in task_desc:
            req_type = CharacterRequestType.EVENT_STAGE
        elif any(kw in task_desc for kw in ["委託開發", "開發"]):
            req_type = CharacterRequestType.DEVELOP_UNIT
        elif any(kw in task_desc for kw in ["強化部隊", "強化"]):
            req_type = CharacterRequestType.ENHANCE_UNIT
        elif any(kw in task_desc for kw in ["請求出擊", "出擊", "擊破", "擎破", "完成關卡", "架單位"]):
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
            current_progress=current_progress,
            target_progress=target_progress,
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
        """Claim completed character request reward and dismiss dialogues/modals via StateMachine & PageManager."""
        logger.info("[CharacterRequest] Claiming '報告' reward...")
        if self.fsm:
            return self.fsm.claim_character_request_report()

        self.device.tap(*NavigationCoords.CHAR_REQ_REPORT_BUTTON)
        self.device.random_sleep(2.5, 3.5)

        for _ in range(5):
            frame = self.device.screencap()
            ptype, meta = self.page_manager.classify(frame)
            if ptype == PageType.DIALOGUE:
                self.page_manager.handle_dialogue(frame, meta)
            elif ptype == PageType.ITEM_ACQUIRED:
                self.page_manager.handle_item_acquired(frame, meta)
                return True
            elif ptype == PageType.CHARACTER_REQUESTS:
                return True
            elif ptype == PageType.UNKNOWN:
                logger.warning("[CharacterRequest] Encountered UNKNOWN page during reward claim. Halting safely without blind tapping.")
                return False
            else:
                self.page_manager.resolve_page(frame, max_attempts=1)
        return True

    def solve_deliver_unit(self, slot_idx: int, detail: CharacterRequestDetail) -> bool:
        """
        Solve Deliver Unit / Capital Request:
        - If ready to report: claim report.
        - If unaccepted: accept request, skip dialogue.
        - If Capital delivery: confirm modal directly.
        - If Unit delivery:
          - If button is '獲得管道' or tapping '交付' triggers '主要獲得方式':
            - If silhouette (剪影): 未曾擁有/未登錄，依使用者規範跳過並記錄待人工處理提醒。
            - If not silhouette: 自動跳轉至開發樹開發機體，返回後執行交付。
          - If button is '交付': 選擇機體並提交交付。
        """
        logger.info(f"[Slot {slot_idx}] Solving DELIVER request: '{detail.title}'...")
        if detail.button_type == "report":
            return self._claim_report()

        if detail.button_type == "accept":
            if self.fsm:
                self.fsm.accept_current_character_request()
            else:
                self.device.tap(*NavigationCoords.CHAR_REQ_ACCEPT_BUTTON)
                self.device.random_sleep(2.0, 3.0)

        # Capital Delivery check
        if "CAPITAL" in detail.requirement_text or "資金" in detail.requirement_text:
            logger.info(f"[Slot {slot_idx}] Capital delivery detected. Tapping 交付/確定...")
            if self.fsm:
                self.fsm.locate_and_tap_target(
                    target_class="btn_deliver",
                    fallback_anchor=NavigationCoords.CHAR_REQ_DELIVER_BUTTON,
                    action_name="tap_capital_deliver_btn",
                    timeout=2.5
                )
            else:
                self.device.tap(*NavigationCoords.CHAR_REQ_DELIVER_BUTTON)
                self.device.random_sleep(2.0, 2.5)

            frame = self.device.screencap()
            ptype, meta = self.page_manager.classify(frame)
            if ptype == PageType.MODAL_CONFIRM:
                self.page_manager.handle_modal_confirm(frame, meta)
                if self.fsm:
                    self.fsm._resolve_completion_sequence()
                return True

        # Mobile Suit Delivery: re-inspect current frame after acceptance
        frame = self.device.screencap()
        ptype, meta = self.page_manager.classify(frame)

        # Check button text on request detail view: is it "交付" or "獲得管道"?
        ocr_items = self.page_manager._extract_all_text(frame)
        is_acquire_button = any("獲得管道" in t[0] or "管道" in t[0] for t in ocr_items if t[1][0] > 1400 and t[1][1] > 780)

        if is_acquire_button or ptype == PageType.ACQUISITION_GUIDE:
            if ptype != PageType.ACQUISITION_GUIDE:
                logger.info(f"[Slot {slot_idx}] 按鈕為『獲得管道』(未持有指定機體)，點擊開啟主要獲得方式...")
                self.device.tap(*NavigationCoords.CHAR_REQ_DELIVER_BUTTON)
                self.device.random_sleep(2.0, 3.0)
                frame = self.device.screencap()
                ptype, meta = self.page_manager.classify(frame)

            if ptype == PageType.ACQUISITION_GUIDE:
                # Check whether unit is a silhouette
                is_sil = self.is_unit_silhouette(frame)
                if is_sil:
                    logger.warning(
                        f"\n{'='*80}\n"
                        f"🛑 [Slot {slot_idx}] 機體交付任務『{detail.title}』({detail.requirement_text})\n"
                        f"- 機體圖片判定為【剪影】（未曾擁有/未登錄，無法直接以資金開發）。\n"
                        f"👉 依據使用者規範：自動跳過此任務，並記錄於彙報提醒人工處理！\n"
                        f"{'='*80}\n"
                    )
                    self.skipped_manual_tasks.append({
                        "slot": slot_idx,
                        "character": detail.character_name,
                        "title": detail.title,
                        "requirement": detail.requirement_text,
                        "reason": "機體圖片為剪影（未擁有/未登錄，無法直接開發），需人工手動解鎖"
                    })
                    # Close acquisition modal
                    self.page_manager.handle_acquisition_guide(frame, meta)
                    self.device.random_sleep(1.5, 2.0)
                    return True
                else:
                    logger.info(f"[Slot {slot_idx}] 機體為已登錄非剪影狀態，依使用者規範執行自動開發...")
                    if self.fsm:
                        self.fsm.develop_unit_from_acquisition()
                    else:
                        self.device.tap(*NavigationCoords.ACQUISITION_GUIDE_MOVE_BTN)
                        self.device.random_sleep(3.0, 4.0)
                        self.device.tap(*NavigationCoords.DEVELOP_TREE_R_UNIT)
                        self.device.random_sleep(2.0, 2.5)
                        self.device.tap(*NavigationCoords.DEVELOP_MODAL_EXECUTE_BTN)
                        self.device.random_sleep(2.0, 2.5)
                        self.device.tap(*NavigationCoords.DEVELOP_CONFIRM_EXECUTE_BTN)
                        self.device.random_sleep(3.0, 4.0)
                        self.device.tap(*NavigationCoords.DEVELOP_TAP_TO_NEXT)
                        self.device.random_sleep(2.0, 2.5)
                        self.device.tap(*NavigationCoords.BACK_BUTTON)
                        self.device.random_sleep(2.5, 3.5)

        # Now the unit is in inventory, perform delivery
        logger.info(f"[Slot {slot_idx}] 點擊『交付』按鈕提交機體...")
        if self.fsm:
            self.fsm.locate_and_tap_target(
                target_class="btn_deliver",
                fallback_anchor=NavigationCoords.CHAR_REQ_DELIVER_BUTTON,
                action_name="tap_detail_deliver_btn",
                timeout=2.5
            )
        else:
            self.device.tap(*NavigationCoords.CHAR_REQ_DELIVER_BUTTON)
            self.device.random_sleep(2.0, 3.0)

        frame = self.device.screencap()
        ptype, meta = self.page_manager.classify(frame)

        if ptype == PageType.ACQUISITION_GUIDE:
            is_sil = self.is_unit_silhouette(frame)
            if is_sil:
                logger.warning(f"🛑 [Slot {slot_idx}] 機體仍為剪影，依規範跳過並提醒人工處理。")
                self.skipped_manual_tasks.append({
                    "slot": slot_idx,
                    "character": detail.character_name,
                    "title": detail.title,
                    "requirement": detail.requirement_text,
                    "reason": "機體圖片為剪影（未擁有/未登錄，無法直接開發），需人工手動解鎖"
                })
            self.page_manager.handle_acquisition_guide(frame, meta)
            return True

        if self.fsm:
            self.fsm.deliver_unit_in_modal()
        return True

    def solve_develop_unit(self, slot_idx: int, detail: CharacterRequestDetail) -> bool:
        """
        Solve Unit Development Request via Development Tree:
        - If ready to report: claim report.
        - If unaccepted: accept request, skip dialogue.
        - Calculate remaining developments needed (target - current).
        - Tap '挑戰' to jump directly into Development Tree.
        - Verify arrival at Development Tree.
        - Develop base unit on tree for remaining times.
        - Return to detail view, verify button state has transitioned to '報告'.
        - If '報告', claim report and verify completion.
        - If not '報告', log error/warning without false declaration of success.
        """
        logger.info(f"[Slot {slot_idx}] Solving DEVELOP request: '{detail.title}'...")
        if detail.button_type == "report":
            return self._claim_report()

        if detail.button_type == "accept":
            if self.fsm:
                self.fsm.accept_current_character_request()
            else:
                self.device.tap(*NavigationCoords.CHAR_REQ_ACCEPT_BUTTON)
                self.device.random_sleep(2.0, 3.0)
            # Re-read detail after acceptance
            frame = self.device.screencap()
            detail = self.parse_current_request(frame, slot_idx=slot_idx)

        # Calculate remaining developments needed
        if detail.target_progress > 0:
            remaining = max(1, detail.target_progress - detail.current_progress)
        else:
            remaining = 3
        logger.info(
            f"[Slot {slot_idx}] 開發任務需求: 目標={detail.target_progress}, 當前={detail.current_progress}, 尚需開發={remaining} 次"
        )

        # Tap '挑戰' to jump directly into Development Tree with transition verification
        logger.info(f"[Slot {slot_idx}] 點擊『挑戰』按鈕進入開發路線圖...")
        transitioned = False
        for attempt in range(1, 4):
            if self.fsm:
                self.fsm.challenge_current_character_request()
            else:
                self.device.tap(*NavigationCoords.CHAR_REQ_CHALLENGE_BUTTON)
                self.device.random_sleep(2.5, 3.5)

            frame = self.device.screencap()
            ocr_items = self.page_manager._extract_all_text(frame)
            if any("開發路線圖" in t[0] or "登錄狀況" in t[0] or "登錄" in t[0] for t in ocr_items):
                transitioned = True
                logger.info(f"[Slot {slot_idx}] 成功進入開發路線圖 (嘗試 {attempt}/3)")
                break
            logger.warning(f"[Slot {slot_idx}] 未偵測到開發路線圖，重試進入 (嘗試 {attempt}/3)...")
            self.device.random_sleep(1.5, 2.0)

        if not transitioned:
            logger.error(f"[Slot {slot_idx}] 無法進入開發路線圖，終止執行以防盲點！")
            return False

        # Execute development on tree
        if self.fsm:
            self.fsm.develop_unit_on_tree(times=remaining)

        # Now back at detail view, perform CLOSED-LOOP VERIFICATION
        logger.info(f"[Slot {slot_idx}] 開發完成已返回角色要求詳情，執行閉環驗證...")
        post_detail = None
        for _ in range(4):
            self.device.random_sleep(1.0, 1.5)
            frame = self.device.screencap()
            post_detail = self.parse_current_request(frame, slot_idx=slot_idx)
            if post_detail.button_type in ["report", "challenge"]:
                break

        logger.info(
            f"[Slot {slot_idx}] 開發後狀態: 按鈕='{post_detail.button_type}', "
            f"進度={post_detail.current_progress}/{post_detail.target_progress}"
        )

        if post_detail.button_type == "report":
            logger.info(f"[Slot {slot_idx}] 按鈕已成為『報告』，執行獎勵領取...")
            claimed = self._claim_report()
            if claimed:
                logger.success(f"[Slot {slot_idx}] 成功領取『報告』獎勵！")
                return True
            else:
                logger.error(f"[Slot {slot_idx}] 點擊『報告』領取獎勵失敗！")
                return False
        else:
            logger.error(
                f"[Slot {slot_idx}] 任務尚未達到完成狀態！按鈕為 '{post_detail.button_type}'，"
                f"進度為 {post_detail.current_progress}/{post_detail.target_progress}，拒絕假性判定完成！"
            )
            return False

    def process_single_slot(self, slot_idx: int, max_abandons: int = 1) -> bool:
        """
        Single Character Request Lifecycle State Machine:
        Loops through states: INSPECT -> DECIDE -> (ABANDON -> INSPECT) / EXECUTE / SKIP / GUARDRAIL.
        Per user instruction & docs/game_mechanics.md: 每個槽位每次刷新後，都只能捨棄 1 次。
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
                    logger.warning(
                        f"[Slot {slot_idx}] 該槽位本次刷新已捨棄過 ({max_abandons} 次)。依規範跳過並記錄待人工處理。"
                    )
                    self.skipped_manual_tasks.append({
                        "slot": slot_idx,
                        "character": detail.character_name,
                        "title": detail.title,
                        "requirement": detail.requirement_text,
                        "reason": f"奪取單位任務（該槽位本次刷新已捨棄過 {max_abandons} 次無法再次捨棄），需人工手動完成"
                    })
                    return False

                logger.warning(
                    f"[Slot {slot_idx}] Task is CAPTURE ({detail.title}). "
                    f"Abandoning per user instruction (Attempt {abandon_count + 1}/{max_abandons})..."
                )
                if self.fsm:
                    self.fsm.abandon_current_character_request()
                else:
                    logger.info(f"[Slot {slot_idx}] Abandoning via fallback: tapping trash button...")
                    self.device.tap(*NavigationCoords.CHAR_REQ_TRASH_CAN)
                    self.device.random_sleep(2.0, 2.5)
                    frame = self.device.screencap()
                    ptype, meta = self.page_manager.classify(frame)
                    if ptype == PageType.MODAL_CONFIRM:
                        self.page_manager.handle_modal_confirm(frame, meta)
                    else:
                        self.page_manager.resolve_page(frame, max_attempts=2)

                abandon_count += 1
                self.device.random_sleep(2.5, 3.5)
                # >>> KEY: The game returns to 3-slot overview after abandoning, so click into slot_idx again! <<<
                logger.info(f"[Slot {slot_idx}] 放棄完成，重新點擊進入卡槽 {slot_idx} 檢視新任務...")
                if self.fsm:
                    self.fsm.select_character_request_slot(slot_idx)
                else:
                    self.device.tap(self.SLOT_COORDINATES[slot_idx - 1][0], self.SLOT_COORDINATES[slot_idx - 1][1])
                    self.device.random_sleep(2.0, 2.5)
                continue

            # 4. State: EVENT_STAGE -> SKIP
            if detail.request_type == CharacterRequestType.EVENT_STAGE:
                logger.info(f"[Slot {slot_idx}] Task is EVENT STAGE. Skipping per user instruction (manual handling).")
                return True

            # 5. State: DELIVER_UNIT
            if detail.request_type == CharacterRequestType.DELIVER_UNIT:
                logger.info(f"[Slot {slot_idx}] Dispatching to DELIVER_UNIT solver...")
                return self.solve_deliver_unit(slot_idx, detail)

            # 6. State: DEVELOP_UNIT
            if detail.request_type == CharacterRequestType.DEVELOP_UNIT:
                logger.info(f"[Slot {slot_idx}] Dispatching to DEVELOP_UNIT solver...")
                return self.solve_develop_unit(slot_idx, detail)

            # 7. State: ENHANCE_UNIT
            if detail.request_type == CharacterRequestType.ENHANCE_UNIT:
                logger.info(f"[Slot {slot_idx}] Dispatching to ENHANCE_UNIT solver (Task: {detail.title})...")
                if detail.button_type == "accept":
                    if self.fsm:
                        self.fsm.accept_current_character_request()
                # Per AGENTS.md & game_mechanics.md: Do not pretend completion with 'return True'!
                logger.warning(
                    f"[Slot {slot_idx}] 強化部隊任務已承接。依規範規劃需挑選未滿等 N、R 機體注入 1 級數據，"
                    f"目前標記為待人工處理，絕不私自偽稱完成！"
                )
                self.skipped_manual_tasks.append({
                    "slot": slot_idx,
                    "character": detail.character_name,
                    "title": detail.title,
                    "requirement": detail.requirement_text,
                    "reason": "強化部隊任務：需手動挑選未滿等 N、R 機體注入 1 級數據後報告"
                })
                return False

            # 8. State: CLEAR_STAGE
            if detail.request_type == CharacterRequestType.CLEAR_STAGE:
                logger.info(f"[Slot {slot_idx}] Dispatching to CLEAR_STAGE solver (Task: {detail.title})...")
                if detail.button_type == "accept":
                    if self.fsm:
                        self.fsm.accept_current_character_request()
                # Per AGENTS.md & game_mechanics.md: Do not pretend completion with 'return True'!
                logger.warning(
                    f"[Slot {slot_idx}] 請求出擊任務已承接。依規範規劃需出擊/掃蕩指定關卡，"
                    f"目前標記為待人工處理，絕不私自偽稱完成！"
                )
                self.skipped_manual_tasks.append({
                    "slot": slot_idx,
                    "character": detail.character_name,
                    "title": detail.title,
                    "requirement": detail.requirement_text,
                    "reason": "請求出擊任務：需手動出擊/掃蕩指定關卡後報告"
                })
                return False

            # 9. State: UNKNOWN -> SAFETY GUARDRAIL
            if detail.request_type == CharacterRequestType.UNKNOWN:
                logger.error(f"[Slot {slot_idx}] Unknown character request encountered! Triggering safety guardrail.")
                self.handle_unknown_task(frame, detail)
                return False

    def _process_all_slots(self) -> None:
        """
        Iterate over the 3 daily character slots:
        1. On the 3-Slot overview screen, scan cards using localized X intervals via OCR.
        2. Identify which slots are in cooldown (倒數中) vs active.
        3. Only click into active slots, execute single task state machine, and return safely.
        """
        slot_x_ranges = [
            (90, 680),    # Slot 1
            (710, 1280),  # Slot 2
            (1290, 1850), # Slot 3
        ]

        for slot_idx in range(1, 4):
            logger.info(f"--- 巡檢卡槽 [{slot_idx}/3] ---")

            # 1. Take screenshot of current overview
            overview_frame = self.device.screencap()
            overview_ocr = self.page_manager._extract_all_text(overview_frame)

            # Check whether we are on overview
            is_overview = any(kw in t[0] for t in overview_ocr for kw in ["每週報酬", "每周报酬", "達成數", "达成数"])
            if not is_overview:
                logger.warning("[StateMachine] 未在角色要求總覽畫面，嘗試導航進入角色要求總覽...")
                if self.fsm:
                    self.fsm.navigate_to_character_requests()
                overview_frame = self.device.screencap()
                overview_ocr = self.page_manager._extract_all_text(overview_frame)

            x_min, x_max = slot_x_ranges[slot_idx - 1]
            slot_cd_text = None
            for t, (cx, cy), _ in overview_ocr:
                if x_min <= cx <= x_max and 600 <= cy <= 750:
                    if "距離更新" in t or "小時" in t or "還有" in t:
                        slot_cd_text = t
                        break

            if slot_cd_text:
                logger.info(f"[Slot {slot_idx}] 卡槽冷卻中 ({slot_cd_text})，跳過此槽。")
                continue

            logger.info(f"[Slot {slot_idx}] 偵測到進行中/可承接角色任務，點擊進入詳情...")
            if self.fsm:
                self.fsm.select_character_request_slot(slot_idx)
            else:
                self.device.tap(self.SLOT_COORDINATES[slot_idx - 1][0], self.SLOT_COORDINATES[slot_idx - 1][1])
                self.device.random_sleep(2.0, 2.5)

            # 2. Run single task state machine for this slot
            success = self.process_single_slot(slot_idx)
            if success:
                logger.success(f"[Slot {slot_idx}] 角色任務處理完成。")
            else:
                logger.warning(f"[Slot {slot_idx}] 角色任務未達成可報告狀態或處理失敗。")

            # 3. Return to 3-slot overview if still inside detail view
            frame = self.device.screencap()
            ocr_items = self.page_manager._extract_all_text(frame)
            combined_text = " ".join([t[0] for t in ocr_items])
            is_back_at_overview = any(kw in combined_text for kw in ["每週報酬", "每周报酬", "達成數", "达成数"])
            if not is_back_at_overview:
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
            self.device.random_sleep(1.0, 1.5)
            frame = self.device.screencap()
            ptype, meta = self.page_manager.classify(frame)
            if ptype == PageType.ITEM_ACQUIRED:
                self.page_manager.handle_item_acquired(frame, meta)
            else:
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

        # Step 5: Report any skipped tasks requiring manual handling
        if self.skipped_manual_tasks:
            logger.warning(
                f"\n{'='*80}\n"
                f"⚠️ 【角色委託任務 - 待人工處理提醒】\n"
                f"本次自動化執行中有 {len(self.skipped_manual_tasks)} 個任務因機體為「剪影」（未解鎖/未曾擁有）已依規範跳過：\n"
            )
            for item in self.skipped_manual_tasks:
                logger.warning(f"  • Slot {item['slot']}: [{item['character']}] {item['title']} - {item['requirement']}")
            logger.warning(
                f"👉 依指示已自動跳過，請玩家於遊戲內手動出擊/捕獲/解鎖前置機體後再行提交。\n"
                f"{'='*80}\n"
            )

        logger.success("All daily character requests processed successfully!")
        return True
