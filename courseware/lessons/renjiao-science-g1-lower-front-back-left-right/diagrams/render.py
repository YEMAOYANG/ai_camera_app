"""Compose the two cameras, reference-person maps, and original picture questions."""

from functools import lru_cache
from hashlib import sha256
import json
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
PAPER = '#fff3dd'
INK = '#203e37'
MINT = '#d4e8d4'
STROKE = '#426754'
PLUM = '#773d60'
RUST = '#a3422e'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
DIRECTION = {'north': (0, -1), 'east': (1, 0), 'south': (0, 1), 'west': (-1, 0)}
ROTATION = {'north': 0, 'east': -90, 'south': 180, 'west': 90}
PROPS = {
    'purple-drum': (0, -1), 'blue-lantern': (1, 0),
    'orange-crate': (0, 1), 'green-flag': (-1, 0),
}
PEOPLE = ('green-top', 'star-top')
PAIRS = {'forward': 'north', 'turned': 'south', 'sideways': 'east'}
ROW_SIZE = (3, 4)


def relation(origin, target, face):
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    fx, fy = DIRECTION[face]
    return dx * fx + dy * fy, -dx * fy + dy * fx


def side_ground(world):
    x, y = world
    return 306 - 162 * y + 64 * x, 316 + 83 * x


def board(size=(610, 410)):
    im = Image.new('RGBA', size, PAPER)
    return im, ImageDraw.Draw(im)


@lru_cache
def font(size):
    return ImageFont.truetype(FONT, size)


def text(draw, value, point, size, color=INK):
    draw.text(point, str(value), font=font(size), anchor='mm', fill=color)


@lru_cache
def art(key):
    with Image.open(ASSETS / f'{key}.png') as original:
        im = original.convert('RGBA')
    bounds = im.getchannel('A').point(lambda a: 255 if a >= 16 else 0).getbbox()
    return im.crop(bounds)


@lru_cache
def sprite(key, box, angle, mirror):
    im = art(key).rotate(angle, expand=True)
    im.thumbnail(tuple(map(round, box)), Image.Resampling.LANCZOS)
    return ImageOps.mirror(im) if mirror else im


