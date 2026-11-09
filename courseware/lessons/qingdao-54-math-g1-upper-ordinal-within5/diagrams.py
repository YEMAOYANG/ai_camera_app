"""Draw ordinal lesson pictures with exactly one object at each declared position."""
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent / "assets"
INK = "#284b47"
TEAL = "#3b857d"
LIGHT_TEAL = "#d9f0e8"
PAPER = "#fff8e8"
GOLD = "#f2ad4a"
PEACH = "#e88059"
INDIGO = "#5874a4"
PINK = "#c67b91"


def icon(name):
    image = Image.new("RGBA", (120, 120))
    d = ImageDraw.Draw(image)

    def shape(points, fill, stroke=INK):
        d.polygon(points, fill=fill)
        d.line([*points, points[0]], fill=stroke, width=4, joint="curve")

    def ellipse(box, fill, stroke=INK):
        d.ellipse(box, fill=fill, outline=stroke, width=4)

    def rect(box, fill, radius=8):
        d.rounded_rectangle(box, radius=radius, fill=fill, outline=INK, width=4)

    if name == "drum":
        rect((18, 48, 102, 95), PEACH, 12)
        ellipse((16, 36, 104, 62), "#fff0c3")
        d.line([(22, 64), (41, 89), (57, 65), (74, 89), (98, 64)], fill=INK, width=4)
        d.line([(29, 19), (62, 47)], fill=INK, width=6)
        d.line([(88, 18), (60, 49)], fill=INK, width=6)
    elif name == "trumpet":
        d.rounded_rectangle((40, 55, 85, 84), radius=13, outline=INK, width=9)
        d.rounded_rectangle((40, 55, 85, 84), radius=13, outline=GOLD, width=5)
        shape([(22, 49), (74, 49), (104, 32), (104, 68), (74, 57), (22, 57)], GOLD)
        rect((12, 45, 25, 61), PEACH, 4)
        for x in (48, 59, 70):
            d.line((x, 38, x, 62), fill=INK, width=4)
            d.line((x-4, 38, x+4, 38), fill=INK, width=3)
    elif name == "piano":
        rect((19, 37, 102, 85), INDIGO)
        rect((24, 51, 97, 72), "#fff5da", 3)
        for x in (37, 49, 61, 73, 85):
            d.line((x, 53, x, 70), fill=INK, width=2)
        for x in (36, 49, 73, 85):
            d.rectangle((x-2, 53, x+2, 62), fill=INK)
        d.line((27, 83, 27, 99), fill=INK, width=5)
        d.line((94, 83, 94, 99), fill=INK, width=5)
    elif name == "harp":
        shape([(20, 98), (91, 98), (85, 23), (60, 40), (35, 32)], GOLD)
        shape([(35, 86), (77, 86), (73, 39), (59, 50), (45, 43)], PAPER)
        for x, y in ((47, 48), (54, 51), (61, 52), (68, 47)):
            d.line((x, y, x, 87), fill=TEAL, width=2)
        d.line((20, 98, 91, 98), fill=INK, width=5)
    elif name == "tambourine":
        ellipse((20, 22, 100, 101), PEACH)
        ellipse((32, 34, 88, 89), "#fff2cd")
        for x, y in ((33, 42), (60, 30), (87, 42), (84, 81), (36, 81)):
            ellipse((x-7, y-4, x+7, y+4), GOLD)
    elif name == "cup":
        d.arc((67, 45, 104, 80), 270, 90, fill=INK, width=6)
        shape([(20, 38), (81, 38), (73, 86), (28, 86)], TEAL)
        ellipse((20, 31, 81, 48), "#f3fcf6")
    elif name.startswith("kite-"):
        form = name[5:]
        if form == "circle":
            ellipse((28, 18, 92, 78), PEACH)
        elif form == "diamond":
            shape([(60, 12), (97, 47), (60, 82), (23, 47)], TEAL)
        elif form == "triangle":
            shape([(60, 17), (98, 77), (22, 77)], GOLD)
        elif form == "pinwheel":
            for points in ([(60, 46), (58, 15), (30, 25)], [(60, 46), (92, 44), (82, 17)],
                           [(60, 46), (62, 77), (90, 67)], [(60, 46), (28, 48), (38, 75)]):
                shape(points, INDIGO)
        else:
            shape([(20, 27), (60, 14), (100, 27), (90, 78), (60, 56), (30, 78)], PINK)
        tail = 59 if form != "pinwheel" else 47
        d.line([(60, 80 if tail == 59 else 48), (69, 92), (56, 105)], fill=INK, width=3)
    elif name.startswith("bag-"):
        rect((26, 33, 94, 98), INDIGO, 12)
        d.arc((45, 17, 75, 48), 180, 360, fill=INK, width=5)
        form = name[4:]
        if form == "stripe":
            for y in (53, 64, 75):
                d.line((42, y, 78, y), fill="#fff5dc", width=5)
        elif form == "circle":
            ellipse((46, 50, 74, 79), GOLD)
        elif form == "star":
            shape([(60, 45), (64, 57), (77, 58), (67, 66), (71, 80),
                   (60, 72), (49, 80), (53, 66), (43, 58), (56, 57)], PEACH)
        else:
            rect((47, 50, 73, 78), LIGHT_TEAL, 3)
    elif name == "lantern":
        rect((38, 34, 82, 88), GOLD, 6)
        d.arc((48, 17, 72, 49), 180, 360, fill=INK, width=4)
        for x in (51, 67):
            d.line((x, 41, x, 82), fill="#b36a30", width=3)
    elif name == "hat":
        ellipse((19, 65, 101, 87), PEACH)
        rect((37, 40, 83, 73), PEACH, 13)
        d.line((38, 62, 82, 62), fill=INK, width=4)
    elif name == "flask":
        rect((42, 25, 78, 45), PEACH, 5)
        rect((32, 40, 88, 96), TEAL, 11)
        d.line((43, 57, 77, 57), fill="#f4f8e4", width=4)
    elif name.startswith("cart"):
        freight = name.removeprefix("cart-")
        if freight == "crate":
            rect((38, 41, 75, 72), GOLD, 4)
            d.line((41, 43, 72, 69), fill=INK, width=3)
        elif freight == "bucket":
            d.arc((40, 27, 76, 55), 180, 360, fill=INK, width=4)
            shape([(37, 40), (80, 40), (73, 72), (43, 72)], INDIGO)
        elif freight == "roll":
            rect((35, 44, 78, 68), PINK, 8)
            ellipse((66, 44, 82, 68), "#eed9ed")
        elif freight == "tripod":
            d.line([(37, 72), (60, 31), (82, 72)], fill=INK, width=6)
            d.line((59, 32, 59, 72), fill=INK, width=5)
            rect((51, 27, 69, 38), GOLD, 3)
        elif freight == "parcel":
            rect((39, 42, 78, 72), GOLD, 4)
            d.line((57, 45, 57, 68), fill=INK, width=3)
        d.line([(18, 49), (27, 77), (98, 77)], fill=INK, width=6, joint="curve")
        ellipse((30, 76, 46, 92), TEAL)
        ellipse((75, 76, 91, 92), TEAL)
    elif name.startswith("leaf-"):
        form = name[5:]
        outlines = {
            "long": [(26, 88), (31, 73), (26, 67), (41, 62), (36, 56), (54, 49),
                     (49, 43), (69, 37), (66, 30), (92, 25), (87, 52), (79, 49),
                     (74, 69), (67, 63), (58, 82), (52, 76), (41, 90)],
            "round": [(27, 77), (24, 54), (33, 36), (52, 28), (77, 29), (93, 43),
                      (94, 61), (82, 79), (60, 88), (40, 85)],
            "heart": [(27, 43), (39, 31), (53, 38), (61, 47), (73, 35), (88, 35),
                      (97, 50), (90, 68), (59, 91), (38, 71)],
            "oval": [(25, 85), (29, 60), (52, 35), (81, 26), (95, 28), (91, 53),
                     (75, 75), (48, 91)],
            "fan": [(60, 91), (26, 62), (23, 43), (35, 30), (54, 37), (61, 27),
                    (70, 38), (88, 32), (97, 46), (94, 62)],
        }
        shape(outlines[form], {"long":TEAL,"round":GOLD,"heart":PEACH,"oval":INDIGO,"fan":PINK}[form])
        d.line((39, 93, 74, 56), fill=INK, width=3)
    else:
        raise ValueError(f"Unknown drawing {name}")
    return image


