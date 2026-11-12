"""Draw this lesson's exact counts from original ImageGen object cutouts."""

from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PAPER = "#fff5df"
INK = "#263f35"
PINE = "#387362"
LEAF = "#dce9ce"
ORANGE = "#b95c39"
GOLD = "#f8deb4"
GRID = "#e6c599"


def card(size):
    image = Image.new("RGB", size, PAPER)
    ImageDraw.Draw(image).rounded_rectangle((4, 4, size[0] - 5, size[1] - 5), 20, outline=GRID, width=3)
    return image


def label(draw, at, value, size=36, color=INK):
    draw.text(at, str(value), anchor="mm", fill=color, font=ImageFont.load_default(size=size))


def sprite(image, asset, x, y, size):
    with Image.open(ASSETS / (asset + ".png")) as source:
        icon = ImageOps.contain(source.convert("RGBA"), size, Image.Resampling.LANCZOS)
    image.paste(icon, (round(x - icon.width / 2), round(y - icon.height / 2)), icon)


def frame(draw, box, color=ORANGE, width=5):
    draw.rounded_rectangle(box, 9, outline=color, width=width)


def brace(draw, left, right, y, value, *, color=INK, size=37):
    draw.line((left, y + 9, left, y, right, y, right, y + 9), fill=color, width=4)
    label(draw, ((left + right) / 2, y - size * .65), value, size, color)


def segment(image, left, right, y, count, *, color=PINE, fill=LEAF, height=55, asset=None, hide=False):
    draw = ImageDraw.Draw(image)
    bounds = (left, y, right, y + height)
    draw.rounded_rectangle(bounds, 7, fill=PAPER if hide else fill, outline=color, width=3)
    if hide:
        label(draw, ((left + right) / 2, y + height / 2), "?", 35, color)
        return
    pitch = (right - left) / count
    for index in range(count):
        x = round(left + index * pitch)
        if asset:
            sprite(image, asset, x + pitch / 2, y + height / 2, (max(9, int(pitch * .82)), int(height * .82)))
        elif index:
            draw.line((x, y + 4, x, y + height - 4), fill=color, width=2 if index % 10 else 4)


def whole(a, b, *, unknown=None, asset=None, size=(660, 325)):
    image = card(size)
    draw = ImageDraw.Draw(image)
    w, h = size
    left, right, y = 34, w - 34, round(h * .44)
    split = round(left + (right - left) * a / (a + b))
    segment(image, left, split, y, a, asset=asset)
    segment(image, split, right, y, b, color=ORANGE, fill=GOLD, asset=asset, hide=unknown == "part")
    brace(draw, left, right, y - 15, "?" if unknown == "whole" else a + b, color=PINE)
    label(draw, ((left + split) / 2, y + 90), a)
    label(draw, ((split + right) / 2, y + 90), "?" if unknown == "part" else b, color=ORANGE)
    return image


def compare(a, b, *, mark="gap", unknown=None, gap_label=None, asset=None, size=(690, 390)):
    image = card(size)
    draw = ImageDraw.Draw(image)
    w, h = size
    left, right = round(w * .10), round(w * .85)
    pitch = (right - left) / max(a, b)
    end = lambda count: round(left + count * pitch)
    top, bottom, height = round(h * .30), round(h * .67), round(h * .15)
    draw.line((left, top - 8, left, bottom + height + 8), fill=INK, width=4)
    for idx, (y, amount) in enumerate(((top, a), (bottom, b))):
        if idx == 0:
            draw.ellipse((14, y + 9, left - 13, y + height - 9), fill=PINE)
        else:
            draw.polygon([(left / 2, y + 5), (14, y + height - 7), (left - 13, y + height - 7)], fill=ORANGE)
        segment(image, left, end(amount), y, amount, color=PINE if idx == 0 else ORANGE,
                fill=LEAF if idx == 0 else GOLD, height=height, asset=asset, hide=unknown == idx)
        label(draw, (round(w * .93), y + height / 2), "?" if unknown == idx else amount, 28)
    short = min(a, b)
    boundary = end(short)
    draw.line((boundary, top - 5, boundary, bottom + height + 6), fill=INK, width=3)
    if mark == "paired":
        frame(draw, (left - 4, top - 7, boundary + 2, bottom + height + 7))
    if mark == "long":
        y = top if a > b else bottom
        frame(draw, (left - 4, y - 7, end(max(a, b)) + 3, y + height + 7))
    if mark in {"gap", "reverse", "short"} and a != b:
        long_y, short_y = (top, bottom) if a > b else (bottom, top)
        far = end(max(a, b))
        if mark in {"gap", "reverse"}:
            frame(draw, (boundary + 2, long_y - 6, far + 3, long_y + height + 6))
        if mark in {"reverse", "short"}:
            for unit in range(short, max(a, b)):
                cx, cy = left + (unit + .5) * pitch, short_y + height / 2
                radius = max(3, min(pitch * .30, height * .26))
                draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=ORANGE, width=3)
            frame(draw, (boundary + 2, short_y - 6, far + 3, short_y + height + 6))
        if gap_label is not None:
            brace(draw, boundary + 1, far, top - 15, gap_label, color=ORANGE, size=30)
    return image


