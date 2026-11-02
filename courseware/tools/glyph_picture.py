"""Render small, content-addressed quiz illustrations."""

import hashlib
import io
import math

from PIL import Image, ImageDraw, ImageFont


_SIZE = (480, 240)
_EMOJI_FONT = '/System/Library/Fonts/Apple Color Emoji.ttc'
_TEXT_FONT = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'


def _layout_cells(spec):
    """Return cell positions in logical units and the total layout dimensions."""
    groups = spec['groups']
    separator = spec.get('separator', 'gap')
    if separator not in {'gap', 'plus', 'equals', 'none'}:
        raise ValueError('invalid separator')
    cells = []
    signs = []
    x = 0
    for index, group in enumerate(groups):
        if index:
            if separator in {'plus', 'equals'}:
                signs.append((x + 0.5, '+' if separator == 'plus' else '='))
                x += 1
            elif separator == 'gap':
                x += 0.5
        items = group['cells']
        columns = math.ceil(len(items) / 2) if len(items) > 8 else len(items)
        for i, cell in enumerate(items):
            cells.append((x + i % columns, i // columns, cell))
        x += columns
    return cells, signs, max(x, 1), 2 if any(len(g['cells']) > 8 for g in groups) else 1


def render_picture(spec):
    cells, signs, width, height = _layout_cells(spec)
    unit = 200
    canvas = Image.new('RGBA', (math.ceil(width * unit), height * unit), 'white')
    draw = ImageDraw.Draw(canvas)
    emoji_font = ImageFont.truetype(_EMOJI_FONT, 160)
    text_font = ImageFont.truetype(_TEXT_FONT, 140)
    for x, y, cell in cells:
        glyph = cell['glyph']
        emoji = any(ord(c) >= 0x1F000 for c in glyph)
        font = emoji_font if emoji else text_font
        box = draw.textbbox((0, 0), glyph, font=font, embedded_color=emoji)
        draw.text((x * unit + (unit - box[2] - box[0]) / 2,
                   y * unit + (unit - box[3] - box[1]) / 2), glyph,
                  font=font, fill='black', embedded_color=emoji)
        bounds = (x * unit + 8, y * unit + 8, (x + 1) * unit - 8, (y + 1) * unit - 8)
        if cell.get('highlight'):
            draw.ellipse(bounds, outline='#eb9200', width=10)
        if cell.get('crossed'):
            left, top, right, bottom = bounds
            draw.line((left, top, right, bottom), fill='#d62828', width=12)
            draw.line((left, bottom, right, top), fill='#d62828', width=12)
    for x, sign in signs:
        box = draw.textbbox((0, 0), sign, font=text_font)
        draw.text((x * unit - (box[2] + box[0]) / 2,
                   height * unit / 2 - (box[3] + box[1]) / 2), sign, font=text_font, fill='black')
    canvas.thumbnail((_SIZE[0] - 16, _SIZE[1] - 16), Image.Resampling.LANCZOS)
    result = Image.new('RGBA', _SIZE, 'white')
    result.alpha_composite(canvas, ((_SIZE[0] - canvas.width) // 2, (_SIZE[1] - canvas.height) // 2))
    output = io.BytesIO()
    result.save(output, format='PNG')
    return output.getvalue()


def png_name(png_bytes):
    return hashlib.sha256(png_bytes).hexdigest() + '.png'
