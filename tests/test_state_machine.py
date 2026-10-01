"""Unit tests for StateMachine and Home Screen 3-Anchor verification."""
import numpy as np
import pytest

from core.device import Device, DeviceConfig
from core.state_machine import StateMachine, GameState, HomeAnchorROI
from core.vision import Vision


class DummyDevice(Device):
    """Mock device that returns synthetic frames."""
    def __init__(self):
        super().__init__(DeviceConfig())
        self._connected = True

    def screencap(self) -> np.ndarray:
        # Return a blank 1920x1080 frame
        return np.zeros((1080, 1920, 3), dtype=np.uint8)


def test_home_anchor_roi_constants():
    """Verify ROI coordinates are within 1920x1080 bounds."""
    for roi in [HomeAnchorROI.TOP_LEFT_LEVEL, HomeAnchorROI.TOP_RIGHT_STAMINA, HomeAnchorROI.BOTTOM_RIGHT_SORTIE]:
        x, y, w, h = roi
        assert x >= 0 and y >= 0
        assert x + w <= 1920
        assert y + h <= 1080


def test_state_machine_initial_unknown():
    """Verify state machine initializes in UNKNOWN state."""
    dev = DummyDevice()
    fsm = StateMachine(dev)
    assert fsm.current_state == GameState.UNKNOWN

    blank_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # Blank frame without templates should return False
    assert not fsm.is_home_screen(blank_frame)


def test_navigation_coords_within_bounds():
    """Verify all calibrated navigation coordinates fall inside 1920x1080."""
    from core.state_machine import NavigationCoords

    # Check bottom navigation bar
    for tab, (x, y) in NavigationCoords.BOTTOM_NAV.items():
        assert 0 <= x <= 1920, f"Tab {tab} x={x} out of bounds"
        assert 0 <= y <= 1080, f"Tab {tab} y={y} out of bounds"

    # Check back button
    bx, by = NavigationCoords.BACK_BUTTON
    assert 0 <= bx <= 1920 and 0 <= by <= 1080

    # Check slot cards
    for idx, (sx, sy) in enumerate(NavigationCoords.CHAR_REQ_SLOT_CARDS, start=1):
        assert 0 <= sx <= 1920 and 0 <= sy <= 1080, f"Slot {idx} out of bounds"

    # Check navigation arrows
    px, py = NavigationCoords.CHAR_REQ_ARROW_PREV
    nx, ny = NavigationCoords.CHAR_REQ_ARROW_NEXT
    assert 0 <= px <= 1920 and 0 <= py <= 1080
    assert 0 <= nx <= 1920 and 0 <= ny <= 1080

