#!/usr/bin/env python3
"""Render at 8x, then downsample with Lanczos (windowed sinc)."""
from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image

# Favicon (16-48), small UI (64-128), touch/PWA icons (180, 192), and full size.
SIZES = (16, 32, 48, 64, 128, 180, 192, 256, 512)
SUPERSAMPLE = 8
here = Path(__file__).resolve().parent
svg_bytes = (here / "dag-e-icon.svg").read_bytes()
outdir = here.parent

for size in SIZES:
    hi = size * SUPERSAMPLE
    raw = cairosvg.svg2png(bytestring=svg_bytes, output_width=hi, output_height=hi)
    with Image.open(BytesIO(raw)).convert("RGBA") as image:
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        path = outdir / f"dag-e-icon-{size}x{size}.png"
        image.save(path, optimize=True)
        print("Wrote", path)
