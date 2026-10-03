"""Raw Dataset Collector for SD Gundam UI YOLO Model Training.

Automatically captures diverse, high-resolution (1920x1080) game screenshots
across all core categories to build a comprehensive YOLO annotation dataset:
1. dev_route: Tech tree canvas across multiple series (SSR/SR/R, stars_3, pills x0/x1, pedestals, tabs)
2. dev_modal: Unit info and acquisition guide dialogs (modals, cancel, confirm, close)
3. series_grid: Series selection list (top, middle, bottom scrolls)
4. enhancement: Enhancement screen grid, cards (1/2/3 stars), search bar, and filter dialog
5. main_ui: Home screen, navbar, and system dialogs
"""
import os
import sys
import time
from typing import Optional, Tuple

import cv2
import numpy as np
from loguru import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.device import Device
from core.vision import Vision
from core.page_manager import PageManager, PageType

DATASET_RAW_DIR = os.path.join(PROJECT_ROOT, "datasets", "gundam_ui", "raw_to_label")
os.makedirs(DATASET_RAW_DIR, exist_ok=True)


class RawDataCollector:
    """Safe, automated multi-category screenshot collector for YOLO labeling."""

    def __init__(self, serial: Optional[str] = None):
        self.device = Device(serial=serial)
        self.vision = Vision()
        self.page_manager = PageManager(self.device, self.vision)
        self.device.connect()
        self.capture_count = 0

    def save_capture(self, category: str, label: str = "") -> str:
        """Capture live screen and save with standardized name."""
        frame = self.device.screencap()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.capture_count += 1
        safe_label = f"_{label}" if label else ""
        filename = f"raw_{category}_{timestamp}_{self.capture_count:03d}{safe_label}.png"
        filepath = os.path.join(DATASET_RAW_DIR, filename)

        is_success, buf = cv2.imencode(".png", frame)
        if is_success:
            with open(filepath, "wb") as f:
                buf.tofile(f)
            logger.info(f"📸 [{category.upper()}] Captured: {filename}")
            return filepath
        else:
            logger.warning(f"Failed to encode capture: {filepath}")
            return ""

    def collect_dev_route_views(self, series_name: str) -> None:
        """Capture multiple canvas positions and branch views in a route map."""
        logger.info(f"Collecting route canvas views for: {series_name}...")
        # 1. Initial view
        self.save_capture("dev_route", f"{series_name}_view1_init")
        time.sleep(0.8)

        # 2. Swipe right to view terminal SSRs
        self.device.swipe_bezier((1600, 500), (300, 500), duration_ms=450)
        time.sleep(1.2)
        self.save_capture("dev_route", f"{series_name}_view2_right_ssrs")

        # 3. Swipe down to view mid/lower branches
        self.device.swipe_bezier((1000, 750), (1000, 250), duration_ms=450)
        time.sleep(1.2)
        self.save_capture("dev_route", f"{series_name}_view3_mid_branch")

        # 4. Swipe down again for bottom branch
        self.device.swipe_bezier((1000, 750), (1000, 250), duration_ms=450)
        time.sleep(1.2)
        self.save_capture("dev_route", f"{series_name}_view4_bottom_branch")

        # 5. Swipe left to return to starting R/SR nodes
        self.device.swipe_bezier((300, 500), (1600, 500), duration_ms=450)
        time.sleep(1.2)
        self.save_capture("dev_route", f"{series_name}_view5_left_start_nodes")

    def collect_dev_modals(self) -> None:
        """Tap on visible unit nodes to trigger and capture popup dialogs."""
        logger.info("Collecting development popup dialogs (unit info and guide)...")
        # Try tapping a unit in current view
        # Usually centered around (960, 500) or (1100, 500)
        self.device.tap(960, 480)
        time.sleep(1.5)
        self.save_capture("dev_modal", "unit_info_dialog")

        # Check if 主要獲得方式 button exists or tap its typical pos (1160, 760)
        self.device.tap(1160, 760)
        time.sleep(1.5)
        self.save_capture("dev_modal", "acquisition_guide_dialog")

        # Close acquisition guide (usually KEY_BACK or close button)
        self.device.key_back()
        time.sleep(1.0)

        # Close unit info dialog (cancel button at 755, 975)
        self.device.tap(755, 975)
        time.sleep(1.2)
        self.device.key_back()
        time.sleep(1.0)

    def return_to_series_list(self) -> None:
        """Safely navigate back to series selection screen."""
        for _ in range(3):
            # Tap header back button at (120, 50)
            self.device.tap(120, 50)
            time.sleep(1.5)
            # Or tap bottom nav 開發 at (714, 1029)
            self.device.tap(714, 1029)
            time.sleep(1.5)

    def collect_series_grid(self) -> None:
        """Capture series selection grid at different scroll positions."""
        logger.info("Collecting series selection grid views...")
        # 1. Page 1 (Top)
        self.save_capture("series_grid", "page1_top")
        time.sleep(0.8)

        # 2. Slight scroll down
        self.device.swipe_bezier((960, 700), (960, 450), duration_ms=400)
        time.sleep(1.2)
        self.save_capture("series_grid", "page1_middle_scroll")

        # 3. Full scroll down to Page 2
        self.device.swipe_bezier((960, 850), (960, 250), duration_ms=500)
        time.sleep(1.2)
        self.save_capture("series_grid", "page2_bottom")

        # 4. Scroll back to top
        self.device.swipe_bezier((960, 250), (960, 850), duration_ms=500)
        time.sleep(1.2)

    def collect_enhancement_views(self) -> None:
        """Capture enhancement screen, card stars, search, and filter dialog."""
        logger.info("Collecting enhancement screen views...")
        # 1. Navigate to 強化 via bottom navbar (431, 1021)
        self.device.tap(431, 1021)
        time.sleep(2.5)
        self.save_capture("enhancement", "unit_grid_view1")

        # 2. Scroll unit grid down for more diverse units/stars
        self.device.swipe_bezier((960, 750), (960, 300), duration_ms=450)
        time.sleep(1.5)
        self.save_capture("enhancement", "unit_grid_view2_scrolled")

        # 3. Open Filter dialog (1670, 900)
        self.device.tap(1670, 900)
        time.sleep(1.5)
        self.save_capture("enhancement", "filter_dialog_modal")

        # 4. Tap 重置 (1730, 855) and 確定 (1800, 990) to close filter
        self.device.tap(1800, 990)
        time.sleep(1.5)

        # 5. Open Search input (500, 160)
        self.device.tap(500, 160)
        time.sleep(1.2)
        self.save_capture("enhancement", "search_input_active")

        # Close search bar
        self.device.tap(1215, 65)
        time.sleep(1.2)

    def collect_main_ui_views(self) -> None:
        """Capture home screen and main menu navigation."""
        logger.info("Collecting Home and navigation views...")
        # Navigate to 主畫面 (197, 1028)
        self.device.tap(197, 1028)
        time.sleep(2.5)
        self.save_capture("main_ui", "home_screen")

        # Navigate to 關卡 (1002, 1029)
        self.device.tap(1002, 1029)
        time.sleep(2.5)
        self.save_capture("main_ui", "stages_screen")

        # Return to 開發 (714, 1029)
        self.device.tap(714, 1029)
        time.sleep(2.5)
        self.save_capture("main_ui", "returned_to_dev")

    def run_suite(self) -> int:
        """Run the comprehensive screenshot collection suite."""
        logger.info("=== Starting Comprehensive Raw Dataset Collection ===")
        initial_captures = self.capture_count

        try:
            # Phase 1: Current route view & modals
            self.collect_dev_route_views("Endless_Waltz")
            self.collect_dev_modals()

            # Phase 2: Series Grid views
            self.return_to_series_list()
            self.collect_series_grid()

            # Phase 3: Sample 3 different series for high visual diversity
            # Series A: 機動戰士GUNDAM (Row 1 Col 1: 575, 340)
            logger.info("Entering series: 機動戰士GUNDAM...")
            self.device.tap(575, 340)
            time.sleep(2.5)
            self.collect_dev_route_views("First_Gundam_UC0079")
            self.collect_dev_modals()
            self.return_to_series_list()

            # Series B: 0080 口袋裡的戰爭 (Row 1 Col 2: 1235, 340)
            logger.info("Entering series: 0080 口袋裡的戰爭...")
            self.device.tap(1235, 340)
            time.sleep(2.5)
            self.collect_dev_route_views("Gundam_0080_WarInPocket")
            self.return_to_series_list()

            # Series C: Scroll to Page 2, enter 機動戰士GUNDAM SEED (245, 620)
            logger.info("Entering series: 機動戰士GUNDAM SEED...")
            self.device.swipe_bezier((960, 850), (960, 250), duration_ms=500)
            time.sleep(1.2)
            self.device.tap(245, 620)
            time.sleep(2.5)
            self.collect_dev_route_views("Gundam_SEED")
            # Switch to route tab 2 if available
            self.device.tap(100, 400)
            time.sleep(1.5)
            self.save_capture("dev_route", "Gundam_SEED_route2")
            self.return_to_series_list()

            # Phase 4: Enhancement screens, unit cards, filters
            self.collect_enhancement_views()

            # Phase 5: Home & system UI
            self.collect_main_ui_views()

        except Exception as e:
            logger.error(f"Error during raw data collection: {e}")
            self.return_to_series_list()

        total_collected = self.capture_count - initial_captures
        logger.success(
            f"=== Finished Raw Dataset Collection! Total newly captured: {total_collected} ==="
        )
        logger.info(f"Target directory: {DATASET_RAW_DIR}")
        return total_collected


if __name__ == "__main__":
    collector = RawDataCollector()
    collector.run_suite()
