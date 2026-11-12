"""Arrange speakers, groups and sports from the lesson's generated cutouts."""

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'


@lru_cache(maxsize=32)
def cutout(key):
    with Image.open(ASSETS / f'sport-{key}.png') as source:
        image = source.convert('RGBA')
    outline = image.getchannel('A').point(lambda alpha: 255 if alpha >= 32 else 0)
    return image.crop(outline.getbbox())


def card(specification):
    width, height = specification['canvas']
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    if specification.get('mat'):
        draw.rounded_rectangle((1, 1, width - 2, height - 2), 20,
                               fill='#fff3d8', outline='#9baf9b', width=3)
    for panel in specification.get('groups', []):
        draw.rounded_rectangle(tuple(panel), 16, fill='#d6ebe1', outline='#3b8576', width=4)
    boxes = []
    for key, x, y, max_width, max_height, flip in specification['pieces']:
        piece = cutout(key).copy()
        if flip:
            piece = ImageOps.mirror(piece)
        piece.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        left, top = x - piece.width // 2, y - piece.height // 2
        right, bottom = left + piece.width, top + piece.height
        if not (2 <= left < right <= width - 2 and 2 <= top < bottom <= height - 2):
            raise ValueError(f'{key} does not fit on its picture card')
        if any(left < r and l < right and top < b and t < bottom for l, t, r, b in boxes):
            raise ValueError(f'{key} overlaps another picture')
        image.alpha_composite(piece, (left, top))
        boxes.append((left, top, right, bottom))
    return image


def main():
    recipes = json.loads((HERE / 'sport-cards.json').read_text(encoding='utf-8'))
    for key, specification in recipes.items():
        card(specification).save(ASSETS / f'sport-{key}.png', optimize=True)


if __name__ == '__main__':
    main()
