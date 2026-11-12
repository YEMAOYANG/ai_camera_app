"""Render the lesson's exact letter placement and stroke progression diagrams."""

import argparse
from functools import lru_cache
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ASSETS = Path(__file__).resolve().parents[1] / 'assets'
FONT = '/System/Library/Fonts/Supplemental/Songti.ttc'
CREAM, PAPER, GREEN, ORANGE, LINE = '#fbefcf', '#fff9e8', '#244f46', '#bc542d', '#cda76b'
PALE = '#e3cf9e'
MODEL = {
    'ox': ('牛', 'niú', [[(36,21),(33,29),(25,43)],[(31,36),(75,36)],
                       [(20,56),(84,56)],[(53,16),(53,86)]]),
    'sheep': ('羊', 'yáng', [[(35,16),(40,26)],[(64,15),(58,26)],
                           [(25,34),(75,34)],[(29,49),(71,49)],
                           [(18,64),(82,64)],[(50,35),(50,85)]]),
    'fruit': ('果', 'guǒ', [[(26,21),(26,53)],[(26,21),(73,21),(73,53)],
                           [(28,37),(71,37)],[(27,52),(73,52)],[(18,61),(83,61)],
                           [(50,20),(50,89)],[(48,62),(36,76),(18,85)],
                           [(52,62),(67,77),(84,84)]]),
    'white': ('白', 'bái', [[(46,13),(39,26)],[(27,27),(31,82)],[(27,27),(73,27),(68,82)],
                           [(29,52),(70,52)],[(31,80),(68,80)]]),
    'moon': ('月', 'yuè', [[(32,19),(32,45),(30,66),(22,84)],
                          [(32,20),(76,20),(76,79),(73,85),(66,81)],
                          [(34,42),(74,42)],[(33,60),(74,60)]]),
    'wind': ('风', 'fēng', [[(31,19),(30,43),(27,65),(18,83)],
                           [(31,20),(69,20),(70,43),(73,63),(79,77),(86,84),(89,76)],
                           [(61,37),(57,48),(49,59),(37,68)],[(41,40),(54,53),(66,66)]]),
    'small': ('小', 'xiǎo', [[(52,17),(52,77),(49,84),(42,80)],
                            [(34,42),(29,53),(21,66)],[(68,43),(79,55),(84,65)]]),
    'water': ('水', 'shuǐ', [[(51,16),(51,78),(48,86),(41,82)],
                            [(18,42),(41,42),(34,58),(26,70),(15,77)],
                            [(76,32),(70,40),(57,48)],[(54,46),(68,64),(86,77)]]),
    'mountain': ('山', 'shān', [[(51,20),(51,77)],[(25,37),(25,77),(77,77)],
                                [(77,35),(77,81)]]),
    'use': ('用', 'yòng', [[(31,22),(31,48),(29,66),(21,84)],
                          [(31,23),(77,23),(77,80),(74,84),(68,80)],
                          [(32,44),(76,44)],[(31,63),(76,63)],[(53,24),(53,80)]]),
}
CHARACTERS = {'ox':'牛', 'sheep':'羊', 'claws':'爪', 'dawn':'旦', 'assemble':'拼',
              'bell':'音', 'fruit':'果', 'white':'白', 'flower':'花', 'leaf':'叶',
              'bright':'明', 'early':'早', 'mouth':'口', 'work':'作', 'only':'只'}
TITLES = {
    'look-at-shapes': ('牛', '羊', '爪', '旦', '拼', '音'),
    'word-partners': ('果皮', '树皮', '加法', '办法', '回来', '回答',
                      '许多', '不许', '到处', '四处', '方向', '地方'),
}
ART = {}


@lru_cache
def font(size, heavy=False):
    return ImageFont.truetype(FONT, size, index=1 if heavy else 6)


def canvas(width, height):
    return Image.new('RGB', (width, height), CREAM)


def label(draw, xy, text, size, *, color=GREEN):
    draw.text(xy, text, font=font(size, True), anchor='mm', fill=color)


