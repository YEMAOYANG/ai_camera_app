"""Draw the lesson's countable materials, contact faces, and common baselines."""

from dataclasses import dataclass
import json
from math import ceil, hypot, sqrt
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


LESSON = Path(__file__).resolve().parent
ASSETS = LESSON / "assets"
PAPER = "#fff5e4"
PANEL = "#f7e6c8"
INK = "#263c34"
TEAL = "#64a591"
MINT = "#8ab79a"
AMBER = "#e0a350"
APRICOT = "#e48858"
PLUM = "#a688a5"
BLUE = "#80a9bb"
CONTACT = "#c56736"


@dataclass(frozen=True)
class Piece:
    key: str
    kind: str
    size: tuple[float, float, float]
    color: str

    def pose(self, x, y, z, axes=(0, 1, 2)):
        return self, (x, y, z), tuple(self.size[axis] for axis in axes)


RAILS = tuple(Piece(f"rail-{i}", "block", (0.74, 0.74, 2.0), PLUM) for i in range(3))
BOARDS = tuple(Piece(f"board-{i}", "block", (4.7, 2.9, 0.72), TEAL) for i in range(3))
BRICK = Piece("brick", "block", (3.2, 2.9, 1.12), AMBER)
CUBE = Piece("cube", "block", (1.62, 1.62, 1.62), APRICOT)
CYLINDER = Piece("cylinder", "cylinder", (2.9, 2.9, 0.82), BLUE)
BALL = Piece("ball", "sphere", (2.2, 2.2, 2.2), AMBER)
MATERIALS = (*RAILS, *BOARDS, BRICK, CUBE, CYLINDER, BALL)
PAD_CONTACT_RADIUS = .28


def cradle(z):
    # Equal-height supports surround the open center. The sphere settles
    # slightly between their upper inner edges, without touching the surface below.
    pads = ((-.65, -.12), (.14, -.65), (.538, .594))
    radius = BALL.size[2] / 2
    sink = radius - sqrt(radius**2 - PAD_CONTACT_RADIUS**2)
    return [
        *(rail.pose(x, y, z) for rail, (x, y) in zip(RAILS, pads)),
        BALL.pose(0, 0, z + RAILS[0].size[2] - sink),
    ]


def bases():
    legs_and_cap = [
        BOARDS[0].pose(-1.70, 0, 0, (2, 1, 0)),
        BOARDS[1].pose(1.70, 0, 0, (2, 1, 0)),
        BOARDS[2].pose(0, 0, 4.7),
    ]
    flat = [piece.pose(0, 0, i * 0.72) for i, piece in enumerate(BOARDS)]
    thin_stack = [piece.pose(0, 0, i * 4.7, (2, 1, 0)) for i, piece in enumerate(BOARDS)]
    return flat, thin_stack, legs_and_cap


def full_build(base):
    base_top = max(position[2] + size[2] for _, position, size in base)
    cube_top = base_top + CUBE.size[2]
    brick_top = cube_top + BRICK.size[2]
    return [
        *base, CUBE.pose(0, 0, base_top), BRICK.pose(0, 0, cube_top),
        CYLINDER.pose(0, 0, brick_top), *cradle(brick_top + CYLINDER.size[2]),
    ]


def canvas(width=648, height=430):
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, width - 13, height - 13), radius=25, fill=PANEL)
    return image


def mix(color, target, amount):
    a = bytes.fromhex(color[1:])
    b = bytes.fromhex(target[1:])
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def project(position, origin, scale):
    x, y, z = position
    return origin[0] + (x - y) * scale * 0.78, origin[1] + ((x + y) * 0.31 - z) * scale


def polygon(draw, points, fill):
    draw.polygon(points, fill=fill)
    draw.line([*points, points[0]], fill=INK, width=2, joint="curve")


