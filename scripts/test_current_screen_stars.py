import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from core.vision import Vision
from rapidocr_onnxruntime import RapidOCR

def analyze_current_screen():
    v = Vision()
    ocr = RapidOCR()
    img = cv2.imread("captures/temp/current_screen.png")
    out = img.copy()

    # 1. Match SSR badges with calibrated threshold
    all_b = v.match_all(img, "assets/icons/badge_ssr.png", threshold=0.42, min_distance=40)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    ssr_matches = []
    for m in all_b:
        # Ignore top header area
        if m.center[1] < 120:
            continue
        crop = img[m.y : m.y + m.h, m.x : m.x + m.w]
        h_crop, w_crop = crop.shape[:2]
        if h_crop < 20 or w_crop < 20:
            continue
        r_mean = np.mean(crop[10 : h_crop - 10, 10 : w_crop - 10, 2])
        c_hsv = hsv[m.y : m.y + m.h, m.x : m.x + m.w]
        gold_px = np.sum((c_hsv[:, :, 0] >= 15) & (c_hsv[:, :, 0] <= 35) & (c_hsv[:, :, 1] >= 120) & (c_hsv[:, :, 2] >= 120))
        # SSR badge has distinct gold pixels >= 180 and red mean >= 110
        is_ssr = (r_mean >= 110 and gold_px >= 180)
        if is_ssr:
            ssr_matches.append(m)

    print(f"=== 當前畫面偵測到 {len(ssr_matches)} 個 SSR 機體 ===")

    for idx, m in enumerate(ssr_matches):
        bx, by, bw, bh = m.rect
        # Draw badge bounding box in orange
        cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 165, 255), 3)

        # 2. Check ownership pill (x0 or x1)
        pill_crop = img[by : by + bh, bx + bw : bx + bw + 90]
        pill_res, _ = ocr(pill_crop)
        pill_text = " ".join([r[1] for r in pill_res or []])
        owned_count = 0 if "0" in pill_text else 1
        cv2.rectangle(out, (bx + bw, by), (bx + bw + 90, by + bh), (0, 255, 255), 2)

        # 3. Check for 3 purple stars in ROI
        pad_x1 = max(0, bx - 10)
        pad_x2 = min(img.shape[1], bx + 220)
        pad_y1 = max(0, by - 70)
        pad_y2 = min(img.shape[0], by + 10)

        star_roi = img[pad_y1:pad_y2, pad_x1:pad_x2]
        purple_match = v.match_template(star_roi, "assets/icons/stars_3_purple.png", threshold=0.60)

        has_purple_3 = (purple_match is not None)
        star_conf = purple_match.confidence if purple_match else 0.0

        if has_purple_3:
            sx1 = pad_x1 + purple_match.x
            sy1 = pad_y1 + purple_match.y
            sx2 = sx1 + purple_match.w
            sy2 = sy1 + purple_match.h
            cv2.rectangle(out, (sx1, sy1), (sx2, sy2), (255, 0, 255), 3)
            cv2.putText(out, f"3 Purple Stars ({star_conf:.2f})", (sx1 - 30, sy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

        verdict = "已滿星 (紫3星，無需點入)" if has_purple_3 else ("未持有 (0星)" if owned_count == 0 else "需進強化查詢")
        print(f"機體 #{idx+1} [座標 {m.center}]: 持有標記='{pill_text}' (數量={owned_count}) | 紫三星={has_purple_3} (信心度={star_conf:.3f}) => 判定: {verdict}")
        cv2.putText(out, f"SSR #{idx+1}: {verdict}", (bx - 50, by + bh + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0) if has_purple_3 else (0, 0, 255), 2)

    cv2.imwrite("captures/temp/purple_star_detection_result.png", out)
    print("輸出標註圖檔至: captures/temp/purple_star_detection_result.png")

if __name__ == "__main__":
    analyze_current_screen()
