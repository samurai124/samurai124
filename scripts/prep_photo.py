#!/usr/bin/env python3
"""
Prepare a portrait photo or hero image for clean ASCII conversion:
  1. Detect transparency / alpha channel or remove background (rembg with OpenCV fallback)
  2. Boost LOCAL contrast (CLAHE) and sharpen contours so edges and details pop
  3. Composite onto pure white so the background reads as blank (white -> spaces in ASCII ramp)

Output: source-prepped.png (grayscale), consumed by make_ascii_svg.py.
Run whenever the source photo changes; the ascii SVG itself is static.

    python scripts/prep_photo.py [input_image] [output.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))

# Look for candidate inputs if not provided
candidates = [
    os.path.join(HERE, "..", "source-photo.png"),
    os.path.join(HERE, "..", "source-photo.jpg"),
    os.path.join(HERE, "..", "source-photo.jpeg"),
    r"C:\Users\Pc\Desktop\My_portfolio\src\assets\hero.png"
]

INP = sys.argv[1] if len(sys.argv) > 1 else None
if not INP:
    for c in candidates:
        if os.path.exists(c):
            INP = c
            break

OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

if not INP or not os.path.exists(INP):
    print(f"Error: no valid source image found.", file=sys.stderr)
    sys.exit(1)

print(f"Processing source image: {INP}")

# Load image with PIL and convert to RGBA
img_pil = Image.open(INP)
rgba = img_pil.convert("RGBA")
rgb = np.array(rgba.convert("RGB"))
alpha = np.array(rgba.split()[-1])

has_alpha = (int(np.min(alpha)) < 240)

if has_alpha:
    print("Detected transparent image (alpha mask present). Isolating background cleanly...")
else:
    print("Image has no transparent background. Attempting subject extraction...")
    cut_succeeded = False
    try:
        from rembg import remove
        print("Using rembg for background removal...")
        rgba = remove(img_pil.convert("RGBA"))
        rgb = np.array(rgba.convert("RGB"))
        alpha = np.array(rgba.split()[-1])
        cut_succeeded = True
    except Exception as e:
        print(f"rembg unavailable or skipped ({e}); using OpenCV segmentation...")

    if not cut_succeeded:
        img_bgr = cv2.imread(INP)
        h, w = img_bgr.shape[:2]
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        mask_init = np.zeros((h, w), np.uint8)
        rect = (int(w * 0.05), int(h * 0.05), int(w * 0.9), int(h * 0.9))
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(img_bgr, mask_init, rect, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_RECT)
            alpha = np.where((mask_init == 2) | (mask_init == 0), 0, 255).astype(np.uint8)
        except Exception:
            alpha = np.full((h, w), 255, dtype=np.uint8)

# Convert RGB to Grayscale
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

# Bilateral smoothing + CLAHE contrast boost
filtered = cv2.bilateralFilter(gray, 5, 50, 50)
clahe = cv2.createCLAHE(clipLimit=3.2, tileGridSize=(6, 6))
contrast = clahe.apply(filtered)

# Edge enhancement to ensure thin lines and bevel contours print cleanly
edges = cv2.Canny(gray, 20, 80)
enhanced = np.where(edges > 0, np.minimum(contrast, 35), contrast)

# Paste onto pure white background using alpha mask
mask = (alpha.astype(np.float32) / 255.0)
mask = cv2.GaussianBlur(mask, (0, 0), 0.8)
out = enhanced.astype(np.float32) * mask + 255.0 * (1.0 - mask)
out = np.clip(out, 0, 255).astype(np.uint8)

Image.fromarray(out, mode="L").save(OUT)
print(f"Wrote prepped image: {OUT} ({out.shape[1]}x{out.shape[0]})")
