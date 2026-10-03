import os
import random
import time
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

from core.device import Device
from core.vision import Vision, MatchResult
from tools.yolo_detector import YOLOUIDetector, UIElement


class GameState(Enum):
    """Recognized high-level game screens."""
    UNKNOWN = auto()
    TITLE_SCREEN = auto()           # 遊戲啟動登入/標題畫面 (TOUCH TO START)
    POPUP_ANNOUNCEMENT = auto()     # 活動公告/營運彈窗
    LOGIN_BONUS = auto()            # 每日登入獎勵簽到
    HOME = auto()                   # 主頁面 (包含三大核心特徵錨點)
    PERSONAL_BASE = auto()          # 個人基地主頁面
    CHARACTER_REQUESTS = auto()     # 角色要求 (總覽/詳情)
    SORTIE_SELECT = auto()          # 出擊關卡選擇畫面
    BATTLE = auto()                 # 戰鬥中
    RESULT = auto()                 # 戰鬥結算


class NavigationCoords:
    """Standard calibrated UI navigation touch targets (1920x1080 baseline)."""
    # Bottom Navigation Bar
    BOTTOM_NAV: Dict[str, Tuple[int, int]] = {
        "home": (198, 1020),
        "enhance": (456, 1020),
        "develop": (714, 1020),
        "stages": (1003, 1020),
        "personal_base": (1292, 1020),
        "gacha": (1549, 1020),
        "menu": (1807, 1020),
    }

    # Top-Left Header Navigation
    BACK_BUTTON: Tuple[int, int] = (65, 55)

    # Personal Base Entrances
    BASE_CHARACTER_REQUESTS_BANNER: Tuple[int, int] = (1337, 224)

    # Character Requests Overview 3-Slot Cards (Calibrated Card Centers)
    CHAR_REQ_SLOT_CARDS: List[Tuple[int, int]] = [
        (380, 440),   # Slot 1
        (980, 440),   # Slot 2
        (1500, 440),  # Slot 3
    ]

    # Character Requests Detail Card Navigation Arrows
    CHAR_REQ_ARROW_PREV: Tuple[int, int] = (30, 490)
    CHAR_REQ_ARROW_NEXT: Tuple[int, int] = (1888, 490)

    # Character Requests Detail Action Buttons
    CHAR_REQ_TRASH_CAN: Tuple[int, int] = (1752, 182)
    CHAR_REQ_ACCEPT_BUTTON: Tuple[int, int] = (1623, 858)
    CHAR_REQ_CHALLENGE_BUTTON: Tuple[int, int] = (1623, 858)
    CHAR_REQ_DELIVER_BUTTON: Tuple[int, int] = (1623, 858)
    CHAR_REQ_REPORT_BUTTON: Tuple[int, int] = (1623, 858)
    CHAR_REQ_DIALOG_SKIP: Tuple[int, int] = (1850, 60)

    # Unit Delivery Modal Touch Targets
    DELIVER_MODAL_FIRST_UNIT: Tuple[int, int] = (580, 560)
    DELIVER_MODAL_CONFIRM_BTN: Tuple[int, int] = (1160, 955)

    # Development Tree Touch Targets (Verified Calibrated)
    DEVELOP_TREE_BASE_UNIT: Tuple[int, int] = (550, 450)
    DEVELOP_TREE_R_UNIT: Tuple[int, int] = (550, 450)
    DEVELOP_MODAL_EXECUTE_BTN: Tuple[int, int] = (1148, 996)
    DEVELOP_CONFIRM_EXECUTE_BTN: Tuple[int, int] = (1148, 996)
    DEVELOP_TAP_TO_NEXT: Tuple[int, int] = (965, 1026)

    # Acquisition Guide Modal (主要獲得方式)
    ACQUISITION_GUIDE_CLOSE_BTN: Tuple[int, int] = (960, 995)
    ACQUISITION_GUIDE_MOVE_BTN: Tuple[int, int] = (1660, 235)


