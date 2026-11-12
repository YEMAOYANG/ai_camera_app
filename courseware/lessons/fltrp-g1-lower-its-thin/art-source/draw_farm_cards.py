"""Arrange original animal cutouts at exact counts and comparable scales."""
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / 'assets'


@lru_cache(maxsize=80)
def sprite(kind, width):
    with Image.open(ASSETS / f'farm-{kind}.png') as source:
        image = source.convert('RGBA')
    mask = image.getchannel('A').point(lambda alpha: 255 if alpha >= 16 else 0)
    crop = image.crop(mask.getbbox())
    return crop.resize((width, round(width * crop.height / crop.width)), Image.Resampling.LANCZOS)


def photograph(specification):
    width, height = specification.get('canvas', [420, 250])
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), 14,
                           fill='#f9efd5', outline='#9cae89', width=3)
    baseline = height - 20
    draw.line((11, baseline + 1, width - 11, baseline + 1), fill='#aeb995', width=3)
    gap = specification.get('gap', 8)
    animals = [sprite(kind, size) for kind, size in specification['figures']]
    span = sum(animal.width for animal in animals) + gap * (len(animals) - 1)
    if not animals or span > width - 18 or any(animal.height > baseline - 9 for animal in animals):
        raise ValueError('Animal cutouts must stay inside the frame without overlap')
    left = (width - span) // 2
    for animal in animals:
        image.alpha_composite(animal, (left, baseline - animal.height))
        left += animal.width + gap
    if 'focus' in specification:
        draw.ellipse(specification['focus'], outline='#ad491f', width=5)
    return image


def main():
    recipes = json.loads((HERE / 'farm-cards.json').read_text(encoding='utf-8'))
    for key, specification in recipes.items():
        photograph(specification).save(ASSETS / f'{key}.png', optimize=True)


if __name__ == '__main__':
    main()
