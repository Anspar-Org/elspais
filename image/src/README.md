# DAG / lowercase-e icon source

`generate_svg.py` generates the canonical SVG. All graph paths use the same
stroke width. The lower branch ends at a separate node to strengthen the open
lowercase-e silhouette.

Generate everything with:

    python generate_svg.py
    python render.py

Dependencies for rendering:

    pip install cairosvg pillow

The renderer rasterizes at 8x target resolution and downsamples using Pillow's
LANCZOS windowed-sinc filter. It writes 16, 32, 48, 64, 128, 180, 192, 256,
and 512 px PNGs into the parent `image/` directory.

Edit `NODE_R`, `STROKE`, colors, or path/node coordinates in generate_svg.py
to tune the mark.
