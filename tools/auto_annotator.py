"""Automated Pseudo-Labeling Tool for SD Gundam UI Elements.

Leverages existing RapidOCR text bounding boxes and OpenCV template matching
to bootstrap high-quality YOLO annotations from real game screenshots.
Generates standard YOLO format (.txt) labels normalized to [0, 1].
"""
import os
import shutil
import sys
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import cv2
import numpy as np
from loguru import logger
from rapidocr_onnxruntime import RapidOCR

from core.vision import Vision
DATASET_DIR = os.path.join(PROJECT_ROOT, "datasets", "gundam_ui")
RAW_DIR = os.path.join(DATASET_DIR, "raw_to_label")
IMAGES_TRAIN = os.path.join(DATASET_DIR, "images", "train")
LABELS_TRAIN = os.path.join(DATASET_DIR, "labels", "train")
IMAGES_VAL = os.path.join(DATASET_DIR, "images", "val")
LABELS_VAL = os.path.join(DATASET_DIR, "labels", "val")

# Class ID mapping matching data.yaml
CLASS_MAP = {
    "btn_accept": 0,
    "btn_challenge": 1,
    "btn_report": 2,
    "btn_deliver": 3,
    "btn_confirm": 4,
    "btn_cancel": 5,
    "btn_skip": 6,
    "btn_trash": 7,
    "btn_close": 8,
    "unit_r": 9,
    "unit_sr": 10,
    "unit_ssr": 11,
    "badge_rarity": 12,
    "modal_card": 13,
}


