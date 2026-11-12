"""Compose exact paper-tab quantities and ten frames for the kite workshop."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LESSON = Path(__file__).resolve().parents[1]
ASSETS = LESSON / 'assets'
ORANGE, GREEN = 'o', 'g'
INK = '#204637'
CREAM = '#fff7df'
LINE = '#789581'


def tab(color):
    names = {ORANGE: 'orange', GREEN: 'green'}
    with Image.open(ASSETS / ('ribbon-' + names[color] + '.png')) as source:
        rgba = source.convert('RGBA')
        bounds = rgba.getchannel('A').point(lambda alpha: 255 if alpha >= 16 else 0).getbbox()
        return rgba.crop(bounds)


def put_tabs(canvas, colors, x, y, pitch, row_width=5):
    for index, color in enumerate(colors):
        row, col = divmod(index, row_width)
        sprite = tab(color)
        sprite.thumbnail((round(pitch * .82), round(pitch * .55)), Image.Resampling.LANCZOS)
        left = round(x + col * pitch + (pitch - sprite.width) / 2)
        top = round(y + row * pitch + (pitch - sprite.height) / 2)
        canvas.alpha_composite(sprite, (left, top))


def quantity(color, count):
    if type(count) is not int or not 0 <= count <= 10:
        raise ValueError('Expected a single group of zero to ten tabs')
    return color * count


def ten_frame(canvas, x, y, colors, pitch):
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x, y, x + 5 * pitch, y + 2 * pitch), radius=8, fill=CREAM, outline=LINE, width=3)
    for col in range(1, 5):
        draw.line((x + col * pitch, y + 1, x + col * pitch, y + 2 * pitch - 1), fill=LINE, width=2)
    draw.line((x, y + pitch, x + 5 * pitch, y + pitch), fill=LINE, width=2)
    put_tabs(canvas, colors, x, y, pitch)


def number(canvas, value, x, y, size):
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', size)
    ImageDraw.Draw(canvas).text((x, y), str(value), anchor='mm', font=font, fill=INK)


def pair(left, right, *, reverse=False, compact=False, moved=False):
    colors = (GREEN, ORANGE) if reverse else (ORANGE, GREEN)
    first, second = quantity(colors[0], left), quantity(colors[1], right)
    if moved:
        first = first[:-1] + GREEN
    if compact:
        canvas = Image.new('RGBA', (240, 220), '#fff7df')
        ten_frame(canvas, 14, 15, first, 20)
        ten_frame(canvas, 126, 15, second, 20)
        number(canvas, f'{left}+{right}', 120, 122, 82)
        return canvas.crop((0, 0, 240, 179))
    canvas = Image.new('RGBA', (430, 240), '#f5edce')
    ten_frame(canvas, 16, 28, first, 36)
    ten_frame(canvas, 234, 28, second, 36)
    number(canvas, left, 106, 159, 58)
    number(canvas, '+', 215, 159, 41)
    number(canvas, right, 324, 159, 58)
    return canvas


def total(extra, compact=False):
    if not 0 <= extra <= 9:
        raise ValueError('Expected a total between ten and nineteen')
    if compact:
        canvas = Image.new('RGBA', (240, 220), '#e9f1d8')
        ten_frame(canvas, 14, 18, GREEN * 10, 27)
        put_tabs(canvas, ORANGE * extra, 156, 18, 23, row_width=3)
        number(canvas, 10 + extra, 120, 150, 105)
        return canvas
    canvas = Image.new('RGBA', (430, 240), '#e9f1d8')
    ten_frame(canvas, 22, 42, GREEN * 10, 43)
    put_tabs(canvas, ORANGE * extra, 254, 42, 36)
    number(canvas, 10 + extra, 215, 171, 66)
    return canvas


def transfer(left, right, count, side):
    """One arrow moves tabs between existing groups. Counts are conserved."""
    first, second = quantity(ORANGE, left), quantity(GREEN, right)
    if side == 'right':
        if not 0 <= count <= left or right + count > 10:
            raise ValueError('Transfer does not fit the right frame')
        first, second = first[count:], second + first[:count]
    elif side == 'left':
        if not 0 <= count <= right or left + count > 10:
            raise ValueError('Transfer does not fit the left frame')
        first, second = first + second[:count], second[count:]
    else:
        raise ValueError('Unknown transfer direction')
    return first, second


def regroup(left, right, count, side):
    first, second = transfer(left, right, count, side)
    canvas = Image.new('RGBA', (430, 240), '#f5edce')
    ten_frame(canvas, 16, 25, first, 35)
    ten_frame(canvas, 239, 25, second, 35)
    draw = ImageDraw.Draw(canvas)
    tip, tail = (264, 161) if side == 'right' else (161, 264)
    draw.line((tail, 139, tip, 139), fill=INK, width=7)
    direction = 1 if tip > tail else -1
    draw.polygon([(tip, 139), (tip - direction * 22, 124), (tip - direction * 22, 154)], fill=INK)
    number(canvas, count, 215, 171, 34)
    number(canvas, len(first), 105, 170, 56)
    number(canvas, len(second), 326, 170, 56)
    return canvas


def shipment(count):
    canvas = Image.new('RGBA', (430, 240), '#f5edce')
    draw = ImageDraw.Draw(canvas)
    draw.line((96, 105, 337, 105), fill=INK, width=14)
    draw.polygon([(352, 105), (317, 80), (317, 130)], fill=INK)
    put_tabs(canvas, ORANGE * count, 151, 40, 48)
    number(canvas, count, 215, 171, 63)
    return canvas


def main():
    specs = json.loads((Path(__file__).with_name('math-diagrams.json')).read_text())
    for key, (kind, args, options) in specs.items():
        image = {'pair': pair, 'total': total, 'regroup': regroup, 'shipment': shipment}[kind](*args, **options)
        image.save(ASSETS / (key + '.png'), optimize=True)


if __name__ == '__main__':
    main()
