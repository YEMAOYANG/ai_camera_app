"""Render this exhibition lesson's exact quantities and record image provenance."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

LESSON = Path(__file__).resolve().parent.parent
ASSETS = LESSON / 'assets'
PAPER = '#fff6e4'
INK = '#183a31'
GREEN = '#286956'
ORANGE = '#a74524'
MINT = '#c2e6d6'
PEACH = '#f5ceaa'
GRAY = '#777469'


def board(size=(720, 385), color=PAPER):
    image = Image.new('RGBA', size, color)
    return image, ImageDraw.Draw(image)


@lru_cache
def font(size, chinese=False):
    name = 'Hiragino Sans GB.ttc' if chinese else 'SFNS.ttf'
    return ImageFont.truetype('/System/Library/Fonts/' + name, size)


def word(draw, value, x, y, size, fill=INK, *, chinese=False):
    draw.text((x, y), str(value), font=font(size, chinese), fill=fill, anchor='mm',
              stroke_width=1, stroke_fill=fill)


@lru_cache
def tile_sprite(key, edge):
    with Image.open(ASSETS / f'{key}.png') as source:
        sprite = source.convert('RGBA')
    bounds = sprite.getchannel('A').point(lambda v: 255 if v >= 24 else 0).getbbox()
    sprite = sprite.crop(bounds)
    sprite.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return sprite


def tile(image, key, xy, edge):
    sprite = tile_sprite(key, edge)
    x, y = xy
    image.alpha_composite(sprite, (x - sprite.width // 2, y - sprite.height // 2))


def matrix(count, x, y, pitch, columns=5):
    return [(x + (index % columns) * pitch, y + (index // columns) * pitch)
            for index in range(count)]


def split_positions(tens, ones):
    """A tray always holds precisely two rows of five; loose objects sit apart."""
    if tens == 2:
        return [matrix(10, x, 139, 58) for x in (48, 431)], matrix(ones, 362, 301, 55)
    return [matrix(10, 67, 137, 64)] if tens else [], matrix(ones, 437, 137, 51)


def tray(draw, points, pad=32):
    draw.rounded_rectangle((points[0][0] - pad, points[0][1] - pad,
                            points[-1][0] + pad, points[-1][1] + pad),
                           radius=17, fill=MINT, outline=GREEN, width=5)


def groups(tens, ones, key='blank-label', *, emphasized=0):
    image, draw = board()
    trays, singles = split_positions(tens, ones)
    for positions in trays:
        tray(draw, positions)
        for point in positions:
            tile(image, key, point, 45)
    for x, y in singles[-emphasized:] if emphasized else []:
        draw.ellipse((x-24, y-24, x+24, y+24), fill='#ffca74', outline=ORANGE, width=3)
    for point in singles:
        tile(image, key, point, 40)
    return image


# Spaced irregular layout for the same 16 cards before they are sorted.
SCATTER = ((105,85),(212,71),(370,99),(513,73),(609,111),(153,172),(266,155),(420,161),
           (560,187),(99,259),(190,280),(319,238),(453,250),(592,266),(356,321),(502,331))


def scattered():
    image, _ = board()
    for point in SCATTER:
        tile(image, 'blank-label', point, 61)
    return image


def rails(tens, ones, *, compact=False):
    image, draw = board((160,160) if compact else (720,385), PAPER)
    if compact:
        columns = (46, 113)
        top, base, pitch, half, height = 13, 134, 13, 25, 11
    else:
        columns = (200, 518)
        top, base, pitch, half, height = 37, 312, 29, 104, 23
    for x, count, color in zip(columns, (tens, ones), (GREEN, ORANGE)):
        draw.line((x, top, x, base), fill=INK, width=4 if compact else 11)
        for index in range(count):
            y = base - height - pitch * index - (4 if compact else 10)
            draw.rounded_rectangle((x-half, y-height//2, x+half, y+height//2),
                                   radius=height//2, fill=color)
    draw.rounded_rectangle((columns[0]-half-8, base, columns[1]+half+8, base+(8 if compact else 16)),
                           radius=6, fill=INK)
    if not compact:
        for x, label in zip(columns, ('十', '个')):
            word(draw, label, x, 354, 39, chinese=True)
    return image


def compact_groups(tens, ones):
    image, draw = board((160,160))
    for index in range(tens):
        x = 4 + index * 78
        draw.rounded_rectangle((x,6,x+74,153),radius=10,fill=MINT,outline=GREEN,width=5)
        for point in matrix(10, x+22, 24, 28, 2):
            tile(image, 'blank-label', point, 23)
    for point in matrix(ones, 92, 45, 27, 3):
        tile(image, 'blank-label', point, 24)
    return image


def seed_tray(grouped):
    image, draw = board((300, 220))
    inside = [(32 + (i % 5)*30, 43 + (i // 5)*38) for i in range(grouped)]
    outside = [(204 + (i % 3)*33, 43 + (i // 3)*38) for i in range(17-grouped)]
    if grouped > 10:
        inside[-1] = (32, 119)
    draw.rounded_rectangle((12,19,169,inside[-1][1]+21),radius=16,fill=MINT,outline=GREEN,width=5)
    for point in inside + outside:
        tile(image, 'blank-label', point, 28)
    return image


def loose_pieces(count, key):
    image, draw = board((300,220))
    draw.rounded_rectangle((13,22,287,198),radius=22,fill=MINT,outline=GREEN,width=5)
    rows = (count+2)//3
    for i in range(rows):
        per_row = min(3, count-i*3)
        for x, y in matrix(per_row, 150-(per_row-1)*40, 110-(rows-1)*40+i*80, 80, 3):
            tile(image, key, (x, y), 63)
    return image


def number_card(value, *, compact=False):
    size = 160 if compact else 240
    image, draw = board((size,size), PAPER)
    draw.rounded_rectangle((8,8,size-9,size-9),radius=22,fill=MINT,outline=GREEN,width=5)
    word(draw, value, size//2, size//2, round(size*.54))
    return image


def formula_card(left, sign, right):
    image, draw = board((160,160))
    draw.rounded_rectangle((3,3,156,156),radius=16,fill=PAPER,outline=GREEN,width=6)
    word(draw, left, 80, 42, 60)
    word(draw, f'{sign}{right}', 80, 116, 60)
    return image


def strip(start, end, *, flags=(), highlighted=(), show=(), arrows=(),
          marker='flag', size=(720,385)):
    image, draw = board(size)
    width, height = size
    y = int(height*.53)
    xs = {n: round(width*.09+(n-start)*width*.82/(end-start)) for n in range(start,end+1)}
    first, last = xs[start], xs[end]
    draw.line((first,y,last,y),fill=GRAY,width=5)
    radius = max(11,min(21,int(width*.028)))
    for n, x in xs.items():
        fill = GREEN if n in highlighted else ORANGE if n in flags else PAPER
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill,outline=INK,width=4)
        if n in flags:
            yy = y - int(height*.27)
            if marker == 'flag':
                tile(image,'exhibit-flag',(x,yy),int(height*.31))
            else:
                bulb = int(height*.088)
                draw.line((x,yy+bulb,x,y-radius), fill=ORANGE, width=4)
                draw.ellipse((x-bulb,yy-bulb,x+bulb,yy+bulb),fill='#ffc64a',outline=ORANGE,width=4)
                draw.ellipse((x-6,yy-10,x+6,yy+2),fill='#fff8e2')
        if n in show:
            word(draw,n,x,y+int(height*.23),int(width*.06))
    for index, direction in enumerate(arrows):
        yy = int(height*.24) + index * int(height*.15)
        a,b = (first,last) if direction==1 else (last,first)
        draw.line((a,yy,b,yy),fill=GREEN,width=6)
        draw.polygon([(b,yy),(b-direction*19,yy-11),(b-direction*19,yy+11)],fill=GREEN)
    return image


def endpoints(start, end):
    image, draw = board()
    for x, value in ((120,start),(600,end)):
        tile(image,'exhibit-flag',(x,134),146)
        word(draw,value,x,290,83)
    draw.line((213,206,507,206),fill=GREEN,width=6)
    for x in matrix(end-start-1, 241, 206, 60):
        draw.ellipse((x[0]-9,x[1]-9,x[0]+9,x[1]+9),fill=PAPER,outline=GRAY,width=4)
    return image


def equations(lines):
    image, draw = board()
    for i, value in enumerate(lines):
        y = round((i+.5)*385/len(lines))
        draw.rounded_rectangle((58,y-53,662,y+53),radius=22,fill=MINT,outline=GREEN,width=4)
        word(draw,value,360,y,72,chinese=True)
    return image


def opening_clues():
    image, draw = board((660,380))
    for x in (10,230,450):
        draw.rounded_rectangle((x,30,x+200,340),radius=18,fill='#fff9ec',outline=GREEN,width=4)
    small = compact_groups(1,6)
    image.alpha_composite(small, (30,98))
    tile(image,'blank-label',(330,184),156)
    word(draw,'16',330,180,66)
    tile(image,'exhibit-flag',(550,147),139)
    word(draw,'16',550,270,66)
    return image


def map_icons():
    image, draw = board((600,380))
    slots = [(92,148),(300,148),(508,148)]
    for first, second in zip(slots, slots[1:]):
        x = second[0]-77
        draw.line((first[0]+72,148,x,148),fill=GREEN,width=8)
        draw.polygon([(x+12,148),(x-12,133),(x-12,163)],fill=GREEN)
    for key, point in zip(('blank-label','wood-badge','exhibit-flag'),slots):
        tile(image,key,point,112)
    for mark, (x,_) in zip(('16','＋2','18'),slots):
        word(draw,mark,x,257,66,chinese=True)
    return image


def background(key):
    with Image.open(ASSETS / f'{key}.png') as source:
        image = source.convert('RGBA')
    # The painterly crops are 4:3. Frame the quiet center for the 16:9 game
    # surface; stretching here would distort the door, shelving and plinths.
    width, height = image.size
    image = image.crop((8,8,width-8,height-8))
    return ImageOps.fit(image.convert('RGB'), (400,225), Image.Resampling.LANCZOS)


def art():
    yield 'depot-room', background('depot-backdrop'), ['depot'], ['depot-backdrop']
    yield 'route-room', background('route-backdrop'), ['route-by-result'], ['route-backdrop']
    yield 'open-clues', opening_clues(), ['open-map'], ['blank-label', 'exhibit-flag']
    yield 'scattered-16', scattered(), ['estimate-bundle'], ['blank-label']
    yield 'groups-16', groups(1,6), ['estimate-bundle'], ['blank-label']
    yield 'beads-16', rails(1,6), ['place-value'], []
    yield 'beads-20', rails(2,0), ['place-value'], []
    yield 'neighbors-line', strip(11,20,show=range(11,21),arrows=(1,-1)), ['neighbors'], []
    yield 'compose-16', equations(('10＋6＝16','16－6＝10','16－10＝6')), ['calculate-from-groups'], []
    yield 'add-two-cards', groups(1,8,emphasized=2), ['calculate-from-groups'], ['blank-label']
    yield 'flags-11-17', endpoints(11,17), ['between-stops'], ['exhibit-flag']
    yield 'interior-five', strip(11,17,flags=(11,17),highlighted=range(12,17),show=range(11,18)), ['between-stops'], ['exhibit-flag']
    yield 'same-15', equations(('11＋4＝15','18－3＝15')), ['equal-result'], []
    yield 'fill-15', equations(('11＋□＝15','15－11＝4')), ['equal-result'], []
    yield 'finish-diagram', map_icons(), ['finish-map'], ['blank-label', 'wood-badge', 'exhibit-flag']

    for value in (14,15):
        yield f'depot-number-{value}', number_card(value,compact=True), ['depot'], []
    for value in (10,11,12,13,15,19,20):
        yield f'depot-beads-{value}', rails(value//10,value%10,compact=True), ['depot'], []
    for value in (10,11,12,13,14,15,19,20):
        yield f'depot-cards-{value}', compact_groups(value//10,value%10), ['depot'], ['blank-label']

    for key, left, sign, right in (
            ('a',13,'−',2),('b',10,'+',2),('c',16,'−',3),('d',14,'−',2),('e',10,'+',3),
            ('f',16,'−',2),('g',17,'−',2),('h',10,'+',6),('i',19,'−',2),('j',16,'+',2),
            ('k',15,'+',4),('m',10,'+',10)):
        yield f'route-{key}', formula_card(left,sign,right), ['route-by-result'], []

    for suffix, value in zip('abc',(10,9,11)):
        yield f'q1-{suffix}', seed_tray(value), ['picture-check.q1'], ['blank-label']
    for suffix, (tens, ones) in zip('abc',((1,7),(2,0),(1,8))):
        yield f'q2-{suffix}', rails(tens,ones), ['picture-check.q2'], []
    for suffix, value in zip('abc',(16,17,19)):
        yield f'q3-{suffix}', number_card(value), ['picture-check.q3'], []
    yield 'q3-stimulus', strip(17,19,show=(18,19),arrows=(-1,)), ['picture-check.q3'], []
    for suffix, value in zip('abc',(4,3,2)):
        yield f'q4-{suffix}', groups(1,value,'paper-button'), ['picture-check.q4'], ['paper-button']
    yield 'q4-stimulus', groups(1,5,'paper-button'), ['picture-check.q4'], ['paper-button']
    for suffix, value in zip('abc',(5,4,6)):
        yield f'q5-{suffix}', loose_pieces(value,'wood-badge'), ['picture-check.q5'], ['wood-badge']
    yield 'q5-stimulus', groups(1,2,'wood-badge'), ['picture-check.q5'], ['wood-badge']
    for suffix, values in zip('abc',(range(8,11),range(7,12),range(7,11))):
        yield f'q6-{suffix}', strip(6,11,flags=(6,11),highlighted=values,marker='light',size=(420,270)), ['picture-check.q6'], []
    yield 'q6-stimulus', strip(6,11,flags=(6,11),show=(6,11),marker='light'), ['picture-check.q6'], []


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def render():
    receipt = json.loads((LESSON/'art-source'/'museum-atlas.receipt.json').read_text())
    sources = {row['assetKey']: {**row, 'file':row['path'], 'kind':'codex-builtin-imagegen'}
               for row in receipt['assets']}
    for key, picture, uses, parents in art():
        path = ASSETS / f'{key}.png'
        picture.save(path, optimize=True)
        sources[key] = {
            'file': path.relative_to(LESSON).as_posix(), 'sha256': digest(path),
            'kind': 'deterministic-lesson-diagram', 'usedBy': uses,
            'source': 'diagrams/render.py', 'sourceSha256': digest(Path(__file__)),
            'sourceAssets': {p: sources[p]['sha256'] for p in parents},
        }
    manifest = {'schemaVersion':'mira.courseware.asset-sources.v1','assets':sources}
    (LESSON/'asset-sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    render()
