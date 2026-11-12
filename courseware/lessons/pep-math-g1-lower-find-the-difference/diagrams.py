"""Compose exact quantities and equal-origin diagrams from this lesson's sprites."""

from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CREAM = "#fff5df"
INK = "#253e34"
GREEN = "#3e7261"
ORANGE = "#bd613b"
GOLD = "#efb65d"
GRID = "#e7c89d"
ROWS = ("#e7ead5", "#f7e1b8")
SORT_LEVELS = ((8, 5), (9, 13), (16, 11))
MARBLE_ORDERS = {
    "order-9-5": (9, 5),
    "order-8-6": (8, 6),
    "order-14-8": (8, 14),
    "order-13-8": (13, 8),
    "order-31-23": (31, 23, 27),
    "order-34-25": (34, 25, 29),
    "order-27-20": (27, 20, 22),
}


def paper(size):
    image = Image.new("RGB", size, CREAM)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, size[0] - 5, size[1] - 5), 22, outline=GRID, width=3)
    return image


def sprite(image, asset, center, size):
    with Image.open(ASSETS / (asset + ".png")) as raw:
        fitted = ImageOps.contain(raw.convert("RGBA"), size, Image.Resampling.LANCZOS)
    x, y = center
    image.paste(fitted, (round(x - fitted.width / 2), round(y - fitted.height / 2)), fitted)


def numeral(draw, value, position, size=35, color=INK):
    draw.text(position, str(value), font=ImageFont.load_default(size=size), anchor="mm", fill=color)


