#!/usr/bin/env python3
from pathlib import Path

SIZE = 512
BG = "#07346d"
FG = "#ffffff"
NODE_R = 27
STROKE = 24

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">
<defs>
  <marker id="arrow" markerWidth="12" markerHeight="12" refX="9" refY="6" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M 0 0 L 12 6 L 0 12 z" fill="{FG}"/>
  </marker>
</defs>
<rect x="8" y="8" width="496" height="496" rx="76" fill="{BG}"/>
<g fill="none" stroke="{FG}" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">
  <path d="M 105 250 C 112 125, 195 83, 286 86 C 371 89, 413 139, 415 216" marker-end="url(#arrow)"/>
  <path d="M 111 244 C 142 180, 190 146, 257 142" marker-end="url(#arrow)"/>
  <path d="M 115 250 L 250 250" marker-end="url(#arrow)"/>
  <path d="M 276 250 L 404 250" marker-end="url(#arrow)"/>
  <path d="M 108 263 C 132 355, 225 382, 326 370 C 366 365, 391 354, 414 340" marker-end="url(#arrow)"/>
</g>
<g fill="{FG}">
  <circle cx="105" cy="250" r="{NODE_R}"/>
  <circle cx="270" cy="140" r="{NODE_R}"/>
  <circle cx="263" cy="250" r="{NODE_R}"/>
  <circle cx="416" cy="250" r="{NODE_R}"/>
  <circle cx="431" cy="333" r="{NODE_R}"/>
</g>
</svg>
"""
(Path(__file__).resolve().parent / "dag-e-icon.svg").write_text(svg)
print("Wrote dag-e-icon.svg")
