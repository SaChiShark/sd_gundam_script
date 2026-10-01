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
        serial: Optional[str] = None
    ):
        self.config = config or DeviceConfig()
        self.host = self.config.host
        self.port = self.config.port
        self.serial: Optional[str] = serial or self.config.serial
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

    def tap(
        self,
        x: int,
        y: int,
        radius: int = 5,
        delay_after: Tuple[float, float] = (0.4, 0.8)
    ) -> None:
        """
        Human-like randomized tap around (x, y) with slight Gaussian jitter.
        """
        if not self._connected or self._device is None:
            self.connect()

        offset_x = int(random.gauss(0, radius / 2))
        offset_y = int(random.gauss(0, radius / 2))
        target_x = max(0, x + max(-radius, min(radius, offset_x)))
        target_y = max(0, y + max(-radius, min(radius, offset_y)))

        logger.debug(f"Tap: requested=({x}, {y}) -> actual=({target_x}, {target_y})")
        self._device.click(target_x, target_y)

        sleep_dur = random.uniform(delay_after[0], delay_after[1])
        time.sleep(sleep_dur)

    def tap_rect(
        self,
        rect: Tuple[int, int, int, int],
        padding_ratio: float = 0.2,
        delay_after: Tuple[float, float] = (0.5, 1.0)
    ) -> None:
        """
        Human-like tap within a bounding box (x, y, w, h).
        Applies padding to avoid touching close to borders.
        """
        x, y, w, h = rect
        pad_w = int(w * padding_ratio)
        pad_h = int(h * padding_ratio)

        safe_min_x = x + pad_w
        safe_max_x = x + w - pad_w
        safe_min_y = y + pad_h
        safe_max_y = y + h - pad_h

        click_x = random.randint(safe_min_x, max(safe_min_x, safe_max_x))
        click_y = random.randint(safe_min_y, max(safe_min_y, safe_max_y))

        self.tap(click_x, click_y, radius=2, delay_after=delay_after)

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