def stamp(im, key, point, box, angle=0, ground=False, mirror=False):
    item = sprite(key, box, angle, mirror)
    x, y = (round(v) for v in point)
    im.alpha_composite(item, (x - item.width // 2, y - (item.height if ground else item.height // 2)))


def panel(draw, box, fill=MINT, outline=STROKE, width=4):
    draw.rounded_rectangle(box, radius=17, fill=fill, outline=outline, width=width)


def arrow(draw, a, b, width=8, color=RUST):
    if a == b:
        return
    draw.line((*a, *b), fill=color, width=width)
    direction = atan2(b[1] - a[1], b[0] - a[0])
    head = max(14, 2.9 * width)
    edges = [(b[0] - head*cos(direction + d), b[1] - head*sin(direction + d))
             for d in (-.53, .53)]
    draw.polygon([b, *edges], fill=color)


def background(key, size=(416, 234)):
    return ImageOps.fit(art(key).convert('RGB'), size, Image.Resampling.LANCZOS).convert('RGBA')


def stage_mark(draw, extent=610):
    panel(draw, (extent//2-118, 12, extent//2+118, 58), '#d68d57', PLUM)
    draw.line((extent//2-89, 35, extent//2+89, 35), fill='#ffe3b2', width=7)


def footprint(draw, xy, size, fill=MINT):
    x, y = xy
    draw.ellipse((x-size, y-size, x+size, y+size), fill=fill, outline=STROKE, width=4)


def actor(im, draw, key, point, heading, radius=37, mat='#d6e8c7'):
    footprint(draw, point, radius, mat)
    stamp(im, key, point, (radius*1.34, radius*1.5), ROTATION[heading])
    x, y = point
    fx, fy = DIRECTION[heading]
    arrow(draw, (x+fx*(radius-4), y+fy*(radius-4)),
          (x+fx*(radius+29), y+fy*(radius+29)), width=7)


def map_image(objects, people=(), *, door=False, mats=(), stage=True, side_indicator=False, floor_arrows=()):
    im, draw = board()
    panel(draw, (14, 65 if stage else 14, 596, 396), '#f7e3b9', '#be956d')
    if stage:
        stage_mark(draw)
    if door:
        stamp(im, 'stage-door', (568, 223), (54, 90))
    if side_indicator:
        draw.arc((219, 153, 391, 329), 255, 80, fill=PLUM, width=7)
        arrow(draw, (376, 306), (337, 327), width=7, color=PLUM)
    def locate(p):
        return 305 + p[0]*150, 225 + p[1]*108
    for point, color in mats:
        footprint(draw, locate(point), 34, color)
    for point, heading in floor_arrows:
        x, y = locate(point)
        fx, fy = DIRECTION[heading]
        arrow(draw, (x, y), (x+fx*76, y+fy*76))
    for key, position in objects.items():
        stamp(im, key, locate(position), (78, 66))
    for key, position, heading in people:
        actor(im, draw, key, locate(position), heading, mat=dict(mats).get(position, MINT))
    return im


def top_photo(heading):
    return map_image(PROPS, [('green-top', (0, 0), heading)])


def side_photo(heading):
    im, draw = board()
    draw.polygon([(73, 213), (537, 213), (603, 400), (7, 400)], fill='#efcc9a', outline='#9b634b', width=5)
    for world in [*PROPS.values(), (0, 0)]:
        x, y = side_ground(world)
        draw.ellipse((x-40, y-10, x+40, y+10), fill='#a17a5b')
    # Same scene positions and same camera direction for all three portraits.
    fx, fy = DIRECTION[heading]
    x, y = side_ground((0, 0))
    end = side_ground((.62*fx, .62*fy))
    arrow(draw, (x, y+10), (end[0], end[1]+10), color=RUST, width=8)
    entries = [(key, pos) for key, pos in PROPS.items()]
    entries.append(('actor', (0, 0)))
    for key, pos in sorted(entries, key=lambda item: item[1][0]):
        p = side_ground(pos)
        if key == 'actor':
            image = 'green-front' if heading == 'east' else 'green-profile'
            stamp(im, image, p, (98, 174), ground=True, mirror=heading == 'south')
        else:
            stamp(im, key, p, (82, 78), ground=True)
    return im


def prop_card(key):
    im, draw = board((320, 235))
    panel(draw, (17, 14, 303, 221), '#f5e0b9')
    stamp(im, key, (160, 118), (178, 169))
    return im


def station(heading, who):
    im, draw = board((168, 168))
    panel(draw, (3, 3, 164, 164), MINT, width=8)
    dx, dy = DIRECTION[heading]
    actor(im, draw, who, (84-dx*13, 84-dy*13), heading, 43)
    return im


def shelf():
    im, draw = board()
    stamp(im, 'shelf-front', (309, 213), (496, 375))
    stamp(im, 'purple-drum', (310, 163), (103, 75))
    stamp(im, 'orange-crate', (310, 286), (97, 79))
    return im


def entrance():
    im = background('theatre-entry', (700, 440))
    stamp(im, 'green-profile', (304, 358), (123, 240), ground=True)
    stamp(im, 'purple-drum', (451, 369), (123, 115), ground=True)
    return im


def table_distance(teaching=False):
    im, draw = board()
    panel(draw, (18, 24, 592, 390), '#f3e0b8')
    stamp(im, 'oak-table', (295, 209), (239, 139))
    close, far = ('triangle-shaker','green-flag') if teaching else ('bear-toy','paper-plane')
    stamp(im, close, (295, 112), (66, 73))
    stamp(im, 'striped-ball', (500, 216), (75, 72))
    stamp(im, far, (104, 329), (86, 68))
    return im


def seating(selected):
    im, draw = board((520, 382))
    stage_mark(draw, 520)
    for r in range(1, ROW_SIZE[0]+1):
        y = 111 + (r-1)*101
        text(draw, r, (57, y), 48, PLUM)
        draw.line((95, y+43, 491, y+43), fill='#c6a97c', width=3)
        for c in range(1, ROW_SIZE[1]+1):
            x = 147 + (c-1)*99
            if (r, c) == selected:
                panel(draw, (x-43, y-43, x+43, y+44), '#f6c978', RUST, 7)
            stamp(im, 'seat-top', (x, y), (64, 67), 180)
            text(draw, c, (x, y-2), 37, 'white')
    return im


def ticket(row, seat):
    im, draw = board((380, 255))
    stamp(im, 'blank-ticket', (190, 128), (362, 215))
    text(draw, f'{row}排  {seat}座', (190, 128), 60)
    return im


def paired(top, side):
    im, draw = board((840, 365))
    for index, photo in enumerate((top, side)):
        part = photo.copy()
        part.thumbnail((390, 279), Image.Resampling.LANCZOS)
        x = 12+index*423
        panel(draw, (x, 62, x+390, 344), '#f8dfa8', PLUM)
        im.alpha_composite(part, (x+(390-part.width)//2, 72))
        stamp(im, 'camera-badge', (x+195, 30), (49, 49))
    return im


def visuals():
    top_parents = [*PROPS, 'green-top']
    side_parents = [*PROPS, 'green-profile', 'green-front']
    yield 'entrance', entrance(), 'where-to-put-it', ['theatre-entry','green-profile','purple-drum']
    yield 'shelf-model', shelf(), 'where-to-put-it', ['shelf-front', 'purple-drum', 'orange-crate']
    yield 'delivery-background', background('theatre-floor'), 'costume-delivery', ['theatre-floor']
    yield 'camera-background', background('photo-bench'), 'camera-compare', ['photo-bench']
    for pose, heading in PAIRS.items():
        yield 'stage-top-'+pose, top_photo(heading), ['stand-then-face', 'camera-compare'], top_parents
        yield 'stage-side-'+pose, side_photo(heading), 'camera-compare', side_parents
    yield 'camera-cover', paired(top_photo('north'), side_photo('north')), 'camera-compare', [*top_parents, *side_parents, 'camera-badge']
    yield 'star-reference', map_image(
        {'purple-drum': (0, -1), 'triangle-shaker': (1, 1), 'blue-lantern': (1.65, -1)},
        [('green-top', (-1, .1), 'north'), ('star-top', (1, .1), 'west')], door=True
    ), 'another-person', [*PEOPLE, 'purple-drum', 'triangle-shaker', 'blue-lantern', 'stage-door']
    for key, x in [('red-spot', -1.12), ('blue-spot', 1.12)]:
        yield key, map_image({'oak-table': (0, 0)}, [('green-top', (x, 0), 'north')], mats=[((-1.12,0),'#ec9e82'),((1.12,0),'#9dd4dc')]), 'two-places', ['oak-table', 'green-top']
    for who in ('green', 'star'):
        for heading in DIRECTION:
            yield f'{who}-ref-{heading}', station(heading, who+'-top'), 'costume-delivery', [who+'-top']
    yield 'teach-near', table_distance(teaching=True), 'near-and-far', ['oak-table','triangle-shaker','striped-ball','green-flag']
    yield 'sample-ticket', ticket(1, 2), 'ticket-row', ['blank-ticket']
    yield 'sample-seat', seating((1, 2)), 'ticket-row', ['seat-top']
    yield 'q1-stimulus', map_image({'purple-drum': (0,-1), 'blue-lantern': (0,1), 'orange-crate':(-1,0)}, [('green-top',(0,0),'east')], door=True), 'picture-check', ['purple-drum','blue-lantern','orange-crate','green-top','stage-door']
    yield 'q2-stimulus', map_image({'purple-drum': (0,-1)}, [('green-top',(0,0),'north')], side_indicator=True), 'picture-check', ['purple-drum', 'green-top']
    yield 'q3-stimulus', map_image(
        {'orange-crate': (0,-1),'triangle-shaker': (0,1),'paper-plane':(1.24,0)},
        [('green-top',(-1.2,-.42),'north'),('star-top',(0,0),'west')]
    ), 'picture-check', [*PEOPLE,'orange-crate','triangle-shaker','paper-plane']
    yield 'q5-stimulus', table_distance(), 'picture-check', ['oak-table','bear-toy','striped-ball','paper-plane']
    yield 'q6-stimulus', ticket(2, 3), 'picture-check', ['blank-ticket']
    for letter, key in zip('abc', ['purple-drum','blue-lantern','orange-crate']):
        yield 'q1-'+letter, prop_card(key), 'picture-check', [key]
    for letter, pos in zip('abc', [(0,1),(1,0),(0,-1)]):
        yield 'q2-'+letter, map_image({'purple-drum':pos}, [('green-top',(0,0),'south')]), 'picture-check', ['purple-drum','green-top']
    for letter, key in zip('abc', ['triangle-shaker','orange-crate','paper-plane']):
        yield 'q3-'+letter, prop_card(key), 'picture-check', [key]
    for letter, mat, heading in [('a',True,False),('b',True,True),('c',False,True)]:
        yield 'q4-'+letter, map_image({}, door=True, mats=[((0,0),MINT)] if mat else [], stage=False, floor_arrows=[((0,0),'east')] if heading else []), 'picture-check', ['stage-door']
    for letter, key in zip('abc', ['bear-toy','striped-ball','paper-plane']):
        yield 'q5-'+letter, prop_card(key), 'picture-check', [key]
    for letter, pos in zip('abc', [(1,3),(3,2),(2,3)]):
        yield 'q6-'+letter, seating(pos), 'picture-check', ['seat-top']
    yield 'family-model', map_image(PROPS, [('green-top',(0,0),'south')], stage=False), 'try-it-together', [*PROPS,'green-top']


def render():
    def digest(p):
        return sha256(p.read_bytes()).hexdigest()
    sources = {}
    for receipt in sorted((ROOT/'art-source').glob('*.receipt.json')):
        for row in json.loads(receipt.read_text())['assets']:
            sources[row['assetKey']] = {**row, 'file': row['path'], 'kind': 'codex-builtin-imagegen'}
    for key, im, uses, parents in visuals():
        p = ASSETS / f'{key}.png'
        im.save(p, optimize=True)
        sources[key] = {
            'file': p.relative_to(ROOT).as_posix(), 'sha256': digest(p),
            'kind': 'deterministic-lesson-diagram', 'usedBy': [uses] if isinstance(uses, str) else uses,
            'source': 'diagrams/render.py', 'sourceSha256': digest(Path(__file__)),
            'sourceAssets': {a: sources[a]['sha256'] for a in parents},
        }
    doc = {'schemaVersion': 'mira.courseware.asset-sources.v1', 'assets': sources}
    (ROOT/'asset-sources.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    render()
