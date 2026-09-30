"""Integration test for Device module with connected emulator."""
import numpy as np
import pytest

from core.device import Device, DeviceConfig


def test_device_live_connection():
    """Verify live connection to BlueStacks emulator and screencap dimensions."""
    cfg = DeviceConfig(
        host="127.0.0.1",
        port=5555,
        serial="emulator-5554",
        adb_path=r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    )
    device = Device(cfg)

    # 1. Connect
    connected = device.connect()
    assert connected is True
    assert device._connected is True

    # 2. Screencap
    frame = device.screencap()
    assert isinstance(frame, np.ndarray)
    assert len(frame.shape) == 3
    h, w, c = frame.shape
    assert w == 1920
    assert h == 1080
    assert c == 3
