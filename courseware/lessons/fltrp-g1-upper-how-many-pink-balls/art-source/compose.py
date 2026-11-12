"""Render the lesson's counted art from its registered single-object PNGs."""

import argparse
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FILTER = Image.Resampling.LANCZOS


def visible(image):
    alpha = image.getchannel("A").point(lambda value: 255 if value >= 8 else 0)
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("empty image layer")
    return image.crop(bounds)


def place(canvas, image, centre, size):
    sprite = ImageOps.contain(visible(image), tuple(size), FILTER)
    left = round(centre[0] - sprite.width / 2)
    top = round(centre[1] - sprite.height / 2)
    if not (0 <= left <= canvas.width - sprite.width and 0 <= top <= canvas.height - sprite.height):
        raise ValueError(f"sprite outside canvas at {centre}")
    canvas.alpha_composite(sprite, (left, top))


def render_all(output):
    brief = json.loads((ROOT / "brief.json").read_text(encoding="utf-8"))
    atlas = brief["mediaPlan"]["ballAtlas"]
    layout = json.loads((ROOT / "art-source" / "counted-layout.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)

    @lru_cache(maxsize=None)
    def source(key):
        with Image.open(ROOT / "assets" / f"{key}.png") as image:
            return image.convert("RGBA")

    def save(key, image):
        image.save(output / f"{key}.png", optimize=True, compress_level=9)

    groups = {}
    for key, order in atlas["paintOrderByGroup"].items():
        grid = atlas["gridsByTotal"][str(len(order))]
        canvas = Image.new("RGBA", (256, 256))
        size = round(grid["diameter"] * 256 / 100)
        if len(order) != len(grid["centres"]):
            raise ValueError(f"layout does not cover the exact quantity for {key}")
        for colour, xy in zip(order, grid["centres"]):
            centre = tuple(round(value * 256 / 100) for value in xy)
            place(canvas, source(atlas["singleSources"][colour]["id"]), centre, (size, size))
        group_key = f"group-{key}"
        groups[group_key] = canvas
        save(group_key, canvas)

    for key, spec in layout.items():
        size = tuple(spec["size"])
        if "background" in spec:
            canvas = source(spec["background"]).resize(size, FILTER)
        else:
            canvas = Image.new("RGBA", size, spec.get("fill", "#fff4dc"))
        draw = ImageDraw.Draw(canvas)
        for panel in spec.get("panels", []):
            draw.rounded_rectangle(panel["bounds"], radius=panel["radius"], fill=panel["fill"],
                                   outline=panel.get("outline"), width=panel.get("width", 1))
        for band in spec.get("arcs", []):
            draw.arc(band["bounds"], start=180, end=360, fill=band["fill"], width=band["width"])
        for layer in spec.get("sprites", []):
            image = groups[layer["asset"]] if layer["asset"] in groups else source(layer["asset"])
            place(canvas, image, layer["centre"], layer["size"])
        if spec.get("fill") != "transparent":
            canvas = canvas.convert("RGB")
        save(key, canvas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="directory for rendered PNG assets")
    args = parser.parse_args()
    render_all(args.output)
