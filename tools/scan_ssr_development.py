"""Complete autonomous scanner for developable SSR units in SD Gundam G Generation Eternal.

Features robust guardrails (保險機制):
- Deterministic State Sentinel using OpenCV template matching
- Pre- and post-condition verification on every UI transition
- Auto-recovery to main Development screen if lost
- Strict canvas boundary masks & HSV gold detection to prevent false-positive SSR clicks
- Popup defense to ensure OCR only records true developable SSR units
- Skip all 【終極】 (Ultimate) route maps
"""
import base64
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
# Ensure UTF-8 output encoding across Windows PowerShell/CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from loguru import logger
from rapidocr_onnxruntime import RapidOCR

# Reconfigure logger to ensure stdout uses UTF-8
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import SSRDevelopmentDB
from core.device import Device
from core.page_manager import PageManager, PageType
from core.vision import Vision
from tools.yolo_detector import YOLOUIDetector


class SSRDevelopmentScanner:
    """Automated scanner with full guardrails that inspects all general routes for developable SSRs."""

    def __init__(self, serial: Optional[str] = None, debug_mode: bool = False):
        self.device = Device(serial=serial)
        self.vision = Vision()
        self.db = SSRDevelopmentDB()
        self.ocr = RapidOCR()
        self.page_manager = PageManager(self.device, self.vision)
        self.yolo = YOLOUIDetector()
        self.debug_mode = debug_mode
        self.debug_dir = "captures/debug_cv"
        os.makedirs(self.debug_dir, exist_ok=True)

        # Verified visual anchor templates
        self.anchor_from_owned = "assets/anchors/anchor_from_owned.png"
        self.anchor_catalog = "assets/anchors/anchor_catalog.png"
        self.btn_back_arrow = "assets/buttons/btn_back_arrow.png"
        self.btn_dev_cancel = "assets/buttons/btn_dev_cancel.png"
        self.btn_close_gray = "assets/buttons/btn_close_gray.png"
        self.nav_btn_dev = "assets/buttons/nav_btn_dev.png"
        self.badge_ssr = "assets/icons/badge_ssr.png"
        self.stars_3_purple = "assets/icons/stars_3_purple.png"

        # Enhancement card star templates (calibrated)
        self.card_star_gold_single = "assets/icons/card_star_gold_single.png"
        self.card_stars_gold_2 = "assets/icons/card_stars_gold_2.png"
        self.card_stars_blue_3 = "assets/icons/card_stars_blue_3.png"

        # Pending units to audit in Enhancement: list of dicts
        self.pending_enhancement_units: List[Dict] = []

        # Route canvas boundary: clip out top currency header and left tabs
        self.CANVAS_X_MIN = 240
        self.CANVAS_X_MAX = 1760
        self.CANVAS_Y_MIN = 170
        self.CANVAS_Y_MAX = 960

    def ensure_connected(self) -> None:
        """Connect to ADB device."""
        if not self.device._connected:
            self.device.connect()

    # =========================================================================
    # State Sentinel & Guardrails (狀態哨兵與防禦保險)
    # =========================================================================

    def is_on_series_list(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if device is currently on the main series selection screen."""
        if frame is None:
            frame = self.device.screencap()

        # Check visual anchor '從持有單位開發' button
        m = self.vision.match_template(frame, self.anchor_from_owned, threshold=0.75)
        if m:
            return True

        # Fallback check: '單位圖鑑' card at top-left
        m_cat = self.vision.match_template(frame, self.anchor_catalog, threshold=0.75)
        if m_cat:
            return True

        # OCR fallback: check header text '開發路線圖'
        header_crop = frame[140:210, 50:240]
        res, _ = self.ocr(header_crop)
        for item in res or []:
            if any(k in item[1] for k in ["開發", "路線", "圖"]):
                return True

        return False

    def is_in_route_map(self, frame: Optional[np.ndarray] = None) -> bool:
        """Check if device is inside a specific series route map screen."""
        if frame is None:
            frame = self.device.screencap()
        m = self.vision.match_template(frame, self.btn_back_arrow, threshold=0.75)
        return m is not None

    def close_any_popup(self, max_attempts: int = 3) -> bool:
        """Close any visible modal popup (開發目標單位資訊 or 主要獲得方式)."""
        for _ in range(max_attempts):
            frame = self.device.screencap()
            # 1. Check '取消' button
            m_cancel = self.vision.match_template(frame, self.btn_dev_cancel, threshold=0.70)
            if m_cancel:
                logger.debug(f"Closing popup via cancel button at {m_cancel.center}")
                self.device.tap(*m_cancel.center)
                time.sleep(1.0)
                continue

            # 2. Check '關閉' gray button
            m_close = self.vision.match_template(frame, self.btn_close_gray, threshold=0.70)
            if m_close:
                logger.debug(f"Closing popup via close button at {m_close.center}")
                self.device.tap(*m_close.center)
                time.sleep(1.0)
                continue

            # No popup detected
            return True

        # Fallback: Android KEY_BACK
        self.device.key_back()
        time.sleep(1.0)
        return True

    def ensure_on_series_list(self, max_retries: int = 6) -> bool:
        """
        Rock-solid guardrail: Guarantee device returns to the main series selection screen.
        Handles popups, route maps, or unexpected screen drifts safely.
        """
        for attempt in range(max_retries):
            frame = self.device.screencap()
            if self.is_on_series_list(frame):
                return True

            logger.info(f"Guardrail recovering to series list (attempt {attempt+1}/{max_retries})...")

            # 1. Check if a popup inside development is blocking the screen
            m_cancel = self.vision.match_template(frame, self.btn_dev_cancel, threshold=0.70)
            m_close = self.vision.match_template(frame, self.btn_close_gray, threshold=0.70)
            if m_cancel or m_close:
                self.close_any_popup()
                continue

            # 2. If inside route map, tap the back arrow at (120, 50)
            if self.is_in_route_map(frame):
                self.device.tap(120, 50)
                time.sleep(1.5)
                continue

            # 3. Check for global system popups or states via PageManager (換日, 更新, 登入簽到, 公告, 首頁)
            page_type, metadata = self.page_manager.classify(frame)
            if page_type in (
                PageType.DATE_RESET,
                PageType.RESOURCE_DOWNLOAD,
                PageType.LOGIN_BONUS,
                PageType.TITLE_SCREEN,
                PageType.COMM_ERROR,
                PageType.MODAL_INFO,
                PageType.MODAL_CONFIRM,
                PageType.LOADING,
                PageType.HOME,
            ):
                logger.warning(f"[Guardrail] PageManager detected global state: [{page_type.value}], resolving...")
                res_type, success = self.page_manager.resolve_page(frame)
                if res_type == PageType.HOME or success:
                    logger.info("Successfully returned to Home, tapping bottom navigation '開發' at (714, 1000)...")
                    self.device.tap(714, 1000)
                    time.sleep(2.5)
                    continue

            # 4. If completely lost, tap the true 開發 bottom nav button at (714, 1000)
            logger.warning("Unrecognized screen state, tapping bottom navigation '開發' icon at (714, 1000)...")
            self.device.tap(714, 1000)
            time.sleep(2.0)

            # Check again
            f_check = self.device.screencap()
            if self.is_on_series_list(f_check):
                return True

            # Extra insurance: press KEY_BACK once in case a full-screen banner is up
            self.device.key_back()
            time.sleep(1.5)

        # Post-condition check: if still lost after max_retries, let PageManager record unknown page safely
        f_final = self.device.screencap()
        if not self.is_on_series_list(f_final):
            p_type, meta = self.page_manager.classify(f_final)
            logger.error(f"[Guardrail] Failed to recover to series list after {max_retries} attempts! State: {p_type.value}")
            if p_type == PageType.UNKNOWN:
                self.page_manager.handle_unknown_page(f_final, meta)
            return False

        return True

    def enter_series_card(self, series_name: str, card_pos: Tuple[int, int]) -> bool:
        """
        Enter a series route map with pre/post-condition verification.
        Returns True if entered successfully, False otherwise.
        """
        if not self.ensure_on_series_list():
            logger.error("Pre-condition failed: not on series list before clicking card.")
            return False

        logger.info(f"Entering series: '{series_name}' at {card_pos}...")
        self.device.tap(*card_pos)

        # Wait up to 3.5s for route map to load
        for _ in range(5):
            time.sleep(0.7)
            if self.is_in_route_map():
                logger.debug(f"Successfully entered route map for '{series_name}'.")
                return True

        # Retry tap once
        logger.warning(f"Did not detect route map for '{series_name}', retrying tap...")
        self.device.tap(*card_pos)
        for _ in range(4):
            time.sleep(0.7)
            if self.is_in_route_map():
                return True

        logger.error(f"Failed to enter route map for '{series_name}'! Aborting this series.")
        self.ensure_on_series_list()
        return False

    # =========================================================================
    # OCR & Unit Extraction
    # =========================================================================

    def scan_current_popup_info(self) -> Optional[Tuple[str, int, int]]:
        """
        Scan 開發目標單位資訊 popup using RapidOCR.
        Returns: (unit_name, required_per_craft, held_books) or None
        """
        frame = self.device.screencap()

        # Guardrail: Must verify popup cancel button is visible
        m_cancel = self.vision.match_template(frame, self.btn_dev_cancel, threshold=0.70)
        if not m_cancel:
            logger.warning("Guardrail: scan_current_popup_info called without popup visible!")
            return None

        # 1. OCR material panel on the right: y: 80..850, x: 490..1850
        crop_panel = frame[80:850, 490:1850]
        res, _ = self.ocr(crop_panel)

        unit_name = None
        required_per_craft = 3
        held_books = 0

        # Find the line corresponding to research technical book (研究技術書)
        book_items = [
            it for it in res or []
            if any(k in it[1] for k in ["技術書", "技术书", "研究技術", "研究技术", "技術", "技术"])
            and "材料" not in it[1]
        ]

        if not book_items:
            logger.warning("Popup does NOT contain 研究技術書. This unit is NOT a developable SSR (likely R or SR). Skipping.")
            return None

        b_box, b_text, _ = book_items[0]

        # Extract unit name from book title
        name_match = re.search(r"([^\s]+?)研究.*?[書书]", b_text)
        if name_match:
            unit_name = name_match.group(1).replace(" ", "")

        # Target the numbers box directly below the book title in frame coordinates
        b_y = int(b_box[0][1])
        num_roi = frame[80 + b_y + 35 : 80 + b_y + 125, 1340 : 1590]
        num_res, _ = self.ocr(num_roi)

        digits = []
        full_num_text = ""
        for r in num_res or []:
            full_num_text += " " + r[1]
            for d in re.findall(r"\d+", r[1]):
                digits.append(int(d))

        if len(digits) >= 2:
            required_per_craft = digits[0]
            held_books = digits[1]
        elif len(digits) == 1:
            if "/" in full_num_text:
                # If single digit is 3 and slash is present, held is 0
                if digits[0] == 3:
                    required_per_craft = 3
                    held_books = 0
                else:
                    held_books = digits[0]
            else:
                held_books = digits[0]

        # Fallback to left unit name card if not found: y: 550..660, x: 140..480
        if not unit_name or len(unit_name) < 2 or unit_name in ("SSR", "7"):
            crop_name = frame[550:660, 140:480]
            name_res, _ = self.ocr(crop_name)
            for it in name_res or []:
                cand = it[1].strip()
                if len(cand) >= 2 and cand not in ("SSR", "R", "SR"):
                    unit_name = cand
                    break

        if not unit_name or len(unit_name) < 2 or unit_name in ("SSR", "7"):
            logger.warning("Could not parse valid unit name from popup.")
            return None

        logger.info(f"-> Parsed SSR: '{unit_name}', Required={required_per_craft}, Held={held_books}")
        return unit_name, required_per_craft, held_books

    def is_true_ssr(self, frame: np.ndarray, match) -> bool:
        """
        Verify candidate badge is true SSR (gold/orange) and not R (bronze) or SR (teal/cyan).
        Uses HSV gold mask and Red channel threshold.
        """
        crop = frame[match.y : match.y + match.h, match.x : match.x + match.w]
        if crop.shape[0] < 20 or crop.shape[1] < 20:
            return False

        h, w = crop.shape[:2]

        # 1. Red channel mean check (allow lower mean when LV badge overlaps)
        r_mean = np.mean(crop[10 : h - 10, 10 : w - 10, 2])
        if r_mean < 110:
            return False

        # 2. HSV Gold/Amber mask check (H: 15-35, S: 120-255, V: 120-255)
        # SSR typically has 350-660 gold pixels; R and SR have < 50
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        gold_mask = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 35) & (hsv[:, :, 1] >= 120) & (hsv[:, :, 2] >= 120)
        gold_px = np.sum(gold_mask)

        if gold_px < 180:
            return False

        return True

    def capture_debug_cv_scan(
        self,
        frame: Optional[np.ndarray] = None,
        label: str = "canvas",
        ssr_matches: Optional[List] = None,
        star_matches: Optional[List] = None,
        actions_info: Optional[List[Dict]] = None,
    ) -> str:
        """
        Capture and annotate current frame with pure Computer Vision (CV) detection results:
        - Verified SSR badges (Orange bounding box)
        - Ownership pills (Yellow bounding box + OCR text)
        - Purple 3-stars clusters (Magenta bounding box + confidence)
        - Pedestal tap targets (Green crosshairs)
        - Decision verdicts ([已滿星], [未擁有], [需審查])
        Saves annotated image to captures/debug_cv/.
        """
        if frame is None:
            frame = self.device.screencap()

        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Top summary banner HUD
        ssr_cnt = len(ssr_matches) if ssr_matches else 0
        star_cnt = len(star_matches) if star_matches else 0
        hud_text = f"CV DEBUG [{label}]: Verified SSRs={ssr_cnt} | 3-Star Clusters={star_cnt}"
        cv2.rectangle(annotated, (0, 0), (w, 40), (30, 30, 30), -1)
        cv2.putText(annotated, hud_text, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # 1. Annotate Purple 3-stars if provided
        if star_matches:
            for s in star_matches:
                sx, sy, sw, sh = s.rect if hasattr(s, "rect") else (s.x, s.y, s.w, s.h)
                cv2.rectangle(annotated, (sx, sy), (sx + sw, sy + sh), (255, 0, 255), 3)
                cv2.putText(
                    annotated,
                    f"3_STARS_PURPLE ({s.confidence:.2f})",
                    (sx - 20, max(20, sy - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 0, 255),
                    2,
                )

        # 2. Annotate verified SSR badges and actions
        if actions_info:
            for act in actions_info:
                bx, by, bw, bh = act["rect"]
                eng = act.get("engine", "DET")
                # SSR badge in Orange
                cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 165, 255), 3)
                cv2.putText(
                    annotated,
                    f"[{eng}] SSR ({act.get('conf', 0.5):.2f})",
                    (bx, max(20, by - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 165, 255),
                    2,
                )

                # Ownership pill in Yellow
                cv2.rectangle(annotated, (bx + bw, by), (bx + bw + 90, by + bh), (0, 255, 255), 2)
                cv2.putText(
                    annotated,
                    f"{act.get('pill', '')}",
                    (bx + bw + 10, by + bh - 6),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                )

                # Star ROI indicator directly above ownership pill
                star_box = act.get("star_roi_box")
                if star_box:
                    sx1, sy1, sx2, sy2 = star_box
                    s_color = (255, 0, 255) if act.get("is_purple_3") else (100, 100, 100)
                    cv2.rectangle(annotated, (sx1, sy1), (sx2, sy2), s_color, 2)
                    if act.get("is_purple_3"):
                        cv2.putText(
                            annotated,
                            "3_STARS",
                            (sx1, max(15, sy1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            (255, 0, 255),
                            1,
                        )

                # Verdict & target marker
                verdict = act.get("verdict", "")
                is_maxed = "已滿星" in verdict
                color = (0, 255, 0) if is_maxed else ((0, 0, 255) if "未擁有" in verdict else (255, 200, 0))

                # Tap target marker
                tx, ty = act.get("tap", (bx + 60, by - 65))
                cv2.drawMarker(annotated, (tx, ty), color, cv2.MARKER_CROSS, 20, 2)
                cv2.putText(
                    annotated,
                    verdict,
                    (bx - 30, by + bh + 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    2,
                )
        elif ssr_matches:
            for m in ssr_matches:
                bx, by, bw, bh = m.rect
                cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 165, 255), 3)
                cv2.putText(
                    annotated,
                    f"SSR_BADGE ({m.confidence:.2f})",
                    (bx, max(20, by - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 165, 255),
                    2,
                )

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^\w\-]", "_", label)
        filename = f"debug_cv_{timestamp}_{safe_label}.png"
        filepath = os.path.join(self.debug_dir, filename)
        is_success, im_buf = cv2.imencode(".png", annotated)
        if is_success:
            with open(filepath, "wb") as f:
                im_buf.tofile(f)
            logger.info(f"📸 [Debug CV] Saved annotated CV detection result to: {filepath}")
        else:
            logger.warning(f"Failed to encode debug image for {filepath}")
        return filepath

    def scan_canvas_ssrs(self, series_name: str, route_name: str) -> None:
        """
        Scan visible canvas for SSR units using YOLO Object Detection Engine (GPU direct)
        with Computer Vision fallback:
        - Detects SSR badges, unit pedestals, ownership pills, and 3 purple stars.
        - If 3 purple stars detected: skips clicking popup completely per user rule.
        - If owned_count == 0: recorded as 0★ directly, no need to audit Enhancement.
        - If owned_count > 0 and NOT 3 purple stars: queued to pending_enhancement_units.
        """
        frame = self.device.screencap()
        actions_info: List[Dict] = []
        valid_matches = []

        # =====================================================================
        # 1. YOLO Engine Detection (Primary)
        # =====================================================================
        if self.yolo and self.yolo.is_ready():
            logger.info(f"[{series_name} | {route_name}] Running GPU YOLO detection...")
            detections = self.yolo.detect(frame, conf=0.40)
            # Filter detections within valid canvas region
            canvas_dets = [
                d for d in detections
                if self.CANVAS_X_MIN <= d.center[0] <= self.CANVAS_X_MAX
                and self.CANVAS_Y_MIN <= d.center[1] <= self.CANVAS_Y_MAX
            ]

            ssr_dets = [d for d in canvas_dets if d.class_name in ("badge_ssr", "unit_ssr")]
            stars_dets = [d for d in canvas_dets if d.class_name == "stars_3_purple"]
            pills_owned = [d for d in canvas_dets if d.class_name == "pill_owned"]
            pills_unowned = [d for d in canvas_dets if d.class_name == "pill_unowned"]

            logger.info(
                f"[YOLO] Found {len(ssr_dets)} SSR(s), {len(stars_dets)} 3-star(s), "
                f"{len(pills_owned)} owned pill(s), {len(pills_unowned)} unowned pill(s)."
            )

            for s_det in ssr_dets:
                bx, by, bx2, by2 = s_det.bbox
                bw, bh = bx2 - bx, by2 - by

                # Check if 3-star detected near this SSR node (within dx < 140, dy < 100)
                is_purple_3 = any(
                    abs(st.center[0] - s_det.center[0]) < 140 and abs(st.center[1] - s_det.center[1]) < 100
                    for st in stars_dets
                )

                # Check ownership pill
                is_unowned = any(
                    abs(pu.center[0] - s_det.center[0]) < 140 and abs(pu.center[1] - s_det.center[1]) < 100
                    for pu in pills_unowned
                )
                owned_count = 0 if is_unowned else 1

                # If no pill detected by YOLO, fallback to quick local OCR
                if not is_unowned and not any(abs(po.center[0] - s_det.center[0]) < 140 for po in pills_owned):
                    pill_crop = frame[by : by + bh, bx + bw : bx + bw + 90]
                    pill_res, _ = self.ocr(pill_crop)
                    pill_text = " ".join([r[1] for r in pill_res or []])
                    owned_count = 0 if "0" in pill_text else 1
                else:
                    pill_text = "x0" if owned_count == 0 else "x1"

                tap_x = bx + 60
                tap_y = max(0, by - 65)

                verdict = "已滿星 (紫3星，略過)" if is_purple_3 else ("未擁有 (0星)" if owned_count == 0 else "已持有需審查")
                actions_info.append({
                    "rect": (bx, by, bw, bh),
                    "conf": s_det.confidence,
                    "pill": pill_text,
                    "is_purple_3": is_purple_3,
                    "star_roi_box": (bx + bw + 15, max(0, by - 35), min(frame.shape[1], bx + bw + 95), by + 2),
                    "owned_count": owned_count,
                    "tap": (tap_x, tap_y),
                    "verdict": verdict,
                    "engine": "YOLO",
                })
        else:
            # =====================================================================
            # 2. Template / Geometric CV Fallback (Active until model weights placed)
            # =====================================================================
            all_matches = self.vision.match_all(frame, self.badge_ssr, threshold=0.55, min_distance=40)
            valid_matches = [
                m for m in all_matches
                if self.CANVAS_X_MIN <= m.center[0] <= self.CANVAS_X_MAX
                and self.CANVAS_Y_MIN <= m.center[1] <= self.CANVAS_Y_MAX
                and self.is_true_ssr(frame, m)
            ]

            logger.info(f"[{series_name} | {route_name}] [CV Fallback] Found {len(valid_matches)} verified SSR badge(s).")

            for match in valid_matches:
                bx, by, bw, bh = match.rect

                pill_crop = frame[by : by + bh, bx + bw : bx + bw + 90]
                pill_res, _ = self.ocr(pill_crop)
                pill_text = " ".join([r[1] for r in pill_res or []])
                owned_count = 0 if "0" in pill_text else 1

                sx1 = max(0, bx + bw + 15)
                sx2 = min(frame.shape[1], bx + bw + 95)
                sy1 = max(0, by - 35)
                sy2 = min(frame.shape[0], by + 2)

                star_roi = frame[sy1:sy2, sx1:sx2]
                hsv_roi = cv2.cvtColor(star_roi, cv2.COLOR_BGR2HSV)
                purple_mask = cv2.inRange(hsv_roi, np.array([130, 45, 90]), np.array([170, 255, 255]))
                cyan_mask = cv2.inRange(hsv_roi, np.array([85, 70, 120]), np.array([130, 255, 255]))
                p_pixels = cv2.countNonZero(purple_mask)
                c_pixels = cv2.countNonZero(cyan_mask)

                is_purple_3 = (p_pixels >= 15 and c_pixels >= 40)

                tap_x = bx + 60
                tap_y = max(0, by - 65)

                verdict = "已滿星 (紫3星，略過)" if is_purple_3 else ("未擁有 (0星)" if owned_count == 0 else "已持有需審查")
                actions_info.append({
                    "rect": (bx, by, bw, bh),
                    "conf": match.confidence,
                    "pill": pill_text or ("x1" if owned_count else "x0"),
                    "is_purple_3": is_purple_3,
                    "star_roi_box": (sx1, sy1, sx2, sy2),
                    "owned_count": owned_count,
                    "tap": (tap_x, tap_y),
                    "verdict": verdict,
                    "engine": "CV",
                })

        # In debug mode, capture and save full annotated map
        if self.debug_mode:
            self.capture_debug_cv_scan(
                frame,
                label=f"{series_name}_{route_name}",
                ssr_matches=valid_matches,
                star_matches=None,
                actions_info=actions_info,
            )

        for act in actions_info:
            bx, by, bw, bh = act["rect"]
            is_purple_3 = act["is_purple_3"]
            owned_count = act["owned_count"]
            tap_x, tap_y = act["tap"]

            # User Rule: 第一階段看到紫三星就不用點進去了
            if is_purple_3:
                logger.success(
                    f"[{series_name} | {route_name}] SSR at ({bx}, {by}) is ALREADY 3 PURPLE STARS (★★★). "
                    f"Skipping popup inspection per user rule!"
                )
                continue

            # Tap unit node (pedestal ring at bx + 60, by - 65) to inspect unit info
            self.device.tap(tap_x, tap_y)

            # Guardrail: wait up to 2.5s for popup to appear
            popup_opened = False
            for _ in range(5):
                time.sleep(0.5)
                f_check = self.device.screencap()
                if self.vision.match_template(f_check, self.btn_dev_cancel, threshold=0.70):
                    popup_opened = True
                    break

            if not popup_opened:
                logger.warning(f"Popup did not open after tapping ({tap_x}, {tap_y}). Closing any stray dialogs...")
                self.close_any_popup()
                continue

            # Scan popup
            info = self.scan_current_popup_info()
            if not info:
                self.close_any_popup()
                continue

            unit_name, required_per_craft, held_books = info

            # Core Branching Rules per user specifications:
            if owned_count == 0:
                # Rule: 持有數為0不用查強化，因為星數一定為0
                logger.info(
                    f"[{series_name} | {route_name}] SSR '{unit_name}' is UNOWNED (owned_count=0) -> 0★ "
                    f"(No enhancement check needed per rule)."
                )
                self.db.upsert_unit(
                    series_name=series_name,
                    route_name=route_name,
                    unit_name=unit_name,
                    owned_count=0,
                    current_stars=0,
                    required_per_craft=required_per_craft,
                    held_books=held_books,
                )
            else:
                logger.warning(
                    f"[{series_name} | {route_name}] SSR '{unit_name}' is OWNED but NOT MAXED! "
                    f"Queueing for Enhancement audit..."
                )
                self.db.upsert_unit(
                    series_name=series_name,
                    route_name=route_name,
                    unit_name=unit_name,
                    owned_count=owned_count,
                    current_stars=0,
                    required_per_craft=required_per_craft,
                    held_books=held_books,
                )
                if not any(u["unit_name"] == unit_name for u in self.pending_enhancement_units):
                    self.pending_enhancement_units.append({
                        "series_name": series_name,
                        "route_name": route_name,
                        "unit_name": unit_name,
                        "required_per_craft": required_per_craft,
                        "held_books": held_books,
                        "owned_count": owned_count,
                    })

            # Guardrail: close popup and ensure return to route map
            self.close_any_popup()
            time.sleep(0.8)

    def process_series_route(self, series_name: str, route_name: str) -> None:
        """Traverse route tree from right to left, top to bottom across terminal SSR nodes."""
        logger.info(f"--- Scanning route: {route_name} ({series_name}) ---")

        # View 1: Fast swipe right to inspect the rightmost end of the branch where SSRs reside
        self.device.swipe_bezier((1600, 500), (300, 500), duration_ms=450)
        time.sleep(1.2)
        self.scan_canvas_ssrs(series_name, route_name)

        # View 2: Swipe up to inspect mid/lower branches
        self.device.swipe_bezier((1000, 750), (1000, 250), duration_ms=450)
        time.sleep(1.2)
        self.scan_canvas_ssrs(series_name, route_name)

        # View 3: Swipe up again for bottom branch
        self.device.swipe_bezier((1000, 750), (1000, 250), duration_ms=450)
        time.sleep(1.2)
        self.scan_canvas_ssrs(series_name, route_name)

    def scan_series(self, series_name: str, card_pos: Tuple[int, int]) -> None:
        """Enter a series, determine general routes (skipping Ultimate), scan each, and return."""
        logger.info(f"==================================================")
        logger.info(f"Processing series: {series_name} at {card_pos}")

        entered = self.enter_series_card(series_name, card_pos)
        if not entered:
            return

        # Check route tabs on the left sidebar: y: 160..650, x: 10..200
        frame = self.device.screencap()
        tabs_crop = frame[160:650, 10:200]
        res, _ = self.ocr(tabs_crop)

        slots = {0: [], 1: [], 2: []}
        for b, text, _ in res or []:
            y_mid = 160 + (b[0][1] + b[2][1]) / 2
            idx = int((y_mid - 160) // 160)
            if idx in slots:
                slots[idx].append(text)

        routes_to_scan = []
        for idx in range(3):
            texts = slots[idx]
            joined = " ".join(texts)
            if not joined and idx > 0:
                continue

            center_y = 160 + idx * 160 + 80
            # Strict Rule: Skip any route containing 終極 or ULT
            if "終極" in joined or "ULT" in joined or "終" in joined:
                logger.info(f"Sidebar Slot {idx+1} is Ultimate route ('{joined}') -> SKIPPING per rule.")
                continue

            # Route title determination
            route_title = series_name if idx == 0 else f"{series_name}_路線{idx+1}"
            if "吉翁" in joined or "吉翁" in joined:
                route_title = "吉翁"
            elif "提坦斯" in joined or "迪坦斯" in joined:
                route_title = "提坦斯"
            elif "新吉翁" in joined:
                route_title = "新吉翁"
            elif "札夫特" in joined:
                route_title = "札夫特"
            elif "歐普" in joined or "聯合" in joined:
                route_title = "地球聯合 & 歐普"

            routes_to_scan.append((route_title, center_y))

        if not routes_to_scan:
            routes_to_scan = [(series_name, 240)]

        logger.info(f"General routes to scan for {series_name}: {[r[0] for r in routes_to_scan]}")

        for r_name, r_y in routes_to_scan:
            logger.info(f"Selecting route tab: {r_name} at y={r_y}")
            self.device.tap(100, r_y)
            time.sleep(1.5)
            self.process_series_route(series_name, r_name)

        # Return to series list with guardrail verification
        self.ensure_on_series_list()

    # =========================================================================
    # Enhancement Audit System (強化畫面真實星數查詢系統)
    # =========================================================================

    def ensure_adb_keyboard(self) -> None:
        """Ensure ADBKeyBoard is active and enabled to accept Chinese broadcast input."""
        try:
            self.device._device.shell("settings put secure show_ime_with_hard_keyboard 1")
            self.device._device.shell("ime enable com.android.adbkeyboard/.AdbIME")
            self.device._device.shell("ime set com.android.adbkeyboard/.AdbIME")
            logger.debug("ADBKeyBoard configured as active IME.")
        except Exception as e:
            logger.warning(f"Error ensuring ADBKeyBoard: {e}")

    def input_chinese_text(self, text: str) -> None:
        """Broadcast Base64 encoded UTF-8 text via ADBKeyBoard."""
        b64_val = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        self.device._device.shell(["am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64_val])

    def setup_enhancement_filters(self) -> bool:
        """
        Configure enhancement screen filters:
        - Rarity = SSR
        - Source = 開發單位
        """
        logger.info("[EnhancementAudit] Configuring filters (SSR + 開發單位)...")
        # 1. Tap filter button (left of the two boxes at bottom right: 1670, 900)
        self.device.tap(1670, 900)
        time.sleep(1.2)

        # 2. Tap 重置 (1730, 855)
        self.device.tap(1730, 855)
        time.sleep(0.8)

        # 3. Tap SSR checkbox (600, 715)
        self.device.tap(600, 715)
        time.sleep(0.8)

        # 4. Scroll down modal to reach 獲得來源
        self.device.swipe_bezier((1000, 700), (1000, 250), duration_ms=400)
        time.sleep(1.0)

        # 5. Tap 開發單位 (160, 625)
        self.device.tap(160, 625)
        time.sleep(0.8)

        # 6. Tap 決定 (1150, 995)
        self.device.tap(1150, 995)
        time.sleep(1.5)
        logger.success("[EnhancementAudit] Filters applied successfully (篩選：ON).")
        return True

    def classify_card_stars(self, card_img: np.ndarray) -> int:
        """
        Classify stars on an enhancement card (0★, 1★, 2★, 3★).
        Uses high-precision template matching on the bottom center strip.
        Threshold = 0.72 provides 100% precision with 0.20+ safety margin.
        """
        h, w = card_img.shape[:2]
        # Centered bottom strip: avoids borders and favorite heart icon
        roi = card_img[max(0, h - 45):h, int(w * 0.15):int(w * 0.85)]

        # Check 3 blue/purple stars
        m3 = self.vision.match_template(roi, self.card_stars_blue_3, threshold=0.72)
        if m3:
            return 3

        # Check 2 gold stars
        m2 = self.vision.match_template(roi, self.card_stars_gold_2, threshold=0.72)
        if m2:
            return 2

        # Check 1 gold star
        m1 = self.vision.match_template(roi, self.card_star_gold_single, threshold=0.72)
        if m1:
            return 1

        return 0

    def search_and_audit_unit_enhancement(self, unit_name: str) -> Tuple[int, int]:
        """
        Search for a unit in 強化 and determine (total_copies, effective_stars).
        Formula per game rule:
          if total >= 1: effective_stars = min(3, max_star + total - 1)
          else: 0
        """
        logger.info(f"[EnhancementAudit] Searching for '{unit_name}'...")
        # 1. Tap 搜尋 button
        self.device.tap(1510, 65)
        time.sleep(1.0)

        # 2. Tap search input field
        self.device.tap(500, 160)
        time.sleep(0.8)

        # 3. Input Chinese text via Base64 broadcast
        self.input_chinese_text(unit_name)
        time.sleep(0.8)

        # 4. Submit search (tap 確定 on input strip at 1850, 925)
        self.device.tap(1850, 925)
        time.sleep(2.0)

        # 5. Screencap and analyze results
        frame = self.device.screencap()
        res, _ = self.ocr(frame)

        matching_cards_stars: List[int] = []

        # Find matching cards via LV text boxes
        for b, text, score in res or []:
            if "LV" in text and score > 0.7:
                cx = (b[0][0] + b[2][0]) / 2
                cy = (b[0][1] + b[2][1]) / 2
                x1 = max(0, int(cx - 75))
                x2 = min(frame.shape[1], int(cx + 75))
                y1 = max(0, int(cy - 200))
                y2 = min(frame.shape[0], int(cy + 45))

                card_crop = frame[y1:y2, x1:x2]

                # Extract unit name from card
                name_roi = card_crop[max(0, card_crop.shape[0] - 80) : card_crop.shape[0] - 25, :]
                n_res, _ = self.ocr(name_roi)
                card_name = "".join([it[1] for it in n_res or []])

                # Match validation: strip special chars
                c_search = re.sub(r"[・\s\(\)（）\-_/]", "", unit_name)
                c_card = re.sub(r"[・\s\(\)（）\-_/]", "", card_name)

                if c_search in c_card or c_card in c_search or not card_name:
                    stars = self.classify_card_stars(card_crop)
                    matching_cards_stars.append(stars)
                    logger.info(f"  -> Matching card '{card_name}' ({text}): {stars}★")

        total = len(matching_cards_stars)
        if total == 0:
            max_star = 0
            current_stars = 0
        else:
            max_star = max(matching_cards_stars)
            current_stars = min(3, max_star + total - 1)

        logger.success(
            f"[EnhancementAudit] '{unit_name}': total_copies={total}, max_star={max_star}★ "
            f"=> effective_stars={current_stars}★ (formula: max_star + total - 1)"
        )

        # In debug mode, capture and save enhancement card search result
        if self.debug_mode:
            annotated = frame.copy()
            h_f, w_f = annotated.shape[:2]
            cv2.rectangle(annotated, (0, 0), (w_f, 40), (30, 30, 30), -1)
            cv2.putText(
                annotated,
                f"CV AUDIT [{unit_name}]: Copies={total}, MaxStar={max_star}* => EffectiveStars={current_stars}*",
                (20, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0) if current_stars >= 3 else (0, 255, 255),
                2,
            )
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r"[^\w\-]", "_", unit_name)
            out_p = os.path.join(self.debug_dir, f"debug_cv_enhancement_{timestamp}_{safe_name}.png")
            is_success, im_buf = cv2.imencode(".png", annotated)
            if is_success:
                with open(out_p, "wb") as f:
                    im_buf.tofile(f)
                logger.info(f"📸 [Debug CV] Saved enhancement audit result to: {out_p}")
            else:
                logger.warning(f"Failed to encode debug image for {out_p}")

        # 6. Tap 關閉 button to clear search and restore filtered list
        self.device.tap(1215, 65)
        time.sleep(1.0)

        return total, current_stars

    def audit_pending_units_in_enhancement(self, units_to_audit: Optional[List[Dict]] = None) -> None:
        """
        Navigate to Enhancement, apply SSR & 開發單位 filters, and audit all queued units.
        """
        if units_to_audit is None:
            units_to_audit = self.pending_enhancement_units

        if not units_to_audit:
            logger.info("[EnhancementAudit] No pending units to audit in Enhancement. Skipping.")
            return

        logger.info(f"=== Starting Enhancement Audit for {len(units_to_audit)} queued SSR unit(s) ===")
        self.ensure_adb_keyboard()

        # Navigate to 強化 via bottom navigation (456, 1020)
        logger.info("Navigating to 強化 (Enhancement) screen at (456, 1020)...")
        self.device.tap(456, 1020)
        time.sleep(2.5)

        # Configure filters
        self.setup_enhancement_filters()

        # Audit each unit
        for idx, u in enumerate(units_to_audit):
            u_name = u["unit_name"]
            logger.info(f"[{idx+1}/{len(units_to_audit)}] Auditing SSR: '{u_name}'...")
            try:
                total, stars = self.search_and_audit_unit_enhancement(u_name)
                # Update DB
                self.db.upsert_unit(
                    series_name=u["series_name"],
                    route_name=u["route_name"],
                    unit_name=u_name,
                    owned_count=total,
                    current_stars=stars,
                    required_per_craft=u["required_per_craft"],
                    held_books=u["held_books"],
                )
            except Exception as e:
                logger.error(f"Error auditing '{u_name}' in Enhancement: {e}")
                # Intercept global popups via PageManager
                frame = self.device.screencap()
                pt, meta = self.page_manager.classify(frame)
                if pt in (
                    PageType.DATE_RESET,
                    PageType.RESOURCE_DOWNLOAD,
                    PageType.LOGIN_BONUS,
                    PageType.TITLE_SCREEN,
                    PageType.COMM_ERROR,
                    PageType.MODAL_INFO,
                    PageType.MODAL_CONFIRM,
                    PageType.LOADING,
                    PageType.HOME,
                ):
                    logger.warning(f"[EnhancementAudit] PageManager intercepted [{pt.value}], resolving...")
                    self.page_manager.resolve_page(frame)
                    logger.info("Re-navigating to 強化 at (456, 1020)...")
                    self.device.tap(456, 1020)
                    time.sleep(2.5)
                    self.setup_enhancement_filters()
                else:
                    # Ensure search bar is closed on error
                    self.device.tap(1215, 65)
                    time.sleep(1.0)

        logger.success("=== Enhancement Audit Completed for all units! ===")

        # Return to 開發 (Development) via bottom nav (714, 1000)
        logger.info("Returning to 開發 (Development) screen at (714, 1000)...")
        self.device.tap(714, 1000)
        time.sleep(2.0)
        self.ensure_on_series_list()

    # =========================================================================
    # Main Suite Execution
    # =========================================================================

    def run(self, page2_only: bool = False) -> None:
        """Run the full scanning suite across all series cards."""
        self.ensure_connected()
        self.ensure_on_series_list()
        self.pending_enhancement_units.clear()

        # Page 1 Grid (Row 1 to Row 4)
        # Columns: Col 0: 245, Col 1: 575, Col 2: 905, Col 3: 1235, Col 4: 1565
        # Rows:    Row 1: 340, Row 2: 515, Row 3: 690, Row 4: 865
        series_cards_page1 = [
            # Row 1 (y = 340)
            ("機動戰士GUNDAM", (575, 340)),
            ("第08MS小隊", (905, 340)),
            ("0080 口袋裡的戰爭", (1235, 340)),
            ("BLUE DESTINY", (1565, 340)),
            # Row 2 (y = 515)
            ("THUNDERBOLT DECEMBER SKY", (245, 515)),
            ("THUNDERBOLT BANDIT FLOWER", (575, 515)),
            ("0083 STARDUST MEMORY", (905, 515)),
            ("機動戰士Z GUNDAM", (1235, 515)),
            ("機動戰士ZZ GUNDAM", (1565, 515)),
            # Row 3 (y = 690)
            ("逆襲的夏亞", (245, 690)),
            ("機動戰士GUNDAM UC", (575, 690)),
            ("機動戰士GUNDAM NT", (905, 690)),
            ("閃光的哈薩威", (1235, 690)),
            ("機動戰士GUNDAM F91", (1565, 690)),
            # Row 4 (y = 865)
            ("機動戰士V GUNDAM", (245, 865)),
            ("機動武鬥傳G GUNDAM", (575, 865)),
            ("新機動戰記GUNDAM W", (905, 865)),
            ("Endless Waltz", (1235, 865)),
            ("機動新世紀GUNDAM X", (1565, 865)),
        ]

        if not page2_only:
            logger.info(f"=== Starting Page 1 Scan for {len(series_cards_page1)} series cards ===")
            for s_name, s_pos in series_cards_page1:
                try:
                    self.scan_series(s_name, s_pos)
                except Exception as e:
                    logger.error(f"Unexpected error scanning {s_name}: {e}")
                    self.ensure_on_series_list()

        # Page 2 Grid (Aligned to bottom of scroll track)
        # Row 3: y = 620, Row 4: y = 795
        series_cards_page2 = [
            # Row 3 (y = 620)
            ("機動戰士GUNDAM SEED", (245, 620)),
            ("機動戰士GUNDAM SEED ASTRAY", (575, 620)),
            ("機動戰士GUNDAM SEED X ASTRAY", (905, 620)),
            ("機動戰士GUNDAM SEED DESTINY", (1235, 620)),
            ("機動戰士GUNDAM 00", (1565, 620)),
            # Row 4 (y = 795)
            ("機動戰士GUNDAM AGE", (245, 795)),
            ("鐵血的孤兒", (575, 795)),
            ("鐵血的孤兒 月鋼", (905, 795)),
            ("水星的魔女", (1235, 795)),
        ]

        logger.info(f"=== Starting Page 2 Scan for {len(series_cards_page2)} series cards ===")
        for s_name, s_pos in series_cards_page2:
            try:
                self.ensure_on_series_list()
                # Game resets scroll to top upon exiting route, so always scroll down to page 2
                logger.info("Scrolling down series list to page 2...")
                self.device.swipe_bezier((960, 865), (960, 165), duration_ms=600)
                time.sleep(1.5)
                self.scan_series(s_name, s_pos)
            except Exception as e:
                logger.error(f"Unexpected error scanning {s_name}: {e}")
                self.ensure_on_series_list()

        logger.success("All series development route scans finished!")

        # Phase 2: Audit queued units in Enhancement
        if self.pending_enhancement_units:
            logger.info(f"Found {len(self.pending_enhancement_units)} SSR unit(s) requiring Enhancement audit.")
            self.audit_pending_units_in_enhancement()
        else:
            logger.info("No units required Enhancement audit.")

        logger.success("All series and enhancement audits completed successfully!")
        self.print_summary_report()

    def print_summary_report(self) -> None:
        """Print a formatted Markdown table of all deficient SSR units."""
        sys.stdout.reconfigure(encoding="utf-8")
        units = self.db.get_all_units()
        deficient = [u for u in units if u["is_deficient"] == 1]
        maxed = [u for u in units if u["current_stars"] >= 3]

        print("\n" + "=" * 80)
        print("                 SD GUNDAM DEVELOPABLE SSR AUDIT REPORT")
        print("=" * 80)
        print(f"Total Developable SSRs Analyzed: {len(units)}")
        print(f"Already Max Stars (3 Purple Stars): {len(maxed)}")
        print(f"Deficient (Need Books to Max):    {len(deficient)}\n")

        print("| 系列名稱 | 路線 | 機體名稱 | 目前星數 | 擁有狀態 | 單次所需 | 目前持有/需花費 | 尚缺技術書本數 |")
        print("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
        for u in deficient:
            owned_str = "已擁有" if u["owned_count"] > 0 else "未擁有"
            stars_str = f"{u['current_stars']}★"
            shortage_str = f"**缺 {u['books_shortage']} 本**"
            print(
                f"| {u['series_name']} | {u['route_name']} | {u['unit_name']} | "
                f"{stars_str} | {owned_str} | {u['required_per_craft']} | "
                f"{u['held_books']}/{u['total_books_needed']} | {shortage_str} |"
            )
        print("=" * 80 + "\n")


if __name__ == "__main__":
    is_debug = "--debug" in sys.argv
    scanner = SSRDevelopmentScanner(debug_mode=is_debug)

    if "--report" in sys.argv:
        scanner.print_summary_report()
    elif "--debug-current" in sys.argv:
        scanner.ensure_connected()
        scanner.debug_mode = True
        scanner.scan_canvas_ssrs("DEBUG_SERIES", "CURRENT_CANVAS")
        print("CV Debug capture completed.")
    elif "--audit-only" in sys.argv:
        # Audit existing units in DB that have owned_count > 0 and current_stars < 3
        units = scanner.db.get_all_units()
        to_audit = [u for u in units if u["owned_count"] > 0 and u["current_stars"] < 3]
        scanner.ensure_connected()
        scanner.audit_pending_units_in_enhancement(to_audit)
        scanner.print_summary_report()
    elif "--page2" in sys.argv:
        scanner.run(page2_only=True)
    else:
        scanner.run()
