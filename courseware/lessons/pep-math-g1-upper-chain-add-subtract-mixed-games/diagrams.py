"""Draw this lesson's exact book inventories and quiz quantities."""

from pathlib import Path
import json

from PIL import Image, ImageDraw


SOURCE = Path(__file__).resolve().parent
PALETTE = {"ink": "#294743", "border": "#a0b7a6", "cream": "#fff9eb",
           "sage": "#e3efe7", "blue": "#dceef4", "peach": "#f7e7d9"}
LECTURE_IMAGES = {
    "add-inventory": (3, 4, 8),
    "subtract-inventory": (7, 6, 3),
    "plus-then-minus": (5, 8, 7),
    "minus-then-plus": (5, 4, 7),
}
QUIZ_OBJECTS = ("bead", "block", "pen", "paper", "counter", "bean")


def count_positions(amount, center, space, columns=5):
    """Center each row and preserve a visible break after five."""
    for index in range(amount):
        row, column = divmod(index, columns)
        length = min(columns, amount - row * columns)
        rows = (amount + columns - 1) // columns
        yield (round(center[0] + (column - (length - 1) / 2) * space[0]),
               round(center[1] + (row - (rows - 1) / 2) * space[1]))


def arrow(draw, x, y, *, vertical=False):
    if vertical:
        draw.line((x, y - 18, x, y + 13), fill=PALETTE["ink"], width=6)
        draw.polygon(((x - 13, y + 6), (x + 13, y + 6), (x, y + 22)), fill=PALETTE["ink"])
    else:
        draw.line((x - 19, y, x + 11, y), fill=PALETTE["ink"], width=6)
        draw.polygon(((x + 4, y - 13), (x + 4, y + 13), (x + 21, y)), fill=PALETTE["ink"])


def inventory(counts, book):
    picture = Image.new("RGBA", (720, 510), PALETTE["cream"])
    draw = ImageDraw.Draw(picture)
    sprite = book.copy()
    sprite.thumbnail((51, 51), Image.Resampling.LANCZOS)
    for index, amount in enumerate(counts):
        center_y = 76 + index * 179
        draw.rounded_rectangle((52, center_y - 59, 668, center_y + 59), 25,
                               fill=(PALETTE["sage"], PALETTE["blue"], PALETTE["peach"])[index],
                               outline=PALETTE["border"], width=3)
        for x, y in count_positions(amount, (360, center_y), (82, 54)):
            picture.alpha_composite(sprite, (x - sprite.width // 2, y - sprite.height // 2))
        if index < 2:
            arrow(draw, 360, center_y + 90, vertical=True)
    return picture.convert("RGB")


def draw_object(draw, kind, x, y, color):
    ink = PALETTE["ink"]
    if kind == "bead":
        draw.ellipse((x - 19, y - 19, x + 19, y + 19), fill=color, outline=ink, width=2)
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="#fff9eb", outline=ink, width=2)
    elif kind == "block":
        draw.polygon(((x - 16, y - 10), (x + 8, y - 18), (x + 19, y - 9), (x - 6, y)), fill="#f7d4a1", outline=ink)
        draw.polygon(((x - 16, y - 10), (x - 6, y), (x - 6, y + 19), (x - 16, y + 10)), fill="#c18b5b", outline=ink)
        draw.polygon(((x - 6, y), (x + 19, y - 9), (x + 19, y + 10), (x - 6, y + 19)), fill=color, outline=ink)
    elif kind == "pen":
        draw.rounded_rectangle((x - 6, y - 18, x + 6, y + 12), 3, fill=color, outline=ink, width=2)
        draw.line((x - 5, y - 10, x + 5, y - 10), fill=ink, width=2)
        draw.polygon(((x - 5, y + 12), (x + 5, y + 12), (x, y + 19)), fill=ink)
    elif kind == "paper":
        draw.polygon(((x - 14, y - 17), (x + 7, y - 17), (x + 14, y - 9), (x + 14, y + 17), (x - 14, y + 17)),
                     fill="#fffdfa", outline=ink)
        draw.line((x + 6, y - 16, x + 6, y - 9, x + 13, y - 9), fill=ink, width=1)
        for dy in (-3, 4, 11):
            draw.line((x - 8, y + dy, x + 8, y + dy), fill=color, width=2)
    elif kind == "counter":
        draw.ellipse((x - 19, y - 19, x + 19, y + 19), fill=color, outline=ink, width=2)
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), outline="#ecf6e5", width=3)
    else:
        draw.ellipse((x - 17, y - 11, x + 17, y + 11), fill=color, outline=ink, width=2)
        draw.arc((x - 12, y - 7, x + 12, y + 5), 205, 332, fill="#fbe0af", width=3)


def quiz_story(calculation, kind):
    """Show the starting count and the two distinct changes, without solving them."""
    picture = Image.new("RGB", (900, 275), PALETTE["cream"])
    draw = ImageDraw.Draw(picture)
    colors = {"block": "#dfac71", "pen": "#51847d", "paper": "#669a96",
              "counter": "#7ca982", "bean": "#ba824e"}
    for index, value in enumerate(calculation):
        x = 148 + index * 302
        y = 145
        draw.rounded_rectangle((x - 125, 43, x + 125, 246), 28,
                               fill=(PALETTE["blue"], PALETTE["sage"], PALETTE["peach"])[index],
                               outline=PALETTE["border"], width=3)
        if index:
            sign_color = "#31774f" if value > 0 else "#9c3b3a"
            draw.line((x - 13, 83, x + 13, 83), fill=sign_color, width=6)
            if value > 0:
                draw.line((x, 70, x, 96), fill=sign_color, width=6)
            y += 24
        color = ("#62add2", "#6ea982", "#cc6f68")[index] if kind == "bead" else colors[kind]
        for px, py in count_positions(abs(value), (x, y), (45, 49)):
            draw_object(draw, kind, px, py, color)
        if index < 2:
            arrow(draw, x + 151, 147)
    return picture


def render():
    assets = SOURCE / "assets"
    with Image.open(assets / "single-book.png") as image:
        book = image.convert("RGBA")
    for name, counts in LECTURE_IMAGES.items():
        inventory(counts, book).save(assets / (name + ".png"))
    quiz = json.loads((SOURCE / "brief.json").read_text(encoding="utf-8"))["quiz"]
    if len(quiz) != len(QUIZ_OBJECTS):
        raise ValueError("Every quiz question needs one picture type.")
    for item, kind in zip(quiz, QUIZ_OBJECTS):
        quiz_story(item["calculation"], kind).save(assets / (item["id"] + ".png"))


if __name__ == "__main__":
    render()
