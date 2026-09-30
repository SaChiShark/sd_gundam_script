"""Unit tests for Vision module using synthetic images."""
import cv2
import numpy as np
import pytest

from core.vision import Vision, MatchResult


def test_template_match_synthetic():
    """Verify that template matching finds an embedded target with high confidence."""
    vision = Vision(template_cache=False)

    # 1. Create a synthetic 1920x1080 background
    bg = np.zeros((1080, 1920, 3), dtype=np.uint8)
    bg[:] = (40, 40, 40)  # dark gray

    # 2. Create a synthetic 100x60 button
    button = np.zeros((60, 100, 3), dtype=np.uint8)
    button[:] = (0, 120, 255)  # orange button
    cv2.putText(button, "OK", (25, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    # 3. Paste button onto background at (500, 300)
    bg[300:360, 500:600] = button

    # 4. Perform match
    match = vision.match_template(bg, button, threshold=0.90)

    assert match is not None
    assert isinstance(match, MatchResult)
    assert match.x == 500
    assert match.y == 300
    assert match.w == 100
    assert match.h == 60
    assert match.confidence >= 0.99
    assert match.center == (550, 330)


def test_pixel_color_check():
    """Verify pixel BGR comparison logic."""
    vision = Vision()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[50, 50] = (255, 100, 50)  # BGR

    assert vision.check_pixel_bgr(frame, 50, 50, (255, 100, 50), tolerance=0)
    assert vision.check_pixel_bgr(frame, 50, 50, (250, 105, 55), tolerance=10)
    assert not vision.check_pixel_bgr(frame, 50, 50, (0, 0, 0), tolerance=10)