def tile(image, name, bounds):
    with Image.open(ASSETS / (name + '.png')) as source:
        x, y, w, h = bounds
        fitted = ImageOps.contain(source.convert('RGBA'), (w, h), Image.Resampling.LANCZOS)
        image.paste(fitted, (x + (w-fitted.width)//2, y + (h-fitted.height)//2), fitted.getchannel('A'))


def save(key, image, inputs=()):
    ART[key] = list(inputs)
    if not args.describe:
        image.save(ASSETS / (key + '.png'), optimize=True)


def grid(draw, x, y, size):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=8, fill=PAPER, outline=LINE, width=3)
    for step in range(0, size, 10):
        m = min(size, step + 5)
        draw.line((x + step, y + size / 2, x + m, y + size / 2), fill=PALE, width=2)
        draw.line((x + size / 2, y + step, x + size / 2, y + m), fill=PALE, width=2)


def paths(draw, x, y, size, parts, current):
    radius = max(2, size // 45)
    for index, part in enumerate(parts):
        pts = [(x + round(a * size / 100), y + round(b * size / 100)) for a, b in part]
        ink = ORANGE if index == current else GREEN
        draw.line(pts, fill=ink, width=2 * radius, joint='curve')
        for a, b in (pts[0], pts[-1]):
            draw.ellipse((a - radius, b - radius, a + radius, b + radius), fill=ink)


def arrow(draw, x, y, end_x, end_y, color=GREEN):
    draw.line((x, y, end_x, end_y), fill=color, width=9)
    dx, dy = end_x - x, end_y - y
    length = (dx * dx + dy * dy) ** .5
    ax, ay = dx / length, dy / length
    draw.polygon([(end_x, end_y), (end_x - 19 * ax + 9 * ay, end_y - 19 * ay - 9 * ax),
                  (end_x - 19 * ax - 9 * ay, end_y - 19 * ay + 9 * ax)], fill=color)


def shape(draw, kind, left, top, size):
    x, y = left, top
    bounds = {
        'whole': [(x+10, y+10, x+size-10, y+size-10)],
        'up': [(x+10, y+10, x+size-10, y+size/2-5),
               (x+10, y+size/2+5, x+size-10, y+size-10)],
        'side': [(x+10, y+10, x+size/2-5, y+size-10),
                 (x+size/2+5, y+10, x+size-10, y+size-10)],
    }
    for rectangle in bounds[kind]:
        draw.rounded_rectangle(rectangle, radius=13, fill='#648674')


def structures():
    for kind in ('whole','up','side'):
        image = canvas(186,186)
        shape(ImageDraw.Draw(image), kind, 9, 9, 168)
        save('structure-' + kind, image)
    for key, char in CHARACTERS.items():
        if key in ('flower','work','mouth','claws'):
            continue
        image = canvas(186,186)
        draw = ImageDraw.Draw(image)
        grid(draw, 5, 5, 176)
        label(draw, (93,93), char, 126)
        save('character-' + key, image)
    image = canvas(654,244)
    draw = ImageDraw.Draw(image)
    for index, (key, kind) in enumerate([('flower','up'),('work','side'),('mouth','whole')]):
        left = 32 + index * 217
        grid(draw, left, 20, 114)
        label(draw, (left+57,77), CHARACTERS[key], 82)
        shape(draw, kind, left+11, 148, 92)
    save('structure-examples', image)


def recognition():
    pictures = ('cow','sheep','claws','dawn','assemble','bell')
    names = ('niú','yáng','zhuǎ','dàn','pīn','yīn')
    image = canvas(954,512)
    for index, (picture, char, pinyin) in enumerate(zip(pictures, TITLES['look-at-shapes'], names)):
        left, top = 15+316*(index%3), 14+250*(index//3)
        tile(image, picture, (left,top+11,149,203))
        draw = ImageDraw.Draw(image)
        grid(draw, left+155, top+30, 136)
        label(draw, (left+224,top+100), char, 92)
        label(draw, (left+221,top+195), pinyin, 36)
    save('recognition-chart', image, pictures)


def strokes(key, glyph, order=None):
    char, _, parts = MODEL[glyph]
    order = list(range(len(parts))) if order is None else order
    columns = 4 if len(order) in (4, 8) else 3
    rows = (len(order) + columns - 1) // columns
    size = 125
    image = canvas(20 + columns * (size+10), 20 + rows * (size+18))
    draw = ImageDraw.Draw(image)
    for step in range(len(order)):
        x, y = 11 + (step%columns)*(size+10), 11 + (step//columns)*(size+18)
        grid(draw, x, y, size)
        paths(draw, x, y, size, [parts[i] for i in order[:step+1]], step)
    save(key, image)


def sequence_assets():
    for key in ('ox','sheep','fruit','white','moon','wind','small','water'):
        strokes('write-' + key, key)
    for glyph, variations in (
        ('mountain', {'correct':[0,1,2],'left-first':[1,0,2],'right-first':[2,0,1]}),
        ('use', {'correct':[0,1,2,3,4],'middle-first':[4,0,1,2,3],'inside-first':[2,3,0,1,4]}),
    ):
        for label, order in variations.items():
            strokes('q-' + glyph + '-' + label, glyph, order)


def pair_sheet(key, pictures, words, *, wide=False):
    columns, rows = (2, 2) if wide else (len(pictures), 1)
    cell_width, cell_height = (338, 265) if wide else (179, 199)
    image = canvas(cell_width * columns, cell_height * rows)
    draw = ImageDraw.Draw(image)
    for i, (picture, word) in enumerate(zip(pictures,words)):
        row, column = divmod(i, columns)
        margin = 50 if word else 13
        size = min(cell_width - 18, cell_height - 16 - margin)
        x = column * cell_width + (cell_width - size) // 2
        y = row * cell_height + 12
        tile(image, picture, (x,y,size,size))
        if word:
            label(draw, (column*cell_width+cell_width//2,y+size+24), word, 36)
    save(key, image, pictures)

def word_sheets():
    image = canvas(272,272)
    draw = ImageDraw.Draw(image)
    for x,y in [(67,103),(67,165)]:
        draw.ellipse((x-15,y-15,x+15,y+15), fill=ORANGE)
    draw.line((116,135,152,135), fill=GREEN, width=8)
    draw.line((134,117,134,153), fill=GREEN, width=8)
    draw.ellipse((186,120,216,150), fill='#648674')
    save('addition-groups', image)
    direction = canvas(362,362)
    tile(direction,'garden-paths',(0,0,362,362))
    arrow(ImageDraw.Draw(direction),166,268,104,192)
    save('path-direction',direction,('garden-paths',))
    pair_sheet('word-samples-a',('fruit-peel','tree-bark','addition-groups','clip-idea'),
               ('果皮','树皮','加法','办法'),wide=True)
    pair_sheet('word-samples-b',('return-to-door','answer-teacher','many-lanterns','stop-at-rope'),
               ('回来','回答','许多','不许'),wide=True)
    pair_sheet('word-samples-c',('flowers-everywhere','search-around','path-direction','exhibit-place'),
               ('到处','四处','方向','地方'),wide=True)
    pair_sheet('wind-scenes',('autumn-gust','spring-blossoms','river-waves','bamboo-gust'),
               ('','','',''),wide=True)
    pair_sheet('move-open',('cart-rest','character-only','structure-up','structure-whole'),('','','',''))
    pair_sheet('bubbles-open',('fruit-peel','tree-bark','skiff'),('','',''))
    for key, path in [('q-return-away','q-walk-away'),('q-return-back','q-walk-back'),
                      ('q-return-stay','q-sit-still')]:
        image = canvas(600,315)
        tile(image,'q-walk-away',(16,27,241,241))
        tile(image,path,(342,27,241,241))
        arrow(ImageDraw.Draw(image),273,149,325,149)
        save(key,image,('q-walk-away',path))


def small_game_cards():
    for key in ('autumn-gust','river-waves','bamboo-gust'):
        with Image.open(ASSETS / (key + '.png')) as source:
            image = ImageOps.contain(source.convert('RGB'), (240,240), Image.Resampling.LANCZOS)
            save('game-' + key, image, (key,))


def main():
    structures()
    recognition()
    sequence_assets()
    word_sheets()
    small_game_cards()
    if args.describe:
        print(json.dumps(ART,ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--describe', action='store_true')
    args=parser.parse_args()
    main()
