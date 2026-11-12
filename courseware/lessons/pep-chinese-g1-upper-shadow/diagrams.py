"""Draw the lesson's precise position and stroke diagrams."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
CREAM = "#fff5dc"
PINE = "#233f35"
SAGE = "#90a67f"
ORANGE = "#cc5b2c"
INK = "#253a32"

OFFSETS = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}

# Centerlines follow the stroke order shown in the reviewed grade-one textbook.
# A turn remains part of its stroke, including the hook at the end of 斜钩.
STROKES = {
    "左": (
        ((25, 29), (79, 24)),
        ((47, 15), (44, 39), (34, 58), (16, 77)),
        ((44, 54), (77, 51)),
        ((60, 54), (59, 83)),
        ((33, 85), (88, 82)),
    ),
    "右": (
        ((22, 30), (82, 25)),
        ((47, 16), (44, 39), (35, 59), (16, 77)),
        ((44, 56), (47, 86)),
        ((44, 56), (81, 53), (77, 84)),
        ((47, 83), (77, 82)),
    ),
    "在": (
        ((24, 29), (84, 24)),
        ((47, 15), (44, 39), (33, 60), (17, 78)),
        ((35, 55), (35, 89)),
        ((48, 59), (82, 56)),
        ((65, 47), (65, 85)),
        ((43, 87), (91, 84)),
    ),
    "我": (
        ((47, 15), (38, 20), (23, 24)),
        ((15, 43), (87, 35)),
        ((37, 23), (38, 70), (38, 84), (32, 89), (25, 81)),
        ((15, 68), (52, 53)),
        ((57, 12), (59, 36), (64, 56), (72, 72), (82, 85), (90, 88), (91, 76)),
        ((79, 48), (72, 62), (63, 71), (52, 78)),
        ((74, 17), (85, 24)),
    ),
}


def offset(direction, heading):
    x, y = OFFSETS[direction]
    return (x, y) if heading == "up" else (-y, x)


def point(center, direction, heading, radius):
    x, y = offset(direction, heading)
    return center[0] + x * radius, center[1] + y * radius


def place(canvas, sprite, center, size, rotation=0):
    image = sprite.copy()
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    if rotation:
        image = image.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(image, (round(center[0] - image.width / 2),
                                   round(center[1] - image.height / 2)))


def arrow(canvas, center, heading, radius):
    tip = point(center, "front", heading, radius)
    tail = point(center, "front", heading, radius - 18)
    side = offset("left", heading)
    draw = ImageDraw.Draw(canvas)
    draw.line([tail, tip], fill=ORANGE, width=5)
    draw.polygon([tip, (tail[0] + side[0] * 8, tail[1] + side[1] * 8),
                  (tail[0] - side[0] * 8, tail[1] - side[1] * 8)], fill=ORANGE)


def room_diagram(actor, target, direction, heading, *, game_card=False, overview=False):
    size = (320, 320) if game_card else (420, 350)
    center = size[0] // 2, size[1] // 2
    radius = 90 if game_card else 96
    canvas = Image.new("RGBA", size, CREAM)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((8, 8, size[0] - 8, size[1] - 8), radius=22, outline=SAGE, width=5)
    rotation = 0 if heading == "up" else -90
    place(canvas, actor, center, 100, rotation)
    if not game_card:
        door_x, door_y = point(center, "front", heading, 148)
        width, height = (25, 15) if heading == "up" else (15, 25)
        draw.rounded_rectangle((door_x - width, door_y - height, door_x + width, door_y + height),
                               radius=6, fill=PINE, outline=INK, width=2)
        draw.ellipse((door_x + 6, door_y - 2, door_x + 12, door_y + 4), fill=CREAM)
    arrow(canvas, center, heading, 63)
    for side in OFFSETS if overview else (direction,):
        x, y = point(center, side, heading, radius)
        if game_card or overview:
            draw.ellipse((x - 33, y - 33, x + 33, y + 33), fill="#edbd74")
        place(canvas, target, (x, y), 57 if not overview else 47, rotation if overview else 0)
    return canvas


def projection_choice(lamp, shadow_x):
    canvas = Image.new("RGBA", (420, 290), "#315445")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((25, 18, 395, 171), radius=15, fill=CREAM, outline="#e3b46c", width=5)
    draw.rounded_rectangle((shadow_x - 33, 73, shadow_x + 33, 119), radius=8, fill=PINE)
    draw.rounded_rectangle((185, 192, 235, 219), radius=6, fill="#bc8d50")
    place(canvas, lamp, (329, 235), 82, 28)
    return canvas


def stroke_grid(canvas, box, glyph, *, completed=None, highlighted=None):
    x, y, span = box
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x, y, x + span, y + span), radius=max(3, span // 20),
                           fill=CREAM, outline="#96b0a1", width=max(1, span // 48))
    center_x, center_y = x + span // 2, y + span // 2
    draw.line((center_x, y + 4, center_x, y + span - 4), fill="#c5cbb0", width=1)
    draw.line((x + 4, center_y, x + span - 4, center_y), fill="#c5cbb0", width=1)
    for index, stroke in enumerate(STROKES[glyph][:completed], 1):
        points = [(round(x + px * span / 100), round(y + py * span / 100)) for px, py in stroke]
        width = max(2, span // 15)
        color = ORANGE if index == highlighted else INK
        draw.line(points, fill=color, width=width, joint="curve")
        radius = width // 2
        for px, py in (points[0], points[-1]):
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=color)


def write_pair(glyphs):
    canvas = Image.new("RGBA", (780, 552), "#f2e6c8")
    for row, glyph in enumerate(glyphs):
        top = 14 + row * 271
        stroke_grid(canvas, (14, top, 240), glyph)
        for i in range(len(STROKES[glyph])):
            x = 276 + i % 4 * 123
            y = top + i // 4 * 123
            stroke_grid(canvas, (x, y, 110), glyph, completed=i + 1, highlighted=i + 1)
    return canvas


def write_choice(stroke):
    canvas = Image.new("RGBA", (420, 290), "#f2e6c8")
    stroke_grid(canvas, (83, 17, 254), "我", highlighted=stroke)
    return canvas


def draw_assets(root=ROOT):
    assets = root / "assets"
    with Image.open(root / "art-source" / "actor.png") as image:
        actor = image.convert("RGBA")
    with Image.open(assets / "lamp.png") as image:
        lamp = image.convert("RGBA")
    with Image.open(assets / "bell.png") as image:
        bell = image.convert("RGBA")
    with Image.open(assets / "leaf.png") as image:
        leaf = image.convert("RGBA")

    def save(name, image):
        image.save(assets / (name + ".png"), optimize=True)

    for side in OFFSETS:
        save("station-" + side, room_diagram(actor, actor, side, "up", game_card=True))
    save("direction-map", room_diagram(actor, actor, "front", "up", overview=True))
    for suffix, side in zip("abc", ("left", "front", "back")):
        save("front-choice-" + suffix, room_diagram(actor, bell, side, "up"))
    for suffix, side in zip("abc", ("left", "right", "front")):
        save("left-choice-" + suffix, room_diagram(actor, leaf, side, "right"))
    for suffix, position in zip("abc", (210, 302, 118)):
        save("lamp-choice-" + suffix, projection_choice(lamp, position))
    for suffix, highlighted in zip("abc", (1, 3, 5)):
        save("stroke-choice-" + suffix, write_choice(highlighted))
    save("write-left-right", write_pair(("左", "右")))
    save("write-at-me", write_pair(("在", "我")))


if __name__ == "__main__":
    draw_assets()
