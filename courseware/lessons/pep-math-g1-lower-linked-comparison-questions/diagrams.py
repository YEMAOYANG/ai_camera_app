"""Draw the exact, original quantity models used by the patrol lesson."""

from functools import lru_cache
from math import atan2, cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ASSETS = Path(__file__).with_name('assets')
PAPER = '#fff9eb'
INK = '#203d35'
PINE = '#357761'
MOSS = '#dce9ce'
ORANGE = '#cf7940'
PEACH = '#f5dbc0'
BLUE = '#35758b'
GOLD = '#edb651'


@lru_cache(maxsize=None)
def font(size):
    for path in ('DejaVuSans-Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def canvas(width=880, height=468):
    image = Image.new('RGB', (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, width - 11, height - 11), radius=28, outline=MOSS, width=4)
    return image, draw


def number(draw, xy, value, size=52, color=INK):
    draw.text(xy, str(value), font=font(size), fill=color, anchor='mm')


def arrow(draw, start, end, color=PINE, width=7):
    x, y = end
    heading = atan2(y - start[1], x - start[0])
    draw.line((start, end), fill=color, width=width)
    draw.polygon([end, *[(x - 20 * cos(heading + a), y - 20 * sin(heading + a))
                         for a in (-.59, .59)]], fill=color)


def mark(draw, x, y, size, shape, color):
    """Draw one countable object, leaving a clear gap to every other object."""
    r = size / 2
    if shape == 'bottle':
        draw.rounded_rectangle((x-r*.6, y-r*.54, x+r*.6, y+r), radius=r*.22, fill=color)
        draw.rectangle((x-r*.31, y-r*.86, x+r*.31, y-r*.42), fill=color)
        draw.rounded_rectangle((x-r*.44, y-r, x+r*.44, y-r*.72), radius=r*.12, fill=INK)
        draw.line((x-r*.34, y+r*.15, x+r*.34, y+r*.15), fill=PAPER, width=max(1, round(r*.23)))
    elif shape == 'bird':
        draw.ellipse((x-r*.8, y-r*.28, x+r*.65, y+r*.63), fill=color)
        draw.ellipse((x+r*.1, y-r*.73, x+r*.74, y-r*.07), fill=color)
        draw.polygon(((x+r*.61, y-r*.42), (x+r, y-r*.28), (x+r*.6, y-r*.12)), fill=GOLD)
        draw.polygon(((x-r*.5, y), (x-r, y-r*.56), (x-r*.75, y+r*.31)), fill=color)
    elif shape == 'square':
        draw.rounded_rectangle((x-r*.78, y-r*.78, x+r*.78, y+r*.78), radius=r*.24, fill=color)
    elif shape == 'pen':
        draw.polygon(((x-r*.3, y-r*.78), (x+r*.34, y-r*.78), (x+r*.34, y+r*.5),
                      (x, y+r*.96), (x-r*.3, y+r*.5)), fill=color)
        draw.line((x-r*.3, y-r*.47, x+r*.34, y-r*.47), fill=PAPER, width=max(1, int(r*.15)))
    elif shape == 'tent':
        draw.polygon(((x-r, y+r*.74), (x, y-r*.88), (x+r, y+r*.74)), fill=color)
        draw.polygon(((x-r*.25, y+r*.74), (x, y-r*.12), (x+r*.25, y+r*.74)), fill=PAPER)
    else:
        draw.ellipse((x-r*.78, y-r*.78, x+r*.78, y+r*.78), fill=color)
        if shape == 'button':
            for offset in (-.25, .25):
                draw.ellipse((x+r*offset-r*.1, y-r*.1, x+r*offset+r*.1, y+r*.1), fill=PAPER)
        if shape == 'lantern':
            draw.line((x, y-r, x, y+r), fill=color, width=max(2, round(r*.28)))
            draw.arc((x-r*.42, y-r*.59, x+r*.42, y+r*.59), 95, 265, fill=PAPER, width=2)


def row(draw, count, x, y, step, shape, color):
    for i in range(count):
        mark(draw, x + i*step, y, step*.85, shape, color)


def badge(draw, x, y, value, color=PINE, fill=MOSS):
    draw.rounded_rectangle((x-56, y-42, x+56, y+42), radius=19, fill=fill)
    number(draw, (x, y), value, 51, color)


def comparison(first, delta, *, answer=False, shapes=('bottle','bottle'), equation=False, cover=False):
    image, draw = canvas()
    a, b = shapes
    second = first + delta
    step = min(32, 598 / max(first, second))
    x = 150
    if cover:
        cover_image = Image.open(ASSETS/'patrol-cover.png')
        image.paste(cover_image.resize((197,197)), (654,24))
        step = min(step, 490/max(first, second))
    row(draw, first, x, 141, step, a, PINE)
    badge(draw, 68, 141, first)
    if answer:
        row(draw, second, x, 253, step, b, ORANGE)
        badge(draw, 68, 253, second, ORANGE, PEACH)
        boundary = min(first, second)
        start = x+(boundary-.47)*step
        end = x+(max(first, second)-.53)*step
        bracket_y = 185 if delta < 0 else 289
        draw.line((start, bracket_y, end, bracket_y), fill=ORANGE, width=4)
        for edge in (start, end):
            draw.line((edge, bracket_y-8, edge, bracket_y+8), fill=ORANGE, width=4)
    else:
        badge(draw, 68, 253, '?', ORANGE, PEACH)
        draw.rounded_rectangle((140, 225, 448, 281), radius=18, outline=ORANGE, width=3)
        mark(draw, 177, 252, 34, b, ORANGE)
        number(draw, (294, 252), '?', 40, ORANGE)
    sign = '+' if delta > 0 else '−'
    if equation:
        number(draw, (440, 371), f'{first} {sign} {abs(delta)} = {second}', 60)
    else:
        draw.rounded_rectangle((323, 333, 557, 413), radius=24, fill=PEACH)
        number(draw, (440, 373), f'{sign}{abs(delta)}', 54, ORANGE)
    return image


def merge(first, second, *, shape='bottle', answer=True):
    image, draw = canvas()
    for y, value, color, fill in ((115, first, PINE, MOSS), (234, second, ORANGE, PEACH)):
        badge(draw, 105, y, value, color, fill)
        if isinstance(value, int):
            row(draw, value, 182, y, min(26, 414/value), shape, color)
        else:
            draw.rounded_rectangle((164, y-25, 499, y+25), radius=15, outline=color, width=3)
        arrow(draw, (590, y), (688, 174), color)
    total = first+second if answer else '?'
    badge(draw, 750, 174, total)
    number(draw, (442, 371), f'{first} + {second} = {total}', 65)
    return image


def chain(first, remove_one, remove_two, *, shape='button', reveal=True):
    image, draw = canvas()
    second = first-remove_one
    third = second-remove_two
    for x, value, color, fill in ((151, first, PINE, MOSS), (440, second, ORANGE, PEACH),
                                  (729, third, BLUE, MOSS)):
        badge(draw, x, 260, value if reveal or x == 151 else '?', color, fill)
        mark(draw, x, 339, 44, shape, color)
    for x, quantity in ((296, remove_one), (584, remove_two)):
        arrow(draw, (x-76, 259), (x+76, 259), ORANGE)
        number(draw, (x, 195), f'−{quantity}', 43, ORANGE)
    if reveal:
        number(draw, (440, 405), f'{first} − {remove_one} = {second}     {second} − {remove_two} = {third}', 35)
    return image


def choice(*values, shape='bottle', operation=None):
    image, draw = canvas(530, 340)
    if len(values) == 1:
        value = values[0]
        badge(draw, 265, 155, value, ORANGE, PEACH)
        if isinstance(value, int):
            row(draw, value, 265-(value-1)*min(25, 424/value)/2, 239, min(25, 424/value), shape, ORANGE)
        else:
            mark(draw, 265, 244, 44, shape, ORANGE)
        return image
    colors = (PINE, ORANGE)
    for x, value, color, fill in zip((147, 382), values, colors, (MOSS, PEACH)):
        badge(draw, x, 164, value, color, fill)
        mark(draw, x, 247, 43, shape, color)
    if operation == 'arrow':
        arrow(draw, (221, 165), (309, 165), ORANGE)
    else:
        number(draw, (265, 165), '+', 62)
    return image


def quiz_focus(kind, first, delta, shape):
    """Show the asked quantity without the completed calculation or its value."""
    image, draw = canvas(530, 340)
    color, fill = {'group': (ORANGE, PEACH), 'difference': (BLUE, MOSS), 'total': (PINE, MOSS)}[kind]
    if kind == 'total':
        badge(draw, 112, 109, first, PINE, MOSS)
        badge(draw, 112, 224, '?', ORANGE, PEACH)
        arrow(draw, (182, 111), (335, 163), PINE)
        arrow(draw, (182, 224), (335, 175), ORANGE)
        badge(draw, 405, 169, '?', color, fill)
    else:
        badge(draw, 102, 107, first, PINE, MOSS)
        badge(draw, 102, 232, '?', ORANGE, PEACH)
        draw.rounded_rectangle((175, 69, 442, 145), radius=21, fill=MOSS)
        draw.rounded_rectangle((175, 194, 442, 270), radius=21,
                               fill=PEACH if kind == 'group' else PAPER, outline=ORANGE, width=4)
        mark(draw, 220, 107, 45, shape, PINE)
        mark(draw, 220, 232, 45, shape, ORANGE)
        if kind == 'difference':
            number(draw, (384, 170), f'{"+" if delta > 0 else "−"}{abs(delta)}', 37, BLUE)
        else:
            number(draw, (335, 230), '?', 44, ORANGE)
    return image


def campground(draw, x, y, forest):
    if forest:
        draw.rectangle((x-5,y+10,x+5,y+29),fill=INK)
        for offset in (-24,-9,6):
            draw.polygon(((x,y+offset-16),(x-28,y+offset+13),(x+28,y+offset+13)),fill=PINE)
    else:
        for offset in (-14,4,22):
            draw.line([(x-34+i*5,y+offset+5*sin(i*pi/4)) for i in range(14)],fill=BLUE,width=5)


def campsite_option(kind):
    image,draw=canvas(530,340)
    if kind=='creek':
        campground(draw,100,86,False)
        badge(draw,399,92,19)
        for y,count in ((189,10),(250,9)):
            row(draw,count,104,y,35,'tent',BLUE)
    elif kind=='extra':
        campground(draw,89,87,False)
        campground(draw,89,201,True)
        draw.rounded_rectangle((142,58,331,118),radius=14,fill=MOSS)
        number(draw,(237,88),19,42)
        draw.rounded_rectangle((142,166,490,236),radius=15,outline=ORANGE,width=4)
        draw.rounded_rectangle((334,166,490,236),radius=15,fill=PEACH)
        row(draw,5,354,198,26,'tent',ORANGE)
        draw.line((334,252,489,252),fill=ORANGE,width=5)
        for x in (334,489):
            draw.line((x,241,x,261),fill=ORANGE,width=5)
        number(draw,(410,293),'+5',48,ORANGE)
    else:
        campground(draw,88,130,True)
        draw.rounded_rectangle((143,72,483,186),radius=22,fill=PEACH,outline=ORANGE,width=6)
        mark(draw,209,126,62,'tent',ORANGE)
        number(draw,(351,128),'?',72,ORANGE)
        draw.line((150,229,476,229),fill=ORANGE,width=6)
        for x in (150,476):
            draw.line((x,215,x,244),fill=ORANGE,width=6)
        number(draw,(314,280),'?',49,ORANGE)
    return image


def campsite_prompt():
    image=comparison(19,5,shapes=('tent','tent'))
    draw=ImageDraw.Draw(image)
    campground(draw,783,137,False)
    campground(draw,783,251,True)
    return image


def token(value, shape):
    image = Image.new('RGBA', (192,192))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5,5,186,186), radius=29, fill=MOSS if shape == 'tent' else PEACH,
                           outline=PINE if shape == 'tent' else ORANGE, width=6)
    mark(draw, 96, 43, 42, shape, PINE if shape == 'tent' else ORANGE)
    number(draw, (96, 123), value, 94)
    return image


