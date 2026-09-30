"""Computer Vision module for template matching and pixel analysis."""
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from loguru import logger


@dataclass
class MatchResult:
    """Represents a successful template match."""
    x: int
    y: int
    w: int
    h: int
    confidence: float

    @property
    def center(self) -> Tuple[int, int]:
        """Returns the (center_x, center_y) of the matched area."""
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, w, h)."""
        return self.x, self.y, self.w, self.h


class Vision:
    """Provides OpenCV-based visual recognition routines."""

    def __init__(self, template_cache: bool = True):
        self.template_cache = template_cache
        self._cached_templates = {}

    def load_template(self, template_path: str) -> np.ndarray:
        """Load template image from disk with caching support."""
        if self.template_cache and template_path in self._cached_templates:
            return self._cached_templates[template_path]

        if not os.path.isfile(template_path):
            raise FileNotFoundError(f"Template image not found: {template_path}")

        # Load with cv2.imread
        tmpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if tmpl is None:
            raise ValueError(f"Failed to read image at: {template_path}")

        if self.template_cache:
            self._cached_templates[template_path] = tmpl

        return tmpl

    def match_template(
        self,
        frame: np.ndarray,
        template: Union[str, np.ndarray],
        threshold: float = 0.82
    ) -> Optional[MatchResult]:
        """
        Locate a template within the frame using normalized cross-correlation.

        Args:
            frame: Target BGR screenshot.
            template: Either path to template image or pre-loaded BGR numpy array.
            threshold: Minimum correlation score (0.0 - 1.0).

        Returns:
            MatchResult with coordinates and confidence if found, else None.
        """
        if isinstance(template, str):
            tmpl_img = self.load_template(template)
        else:
            tmpl_img = template

        fh, fw = frame.shape[:2]
        th, tw = tmpl_img.shape[:2]

        if th > fh or tw > fw:
            logger.warning(f"Template size ({tw}x{th}) exceeds frame size ({fw}x{fh})")
            return None

        # Execute template matching
        res = cv2.matchTemplate(frame, tmpl_img, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            logger.debug(f"Match found at {max_loc} with confidence {max_val:.3f} (threshold {threshold})")
            return MatchResult(
                x=max_loc[0],
                y=max_loc[1],
                w=tw,
                h=th,
                confidence=float(max_val)
            )

        return None

    def match_all(
        self,
        frame: np.ndarray,
        template: Union[str, np.ndarray],
        threshold: float = 0.82,
        min_distance: int = 15
    ) -> List[MatchResult]:
        """
        Find multiple non-overlapping occurrences of a template in the frame.
        """
        if isinstance(template, str):
            tmpl_img = self.load_template(template)
        else:
            tmpl_img = template

        fh, fw = frame.shape[:2]
        th, tw = tmpl_img.shape[:2]
        if th > fh or tw > fw:
            return []

        res = cv2.matchTemplate(frame, tmpl_img, cv2.TM_CCOEFF_NORMED)
        locs = np.where(res >= threshold)

        matches: List[MatchResult] = []
        for pt in zip(*locs[::-1]):
            x, y = int(pt[0]), int(pt[1])
            conf = float(res[y, x])

            # Check overlap with existing matches
            overlap = False
            for m in matches:
                if abs(m.x - x) < min_distance and abs(m.y - y) < min_distance:
                    overlap = True
                    break

            if not overlap:
                matches.append(MatchResult(x=x, y=y, w=tw, h=th, confidence=conf))

        return matches

    def check_pixel_bgr(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        expected_bgr: Tuple[int, int, int],
        tolerance: int = 15
    ) -> bool:
        """
        Verify if the pixel at (x, y) matches the expected BGR color within tolerance.
        """
        h, w = frame.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return False

        b, g, r = frame[y, x]
        eb, eg, er = expected_bgr

        diff = abs(int(b) - eb) + abs(int(g) - eg) + abs(int(r) - er)
        return diff <= tolerance * 3
