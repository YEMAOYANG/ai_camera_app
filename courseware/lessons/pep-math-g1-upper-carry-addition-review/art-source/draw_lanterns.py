"""Draw exact lantern counts and an original subset of the addition table."""
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'
INK = '#183f36'
PAPER = '#fff4dc'
TEAL = '#bcdbc9'
APRICOT = '#fad6ab'
FONT = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'


@lru_cache(maxsize=32)
def sprite(color, size):
    with Image.open(ASSETS / f'lantern-{color}.png') as source:
        rgba = source.convert('RGBA')
        alpha = rgba.getchannel('A').point(lambda level: 255 if level >= 16 else 0)
        piece = rgba.crop(alpha.getbbox())
        piece.thumbnail((size, size), Image.Resampling.LANCZOS)
        return piece


def text(image, value, x, y, size=48, color=INK):
    font = ImageFont.truetype(FONT, size)
    ImageDraw.Draw(image).text((x, y), str(value), anchor='mm', font=font, fill=color)


def draw_group(image, colors, x, y, pitch=35, *, cols=5, frame=False):
    if frame:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((x, y, x + 5 * pitch, y + 2 * pitch), radius=9, fill=PAPER, outline='#7b9a81', width=3)
        for col in range(1, 5):
            draw.line((x + col * pitch, y + 1, x + col * pitch, y + 2 * pitch - 1), fill='#7b9a81', width=2)
        draw.line((x + 1, y + pitch, x + 5 * pitch - 1, y + pitch), fill='#7b9a81', width=2)
    for i, color in enumerate(colors):
        row, col = divmod(i, cols)
        lamp = sprite(color, round(pitch * .78))
        image.alpha_composite(lamp, (x + col * pitch + (pitch - lamp.width)//2,
                                     y + row * pitch + (pitch - lamp.height)//2))


def pair(a, b, *, mini=False):
    if mini:
        image = Image.new('RGBA', (244, 184), PAPER)
        draw_group(image, ['orange'] * a, 12, 12, 20, frame=True)
        draw_group(image, ['green'] * b, 132, 12, 20, frame=True)
        text(image, f'{a}+{b}', 122, 118, 83)
        return image
    image = Image.new('RGBA', (510, 260), PAPER)
    draw_group(image, ['orange'] * a, 22, 34, 40, frame=True)
    draw_group(image, ['green'] * b, 290, 34, 40, frame=True)
    text(image, a, 122, 178, 62)
    text(image, '+', 256, 178)
    text(image, b, 391, 178, 62)
    return image


def make_ten(a, b, moved, *, right=False):
    source, destination = (a, b) if right else (b, a)
    if not 0 <= moved <= source or destination + moved > 10:
        raise ValueError('The moved lanterns must fit in the destination ten frame')
    image = Image.new('RGBA', (510, 260), PAPER)
    if right:
        left = ['orange'] * (a-moved)
        right_group = ['green'] * b + ['orange'] * moved
        tip, tail, direction = 294, 214, 1
    else:
        left = ['orange'] * a + ['green'] * moved
        right_group = ['green'] * (b-moved)
        tip, tail, direction = 214, 294, -1
    draw_group(image, left, 22, 34, 40, frame=not right)
    draw_group(image, right_group, 290, 34, 40, frame=right)
    draw = ImageDraw.Draw(image)
    draw.line((tail, 165, tip, 165), fill=INK, width=7)
    draw.polygon([(tip, 165), (tip-direction*21, 154), (tip-direction*21, 176)], fill=INK)
    text(image, moved, 255, 202, 42)
    text(image, len(left), 123, 178, 62)
    text(image, len(right_group), 385, 178, 62)
    return image


def total(n):
    if not 10 <= n <= 20:
        raise ValueError('This ten-and-ones picture covers ten through twenty')
    image = Image.new('RGBA', (510, 260), '#e4edda')
    draw_group(image, ['green'] * 10, 28, 43, 41, frame=True)
    draw_group(image, ['orange'] * (n - 10), 279, 43, 39, frame=n == 20)
    text(image, n, 255, 193, 72)
    return image


def mixed(a, b, c, d):
    image = Image.new('RGBA', (510, 260), PAPER)
    draw = ImageDraw.Draw(image)
    for row, (orange, green) in enumerate(((a,b),(c,d))):
        y = 28 + 111 * row
        draw.rounded_rectangle((38, y, 472, y+82), radius=16, fill=APRICOT if row==0 else TEAL)
        draw_group(image, ['orange'] * orange + ['green'] * green, 52, y+11, 44, cols=9)
    return image


def delivered(away, remaining):
    image = pair(away, remaining)
    draw = ImageDraw.Draw(image)
    for i in range(away):
        row, col = divmod(i, 5)
        x, y = 22 + col*40, 34 + row*40
        draw.line((x+7, y+32, x+33, y+6), fill='#ad6447', width=4)
    return image


def table(rows, highlight):
    image = Image.new('RGBA', (610, 315), '#e1ebdb')
    draw = ImageDraw.Draw(image)
    for row, target_sum in enumerate(rows):
        y = 22 + 58*row
        text(image, target_sum, 34, y+25, 30)
        for col, a in enumerate((9, 8, 7, 6)):
            b = target_sum-a
            if not 1 <= b <= 9:
                continue
            x = 76+128*col
            marked = (highlight == 'row' and target_sum == 12) or (highlight == 'directions' and a == 8)
            diagonal = highlight == 'directions' and b == 4
            draw.rounded_rectangle((x,y,x+114,y+49), radius=12, fill=APRICOT if marked else PAPER,
                                   outline='#278465' if diagonal else None, width=5)
            text(image, f'{a}+{b}', x+57, y+25, 33)
    return image


def sequence(expressions):
    image = Image.new('RGBA', (610, 315), '#e1ebdb')
    draw = ImageDraw.Draw(image)
    for i, value in enumerate(expressions):
        y=31+i*68
        draw.rounded_rectangle((73,y,537,y+55),radius=14,fill=PAPER)
        text(image, value, 305, y+28, 46)
    return image


def row_cards(expressions, result):
    image = Image.new('RGBA', (610, 190), '#e1ebdb')
    draw = ImageDraw.Draw(image)
    width = 125
    gap = 12
    start = (610 - len(expressions) * width - (len(expressions)-1) * gap) // 2
    for index, value in enumerate(expressions):
        x = start + index * (width + gap)
        draw.rounded_rectangle((x, 20, x+width, 106), radius=16, fill=PAPER)
        text(image, value, x+width//2, 63, 44)
    draw.rounded_rectangle((256, 123, 354, 175), radius=16, fill=APRICOT)
    text(image, result, 305, 149, 36)
    return image


def one_group(n):
    image = Image.new('RGBA', (510, 260), PAPER)
    draw_group(image, ['orange'] * n, 137, 32, 47, frame=True)
    text(image, n, 255, 191, 74)
    return image


def main():
    renderers = dict(pair=pair, make_ten=make_ten, total=total, mixed=mixed, delivered=delivered,
                     table=table, sequence=sequence, row_cards=row_cards, one_group=one_group)
    definitions = json.loads((HERE/'lantern-math.json').read_text())
    for key, (kind, values, options) in definitions.items():
        renderers[kind](*values, **options).save(ASSETS/(key+'.png'), optimize=True)


if __name__ == '__main__':
    main()