def quantity(count, asset, *, size=(465, 310)):
    image = card(size)
    draw = ImageDraw.Draw(image)
    w, h = size
    tens, singles = divmod(count, 10)
    if not tens:
        columns = min(5, count)
        rows = (count + columns - 1) // columns
        for i in range(count):
            row, col = divmod(i, columns)
            n = min(columns, count - row * columns)
            step = min(95, (w - 40) / columns)
            sprite(image, asset, w / 2 + (col - (n - 1) / 2) * step,
                   22 + (h - 78) * (row + .5) / rows, (int(step * .77), int((h - 88) * .70 / rows)))
    else:
        boxes = min(3, tens)
        for i in range(tens):
            row, col = divmod(i, boxes)
            y = 24 + row * 71
            pitch = (w - 34) / boxes
            x = 17 + pitch * col
            frame(draw, (x + 4, y, x + pitch - 4, y + 64), PINE, 3)
            for unit in range(10):
                urow, ucol = divmod(unit, 5)
                sprite(image, asset, x + pitch * (ucol + .5) / 5, y + 15 + urow * 31, (int(pitch / 6), 27))
        for i in range(singles):
            pitch = min(62, (w - 33) / singles)
            sprite(image, asset, w / 2 + (i - (singles - 1) / 2) * pitch, h - 74, (int(pitch * .78), 48))
    label(draw, (w / 2, h - 27), count, 35)
    return image


def alongside(first, second):
    result = card((first.width + second.width + 12, max(first.height, second.height) + 16))
    result.paste(first, (2, 8))
    result.paste(second, (first.width + 10, 8))
    return result


def chain(a, b, c, asset):
    image = card((745, 400))
    draw = ImageDraw.Draw(image)
    start = 55
    stop = lambda n: round(start + n * 590 / max(a, b, c))
    rows = (62, 173, 284)
    for i, (value, y) in enumerate(zip((a, b, c), rows, strict=True)):
        color, fill = (PINE, LEAF) if i != 1 else (ORANGE, GOLD)
        segment(image, start, stop(value), y, value, color=color, fill=fill, height=54)
        sprite(image, asset, 29, y + 28, (30, 36))
        label(draw, (690, y + 27), value, 31, color)
    brace(draw, stop(b), stop(a), rows[0] - 8, a - b, color=ORANGE, size=28)
    brace(draw, stop(b), stop(c), rows[2] - 8, c - b, color=ORANGE, size=28)
    end = stop(b)
    draw.line((end, rows[1] + 58, end, rows[2] - 12), fill=PINE, width=6)
    draw.polygon([(end - 10, rows[2] - 15), (end + 10, rows[2] - 15), (end, rows[2] + 1)], fill=PINE)
    return image


def pair_quantities(a, b, asset):
    return alongside(quantity(a, asset, size=(405, 300)), quantity(b, asset, size=(405, 300)))