def draw_piece(draw, pose, origin, scale, *, outline_contact=False):
    piece, (x, y, z), (width, depth, height) = pose
    p = lambda dx, dy, dz: project((x + dx, y + dy, z + dz), origin, scale)
    color = piece.color
    if piece.kind == "sphere":
        cx, cy = p(0, 0, height / 2)
        radius = width * scale / 2
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill=color, outline=INK, width=2)
        draw.ellipse((cx - radius * .54, cy - radius * .65, cx - radius * .06, cy - radius * .2),
                     fill=mix(color, "#fff4d0", .67))
        return
    if piece.kind == "cylinder":
        cx, lower = p(0, 0, 0)
        _, upper = p(0, 0, height)
        rx, ry = width * scale * .56, depth * scale * .22
        draw.rectangle((cx - rx, upper, cx + rx, lower), fill=color)
        draw.ellipse((cx - rx, lower - ry, cx + rx, lower + ry), fill=color)
        draw.arc((cx - rx, lower - ry, cx + rx, lower + ry), 0, 180, fill=INK, width=2)
        draw.line((cx - rx, upper, cx - rx, lower), fill=INK, width=2)
        draw.line((cx + rx, upper, cx + rx, lower), fill=INK, width=2)
        draw.ellipse((cx - rx, upper - ry, cx + rx, upper + ry),
                     fill=mix(color, "#fff4d0", .35), outline=INK, width=2)
        return
    a, b, c, d = [(-width / 2, -depth / 2), (width / 2, -depth / 2),
                  (width / 2, depth / 2), (-width / 2, depth / 2)]
    top = [p(*corner, height) for corner in (a, b, c, d)]
    bottom = [p(*corner, 0) for corner in (a, b, c, d)]
    polygon(draw, [top[1], top[2], bottom[2], bottom[1]], mix(color, "#29483c", .30))
    polygon(draw, [top[2], top[3], bottom[3], bottom[2]], color)
    polygon(draw, top, mix(color, "#fff4d0", .32))
    if outline_contact:
        draw.line((bottom[1], bottom[2], bottom[3]), fill=CONTACT, width=6, joint="curve")


def draw_model(draw, poses, origin, scale):
    for pose in sorted(poses, key=lambda row: (row[1][2], row[1][0] + row[1][1])):
        draw_piece(draw, pose, origin, scale)


def baseline(draw, x, y, width):
    draw.line((x, y, x + width, y), fill=INK, width=4)


def model_panel(models, *, scale, width=648, height=430, contact=False, floor_reserve=35):
    image = canvas(width, height)
    draw = ImageDraw.Draw(image)
    floor_depth = max(
        x + y + (w + d) / 2
        for model in models for _, (x, y, z), (w, d, _) in model if z == 0
    )
    floor = height - 14 - max(floor_reserve, ceil(floor_depth * .31 * scale))
    baseline(draw, 30, floor, width - 60)
    for index, model in enumerate(models):
        center = width * (index + .5) / len(models)
        if contact:
            draw_piece(draw, model[0], (center, floor), scale, outline_contact=True)
        else:
            draw_model(draw, model, (center, floor), scale)
    return image


def tray(pieces, *, size=(750, 450), columns=5):
    width, height = size
    image = canvas(width, height)
    draw = ImageDraw.Draw(image)
    columns = min(columns, len(pieces))
    rows = (len(pieces) + columns - 1) // columns
    cell_w, cell_h = (width - 40) / columns, (height - 36) / rows
    for index, piece in enumerate(pieces):
        col, row = index % columns, index // columns
        x, y = 20 + col * cell_w, 18 + row * cell_h
        draw.rounded_rectangle((x + 4, y + 7, x + cell_w - 4, y + cell_h - 7),
                               radius=14, fill=PAPER)
        draw_piece(draw, piece.pose(0, 0, 0), (x + cell_w / 2, y + cell_h * .66),
                   min(37, cell_w / 6.3))
    return image


