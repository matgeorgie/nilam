"""Render genuine raw HouseGAN++ masks from the bundled sample graph.

Run with ``archai/.venv/bin/python scripts/render_housegan_sample.py`` from the
repository root. This deliberately bypasses Nilam's geometric validation so
the image shows the checkpoint's actual output, rather than a fallback plan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "archai/apps/api"))
from app.ml.engine import MLGenerativeLayoutEngine, ROOT as MODEL_ROOT  # noqa: E402


SAMPLE = MODEL_ROOT / "data/json/18477.json"
OUTPUT = ROOT / "docs/housegan-raw-sample.png"
ROOM_NAMES = ["Bedroom 1", "Kitchen", "Balcony", "Bedroom 2", "Bathroom", "Living room"]
COLORS = ["#687CA1", "#CF7954", "#8FAA74", "#A67FA9", "#C9A45F", "#658D88"]
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def model_output() -> np.ndarray:
    data = json.loads(SAMPLE.read_text())
    types = data["room_type"]
    nodes = torch.zeros(len(types), 18)
    for index, room_type in enumerate(types):
        nodes[index, room_type - 1] = 1
    edge_rooms = [set(room_ids) for room_ids in data["ed_rm"]]
    edges = torch.tensor(
        [
            [a, 1 if any(a in rooms and b in rooms for rooms in edge_rooms) else -1, b]
            for a in range(len(types))
            for b in range(a + 1, len(types))
        ],
        dtype=torch.long,
    )
    noise = torch.randn(len(types), 128, generator=torch.Generator().manual_seed(2301))
    given = torch.zeros(len(types), 2, 64, 64)
    given[:, 0] = -1
    torch.set_num_threads(2)
    engine = MLGenerativeLayoutEngine()
    if not engine.is_loaded:
        raise RuntimeError(f"HouseGAN++ checkpoint did not load: {engine.load_error}")
    with torch.inference_mode():
        return engine.model(noise, given, nodes, edges).cpu().numpy()


def draw() -> None:
    scores = model_output()
    masks = scores[:6] > 0  # Six rooms; the remaining sample nodes are door markers.
    occupied = masks.any(axis=0)
    ys, xs = np.where(occupied)
    x0, x1 = max(0, int(xs.min()) - 4), min(64, int(xs.max()) + 5)
    y0, y1 = max(0, int(ys.min()) - 4), min(64, int(ys.max()) + 5)
    crop = (x0, y0, x1, y1)

    canvas = Image.new("RGB", (1800, 1120), "white")
    pen = ImageDraw.Draw(canvas)
    title = ImageFont.truetype(BOLD, 48)
    section = ImageFont.truetype(BOLD, 27)
    body = ImageFont.truetype(FONT, 23)
    small = ImageFont.truetype(FONT, 20)
    pen.text((65, 48), "HouseGAN++ | actual checkpoint output", font=title, fill="#171717")
    pen.text((67, 112), "Bundled sample graph 18477  ·  seed 2301  ·  six room masks shown", font=body, fill="#555555")
    pen.line((65, 162, 1735, 162), fill="#B8B8B8", width=2)
    pen.text((67, 195), "Combined predicted masks", font=section, fill="#171717")
    pen.text((804, 195), "Individual room masks", font=section, fill="#171717")

    # A common crop preserves the relative positions of all model predictions.
    scale = 11
    composite = Image.new("RGB", (x1 - x0, y1 - y0), "#F2F2F2")
    for mask, color in zip(masks, COLORS):
        layer = Image.new("RGB", composite.size, color)
        alpha = Image.fromarray((mask.astype("uint8") * 255)).crop(crop)
        composite.paste(layer, mask=alpha)
    composite = composite.resize((composite.width * scale, composite.height * scale), Image.Resampling.NEAREST)
    canvas.paste(composite, (67, 255))
    pen.rectangle((66, 254, 68 + composite.width, 256 + composite.height), outline="#555555", width=2)
    pen.text((67, 850), "Colors distinguish overlapping predicted masks.", font=small, fill="#555555")

    cell_w, cell_h = 290, 285
    for index, (mask, name, color) in enumerate(zip(masks, ROOM_NAMES, COLORS)):
        col, row = index % 3, index // 3
        left, top = 803 + col * 310, 254 + row * 315
        pen.rectangle((left, top, left + cell_w, top + cell_h), outline="#777777", width=2)
        pen.rectangle((left + 13, top + 14, left + 36, top + 37), fill=color)
        pen.text((left + 46, top + 12), name, font=body, fill="#171717")
        tile = Image.new("RGB", (x1 - x0, y1 - y0), "#F2F2F2")
        alpha = Image.fromarray((mask.astype("uint8") * 255)).crop(crop)
        tile.paste(Image.new("RGB", tile.size, color), mask=alpha)
        tile = tile.resize((cell_w - 34, cell_h - 72), Image.Resampling.NEAREST)
        canvas.paste(tile, (left + 17, top + 54))
        pen.text((left + 17, top + cell_h - 27), f"{int(mask.sum())} positive pixels / 4096", font=small, fill="#555555")

    pen.line((65, 914, 1735, 914), fill="#B8B8B8", width=2)
    pen.text((67, 951), "What this is", font=section, fill="#171717")
    pen.text((67, 992), "Raw 64 × 64 per-room model predictions, thresholded at zero and zoomed for visibility.", font=body, fill="#333333")
    pen.text((67, 1027), "No walls, doors, dimensions, setbacks, or construction-ready geometry are generated here.", font=body, fill="#333333")
    pen.text((67, 1075), "Source: bundled HouseGAN++ checkpoint and sample graph; rendered by scripts/render_housegan_sample.py", font=small, fill="#666666")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT)
    print(f"Saved {OUTPUT}; output tensor {scores.shape}; room pixels {[int(mask.sum()) for mask in masks]}")


if __name__ == "__main__":
    draw()