def sticker():
    image = Image.new('RGBA', (192,192))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8,8,184,184), fill=PEACH, outline=PINE, width=9)
    draw.polygon([(96+radius*cos(i*pi/5-pi/2), 96+radius*sin(i*pi/5-pi/2))
                  for i, radius in enumerate([62,28]*5)], fill=GOLD, outline=ORANGE, width=5)
    return image


def delivery_clue(first, change, next_change=None):
    image, draw = canvas(880,240)
    if next_change is None:
        for x,y,value,color,fill in ((180,77,first,PINE,MOSS),(180,171,'?',ORANGE,PEACH)):
            draw.rounded_rectangle((86,y-40,274,y+40), radius=17, fill=fill)
            mark(draw, 119, y, 41, 'bottle', color)
            number(draw, (208,y), value, 76, color)
        draw.line((330,77,330,171), fill=ORANGE, width=6)
        number(draw, (480,121), f'{"+" if change > 0 else "−"}{abs(change)}', 95, ORANGE)
        arrow(draw, (595,123), (711,123), PINE, 9)
        number(draw, (772,123), '?', 94, PINE)
    else:
        for x,value,color,fill in ((114,first,PINE,MOSS),(440,'?',ORANGE,PEACH),(766,'?',BLUE,MOSS)):
            draw.rounded_rectangle((x-77,100,x+77,202), radius=18, fill=fill)
            number(draw, (x,150), value, 86, color)
        for x,value in ((277,change),(603,next_change)):
            number(draw, (x,81), f'−{value}', 78, ORANGE)
            arrow(draw, (x-73,151), (x+73,151), ORANGE, 8)
    return image


