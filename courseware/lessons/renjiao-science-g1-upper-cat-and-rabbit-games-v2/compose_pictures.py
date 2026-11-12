"""Lay registered originals side by side for matched observations."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


COMPARISONS = {
    "listen-strip": ("listen-bare", "listen-cup", "listen-cone"),
    "cat-eyes": ("cat-eye-bright", "cat-eye-dim"),
    "climb-pair": ("cat-climb", "claw"),
    "rabbit-move": ("hindleg", "rabbit-jump"),
    "care-strip": ("wash", "gloves", "tell-adult"),
}


def comparison(directory, keys):
    tile, gap = 320, 18
    image = Image.new("RGB", (tile * len(keys) + gap * (len(keys) + 1), tile + 2 * gap), "#f6efdc")
    outline = ImageDraw.Draw(image)
    for i, key in enumerate(keys):
        x = gap + i * (tile + gap)
        with Image.open(directory / (key + ".png")) as asset:
            fitted = ImageOps.contain(asset.convert("RGB"), (tile, tile), Image.Resampling.LANCZOS)
        outline.rounded_rectangle((x, gap, x + tile - 1, gap + tile - 1), radius=12, fill="#fffdf4")
        image.paste(fitted, (x + (tile - fitted.width) // 2, gap + (tile - fitted.height) // 2))
        outline.rectangle((x, gap, x + tile - 1, gap + tile - 1), outline="#d7c9a8", width=3)
    return image


if __name__ == "__main__":
    assets = Path(__file__).with_name("assets")
    for name, sources in COMPARISONS.items():
        comparison(assets, sources).save(assets / (name + ".png"), optimize=True)