class AutoAnnotator:
    """Bootstrap dataset with deterministic OCR and CV rules."""

    def __init__(self):
        self.ocr = RapidOCR()
        self.vision = Vision()

    @staticmethod
    def to_yolo_bbox(
        box: Tuple[int, int, int, int],
        img_w: int,
        img_h: int
    ) -> Tuple[float, float, float, float]:
        """Convert (x, y, w, h) to normalized (cx, cy, nw, nh)."""
        x, y, w, h = box
        cx = (x + w / 2) / img_w
        cy = (y + h / 2) / img_h
        nw = w / img_w
        nh = h / img_h
        return cx, cy, nw, nh

    def annotate_frame(self, frame: np.ndarray) -> List[Tuple[int, float, float, float, float]]:
        """Extract labeled bounding boxes from a single frame."""
        h, w = frame.shape[:2]
        annotations: List[Tuple[int, float, float, float, float]] = []

        # 1. OCR Extraction
        res, _ = self.ocr(frame)
        if res:
            for box, text, score in res:
                if score < 0.65:
                    continue
                bx1, by1 = int(box[0][0]), int(box[0][1])
                bx2, by2 = int(box[2][0]), int(box[2][1])
                bw = bx2 - bx1
                bh = by2 - by1
                cx = (bx1 + bx2) // 2
                cy = (by1 + by2) // 2

                # Detect Buttons by Text and Spatial Anchors
                # 承接
                if "承接" in text and cx > 1300 and cy > 700:
                    btn_box = (max(0, bx1 - 60), max(0, by1 - 20), bw + 120, bh + 40)
                    annotations.append((CLASS_MAP["btn_accept"], *self.to_yolo_bbox(btn_box, w, h)))

                # 挑戰
                elif "挑戰" in text and cx > 1300 and cy > 700:
                    btn_box = (max(0, bx1 - 60), max(0, by1 - 20), bw + 120, bh + 40)
                    annotations.append((CLASS_MAP["btn_challenge"], *self.to_yolo_bbox(btn_box, w, h)))

                # 報告
                elif "報告" in text and cx > 1300 and cy > 700:
                    btn_box = (max(0, bx1 - 60), max(0, by1 - 20), bw + 120, bh + 40)
                    annotations.append((CLASS_MAP["btn_report"], *self.to_yolo_bbox(btn_box, w, h)))

                # 交付
                elif "交付" in text and cx > 1000 and cy > 700:
                    btn_box = (max(0, bx1 - 60), max(0, by1 - 20), bw + 120, bh + 40)
                    annotations.append((CLASS_MAP["btn_deliver"], *self.to_yolo_bbox(btn_box, w, h)))

                # 執行開發
                elif "執行開發" in text and cy > 900:
                    btn_box = (max(0, bx1 - 40), max(0, by1 - 15), bw + 80, bh + 30)
                    annotations.append((CLASS_MAP["btn_confirm"], *self.to_yolo_bbox(btn_box, w, h)))

                # 執行 (彈窗確認 / 執行開發 / 決定)
                elif any(k in text for k in ["執行", "確定", "確認", "決定"]) and cy > 650:
                    btn_box = (max(0, bx1 - 50), max(0, by1 - 20), bw + 100, bh + 40)
                    annotations.append((CLASS_MAP["btn_confirm"], *self.to_yolo_bbox(btn_box, w, h)))

                # 略過
                elif any(k in text.upper() for k in ["略過", "SKIP"]) and (cx > 1500 or cy < 200):
                    btn_box = (max(0, bx1 - 20), max(0, by1 - 10), bw + 40, bh + 20)
                    annotations.append((CLASS_MAP["btn_skip"], *self.to_yolo_bbox(btn_box, w, h)))

                # 取消 / 放棄
                elif any(k in text for k in ["取消", "放棄"]) and cy > 650:
                    btn_box = (max(0, bx1 - 40), max(0, by1 - 15), bw + 80, bh + 30)
                    annotations.append((CLASS_MAP["btn_cancel"], *self.to_yolo_bbox(btn_box, w, h)))

                # 關閉
                elif "關閉" in text:
                    btn_box = (max(0, bx1 - 30), max(0, by1 - 15), bw + 60, bh + 30)
                    annotations.append((CLASS_MAP["btn_close"], *self.to_yolo_bbox(btn_box, w, h)))

                # 開發樹上的 R 機體 (利用 X0/X1/W-01 等標籤向上定位機體本體)
                elif any(k in text for k in ["X0", "X1", "x0", "x1", "W-01", "OZ-", "MS-"]) and 400 < cx < 1200 and 450 < cy < 750:
                    badge_box = (bx1 - 30, by1 - 5, bw + 40, bh + 10)
                    annotations.append((CLASS_MAP["badge_rarity"], *self.to_yolo_bbox(badge_box, w, h)))
                    # 機體節點 (向上偏移 ~115px)
                    unit_box = (cx - 75, cy - 180, 150, 150)
                    annotations.append((CLASS_MAP["unit_r"], *self.to_yolo_bbox(unit_box, w, h)))

        # 2. Template Matching for Trash Can
        trash_match = self.vision.match_template(frame, "assets/buttons/btn_trash_can.png", threshold=0.75)
        if trash_match:
            annotations.append((CLASS_MAP["btn_trash"], *self.to_yolo_bbox(trash_match.rect, w, h)))

        # 3. Template Matching for Blue Close Button
        close_match = self.vision.match_template(frame, "assets/buttons/btn_close_blue.png", threshold=0.78)
        if close_match:
            annotations.append((CLASS_MAP["btn_close"], *self.to_yolo_bbox(close_match.rect, w, h)))

        return annotations

    def run_batch_annotation(self) -> int:
        """Process all raw candidate screenshots and split into train/val sets."""
        if not os.path.exists(RAW_DIR):
            logger.error(f"Raw directory does not exist: {RAW_DIR}")
            return 0

        # Clean old train and val splits
        for d in [IMAGES_TRAIN, LABELS_TRAIN, IMAGES_VAL, LABELS_VAL]:
            if os.path.exists(d):
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
            os.makedirs(d, exist_ok=True)

        files = [f for f in os.listdir(RAW_DIR) if f.lower().endswith((".png", ".jpg"))]
        logger.info(f"Starting auto-annotation for {len(files)} candidate screenshots...")

        total_annotated = 0
        for idx, filename in enumerate(files):
            img_path = os.path.join(RAW_DIR, filename)
            frame = cv2.imread(img_path)
            if frame is None:
                continue

            anns = self.annotate_frame(frame)
            if not anns:
                continue

            # 80/20 train/val split
            is_val = (idx % 5 == 0)
            target_img_dir = IMAGES_VAL if is_val else IMAGES_TRAIN
            target_lbl_dir = LABELS_VAL if is_val else LABELS_TRAIN

            base_name = os.path.splitext(filename)[0]
            dst_img = os.path.join(target_img_dir, f"{base_name}.png")
            dst_lbl = os.path.join(target_lbl_dir, f"{base_name}.txt")

            shutil.copy2(img_path, dst_img)
            with open(dst_lbl, "w", encoding="utf-8") as f:
                for cls_id, cx, cy, nw, nh in anns:
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")

            total_annotated += 1

        logger.success(f"Successfully auto-annotated and partitioned {total_annotated} images!")
        return total_annotated


if __name__ == "__main__":
    annotator = AutoAnnotator()
    annotator.run_batch_annotation()
