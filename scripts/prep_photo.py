#!/usr/bin/env python3
"""
Prepare a portrait photo for clean ASCII conversion:
  1. remove the background (rembg with fallback) so the subject is isolated
  2. boost LOCAL contrast (CLAHE) so a flatly-lit face gains highlights and
     shadows -- this is what turns a dark blob into a recognizable face
  3. composite the subject onto pure white so the background reads as blank
     (white -> spaces in the ascii ramp)

Output: source-prepped.png (grayscale), consumed by make_ascii_svg.py.
Run once whenever the source photo changes; the ascii SVG itself is static.

    python scripts/prep_photo.py <input.jpg> [output.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-photo.jpg")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

if not os.path.exists(INP):
    # Try alternate extensions or fallback paths
    for alt in ["source-photo.png", "source-photo.jpeg"]:
        alt_path = os.path.join(HERE, "..", alt)
        if os.path.exists(alt_path):
            INP = alt_path
            break

if not os.path.exists(INP):
    print(f"Error: input photo not found at {INP}", file=sys.stderr)
    sys.exit(1)

print(f"Processing photo: {INP}")

# 1. Background removal
cut_succeeded = False
try:
    from rembg import remove
    print("Using rembg for precise background removal...")
    img_pil = Image.open(INP).convert("RGBA")
    cut = remove(img_pil)
    rgb = np.array(cut.convert("RGB"))
    alpha = np.array(cut.split()[-1])
    cut_succeeded = True
except Exception as e:
    print(f"rembg not available or failed ({e}); falling back to OpenCV segmentation...")

if not cut_succeeded:
    img_bgr = cv2.imread(INP)
    h, w = img_bgr.shape[:2]
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    
    # Simple grabcut fallback or center oval mask
    mask_init = np.zeros((h, w), np.uint8)
    rect = (int(w * 0.05), int(h * 0.05), int(w * 0.9), int(h * 0.9))
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_bgr, mask_init, rect, bgdModel, fgdModel, 3, cv2.GC_INIT_WITH_RECT)
        alpha = np.where((mask_init == 2) | (mask_init == 0), 0, 255).astype(np.uint8)
    except Exception:
        # Fallback to full image if grabCut fails
        alpha = np.full((h, w), 255, dtype=np.uint8)

# 2. Local-contrast the luminance (CLAHE)
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
gray = clahe.apply(gray)

# Touch of global lift so face tones map nicely to the sparse end of the ramp
gray = cv2.convertScaleAbs(gray, alpha=1.05, beta=18)

# 3. Paste onto white using the alpha mask
mask = (alpha.astype(np.float32) / 255.0)
mask = cv2.GaussianBlur(mask, (0, 0), 1.0)
out = gray.astype(np.float32) * mask + 255.0 * (1.0 - mask)
out = np.clip(out, 0, 255).astype(np.uint8)

Image.fromarray(out, mode="L").save(OUT)
print("wrote", OUT, out.shape)
