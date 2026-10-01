"""Complete autonomous scanner for developable SSR units in SD Gundam G Generation Eternal.

Features robust guardrails (保險機制):
- Deterministic State Sentinel using OpenCV template matching
- Pre- and post-condition verification on every UI transition
- Auto-recovery to main Development screen if lost
- Strict canvas boundary masks & HSV gold detection to prevent false-positive SSR clicks
- Popup defense to ensure OCR only records true developable SSR units
- Skip all 【終極】 (Ultimate) route maps
"""
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger
from rapidocr_onnxruntime import RapidOCR

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.database import SSRDevelopmentDB
from core.device import Device
from core.vision import Vision


class SSRDevelopmentScanner:
    """Automated scanner with full guardrails that inspects all general routes for developable SSRs."""

    def __init__(self, serial: Optional[str] = None):
        self.device = Device(serial=serial)
        self.vision = Vision()
        self.db = SSRDevelopmentDB()
        self.ocr = RapidOCR()

        # Verified visual anchor templates
        self.anchor_from_owned = "assets/anchors/anchor_from_owned.png"
        self.anchor_catalog = "assets/anchors/anchor_catalog.png"
        self.btn_back_arrow = "assets/buttons/btn_back_arrow.png"
        self.btn_dev_cancel = "assets/buttons/btn_dev_cancel.png"
        self.btn_close_gray = "assets/buttons/btn_close_gray.png"
        self.nav_btn_dev = "assets/buttons/nav_btn_dev.png"
        self.badge_ssr = "assets/icons/badge_ssr.png"
        self.stars_3_purple = "assets/icons/stars_3_purple.png"

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

            # Check if a popup is blocking the screen
            m_cancel = self.vision.match_template(frame, self.btn_dev_cancel, threshold=0.70)
            m_close = self.vision.match_template(frame, self.btn_close_gray, threshold=0.70)
            if m_cancel or m_close:
                self.close_any_popup()
                continue

            # If inside route map, tap the back arrow at (120, 50)
            if self.is_in_route_map(frame):
                self.device.tap(120, 50)
                time.sleep(1.5)
                continue

            # If completely lost, tap the true 開發 bottom nav button at (660, 980)
            logger.warning("Unrecognized screen state, tapping bottom navigation '開發' icon at (660, 980)...")
            self.device.tap(660, 980)
            time.sleep(2.0)

            # Check again
            f_check = self.device.screencap()
            if self.is_on_series_list(f_check):
                return True

            # Extra insurance: press KEY_BACK once in case a full-screen banner is up
            self.device.key_back()
            time.sleep(1.5)

        return self.is_on_series_list()

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

        # 1. Red channel mean check
        r_mean = np.mean(crop[10 : h - 10, 10 : w - 10, 2])
        if r_mean < 138:
            return False

        # 2. HSV Gold/Amber mask check (H: 15-35, S: 120-255, V: 120-255)
        # SSR typically has 450-660 gold pixels; R and SR have < 50
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        gold_mask = (hsv[:, :, 0] >= 15) & (hsv[:, :, 0] <= 35) & (hsv[:, :, 1] >= 120) & (hsv[:, :, 2] >= 120)
        gold_px = np.sum(gold_mask)

        if gold_px < 200:
            return False

        return True

    def scan_canvas_ssrs(self, series_name: str, route_name: str) -> None:
        """
        Scan visible canvas for SSR units.
        - Filters out badges outside valid route canvas.
        - Verifies true SSR gold color to reject R and SR false-positives.
        - If 3 purple stars are visible -> recorded as maxed, no need to open popup.
        - If not maxed -> taps unit, validates popup, runs OCR, saves to SQLite, closes popup.
        """
        frame = self.device.screencap()

        # Find SSR badges with template matching + HSV gold verification
        all_matches = self.vision.match_all(frame, self.badge_ssr, threshold=0.50, min_distance=50)

        # Strict Spatial Mask & Multi-factor SSR Verification
        valid_matches = [
            m for m in all_matches
            if self.CANVAS_X_MIN <= m.center[0] <= self.CANVAS_X_MAX
            and self.CANVAS_Y_MIN <= m.center[1] <= self.CANVAS_Y_MAX
            and self.is_true_ssr(frame, m)
        ]

        logger.info(f"[{series_name} | {route_name}] Found {len(valid_matches)} verified SSR badge(s) on canvas.")

        for match in valid_matches:
            bx, by, bw, bh = match.rect

            # Determine ownership from pill box next to badge
            pill_crop = frame[by : by + bh, bx + bw : bx + bw + 90]
            pill_res, _ = self.ocr(pill_crop)
            pill_text = " ".join([r[1] for r in pill_res or []])
            owned_count = 0 if "0" in pill_text else 1

            # Check for 3 purple stars in the ROI to the right of the badge
            pad_x1 = max(0, bx - 10)
            pad_x2 = min(frame.shape[1], bx + 220)
            pad_y1 = max(0, by - 70)
            pad_y2 = min(frame.shape[0], by + 10)

            star_roi = frame[pad_y1:pad_y2, pad_x1:pad_x2]
            purple_match = self.vision.match_template(star_roi, self.stars_3_purple, threshold=0.65)

            if purple_match:
                logger.success(f"[{series_name} | {route_name}] SSR unit at ({bx}, {by}) is ALREADY 3 PURPLE STARS (★★★)!")
                self.db.upsert_unit(
                    series_name=series_name,
                    route_name=route_name,
                    unit_name=f"{series_name}_{route_name}_滿星SSR_{bx}",
                    owned_count=owned_count,
                    current_stars=3,
                    required_per_craft=3,
                    held_books=0,
                )
            else:
                logger.warning(f"[{series_name} | {route_name}] Found NOT-MAXED SSR at ({bx}, {by})! Inspecting...")
                # Tap unit node (pedestal ring at bx + 60, by - 65)
                tap_x = bx + 60
                tap_y = max(0, by - 65)
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
                if info:
                    unit_name, required_per_craft, held_books = info
                    self.db.upsert_unit(
                        series_name=series_name,
                        route_name=route_name,
                        unit_name=unit_name,
                        owned_count=owned_count,
                        current_stars=0,
                        required_per_craft=required_per_craft,
                        held_books=held_books,
                    )

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
    # Main Suite Execution
    # =========================================================================

    def run(self, page2_only: bool = False) -> None:
        """Run the full scanning suite across all series cards."""
        self.ensure_connected()
        self.ensure_on_series_list()

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

        logger.success("All series scanned successfully!")
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
    scanner = SSRDevelopmentScanner()
    if "--report" in sys.argv:
        scanner.print_summary_report()
    elif "--page2" in sys.argv:
        scanner.run(page2_only=True)
    else:
        scanner.run()
