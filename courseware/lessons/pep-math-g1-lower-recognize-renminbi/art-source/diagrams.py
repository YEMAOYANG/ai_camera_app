"""Draw original classroom money cards from exact denominations and group counts."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
LESSON = ROOT.parent
PAPER = '#fff5df'
INK = '#244f40'
FRAME = '#d7bb91'
COIN = '#efe0b6'
NOTE = '#dce9cf'
UNIT = {'y': '元', 'j': '角', 'f': '分'}
TO_FEN = {'y': 100, 'j': 10, 'f': 1}
VALUES = {'y': (1, 5, 10, 20, 50, 100), 'j': (1, 5), 'f': (1, 2, 5)}
FONT = Path('/System/Library/Fonts/Hiragino Sans GB.ttc')


@lru_cache(maxsize=50)
def font(size):
    return ImageFont.truetype(str(FONT), size, index=1)


def label(draw, point, text, size, color=INK):
    draw.text(point, str(text), fill=color, font=font(size), anchor='mm')


def parse(token):
    style, unit = token[:2]
    number = int(token[2:])
    if style not in 'nc' or number not in VALUES[unit] or (style == 'n' and unit == 'f'):
        raise ValueError(f'Invalid classroom denomination {token}')
    if style == 'c' and unit == 'y' and number != 1:
        raise ValueError(f'Invalid textbook yuan coin {token}')
    return style, unit, number


def classroom_money(draw, box, token, *, word=False):
    x, y, w, h = box
    style, unit, number = parse(token)
    thick = max(2, round(min(w, h) * .028))
    if style == 'c':
        radius = min(w, h) * .47
        cx, cy = x + w / 2, y + h / 2
        bounds = (cx - radius, cy - radius, cx + radius, cy + radius)
        draw.ellipse(bounds, fill=COIN, outline='#7f724b', width=thick)
        inset = radius * .15
        draw.ellipse((bounds[0] + inset, bounds[1] + inset, bounds[2] - inset, bounds[3] - inset),
                     outline='#a28e65', width=thick)
        label(draw, (cx, cy - .05 * radius), f'{number}{UNIT[unit]}', max(8, round(radius * .78)))
        return
    hh = min(h * .76, w * .54)
    yy = y + (h - hh) / 2
    draw.rounded_rectangle((x + 2, yy, x + w - 2, yy + hh), radius=hh * .13,
                           fill=NOTE, outline='#63806b', width=thick)
    draw.rounded_rectangle((x + .11 * w, yy + .13 * hh, x + .89 * w, yy + .87 * hh),
                           radius=hh * .1, outline='#92a980', width=thick)
    label(draw, (x + w / 2, yy + .42 * hh), f'{number}{UNIT[unit]}',
          max(8, round(min(hh * .53, w / (len(str(number)) + 1) * .75))))
    if word:
        label(draw, (x + w / 2, yy + .78 * hh), '伍圆' if number == 5 and unit == 'y' else '教具',
              max(8, round(hh * .24)))


def unit_totals(groups):
    totals = {}
    for group in groups:
        for token in group:
            _, unit, number = parse(token)
            totals[unit] = totals.get(unit, 0) + number
    return totals


def total_fen(groups):
    return sum(TO_FEN[unit] * number for unit, number in unit_totals(groups).items())


def grid(draw, box, tokens, *, columns, word=False):
    x, y, width, height = box
    rows = (len(tokens) + columns - 1) // columns
    h = height / rows
    w = min(width / columns, h * 1.46)
    for index, token in enumerate(tokens):
        row, column = divmod(index, columns)
        remaining = min(columns, len(tokens) - row * columns)
        start = x + (width - remaining * w) / 2
        classroom_money(draw, (start + column * w + w * .025, y + row * h,
                              w * .95, h), token, word=word)


def money_card(groups, *, mode='standard', summaries=False, words=False):
    size = (760, 370) if mode == 'lecture' else (540, 318)
    im = Image.new('RGB', size, PAPER)
    w, h = im.size
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((4, 4, w - 5, h - 5), radius=24, outline=FRAME, width=4)
    inner = (w - 30) / len(groups)
    for index, group in enumerate(groups):
        x = 15 + inner * index
        if len(groups) > 1:
            draw.rounded_rectangle((x + 4, 22, x + inner - 4, h - 22), radius=18,
                                   fill='#f9ecd1', outline=FRAME, width=3)
        if len(group) == 10:
            columns = 5
        elif len(group) > 2:
            columns = 3
        else:
            columns = len(group)
        y, height = 28, h - (100 if summaries else 56)
        grid(draw, (x + 12, y, inner - 24, height), group, columns=columns, word=words)
        if summaries:
            totals = unit_totals([group])
            text = ' '.join(f'{totals[u]}{UNIT[u]}' for u in UNIT if u in totals)
            label(draw, (x + inner / 2, h - 39), text, 45)
    return im


def token_sprite(token):
    image = Image.new('RGBA', (250, 250))
    classroom_money(ImageDraw.Draw(image), (8, 9, 234, 232), token)
    return image


def asset_specs():
    repeated = lambda token, n: [token] * n
    teaching = [
        ('same-one-yuan', [['ny1'], ['cy1']], 'notes-and-coins', True, False),
        ('yuan-paper-range', [['ny100', 'ny50', 'ny20', 'ny10', 'ny5', 'ny1']], 'read-number-and-unit', False, True),
        ('coin-range', [['cy1', 'cj5', 'cj1', 'cf5', 'cf2', 'cf1']], 'read-number-and-unit', False, False),
        ('unmixed-start', [['ny20', 'cj1', 'ny5', 'cj1']], 'count-in-separate-trays', False, False),
        ('yuan-jiao-boxes', [['ny20', 'ny5'], ['cj1', 'cj1']], 'count-in-separate-trays', True, False),
        ('left-fifteen', [['ny10', 'ny5']], 'equal-amount-different-groups', True, False),
        ('right-fifteen', [['ny5', 'ny5', 'ny5']], 'equal-amount-different-groups', True, False),
        ('one-yuan', [['cy1']], 'exchange-yuan-and-jiao', False, False),
        ('ten-jiao', [repeated('cj1', 10)], 'exchange-yuan-and-jiao', True, False),
        ('ten-fen', [['cj1'], repeated('cf1', 10)], 'exchange-jiao-and-fen', True, False),
        ('five-and-five-fen', [['cf5'] + repeated('cf1', 5)], 'exchange-jiao-and-fen', True, False),
        ('family-recap', [['cy1'], repeated('cj1', 10), ['cf5', 'cf5']], 'exchange-with-family', False, False),
    ]
    for key, groups, where, summaries, words in teaching:
        yield key, money_card(groups, mode='lecture', summaries=summaries, words=words), {
            'kind': 'classroom denomination diagram', 'groups': groups, 'usedBy': [where],
            'groupFen': [total_fen([g]) for g in groups], 'summaries': summaries,
        }
    for token in ('ny1', 'cy1', 'cj1', 'ny5', 'cj5', 'cf5', 'nj1', 'cf2', 'ny20', 'ny10'):
        yield f'sort-{token}', token_sprite(token), {
            'kind': 'single classroom denomination', 'tokens': [token],
            'unit': parse(token)[1], 'usedBy': ['sort-the-change'],
        }

    orders = {
        'order-7-yuan': [['ny5', 'cy1', 'cy1']],
        'order-13-yuan': [['ny10', 'cy1', 'cy1', 'cy1']],
        'order-one-yuan': [['cy1']],
        'order-one-jiao': [['cj1']],
        'order-twenty-jiao': [repeated('cj1', 10), repeated('cj1', 10)],
        'order-thirty-fen': [repeated('cf1', 10), repeated('cf1', 10), repeated('cf1', 10)],
    }
    # The first two game orders announce a total rather than showing the equivalent
    # target bundle. Their exact amount and unit remain visible on a number card.
    for key, groups in orders.items():
        if key in {'order-7-yuan', 'order-13-yuan'}:
            image = Image.new('RGB', (540, 318), PAPER)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((4, 4, 535, 313), radius=24, outline=FRAME, width=4)
            label(draw, (270, 158), f"{total_fen(groups)//100}元", 145)
        else:
            image = money_card(groups, summaries=True)
        yield key, image, {'kind':'exchange order', 'groups':groups, 'valueFen':total_fen(groups),
                           'usedBy':['aim-for-the-same-value']}
    targets = {
        'target-7-yuan': [['ny5', 'cy1', 'cy1']],
        'target-13-yuan': [['ny10', 'cy1', 'cy1', 'cy1']],
        'target-6-yuan': [['ny5', 'cy1']],
        'target-ten-jiao': [['cj5'] + repeated('cj1', 5)],
        'target-ten-fen': [['cf5', 'cf2', 'cf2', 'cf1']],
        'target-nine-jiao': [['cj5'] + repeated('cj1', 4)],
        'target-two-yuan': [repeated('cy1', 2)],
        'target-three-jiao': [repeated('cj1', 3)],
        'target-two-jiao': [repeated('cj1', 2)],
        'target-three-yuan': [repeated('cy1', 3)],
    }
    for key, groups in targets.items():
        yield key, money_card(groups), {'kind':'candidate exchange bundle', 'groups':groups,
                                       'valueFen':total_fen(groups), 'usedBy':['aim-for-the-same-value']}
    quiz = [
        ([['cj5', 'cy1', 'cf2']], [[['cj5']], [['cy1']], [['cf2']]], False),
        ([['ny10', 'cy1', 'cj5', 'cj1']], [
            [['ny10','cy1'],['cj5']],
            [['ny10','ny5','cy1'],['cj1']],
            [['ny10','cy1'],['cj5','cj1']],
        ], True),
        ([['cj5','cf2','cf1']], [
            [['cj5'],['cf2','cf1']],
            [repeated('cj1', 3),['cf5']],
            [['cf5','cf2','cf1']],
        ], True),
        ([['ny50']], [[['ny20','ny20','ny5']],[['ny20','ny20','ny10']],[['ny20','ny20','ny20']]], False),
        ([repeated('cy1', 2)], [
            [repeated('cj1', 2)],[repeated('cj1', 10)],[repeated('cj1', 10),repeated('cj1', 10)],
        ], False),
        ([repeated('cj1', 2)], [[repeated('cf5', 4)],[repeated('cf5', 2)],[repeated('cf1', 4)]], False),
    ]
    for index, (prompt, options, summaries) in enumerate(quiz, 1):
        where = f'rmb-q{index}'
        yield where+'-prompt', money_card(prompt, mode='lecture'), {
            'kind':'given classroom money', 'groups':prompt, 'valueFen':total_fen(prompt), 'usedBy':[where],
        }
        for letter, groups in zip('abc', options):
            yield f'{where}-{letter}', money_card(groups, summaries=summaries), {
                'kind':'candidate picture answer', 'groups':groups, 'valueFen':total_fen(groups),
                'unitTotals':unit_totals(groups), 'usedBy':[where],
            }


def make_assets():
    records = {}
    def save(key, image, fields):
        name = f'assets/{key}.png'
        dest = LESSON / name
        image.save(dest, format='PNG', optimize=True)
        records[key] = {'file':name, 'sha256':sha256(dest.read_bytes()).hexdigest(),
                        'bytes':dest.stat().st_size, 'pixels':list(image.size), **fields}

    def imagegen(source, key, image, box, uses, asset_type):
        save(key, image, {'type':asset_type, 'sourceAtlas':str(source.relative_to(LESSON)),
                          'sourceAtlasSha256':sha256(source.read_bytes()).hexdigest(),
                          'sourceCropPx':list(box), 'usedBy':uses,
                          'visualReview':'Owner inspected original and production crop; browser rendering pending.'})

    source = ROOT / 'reading-fair-atlas.png'
    with Image.open(source) as atlas:
        for key, box, use in [
            ('reading-fair-cover',(16,15,508,515),'notes-and-coins'),
            ('reading-fair-table',(526,15,1010,515),'sort-the-change'),
            ('reading-fair-booth',(1028,15,1520,515),'aim-for-the-same-value'),
        ]:
            crop = atlas.crop(box).convert('RGBA')
            base = Image.new('RGBA', crop.size, PAPER)
            base.alpha_composite(crop)
            result = ImageOps.fit(base.convert('RGB'), (500, 500) if key.endswith('cover') else (480, 270))
            imagegen(source, key, result, box, [use], 'imagegen_plate_crop')
    source = ROOT / 'reading-fair-sprites.png'
    with Image.open(source) as atlas:
        for key, box, uses in [
            ('book-cart',(37,70,554,650),['sort-the-change']),
            ('book-cart-moving',(576,70,1152,653),['sort-the-change']),
            ('book-badge',(1218,104,1704,645),['sort-the-change','aim-for-the-same-value']),
            ('glass-marble',(1770,190,2107,535),['aim-for-the-same-value']),
        ]:
            crop = atlas.crop(box).convert('RGBA')
            alpha = crop.getchannel('A')
            assert alpha.getextrema() == (0, 255)
            crop = crop.crop(alpha.point(lambda a: 255 if a >= 16 else 0).getbbox())
            crop.thumbnail((188, 188), Image.Resampling.LANCZOS)
            imagegen(source, key, crop, box, uses, 'imagegen_sprite_crop')

    for key, picture, semantics in asset_specs():
        save(key,picture,{'type':'program_drawn','source':'art-source/diagrams.py',
            'sourceSha256':sha256(Path(__file__).read_bytes()).hexdigest(),'semantics':semantics,
            'usedBy':semantics['usedBy'],'visualReview':'Exact denomination, unit, shape and count specified; browser rendering pending.'})
    (LESSON / 'asset-sources.json').write_text(json.dumps(
        {'schemaVersion':'mira.courseware.asset-sources.v1','assets':records},
        ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    make_assets()