def arrow(d, start, end, y, color=TEAL):
    head = 16 if end > start else -16
    d.line((start, y, end, y), fill=color, width=5)
    d.polygon([(end, y), (end-head, y-10), (end-head, y+10)], fill=color)


def card(size=(720, 300)):
    image = Image.new("RGB", size, PAPER)
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((4, 4, size[0]-5, size[1]-5), radius=27, outline="#e0bc89", width=3)
    return image, d


def row(name, objects, *, marks=(), direction=None, whole=False, number=False, origin=False, door=False):
    image, d = card()
    spacing = min(126, 610 // len(objects))
    centers = [360 + (i - (len(objects)-1) / 2) * spacing for i in range(len(objects))]
    if whole:
        d.rounded_rectangle((centers[0]-61, 102, centers[-1]+61, 232),
                            radius=25, fill=LIGHT_TEAL, outline=TEAL, width=6)
    if door:
        d.rounded_rectangle((16, 38, 56, 84), radius=13, fill=TEAL, outline=INK, width=3)
        d.ellipse((45, 61, 50, 66), fill=GOLD)
    if direction:
        a, b = (centers[0]-36, centers[-1]+42) if direction == "right" else (centers[-1]+36, centers[0]-42)
        if origin:
            d.ellipse((a-8, 51, a+8, 67), fill=GOLD, outline=INK, width=2)
        arrow(d, a + (12 if direction == "right" else -12), b, 59)
    for i, (obj, x) in enumerate(zip(objects, centers, strict=True)):
        if i in marks:
            d.rounded_rectangle((x-57, 105, x+57, 229), radius=23, fill="#ffe3a1", outline="#a9512d", width=5)
        art = icon(obj).resize((106, 106), Image.Resampling.LANCZOS)
        image.paste(art, (round(x-53), 111), art)
        if number:
            rank = i + 1 if direction == "right" else len(objects) - i
            for j in range(rank):
                pip_x = x - (rank-1)*8 + j*16
                d.ellipse((pip_x-4, 249, pip_x+4, 257), fill=INK)
    image.save(ASSETS / f"{name}.png")


def single(name, obj):
    image, _ = card((240, 186))
    art = icon(obj).resize((164, 164), Image.Resampling.LANCZOS)
    image.paste(art, (38, 11), art)
    image.save(ASSETS / f"{name}.png")


COUNT_PATHS = (("#176d61", "#e5f3eb", True), ("#485c91", "#edf0fa", False))


def count_path(d, left, right, y, color, forward, *, scale=1):
    """A diamond start marker is distinct from any round answer dot."""
    start, end = (left, right) if forward else (right, left)
    direction = 1 if forward else -1
    radius = 13 * scale
    head = 19 * scale
    d.line((start + direction * radius, y, end - direction * head, y), fill=color, width=7 * scale)
    d.polygon(((end, y), (end - direction * head, y - 12 * scale),
               (end - direction * head, y + 12 * scale)), fill=color)
    d.polygon(((start, y-radius), (start+radius, y), (start, y+radius), (start-radius, y)),
              fill=color)


def reverse_position_prompt():
    image, d = card((760, 278))
    centers = (120, 293, 467, 640)
    for y, (color, tint, forward) in zip((47, 231), COUNT_PATHS, strict=True):
        d.rounded_rectangle((40, y-27, 719, y+27), radius=22, fill=tint)
        count_path(d, 72, 688, y, color, forward, scale=2)
    for name, x in zip(("bag-stripe", "bag-circle", "bag-star", "bag-square"), centers, strict=True):
        if name == "bag-circle":
            d.rounded_rectangle((x-65, 80, x+65, 197), radius=23,
                                fill="#ffe3a1", outline="#a9512d", width=7)
        art = icon(name).resize((116, 116), Image.Resampling.LANCZOS)
        image.paste(art, (x-58, 80), art)
    image.save(ASSETS / "quiz-3-prompt.png")


def paired_positions(name, from_left, from_right):
    image, d = card((360, 220))
    for lane, ((color, tint, forward), count) in enumerate(zip(COUNT_PATHS, (from_left, from_right), strict=True)):
        top = 13 + lane * 101
        d.rounded_rectangle((15, top, 345, top + 91), radius=16, fill=tint)
        count_path(d, 44, 316, top + 28, color, forward)
        positions = (180 + (2 * index - count + 1) * 19 for index in range(count))
        for x in positions:
            dot_y = top + 65
            d.ellipse((x-14, dot_y-14, x+14, dot_y+14), fill=GOLD, outline=INK, width=3)
    image.save(ASSETS / f"{name}.png")


def vertical(name, objects):
    image, d = card((340, 525))
    for i, obj in enumerate(objects):
        y = 67 + i*120
        d.rounded_rectangle((121, y-52, 274, y+52), radius=16, fill="#fceac8", outline=TEAL, width=4)
        art = icon(obj).resize((101, 101), Image.Resampling.LANCZOS)
        image.paste(art, (146, y-50), art)
    d.ellipse((53, 483, 79, 509), fill=GOLD, outline=INK, width=3)
    d.line((66, 467, 66, 42), fill=TEAL, width=6)
    d.polygon([(66, 31), (52, 53), (80, 53)], fill=TEAL)
    image.save(ASSETS / f"{name}.png")


def generate():
    ASSETS.mkdir(exist_ok=True)
    instruments = ("drum", "trumpet", "piano", "harp", "tambourine")
    for instrument in instruments:
        icon(instrument).save(ASSETS / f"instrument-{instrument}.png")
    row("teach-five-quantity", instruments, whole=True)
    row("teach-fifth-position", instruments, marks=(4,), direction="right", origin=True)
    four = ("trumpet", "piano", "harp", "tambourine")
    row("teach-reverse-left", four, marks=(0,), direction="right", number=True, origin=True)
    row("teach-reverse-right", four, marks=(0,), direction="left", number=True, origin=True)
    row("teach-recap", instruments, marks=(1, 2, 3), direction="right", origin=True)

    cups = ("cup",)*4
    row("quiz-1-prompt", cups)
    for letter, marks in (("a", (0, 1, 2, 3)), ("b", (0, 1, 2)), ("c", (2,))):
        row(f"quiz-1-{letter}", cups, marks=marks)
    kites = ("kite-circle", "kite-diamond", "kite-triangle", "kite-pinwheel", "kite-tail")
    row("quiz-2-prompt", kites, direction="left", origin=True)
    for letter, obj in (("a", kites[1]), ("b", kites[2]), ("c", kites[4])):
        single(f"quiz-2-{letter}", obj)
    reverse_position_prompt()
    for letter, counts in (("a", (2, 2)), ("b", (3, 2)), ("c", (2, 3))):
        paired_positions(f"quiz-3-{letter}", *counts)
    vertical("quiz-4-prompt", ("lantern", "hat", "flask", "bag-square"))
    for letter, obj in (("a", "lantern"), ("b", "hat"), ("c", "flask")):
        single(f"quiz-4-{letter}", obj)
    row("quiz-5-prompt", ("cart-crate", "cart-bucket", "cart-roll", "cart-tripod", "cart-parcel"),
        marks=(1,), direction="left", door=True)
    for letter, count in (("a", 3), ("b", 1), ("c", 4)):
        row(f"quiz-5-{letter}", ("cart",)*count)
    row("quiz-6-prompt", ("leaf-long", "leaf-round", "leaf-heart", "leaf-oval", "leaf-fan"), marks=(0, 4))
    for letter, count in (("a", 2), ("b", 5), ("c", 3)):
        row(f"quiz-6-{letter}", ("leaf-oval",)*count)


if __name__ == "__main__":
    generate()
