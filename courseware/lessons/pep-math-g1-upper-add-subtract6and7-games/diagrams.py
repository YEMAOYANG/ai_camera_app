"""Draw the exact-count teaching and quiz pictures for this lesson."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER = "#fff8e8"
TRAY = "#fffdf7"
EDGE = "#e0c79c"
BLUE = "#228caa"
BLUE_EDGE = "#186b84"
ORANGE = "#e57b37"
ORANGE_EDGE = "#a94927"
GRAY = "#83929b"
WIDTH, HEIGHT = 720, 340


def new_diagram():
    image = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    return image, ImageDraw.Draw(image)


def tray(draw, bounds):
    draw.rounded_rectangle(bounds, radius=23, fill=TRAY, outline=EDGE, width=4)


def disk(draw, x, y, color, outline, radius=24):
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 fill=color, outline=outline, width=4)
    draw.arc((x - radius + 8, y - radius + 7, x + radius - 8, y + radius - 7),
             start=202, end=299, fill="#ffffff", width=3)


def disks(draw, count, start, y, color, outline, spacing=62):
    for index in range(count):
        disk(draw, start + index * spacing, y, color, outline)


def paired(first, second, *, reverse=False, shared=True):
    image, draw = new_diagram()
    groups = [(first, ORANGE, ORANGE_EDGE), (second, BLUE, BLUE_EDGE)]
    if reverse:
        groups.reverse()
    if shared:
        tray(draw, (40, 78, 680, 260))
        draw.line((354, 99, 354, 239), fill=EDGE, width=4)
    else:
        tray(draw, (34, 78, 340, 260))
        tray(draw, (374, 78, 680, 260))
    for index, (count, color, edge) in enumerate(groups):
        center = 186 + index * 340
        disks(draw, count, center - (count - 1) * 31, 169, color, edge)
    return image


def removed(take_orange):
    image, draw = new_diagram()
    tray(draw, (64, 35, 656, 157))
    tray(draw, (64, 203, 656, 307))
    for index in range(7):
        orange = index < 3
        x = 145 + index * 72
        if orange == take_orange:
            draw.ellipse((x - 24, 96 - 24, x + 24, 96 + 24),
                         outline="#b2a996", width=3)
            disk(draw, x, 255, ORANGE if orange else BLUE, ORANGE_EDGE if orange else BLUE_EDGE)
        else:
            disk(draw, x, 96, ORANGE if orange else BLUE, ORANGE_EDGE if orange else BLUE_EDGE)
    # Arrow shows where the removed part went.
    draw.line((687, 108, 687, 233), fill=GRAY, width=6)
    draw.polygon(((673, 229), (701, 229), (687, 253)), fill=GRAY)
    return image


def ticket(draw, x, y, fill, edge):
    draw.rounded_rectangle((x - 37, y - 22, x + 37, y + 22), 7, fill=fill, outline=edge, width=3)
    for edge_x in (x - 37, x + 37):
        draw.ellipse((edge_x - 6, y - 6, edge_x + 6, y + 6), fill=TRAY)
    draw.line((x - 15, y, x + 17, y), fill="#ffffff", width=3)


def tickets():
    image, draw = new_diagram()
    tray(draw, (44, 48, 202, 288))
    tray(draw, (229, 48, 674, 288))
    ticket(draw, 123, 171, BLUE, BLUE_EDGE)
    for x, y in ((332, 118), (450, 118), (568, 118), (390, 218), (508, 218)):
        ticket(draw, x, y, ORANGE, ORANGE_EDGE)
    return image


def sock(draw, x, y, fill, edge):
    outline = [(-16, -23), (13, -23), (12, 2), (26, 6), (30, 12),
               (28, 21), (19, 25), (-6, 22), (-17, 15)]
    points = [(x + dx, y + dy) for dx, dy in outline]
    draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=edge, width=3, joint="curve")
    draw.line((x - 13, y - 15, x + 11, y - 15), fill="#ffffff", width=3)


def socks():
    image, draw = new_diagram()
    draw.line((94, 68, 625, 68), fill="#967456", width=6)
    sock(draw, 354, 104, BLUE, BLUE_EDGE)
    draw.rounded_rectangle((344, 59, 355, 91), 4, fill="#bf8b52", outline="#967456", width=2)
    draw.rounded_rectangle((100, 163, 620, 313), 26, fill="#f6ddae", outline=EDGE, width=4)
    for y in (205, 270):
        for x in (218, 357, 496):
            sock(draw, x, y, ORANGE, ORANGE_EDGE)
    return image


def tag(draw, x, y, fill, edge):
    outline = [(-30, -25), (17, -25), (34, -12), (34, 12), (17, 25), (-30, 25)]
    points = [(x + dx, y + dy) for dx, dy in outline]
    draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=edge, width=3, joint="curve")
    draw.ellipse((x + 14, y - 4, x + 22, y + 4), fill=TRAY)


def tags():
    image, draw = new_diagram()
    tray(draw, (60, 44, 658, 296))
    locations = ((156, 114), (292, 114), (428, 114), (564, 114),
                 (224, 224), (360, 224), (496, 224))
    for index, (x, y) in enumerate(locations):
        fill, edge = (BLUE, BLUE_EDGE) if index < 2 else (ORANGE, ORANGE_EDGE)
        tag(draw, x, y, fill, edge)
    return image


def pictures():
    return {
        "join-forward": paired(2, 4),
        "join-reverse": paired(2, 4, reverse=True),
        "take-three": removed(take_orange=True),
        "take-four": removed(take_orange=False),
        "groups-seven": paired(3, 4, shared=False),
        "equal-six": paired(3, 3, shared=False),
        "fish-equal": paired(3, 3, shared=False).crop((24, 70, 690, 270)),
        "fish-seven": paired(3, 4, shared=False).crop((24, 70, 690, 270)),
        "fish-six": paired(2, 4, shared=False).crop((24, 70, 690, 270)),
        "tickets": tickets(),
        "socks": socks(),
        "tags": tags(),
    }


if __name__ == "__main__":
    for name, image in pictures().items():
        image.save(Path(__file__).with_name("assets") / f"{name}.png", optimize=True)
