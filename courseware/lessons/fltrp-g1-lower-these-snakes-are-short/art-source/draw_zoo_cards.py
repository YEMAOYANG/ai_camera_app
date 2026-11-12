"""Compose measured picture comparisons from the lesson's generated cutouts."""
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'


@lru_cache(maxsize=64)
def sprite(key, dimension, size):
    with Image.open(ASSETS / f'zoo-{key}.png') as source:
        image = source.convert('RGBA')
    outline = image.getchannel('A').point(lambda a: 255 if a >= 16 else 0)
    art = image.crop(outline.getbbox())
    if dimension == 'width':
        return art.resize((size, round(size * art.height / art.width)), Image.Resampling.LANCZOS)
    if dimension == 'height':
        return art.resize((round(size * art.width / art.height), size), Image.Resampling.LANCZOS)
    raise ValueError('Choose width or height as the comparison dimension')


def card(specification):
    width, height = specification['canvas']
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), 14,
                           fill='#fbf1db', outline='#a4ad89', width=3)
    for x, y, end_x, end_y in specification.get('guides', []):
        draw.line((x, y, end_x, end_y), fill='#9ba47c', width=3)
    boxes = []
    for key, dimension, size, x, bottom in specification['subjects']:
        art = sprite(key, dimension, size)
        top = bottom - art.height
        right = x + art.width
        if x < 6 or top < 6 or right > width - 6 or bottom > height - 6:
            raise ValueError(f'{key} does not fit the card')
        if any(x < r and l < right and top < b and t < bottom for l, t, r, b in boxes):
            raise ValueError(f'{key} overlaps another picture')
        image.alpha_composite(art, (x, top))
        boxes.append((x, top, right, bottom))
    return image


def main():
    recipes = json.loads((HERE / 'zoo-cards.json').read_text(encoding='utf-8'))
    for key, specification in recipes.items():
        card(specification).save(ASSETS / f'{key}.png', optimize=True)


if __name__ == '__main__':
    main()
