"""Unit tests for WarshipCruiseTask."""
import numpy as np
import pytest

from core.device import Device, DeviceConfig
from core.vision import Vision
from tasks.warship_cruise import WarshipCruiseTask


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


def test_warship_cruise_initialization():
    dev = MockDevice()
    task = WarshipCruiseTask(dev)
    assert task.name == "warship_cruise"
    assert task.COORD_CRUISE_BANNER == (160, 240)
    assert task.COORD_COLLECT_ALL == (1600, 830)
    assert task.COORD_MODAL_OK == (960, 990)
    assert task.COORD_NAV_HOME == (100, 1030)


def test_is_collect_available_detection():
    dev = MockDevice()
    task = WarshipCruiseTask(dev)

    # Empty frame should not match active collect all template
    empty_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert task.is_collect_available(empty_frame) is False


def test_is_on_cruise_screen_detection():
    dev = MockDevice()
    task = WarshipCruiseTask(dev)

    empty_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert task._is_on_cruise_screen(empty_frame) is False


def test_is_on_base_screen_detection():
    dev = MockDevice()
    task = WarshipCruiseTask(dev)

    empty_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert task._is_on_base_screen(empty_frame) is False

