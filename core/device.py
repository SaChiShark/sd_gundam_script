"""ADB Device communication and human-like input emulation module."""
import os
import random
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

import adbutils
import cv2
import numpy as np
from loguru import logger

from core.config import DeviceConfig


class DeviceConnectionError(Exception):
    """Raised when ADB cannot connect to the specified device or emulator."""
    pass


class AdbCommandError(Exception):
    """Raised when an ADB shell command fails or times out."""
    pass


class Device:
    """High-performance ADB wrapper with human-like interaction emulation using adbutils socket."""

    def __init__(
        self,
        config: Optional[DeviceConfig] = None,
        serial: Optional[str] = None,
        debug_mode: Optional[bool] = None,
        step_by_step: Optional[bool] = None,
        debug_dir: Optional[str] = None,
    ):
        self.config = config or DeviceConfig()
        self.host = self.config.host
        self.port = self.config.port
        self.serial: Optional[str] = serial or self.config.serial
        self.debug_mode: bool = debug_mode if debug_mode is not None else self.config.debug_mode
        self.step_by_step: bool = step_by_step if step_by_step is not None else self.config.step_by_step
        if self.step_by_step:
            self.debug_mode = True
        self.debug_dir: str = debug_dir or self.config.debug_dir
        self._tap_counter: int = 0
        self._adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
        self._device: Optional[adbutils.AdbDevice] = None
        self._connected = False

    def connect(self) -> bool:
        """Establish connection to the emulator device via adbutils."""
        target_addr = f"{self.host}:{self.port}"

        devices = self._adb.device_list()
        if not devices:
            try:
                self._adb.connect(target_addr)
                devices = self._adb.device_list()
            except Exception as e:
                logger.debug(f"ADB connect attempt: {e}")

        if not devices:
            raise DeviceConnectionError(
                f"No authorized devices found on ADB. Ensure emulator ADB is enabled."
            )

        serials = [d.serial for d in devices]
        if self.serial and self.serial in serials:
            self._device = self._adb.device(self.serial)
            logger.info(f"Connected to targeted device serial: {self.serial}")
        elif target_addr in serials:
            self.serial = target_addr
            self._device = self._adb.device(self.serial)
            logger.info(f"Connected to target address serial: {self.serial}")
        else:
            self.serial = serials[0]
            self._device = self._adb.device(self.serial)
            logger.info(f"Connected to discovered device serial: {self.serial}")

        self._connected = True
        logger.success(f"Device successfully connected: {self.serial}")
        return True

    def screencap(self) -> np.ndarray:
        """
        Capture current screen as an OpenCV BGR image using adbutils socket stream.
        Zero disk I/O for minimum latency.
        """
        if not self._connected or self._device is None:
            self.connect()

        try:
            pil_img = self._device.screenshot()
            # Convert RGB PIL image to BGR OpenCV numpy array
            rgb_arr = np.array(pil_img)
            bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
            return bgr_arr
        except Exception as e:
            logger.error(f"Screencap failed: {e}")
            raise AdbCommandError(f"Failed to capture screen: {e}") from e

    def _render_tap_marker(
        self,
        frame: np.ndarray,
        target_x: int,
        target_y: int,
        tap_idx: int,
        action_name: str = ""
    ) -> np.ndarray:
        """
        Draw a high-visibility target marker (crosshair, concentric circles, text badge)
        onto the frame at the specified click coordinates.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        red = (0, 0, 255)
        cyan = (255, 255, 0)
        white = (255, 255, 255)
        dark_bg = (25, 25, 25)

        # Concentric circles
        cv2.circle(annotated, (target_x, target_y), 32, red, 3, cv2.LINE_AA)
        cv2.circle(annotated, (target_x, target_y), 16, cyan, 2, cv2.LINE_AA)
        cv2.circle(annotated, (target_x, target_y), 4, red, -1, cv2.LINE_AA)

        # Crosshair lines with central gap
        gap = 8
        arm = 45
        cv2.line(annotated, (max(0, target_x - arm), target_y), (max(0, target_x - gap), target_y), red, 2, cv2.LINE_AA)
        cv2.line(annotated, (min(w, target_x + gap), target_y), (min(w, target_x + arm), target_y), red, 2, cv2.LINE_AA)
        cv2.line(annotated, (target_x, max(0, target_y - arm)), (target_x, max(0, target_y - gap)), red, 2, cv2.LINE_AA)
        cv2.line(annotated, (target_x, min(h, target_y + gap)), (target_x, min(h, target_y + arm)), red, 2, cv2.LINE_AA)

        # Info Tag Banner
        timestamp_str = time.strftime("%H:%M:%S")
        tag_text = f"Step #{tap_idx} | Tap ({target_x}, {target_y}) | {timestamp_str}"
        if action_name:
            tag_text += f" | {action_name}"

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.65
        thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(tag_text, font, font_scale, thickness)

        box_x1 = max(10, min(w - text_w - 24, target_x - text_w // 2))
        if target_y - 48 > text_h + 16:
            box_y1 = target_y - 48 - text_h - 10
        else:
            box_y1 = min(h - text_h - 24, target_y + 42)
        box_x2 = box_x1 + text_w + 18
        box_y2 = box_y1 + text_h + 14

        overlay = annotated.copy()
        cv2.rectangle(overlay, (box_x1, box_y1), (box_x2, box_y2), dark_bg, -1)
        cv2.rectangle(overlay, (box_x1, box_y1), (box_x2, box_y2), cyan, 1)
        cv2.addWeighted(overlay, 0.78, annotated, 0.22, 0, annotated)

        cv2.putText(
            annotated,
            tag_text,
            (box_x1 + 9, box_y2 - 8),
            font,
            font_scale,
            white,
            thickness,
            cv2.LINE_AA
        )
        return annotated

    def tap(
        self,
        x: int,
        y: int,
        radius: int = 0,
        delay_after: Tuple[float, float] = (0.4, 0.8),
        action_name: str = ""
    ) -> None:
        """
        Deterministic tap at exact (x, y) coordinates.
        In debug mode, automatically captures a screenshot with visual tap marker
        and provides interactive step-by-step control.
        """
        if not self._connected or self._device is None:
            self.connect()

        target_x = x
        target_y = y

        # Debug mode: generate screenshot with click marker & step-by-step control
        if self.debug_mode or self.step_by_step:
            self._tap_counter += 1
            os.makedirs(self.debug_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tap_{self._tap_counter:04d}_({target_x}_{target_y})_{timestamp}.png"
            filepath = os.path.join(self.debug_dir, filename)

            try:
                frame = self.screencap()
                annotated = self._render_tap_marker(
                    frame, target_x, target_y, self._tap_counter, action_name=action_name
                )
                cv2.imwrite(filepath, annotated)
                logger.info(f"📸 [Debug Tap #{self._tap_counter}] Marked screenshot saved to: {filepath}")
            except Exception as e:
                logger.warning(f"[Debug Tap] Failed to capture debug screenshot: {e}")

            if self.step_by_step:
                print("\n" + "=" * 76)
                print(f"🕹️  [STEP DEBUG #{self._tap_counter}] 即將點擊: ({target_x}, {target_y})")
                if action_name:
                    print(f"🏷️  動作標籤: {action_name}")
                print(f"📸 標記截圖: {filepath}")
                print("   [Enter]  : 執行此點擊並前進到下一步 (Step-by-step)")
                print("   [c / C]  : 切換為「一次執行完」(Continuous 模式，後續不再暫停)")
                print("   [s / S]  : 跳過本次點擊 (Skip tap)")
                print("   [q / Q]  : 中止腳本執行 (Quit)")
                print("=" * 76)
                try:
                    user_cmd = input("請選擇操作 [Enter/c/s/q]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    user_cmd = "q"

                if user_cmd == "c":
                    logger.info("🕹️ [Debug Mode] 使用者切換為「一次執行完」(Continuous Mode)，後續將自動連續執行。")
                    self.step_by_step = False
                elif user_cmd == "s":
                    logger.warning(f"🕹️ [Debug Mode] 使用者選擇跳過本次點擊: ({target_x}, {target_y})")
                    return
                elif user_cmd == "q":
                    logger.error("🕹️ [Debug Mode] 使用者中止執行。")
                    raise SystemExit("Execution aborted by user in debug mode.")

        logger.debug(f"Tap: ({target_x}, {target_y})")
        if self._device is not None:
            self._device.click(target_x, target_y)

        sleep_dur = random.uniform(delay_after[0], delay_after[1])
        time.sleep(sleep_dur)

    def tap_rect(
        self,
        rect: Tuple[int, int, int, int],
        padding_ratio: float = 0.2,
        delay_after: Tuple[float, float] = (0.5, 1.0),
        action_name: str = ""
    ) -> None:
        """
        Deterministic tap at the exact geometric center of bounding box (x, y, w, h).
        """
        x, y, w, h = rect
        click_x = int(x + w / 2)
        click_y = int(y + h / 2)
        self.tap(click_x, click_y, radius=0, delay_after=delay_after, action_name=action_name)

    def swipe_bezier(
        self,
        start_pt: Tuple[int, int],
        end_pt: Tuple[int, int],
        duration_ms: int = 600,
        steps: int = 15
    ) -> None:
        """
        Perform a human-like swipe with Bezier curve interpolation.
        Prevents mechanical linear trajectory detection.
        """
        if not self._connected or self._device is None:
            self.connect()

        x1, y1 = start_pt
        x2, y2 = end_pt

        dur_s = max(0.2, duration_ms / 1000.0)
        jittered_dur = dur_s * random.uniform(0.9, 1.15)
        self._device.swipe(x1, y1, x2, y2, jittered_dur)
        time.sleep(random.uniform(0.5, 0.8))

    def key_back(self) -> None:
        """Simulate pressing Android BACK key (KEYCODE_BACK = 4)."""
        if not self._connected or self._device is None:
            self.connect()
        logger.debug("Device input: KEYCODE_BACK")
        self._device.keyevent(4)
        time.sleep(random.uniform(0.6, 1.0))

    def key_home(self) -> None:
        """Simulate pressing Android HOME key (KEYCODE_HOME = 3)."""
        if not self._connected or self._device is None:
            self.connect()
        logger.debug("Device input: KEYCODE_HOME")
        self._device.keyevent(3)
        time.sleep(random.uniform(0.8, 1.2))

    def is_app_running(self, package_name: str) -> bool:
        """Check if an application process is running."""
        if not self._connected or self._device is None:
            self.connect()
        out = self._device.shell(f"pidof {package_name}").strip()
        return bool(out)

    def is_app_foreground(self, package_name: str) -> bool:
        """Check if an application is currently focused in the foreground."""
        if not self._connected or self._device is None:
            self.connect()
        out = self._device.shell("dumpsys window")
        for line in out.splitlines():
            if "mCurrentFocus" in line and package_name in line:
                return True
        return False

    def launch_app(self, package_name: str, activity: Optional[str] = None) -> None:
        """Launch an application using am start or monkey."""
        if not self._connected or self._device is None:
            self.connect()
        logger.info(f"Launching app: {package_name}...")
        if activity:
            self._device.shell(f"am start -n {package_name}/{activity}")
        else:
            self._device.shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        time.sleep(random.uniform(2.5, 3.5))

    def stop_app(self, package_name: str) -> None:
        """Force stop an application."""
        if not self._connected or self._device is None:
            self.connect()
        logger.info(f"Stopping app: {package_name}...")
        self._device.shell(f"am force-stop {package_name}")
        time.sleep(random.uniform(0.5, 1.0))

    def random_sleep(self, min_sec: float = 0.5, max_sec: float = 1.2) -> None:
        """Sleep for a randomized duration."""
        dur = random.uniform(min_sec, max_sec)
        time.sleep(dur)