def pair_panel(left, right):
    panel = canvas(850, 430)
    for image, origin_x in ((left, 18), (right, 426)):
        fitted = ImageOps.contain(image, (406, 390))
        panel.paste(fitted, (origin_x + (406 - fitted.width) // 2, (430 - fitted.height) // 2))
    return panel


def arrow(draw, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    n = hypot(dx, dy)
    ux, uy = dx / n, dy / n
    bx, by = end[0] - ux * 23, end[1] - uy * 23
    draw.line((start, (bx, by)), fill=INK, width=7)
    draw.polygon((end, (bx - uy * 12, by + ux * 12), (bx + uy * 12, by - ux * 12)), fill=INK)


def overhead(blocks, arrows):
    image = canvas()
    draw = ImageDraw.Draw(image)
    cx, cy = 324, 215
    draw.rounded_rectangle((103, 45, 545, 385), radius=25, fill="#e4bf89", outline=INK, width=3)
    for left, top, right, bottom in blocks:
        draw.rounded_rectangle((cx + left, cy + top, cx + right, cy + bottom),
                               radius=6, fill=TEAL, outline=INK, width=3)
    draw.ellipse((cx - 31, cy - 31, cx + 31, cy + 31), fill=AMBER, outline=INK, width=3)
    for dx, dy in arrows:
        arrow(draw, (cx + dx * .29, cy + dy * .29), (cx + dx, cy + dy))
    return image


def cylinder_support(pose):
    image = canvas()
    draw = ImageDraw.Draw(image)
    x, floor = 324, 357
    baseline(draw, 104, floor, 440)
    if pose == "side":
        draw.rounded_rectangle((214, 261, 416, 356), radius=23, fill=BLUE, outline=INK, width=3)
        draw.ellipse((392, 261, 445, 356), fill="#bbd1d1", outline=INK, width=3)
        slab_bottom = 261
    else:
        top, bottom = 166, 347
        draw.rectangle((276, top, 372, bottom), fill=BLUE)
        draw.line((276, top, 276, bottom), fill=INK, width=3)
        draw.line((372, top, 372, bottom), fill=INK, width=3)
        draw.ellipse((276, bottom - 10, 372, bottom + 9), fill=BLUE, outline=INK, width=3)
        draw.ellipse((276, top - 8, 372, top + 8), fill="#bbd1d1", outline=INK, width=3)
        slab_bottom = 158 if pose == "face" else 115
    draw.rounded_rectangle((177, slab_bottom - 30, 471, slab_bottom),
                           radius=6, fill=MINT, outline=INK, width=3)
    return image


QUIZ_BOX = Piece("quiz-box", "block", (4.2, 2.8, 1.1), BLUE)
QUIZ_Q3_WALLS = ((-95, -85, -65, 85), (-65, -85, 107, -58), (-65, 58, 107, 85))
QUIZ_Q4 = (Piece("mint-thin", "block", (3.1, 1.8, 0.55), MINT),
           Piece("apricot-cube", "block", (1.35, 1.35, 1.35), APRICOT),
           Piece("plum-tall", "block", (1.22, 1.1, 2.45), PLUM),
           Piece("blue-cylinder", "cylinder", (1.2, 1.2, 0.72), BLUE),
           Piece("short-teal", "block", (1.95, 1.32, 0.96), TEAL))
QUIZ_Q5 = (Piece("floor-tile", "block", (3.8, 2.4, .6), MINT),
           Piece("column", "block", (2.85, 1.56, 1.05), BLUE),
           Piece("slab", "block", (2.2, 1.5, .9), AMBER))
QUIZ_Q6 = (Piece("wide", "block", (4.4, 2.5, .75), AMBER),
           Piece("long", "block", (3.3, 1.32, .96), APRICOT),
           Piece("medium", "block", (2.6, 1.25, .85), PLUM),
           Piece("thin", "block", (2.2, 1.45, .64), TEAL))


def stack(pieces, axes):
    z = 0
    result = []
    for piece, axis in zip(pieces, axes, strict=True):
        pose = piece.pose(0, 0, z, axis)
        result.append(pose)
        z += pose[2][2]
    return result


FLAT = (0, 1, 2)
TALL = (2, 1, 0)
QUIZ_BOX_ORIENTATIONS = ((0, 2, 1), FLAT, TALL)


def quiz_towers():
    height_only = (
        stack(QUIZ_Q5, (FLAT, TALL, FLAT)),
        stack(QUIZ_Q5, (FLAT, FLAT, FLAT)),
        stack(QUIZ_Q5, (FLAT, TALL, TALL)),
    )
    height_and_inventory = (
        stack(QUIZ_Q6, (FLAT, TALL, FLAT, FLAT)),
        stack(QUIZ_Q6, (FLAT, FLAT, FLAT, FLAT)),
        stack(QUIZ_Q6[:3], (FLAT, TALL, TALL)),
    )
    return height_only, height_and_inventory


def geometry_assets():
    flat, thin, capped = bases()
    low, high = full_build(flat), full_build(capped)
    paired = ((-79, -65, -48, 65), (48, -65, 79, 65))
    q5_models, q6_models = quiz_towers()
    assets = {
        "bench-model": model_panel(([BALL.pose(0, 0, 0)], capped), scale=51),
        "material-tray": tray(MATERIALS),
        "roll-flat": overhead((), ((0, 140), (0, -140), (140, 0), (-140, 0))),
        "roll-side-rails": overhead(paired, ((0, 140), (0, -140))),
        "base-comparison": model_panel((flat, thin, capped), scale=24, width=840),
        "ball-support": model_panel((cradle(0),), scale=79),
        "remaining-six": tray((*BOARDS, BRICK, CUBE, CYLINDER)),
        "height-comparison": model_panel((low, high), scale=34, width=810, height=530),
        "q2-a": cylinder_support("face"), "q2-b": cylinder_support("side"), "q2-c": cylinder_support("gap"),
        "q4-stimulus": pair_panel(tray(QUIZ_Q4, size=(530, 460), columns=3),
            model_panel((stack(QUIZ_Q4[:4], (FLAT, FLAT, FLAT, FLAT)),), scale=55)),
        "q5-compare": model_panel(q5_models, scale=43, width=825),
    }
    for letter, axes in zip("abc", QUIZ_BOX_ORIENTATIONS):
        assets[f"q1-{letter}"] = model_panel(
            ([QUIZ_BOX.pose(0, 0, 0, axes)],), scale=61, contact=True, floor_reserve=67)
    for letter, direction in zip("abc", ((-54, 0), (0, -54), (54, 0))):
        assets[f"q3-{letter}"] = overhead(QUIZ_Q3_WALLS, (direction,))
    for letter, item in zip("abc", (QUIZ_Q4[1], QUIZ_Q4[-1], QUIZ_Q4[3])):
        assets[f"q4-{letter}"] = model_panel(([item.pose(0, 0, 0)],), scale=92)
    for letter, model in zip("abc", q5_models):
        assets[f"q5-{letter}"] = model_panel((model,), scale=43)
    for letter, model in zip("abc", q6_models):
        image = model_panel((model,), scale=43)
        if letter == "c":
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((464, 298, 601, 372), radius=13, fill=PAPER, outline=INK, width=3)
            draw_piece(draw, QUIZ_Q6[-1].pose(0, 0, 0), (535, 346), 26)
        assets[f"q6-{letter}"] = image
    return assets


HOP_ICON_SIZE = (120, 96)
HOP_FLOOR = 80
HOP_SCALE = 13
HOP_PALETTE = {"琥珀色": AMBER, "青绿色": TEAL, "淡紫色": PLUM, "淡蓝色": BLUE}


def hop_cuboid(draw, spec, color):
    width, depth, height = (spec["size"][axis] * HOP_SCALE for axis in spec["axes"])
    depth_x, depth_y = .48 * depth, -.32 * depth
    left = (HOP_ICON_SIZE[0] - width - depth_x) / 2
    front_left, front_right = (left, HOP_FLOOR), (left + width, HOP_FLOOR)
    back_right = (front_right[0] + depth_x, HOP_FLOOR + depth_y)
    top_front_left = (left, HOP_FLOOR - height)
    top_front_right = (front_right[0], top_front_left[1])
    top_back_right = (back_right[0], top_front_left[1] + depth_y)
    top_back_left = (left + depth_x, top_back_right[1])
    polygon(draw, [top_front_right, top_back_right, back_right, front_right],
            mix(color, "#29483c", .29))
    polygon(draw, [top_front_left, top_front_right, front_right, front_left], color)
    polygon(draw, [top_front_left, top_back_left, top_back_right, top_front_right],
            mix(color, "#fff4d0", .32))


def hop_cylinder(draw, spec, color):
    diameter = spec["diameter"] * HOP_SCALE
    length = spec["axialLength"] * HOP_SCALE
    center = HOP_ICON_SIZE[0] / 2
    face_color = mix(color, "#fff4d0", .36)
    if spec["orientation"] == "upright":
        rx, ry = diameter / 2, diameter * .2
        bottom = HOP_FLOOR - ry
        top = bottom - length
        draw.ellipse((center-rx, bottom-ry, center+rx, HOP_FLOOR), fill=color, outline=INK, width=2)
        draw.rectangle((center-rx, top, center+rx, bottom), fill=color)
        draw.line((center-rx, top, center-rx, bottom), fill=INK, width=2)
        draw.line((center+rx, top, center+rx, bottom), fill=INK, width=2)
        draw.ellipse((center-rx, top-ry, center+rx, top+ry), fill=face_color, outline=INK, width=2)
    elif spec["orientation"] == "side":
        left, right = center - length / 2, center + length / 2
        top = HOP_FLOOR - diameter
        rx = diameter * .22
        draw.ellipse((left-rx, top, left+rx, HOP_FLOOR), fill=color, outline=INK, width=2)
        draw.rectangle((left, top, right, HOP_FLOOR), fill=color)
        draw.line((left, top, right, top), fill=INK, width=2)
        draw.line((left, HOP_FLOOR, right, HOP_FLOOR), fill=INK, width=2)
        draw.ellipse((right-rx, top, right+rx, HOP_FLOOR), fill=face_color, outline=INK, width=2)
    else:
        raise ValueError("unknown cylinder posture")


def hop_geometry_assets():
    """Render only the p03 knowledge diagrams declared in the lesson brief."""
    brief = json.loads((LESSON / "brief.json").read_text(encoding="utf-8"))
    plan = next(page["game"]["artPlan"] for page in brief["pageSequence"] if page["key"] == "p03")
    assets = {}
    for key, item in plan.items():
        if item["kind"] != "deterministic-geometry":
            continue
        spec = item["spec"]
        image = Image.new("RGBA", HOP_ICON_SIZE)
        draw = ImageDraw.Draw(image)
        draw.line((9, HOP_FLOOR + 1, 111, HOP_FLOOR + 1), fill=INK, width=4)
        renderer = {"cuboid": hop_cuboid, "cylinder": hop_cylinder}[spec["shape"]]
        renderer(draw, spec, HOP_PALETTE[spec["color"]])
        assets[key] = image
    return assets


def support_depot_assets():
    """Small matching illustrations of the same ball on different supports."""
    board = BOARDS[0].pose(0, 0, 0)
    ball_on_board = BALL.pose(0, 0, BOARDS[0].size[2])
    rails = [
        rail.pose(x, 0, BOARDS[0].size[2], (0, 2, 1))
        for rail, x in zip(RAILS, (-1.41, 1.41))
    ]
    row = [rail.pose(x, -x, 0) for rail, x in zip(RAILS, (-.74, 0, .74))]
    centered = cradle(0)
    turned = [
        (piece, (-y, x, z), size)
        for piece, (x, y, z), size in centered
    ]
    models = {
        "depot-flat": [board, ball_on_board],
        "depot-rails": [board, *rails, ball_on_board],
        "depot-row": [*row, BALL.pose(0, 0, RAILS[0].size[2])],
        "depot-cradle": centered,
        "depot-cradle-turn": turned,
        "depot-hold-mark": [
            (piece, (y, -x, z), size) for piece, (x, y, z), size in centered
        ],
    }
    assets = {}
    for key, model in models.items():
        image = Image.new("RGBA", (144, 144))
        draw = ImageDraw.Draw(image)
        baseline(draw, 8, 113, 128)
        draw_model(draw, model, (72, 113), 22)
        assets[key] = image

    roll = Image.new("RGBA", (144, 144))
    draw = ImageDraw.Draw(roll)
    baseline(draw, 8, 113, 128)
    draw_piece(draw, BALL.pose(0, 0, 0), (40, 113), 24)
    arrow(draw, (72, 87), (132, 87))
    assets["depot-roll-mark"] = roll
    return assets


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    for key, image in (geometry_assets() | hop_geometry_assets() | support_depot_assets()).items():
        image.save(ASSETS / f"{key}.png", optimize=True)


if __name__ == "__main__":
    main()
