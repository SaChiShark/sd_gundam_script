"""Unit tests for DailyCultivationTask."""
import numpy as np
import pytest

from core.device import Device, DeviceConfig
from core.state_machine import StateMachine
from core.vision import Vision
from tasks.daily_cultivation import DailyCultivationTask


class MockDevice(Device):
    def __init__(self):
        super().__init__(DeviceConfig())
        self._connected = True
        self.taps = []

    def screencap(self) -> np.ndarray:
        return np.zeros((1080, 1920, 3), dtype=np.uint8)

    def tap(self, x, y, radius=5, delay_after=(0, 0)):
        self.taps.append((x, y))

    def tap_rect(self, rect, padding_ratio=0.2, delay_after=(0, 0)):
        x, y, w, h = rect
        self.taps.append((x + w // 2, y + h // 2))

    def random_sleep(self, min_s=0, max_s=0):
        pass


def test_daily_cultivation_initialization():
    dev = MockDevice()
    task = DailyCultivationTask(dev)
    assert task.name == "daily_cultivation"
    assert len(task.CATEGORIES) == 4
    assert task.CATEGORIES[0] == "CAPITAL"
    assert task.CATEGORIES[1] == "單位培育"
    assert task.CATEGORIES[2] == "角色培育"
    assert task.CATEGORIES[3] == "支援人員培育"


def test_skip_button_color_detection():
    dev = MockDevice()
    task = DailyCultivationTask(dev)

    # Synthetic enabled button frame (bright blue at (1685, 685))
    frame_enabled = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame_enabled[685, 1685] = [200, 80, 20]  # B=200, G=80, R=20
    assert task.is_skip_button_enabled(frame_enabled) is True

    # Synthetic disabled button frame (dark)
    frame_disabled = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame_disabled[685, 1685] = [60, 20, 10]   # B=60, G=20, R=10
    assert task.is_skip_button_enabled(frame_disabled) is False


def test_highest_difficulty_gold_detection():
    dev = MockDevice()
    task = DailyCultivationTask(dev)

    # Frame with no gold stars
    blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    ready, msg = task.check_highest_difficulty_ready(blank_frame)
    assert ready is False
    assert "not show" in msg.lower()

    # Frame with gold pixels in star region (y: 460-570, x: 780-920)
    # BGR for gold/yellow: B=50, G=200, R=255
    star_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    star_frame[480:520, 800:850] = [50, 200, 255]
    ready_gold, msg_gold = task.check_highest_difficulty_ready(star_frame)
    assert ready_gold is True
    assert "LV6 is unlocked" in msg_gold
