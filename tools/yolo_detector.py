"""YOLO-based UI Element Detector and Localization Engine.

Provides deterministic, sub-millisecond object detection for game UI elements
leveraging local GPU acceleration (NVIDIA RTX 4070 SUPER via DirectML / CUDA).
Eliminates mental coordinate guesswork and VLM hallucination.
"""
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

# Default paths
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
DEFAULT_WEIGHTS_PT = os.path.join(MODEL_DIR, "yolo11n_ui.pt")
DEFAULT_WEIGHTS_ONNX = os.path.join(MODEL_DIR, "yolo11n_ui.onnx")


@dataclass
class UIElement:
    """Detected UI Element bounding box and metadata."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2

    @property
    def center(self) -> Tuple[int, int]:
        """Return (cx, cy) center point of bounding box."""
        x1, y1, x2, y2 = self.bbox
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


class YOLOUIDetector:
    """
    High-performance YOLO UI Element Detector.
    Supports ONNX Runtime DirectML (RTX 4070 SUPER) and PyTorch Ultralytics.
    """

    DEFAULT_CLASSES = [
        "btn_accept",        # 承接按鈕
        "btn_challenge",     # 挑戰按鈕
        "btn_report",        # 報告按鈕
        "btn_deliver",       # 交付按鈕
        "btn_confirm",       # 確認 / 執行按鈕
        "btn_cancel",        # 取消按鈕
        "btn_skip",          # 略過對話按鈕
        "btn_trash",         # 垃圾桶捨棄按鈕
        "btn_close",         # 關閉視窗按鈕
        "unit_r",            # 開發樹 / 列表 R 機體
        "unit_sr",           # 開發樹 / 列表 SR 機體
        "unit_ssr",          # 開發樹 / 列表 SSR 機體
        "badge_rarity",      # 機體階級標籤
        "modal_card",        # 浮動視窗主體
    ]

    def __init__(
        self,
        weights_path: Optional[str] = None,
        conf_threshold: float = 0.55,
        use_directml: bool = True
    ):
        self.conf_threshold = conf_threshold
        self.use_directml = use_directml
        self.weights_path = weights_path or (
            DEFAULT_WEIGHTS_ONNX if os.path.exists(DEFAULT_WEIGHTS_ONNX) else DEFAULT_WEIGHTS_PT
        )
        self.model = None
        self.ort_session = None
        self._init_engine()

    def _init_engine(self) -> None:
        """Initialize ONNX Runtime or Ultralytics model."""
        if not os.path.exists(self.weights_path):
            logger.warning(
                f"[YOLOUIDetector] Weights not found at '{self.weights_path}'. "
                f"Detector will operate in Fallback/Pass-through mode until weights are trained."
            )
            return

        if self.weights_path.endswith(".onnx"):
            try:
                import onnxruntime as ort
                providers = ['DmlExecutionProvider', 'CPUExecutionProvider'] if self.use_directml else ['CPUExecutionProvider']
                self.ort_session = ort.InferenceSession(self.weights_path, providers=providers)
                logger.success(f"[YOLOUIDetector] Loaded ONNX model with providers: {self.ort_session.get_providers()}")
            except Exception as e:
                logger.error(f"[YOLOUIDetector] Failed to initialize ONNX Runtime: {e}")
        else:
            try:
                from ultralytics import YOLO
                self.model = YOLO(self.weights_path)
                logger.success(f"[YOLOUIDetector] Loaded PyTorch YOLO model: {self.weights_path}")
            except Exception as e:
                logger.error(f"[YOLOUIDetector] Failed to load PyTorch YOLO model: {e}")

    def is_ready(self) -> bool:
        """Return True if model is loaded and ready for GPU inference."""
        return self.ort_session is not None or self.model is not None

    def detect(self, frame: np.ndarray, conf: Optional[float] = None) -> List[UIElement]:
        """
        Run GPU detection on a BGR frame (1920x1080 baseline).
        Returns list of detected UI elements sorted by confidence.
        """
        threshold = conf or self.conf_threshold
        if not self.is_ready():
            return []

        elements: List[UIElement] = []

        if self.model is not None:
            results = self.model.predict(source=frame, conf=threshold, verbose=False)
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    score = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v.item()) for v in box.xyxy[0]]
                    cls_name = self.model.names.get(cls_id, f"class_{cls_id}")
                    elements.append(UIElement(
                        class_id=cls_id,
                        class_name=cls_name,
                        confidence=score,
                        bbox=(x1, y1, x2, y2)
                    ))

        return sorted(elements, key=lambda e: e.confidence, reverse=True)

    def find_target(
        self,
        frame: np.ndarray,
        target_class: str,
        roi: Optional[Tuple[int, int, int, int]] = None,
        conf: Optional[float] = None
    ) -> Optional[UIElement]:
        """
        Locate the best matching UI element for a given target class.
        Optionally bounded within a Region of Interest (x, y, w, h).
        """
        elements = self.detect(frame, conf=conf)
        for elem in elements:
            if elem.class_name.lower() == target_class.lower():
                if roi:
                    rx, ry, rw, rh = roi
                    cx, cy = elem.center
                    if not (rx <= cx <= rx + rw and ry <= cy <= ry + rh):
                        continue
                return elem
        return None
