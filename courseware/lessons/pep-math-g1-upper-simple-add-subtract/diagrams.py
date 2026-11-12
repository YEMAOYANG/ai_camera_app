"""Draw the exact quantities for the kite festival arithmetic lesson."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LESSON = Path(__file__).resolve().parent
FONT_PATH = LESSON.parents[2] / "mobile/test/assets/fonts/NotoSansCJKsc-Regular.otf"
PAPER = "#fff8e8"
PANEL = "#f8e7c6"
INK = "#243e35"
PINE = "#2e6657"
APRICOT = "#d67e4f"
HINT = "#a8452f"

FALLING_OPERATIONS = ((14, 4), (16, 6), (12, 10), (17, 7), (16, 10),
                      (15, 3), (19, 10), (14, 1), (17, 2))
DELIVERY_STOCK = (11, 12, 13, 14, 16, 18, 19)
DELIVERY_DOCKS = (12, 14, 16, 17, 18)
QUIZ_VALUES = {
    "q1": (11, 10, 12), "q2": (10, 19, 9), "q3": (18, 19, 12),
    "q4": (11, 16, 7), "q5": ((15, "+", 2), (15, "−", 2), (15, "−", 3)),
    "q6": (0, 1, 2),
}


@lru_cache(maxsize=20)
def font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def label(draw, x, y, value, size, color=INK):
    draw.text((x, y), str(value), fill=color, font=font(size), anchor="mm")


def panel(size=(620, 310)):
    image = Image.new("RGB", size, PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size[0] - 9, size[1] - 9), 20, fill=PANEL)
    return image


def token(draw, x, y, radius, kind="round", *, removed=False):
    color = PINE if not removed else "#d0a680"
    if kind == "diamond":
        draw.polygon((x, y-radius, x+radius, y, x, y+radius, x-radius, y), fill=color)
    elif kind == "square":
        draw.rounded_rectangle((x-radius, y-radius, x+radius, y+radius), radius/3, fill=color)
    else:
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    if removed:
        arm = radius * .78
        draw.line((x-arm, y-arm, x+arm, y+arm), fill=HINT, width=max(2, round(radius*.23)))
        draw.line((x-arm, y+arm, x+arm, y-arm), fill=HINT, width=max(2, round(radius*.23)))


def ten_frame(draw, x, y, pitch, kind="round", *, removed=False):
    draw.rounded_rectangle((x-pitch*.58, y-pitch*.57, x+pitch*4.58, y+pitch*1.57),
                           radius=pitch*.33, outline=INK, width=max(2, round(pitch*.07)))
    for index in range(10):
        token(draw, x+(index%5)*pitch, y+(index//5)*pitch, pitch*.33, kind, removed=removed)


def loose(draw, x, y, quantity, pitch, kind="round", *, removed=0):
    for index in range(quantity):
        token(draw, x+(index%5)*pitch, y+(index//5)*pitch, pitch*.33,
              kind, removed=index >= quantity-removed)


def stock(quantity, *, kind="round", removed=0, show_total=True):
    image = panel()
    draw = ImageDraw.Draw(image)
    whole_ten, ones = divmod(quantity, 10)
    if whole_ten:
        ten_frame(draw, 56, 108, 46, kind, removed=removed == 10)
        loose(draw, 350, 108, ones, 46, kind, removed=0 if removed == 10 else removed)
    else:
        loose(draw, 213, 108, ones, 49, kind)
    if show_total:
        label(draw, 310, 233, quantity if removed == 0 else f"{quantity} − {removed}", 53)
    return image


def counter(quantity, *, changed=0, direction=None, small=False):
    size = (192, 192) if small else (620, 310)
    image = panel(size)
    draw = ImageDraw.Draw(image)
    tens, ones = divmod(quantity, 10)
    xs = (58, 132) if small else (226, 388)
    bottom = 134 if small else 223
    top = 14 if small else 30
    step = 11 if small else 19
    rx, ry = (17, 5) if small else (34, 8)
    for x, count in zip(xs, (tens, ones)):
        draw.line((x, top, x, bottom + 4), fill=INK, width=4 if small else 6)
        for index in range(count):
            y = bottom - step*index
            color = APRICOT if x == xs[1] and index >= count-changed else PINE
            draw.rounded_rectangle((x-rx, y-ry, x+rx, y+ry), radius=ry, fill=color)
    draw.rounded_rectangle((xs[0]-35, bottom+6, xs[1]+35, bottom+13), 3, fill=INK)
    if direction:
        y = bottom - step*max(0, ones-changed)
        x = xs[1] + 62
        start, end = (y-70, y-8) if direction == "in" else (y-8, y-70)
        draw.line((x, start, x, end), fill=HINT, width=8)
        offset = -14 if direction == "in" else 14
        draw.polygon((x, end, x-13, end+offset, x+13, end+offset), fill=HINT)
    label(draw, size[0]/2, bottom + (34 if small else 50), quantity, 42 if small else 53)
    return image


def compact_stock(quantity):
    image = panel((192, 192))
    draw = ImageDraw.Draw(image)
    if quantity >= 10:
        ten_frame(draw, 32, 39, 28)
        draw.line((24, 95, 168, 95), fill=INK, width=2)
    loose(draw, 35, 112, quantity % 10, 27)
    label(draw, 96, 166, quantity, 45)
    return image


def equation(a, op, b, *, mark=None, compact=False):
    size = (192, 192) if compact else (620, 310)
    image = panel(size)
    draw = ImageDraw.Draw(image)
    if compact:
        label(draw, 96, 99, f"{a}{op}{b}", 57)
        return image
    result = a+b if op == "+" else a-b
    for index, (x, value) in enumerate(zip((93, 184, 286, 383, 505), (a, op, b, "=", result))):
        if mark is not None and index == mark*2:
            draw.rounded_rectangle((x-61, 93, x+61, 217), 24, fill="#ffe7a7", outline=HINT, width=6)
        label(draw, x, 158, value, 74)
    return image


def unknown(left, right, *, total_unknown):
    image = panel()
    draw = ImageDraw.Draw(image)
    parts = (left, right if total_unknown else "?")
    for x, value in zip((178, 442), parts):
        draw.rounded_rectangle((x-107, 43, x+107, 164), 17, fill=PAPER, outline=PINE, width=4)
        label(draw, x, 105, value, 63)
    draw.line((71, 176, 71, 202, 549, 202, 549, 176), fill=INK, width=5)
    label(draw, 310, 256, "?" if total_unknown else left+right, 62, HINT)
    return image


def add_one_badge():
    image = panel()
    draw = ImageDraw.Draw(image)
    ten_frame(draw, 79, 112, 52, "diamond")
    label(draw, 372, 137, "+", 55)
    token(draw, 490, 137, 28, "diamond")
    return image


def geometry_assets():
    assets = {
        "box-and-eight": stock(18, show_total=False),
        "take-eight": stock(18, removed=8), "take-the-ten": stock(18, removed=10),
        "counter-add-four": counter(16, changed=4, direction="in"),
        "counter-remove-four": counter(16, changed=4, direction="out"),
        "operation-total": unknown(12, 2, total_unknown=True),
        "operation-part": unknown(3, 13, total_unknown=False),
        "roles-add": equation(12, "+", 4), "roles-minus": equation(16, "−", 4),
        "q1-main": add_one_badge(),
        "q2-main": stock(19, kind="square", removed=10),
        "q3-main": counter(12), "q4-main": stock(17, removed=6),
        "q5-main": stock(15, kind="diamond", removed=2, show_total=False), "q6-main": equation(14, "+", 3),
    }
    for a, b in FALLING_OPERATIONS:
        assets[f"take-{a:02d}-{b:02d}"] = equation(a, "−", b, compact=True)
        assets[f"rem-{a-b:02d}"] = compact_stock(a-b)
    for value in DELIVERY_STOCK:
        assets[f"stock-{value:02d}"] = compact_stock(value)
    for value in DELIVERY_DOCKS:
        assets[f"dock-{value:02d}"] = counter(value, small=True)
    for q, values in QUIZ_VALUES.items():
        for letter, value in zip("abc", values):
            if q == "q3":
                image = counter(value)
            elif q == "q5":
                image = equation(*value)
            elif q == "q6":
                image = equation(14, "+", 3, mark=value)
            else:
                kind = {"q1": "diamond", "q2": "square", "q4": "round"}[q]
                image = stock(value, kind=kind, show_total=False)
            assets[f"{q}-{letter}"] = image
    return assets


def main():
    for key, image in geometry_assets().items():
        image.save(LESSON / "assets" / (key + ".png"), optimize=True)


if __name__ == "__main__":
    main()
