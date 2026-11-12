"""Draw exact number, comparison and quantity diagrams for this lesson."""

import argparse
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LESSON = Path(__file__).resolve().parents[1]
BACKGROUND = '#fff9eb'
INK = '#27463d'
ORANGE = '#be592f'
GREEN = '#38826b'
LINE = '#ad9270'
CREAM = '#f5e2bb'
FADED = '#d7cfbb'
PAPER = '#fffcf4'
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'


@lru_cache(maxsize=None)
def font(size):
    return ImageFont.truetype(FONT, size)


class Drawing:
    def __init__(self, width=720, height=360):
        self.image = Image.new('RGB', (width, height), BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    def text(self, x, y, value, size=50, color=INK):
        self.draw.text((x, y), str(value), font=font(size), fill=color, anchor='mm', stroke_width=0)

    def card(self, x, y, w, h, label=None, fill=PAPER, size=47):
        self.draw.rounded_rectangle((x-w/2, y-h/2, x+w/2, y+h/2), radius=13,
                                    fill=fill, outline=LINE, width=3)
        if label is not None:
            self.text(x, y, label, size)

    def arrow(self, start, end, y):
        self.draw.line((start, y, end, y), fill=INK, width=5)
        dx = 1 if end > start else -1
        self.draw.polygon([(end, y), (end-17*dx, y-10), (end-17*dx, y+10)], fill=INK)

    def chip(self, x, y, shape='round', fill=GREEN, size=17, crossed=False, circled=False):
        bounds = (x-size, y-size, x+size, y+size)
        if shape == 'round':
            self.draw.ellipse(bounds, fill=fill, outline=INK, width=2)
        elif shape == 'square':
            self.draw.rounded_rectangle(bounds, radius=4, fill=fill, outline=INK, width=2)
        elif shape == 'triangle':
            self.draw.polygon([(x, y-size), (x+size, y+size), (x-size, y+size)], fill=fill, outline=INK, width=2)
        else:
            raise ValueError(shape)
        if crossed:
            for dx in (-1, 1):
                self.draw.line((x+dx*size, y-size, x-dx*size, y+size), fill=ORANGE, width=5)
        if circled:
            self.draw.ellipse((x-size-9, y-size-9, x+size+9, y+size+9), outline=ORANGE, width=5)

    def chips(self, x, y, count, *, columns=5, gap=42, shape='round', fill=GREEN, size=15, crossed=(), circled=()):
        for i in range(count):
            self.chip(x+(i % columns)*gap, y+(i//columns)*gap, shape, fill, size,
                      crossed=i in crossed, circled=i in circled)

    def slots(self, x, y, capacity, colors, *, columns=5, gap=54):
        for i in range(capacity):
            px, py = x+(i % columns)*gap, y+(i//columns)*gap
            self.card(px, py, gap-4, gap-4, fill=CREAM)
            if i < len(colors):
                self.chip(px, py, fill=colors[i], size=gap//3)


def number_line():
    c = Drawing()
    c.arrow(51, 684, 145)
    for n in range(11):
        x = 68+59*n
        c.draw.line((x, 137, x, 157), fill=INK, width=4)
        c.text(x, 105, n, 36, ORANGE if n >= 6 else INK)
    c.arrow(107, 593, 231)
    c.chips(164, 286, 6, columns=6, gap=75, circled=(3,), size=19)
    return c


def writing_ten(complete):
    c = Drawing()
    c.draw.rectangle((210, 30, 510, 330), outline=INK, width=4, fill=PAPER)
    for position in range(43, 327, 18):
        c.draw.line((210+position-30, 180, 210+position-20, 180), fill=LINE, width=3)
        c.draw.line((360, position, 360, position+10), fill=LINE, width=3)

    def trace(points, arrow_index):
        c.draw.line(points, fill=INK, width=14, joint='curve')
        x, y = points[0]
        c.draw.ellipse((x-10, y-10, x+10, y+10), fill=ORANGE, outline=PAPER, width=2)
        x, y = points[arrow_index]
        nx, ny = points[arrow_index+1]
        length = math.hypot(nx-x, ny-y)
        dx, dy = (nx-x)/length, (ny-y)/length
        c.draw.polygon([(x+14*dx, y+14*dy),
                        (x-14*dx+11*dy, y-14*dy-11*dx),
                        (x-14*dx-11*dy, y-14*dy+11*dx)], fill=ORANGE)

    trace([(330, 58), (276, 224), (252, 305)], 1)
    if complete:
        points = []
        for angle in range(280, 641, 4):
            theta = math.radians(angle)
            y = 119*math.sin(theta)
            points.append((436+54*math.cos(theta)-0.23*y, 180+y))
        trace(points, 11)
    return c


def compare_dots():
    c = Drawing()
    for index in range(7):
        x = 90+64*index
        c.draw.line((x, 130, x, 206), fill=LINE, width=3)
    c.chips(90, 112, 7, columns=9, gap=64, fill=GREEN, size=18)
    c.chips(90, 225, 9, columns=9, gap=64, fill=GREEN, circled=(7, 8), size=18)
    c.text(618, 112, 7, 38)
    c.text(618, 275, 9, 38)
    return c


def split_ten():
    c = Drawing()
    for y, a, b in [(106, 6, 4), (253, 7, 3)]:
        c.slots(106, y-22, 10, [GREEN]*a+[ORANGE]*b, gap=51)
        c.text(490, y, f'{a} + {b} = 10', 56)
    return c


def remove_ten():
    c = Drawing()
    for y, taken in [(104, 6), (253, 4)]:
        c.chips(79, y-22, 10, gap=49, size=15, crossed=tuple(range(taken)))
        c.text(491, y, f'10 − {taken} = {10-taken}', 56)
    return c


def add_row():
    c = Drawing()
    for i, (a, b) in enumerate([(8, 1), (7, 2), (6, 3), (5, 4)]):
        x = 104+i*171
        c.card(x, 119, 146, 76, '?' if i == 2 else f'{a} + {b}', fill=CREAM if i == 2 else PAPER)
        if i == 2:
            continue
        c.slots(x-56, 210, 9, [GREEN]*a+[ORANGE]*b, gap=28)
    c.text(360, 306, '= 9', 48)
    return c


def add_column():
    c = Drawing()
    for i, a in enumerate((5, 6, 7)):
        y = 68+110*i
        c.card(170, y, 183, 73, '?' if a == 6 else f'{a} + 3', fill=CREAM if a == 6 else PAPER)
        if a != 6:
            c.chips(332, y, a, columns=7, gap=35, size=12)
        c.chips(608, y, 3, columns=3, gap=32, fill=ORANGE, size=11)
    return c


def add_diagonal():
    c = Drawing()
    for i, total in enumerate((7, 8, 9)):
        y = 77+101*i
        c.text(69, y, total, 45)
        for j, second in enumerate(range(3, 7)):
            first = total-second
            c.card(198+138*j, y, 124, 75, f'{first} + {second}',
                   fill=CREAM if first == 3 else PAPER, size=44)
    return c


def subtraction_row():
    c = Drawing()
    for i, taken in enumerate((1, 2, 3)):
        x = 125+235*i
        c.card(x, 103, 205, 67, f'8 − {taken} = {8-taken}', size=41)
        c.chips(x-60, 209, 8, columns=4, gap=40, size=13, crossed=tuple(range(taken)))
    return c


def zero_pair():
    c = Drawing()
    for y, sign in [(101, '+'), (255, '−')]:
        c.chips(125, y, 5, columns=5, gap=43, size=15)
        c.card(490, y, 240, 73, f'5 {sign} 0 = 5', size=56)
    return c


def choose_add():
    c = Drawing()
    c.card(182, 163, 250, 206)
    c.card(538, 163, 250, 206)
    c.chips(132, 144, 3, columns=3, gap=50, shape='square', size=16)
    c.chips(157, 205, 2, columns=2, gap=50, fill=ORANGE, size=16)
    c.chips(438, 144, 5, columns=5, gap=50, shape='square', size=16)
    c.chips(488, 205, 3, columns=3, gap=50, fill=ORANGE, size=16)
    c.text(360, 303, '3 + 5 = 8', 56)
    return c


def choose_subtract():
    c = Drawing()
    c.card(360, 142, 588, 165)
    c.chips(121, 142, 7, columns=7, gap=79, shape='square', size=22, crossed=(5, 6))
    c.text(360, 289, '7 − 2 = 5', 56)
    return c


def two_step_board():
    c = Drawing(height=500)
    for i, (start, step_one, step_two) in enumerate([(4, 2, 3), (9, -1, -3), (6, 2, -4)]):
        y = 86+i*164
        for j, count in enumerate([start, start+step_one, start+step_one+step_two]):
            x = 109+j*250
            c.card(x, y, 195, 111)
            c.chips(x-65, y-18, count, columns=5, gap=32, size=11)
        for j, change in enumerate([step_one, step_two]):
            x = 232+j*250
            c.arrow(x-24, x+27, y+20)
            c.text(x, y-17, str(change).replace('-', '−') if change<0 else f'+{change}', 34)
    return c


def label(value):
    c = Drawing(480, 240)
    c.card(240, 120, 385, 160, value, size=96 if len(str(value)) <= 2 else 73)
    return c


def quiz_next_stop():
    c = Drawing()
    for i, value in enumerate((6, 5, None, 3)):
        x = 94+i*175
        c.card(x, 180, 125, 117, value, fill=CREAM if value is None else PAPER, size=67)
        if i < 3:
            c.arrow(x+69, x+105, 180)
    return c


def pegs(circled=None):
    c = Drawing()
    c.arrow(656, 66, 108)
    c.chips(70, 223, 9, columns=9, gap=72, size=19, circled=() if circled is None else (circled,))
    return c


def quiz_nine():
    c = Drawing()
    c.slots(204, 117, 9, [GREEN]*4, columns=3, gap=63)
    return c


def chips_option(count):
    c = Drawing(480, 240)
    cols = min(count, 3)
    c.chips(240-(cols-1)*32, 93, count, columns=cols, gap=64, size=21)
    return c


def quiz_missing_sum():
    c = Drawing()
    for y, expression in [(68, '5 + 2'), (180, None), (292, '7 + 2')]:
        c.card(360, y, 176, 75, expression, fill=CREAM)
    for x, expression in [(156, '7 + 1'), (565, '5 + 3')]:
        c.card(x, 180, 176, 75, expression)
    return c


def quiz_inequality():
    c = Drawing()
    c.card(171, 180, 243, 113, '10 − 4', size=61)
    c.card(360, 180, 94, 113, fill=CREAM)
    c.card(549, 180, 243, 113, '10 − 3', size=61)
    return c


def quiz_tool_bag():
    c = Drawing()
    c.card(237, 180, 337, 227)
    c.card(553, 180, 218, 227)
    c.chips(145, 126, 9, columns=3, gap=64, shape='triangle', size=20, crossed=(7, 8))
    c.chips(518, 146, 4, columns=2, gap=70, fill=ORANGE, size=21)
    return c


def quiz_two_moves():
    c = Drawing()
    for i, (count, sign) in enumerate([(7, None), (3, '−'), (5, '+')]):
        x = 124+i*235
        c.card(x, 180, 194, 198, fill=CREAM if i else PAPER)
        if sign:
            c.text(x, 123, sign, 54)
        c.chips(x-66, 165, count, columns=4, gap=44, size=15, crossed=tuple(range(count)) if sign=='−' else ())
        if i<2:
            c.arrow(x+102, x+132, 182)
    return c


def drawings():
    yield from [
        ('number-line', number_line()), ('compare-dots', compare_dots()),
        ('write-ten-one', writing_ten(False)), ('write-ten-complete', writing_ten(True)), ('split-ten', split_ten()),
        ('remove-ten', remove_ten()), ('sum-row', add_row()), ('sum-column', add_column()), ('sum-diagonal', add_diagonal()),
        ('subtract-row', subtraction_row()), ('zero-pair', zero_pair()),
        ('choose-add', choose_add()), ('choose-subtract', choose_subtract()), ('two-step-board', two_step_board()),
    ]
    quiz = {
        'next-stop': (quiz_next_stop(), [label(n) for n in (4, 7, 2)]),
        'seventh-peg': (pegs(), [pegs(n) for n in (6, 2, 3)]),
        'part-of-nine': (quiz_nine(), [chips_option(n) for n in (4, 6, 5)]),
        'missing-sum': (quiz_missing_sum(), [label(n) for n in ('5 + 2', '6 + 2', '6 + 3')]),
        'less-by-one': (quiz_inequality(), [label(n) for n in ('>', '=', '<')]),
        'tool-bag': (quiz_tool_bag(), [label(n) for n in ('9 − 2', '2 + 7', '4 − 2')]),
        'two-moves': (quiz_two_moves(), [label(n) for n in (5, 9, 4)]),
    }
    for key, (stem, options) in quiz.items():
        yield 'q-'+key, stem
        for letter, option in zip('abc', options):
            yield f'q-{key}-{letter}', option


def write_assets(directory):
    directory.mkdir(parents=True, exist_ok=True)
    records = {}
    for key, drawing in drawings():
        output = directory/(key+'.png')
        drawing.image.save(output, optimize=True)
        records[key] = {
            'file': 'assets/'+output.name,
            'kind': 'deterministic_semantic_diagram',
            'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'pixels': list(drawing.image.size),
        }
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=LESSON/'assets')
    args = parser.parse_args()
    print(json.dumps(write_assets(args.output), ensure_ascii=False, indent=2))
