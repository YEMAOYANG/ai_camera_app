"""Draw paired observations of each unchanged model paper sample."""

from math import cos, radians, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render import FAIR, basin, board


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MESHES = {
    "kraft": (
        (198, 151, 92),
        ((0, 4, 17, 23, 58), (4, 7, 25, 11, 19), (1, 10, 29, 9, 1),
         (3, 23, 15, 3, 3), (18, 12, 3, 0, 3)),
        (((0, 4), (1, 3), (2, 2), (2, 1), (2, 0)),),
    ),
    "news": (
        (215, 216, 209),
        ((1, 1, 10, 9, 26), (3, 3, 17, 3, 29), (2, 15, 10, 4, 24),
         (14, 9, 2, 13, 24), (32, 5, 3, 9, 30)),
        (((0, 4), (1, 3), (2, 2), (2, 1)), ((3, 1), (3, 2), (3, 3), (3, 4))),
    ),
    "print": (
        (248, 240, 219),
        ((16, 6, 12, 2, 1), (21, 12, 3, 10, 4), (51, 12, 22, 8, 2),
         (25, 12, 2, 11, 3), (12, 4, 10, 3, 1)),
        (((0, 2), (1, 2), (2, 2), (3, 1), (4, 0)), ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4))),
    ),
}


def paper_view(sample, from_above):
    """The two cameras project the same vertices, marks, and creases."""
    color, heights, creases = MESHES[sample]
    image, draw = board((416, 304))
    elevation = radians(90 if from_above else 19)

    def project(col, row):
        x = 57 + 76 * col + (row - 2) * 2
        y = 153 + (row - 2) * 51 * sin(elevation)
        return round(x), round(y - heights[row][col] * cos(elevation) * 1.55)

    def blend(a, b, amount):
        return tuple(round(v + (w - v) * amount) for v, w in zip(a, b))

    if not from_above:
        draw.ellipse((40, 146, 376, 211), fill="#c7c9ac")
    edges = []
    for row in range(4):
        for col in range(4):
            corners = (project(col, row), project(col + 1, row),
                       project(col + 1, row + 1), project(col, row + 1))
            tilt = heights[row][col] + heights[row][col + 1] - heights[row + 1][col] - heights[row + 1][col + 1]
            shade = max(-29, min(23, tilt))
            paint = tuple(min(255, max(0, value + shade)) for value in color)
            draw.polygon(corners, fill=paint)
            if sample == "news" and (row, col) in {(0, 0), (0, 1), (1, 1), (1, 3), (2, 2), (2, 3), (3, 0), (3, 2)}:
                left, right, bottom_right, bottom_left = corners
                for fraction in (.26, .46, .66):
                    a = blend(left, bottom_left, fraction)
                    b = blend(right, bottom_right, fraction)
                    draw.line((blend(a, b, .17), blend(a, b, .78)), fill="#77786d", width=3)
            if row == 0:
                edges.append(corners[:2])
            if row == 3:
                edges.append(corners[2:])
            if col == 0:
                edges.append((corners[0], corners[3]))
            if col == 3:
                edges.append((corners[1], corners[2]))
    for edge in edges:
        draw.line(edge, fill="#73634b", width=2)
    for crease in creases:
        draw.line([project(*point) for point in crease], fill="#9a7f61", width=3)
    return image


def pull_test(sample):
    """Same holders and strip width; display the observed break only."""
    image, draw = board((416, 304))
    colors = {"tissue": "#f5efdb", "news": "#d6d7cd", "kraft": "#d3a061"}
    color = colors[sample]
    if sample == "kraft":
        draw.rectangle((64, 133, 352, 169), fill=color, outline="#786547", width=3)
    else:
        draw.polygon(((64, 133), (179, 133), (168, 143), (181, 152), (170, 169), (64, 169)),
                     fill=color, outline="#786547", width=3)
        draw.polygon(((238, 133), (352, 133), (352, 169), (230, 169), (243, 157), (230, 148)),
                     fill=color, outline="#786547", width=3)
    if sample == "news":
        for x in (101, 125, 148, 260, 285, 310):
            for y in (143, 151, 159):
                draw.line((x, y, x + 12, y), fill="#7f847c", width=2)
    for x in (50, 348):
        draw.rounded_rectangle((x, 112, x + 20, 190), 6, fill="#526a5b", outline="#31473d", width=2)
    return image


def compose(keys, panel_size=(274, 212), *, camera=None):
    width, height = panel_size
    head = 105 if camera else 32
    image = Image.new("RGB", (len(keys) * (width + 20) + 20, height + head + 22), "#fff5df")
    draw = ImageDraw.Draw(image)
    for index, key in enumerate(keys):
        x = index * (width + 20) + 20
        with Image.open(ASSETS / f"{key}.png") as panel:
            card = ImageOps.contain(panel.convert("RGB"), (width, height))
            image.paste(card, (x + (width - card.width) // 2, head + (height - card.height) // 2))
        if index and not camera:
            draw.ellipse((x - 17, head + height // 2 - 5, x - 7, head + height // 2 + 5), fill="#68816c")
    if camera:
        with Image.open(ASSETS / f"{camera}.png") as panel:
            card = ImageOps.fit(panel.convert("RGB"), (105, 82))
            image.paste(card, ((image.width - 105) // 2, 11))
    return image


def render():
    for sample in MESHES:
        paper_view(sample, True).save(ASSETS / f"paper-top-{sample}.png", optimize=True)
        paper_view(sample, False).save(ASSETS / f"paper-side-{sample}.png", optimize=True)
    for sample in ("tissue", "news", "kraft"):
        pull_test(sample).save(ASSETS / f"quiz-bag-{sample}.png", optimize=True)
    family, _ = board((496, 373))
    family.paste(basin(FAIR), (20, 20))
    family.save(ASSETS / "paper-family-record.png", optimize=True)
    compose(["paper-top-kraft", "paper-side-kraft"], camera="paper-observer-camera").save(
        ASSETS / "paper-photo-cover.png", optimize=True)
    compose(["paper-scout-idle", "paper-scraps", "paper-pulp"]).save(
        ASSETS / "paper-route-cover.png", optimize=True)
    compose(["paper-scraps", "paper-pulp", "paper-on-mesh", "paper-dry"]).save(
        ASSETS / "paper-making-sequence.png", optimize=True)
    with Image.open(ASSETS / "paper-dry.png") as dry:
        ImageOps.contain(dry, (160, 160)).save(ASSETS / "paper-made-badge.png", optimize=True)


if __name__ == "__main__":
    render()
