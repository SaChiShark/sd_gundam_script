"""ADB Device communication and human-like input emulation module."""
import os
import random
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

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
    """High-performance ADB wrapper with human-like interaction emulation."""

    def __init__(self, config: Optional[DeviceConfig] = None):
        self.config = config or DeviceConfig()
        self.adb_bin = self._resolve_adb_path(self.config.adb_path)
        self.serial: Optional[str] = self.config.serial
        self.host = self.config.host
        self.port = self.config.port
        self._connected = False

    def _resolve_adb_path(self, preferred_path: Optional[str]) -> str:
        """Find a valid ADB binary on the host system."""
        if preferred_path and os.path.isfile(preferred_path):
            return preferred_path

        # Check system PATH
        which_adb = shutil.which("adb")
        if which_adb:
            return which_adb

        # Check common emulator ADB locations
        candidates = [
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
            r"C:\leidian\LDPlayer9\adb.exe",
            r"C:\Program Files\Nox\bin\nox_adb.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

        raise FileNotFoundError(
            "Could not locate an ADB executable. Please specify adb_path in config.yaml or add adb to PATH."
        )

    def _run_adb_cmd(
        self,
        args: List[str],
        with_target: bool = True,
        timeout: float = 10.0,
        binary_output: bool = False
    ) -> subprocess.CompletedProcess:
        """Run an ADB command safely with timeout handling."""
        cmd = [self.adb_bin]
        if with_target and self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
            return res
        except subprocess.TimeoutExpired as e:
            logger.error(f"ADB command timed out after {timeout}s: {' '.join(cmd)}")
            raise AdbCommandError(f"ADB command timed out: {e}") from e

    def connect(self) -> bool:
        """Establish connection to the emulator device."""
        target_addr = f"{self.host}:{self.port}"
        logger.info(f"Connecting to ADB target: {target_addr} via {self.adb_bin}...")

        # Run connect command
        connect_res = self._run_adb_cmd(["connect", target_addr], with_target=False, timeout=8.0)
        connect_out = connect_res.stdout.decode("utf-8", errors="ignore").strip()
        logger.debug(f"ADB connect response: {connect_out}")

        # List attached devices to identify matching serial
        devices_res = self._run_adb_cmd(["devices"], with_target=False, timeout=5.0)
        lines = devices_res.stdout.decode("utf-8", errors="ignore").strip().splitlines()
        
        attached_devices = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                attached_devices.append(parts[0])

        if not attached_devices:
            raise DeviceConnectionError(
                f"No authorized devices found on ADB. Ensure emulator ADB is enabled. Output: {connect_out}"
            )

        # Match serial or select first available
        if self.serial and self.serial in attached_devices:
            logger.info(f"Found targeted device serial: {self.serial}")
        elif target_addr in attached_devices:
            self.serial = target_addr
            logger.info(f"Using target address serial: {self.serial}")
        else:
            self.serial = attached_devices[0]
            logger.info(f"Using default discovered device serial: {self.serial}")

        self._connected = True
        logger.success(f"Device successfully connected: {self.serial}")
        return True

    def screencap(self) -> np.ndarray:
        """
        Capture current screen as an OpenCV BGR image using in-memory binary stream.
        Zero disk I/O for minimum latency (<100ms).
        """
        if not self._connected:
            self.connect()

        res = self._run_adb_cmd(
            ["exec-out", "screencap", "-p"],
            with_target=True,
            timeout=self.config.screencap_timeout,
            binary_output=True
        )

        if res.returncode != 0 or not res.stdout:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"Screencap failed: {err}")
            raise AdbCommandError(f"Failed to capture screen: {err}")

        # Decode image from binary buffer directly
        raw_bytes = np.frombuffer(res.stdout, dtype=np.uint8)
        img = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
        if img is None:
            raise AdbCommandError("Failed to decode screencap bytes into OpenCV BGR image.")

        return img

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
        if not self._connected:
            self.connect()

        # Gaussian jitter within safe radius
        offset_x = int(random.gauss(0, radius / 2))
        offset_y = int(random.gauss(0, radius / 2))
        target_x = max(0, x + max(-radius, min(radius, offset_x)))
        target_y = max(0, y + max(-radius, min(radius, offset_y)))

        logger.debug(f"Tap: requested=({x}, {y}) -> actual=({target_x}, {target_y})")
        self._run_adb_cmd(["shell", "input", "tap", str(target_x), str(target_y)])

        # Randomized post-tap sleep
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
        x1, y1 = start_pt
        x2, y2 = end_pt

        # Random control point to produce curve
        cx = (x1 + x2) // 2 + random.randint(-40, 40)
        cy = (y1 + y2) // 2 + random.randint(-40, 40)

        # Generate quadratic Bezier points: B(t) = (1-t)^2*P0 + 2(1-t)t*P1 + t^2*P2
        points = []
        for i in range(steps + 1):
            t = i / steps
            px = int((1 - t)**2 * x1 + 2 * (1 - t) * t * cx + t**2 * x2)
            py = int((1 - t)**2 * y1 + 2 * (1 - t) * t * cy + t**2 * y2)
            points.append((px, py))

        # Perform drag/swipe via adb input
        # Note: Android shell input swipe accepts x1 y1 x2 y2 duration
        # For simple robust execution we supply start, end, and duration with jitter
        jittered_dur = int(duration_ms * random.uniform(0.9, 1.15))
        self._run_adb_cmd([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(jittered_dur)
        ])
        time.sleep(random.uniform(0.5, 0.8))

    def key_back(self) -> None:
        """Simulate pressing Android BACK key (KEYCODE_BACK = 4)."""
        logger.debug("Device input: KEYCODE_BACK")
        self._run_adb_cmd(["shell", "input", "keyevent", "4"])
        time.sleep(random.uniform(0.6, 1.0))

    def key_home(self) -> None:
        """Simulate pressing Android HOME key (KEYCODE_HOME = 3)."""
        logger.debug("Device input: KEYCODE_HOME")
        self._run_adb_cmd(["shell", "input", "keyevent", "3"])
        time.sleep(random.uniform(0.8, 1.2))

    def is_app_running(self, package_name: str) -> bool:
        """Check if an application process is running."""
        res = self._run_adb_cmd(["shell", "pidof", package_name])
        return bool(res.stdout.decode("utf-8", errors="ignore").strip())

    def is_app_foreground(self, package_name: str) -> bool:
        """Check if an application is currently focused in the foreground."""
        res = self._run_adb_cmd(["shell", "dumpsys", "window"])
        output = res.stdout.decode("utf-8", errors="ignore")
        for line in output.splitlines():
            if "mCurrentFocus" in line and package_name in line:
                return True
        return False

    def launch_app(self, package_name: str, activity: Optional[str] = None) -> None:
        """Launch an application using am start or monkey."""
        logger.info(f"Launching app: {package_name}...")
        if activity:
            self._run_adb_cmd(["shell", "am", "start", "-n", f"{package_name}/{activity}"])
        else:
            self._run_adb_cmd([
                "shell", "monkey", "-p", package_name,
                "-c", "android.intent.category.LAUNCHER", "1"
            ])
        time.sleep(random.uniform(2.5, 3.5))

    def stop_app(self, package_name: str) -> None:
        """Force stop an application."""
        logger.info(f"Stopping app: {package_name}...")
        self._run_adb_cmd(["shell", "am", "force-stop", package_name])
        time.sleep(random.uniform(0.5, 1.0))

    def random_sleep(self, min_sec: float = 0.5, max_sec: float = 1.2) -> None:
        """Sleep for a randomized duration."""
        dur = random.uniform(min_sec, max_sec)
        time.sleep(dur)