def tag(draw, index, x, y, radius):
    if index == 0:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GREEN, outline=INK, width=2)
    elif index == 1:
        draw.polygon([(x, y - radius), (x - radius, y + radius), (x + radius, y + radius)], fill=GOLD, outline=INK)
    else:
        draw.rounded_rectangle((x - radius, y - radius, x + radius, y + radius), radius // 4, fill="#b9866d", outline=INK, width=2)


def bracket(draw, x0, x1, y0, y1, color=ORANGE, width=5):
    draw.rounded_rectangle((x0, y0, x1, y1), radius=9, outline=color, width=width)


def comparison(counts, *, mode="plain", asset=None, numbers=False, connected=True, size=(760, 420)):
    """Represent each unit at a common scale and the unmatched segment at the actual end."""
    image = paper(size)
    draw = ImageDraw.Draw(image)
    width, height = size
    left = round(width * .12)
    right = round(width * (.85 if numbers else .93))
    long, short = max(counts[:2]), min(counts[:2])
    pitch = (right - left) / max(counts)
    rows = [round(height * (.34 + index * .35)) for index in range(2)] if len(counts) == 2 else [
        round(height * (.22 + index * .27)) for index in range(3)]
    half = round(height * (.103 if len(counts) == 2 else .081))
    x = lambda index: round(left + index * pitch)
    col = lambda index: round(left + (index + .5) * pitch)
    short_row = 0 if counts[0] < counts[1] else 1
    long_row = 1 - short_row
    draw.line((left, rows[0] - half - 9, left, rows[-1] + half + 9), fill=INK, width=4)
    for i, (amount, y) in enumerate(zip(counts, rows, strict=True)):
        tag(draw, i, round(left * .50), y, max(10, half // 2))
        draw.rounded_rectangle((left, y - half, x(amount), y + half), radius=5,
                               fill=ROWS[i % len(ROWS)], outline=INK, width=2)
        for unit in range(amount):
            if asset:
                sprite(image, asset, (col(unit), y), (max(8, int(pitch * .82)), int(half * 1.62)))
            else:
                draw.line((x(unit), y - half + 2, x(unit), y + half - 2),
                          fill=GREEN, width=3 if unit % 10 == 0 else 1)
        if numbers:
            numeral(draw, amount, (round(width * .925), y), max(21, half))
    if connected:
        for unit in range(short):
            draw.line((col(unit), rows[0] + half + 1, col(unit), rows[1] - half - 1), fill=GREEN, width=2)
    if mode in {"short", "reverse"}:
        y = rows[short_row]
        for unit in range(short, long):
            radius = max(4, min(int(pitch * .35), half - 3))
            draw.ellipse((col(unit) - radius, y - radius, col(unit) + radius, y + radius),
                         outline=ORANGE, width=3)
    if mode == "equal":
        bracket(draw, left - 4, x(short) + 2, rows[0] - half - 7, rows[1] + half + 7)
    if mode in {"gap", "reverse"}:
        y = rows[long_row]
        bracket(draw, x(short) + 2, x(long) + 3, y - half - 6, y + half + 6)
    if mode in {"short", "reverse"}:
        y = rows[short_row]
        bracket(draw, x(short) + 2, x(long) + 3, y - half - 6, y + half + 6)
    if mode == "whole":
        bracket(draw, left - 4, x(long) + 4, rows[0] - half - 7, rows[1] + half + 7)
    if mode == "whole-rows":
        for y in rows:
            bracket(draw, left - 4, x(long) + 4, y - half - 6, y + half + 6)
    if mode == "compare-first-two":
        bracket(draw, round(left * .13), x(long) + 3, rows[0] - half - 11, rows[1] + half + 11, GREEN, 4)
    return image


def quantity(asset, count, *, size=(420, 300), by_tens=False):
    image = paper(size)
    draw = ImageDraw.Draw(image)
    width, height = size
    if by_tens:
        full, loose = divmod(count, 10)
        columns = max(full, loose, 1)
        step = (width - 50) / columns
        for i in range(full):
            x = round(25 + (i + .5) * step)
            bracket(draw, x - 21, x + 21, 49, height // 2, GREEN, 4)
            numeral(draw, 10, (x, round(height * .33)), 28)
        for i in range(loose):
            sprite(image, asset, (25 + (i + .5) * step, round(height * .71)), (min(53, round(step - 5)), 58))
        return image
    columns = min(5, count)
    rows = (count + columns - 1) // columns
    cell_w, cell_h = (width - 50) / columns, (height - 42) / rows
    for i in range(count):
        row, col = divmod(i, columns)
        row_count = min(columns, count - row * columns)
        sprite(image, asset, (width / 2 + (col - (row_count - 1) / 2) * cell_w, 21 + (row + .5) * cell_h),
               (round(cell_w * .88), round(cell_h * .81)))
    return image


def grouped_kites(selected=None):
    image = paper((560, 410))
    draw = ImageDraw.Draw(image)
    for row, count in enumerate((10, 6, 9)):
        y = 75 + row * 128
        tag(draw, row, 43, y, 18)
        for i in range(count):
            sprite(image, "quiz-kite", (99 + i * 42, y), (36, 56))
        if selected is not None and row in selected:
            bracket(draw, 16, 534, y - 45, y + 45, GREEN, 6)
    return image


def composed_check(left, right, target):
    image = paper((610, 365))
    draw = ImageDraw.Draw(image)
    origin, step = 39, 12
    for amount, offset, y, color in [(target, 0, 90, GREEN), (left, 0, 222, GREEN), (right, left, 222, ORANGE)]:
        start, end = origin + offset * step, origin + (offset + amount) * step
        draw.rounded_rectangle((start, y, end, y + 48), 5, fill=ROWS[color == ORANGE], outline=color, width=4)
        for index in range(1, amount):
            x = start + index * step
            draw.line((x, y + 5, x, y + 43), fill=color, width=1)
        numeral(draw, amount, ((start + end) // 2, y + 83), 32, color)
    draw.line((origin + target * step, 80, origin + target * step, 280), fill=INK, width=3)
    sprite(image, "quiz-rhythm", (542, 102), (85, 65))
    return image


def images():
    yield "camp-counts", comparison((11, 7), asset="camp-chair", numbers=True, connected=False), ["two-camps"]
    yield "chair-pairs", comparison((11, 7), mode="gap", asset="camp-chair", numbers=True), ["match-the-chairs"]
    yield "chair-reverse", comparison((11, 7), mode="reverse", asset="camp-chair", numbers=True), ["reverse-the-question"]
    yield "three-lamp-tags", comparison((36, 28, 23), mode="compare-first-two", numbers=True, connected=False), ["choose-two-counts"]
    yield "home-example", comparison((15, 10), mode="reverse", asset="camp-lantern", numbers=True), ["say-it-at-home"]
    yield "tray-paired", comparison((4, 4), mode="equal", size=(290, 250)), ["sort-the-pairing-cards"]
    yield "tray-gap", comparison((5, 3), mode="gap", size=(290, 250)), ["sort-the-pairing-cards"]
    for level, counts in enumerate(SORT_LEVELS, 1):
        for mode in ("equal", "gap", "short"):
            if mode != "short" or level == 3:
                yield f"pair-card-{level}-{mode}", comparison(counts, mode=mode, size=(380, 300)), ["sort-the-pairing-cards"]
    for name, counts in MARBLE_ORDERS.items():
        mode = "compare-first-two" if len(counts) == 3 else "plain"
        yield name, comparison(counts, mode=mode, asset="camp-lantern" if len(counts) == 2 else None,
                               numbers=True, connected=len(counts) == 2, size=(520, 390)), ["light-the-gap"]
    for count in (2, 4, 5, 6, 7, 8, 9):
        yield f"lamp-target-{count}", quantity("camp-lantern", count, size=(360, 252)), ["light-the-gap"]
    yield "quiz-kite-prompt", grouped_kites(), ["choose-kite-groups"]
    for key, pair in zip("abc", [(0, 2), (0, 1), (1, 2)], strict=True):
        yield f"quiz-kite-{key}", grouped_kites(pair), ["choose-kite-groups"]
    for key, mode in zip("abc", ["equal", "whole", "gap"], strict=True):
        yield f"quiz-patch-{key}", comparison((13, 8), mode=mode, asset="quiz-patch"), ["patch-gap"]
    yield "quiz-clip-prompt", comparison((18, 14), asset="quiz-clip", numbers=True), ["clip-difference"]
    for key, count in zip("abc", [4, 14, 32], strict=True):
        yield f"quiz-clip-{key}", quantity("quiz-clip", count, by_tens=count >= 10), ["clip-difference"]
    for key, mode in zip("abc", ["equal", "reverse", "whole-rows"], strict=True):
        yield f"quiz-flag-{key}", comparison((19, 12), mode=mode, asset="quiz-flag"), ["reverse-flags"]
    yield "quiz-book-prompt", comparison((30, 24, 21), asset="quiz-book", numbers=True, connected=False), ["book-shelves"]
    for key, count in zip("abc", [9, 54, 6], strict=True):
        yield f"quiz-book-{key}", quantity("quiz-book", count, by_tens=count >= 10), ["book-shelves"]
    for key, parts in zip("abc", [(16, 11), (16, 10), (27, 16)], strict=True):
        yield f"quiz-rhythm-{key}", composed_check(*parts, 27), ["check-rhythm"]


def main():
    manifest_path = ROOT / "asset-sources.json"
    manifest = json.loads(manifest_path.read_text())
    source_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    for key, image, uses in images():
        path = ASSETS / (key + ".png")
        image.save(path, optimize=True)
        manifest["assets"][key] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "source": "exact_quantity_diagram",
            "diagramSource": "diagrams.py",
            "diagramSourceSha256": source_hash,
            "usedBy": uses,
            "visualReview": "pending",
        }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
