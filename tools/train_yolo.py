"""Train YOLOv11-UI on the annotated dataset and export to ONNX.

Exports to:
- models/yolo11n_ui.pt
- models/yolo11n_ui.onnx (Inference via ONNX Runtime DirectML on RTX 4070 SUPER)
"""
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger
from ultralytics import YOLO

DATA_YAML = os.path.join(PROJECT_ROOT, "datasets", "gundam_ui", "data.yaml")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")


def train_and_export(epochs: int = 30, imgsz: int = 640) -> str:
    """Train YOLOv11n and export to ONNX for GPU DirectML inference."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    logger.info(f"Starting YOLOv11-UI training with data: {DATA_YAML}...")

    # Load baseline nano model
    model = YOLO("yolo11n.pt")

    # Train for lightweight UI element localization
    results = model.train(
        data=DATA_YAML,
        epochs=epochs,
        imgsz=imgsz,
        batch=8,
        workers=2,
        project=os.path.join(PROJECT_ROOT, "runs"),
        name="gundam_ui_train",
        exist_ok=True,
        verbose=True
    )

    # Save best pt to models/
    best_pt = os.path.join(PROJECT_ROOT, "runs", "gundam_ui_train", "weights", "best.pt")
    target_pt = os.path.join(MODELS_DIR, "yolo11n_ui.pt")
    if os.path.exists(best_pt):
        shutil.copy2(best_pt, target_pt)
        logger.success(f"Saved trained PyTorch weights to: {target_pt}")
    else:
        # Fallback to last.pt
        last_pt = os.path.join(PROJECT_ROOT, "runs", "gundam_ui_train", "weights", "last.pt")
        if os.path.exists(last_pt):
            shutil.copy2(last_pt, target_pt)
            logger.success(f"Saved trained PyTorch weights to: {target_pt}")

    # Export to ONNX
    logger.info("Exporting trained model to ONNX format...")
    trained_model = YOLO(target_pt)
    onnx_path = trained_model.export(format="onnx", imgsz=imgsz, dynamic=False)

    target_onnx = os.path.join(MODELS_DIR, "yolo11n_ui.onnx")
    if os.path.exists(onnx_path) and os.path.abspath(onnx_path) != os.path.abspath(target_onnx):
        shutil.copy2(onnx_path, target_onnx)
        logger.success(f"Exported ONNX model to: {target_onnx}")
    else:
        logger.success(f"ONNX model ready at: {target_onnx}")

    logger.success("YOLOv11-UI model training and export completed successfully!")
    return target_onnx


if __name__ == "__main__":
    train_and_export(epochs=40)
