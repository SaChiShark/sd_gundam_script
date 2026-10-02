"""Unit tests for YOLOUIDetector and StateMachine Three-Tier Localization Pipeline."""
import os
import shutil
import cv2
import numpy as np
import pytest

from core.device import Device, DeviceConfig
from core.state_machine import StateMachine, NavigationCoords
from core.page_manager import PageType
from tools.yolo_detector import YOLOUIDetector, UIElement


class DummyDevice(Device):
    """Mock device for unit tests."""
    def __init__(self, frame: np.ndarray):
        super().__init__(DeviceConfig())
        self._connected = True
        self._frame = frame
        self.tapped_coords = []

    def screencap(self) -> np.ndarray:
        return self._frame.copy()

    def tap(self, x: int, y: int) -> None:
        self.tapped_coords.append((x, y))

    def random_sleep(self, min_s: float, max_s: float) -> None:
        pass


def test_yolo_detector_initialization():
    """Verify YOLOUIDetector initializes and loads ONNX or PyTorch weights."""
    detector = YOLOUIDetector()
    assert detector.is_ready()
    assert len(detector.class_names) >= 10
    assert "btn_accept" in detector.DEFAULT_CLASSES
    assert "btn_trash" in detector.DEFAULT_CLASSES
    assert "unit_r" in detector.DEFAULT_CLASSES


def test_yolo_detector_blank_frame():
    """Verify detector produces no hallucinations or crashes on blank frames."""
    detector = YOLOUIDetector()
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    elements = detector.detect(blank, conf=0.5)
    assert elements == []
    target = detector.find_target(blank, "btn_accept")
    assert target is None


def test_yolo_detector_real_capture_skip_button():
    """Verify real capture detection on dialogue skip button."""
    test_img_path = "captures/after_accept.png"
    if not os.path.exists(test_img_path):
        pytest.skip(f"Test image {test_img_path} not available.")

    detector = YOLOUIDetector()
    img = cv2.imread(test_img_path)
    target = detector.find_target(img, "btn_skip", conf=0.60)
    assert target is not None
    assert target.class_name == "btn_skip"
    assert target.confidence >= 0.70
    cx, cy = target.center
    assert 1700 <= cx <= 1850
    assert 30 <= cy <= 120


def test_state_machine_three_tier_fallback_and_guardrail(tmp_path):
    """Verify three-tier localization: fallback when target missing, guardrail when both fail."""
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    dev = DummyDevice(blank)
    fsm = StateMachine(dev)

    # 1. Level 2 Fallback Test: YOLO finds nothing on blank, falls back to anchor
    fallback_anchor = (1623, 800)
    res = fsm.locate_and_tap_target(
        target_class="btn_accept",
        fallback_anchor=fallback_anchor,
        timeout=1.0,
        action_name="test_fallback"
    )
    assert res is True
    assert len(dev.tapped_coords) == 1
    # Check tapped near fallback anchor with jitter (+/- 5px)
    tx, ty = dev.tapped_coords[0]
    assert abs(tx - fallback_anchor[0]) <= 5
    assert abs(ty - fallback_anchor[1]) <= 5

    # 2. Level 3 Guardrail Test: Neither YOLO nor anchor present -> must trigger guardrail
    res_fail = fsm.locate_and_tap_target(
        target_class="non_existent_element",
        fallback_anchor=None,
        action_name="test_guardrail"
    )
    assert res_fail is False