def diagrams():
    yield "whole-pots", whole(11, 6, unknown="whole", asset="garden-pot"), ["whole-and-parts"]
    yield "part-pots", whole(11, 6, unknown="part", asset="garden-pot"), ["whole-and-parts"]
    yield "gap-pots", compare(11, 6, mark="reverse", asset="garden-pot"), ["one-gap-several-questions"]
    yield "shorter-markers", compare(27, 19, unknown=1, gap_label=8), ["known-shorter-or-longer"]
    yield "longer-seedlings", compare(18, 25, unknown=1, gap_label=7), ["known-shorter-or-longer"]
    yield "independent-total", whole(12, 8, asset="garden-marker"), ["two-questions-one-picture"]
    yield "independent-gap", compare(12, 8, asset="garden-marker", size=(650, 325)), ["two-questions-one-picture"]
    yield "dependent-reference", chain(37, 29, 34, "garden-tray"), ["carry-the-first-answer"]
    yield "dependent-combine", whole(17, 23), ["carry-the-first-answer"]
    yield "home-clips", compare(13, 8, mark="reverse", asset="garden-clip"), ["draw-your-own-comparison"]
    sort = "sort-by-what-is-missing"
    for key, im in [
        ("tray-whole", whole(4, 3, unknown="whole")),
        ("tray-part", whole(5, 3, unknown="part")),
        ("tray-gap", compare(6, 4, gap_label="?")),
        ("card-seeds-total", whole(7, 5, unknown="whole", asset="garden-seed-packet")),
        ("card-seeds-gap", compare(7, 5, gap_label="?", asset="garden-seed-packet")),
        ("card-seeds-part", whole(9, 7, unknown="part", asset="garden-seed-packet")),
        ("card-pots-gap", compare(17, 12, gap_label="?", asset="garden-pot")),
        ("card-markers-total", whole(6, 8, unknown="whole", asset="garden-marker")),
        ("card-twenty-part", whole(13, 7, unknown="part")),
        ("card-twenty-three-gap", compare(23, 15, gap_label="?")),
        ("card-nineteen-total", whole(10, 9, unknown="whole")),
        ("card-twenty-four-part", whole(11, 13, unknown="part")),
    ]:
        yield key, im, [sort]
    shots = "aim-at-the-matching-count"
    for key, im in [
        ("order-find-13", compare(9, 13, unknown=1, gap_label=4)),
        ("order-find-gap", compare(9, 13, gap_label="?")),
        ("order-find-27", compare(36, 27, unknown=1, gap_label=9)),
        ("order-find-63", whole(36, 27, unknown="whole")),
        ("order-west-27", compare(33, 27, unknown=1, gap_label=6)),
        ("order-south-35", compare(27, 35, unknown=1, gap_label=8)),
    ]:
        yield key, im, [shots]
    for n in (4, 9, 13, 27, 35, 39, 41, 45, 63):
        yield f"target-{n}", quantity(n, "garden-sprout"), [shots]
    yield "quiz-total-prompt", whole(14, 5, unknown="whole", asset="garden-sprout"), ["quiz-total"]
    yield "quiz-total-a", quantity(9, "garden-sprout"), ["quiz-total"]
    yield "quiz-total-b", whole(14, 5, asset="garden-sprout"), ["quiz-total"]
    yield "quiz-total-c", quantity(14, "garden-sprout"), ["quiz-total"]
    yield "quiz-difference-a", compare(22, 16, mark="paired", asset="garden-flower"), ["quiz-difference"]
    yield "quiz-difference-b", whole(22, 16, asset="garden-flower"), ["quiz-difference"]
    yield "quiz-difference-c", compare(22, 16, mark="gap", asset="garden-flower"), ["quiz-difference"]
    yield "quiz-unknown-group-prompt", compare(23, 27, unknown=1, gap_label=4), ["quiz-unknown-group"]
    for key, n in zip("abc", (27, 19, 4), strict=True):
        yield f"quiz-unknown-group-{key}", quantity(n, "garden-pinecone"), ["quiz-unknown-group"]
    for key, (a, b) in zip("abc", ((31, 9), (31, 22), (22, 9)), strict=True):
        yield f"quiz-dependence-{key}", pair_quantities(a, b, "garden-pot"), ["quiz-dependence"]
    for key, n in zip("abc", (32, 18, 26), strict=True):
        yield f"quiz-changed-reference-{key}", quantity(n, "garden-sprout"), ["quiz-changed-reference"]
    yield "quiz-same-gap-a", compare(15, 11, mark="short", asset="garden-clip"), ["quiz-same-gap"]
    yield "quiz-same-gap-b", whole(15, 11, unknown="whole", asset="garden-clip"), ["quiz-same-gap"]
    yield "quiz-same-gap-c", compare(15, 11, mark="long", asset="garden-clip"), ["quiz-same-gap"]


def main():
    manifest = ROOT / "asset-sources.json"
    document = json.loads(manifest.read_bytes())
    generator_sha = sha256(Path(__file__).read_bytes()).hexdigest()
    for name, image, uses in diagrams():
        path = ASSETS / (name + ".png")
        image.save(path, optimize=True)
        document["assets"][name] = {
            "path": str(path.relative_to(ROOT)), "sha256": sha256(path.read_bytes()).hexdigest(),
            "source": "exact_quantity_diagram", "diagramSource": "diagrams.py",
            "diagramSourceSha256": generator_sha, "usedBy": uses, "visualReview": "pending",
        }
    manifest.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
