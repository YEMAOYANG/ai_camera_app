"""Render the two age games' playback art from their archived masters."""

import io
import json
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
BACKDROPS = ('marble-workshop', 'delivery-workshop')
ACTOR_ATLAS = 'interview-game-actors-atlas'
GUEST_ATLAS = 'workshop-guests-atlas'
ACTOR_CROPS = {
    'reporter-van': (155, 69, 473, 573),
    # Register the matching van frames to the same scale and wheel positions.
    'reporter-van-loaded': (774, 69, 1092, 573),
    'traffic-van': (51, 776, 580, 1100),
    'reporter-sticker': (678, 674, 1184, 1190),
}
GUEST_CELLS = {
    'guest-cap': (0, 0, 512, 530),
    'guest-phones': (512, 0, 1024, 530),
    'guest-scarf': (1024, 0, 1536, 530),
    'guest-headband': (0, 530, 512, 1024),
    'guest-bowtie': (512, 530, 1024, 1024),
    'guest-glasses': (1024, 530, 1536, 1024),
}
SOURCE_GROUPS = {
    'marble-workshop': ('marble-workshop',),
    'delivery-workshop': ('delivery-workshop',),
    ACTOR_ATLAS: tuple(ACTOR_CROPS),
    GUEST_ATLAS: tuple(GUEST_CELLS),
}
OPENINGS = {
    'marble-opening': ('marble-workshop', {
        'badge-six': ((281, 217), (210, 210)),
        'badge-nine': ((487, 217), (210, 210)),
    }),
    'delivery-opening': ('delivery-workshop', {
        'reporter-van': ((212, 259), (160, 196)),
        'guest-cap': ((548, 221), (177, 185)),
        'badge-six': ((382, 224), (145, 145)),
    }),
}


def guest_crop(original, cell):
    """Trim the empty gutter with six pixels of margin around visible alpha."""
    alpha = original.crop(cell).getchannel('A')
    left, top, right, bottom = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
    return (max(cell[0], cell[0] + left - 6), max(cell[1], cell[1] + top - 6),
            min(cell[2], cell[0] + right + 6), min(cell[3], cell[1] + bottom + 6))


def source_art(key, original):
    if key in BACKDROPS:
        backdrop = ImageOps.fit(original.convert('RGB'), (1280, 720), Image.Resampling.LANCZOS)
        return backdrop, None
    crop = ACTOR_CROPS[key] if key in ACTOR_CROPS else guest_crop(original, GUEST_CELLS[key])
    sprite = ImageOps.contain(original.crop(crop), (240, 240), Image.Resampling.LANCZOS)
    return sprite, crop


def opening_art(key, load):
    backdrop, elements = OPENINGS[key]
    image = load(backdrop).convert('RGBA').resize((768, 432), Image.Resampling.LANCZOS)
    for prop, ((x, y), limits) in elements.items():
        sprite = ImageOps.contain(load(prop).convert('RGBA'), limits, Image.Resampling.LANCZOS)
        image.alpha_composite(sprite, (x - sprite.width // 2, y - sprite.height // 2))
    return image.convert('RGB')


def png(image):
    with io.BytesIO() as stream:
        image.save(stream, format='PNG', optimize=True)
        return stream.getvalue()


def write_game_art():
    manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))
    assets = manifest['assets']
    sources = manifest['imagegenOriginals']
    for source, keys in SOURCE_GROUPS.items():
        with Image.open(ROOT / sources[source]['path']) as original:
            for key in keys:
                image, _ = source_art(key, original)
                (ROOT / assets[key]['path']).write_bytes(png(image))

    def load(key):
        with Image.open(ROOT / assets[key]['path']) as image:
            return image.copy()

    for key in OPENINGS:
        (ROOT / assets[key]['path']).write_bytes(png(opening_art(key, load)))


if __name__ == '__main__':
    write_game_art()
