"""YOLO Dataset Preparation and Training Helper for SD Gundam UI.

Assists in collecting training samples from captures/ and scaffolding data.yaml
for training on NVIDIA RTX 4070 SUPER.
"""
import os
import shutil
from typing import List

from loguru import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(PROJECT_ROOT, "datasets", "gundam_ui")
CAPTURES_DIR = os.path.join(PROJECT_ROOT, "captures")


def scaffold_dataset_structure() -> None:
    """Create standard YOLO directory hierarchy."""
    for split in ["train", "val"]:
        os.makedirs(os.path.join(DATASET_DIR, "images", split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, "labels", split), exist_ok=True)

    data_yaml_path = os.path.join(DATASET_DIR, "data.yaml")
    yaml_content = f"""path: {DATASET_DIR.replace('\\', '/')}
train: images/train
val: images/val

names:
  0: btn_accept
  1: btn_challenge
  2: btn_report
  3: btn_deliver
  4: btn_confirm
  5: btn_cancel
  6: btn_skip
  7: btn_trash
  8: btn_close
  9: unit_r
  10: unit_sr
  11: unit_ssr
  12: badge_rarity
  13: modal_card
"""
    with open(data_yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    logger.success(f"[DatasetBuilder] Scaffolded YOLO dataset directory at: {DATASET_DIR}")
    logger.info(f"[DatasetBuilder] Created config at: {data_yaml_path}")


def populate_raw_samples(max_samples: int = 250) -> int:
    """Collect unique screenshots from captures/ into raw labeling directory."""
    raw_dir = os.path.join(DATASET_DIR, "raw_to_label")
    os.makedirs(raw_dir, exist_ok=True)

    # Prioritize UI interaction captures
    priority_keywords = [
        "req", "accept", "report", "dev", "modal", "slot", "confirm",
        "trash", "deliver", "cancel", "tree", "dialogue", "after_"
    ]

    all_files = []
    for root, _, files in os.walk(CAPTURES_DIR):
        for f in files:
            if f.lower().endswith((".png", ".jpg")):
                all_files.append(os.path.join(root, f))

    # Sort so priority images come first
    def priority_score(path: str) -> int:
        name = os.path.basename(path).lower()
        score = sum(1 for kw in priority_keywords if kw in name)
        return score

    all_files.sort(key=priority_score, reverse=True)

    collected = 0
    for src in all_files:
        name = os.path.basename(src)
        dst = os.path.join(raw_dir, f"sample_{collected:03d}_{name}")
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            collected += 1
            if collected >= max_samples:
                break

    logger.success(f"[DatasetBuilder] Collected {collected} candidate screenshots to: {raw_dir}")
    return collected


if __name__ == "__main__":
    scaffold_dataset_structure()
    populate_raw_samples(max_samples=250)
