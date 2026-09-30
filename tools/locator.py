"""Visual UI Element Locator and Click Verification Utility.

Provides automated, deterministic coordinate discovery, visual marking,
and frame-difference verification to eliminate manual coordinate guesswork.
"""
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from loguru import logger


class UILocator:
    """Automated coordinate discovery and click verification toolkit."""

    @staticmethod
    def mark_point(
        frame: np.ndarray,
        x: int,
        y: int,
        label: str = "Target",
        radius: int = 16,
        color: Tuple[int, int, int] = (0, 0, 255),
        save_marked_path: Optional[str] = None,
        save_zoom_path: Optional[str] = None,
        zoom_window: int = 150
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Draw an unmistakable crosshair marker at (x, y) and generate a 2x zoomed crop.

        Args:
            frame: Full BGR screenshot.
            x: X coordinate.
            y: Y coordinate.
            label: Text label to render near the marker.
            radius: Outer circle radius.
            color: BGR color tuple (default Red).
            save_marked_path: Optional path to save annotated full frame.
            save_zoom_path: Optional path to save 2x zoomed crop.
            zoom_window: Half-width/half-height of the zoom crop region.

        Returns:
            Tuple of (annotated_frame, zoomed_crop).
        """
        marked = frame.copy()
        cv2.circle(marked, (x, y), radius, color, 2)
        cv2.circle(marked, (x, y), 3, color, -1)
        cv2.line(marked, (x - radius - 15, y), (x + radius + 15, y), color, 2)
        cv2.line(marked, (x, y - radius - 15), (x, y + radius + 15), color, 2)
        cv2.putText(
            marked,
            f"{label} ({x}, {y})",
            (max(10, x - 80), max(30, y - radius - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2
        )

        h, w = frame.shape[:2]
        y1, y2 = max(0, y - zoom_window), min(h, y + zoom_window)
        x1, x2 = max(0, x - zoom_window), min(w, x + zoom_window)
        crop = marked[y1:y2, x1:x2]
        zoom_2x = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2), interpolation=cv2.INTER_NEAREST)

        if save_marked_path:
            cv2.imwrite(save_marked_path, marked)
            logger.info(f"Saved marked screenshot to: {save_marked_path}")
        if save_zoom_path:
            cv2.imwrite(save_zoom_path, zoom_2x)
            logger.info(f"Saved zoomed crop to: {save_zoom_path}")

        return marked, zoom_2x

    @staticmethod
    def detect_foreground_clusters(
        frame: np.ndarray,
        roi: Optional[Tuple[int, int, int, int]] = None,
        min_size: Tuple[int, int] = (30, 30),
        max_size: Tuple[int, int] = (400, 400)
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detect non-background interactive UI clusters (e.g. tech trees, icon grids).

        Args:
            frame: Full BGR screenshot.
            roi: Optional (x, y, w, h) to restrict search area.
            min_size: Minimum (w, h) bounding box.
            max_size: Maximum (w, h) bounding box.

        Returns:
            List of (x, y, w, h) bounding boxes.
        """
        search_frame = frame
        offset_x, offset_y = 0, 0
        if roi:
            rx, ry, rw, rh = roi
            search_frame = frame[ry:ry+rh, rx:rx+rw]
            offset_x, offset_y = rx, ry

        # Convert to HSV and detect high saturation/value foreground elements
        hsv = cv2.cvtColor(search_frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        fg_mask = (sat > 40) | (val > 180)

        contours, _ = cv2.findContours(fg_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results = []

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if min_size[0] <= w <= max_size[0] and min_size[1] <= h <= max_size[1]:
                results.append((x + offset_x, y + offset_y, w, h))

        # Sort top-to-bottom, left-to-right
        results = sorted(results, key=lambda b: (b[1] // 80, b[0]))
        return results

    @staticmethod
    def verify_click_effect(
        frame_before: np.ndarray,
        frame_after: np.ndarray,
        roi: Optional[Tuple[int, int, int, int]] = None,
        min_diff_percent: float = 1.0
    ) -> Tuple[bool, float]:
        """
        Calculate pixel difference percentage between two frames to verify if a tap produced UI state transition.

        Args:
            frame_before: Screenshot before click.
            frame_after: Screenshot after click.
            roi: Optional bounding box (x, y, w, h) to focus diff check.
            min_diff_percent: Minimum change percentage to consider click effective.

        Returns:
            Tuple of (is_effective, diff_percentage).
        """
        fb, fa = frame_before, frame_after
        if roi:
            x, y, w, h = roi
            fb = frame_before[y:y+h, x:x+w]
            fa = frame_after[y:y+h, x:x+w]

        # Convert to grayscale and compute absolute difference
        gray_b = cv2.cvtColor(fb, cv2.COLOR_BGR2GRAY)
        gray_a = cv2.cvtColor(fa, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray_b, gray_a)

        # Threshold pixels with significant luminance shift (>25)
        changed_pixels = np.count_nonzero(diff > 25)
        total_pixels = gray_b.shape[0] * gray_b.shape[1]
        diff_percent = (changed_pixels / total_pixels) * 100.0

        is_effective = diff_percent >= min_diff_percent
        logger.debug(f"Click effect verification: diff={diff_percent:.2f}% (effective={is_effective})")
        return is_effective, diff_percent
