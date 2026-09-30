"""Screen Capture & UI Inspector Utility."""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from loguru import logger

from core.config import AppConfig
from core.device import Device



def inspect_screen(crop: bool = False, crop_rect: str = None, save_as: str = None) -> None:
    """Capture current screen from connected device and save to disk."""
    config = AppConfig.load_from_file()
    device = Device(config.device)
    device.connect()

    logger.info("Capturing screen from emulator...")
    frame = device.screencap()
    h, w = frame.shape[:2]
    logger.success(f"Captured screen size: {w}x{h}")

    os.makedirs("captures", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    latest_path = Path("captures/latest_screen.png")
    archive_path = Path(f"captures/screen_{timestamp}.png")

    cv2.imwrite(str(latest_path), frame)
    cv2.imwrite(str(archive_path), frame)
    logger.info(f"Saved latest screen to: {latest_path.resolve()}")
    logger.info(f"Saved archive screen to: {archive_path.resolve()}")

    if crop and crop_rect and save_as:
        try:
            x, y, cw, ch = map(int, crop_rect.split(","))
            cropped = frame[y:y+ch, x:x+cw]
            save_path = Path(save_as)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(save_path), cropped)
            logger.success(f"Cropped template saved to: {save_path.resolve()} ({cw}x{ch})")
        except Exception as e:
            logger.error(f"Failed to crop rectangle '{crop_rect}': {e}")


def main():
    parser = argparse.ArgumentParser(description="SD Gundam Screen Inspector & Template Cropper")
    parser.add_argument("--crop", action="store_true", help="Crop a region from the captured frame")
    parser.add_argument("--rect", type=str, help="Crop coordinates: x,y,w,h (e.g. 100,200,80,40)")
    parser.add_argument("--save-as", type=str, help="Destination template file (e.g. assets/buttons/ok.png)")
    args = parser.parse_args()

    inspect_screen(crop=args.crop, crop_rect=args.rect, save_as=args.save_as)


if __name__ == "__main__":
    main()
