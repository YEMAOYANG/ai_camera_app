"""Render the exact tens and ones models registered by this lesson."""

from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SOURCE = Path(__file__).resolve().parent
CREAM = '#fff4dd'
INK = '#285447'
STRIP_FILL = '#e8ead3'
STRIP_DOT = '#497f6d'
LOOSE_DOT = '#df8958'
FRAME = '#dbc49c'


@lru_cache(maxsize=32)
def font(size):
    path = Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default(size=size)


def label(draw, x, y, value, size):
    draw.text((x, y), str(value), fill=INK, font=font(size), anchor='mm')


def dot(draw, x, y, radius, color):
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def sticker_strip(draw, box, *, cells=False):
    x, y, width, height = box
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height * .24,
                           fill=STRIP_FILL, outline=INK, width=max(1, round(height * .067)))
    gap = width / 11
    for column in range(10):
        center = x + (column + 1) * gap
        if cells:
            half = gap * .45
            draw.rectangle((center - half, y + height * .15, center + half, y + height * .85),
                           outline=FRAME, width=max(1, round(gap * .05)))
        dot(draw, center, y + height / 2, min(gap * .36, height * .25), STRIP_DOT)


def model(draw, box, value, *, numeral=True, tone=CREAM):
    x, y, width, height = box
    tens, ones = value['tens'], value['ones']
    if not (0 <= tens <= 9 and 0 <= ones <= 9 and 10 * tens + ones == value['value']):
        raise ValueError(f'invalid tens and ones model: {value}')
    draw.rounded_rectangle((x, y, x + width, y + height), radius=min(width, height) * .08,
                           fill=tone, outline=FRAME, width=max(2, round(height * .018)))
    if numeral:
        label(draw, x + width / 2, y + height * .17, value['value'], round(height * .22))
    first_row = .34 if numeral else .18
    columns = min(3, max(tens, 1))
    strip_width = width * .265
    for index in range(tens):
        row, column = divmod(index, columns)
        row_width = min(columns, tens - row * columns) * width * .30
        sticker_strip(draw, (x + (width - row_width) / 2 + column * width * .30,
                             y + height * (first_row + .135 * row), strip_width, height * .104))
    if ones:
        y_ratio = .83 if tens else (.62 if numeral else .50)
        gap = min(width * .092, height * .15)
        start = x + width / 2 - (ones - 1) * gap / 2
        for index in range(ones):
            dot(draw, start + index * gap, y + height * y_ratio, gap * .34, LOOSE_DOT)


def operands(draw, box, group):
    x, y, width, height = box
    card = width * .44
    model(draw, (x, y, card, height), group[0], tone='#fff4dd')
    label(draw, x + width / 2, y + height / 2, '+', round(height * .23))
    model(draw, (x + width - card, y, card, height), group[1], tone='#f7edcf')


def arrow(draw, x, y, width):
    draw.line((x, y, x + width, y), fill=INK, width=5)
    draw.polygon(((x + width, y), (x + width - 13, y - 10), (x + width - 13, y + 10)), fill=INK)


def render(asset):
    key, spec = asset['key'], asset['semantics']
    if 'originalScene' in spec:
        with Image.open(SOURCE / 'craft-sticker-table-base.png') as background:
            image = background.convert('RGB')
        draw = ImageDraw.Draw(image)
        model(draw, (93, 337, 330, 138), spec['groups'][0], numeral=False)
        model(draw, (472, 337, 298, 138), spec['groups'][1], numeral=False)
        return image
    if key == 'ten-dot-strip':
        image = Image.new('RGB', (540, 235), CREAM)
        sticker_strip(ImageDraw.Draw(image), (32, 55, 476, 125), cells=True)
        return image
    if 'before' in spec:
        image = Image.new('RGB', (920, 310), CREAM)
        draw = ImageDraw.Draw(image)
        operands(draw, (12, 23, 550, 258), spec['before'])
        arrow(draw, 577, 150, 65)
        model(draw, (657, 23, 250, 258), spec['after'], tone='#e9efda')
        return image
    if 'operands' in spec:
        width, height = (440, 268) if spec['format'] == 'tile' else (680, 308)
        image = Image.new('RGB', (width, height), CREAM)
        draw = ImageDraw.Draw(image)
        operands(draw, (9, 8, width - 18, height * .72), spec['operands'])
        label(draw, width / 2, height * .865, spec['formula'], round(height * .17))
        return image
    if spec.get('kind') == 'quiz operands':
        groups = spec['groups'] if isinstance(spec['groups'][0], list) else [spec['groups']]
        row_height = 222 if len(groups) == 1 else 162
        image = Image.new('RGB', (720, len(groups) * (row_height + 12) + 12), CREAM)
        draw = ImageDraw.Draw(image)
        for index, group in enumerate(groups):
            operands(draw, (15, 12 + index * (row_height + 12), 690, row_height), group)
        return image
    if isinstance(spec.get('option'), list):
        image = Image.new('RGB', (470, 430), CREAM)
        draw = ImageDraw.Draw(image)
        for index, value in enumerate(spec['option']):
            model(draw, (14, 12 + 209 * index, 442, 195), value)
        return image
    if 'models' in spec:
        image = Image.new('RGB', (780, 296), CREAM)
        draw = ImageDraw.Draw(image)
        for index, value in enumerate(spec['models']):
            model(draw, (12 + 256 * index, 17, 242, 260), value)
        return image
    value = spec.get('option', spec)
    image = Image.new('RGB', (460, 270), CREAM)
    label_value = not key.startswith('sort-') and not key.endswith('-unit-marker')
    model(ImageDraw.Draw(image), (11, 12, 438, 246), value, numeral=label_value)
    return image


def registered_diagrams():
    records = json.loads((SOURCE / 'diagram-specs.json').read_bytes())['assets']
    for record in records:
        image = render(record)
        png = BytesIO()
        image.save(png, format='PNG', optimize=True)
        yield record, image.size, png.getvalue()
