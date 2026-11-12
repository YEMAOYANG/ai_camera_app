"""Render equal-scale comparisons and exact quantity cards for this lesson."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ART = Path(__file__).resolve().parent
LESSON = ART.parent
PAPER = '#fff5df'
INK = '#234839'
EQUAL = '#8fb29a'
EXTRA = '#ed9c60'
MISSING = '#9d7450'
BORDER = '#d9be94'
MARKERS = {'square': '#3d7968', 'round': '#be642f', 'triangle': '#805e91'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label(draw, point, text, size):
    system_font = Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
    font = (ImageFont.truetype(str(system_font), size) if system_font.is_file()
            else ImageFont.load_default(size=size))
    draw.text(point, str(text), fill=INK, font=font, anchor='mm')


def marker(draw, center, kind, size):
    x, y = center
    h = size / 2
    box = (x - h, y - h, x + h, y + h)
    if kind == 'square':
        draw.rounded_rectangle(box, radius=h * .2, fill=MARKERS[kind])
    elif kind == 'round':
        draw.ellipse(box, fill=MARKERS[kind])
    elif kind == 'triangle':
        draw.polygon([(x, y - h), (x - h, y + h), (x + h, y + h)], fill=MARKERS[kind])
    else:
        raise ValueError(f'Unknown group marker {kind}')


def bracket(draw, start, end, y):
    draw.line([(start, y - 9), (start, y), (end, y), (end, y - 9)], fill=INK, width=5)


def comparison(rows, reference, scale, *, marked=None, compact=False, hidden_number=None):
    """Rows are (marker, count, visible missing cells). All share the left origin."""
    if not rows or any(not 0 <= count <= scale or count + missing > scale for _, count, missing in rows):
        raise ValueError('A comparison row exceeds its common scale.')
    width = 780
    height = (390 if len(rows) == 3 else 260) if not compact else 275
    image = Image.new('RGB', (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, width - 5, height - 5), radius=24, outline=BORDER, width=3)
    x0 = 196 if compact else 91
    step = (width - x0 - (32 if compact else 69)) / scale
    bar = min(50, step * .83)
    h = height / len(rows)
    draw.line((x0 - 2, h * .18, x0 - 2, height - h * .24), fill=BORDER, width=4)
    for index, (kind, count, missing) in enumerate(rows):
        y = (65, 166)[index] if compact else round((index + .45) * h)
        marker(draw, (48, y), kind, 64 if compact else 42)
        for unit in range(count):
            x = x0 + unit * step
            grouped = (unit + 1) % 10 == 0
            cell_fill = EQUAL if unit < reference else EXTRA
            draw.rounded_rectangle((x + 1, y - bar / 2, x + step - (3 if grouped else 1),
                                    y + bar / 2), radius=min(bar * .24, 4), fill=cell_fill)
            if grouped:
                draw.line((x + step - 1, y - bar / 2 - 5, x + step - 1, y + bar / 2 + 5),
                          fill=INK, width=2)
        for unit in range(count, count + missing):
            left = x0 + unit * step + 2
            right = left + step - 5
            for line in (y - bar / 2, y + bar / 2):
                draw.line((left, line, right, line), fill=MISSING, width=3)
            draw.line((right, y - bar / 3, right, y + bar / 3), fill=MISSING, width=2)
        if compact:
            label(draw, (135, y), '?' if index == hidden_number else count, 64)
        elif count and index != hidden_number:
            label(draw, (x0 + count * step - 15, y - bar / 2 - 24), count, 31)
        elif index == hidden_number:
            label(draw, (x0 + (count + missing) * step + 28, y), '?', 32)
        if marked and index == marked[0]:
            _, start, end, number = marked
            bracket(draw, x0 + start * step + 1, x0 + end * step - 1, y + bar / 2 + 16)
            if number is not None:
                label(draw, (x0 + (start + end) * step / 2, y + bar / 2 + (49 if compact else 39)), number, 62 if compact else 29)
    return image


def quantity(value, *, square=False):
    if not 0 < value < 60:
        raise ValueError('Invalid quantity card.')
    width, height = (320, 320) if square else (500, 280)
    image = Image.new('RGB', (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, width - 5, height - 5), radius=24, outline=BORDER, width=3)
    label(draw, (width / 2, height * .18), value, round(height * (.32 if square else .22)))
    tens, singles = divmod(value, 10)
    rows = tens + bool(singles)
    cell = min(width / 12, height * .085)
    for row in range(rows):
        count = 10 if row < tens else singles
        y = height * (.39 if square else .32) + row * (height * (.55 if square else .62) / rows)
        start = (width - count * cell) / 2
        if row < tens:
            draw.rounded_rectangle((start - 4, y - 4, start + 10 * cell + 4, y + cell + 4),
                                   radius=5, fill='#e3ead4', outline=MARKERS['square'], width=2)
        for column in range(count):
            x = start + column * cell
            inset = cell * .18
            draw.rounded_rectangle((x + inset, y + inset, x + cell - inset, y + cell - inset),
                                   radius=3, fill=EQUAL if row < tens else EXTRA)
    return image


def condition_cards(conditions):
    image = Image.new('RGB', (250 * len(conditions), 215), PAPER)
    for index, (kind, number, operation) in enumerate(conditions):
        x = 250 * index
        card = quantity(number).resize((234, 131), Image.Resampling.LANCZOS)
        image.paste(card, (x + 8, 65))
        draw = ImageDraw.Draw(image)
        marker(draw, (x + 123, 32), kind, 36)
        if operation:
            label(draw, (x + 160, 32), operation, 35)
    return image


def order_card(reference, signed_gap):
    """A whole reference row and a visibly attached or dashed change in the target row."""
    target = reference + signed_gap
    rows = [('square', reference, 0), ('round' if signed_gap > 0 else 'triangle',
                                      target, max(0, -signed_gap))]
    return comparison(rows, reference, max(reference, target),
                      marked=(1, min(reference, target), max(reference, target), abs(signed_gap)),
                      compact=True, hidden_number=1)


def record(records, key, image, **metadata):
    path = LESSON / 'assets' / f'{key}.png'
    image.save(path, format='PNG', optimize=True)
    records[key] = {
        'file': f'assets/{key}.png',
        'sha256': sha256(path),
        'bytes': path.stat().st_size,
        'pixels': list(image.size),
        **metadata,
    }


def registered_diagrams():
    def compare(key, rows, reference, scale, marked=None, where=None):
        return key, comparison(rows, reference, scale, marked=marked), {
            'kind': 'aligned unit cells', 'rows': rows, 'reference': reference, 'scale': scale,
            'bracket': marked, 'usedBy': [where] if where else [],
        }

    def quant(key, value, where, square=False):
        return key, quantity(value, square=square), {
            'kind': 'exact groups of ten and loose cells', 'value': value, 'usedBy': [where],
        }

    square, round_, triangle = 'square', 'round', 'triangle'
    rows_more = [(square, 8, 0), (round_, 13, 0)]
    rows_fewer = [(square, 16, 0), (triangle, 10, 6)]
    yield compare('known-row', [(square, 8, 0), (round_, 0, 0)], 8, 13, where='listen-for-the-target')
    yield compare('same-and-extra', rows_more, 8, 13, (1, 8, 13, 5), 'join-the-extra-row')
    yield compare('whole-target-row', rows_more, 8, 13, (1, 0, 13, 13), 'join-the-extra-row')
    yield compare('short-row-gap', rows_fewer, 16, 16, (1, 10, 16, 6), 'fold-away-the-gap')
    yield compare('short-row-whole', rows_fewer, 16, 16, (1, 0, 10, 10), 'fold-away-the-gap')
    yield compare('window-with-more', [(square, 38, 0), (round_, 54, 0)], 38, 54, (1, 38, 54, 16),
                  'keep-one-reference')
    yield compare('window-with-fewer', [(square, 38, 0), (triangle, 29, 9)], 38, 54, (1, 29, 38, 9),
                  'keep-one-reference')
    yield compare('review-reference', [(square, 38, 0), (round_, 54, 0), (triangle, 29, 9)],
                  38, 54, where='recap-compare-with-one-group')
    for reference, gap in [(6, 2), (9, 3), (11, -2), (15, -7), (24, 7), (26, -8)]:
        where = 'arrange-prop-tiles'
        key = f'tile-{reference}-{"plus" if gap > 0 else "minus"}-{abs(gap)}'
        yield key, order_card(reference, gap), {
            'kind': 'comparison order', 'reference': reference, 'signedGap': gap, 'usedBy': [where],
        }
    for total in (8, 12, 9, 31, 18):
        yield quant(f'tile-total-{total}', total, 'arrange-prop-tiles', square=True)
    for reference, gap in [(5, 4), (10, -3), (18, -8), (23, 9), (27, -11)]:
        key = f'delivery-{reference}-{"plus" if gap > 0 else "minus"}-{abs(gap)}'
        yield key, order_card(reference, gap), {
            'kind': 'comparison order', 'reference': reference, 'signedGap': gap,
            'usedBy': ['deliver-the-right-count'],
        }
    for total in (7, 9, 10, 13, 16, 23, 32):
        yield quant(f'delivery-total-{total}', total, 'deliver-the-right-count', square=True)
    for kind in (round_, triangle):
        icon = Image.new('RGBA', (120, 120))
        marker(ImageDraw.Draw(icon), (60, 60), kind, 87)
        yield f'window-{kind}', icon, {
            'kind': 'fixed geometric group marker', 'marker': kind,
            'usedBy': ['deliver-the-right-count'],
        }

    quiz_conditions = [
        [(square, 7, ''), (round_, 4, '+')],
        [(square, 13, ''), (triangle, 5, '−')],
        [(square, 28, ''), (round_, 7, '+')],
        [(square, 21, ''), (triangle, 8, '−')],
        [(round_, 12, '+'), (square, 34, ''), (triangle, 6, '−')],
        [(square, 25, ''), (triangle, 19, '')],
    ]
    for index, conditions in enumerate(quiz_conditions, 1):
        yield f'q{index}-conditions', condition_cards(conditions), {
            'kind': 'given and comparison quantities', 'conditions': conditions, 'usedBy': [f'q{index}'],
        }
    rows_1 = [(square, 7, 0), (round_, 11, 0)]
    for letter, mark in zip('abc', [(0, 0, 7, None), (1, 0, 11, None), (1, 7, 11, None)]):
        yield compare(f'q1-{letter}', rows_1, 7, 11, mark, 'q1')
    for letter, result in zip('abc', (13, 18, 8)):
        yield compare(f'q2-{letter}', [(square, 13, 0), (triangle, result, max(0, 13-result))],
                      13, 18, where='q2')
    for letter, value in zip('abc', (35, 21, 7)):
        yield quant(f'q3-{letter}', value, 'q3')
    for letter, value in zip('abc', (29, 13, 8)):
        yield quant(f'q4-{letter}', value, 'q4')
    for letter, (left, right) in zip('abc', ((28, 28), (28, 46), (46, 28))):
        yield compare(f'q5-{letter}', [(round_, left, 0), (square, 34, 0), (triangle, right, 0)],
                      34, 46, where='q5')
    for letter, result in zip('abc', (19, 20, 31)):
        yield compare(f'q6-{letter}', [(square, 25, 0), (triangle, result, max(0, 25-result))],
                      25, 31, (1, min(25, result), max(25, result), abs(25-result)), 'q6')


def make_assets():
    records = {}
    plate_path = ART / 'puppet-theater-atlas.png'
    sprites_path = ART / 'puppet-theater-sprites.png'
    atlas_sha = sha256(plate_path)
    with Image.open(plate_path) as atlas:
        for key, crop, where in [
            ('theater-cover', (13, 11, 502, 501), 'listen-for-the-target'),
            ('theater-stage', (524, 12, 1011, 500), 'arrange-prop-tiles'),
            ('theater-path', (1035, 12, 1523, 501), 'deliver-the-right-count'),
        ]:
            cropped = atlas.crop(crop).convert('RGBA')
            matte = Image.new('RGBA', cropped.size, PAPER)
            matte.alpha_composite(cropped)
            fitted = (matte.convert('RGB').resize((480, 480), Image.Resampling.LANCZOS)
                      if key == 'theater-cover' else
                      ImageOps.fit(matte.convert('RGB'), (480, 270), Image.Resampling.LANCZOS))
            record(records, key, fitted, type='imagegen_plate_crop',
                   sourceAtlas='art-source/puppet-theater-atlas.png', sourceAtlasSha256=atlas_sha,
                   sourceCropPx=list(crop), usedBy=[where],
                   visualReview='Original cut-paper scene inspected; browser rendering pending.')
    atlas_sha = sha256(sprites_path)
    with Image.open(sprites_path) as atlas:
        for key, crop, uses in [
            ('wood-cart', (40, 60, 671, 643), ['arrange-prop-tiles', 'deliver-the-right-count']),
            ('wood-cart-moving', (683, 60, 1430, 655), ['deliver-the-right-count']),
            ('wood-van', (1450, 65, 2163, 649), ['deliver-the-right-count']),
        ]:
            sprite = atlas.crop(crop).convert('RGBA')
            alpha = sprite.getchannel('A')
            if not alpha.getextrema() == (0, 255):
                raise ValueError(f'Sprite {key} must have an actual transparent field.')
            sprite = sprite.crop(alpha.getbbox())
            sprite.thumbnail((180, 180), Image.Resampling.LANCZOS)
            record(records, key, sprite, type='imagegen_sprite_crop',
                   sourceAtlas='art-source/puppet-theater-sprites.png', sourceAtlasSha256=atlas_sha,
                   sourceCropPx=list(crop), usedBy=uses,
                   visualReview='Original silhouette and alpha inspected; browser rendering pending.')
    for key, image, semantics in registered_diagrams():
        record(records, key, image, type='program_drawn',
               source='art-source/diagrams.py', sourceSha256=sha256(Path(__file__)),
               semantics=semantics, usedBy=semantics['usedBy'],
               visualReview='Exact equal-scale grid from integer data; browser rendering pending.')
    write_json(LESSON / 'asset-sources.json', {
        'schemaVersion': 'mira.courseware.asset-sources.v1',
        'assets': records,
    })


if __name__ == '__main__':
    make_assets()