def diagrams():
    return {
        'story-known': comparison(18,-7,cover=True), 'story-missing': merge(18,'?',answer=False),
        'story-compare': comparison(18,-7,answer=True,equation=True), 'story-merge': merge(18,11),
        'story-more': comparison(21,8),
        'story-more-total': merge(21,29), 'story-left': chain(57,18,14,shape='round'),
        'hop-1': comparison(8,-3), 'hop-2': comparison(9,4), 'hop-3': comparison(20,6),
        'delivery-1': comparison(12,-2),
        'delivery-3': chain(34,9,6,shape='round',reveal=False),
        'delivery-clue-1': delivery_clue(12,-2), 'delivery-clue-2': delivery_clue(16,7),
        'delivery-clue-3': delivery_clue(34,9,6),
        'q1': comparison(11,-4,shapes=('bird','bird')), 'q1-a': quiz_focus('total',11,-4,'bird'),
        'q1-b': quiz_focus('group',11,-4,'bird'), 'q1-c': quiz_focus('difference',11,-4,'bird'),
        'q2': comparison(17,-6,shapes=('round','square')), 'q2-a': choice(23,shape='square'),
        'q2-b': choice(6,shape='square'), 'q2-c': choice(11,shape='square'),
        'q3': comparison(13,7,answer=True,shapes=('lantern','lantern')), 'q3-a': choice(13,20,shape='lantern'),
        'q3-b': choice(13,7,shape='lantern'), 'q3-c': choice(20,7,shape='lantern'),
        'q4': comparison(22,-9,shapes=('pen','pen')), 'q4-a': choice(31,shape='pen'),
        'q4-b': choice(35,shape='pen'), 'q4-c': choice(13,shape='pen'),
        'q5': campsite_prompt(), 'q5-a': campsite_option('creek'),
        'q5-b': campsite_option('extra'), 'q5-c': campsite_option('forest'),
        'q6': chain(41,12,8,reveal=False), 'q6-a': choice(29,21,shape='button',operation='arrow'),
        'q6-b': choice(29,33,shape='button',operation='arrow'),
        'q6-c': choice(21,29,shape='button',operation='arrow'),
        'patrol-sticker': sticker(),
        **{f'parcel-{value}': token(value,'bottle') for value in (2, 7, 9, 10, 12, 16, 19, 23, 25, 29, 34)},
        **{f'station-{value}': token(value,'tent') for value in (12, 16, 19, 22, 23, 25, 34, 39)},
    }


if __name__ == '__main__':
    for key, diagram in diagrams().items():
        diagram.save(ASSETS/f'{key}.png', optimize=True)
