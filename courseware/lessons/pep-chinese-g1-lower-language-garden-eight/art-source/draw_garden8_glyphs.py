"""Render standard glyphs and measured grids for this lesson's visual cards."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
DATA = HERE / 'garden8-glyph-cards.json'
INK = '#233b32'
MUTED = '#565e59'
BACKGROUND = '#fff6df'


def render(card, font):
    width, height = card['canvas']
    image = Image.new('RGB', (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for cell in card['cells']:
        x, y, w, h = cell['bounds']
        if x < 0 or y < 0 or x + w > width or y + h > height:
            raise ValueError('glyph cell extends outside its card')
        if cell.get('grid'):
            draw.rectangle((x, y, x + w, y + h), fill='#fffdf4', outline='#739b9b', width=2)
            draw.line((x + w // 2, y + 4, x + w // 2, y + h - 4), fill='#cbded8')
            draw.line((x + 4, y + h // 2, x + w - 4, y + h // 2), fill='#cbded8')
        if cell.get('muted'):
            draw.rounded_rectangle((x + 2, y + 2, x + w - 2, y + h - 2), 12, fill='#e5e5da')
        glyph = cell['glyph']
        if not glyph:
            continue
        face = font(cell['size'])
        left, top, right, bottom = draw.textbbox((0, 0), glyph, font=face)
        if right - left > w or bottom - top > h:
            raise ValueError(f'{glyph} exceeds its layout cell')
        ink_x = x + (w - right + left) / 2 - left
        ink_y = y + (h - bottom + top) / 2 - top
        if cell.get('punctuation'):
            ink_x, ink_y = x + 7 - left, y + h - (bottom - top) - 9 - top
        draw.text((ink_x, ink_y), glyph, font=face, fill=MUTED if cell.get('muted') else INK)
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(DATA.read_text(encoding='utf-8'))
    spec = data['font']
    if sha256(args.font.read_bytes()).hexdigest() != spec['sha256']:
        raise ValueError('Select the recorded regular Kaiti SC font')
    assets = HERE.parent / 'assets'
    assets.mkdir(exist_ok=True)
    fonts = {}

    def font(size):
        if size not in fonts:
            fonts[size] = ImageFont.truetype(args.font, size=size, index=spec['index'])
        return fonts[size]

    for key, card in data['cards'].items():
        render(card, font).save(assets / f'garden8-{key}.png', optimize=True)


if __name__ == '__main__':
    main()
