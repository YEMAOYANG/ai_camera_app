"""Draw the exact badge counts and place-value positions used by this lesson."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
CREAM, PINE, ORANGE, SAGE = "#fff4de", "#284a3b", "#ba502a", "#8fab8c"
PALE, WHITE, LINE = "#f2dfad", "#fffaf0", "#a8ba95"

# Picture task operands stay separate from teaching examples and quiz operands.
MARBLE_PROBLEMS = {
    "p14-21": (14, 21),
    "p23-44": (23, 44),
    "p27-16": (27, 16),
    "p29-34": (29, 34),
    "p46-14": (46, 14),
    "p9-53": (9, 53),
}
SORT_CARDS = {
    "sort-3-4": (3, 4),
    "sort-6-4": (6, 4),
    "sort-8-5": (8, 5),
    "sort-4-5": (4, 5),
    "sort-7-2": (7, 2),
    "sort-8-6": (8, 6),
    "sort-6-2": (6, 2),
}
QUIZ_PROBLEMS = [(25, 31), (38, 27), (44, 26), (6, 57), (36, 18)]
RESULT_CHOICES = {2: (65, 55, 75), 3: (7, 60, 70), 5: (54, 44, 64)}


def place(value):
    if not isinstance(value, int) or not 0 <= value < 100:
        raise ValueError("badge counts must fit two place-value columns")
    return divmod(value, 10)


def paper(size):
    return Image.new("RGB", size, CREAM)


def label(draw, xy, value, size, color=PINE):
    draw.text(xy, str(value), font=ImageFont.truetype(FONT, size), fill=color, anchor="mm")


def dots(draw, count, x, y, step, *, columns=5, fill=ORANGE):
    radius = step * .34
    for i in range(count):
        cx, cy = x + i % columns * step, y + i // columns * step
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=fill)


def ten_frame(draw, count, x, y, step):
    for i in range(10):
        cx, cy = x + i % 5 * step, y + i // 5 * step
        draw.rounded_rectangle((cx-step*.46, cy-step*.46, cx+step*.46, cy+step*.46),
                               radius=step*.14, fill=WHITE, outline=LINE, width=max(1, step//12))
        if i < count:
            dots(draw, 1, cx, cy, step)


def bundles(draw, count, x, y, step):
    """Each solid strip has exactly ten pips, distinct from the loose badges."""
    for i in range(count):
        cx, cy = x + i % 5 * step, y + i // 5 * (2.45 * step)
        draw.rounded_rectangle((cx-step*.36, cy-step*1.06, cx+step*.36, cy+step*1.06),
                               radius=step*.15, fill=PINE)
        for pip in range(10):
            px = cx + (-.15 if pip % 2 == 0 else .15) * step
            py = cy + (pip//2 - 2) * .34 * step
            r = step * .09
            draw.ellipse((px-r, py-r, px+r, py+r), fill=CREAM)


def place_panel(draw, value, x, y, step, *, show_value=False):
    tens, ones = place(value)
    width = step * 11
    draw.rounded_rectangle((x, y, x+width, y+step*5.6), radius=step*.4, fill=WHITE,
                           outline=LINE, width=max(1, step//12))
    draw.line((x+step*5.5, y+step*.3, x+step*5.5, y+step*5.25), fill=LINE, width=max(2, step//11))
    bundles(draw, tens, x+step*.82, y+step*1.55, step)
    dots(draw, ones, x+step*6.3, y+step*1.45, step)
    if not ones:
        label(draw, (x+step*8.5, y+step*2.28), "0", int(step*1.3))
    if show_value:
        label(draw, (x+step*8.5, y+step*4.28), value, int(step*1.7))


def problem(left, right):
    frame = paper((500, 500))
    draw = ImageDraw.Draw(frame)
    place_panel(draw, left, 41, 24, 38)
    place_panel(draw, right, 41, 261, 38)
    return frame


def result_card(value):
    frame = paper((470, 240))
    draw = ImageDraw.Draw(frame)
    place_panel(draw, value, 9, 4, 41, show_value=True)
    return frame


def sort_card(left, right):
    frame = paper((225, 225))
    draw = ImageDraw.Draw(frame)
    dots(draw, left, 33, 42, 40)
    draw.line((16, 110, 209, 110), fill=PINE, width=4)
    dots(draw, right, 33, 145, 40)
    return frame


def dock(full):
    frame = paper((225, 225))
    draw = ImageDraw.Draw(frame)
    ten_frame(draw, 10 if full else 7, 31, 48, 40)
    if full:
        draw.line((113, 111, 113, 147), fill=ORANGE, width=6)
        draw.polygon(((101, 141), (126, 141), (113, 156)), fill=ORANGE)
        bundles(draw, 1, 113, 188, 24)
    else:
        draw.rounded_rectangle((31, 143, 194, 188), radius=10, outline=LINE, width=4)
    return frame


def write_vertical(draw, left, right, result, x, y, *, scale=1, upper_shift=0,
                   lower_shift=0, carry=False):
    cell = 70*scale
    for i in range(3):
        col = x + cell*i
        fill = WHITE if i == 0 else PALE
        draw.rounded_rectangle((col, y, col+cell-3, y+cell*3.54), radius=9*scale,
                               fill=fill, outline=LINE, width=max(1, int(scale*2)))
    for row, number, shift in ((0, left, upper_shift), (1, right, lower_shift), (2, result, 0)):
        for i, character in enumerate(reversed(str(number))):
            col = 2-i+shift
            if 0 <= col <= 2:
                label(draw, (x+cell*(col+.48), y+cell*(row+.60)), character, int(56*scale))
    label(draw, (x-cell*.18, y+cell*1.58), "+", int(45*scale))
    draw.line((x, y+cell*2.04, x+cell*3, y+cell*2.04), fill=PINE, width=max(2, int(4*scale)))
    if carry:
        label(draw, (x+cell*1.8, y+cell*1.85), "1", int(25*scale), ORANGE)


def vertical(left, right, result, **style):
    frame = paper((440, 400))
    draw = ImageDraw.Draw(frame)
    write_vertical(draw, left, right, result, 72, 18, scale=1.4, **style)
    return frame


def grouping_example():
    frame = paper((650, 470))
    draw = ImageDraw.Draw(frame)
    ten_frame(draw, 10, 69, 79, 79)
    dots(draw, 2, 497, 120, 78)
    draw.line((229, 222, 229, 293), fill=ORANGE, width=9)
    draw.polygon(((208, 280), (250, 280), (229, 313)), fill=ORANGE)
    bundles(draw, 1, 229, 383, 49)
    dots(draw, 2, 497, 383, 78)
    return frame


def side_by_side_examples():
    frame = paper((710, 442))
    draw = ImageDraw.Draw(frame)
    write_vertical(draw, 37, 43, 80, 40, 37, scale=1.34, carry=True)
    write_vertical(draw, 7, 65, 72, 380, 37, scale=1.34, carry=True)
    return frame


# Each row has a wrong written result and a separately counted correct value.
DIAGNOSIS = (
    (22, 6, 82, -1, (1, 1)),
    (26, 37, 53, 0, (1, 2)),
    (32, 28, 6, 0, (2, 2)),
)


def diagnosis():
    frame = paper((735, 555))
    draw = ImageDraw.Draw(frame)
    for i, (left, right, wrong, shift, (column, row)) in enumerate(DIAGNOSIS):
        y = i * 185
        if i:
            draw.line((18, y, 716, y), fill=LINE, width=4)
        label(draw, (32, y+88), i+1, 42)
        x, top, scale = 84, y+11, .65
        cell = 70*scale
        write_vertical(draw, left, right, wrong, x, top, scale=scale, lower_shift=shift)
        cx, cy = x+cell*(column+.48), top+cell*(row+.60)
        draw.ellipse((cx-19, cy-19, cx+19, cy+19), outline=ORANGE, width=4)
        draw.line((246, y+87, 320, y+87), fill=PINE, width=8)
        draw.polygon(((307, y+73), (329, y+87), (307, y+101)), fill=PINE)
        place_panel(draw, left+right, 354, y+8, 30, show_value=True)
    return frame


def quiz_diagnosis_context():
    frame = paper((790, 490))
    frame.paste(problem(36, 18).resize((442, 442), Image.Resampling.LANCZOS), (10, 20))
    write_vertical(ImageDraw.Draw(frame), 36, 18, 44, 477, 47, scale=1.23)
    return frame


def figures():
    yield "alignment-board", problem(21, 43)
    yield "no-carry-board", vertical(21, 43, 64)
    yield "exchange-board", grouping_example()
    yield "zero-single-board", side_by_side_examples()
    yield "diagnosis-board", diagnosis()
    yield "closing-board", vertical(28, 54, 82, carry=True)
    for key, (a, b) in SORT_CARDS.items():
        yield key, sort_card(a, b)
    yield "dock-under", dock(False)
    yield "dock-full", dock(True)
    for key, pair in MARBLE_PROBLEMS.items():
        yield key, problem(*pair)
    for total in (35, 67, 37, 43, 63, 53, 60, 62, 50):
        yield f"result-{total}", result_card(total)
    for i, (a, b) in enumerate(QUIZ_PROBLEMS, 1):
        yield f"quiz-{i}-context", quiz_diagnosis_context() if i == 5 else problem(a, b)
        if i in RESULT_CHOICES:
            for letter, total in zip("abc", RESULT_CHOICES[i]):
                yield f"quiz-{i}-{letter}", result_card(total)
        elif i == 1:
            yield "quiz-1-a", vertical(a, b, 28, lower_shift=-1)
            yield "quiz-1-b", vertical(a, b, 56)
            yield "quiz-1-c", vertical(a, b, 55)
        else:
            yield "quiz-4-a", vertical(a, b, 63, upper_shift=-1, carry=True)
            yield "quiz-4-b", vertical(a, b, 63, carry=True)
            yield "quiz-4-c", vertical(a, b, 63, upper_shift=-2, carry=True)


if __name__ == "__main__":
    for name, image in figures():
        image.save(ROOT / "assets" / f"{name}.png", optimize=True)
