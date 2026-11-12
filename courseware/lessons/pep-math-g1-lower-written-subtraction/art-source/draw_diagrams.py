"""Render the exact place-value diagrams for the park supply lesson."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ART = Path(__file__).resolve().parent
ASSETS = ART.parent / "assets"
PAPER = "#fff6e5"
PINE = "#263e33"
MOSS = "#416650"
ORANGE = "#a74524"
CREAM = "#f5dca9"
RULE = "#adad90"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size):
    return ImageFont.truetype(FONT, size)


def sheet(size=(680, 330)):
    image = Image.new("RGB", size, PAPER)
    return image, ImageDraw.Draw(image)


def digits(draw, value, x, y, size=59, fill=PINE):
    draw.text((x, y), str(value), anchor="mm", font=font(size), fill=fill)


def packet_tiles(count, start_x, start_y, step, *, columns=5):
    return [(start_x + step * (i % columns), start_y + step * (i // columns)) for i in range(count)]


def amount_marks(image, draw, tens, ones, x, y, step, bag=None):
    """Draw tens as enclosed groups and ones as separate packets."""
    for left, top in packet_tiles(tens, x, y, step):
        width, height = step - 4, round(step * .56)
        draw.rounded_rectangle((left, top, left + width, top + height), radius=max(2, step // 10),
                               outline=MOSS, width=max(1, step // 14), fill="#d4e3bf")
        for col in range(5):
            for row in range(2):
                cx = left + width * (.16 + .17 * col)
                cy = top + height * (.34 + .34 * row)
                radius = max(.6, step / 29)
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=PINE)
    loose_x = x + step * 5 + step // 3
    for left, top in packet_tiles(ones, loose_x, y, step):
        if bag is None:
            draw.rounded_rectangle((left + 2, top + 1, left + step - 4, top + step - 4),
                                   radius=max(1, step // 7), outline=ORANGE, width=max(1, step // 10), fill="#e7a662")
        else:
            image.paste(bag, (left, top), bag)


def seed_sprite(step):
    with Image.open(ASSETS / "seed-bag.png") as raw:
        sprite = raw.convert("RGBA")
    sprite = sprite.crop(sprite.getchannel("A").point(lambda a: 255 if a >= 16 else 0).getbbox())
    sprite.thumbnail((step - 3, step - 2), Image.Resampling.LANCZOS)
    return sprite


def stock(tens, ones):
    image, draw = sheet()
    draw.rounded_rectangle((27, 18, 653, 311), radius=24, outline=RULE, width=3)
    draw.line((340, 84, 340, 284), fill=RULE, width=3)
    digits(draw, tens, 170, 62)
    digits(draw, ones, 500, 62)
    amount_marks(image, draw, tens, ones, 42, 112, 58, seed_sprite(58))
    return image


def problem(top, bottom):
    image, draw = sheet()
    draw.rounded_rectangle((17, 16, 663, 155), radius=20, fill="#e5edcd")
    draw.rounded_rectangle((17, 175, 663, 314), radius=20, fill="#f6e2bc")
    digits(draw, top, 95, 84, 57)
    digits(draw, "−" + str(bottom), 90, 244, 55, ORANGE)
    amount_marks(image, draw, *divmod(top, 10), 180, 43, 44, seed_sprite(44))
    amount_marks(image, draw, *divmod(bottom, 10), 180, 202, 44, seed_sprite(44))
    return image


def write_row(draw, value, x_tens, x_ones, y, size, fill=PINE, *, alignment="ones"):
    text = str(value)
    if len(text) == 2:
        digits(draw, text[0], x_tens, y, size, fill)
    last = x_tens if alignment == "tens" and len(text) == 1 else x_ones
    digits(draw, text[-1], last, y, size, fill)


def vertical(top, bottom, *, answer=None, alignment="ones", borrow=False):
    image, draw = sheet()
    draw.rounded_rectangle((140, 14, 538, 316), radius=25, outline=RULE, width=4)
    draw.rounded_rectangle((229, 32, 328, 291), radius=16, fill="#e1ebce")
    draw.rounded_rectangle((357, 32, 456, 291), radius=16, fill="#f6e0b4")
    if borrow:
        draw.ellipse((270, 37, 285, 52), fill=ORANGE)
    write_row(draw, top, 278, 406, 95, 63)
    digits(draw, "−", 191, 161, 60, ORANGE)
    write_row(draw, bottom, 278, 406, 164, 63, alignment=alignment)
    draw.line((174, 204, 494, 204), fill=PINE, width=5)
    if answer is not None:
        write_row(draw, answer, 278, 406, 252, 63, ORANGE)
    return image


def exchange(top, bottom):
    tens, ones = divmod(top, 10)
    remove_tens, remove_ones = divmod(bottom, 10)
    assert tens > 0 and ones < remove_ones and tens > remove_tens
    result_tens, result_ones = tens - 1 - remove_tens, ones + 10 - remove_ones
    assert result_tens * 10 + result_ones == top - bottom
    image, _ = sheet()
    opened = stock(tens - 1, ones + 10)
    opened.thumbnail((440, 214), Image.Resampling.LANCZOS)
    image.paste(opened, (0, 58))
    mini = vertical(top, bottom, answer=str(top-bottom), borrow=True)
    mini = mini.crop((128, 6, 550, 324))
    mini.thumbnail((218, 170), Image.Resampling.LANCZOS)
    image.paste(mini, (448, 80))
    return image


def error_pair(top, bottom, first, second):
    image, _ = sheet()
    for i, answer in enumerate((first, second)):
        example = vertical(top, bottom, answer=answer, borrow=i == 1)
        cropped = example.crop((133, 8, 545, 322))
        cropped.thumbnail((307, 283), Image.Resampling.LANCZOS)
        image.paste(cropped, (15 + i * 340, 40))
    return image


def ledger_token(top, bottom):
    image, draw = sheet((192, 152))
    write_row(draw, top, 96, 146, 35, 53)
    digits(draw, "−", 39, 101, 49, ORANGE)
    write_row(draw, bottom, 96, 146, 99, 53)
    draw.line((27, 132, 174, 132), fill=PINE, width=8)
    return image


def stock_token(value):
    image, draw = sheet((192, 152))
    digits(draw, value, 96, 56, 100)
    amount_marks(image, draw, *divmod(value, 10), 9, 102, 15)
    return image


RENDERERS = {
    "stock": stock,
    "problem": problem,
    "vertical": lambda top, bottom, spec: vertical(top, bottom, **spec),
    "exchange": exchange,
    "error-pair": error_pair,
    "ledger-token": ledger_token,
    "stock-token": stock_token,
}


if __name__ == "__main__":
    for name, (kind, *arguments) in json.loads((ART / "diagram-data.json").read_bytes()).items():
        picture = RENDERERS[kind](*arguments)
        picture.save(ASSETS / f"{name}.png", optimize=True)
