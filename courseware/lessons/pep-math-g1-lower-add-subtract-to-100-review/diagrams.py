"""Exact unit blocks, grouping and comparisons for the radio studio review."""

from hashlib import sha256
from pathlib import Path
import json
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ATLAS = ASSETS / "source" / "radio-studio-atlas.png"
INK = "#173e35"
CREAM = "#fbefcf"
GREEN = "#417e68"
ORANGE = "#db8850"
EDGE = "#a98459"
FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def text(draw, pos, value, size, color=INK):
    draw.text(pos, str(value), fill=color, anchor="mm", font=ImageFont.truetype(str(FONT), size))


def panel(size=(620, 330)):
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rounded_rectangle((4, 4, w - 5, h - 5), radius=min(25, w // 9), fill=CREAM, outline=EDGE, width=3)
    return image, draw


def rod(draw, x, y, unit, color=GREEN):
    draw.rounded_rectangle((x, y, x + unit, y + 10 * unit), radius=max(1, unit // 5), fill=color, outline=INK, width=1)
    for n in range(1, 10):
        draw.line((x + 1, y + n * unit, x + unit - 1, y + n * unit), fill="#e0e2ba")


def square(draw, x, y, unit, color=ORANGE):
    draw.rounded_rectangle((x, y, x + unit, y + unit), radius=max(1, unit // 5), fill=color, outline=INK, width=1)


def stock(draw, box, tens, ones, *, mark=None, remove=0):
    """Keep tens together and align ones in rows of five."""
    assert 0 <= tens <= 9 and 0 <= remove <= ones <= 19
    left, top, width, height = box
    unit = max(2, int(min(width / 23, height / 13)))
    origin = left + int((width - 22 * unit) / 2)
    y = top + (height - 10 * unit) // 2
    for index in range(tens):
        x = origin + index % 5 * int(1.42 * unit)
        if index >= 5:
            x += int(7.3 * unit)
        rod(draw, x, y, unit)
    split = origin + int(14.5 * unit)
    draw.line((split - unit, y - unit, split - unit, y + 11 * unit), fill=EDGE, width=max(1, unit // 6))
    for index in range(ones):
        x = split + (index % 5) * int(1.32 * unit)
        yy = y + unit + index // 5 * int(1.68 * unit)
        square(draw, x, yy, unit)
        if index >= ones - remove:
            draw.line((x - 1, yy + unit + 1, x + unit + 1, yy - 1), fill="#9d372b", width=max(2, unit // 4))
    if mark == "ten":
        draw.rounded_rectangle(
            (split - 4, y + unit - 5, split + int(6.45 * unit), y + int(4.13 * unit)),
            radius=7, outline="#9d372b", width=3,
        )


def arrow(draw, start, end, color=GREEN):
    x, y = start
    tx, ty = end
    draw.line((x, y, tx, ty), fill=color, width=5)
    step = 12 if tx > x else -12
    draw.polygon([(tx, ty), (tx - step, ty - 7), (tx - step, ty + 7)], fill=color)


def equation(left, sign, right, *, small=False):
    image, draw = panel((224, 224) if small else (620, 330))
    w, h = image.size
    text(draw, (w / 2, h * .27 if small else h * .24), f"{left}{sign}{right}", int(w / (2.7 if small else 10)))
    if small:
        stock(draw, (8, 102, 208, 96), *divmod(left, 10))
    else:
        stock(draw, (16, 100, 280, 203), *divmod(left, 10))
        stock(draw, (322, 100, 280, 203), *divmod(right, 10))
        text(draw, (310, 197), sign, 46)
    return image


def value_card(value, size=(620, 330)):
    image, draw = panel(size)
    w, h = size
    text(draw, (w / 2, h * .23), value, int(h * .25))
    stock(draw, (8, int(h * .35), w - 16, int(h * .59)), *divmod(value, 10))
    return image


def join_panels(images, size=(860, 570), *, columns=1):
    image, _ = panel(size)
    w, h = size
    rows = (len(images) + columns - 1) // columns
    cell_w, cell_h = (w - 38) // columns, (h - 30) // rows
    for index, item in enumerate(images):
        fitted = ImageOps.contain(item, (cell_w - 10, cell_h - 8), Image.Resampling.LANCZOS)
        x = 19 + index % columns * cell_w + (cell_w - fitted.width) // 2
        y = 15 + index // columns * cell_h + (cell_h - fitted.height) // 2
        image.alpha_composite(fitted, (x, y))
    return image


def place_comparison(left, right, sign):
    result = left + right if sign == "+" else left - right
    image, draw = panel((920, 218))
    text(draw, (460, 42), f"{left} {sign} {right} = {result}", 42)
    stock(draw, (12, 68, 274, 136), *divmod(left, 10))
    stock(draw, (313, 68, 274, 136), *divmod(right, 10))
    text(draw, (305, 126), sign, 39)
    arrow(draw, (603, 136), (637, 136))
    stock(draw, (644, 68, 265, 136), *divmod(result, 10))
    return image


def exchange_example(left, sign, right):
    tens, ones = divmod(left, 10)
    total = left + right if sign == "+" else left - right
    image, draw = panel((920, 266))
    text(draw, (460, 42), f"{left} {sign} {right} = {total}", 47)
    if sign == "+":
        before, middle, removed = (tens, ones), (tens, ones + right), 0
    else:
        before, middle, removed = (tens, ones), (tens - 1, ones + 10), right
    stock(draw, (10, 64, 274, 158), *before)
    stock(draw, (319, 64, 282, 158), *middle, mark="ten" if sign == "+" else None, remove=removed)
    stock(draw, (627, 64, 282, 158), *divmod(total, 10))
    arrow(draw, (284, 140), (315, 140))
    arrow(draw, (598, 140), (630, 140))
    return image


def symbol_badge(mark):
    image, draw = panel((230, 230))
    if mark in {"+", "−"}:
        text(draw, (115, 111), mark, 174)
    elif mark in {"carry", "borrow"}:
        for i in range(10):
            square(draw, 28 + i % 5 * 16, 76 + i // 5 * 21, 13)
        rod(draw, 172, 58, 11)
        arrow(draw, (122, 105) if mark == "carry" else (162, 105), (161, 105) if mark == "carry" else (123, 105))
    else:
        # Two quantities are both less than ten; no arrow between units.
        for i in range(4 if mark == "keep-add" else 7):
            square(draw, 45 + i % 5 * 28, 79 + i // 5 * 33, 21)
        draw.rounded_rectangle((25, 47, 202, 171), radius=28, outline=GREEN, width=8)
    return image


def matte(image):
    """Derive sprite alpha by removing the atlas's mint production background."""
    result = image.convert("RGBA")
    px = result.load()
    for y in range(result.height):
        for x in range(result.width):
            r, g, b, a = px[x, y]
            if r > 145 and g > 193 and b > 168 and g - r > 13 and b - r > 3:
                px[x, y] = (r, g, b, 0)
    return result.crop(result.getbbox())


def paste_sprite(target, sprite, box):
    x, y, w, h = box
    fitted = ImageOps.contain(sprite, (w, h), Image.Resampling.LANCZOS)
    target.alpha_composite(fitted, (x + (w - fitted.width) // 2, y + (h - fitted.height) // 2))


def ticket_problem(ticket, needed, have, proposed=None):
    image, draw = panel()
    for x, n, color in [(109, needed, GREEN), (308, have, GREEN), (509, "?" if proposed is None else proposed, ORANGE)]:
        paste_sprite(image, ticket, (x - 65, 48, 130, 91))
        text(draw, (x, 93), n, 48)
        if isinstance(n, int):
            stock(draw, (x - 85, 143, 170, 132), *divmod(n, 10))
        draw.rounded_rectangle((x - 76, 278, x + 76, 296), radius=7, fill=color)
    arrow(draw, (394, 105), (432, 105))
    return image


def trips(box_sprite, cart, total, per_trip, count):
    image, draw = panel()
    paste_sprite(image, box_sprite, (43, 23, 76, 67))
    text(draw, (155, 56), total, 55)
    paste_sprite(image, cart, (390, 24, 92, 60))
    text(draw, (516, 56), per_trip, 55)
    for i in range(count):
        w = min(165, 570 // count)
        x = (620 - count * w) // 2 + i * w
        draw.rounded_rectangle((x + 4, 116, x + w - 6, 299), radius=14, outline=GREEN, width=3)
        for box in range(per_trip):
            columns = min(per_trip, 3)
            width = min(31, w // 4)
            paste_sprite(image, box_sprite, (x + (w - width * columns) // 2 + box % columns * width,
                                               135 + box // columns * 28, width - 2, 27))
        paste_sprite(image, cart, (x + 9, 224, w - 18, 59))
    return image


def capacity(ticket, left, right, cap, *, show_total=False):
    image, draw = panel()
    draw.rounded_rectangle((55, 64, 565, 279), radius=34, fill="#e9dfb1", outline=GREEN, width=7)
    draw.rounded_rectangle((215, 27, 405, 96), radius=18, fill="#e3a866", outline=EDGE, width=3)
    text(draw, (310, 62), f"≤ {cap}", 44)
    for x, value in [(181, left), (439, right)]:
        paste_sprite(image, ticket, (x - 70, 112, 140, 98))
        text(draw, (x, 160), value, 51)
    text(draw, (310, 158), "+", 54)
    if show_total:
        text(draw, (310, 244), f"= {left + right}", 39)
    return image


def compare_board():
    image, draw = panel((620, 330))
    text(draw, (310, 82), "27 + □ = 37", 58)
    draw.line((50, 158, 570, 158), fill=EDGE, width=3)
    text(draw, (310, 241), "24 + 15 > □", 58)
    return image


SORT_EXPRESSIONS = {
    "add-26-3": (26, "+", 3), "sub-57-3": (57, "−", 3),
    "add-29-6": (29, "+", 6), "add-43-4": (43, "+", 4), "add-56-7": (56, "+", 7),
    "sub-42-5": (42, "−", 5), "sub-65-4": (65, "−", 4),
    "sub-71-6": (71, "−", 6), "sub-49-8": (49, "−", 8),
}
MARBLE_EXPRESSIONS = {
    "more-tens": (38, "+", 20), "more-ones": (38, "+", 1),
    "carry-first": (27, "+", 9), "carry-next": (56, "+", 8),
    "borrow-first": (61, "−", 8), "borrow-next": (74, "−", 6),
}
MARBLE_VALUES = (48, 58, 39, 40, 36, 46, 54, 64, 43, 53, 63, 68, 78)
CHECK_CARRY = ((34, "+", 5), (34, "+", 8), (38, "+", 10))
CHECK_TENS = (67, 49, 77)
CHECK_BORROW = (55, 43, 45)
CHECK_TICKETS = (44, 26, 66)
CHECK_TRIPS = (4, 3, 5)
CHECK_CAPACITY = ((29, 26), (29, 23), (26, 23))


def lesson_uses():
    lesson_file = ROOT / "lesson.json"
    if not lesson_file.is_file():
        return {}
    uses = {}
    for scene in json.loads(lesson_file.read_text())["scenes"]:
        key = scene["key"]
        if scene["type"] == "slide":
            uses.setdefault(scene["data"]["picture"], set()).add(key)
        elif scene["type"] == "interactive":
            uses.setdefault(scene["startImage"], set()).add(key)
            for suffix in (".html", ".js"):
                source = (ROOT / "pages" / (scene["page"] + suffix)).read_text()
                for asset in re.findall(r"__IMG:([a-z0-9-]+)__", source):
                    uses.setdefault(asset, set()).add(key)
        else:
            for question in scene["questions"]:
                for letter, option in question["options"].items():
                    uses.setdefault(option["visual"]["image"], set()).add(f"{key}/{question['id']}/{letter}")
    return uses


def render():
    original = Image.open(ATLAS).convert("RGBA")
    assert original.size == (1254, 1254)
    trolley = matte(original.crop((650, 672, 936, 924)))
    ticket = matte(original.crop((965, 686, 1216, 892)))
    prop_box = matte(original.crop((669, 961, 911, 1191)))
    mic = matte(original.crop((1000, 958, 1204, 1218)))
    illustrations = {
        "cover": original.crop((3, 3, 624, 624)),
        "sort-backdrop": ImageOps.fit(original.crop((632, 4, 1251, 621)), (960, 540), centering=(.5, .18)),
        "match-backdrop": ImageOps.fit(original.crop((3, 633, 622, 1251)), (960, 540), centering=(.5, .26)),
        "trolley": trolley, "microphone": mic, "ticket": ticket,
    }
    images = {
        "sort-board": join_panels([equation(*spec) for spec in [(37, "+", 5), (43, "+", 6), (39, "−", 4), (52, "−", 6)]], columns=2),
        "digits-board": join_panels([place_comparison(41, n, "+") for n in (7, 30, 26)]),
        "place-board": join_panels([place_comparison(*spec) for spec in [(46, 2, "+"), (46, 30, "+"), (56, 24, "−")]]),
        "exchange-board": join_panels([exchange_example(47, "+", 6), exchange_example(64, "−", 7)]),
        "ticket-teach": ticket_problem(ticket, 59, 23),
        "trips-teach": trips(prop_box, trolley, 18, 6, 3),
        "capacity-teach": capacity(ticket, 24, 23, 47, show_total=True),
        "compare-board": compare_board(),
        "sort-rule-ops": join_panels([symbol_badge("+"), symbol_badge("−")], (400, 194), columns=2),
        "sort-rule-carry": join_panels([symbol_badge("carry"), symbol_badge("keep-add")], (400, 194), columns=2),
        "sort-rule-borrow": join_panels([symbol_badge("keep-sub"), symbol_badge("borrow")], (400, 194), columns=2),
        **{f"dock-{i}": symbol_badge(mark) for i, mark in [
            ("plus", "+"), ("minus", "−"), ("carry", "carry"), ("keep-add", "keep-add"),
            ("borrow", "borrow"), ("keep-sub", "keep-sub"),
        ]},
        **{key: equation(*spec, small=True) for key, spec in SORT_EXPRESSIONS.items()},
        **{key: equation(*spec) for key, spec in MARBLE_EXPRESSIONS.items()},
        **{f"value-{value}": value_card(value, (396, 246)) for value in MARBLE_VALUES},
    }
    for letter, expression in zip("abc", CHECK_CARRY):
        images[f"q1-{letter}"] = equation(*expression)
    for letter, value in zip("abc", CHECK_TENS):
        images[f"q2-{letter}"] = value_card(value)
    for letter, value in zip("abc", CHECK_BORROW):
        images[f"q3-{letter}"] = value_card(value)
    for letter, value in zip("abc", CHECK_TICKETS):
        images[f"q4-{letter}"] = ticket_problem(ticket, 46, 20, value)
    for letter, n in zip("abc", CHECK_TRIPS):
        images[f"q5-{letter}"] = trips(prop_box, trolley, 28, 7, n)
    for letter, pair in zip("abc", CHECK_CAPACITY):
        images[f"q6-{letter}"] = capacity(ticket, *pair, 50)
    manifest = {}
    uses = lesson_uses()
    if uses:
        assert set(uses) == set(illustrations) | set(images)
    for name, image in {**illustrations, **images}.items():
        filename = f"{name}.png"
        path = ASSETS / filename
        image.save(path, optimize=True)
        manifest[name] = {
            "path": f"assets/{filename}",
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "width": image.width,
            "height": image.height,
            "source": "radio-studio" if name in illustrations else "diagrams.py",
            "includesAtlasSprites": name in {"ticket-teach", "trips-teach", "capacity-teach"} or name.startswith(("q4-", "q5-", "q6-")),
            "uses": sorted(uses.get(name, ())),
        }
    evidence = {
        "schemaVersion": "mira.courseware.asset-sources.v1",
        "generatedBy": "codex_builtin_imagegen",
        "imagegenPlan": "imagegen-plan.json",
        "diagramProgram": {"path": "diagrams.py", "sha256": sha256(Path(__file__).read_bytes()).hexdigest()},
        "plates": {"radio-studio": {"source": str(ATLAS.relative_to(ROOT)),
                                     "sourceSha256": sha256(ATLAS.read_bytes()).hexdigest(),
                                     "width": original.width, "height": original.height}},
        "assets": manifest,
    }
    (ROOT / "asset-sources.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    render()
