"""Render seat-relative placement diagrams and registered-art teaching panels."""

from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ASSETS = Path(__file__).resolve().parent / "assets"
PAPER = "#fff8e8"
WOOD = "#edc789"
INK = "#805035"
QUIZ_LAYOUTS = {
    "missing-notebook": {"math-book": (170, 170), "pencil-case": (475, 285)},
    "book-front-right": {"math-book": (460, 147), "notebook": (180, 292), "pencil-case": (330, 221)},
    "book-front-left": {"math-book": (180, 147), "notebook": (460, 292), "pencil-case": (330, 221)},
    "book-back-right": {"math-book": (460, 292), "notebook": (180, 147), "pencil-case": (330, 221)},
    "notebook-ahead": {"notebook": (324, 150), "pencil-case": (324, 300)},
    "notebook-beside": {"notebook": (168, 220), "pencil-case": (480, 220)},
    "notebook-behind": {"notebook": (324, 300), "pencil-case": (324, 150)},
}


def picture(key):
    return Image.open(ASSETS / f"{key}.png").convert("RGB")


def supply_picture(key):
    with Image.open(ASSETS / f"{key}.png") as image:
        rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    left, top, right, bottom = alpha.point(lambda value: 255 if value >= 128 else 0).getbbox()
    return rgba.crop((max(0, left - 7), max(0, top - 7),
                      min(rgba.width, right + 7), min(rgba.height, bottom + 7)))


def seat_diagram(placements):
    image = Image.new("RGB", (648, 470), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 68, 603, 368), radius=37, fill=WOOD, outline=INK, width=7)
    draw.rounded_rectangle((264, 389, 384, 465), radius=19, fill="#6ca993", outline="#376d5a", width=5)
    draw.rounded_rectangle((249, 421, 399, 465), radius=14, fill="#487d6d", outline="#376d5a", width=5)
    for key, (cx, cy) in placements.items():
        image_item = ImageOps.contain(supply_picture(key), (135, 126))
        offset = (cx - image_item.width // 2, cy - image_item.height // 2)
        image.paste(image_item, offset, image_item.getchannel("A"))
    return image


def teaching_panel(keys):
    image = Image.new("RGB", (840, 580), PAPER)
    for key, (left, top) in zip(keys, ((15, 12), (425, 12), (220, 295))):
        paste_panel(image, key, left, top, 400, 267)
    return image


def paste_panel(image, key, left, top, width, height):
    frame = ImageOps.contain(picture(key), (width - 12, height - 12))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((left, top, left + width, top + height), radius=22, fill="#f8e5bc")
    image.paste(frame, (left + (width - frame.width) // 2, top + (height - frame.height) // 2))


def time_panel():
    image = Image.new("RGB", (840, 580), PAPER)
    paste_panel(image, "walk-class", 342, 12, 480, 267)
    paste_panel(image, "class-ready", 342, 297, 480, 267)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((23, 117, 306, 452), radius=30, fill="#f4deb3", outline=INK, width=4)
    draw.ellipse((56, 165, 274, 383), fill="#fffaf1", outline=INK, width=6)
    cx, cy = 165, 274
    for i in range(12):
        angle = i * pi / 6 - pi / 2
        r = 79 if i % 3 == 0 else 85
        draw.line((cx + r * cos(angle), cy + r * sin(angle),
                   cx + 94 * cos(angle), cy + 94 * sin(angle)), fill=INK, width=4)
    for i, r, width in ((8.5, 54, 9), (6, 74, 6)):
        angle = i * pi / 6 - pi / 2
        draw.line((cx, cy, cx + r * cos(angle), cy + r * sin(angle)), fill=INK, width=width)
    draw.ellipse((160, 269, 170, 279), fill=INK)
    return image


def main():
    for key, placements in QUIZ_LAYOUTS.items():
        seat_diagram(placements).save(ASSETS / f"{key}.png", optimize=True)
    seat_diagram({"math-book": (178, 152), "notebook": (475, 276),
                  "pencil-case": (333, 221)}).save(ASSETS / "desk-lesson.png", optimize=True)
    teaching_panel(("raise-hand", "speak-turn", "listen")).save(ASSETS / "turn-lesson.png", optimize=True)
    time_panel().save(ASSETS / "time-lesson.png", optimize=True)


if __name__ == "__main__":
    main()
