"""Draw the exact colour samples and vote marks used with the illustrated art."""

from argparse import ArgumentParser
from pathlib import Path

from PIL import Image, ImageDraw


CREAM = "#fff3de"
PURPLE, GREEN, ORANGE, YELLOW = "#8345a9", "#2f865b", "#e17a29", "#f3c625"
INK, HEART = "#264839", "#da6554"
SWATCHES = {
    "sort-yellow": YELLOW,
    "sort-purple": PURPLE,
    "survey-green": GREEN,
    "quiz-5-a": PURPLE,
    "quiz-5-b": GREEN,
    "quiz-5-c": ORANGE,
}


def swatch(color):
    page = Image.new("RGB", (250, 250), CREAM)
    d = ImageDraw.Draw(page)
    d.rounded_rectangle((29, 29, 221, 221), radius=12, fill=color)
    return page


def colour_tray():
    page = Image.new("RGB", (250, 250), CREAM)
    d = ImageDraw.Draw(page)
    for box, color in [
        ((34, 49, 120, 137), "#d65542"),
        ((99, 81, 186, 168), "#3f79ae"),
        ((131, 119, 217, 206), GREEN),
    ]:
        d.rounded_rectangle(box, radius=8, fill=color, outline=CREAM, width=4)
    return page


def vote_mark(yes):
    page = Image.new("RGB", (238, 280), CREAM)
    d = ImageDraw.Draw(page)
    d.ellipse((38, 78, 121, 163), fill=HEART)
    d.ellipse((117, 78, 200, 163), fill=HEART)
    d.polygon(((39, 127), (199, 127), (194, 154), (119, 217), (44, 154)), fill=HEART)
    if not yes:
        d.line(((48, 199), (190, 86)), fill=INK, width=16)
    return page


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--parts", type=Path, required=True)
    args = parser.parse_args()
    for name, color in SWATCHES.items():
        swatch(color).save(args.assets / f"{name}.png", optimize=True)
    colour_tray().save(args.assets / "dock-colours.png", optimize=True)
    vote_mark(False).save(args.parts / "part-vote-no.png", optimize=True)
    vote_mark(True).save(args.parts / "part-vote-yes.png", optimize=True)
