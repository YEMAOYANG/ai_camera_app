"""Compose this lesson's near/far comparisons from its registered ImageGen art."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parent
SIZE = (640, 380)
PAPER = '#fff3d9'
INK = '#385a4d'
COURTYARD = 'quiz-brick-courtyard'
QUIZ_PALETTE_SIZE = 192
PLAYBACK_BOUNDS = {
    'bird-park-cover': (1000, 562),
    'lookout-background': (1120, 630),
    'lookout-guide': (550, 550),
    'yellow-bird': (420, 420),
    'blue-bird': (420, 420),
    'black-bird': (420, 420),
    'teaching-bag': (470, 470),
    'cat-prop': (420, 420),
    'cap-prop': (420, 420),
    'hat-prop': (420, 420),
    'rhythm-stage': (1000, 562),
    'classroom-desk-closeup': (1000, 562),
    'game-scout-rover': (240, 240),
    'game-scout-rover-pop': (240, 240),
    'game-stage-marble': (200, 200),
}


@dataclass(frozen=True)
class Placement:
    asset: str
    x: int
    baseline: int
    width: int
    height: int
    mirror: bool = False
    framed: bool = False


@dataclass(frozen=True)
class Card:
    background: str
    items: tuple[Placement, ...]
    speaker: bool = False
    stand: bool = False
    focus: tuple[int, int, int, int] | None = None

    @property
    def inputs(self):
        return tuple(dict.fromkeys((self.background, *(item.asset for item in self.items))))


def speaker(x, *, left=False):
    return Placement('lookout-guide', x, 322, 128, 236, left)


def exhibit(asset, x, *, framed=False):
    return Placement(asset, x, 319, 142, 156, framed=framed)


def comparison(asset, subject_x, speaker_x=136, background=COURTYARD, *, framed=False):
    return Card(background, (speaker(speaker_x, left=speaker_x > subject_x), exhibit(asset, subject_x, framed=framed)),
                speaker=True)


def display(asset, background=COURTYARD, *, framed=False):
    return Card(background, (Placement(asset, 320, 296, 238, 219, framed=framed),), stand=True)


CARDS = {
    'near-desk-example': comparison('reference-green-book-desk', 497, 338, 'lookout-background', framed=True),
    'far-desk-example': comparison('reference-green-book-desk', 497, 136, 'lookout-background', framed=True),
    'classroom-door-distance': Card('classroom-door-visit', (), focus=(544, 186, 615, 206)),
    'near-blue-example': comparison('blue-bird', 291, background='lookout-background'),
    'far-black-example': comparison('black-bird', 522, background='lookout-background'),
    'three-stage-props': Card('lookout-background', (
        Placement('cat-prop', 131, 295, 154, 188),
        Placement('cap-prop', 320, 295, 155, 167),
        Placement('hat-prop', 509, 295, 155, 167),
    ), stand=True),
    'quiz-fair-cat': display('cat-prop', COURTYARD, framed=True),
    'quiz-fair-schoolbag': display('reference-orange-schoolbag', COURTYARD, framed=True),
    'quiz-fair-blue-bird': display('blue-bird', COURTYARD, framed=True),
    'quiz-courtyard-display-cat': display('cat-prop', COURTYARD),
    'quiz-courtyard-display-knit-hat': display('hat-prop', COURTYARD),
    'quiz-courtyard-display-baseball-cap': display('cap-prop', COURTYARD),
    'quiz-courtyard-near-blue': comparison('blue-bird', 289, background=COURTYARD),
    'quiz-courtyard-far-black': comparison('black-bird', 525, background=COURTYARD),
    'quiz-courtyard-far-blue': comparison('blue-bird', 525, background=COURTYARD),
    'quiz-courtyard-near-black-cat': comparison('quiz-black-cat', 289),
    'quiz-courtyard-far-black-cat': comparison('quiz-black-cat', 525),
    'quiz-courtyard-near-cream-cat': comparison('cat-prop', 289),
    'quiz-reporter-stimulus': Card(COURTYARD, (speaker(535, left=True),), speaker=True),
    'quiz-reporter-right-near-black': comparison('black-bird', 382, 535, COURTYARD),
    'quiz-reporter-left-far-black': comparison('black-bird', 382, 90, COURTYARD),
    'quiz-reporter-right-near-blue': comparison('blue-bird', 382, 535, COURTYARD),
    'quiz-school-near-desk': comparison('reference-green-book-desk', 289, background=COURTYARD, framed=True),
    'quiz-school-far-desk': comparison('reference-green-book-desk', 525, background=COURTYARD, framed=True),
    'quiz-school-far-schoolbag': comparison('reference-orange-schoolbag', 525, background=COURTYARD, framed=True),
}


def visible_sprite(source, name):
    if 'A' not in source.getbands():
        raise ValueError(f'{name}: expected the registered transparent PNG')
    sprite = source.convert('RGBA')
    alpha = sprite.getchannel('A')
    if alpha.getextrema()[0] != 0:
        raise ValueError(f'{name}: background is not transparent')
    box = alpha.point(lambda value: 255 if value >= 8 else 0).getbbox()
    if not box:
        raise ValueError(f'{name}: empty sprite')
    return sprite.crop(box)


def framed_exhibit(source, placement):
    picture = visible_sprite(source, placement.asset) if 'A' in source.getbands() else source.convert('RGBA')
    size = (placement.width, placement.height)
    tile = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=12, fill='#fff4dc', outline='#d8be95', width=3)
    picture = ImageOps.contain(picture, (size[0] - 20, size[1] - 20), Image.Resampling.LANCZOS)
    tile.alpha_composite(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2))
    return tile


def render(card, images):
    image = ImageOps.fit(images[card.background].convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
    if card.focus is not None:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(card.focus, radius=5, outline='#fff4dc', width=7)
        draw.rounded_rectangle(card.focus, radius=5, outline='#a84725', width=4)
        return image.convert('RGB')
    overlay = Image.new('RGBA', SIZE)
    draw = ImageDraw.Draw(overlay)
    if card.stand:
        draw.rounded_rectangle((35, 39, 605, 343), radius=32, fill=(255, 247, 226, 231))
        draw.rounded_rectangle((52, 292, 588, 322), radius=13, fill='#d3a377')
    else:
        draw.rounded_rectangle((22, 34, 618, 352), radius=28, fill=(255, 247, 226, 216))
        draw.line((36, 322, 604, 322), fill='#cbb597', width=4)
    image.alpha_composite(overlay)
    for item in card.items:
        sprite = framed_exhibit(images[item.asset], item) if item.framed else visible_sprite(images[item.asset], item.asset)
        if item.mirror:
            sprite = ImageOps.mirror(sprite)
        sprite = ImageOps.contain(sprite, (item.width, item.height), Image.Resampling.LANCZOS)
        left, top = item.x - sprite.width // 2, item.baseline - sprite.height
        if not (0 <= left and left + sprite.width <= SIZE[0] and 0 <= top < item.baseline <= SIZE[1]):
            raise ValueError(f'{item.asset}: composition would crop an object')
        image.alpha_composite(sprite, (left, top))
    if card.speaker:
        reporter = card.items[0]
        marker = ImageDraw.Draw(image)
        x = reporter.x
        marker.rounded_rectangle((x - 26, 43, x + 26, 71), radius=12, fill=INK)
        marker.polygon(((x - 7, 69), (x + 7, 69), (x + 2, 77)), fill=INK)
        for offset in (0, 6, 12):
            marker.arc((x - 12 + offset, 50, x + 2 + offset, 65), -65, 65, fill=PAPER, width=2)
    return image.convert('RGB')


def playback_image(source, bounds):
    image = source.copy()
    image.thumbnail(bounds, Image.Resampling.LANCZOS)
    return image


def registered_image(asset_dir, key, entry):
    path = asset_dir / f'{key}.png'
    raw = path.read_bytes()
    if entry['sourceKind'] != 'codex_builtin_imagegen' or sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError(f'{key}: source is not the registered ImageGen original')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != 'PNG':
            raise ValueError(f'{key}: expected a PNG master')
        return image.copy()


def png_bytes(image):
    with io.BytesIO() as buffer:
        image.save(buffer, format='PNG', optimize=True)
        return buffer.getvalue()


def render_card_asset(key, master_images, entries, renderer_hash):
    card = CARDS[key]
    previous = entries.get(key)
    if previous and previous.get('sourceKind') != 'deterministic_imagegen_composition':
        raise ValueError(f'{key}: refusing to replace a registered original illustration')
    image = render(card, master_images)
    is_quiz = key.startswith('quiz-')
    if is_quiz:
        image = image.quantize(colors=QUIZ_PALETTE_SIZE, method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE)
    data = png_bytes(image)
    record = {
        'sourceKind': 'deterministic_imagegen_composition',
        'path': f'assets/{key}.png',
        'sha256': sha256(data).hexdigest(),
        'bytes': len(data),
        'pixels': list(SIZE),
        'renderer': 'illustrations.py',
        'rendererSha256': renderer_hash,
        'inputs': [{'key': name, 'path': entries[name]['path'], 'sha256': entries[name]['sha256']}
                   for name in card.inputs],
    }
    if is_quiz:
        record['encoding'] = {'mode': 'indexed_png', 'colors': QUIZ_PALETTE_SIZE, 'method': 'median_cut', 'dither': False}
    return data, record


def write_illustrations(root, *, available_only=False):
    asset_dir = root / 'assets'
    provenance_file = root / 'asset-provenance.json'
    provenance = json.loads(provenance_file.read_text(encoding='utf-8'))
    entries = provenance['assets']
    master_keys = set(PLAYBACK_BOUNDS) | {name for card in CARDS.values() for name in card.inputs}
    unavailable = {name for name in master_keys if name not in entries or not (asset_dir / f'{name}.png').is_file()}
    if not available_only and unavailable:
        raise ValueError(f'Missing registered source illustrations: {", ".join(sorted(unavailable))}')
    missing = {
        key: tuple(name for name in card.inputs if name in unavailable)
        for key, card in CARDS.items()
    }

    renderer_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    master_images = {name: registered_image(asset_dir, name, entries[name])
                     for name in sorted(master_keys - unavailable)}
    rendered = {}
    for key in CARDS:
        if missing[key]:
            continue
        rendered[key], entries[key] = render_card_asset(key, master_images, entries, renderer_hash)

    lesson_file = root / 'lesson.json'
    lesson = json.loads(lesson_file.read_text(encoding='utf-8'))
    playback = provenance.setdefault('playbackAssets', {})
    playback_files = {}
    playback_changed = False
    for key, bounds in PLAYBACK_BOUNDS.items():
        if key in unavailable:
            continue
        image = playback_image(master_images[key], bounds)
        data = png_bytes(image)
        if len(data) >= entries[key]['bytes']:
            if key in playback:
                playback.pop(key)
                lesson['images'][key] = {'file': entries[key]['path']}
                playback_changed = True
            continue
        target = f'assets/playback/{key}.png'
        playback_files[key] = data
        playback[key] = {
            'sourceKind': 'resized_imagegen_playback',
            'path': target,
            'sha256': sha256(data).hexdigest(),
            'bytes': len(data),
            'pixels': list(image.size),
            'sourcePath': entries[key]['path'],
            'sourceSha256': entries[key]['sha256'],
            'rendererSha256': renderer_hash,
        }
        lesson['images'][key] = {'file': target}
        playback_changed = True

    for key, data in rendered.items():
        (asset_dir / f'{key}.png').write_bytes(data)
    if playback_files:
        playback_dir = asset_dir / 'playback'
        playback_dir.mkdir(exist_ok=True)
        for key, data in playback_files.items():
            (playback_dir / f'{key}.png').write_bytes(data)
    if playback_changed:
        lesson_file.write_text(json.dumps(lesson, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if rendered or playback_changed:
        provenance_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return tuple(rendered), {key: names for key, names in missing.items() if names}, tuple(playback_files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--available-only', action='store_true')
    args = parser.parse_args()
    ready, pending, playback = write_illustrations(ROOT, available_only=args.available_only)
    print(f'Composed {len(ready)} cards; {len(pending)} wait for source illustrations.')
    print(f'Prepared {len(playback)} smaller playback copies from registered originals.')
    for key, dependencies in pending.items():
        print(f'{key}: {", ".join(dependencies)}')