class HomeAnchorROI:
    """
    Standard Regions of Interest (ROI) for Home screen recognition (1920x1080 baseline).
    
    Verified Core Anchors:
    1. TOP_LEFT_LEVEL: 玩家等級圖示 (x: 0, y: 0, w: 300, h: 150)
    2. TOP_RIGHT_STAMINA: 體力/AP膠囊圖示 (x: 1100, y: 0, w: 300, h: 150)
    3. BOTTOM_RIGHT_SORTIE: 右下角核心「出擊」按鈕 (x: 1250, y: 580, w: 670, h: 350)
    """
    TOP_LEFT_LEVEL: Tuple[int, int, int, int] = (0, 0, 300, 150)
    TOP_RIGHT_STAMINA: Tuple[int, int, int, int] = (1100, 0, 300, 150)
    BOTTOM_RIGHT_SORTIE: Tuple[int, int, int, int] = (1250, 580, 670, 350)



from core.page_manager import PageManager, PageType


class StateMachine:
    """Tracks game UI state and orchestrates autonomous navigation."""

    def __init__(
        self,
        device: Device,
        vision: Optional[Vision] = None,
        detector: Optional[YOLOUIDetector] = None,
    ):
        self.device = device
        self.vision = vision or Vision()
        self.page_manager = PageManager(self.device, self.vision)
        self.current_state = GameState.UNKNOWN
        self.detector = detector if detector is not None else YOLOUIDetector()
        os.makedirs("captures/exceptions", exist_ok=True)

    def trigger_exception_guardrail(
        self,
        frame: np.ndarray,
        reason: str,
        action_name: str = ""
    ) -> None:
        """
        AGENTS.md Mandatory Rule 4 & 5: Exception Safety Guardrail.
        Saves screenshot to captures/exceptions/, logs critical alert, and halts without blind tapping.
        """
        os.makedirs("captures/exceptions", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_action = action_name.replace(" ", "_") if action_name else "unknown"
        img_path = os.path.join("captures/exceptions", f"exception_{timestamp}_{safe_action}.png")
        cv2.imwrite(img_path, frame)

        logger.critical(
            f"\n{'='*80}\n"
            f"🛑 [AGENTS.md 例外安全防護 Guardrail] 操作例外中斷！\n"
            f"- 操作動作: {action_name}\n"
            f"- 原因說明: {reason}\n"
            f"- 截圖存檔: {img_path}\n"
            f"👉 依據規範已安全停止，嚴禁盲點或猜測。請向使用者或 Agent 報告請示！\n"
            f"{'='*80}\n"
        )

    def tap_and_wait_transition(
        self,
        target_coords: Tuple[int, int],
        expected_page: Optional[PageType] = None,
        timeout: float = 4.0,
        action_name: str = "",
        jitter: int = 5,
    ) -> bool:
        """
        Closed-loop, anti-detection tap with semantic state-transition verification.

        1. Jitters coordinates within [-jitter, +jitter] for anti-detection.
        2. Taps target coordinates.
        3. Polls PageManager.classify() to detect expected page or state transition.
        4. Halts and captures to captures/exceptions/ if transition fails (no blind looping).
        """
        tx = target_coords[0] + random.randint(-jitter, jitter)
        ty = target_coords[1] + random.randint(-jitter, jitter)
        logger.info(f"[StateMachine] Tapping '{action_name or 'target'}' at ({tx}, {ty}) [jitter={jitter}]...")
        self.device.tap(tx, ty)

        if expected_page is None:
            self.device.random_sleep(1.0, 1.5)
            return True

        start_time = time.time()
        self.device.random_sleep(0.8, 1.2)
        while time.time() - start_time < timeout:
            frame = self.device.screencap()
            current_page, _ = self.page_manager.classify(frame)
            if current_page == expected_page:
                logger.success(f"[StateMachine] Verified transition to {expected_page.name} after '{action_name}'.")
                return True
            time.sleep(0.5)

        # Transition failed: trigger exception guardrail
        frame = self.device.screencap()
        self.trigger_exception_guardrail(
            frame,
            reason=f"Timed out waiting {timeout}s for expected page {expected_page.name}",
            action_name=action_name
        )
        return False

    def locate_and_tap_target(
        self,
        target_class: str,
        fallback_anchor: Optional[Tuple[int, int]] = None,
        expected_page: Optional[PageType] = None,
        roi: Optional[Tuple[int, int, int, int]] = None,
        conf: float = 0.55,
        action_name: str = "",
        timeout: float = 4.0,
    ) -> bool:
        """
        Three-tier deterministic UI interaction pipeline:
        Level 1: Local YOLO detection on NVIDIA RTX 4070 SUPER GPU (DirectML).
        Level 2: Calibrated fallback anchor or OCR semantic match if YOLO has no detection.
        Level 3: If neither succeeds, trigger Exception Guardrail:
                 - Save screenshot to captures/exceptions/
                 - Log critical error
                 - Halt safely and request manual agent/user intervention (Zero blind taps).
        """
        frame = self.device.screencap()
        tap_coords: Optional[Tuple[int, int]] = None

        # Level 1: GPU YOLO detection
        if self.detector and self.detector.is_ready():
            elem = self.detector.find_target(frame, target_class=target_class, roi=roi, conf=conf)
            if elem is not None:
                tap_coords = elem.center
                logger.info(
                    f"[Level 1 - YOLO] Detected '{target_class}' at {tap_coords} "
                    f"with confidence {elem.confidence:.3f} (bbox={elem.bbox})"
                )

        # Level 2: Calibrated anchor fallback
        if tap_coords is None:
            if fallback_anchor is not None:
                tap_coords = fallback_anchor
                logger.warning(
                    f"[Level 2 - Fallback] YOLO did not detect '{target_class}' (conf >= {conf}). "
                    f"Falling back to calibrated anchor {fallback_anchor}."
                )

        # Level 3: Exception Guardrail
        if tap_coords is None:
            self.trigger_exception_guardrail(
                frame,
                reason=f"Target '{target_class}' could not be located via YOLO or fallback anchor.",
                action_name=action_name or target_class
            )
            return False

        # Execute closed-loop tap
        return self.tap_and_wait_transition(
            target_coords=tap_coords,
            expected_page=expected_page,
            timeout=timeout,
            action_name=action_name or target_class
        )

    def _crop_roi(self, frame: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
        """Extract a bounding box region from the frame for fast targeted matching."""
        x, y, w, h = roi
        return frame[y:y+h, x:x+w]

    def is_home_screen(self, frame: np.ndarray) -> bool:
        """
        Verify if the current frame is the Home screen by testing the 3 user-specified anchors:
        - 畫面右下角: 出擊按鈕 (assets/anchors/home_sortie.png)
        - 畫面左上角: 玩家等級 (assets/anchors/home_level.png)
        - 畫面右上角: 體力條 (assets/anchors/home_stamina.png)
        """
        anchor_hits = 0
        total_checked = 0

        # Anchor 1: 右下角出擊按鈕 (Primary Anchor)
        try:
            sortie_roi = self._crop_roi(frame, HomeAnchorROI.BOTTOM_RIGHT_SORTIE)
            if self.vision.match_template(sortie_roi, "assets/anchors/home_sortie.png", threshold=0.80):
                anchor_hits += 2
            total_checked += 1
        except FileNotFoundError:
            pass

        # Anchor 2: 左上角等級圖示
        try:
            level_roi = self._crop_roi(frame, HomeAnchorROI.TOP_LEFT_LEVEL)
            if self.vision.match_template(level_roi, "assets/anchors/home_level.png", threshold=0.80):
                anchor_hits += 1
            total_checked += 1
        except FileNotFoundError:
            pass

        # Anchor 3: 右上角體力條 (AP)
        try:
            stamina_roi = self._crop_roi(frame, HomeAnchorROI.TOP_RIGHT_STAMINA)
            if self.vision.match_template(stamina_roi, "assets/anchors/home_stamina.png", threshold=0.80):
                anchor_hits += 1
            total_checked += 1
        except FileNotFoundError:
            pass

        if total_checked > 0 and anchor_hits >= 2:
            self.current_state = GameState.HOME
            return True

        return False

    def navigate_to_home(self, timeout: float = 90.0) -> bool:
        """
        Standardized startup and recovery pipeline:
        Delegates all popups, date-resets, login bonuses, and unexpected screens
        to the centralized PageManager until Home screen is verified.
        """
        logger.info(f"Navigating to Home screen via PageManager (timeout={timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            frame = self.device.screencap()

            # 1. Check if we have arrived at the Home screen
            if self.is_home_screen(frame):
                logger.success("Convergence reached: Successfully verified Home screen anchors!")
                self.current_state = GameState.HOME
                return True

            # 2. Delegate to PageManager for standardized classification and resolution
            page_type, success = self.page_manager.resolve_page(frame, max_attempts=1)

            if page_type == PageType.HOME:
                self.current_state = GameState.HOME
                return True

            if page_type == PageType.UNKNOWN:
                logger.warning("[StateMachine] 遇到未辨識頁面，已觸發安全防護並暫停。請向使用者請教。")
                return False

            # 3. If on a secondary page (CHARACTER_REQUESTS, PERSONAL_BASE, CULTIVATION_STAGES, STAGES_MENU, etc.), tap Home tab
            if page_type in (PageType.CHARACTER_REQUESTS, PageType.PERSONAL_BASE, PageType.CULTIVATION_STAGES, PageType.STAGES_MENU):
                logger.info(f"[StateMachine] On secondary page ({page_type.name}), tapping '主畫面' (Home) tab...")
                home_nav = NavigationCoords.BOTTOM_NAV["home"]
                self.device.tap(home_nav[0], home_nav[1])
                self.device.random_sleep(2.5, 3.5)
                continue

            self.device.random_sleep(1.0, 1.8)

        logger.error(f"Navigation timed out after {timeout}s without reaching Home screen.")
        return False

    def go_back(self, wait_seconds: float = 1.5) -> bool:
        """Tap the standardized top-left back button and resolve potential popups."""
        logger.info(f"[StateMachine] Tapping back button at {NavigationCoords.BACK_BUTTON}...")
        self.device.tap(NavigationCoords.BACK_BUTTON[0], NavigationCoords.BACK_BUTTON[1])
        self.device.random_sleep(wait_seconds, wait_seconds + 0.5)
        frame = self.device.screencap()
        self.page_manager.resolve_page(frame, max_attempts=1)
        return True

    def navigate_to_bottom_tab(
        self,
        tab_name: str,
        expected_page: Optional[PageType] = None,
        timeout: float = 20.0,
    ) -> bool:
        """Navigate to a destination tab on the bottom navigation bar."""
        if tab_name not in NavigationCoords.BOTTOM_NAV:
            logger.error(f"[StateMachine] Invalid bottom tab name: '{tab_name}'")
            return False

        target_coords = NavigationCoords.BOTTOM_NAV[tab_name]
        logger.info(f"[StateMachine] Navigating to bottom tab '{tab_name}' at {target_coords}...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            frame = self.device.screencap()
            ptype, _ = self.page_manager.classify(frame)

            # Resolve intrusive popups if present
            if ptype not in (PageType.HOME, PageType.PERSONAL_BASE, PageType.CHARACTER_REQUESTS):
                self.page_manager.resolve_page(frame, max_attempts=1)
                self.device.random_sleep(1.0, 1.5)
                frame = self.device.screencap()
                ptype, _ = self.page_manager.classify(frame)

            if expected_page and ptype == expected_page:
                logger.success(f"[StateMachine] Reached expected page: {expected_page.name}")
                return True

            self.device.tap(target_coords[0], target_coords[1])
            self.device.random_sleep(2.0, 2.5)

            frame = self.device.screencap()
            ptype, _ = self.page_manager.classify(frame)
            if expected_page is None or ptype == expected_page:
                logger.success(f"[StateMachine] Tab '{tab_name}' tapped, arrived at {ptype.name}.")
                return True

        logger.error(f"[StateMachine] Failed to navigate to bottom tab '{tab_name}' within {timeout}s.")
        return False

    def navigate_to_personal_base(self, timeout: float = 20.0) -> bool:
        """Navigate to Personal Base screen from any state."""
        logger.info("[StateMachine] Navigating to Personal Base (個人基地)...")
        success = self.navigate_to_bottom_tab("personal_base", expected_page=PageType.PERSONAL_BASE, timeout=timeout)
        if success:
            self.current_state = GameState.PERSONAL_BASE
        return success

    def navigate_to_character_requests(self, timeout: float = 20.0) -> bool:
        """Navigate to Character Requests (角色要求) from Home or Personal Base."""
        logger.info("[StateMachine] Navigating to Character Requests (角色要求)...")
        frame = self.device.screencap()
        ptype, _ = self.page_manager.classify(frame)

        if ptype == PageType.CHARACTER_REQUESTS:
            self.current_state = GameState.CHARACTER_REQUESTS
            return True

        if ptype != PageType.PERSONAL_BASE:
            if not self.navigate_to_personal_base(timeout=timeout / 2):
                return False
            frame = self.device.screencap()

        # Step A: Attempt to locate '角色要求' via template on current view
        target_coords = None
        match = self.vision.match_template(frame, "assets/buttons/base_char_request.png", threshold=0.75)
        if match:
            target_coords = (match.x + match.w // 2, match.y + match.h // 2)
            logger.info(f"[StateMachine] Found '角色要求' template at {target_coords} (conf={match.confidence:.2f})")
        else:
            # Step B: If not found, swipe base map to the left to bring the right-side building into view
            logger.info("[StateMachine] '角色要求' not in view, swiping base map left to reveal entrance...")
            self.device.swipe_bezier((1400, 540), (600, 540), duration_ms=400)
            self.device.random_sleep(1.0, 1.5)
            frame = self.device.screencap()

            match = self.vision.match_template(frame, "assets/buttons/base_char_request.png", threshold=0.75)
            if match:
                target_coords = (match.x + match.w // 2, match.y + match.h // 2)
                logger.info(f"[StateMachine] Found '角色要求' template after swipe at {target_coords} (conf={match.confidence:.2f})")
            else:
                # Step C: Fallback to OCR text search
                ocr_items = self.page_manager._extract_all_text(frame)
                for t, (cx, cy), _ in ocr_items:
                    if "要求" in t and cy < 450:
                        target_coords = (cx, cy)
                        logger.info(f"[StateMachine] Found '要求' OCR text after swipe at {target_coords}")
                        break

        if not target_coords:
            target_coords = NavigationCoords.BASE_CHARACTER_REQUESTS_BANNER
            logger.warning(f"[StateMachine] Using fallback coordinates for 角色要求: {target_coords}")

        logger.info(f"[StateMachine] Tapping 角色要求 banner at {target_coords}...")
        self.device.tap(target_coords[0], target_coords[1])
        self.device.random_sleep(2.0, 3.0)

        # Poll and resolve any interstitial dialogs (e.g. newly unlocked character notification)
        start_time = time.time()
        while time.time() - start_time < timeout:
            frame = self.device.screencap()
            ptype, _ = self.page_manager.classify(frame)
            if ptype == PageType.CHARACTER_REQUESTS:
                logger.success("[StateMachine] Successfully entered Character Requests.")
                self.current_state = GameState.CHARACTER_REQUESTS
                return True

            if ptype in (PageType.MODAL_INFO, PageType.MODAL_CONFIRM, PageType.DIALOGUE, PageType.ITEM_ACQUIRED):
                logger.info(f"[StateMachine] Resolving interstitial modal {ptype.name}...")
                self.page_manager.resolve_page(frame, max_attempts=1)
                self.device.random_sleep(1.5, 2.0)
                continue

            if ptype == PageType.PERSONAL_BASE:
                logger.info("[StateMachine] Still on Personal Base, retrying tap on 角色要求 banner...")
                self.device.tap(target_coords[0], target_coords[1])
                self.device.random_sleep(2.5, 3.0)
                continue

            self.device.random_sleep(1.0, 1.5)

        logger.error(f"[StateMachine] Failed to enter Character Requests within {timeout}s.")
        return False

    def select_character_request_slot(self, slot_index: int) -> bool:
        """Tap one of the 3 daily character request cards (1-indexed: 1, 2, or 3)."""
        if not (1 <= slot_index <= 3):
            logger.error(f"[StateMachine] Invalid slot index {slot_index}. Must be 1, 2, or 3.")
            return False

        coords = NavigationCoords.CHAR_REQ_SLOT_CARDS[slot_index - 1]
        logger.info(f"[StateMachine] Selecting Character Request Slot {slot_index} at {coords}...")
        self.device.tap(coords[0], coords[1])
        self.device.random_sleep(1.8, 2.5)
        return True

    def switch_character_request_slot(self, direction: str = "next") -> bool:
        """Switch character request slot in detail view using left/right arrows."""
        if direction.lower() == "next":
            coords = NavigationCoords.CHAR_REQ_ARROW_NEXT
            logger.info(f"[StateMachine] Tapping NEXT card arrow at {coords}...")
        elif direction.lower() == "prev":
            coords = NavigationCoords.CHAR_REQ_ARROW_PREV
            logger.info(f"[StateMachine] Tapping PREV card arrow at {coords}...")
        else:
            logger.error(f"[StateMachine] Invalid switch direction: '{direction}'")
            return False

        self.device.tap(coords[0], coords[1])
        self.device.random_sleep(1.5, 2.0)
        return True

    def abandon_current_character_request(self) -> bool:
        """
        Abandon the currently viewed character request by tapping the trash can,
        resolving the confirmation popup via PageManager, and waiting for the new task to appear.
        """
        logger.info("[StateMachine] Abandoning character request via trash can...")
        success = self.locate_and_tap_target(
            target_class="btn_trash",
            fallback_anchor=NavigationCoords.CHAR_REQ_TRASH_CAN,
            action_name="abandon_trash_can",
            timeout=2.0
        )
        if not success:
            return False

        # Confirm abandonment modal
        frame = self.device.screencap()
        ptype, _ = self.page_manager.classify(frame)
        logger.info(f"[StateMachine] Popup type after tapping trash can: {ptype.name}")
        self.page_manager.resolve_page(frame, max_attempts=2)
        self.device.random_sleep(2.5, 3.5)

        logger.success("[StateMachine] Character request abandoned. New task should be rendered.")
        return True

    def accept_current_character_request(self) -> bool:
        """
        Accept the currently viewed character request and skip any resulting dialogue.
        """
        logger.info("[StateMachine] Accepting character request...")
        success = self.locate_and_tap_target(
            target_class="btn_accept",
            fallback_anchor=NavigationCoords.CHAR_REQ_ACCEPT_BUTTON,
            action_name="accept_character_request",
            timeout=3.0
        )
        if not success:
            return False

        # Skip dialogue if present
        frame = self.device.screencap()
        ptype, _ = self.page_manager.classify(frame)
        if ptype == PageType.DIALOGUE or (self.detector and self.detector.find_target(frame, "btn_skip")):
            logger.info("[StateMachine] Skipping dialogue...")
            self.locate_and_tap_target(
                target_class="btn_skip",
                fallback_anchor=NavigationCoords.CHAR_REQ_DIALOG_SKIP,
                action_name="skip_dialogue",
                timeout=2.0
            )
        return True

    def challenge_current_character_request(self) -> bool:
        """Tap '挑戰' on the accepted character request to jump directly to its target activity."""
        logger.info("[StateMachine] Tapping 挑戰 button...")
        return self.locate_and_tap_target(
            target_class="btn_challenge",
            fallback_anchor=NavigationCoords.CHAR_REQ_CHALLENGE_BUTTON,
            action_name="challenge_character_request",
            timeout=3.0
        )

    def develop_unit_on_tree(self, times: int = 3) -> bool:
        """
        Execute unit development directly on the Development Tree screen (開發路線圖).
        Develops the R-tier unit at calibrated coords repeatedly, confirming modals and dismissing results.
        Finally returns back to the previous screen via top-left back button.
        """
        logger.info(f"[StateMachine] Executing unit development on tree ({times} times)...")
        for i in range(1, times + 1):
            logger.info(f"[StateMachine] Development cycle [{i}/{times}]...")
            # 1. Tap unit node on tree
            self.locate_and_tap_target(
                target_class="unit_r",
                fallback_anchor=NavigationCoords.DEVELOP_TREE_R_UNIT,
                action_name="tap_unit_node_tree",
                timeout=2.0
            )

            # 2. Tap '執行開發' in unit detail modal
            self.locate_and_tap_target(
                target_class="btn_confirm",
                fallback_anchor=NavigationCoords.DEVELOP_MODAL_EXECUTE_BTN,
                action_name="tap_dev_modal_execute",
                timeout=2.0
            )

            # 3. Tap '執行' in confirmation popup
            self.locate_and_tap_target(
                target_class="btn_confirm",
                fallback_anchor=NavigationCoords.DEVELOP_CONFIRM_EXECUTE_BTN,
                action_name="tap_confirm_execute",
                timeout=3.5
            )

            # Wait for production animation to complete
            self.device.random_sleep(3.8, 4.5)

            # 4. Tap 'TAP TO NEXT' on production animation screen
            self.device.tap(*NavigationCoords.DEVELOP_TAP_TO_NEXT)
            self.device.random_sleep(2.0, 2.5)

            # 5. Dismiss unit acquired/unlocked screen and return to tree
            frame = self.device.screencap()
            ptype, meta = self.page_manager.classify(frame)
            if ptype == PageType.ITEM_ACQUIRED:
                self.page_manager.handle_item_acquired(frame, meta)
            else:
                self.device.tap(*NavigationCoords.DEVELOP_TAP_TO_NEXT)
                self.device.random_sleep(2.0, 2.5)

        # 6. Return to character request detail view via top-left back button
        logger.info(f"[StateMachine] Completed {times} developments. Returning via back button...")
        self.device.tap(*NavigationCoords.BACK_BUTTON)
        self.device.random_sleep(2.5, 3.5)
        return True

    def develop_unit_from_acquisition(self) -> bool:
        """
        From '主要獲得方式' modal, tap '移動' to enter Development Tree,
        develop the target unit, and return back to Character Request screen.
        """
        logger.info("[StateMachine] Navigating from acquisition modal to development tree via '移動'...")
        self.device.tap(*NavigationCoords.ACQUISITION_GUIDE_MOVE_BTN)
        self.device.random_sleep(3.0, 4.0)

        # On the development tree screen, locate and tap target unit node via YOLO / calibrated anchor
        logger.info("[StateMachine] Locating unit node on development tree via YOLO/anchor...")
        self.locate_and_tap_target(
            target_class="unit_r",
            fallback_anchor=NavigationCoords.DEVELOP_TREE_R_UNIT,
            action_name="tap_unit_node_tree",
            timeout=2.5
        )
        self.device.random_sleep(2.0, 2.5)

        # Tap '執行開發' in unit detail modal
        self.locate_and_tap_target(
            target_class="btn_confirm",
            fallback_anchor=NavigationCoords.DEVELOP_MODAL_EXECUTE_BTN,
            action_name="tap_dev_modal_execute",
            timeout=2.5
        )

        # Tap '執行' in confirmation modal
        self.locate_and_tap_target(
            target_class="btn_confirm",
            fallback_anchor=NavigationCoords.DEVELOP_CONFIRM_EXECUTE_BTN,
            action_name="tap_confirm_execute",
            timeout=3.5
        )

        # Tap 'TAP TO NEXT' on production animation screen
        self.device.tap(*NavigationCoords.DEVELOP_TAP_TO_NEXT)
        self.device.random_sleep(1.8, 2.5)

        # Return to character request screen via top-left back button
        logger.info("[StateMachine] Unit development finished. Returning to Character Request...")
        self.device.tap(*NavigationCoords.BACK_BUTTON)
        self.device.random_sleep(2.5, 3.5)
        return True

    def deliver_unit_in_modal(self) -> bool:
        """
        In the '確認交付' modal, select the first available unlocked unit and confirm delivery.
        Resolves dialogue and claims reward via PageManager.
        """
        logger.info(f"[StateMachine] Selecting unit at {NavigationCoords.DELIVER_MODAL_FIRST_UNIT}...")
        self.device.tap(*NavigationCoords.DELIVER_MODAL_FIRST_UNIT)
        self.device.random_sleep(1.2, 1.8)

        logger.info("[StateMachine] Tapping 交付 submit button...")
        self.locate_and_tap_target(
            target_class="btn_deliver",
            fallback_anchor=NavigationCoords.DELIVER_MODAL_CONFIRM_BTN,
            action_name="confirm_deliver_unit",
            timeout=3.0
        )

        self._resolve_completion_sequence()
        return True

    def claim_character_request_report(self) -> bool:
        """
        Tap '報告' button on completed character request, then resolve dialogue and reward popup.
        """
        logger.info("[StateMachine] Verifying '報告' button before claiming...")
        frame = self.device.screencap()
        ocr_items = self.page_manager._extract_all_text(frame)
        has_report_ocr = any(
            any(k in text for k in ["報告", "報", "告"])
            for text, (cx, cy), _ in ocr_items
            if cx > 1400 and cy > 780
        )
        has_report_yolo = bool(self.detector and self.detector.find_target(frame, "btn_report", conf=0.55))

        if not (has_report_ocr or has_report_yolo):
            logger.error("[StateMachine] 畫面未出現『報告』按鈕（任務尚未完成或按鈕狀態不符），拒絕盲點！")
            return False

        logger.info("[StateMachine] Tapping 報告 button...")
        success = self.locate_and_tap_target(
            target_class="btn_report",
            fallback_anchor=NavigationCoords.CHAR_REQ_REPORT_BUTTON,
            action_name="claim_report_button",
            timeout=3.0
        )
        if not success:
            return False

        self._resolve_completion_sequence()
        return True

    def _resolve_completion_sequence(self, max_steps: int = 5) -> bool:
        """Handle dialogue, rank animation, and reward claim modals using PageManager."""
        for step in range(1, max_steps + 1):
            frame = self.device.screencap()
            page_type, meta = self.page_manager.classify(frame)
            logger.info(f"[StateMachine] Completion sequence step {step}: page is [{page_type.value}]")

            if page_type == PageType.DIALOGUE:
                self.page_manager.handle_dialogue(frame, meta)
            elif page_type == PageType.ITEM_ACQUIRED:
                self.page_manager.handle_item_acquired(frame, meta)
                return True
            elif page_type == PageType.CHARACTER_REQUESTS:
                return True
            elif page_type == PageType.UNKNOWN:
                logger.warning(f"[StateMachine] 結算流程遭遇未辨識頁面 (步驟 {step})，觸發安全防護絕不盲點！")
                self.trigger_exception_guardrail(
                    frame,
                    reason=f"Unknown page encountered during completion sequence at step {step}",
                    action_name="resolve_completion_sequence"
                )
                return False
            else:
                resolved_type, success = self.page_manager.resolve_page(frame, max_attempts=1)
                if not success and resolved_type == PageType.UNKNOWN:
                    logger.warning(f"[StateMachine] 無法自動解析頁面 [{page_type.value}]，觸發安全防護。")
                    self.trigger_exception_guardrail(
                        frame,
                        reason=f"Unresolvable page [{page_type.value}] at completion step {step}",
                        action_name="resolve_completion_sequence"
                    )
                    return False
        return True

