"""Unit and Integration tests for Device module."""
import os
from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest

from core.device import Device, DeviceConfig, DeviceConnectionError


def test_device_live_connection():
    """Verify live connection to BlueStacks emulator and screencap dimensions if connected."""
    cfg = DeviceConfig(
        host="127.0.0.1",
        port=5555,
        serial="emulator-5554",
        adb_path=r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    )
    device = Device(cfg)

    try:
        connected = device.connect()
    except DeviceConnectionError:
        pytest.skip("Emulator is not running; skipping live connection test.")

    assert connected is True
    assert device._connected is True

    frame = device.screencap()
    assert isinstance(frame, np.ndarray)
    assert len(frame.shape) == 3
    h, w, c = frame.shape
    assert w == 1920
    assert h == 1080
    assert c == 3


def test_render_tap_marker():
    """Verify that _render_tap_marker draws target overlay and returns valid annotated image."""
    device = Device(DeviceConfig())
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    annotated = device._render_tap_marker(
        dummy_frame,
        target_x=960,
        target_y=540,
        tap_idx=1,
        action_name="test_click"
    )

    assert annotated.shape == (1080, 1920, 3)
    # The annotated frame must have non-zero pixels where markers were rendered
    assert np.count_nonzero(annotated) > 0


def test_tap_debug_mode_generates_screenshot(tmp_path):
    """Verify that Device.tap() with debug_mode=True saves a marked screenshot."""
    debug_dir = str(tmp_path / "debug_taps")
    cfg = DeviceConfig(debug_mode=True, step_by_step=False, debug_dir=debug_dir)
    device = Device(cfg)

    # Mock device internals so hardware is not required
    device._connected = True
    device._device = MagicMock()
    dummy_frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    device.screencap = MagicMock(return_value=dummy_frame)

    device.tap(500, 600, delay_after=(0.0, 0.0), action_name="test_action")

    # Verify device.click was called
    assert device._device.click.called

    # Verify screenshot was saved in debug_dir
    files = os.listdir(debug_dir)
    assert len(files) == 1
    assert files[0].startswith("tap_0001_")
    assert files[0].endswith(".png")

    saved_img = cv2.imread(os.path.join(debug_dir, files[0]))
    assert saved_img is not None
    assert saved_img.shape == (1080, 1920, 3)


def test_tap_step_by_step_continuous(tmp_path, monkeypatch):
    """Verify that entering 'c' switches step_by_step to False (continuous execution)."""
    debug_dir = str(tmp_path / "debug_taps")
    cfg = DeviceConfig(debug_mode=True, step_by_step=True, debug_dir=debug_dir)
    device = Device(cfg)

    device._connected = True
    device._device = MagicMock()
    dummy_frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    device.screencap = MagicMock(return_value=dummy_frame)

    monkeypatch.setattr("builtins.input", lambda _: "c")
    device.tap(500, 600, delay_after=(0.0, 0.0))

    # Should have executed the click
    assert device._device.click.called
    # And switched step_by_step to False
    assert device.step_by_step is False


def test_tap_step_by_step_skip(tmp_path, monkeypatch):
    """Verify that entering 's' skips the click entirely."""
    debug_dir = str(tmp_path / "debug_taps")
    cfg = DeviceConfig(debug_mode=True, step_by_step=True, debug_dir=debug_dir)
    device = Device(cfg)

    device._connected = True
    device._device = MagicMock()
    dummy_frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    device.screencap = MagicMock(return_value=dummy_frame)

    monkeypatch.setattr("builtins.input", lambda _: "s")
    device.tap(500, 600, delay_after=(0.0, 0.0))

    # Click should NOT have been called
    assert not device._device.click.called


def test_tap_step_by_step_quit(tmp_path, monkeypatch):
    """Verify that entering 'q' raises SystemExit to safely abort."""
    debug_dir = str(tmp_path / "debug_taps")
    cfg = DeviceConfig(debug_mode=True, step_by_step=True, debug_dir=debug_dir)
    device = Device(cfg)

    device._connected = True
    device._device = MagicMock()
    dummy_frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    device.screencap = MagicMock(return_value=dummy_frame)

    monkeypatch.setattr("builtins.input", lambda _: "q")
    with pytest.raises(SystemExit):
        device.tap(500, 600, delay_after=(0.0, 0.0))
