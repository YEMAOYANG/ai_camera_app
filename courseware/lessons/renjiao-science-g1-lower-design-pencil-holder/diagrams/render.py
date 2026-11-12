"""Draw paired orthographic records and precise picture choices from one holder model."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


SIZE = (720, 460)
PAPER = '#fff7e5'
PAPER_LIGHT = '#fffdf3'
INK = '#294c48'
WOOD = '#e5bf89'
MARK = '#3f9a71'
TOOLS = {
    'ruler': ('#17988d', 154, 17),
    'pencil-red': ('#de664f', 67, 13),
    'pencil-ochre': ('#d99a37', 73, 13),
    'marker-blue': ('#417db7', 113, 16),
    'eraser': ('#d88ba5', 9, 25),
    'brush': ('#7254a1', 144, 17),
    'wax': ('#e3814c', 64, 16),
    'small-wax': ('#e3814c', 36, 16),
}


@dataclass(frozen=True)
class Bin:
    x: int
    y: int
    width: int
    depth: int
    height: int
    outside: str
    inside: str
    round: bool = True


@dataclass(frozen=True)
class Piece:
    kind: str
    bin: str
    offset: int = 0

    @property
    def size(self):
        return TOOLS[self.kind][1]


BINS = {
    'tall': Bin(48, 58, 65, 65, 102, '#637da4', '#b2c5dd'),
    'low': Bin(124, 58, 64, 64, 50, '#c77545', '#f4c495'),
    'tray': Bin(203, 67, 58, 47, 15, '#639276', '#c0dfc4', False),
}

TRIALS = (
    (Piece('ruler', 'tall'), Piece('pencil-red', 'low'), Piece('eraser', 'tray')),
    (Piece('ruler', 'tall', -12), Piece('pencil-red', 'tall', 14), Piece('eraser', 'tray')),
    (Piece('ruler', 'tall', -13), Piece('marker-blue', 'tall', 14),
     Piece('pencil-red', 'low', -11), Piece('pencil-ochre', 'low', 12), Piece('eraser', 'tray')),
)


def visible_from_side(load, bins=BINS):
    """A tool below its own front rim cannot be seen from the model's side."""
    return tuple(p.kind for p in load if p.bin in bins and p.size > bins[p.bin].height)


def card(size=SIZE):
    image = Image.new('RGB', size, PAPER)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rounded_rectangle((12, 12, w-13, h-13), radius=25,
                           fill=PAPER_LIGHT, outline='#e8d6b9', width=4)
    return image, draw


def _rim(draw, box, rim, center, is_round):
    draw_shape = draw.ellipse if is_round else draw.rounded_rectangle
    extras = {} if is_round else {'radius': 14}
    draw_shape(box, fill=rim, outline=INK, width=4, **extras)
    x0, y0, x1, y1 = box
    draw_shape((x0+9, y0+9, x1-9, y1-9), fill=center, outline=INK, width=3, **extras)


def from_top(load, bins=BINS, *, board=True):
    image, draw = card()
    scale = 2.22
    ox, oy = 86, 105
    if board:
        draw.rounded_rectangle((ox, oy, ox+249*scale, oy+119*scale), radius=19,
                               fill=WOOD, outline=INK, width=5)
        draw.ellipse((345, 337, 375, 365), fill=MARK, outline=INK, width=3)
    for section in bins.values():
        x, y = ox+section.x*scale, oy+section.y*scale
        hw, hd = section.width*scale/2, section.depth*scale/2
        _rim(draw, (x-hw, y-hd, x+hw, y+hd), section.outside, section.inside, section.round)
    for piece in load:
        if piece.bin not in bins:
            continue
        section = bins[piece.bin]
        color, _, _ = TOOLS[piece.kind]
        x = ox+(section.x+piece.offset)*scale
        y = oy+section.y*scale
        if piece.kind in ('ruler', 'eraser'):
            w, h = (42, 13) if piece.kind == 'ruler' else (50, 30)
            draw.rounded_rectangle((x-w/2, y-h/2, x+w/2, y+h/2), radius=4,
                                   fill=color, outline=INK, width=3)
        else:
            r = 14
            draw.ellipse((x-r, y-r, x+r, y+r), fill=color, outline=INK, width=3)
            draw.ellipse((x-4, y-4, x+4, y+4), fill=PAPER_LIGHT)
    return image


def _draw_upright(draw, piece, x, base):
    color, height, width = TOOLS[piece.kind]
    top = base-height*1.74
    draw.rounded_rectangle((x-width/2, top, x+width/2, base), radius=4,
                           fill=color, outline=INK, width=3)
    if piece.kind == 'ruler':
        for delta in range(11, 58, 10):
            draw.line((x-width/2+2, top+delta, x+1, top+delta), fill=PAPER_LIGHT, width=2)
    elif piece.kind == 'brush':
        draw.ellipse((x-8, top-21, x+8, top+9), fill='#5e4651', outline=INK, width=2)
        draw.rectangle((x-width/2+1, top+8, x+width/2-1, top+15), fill='#d7bb84')
    else:
        draw.line((x-width/2+2, top+10, x+width/2-2, top+10), fill=PAPER_LIGHT, width=2)


def from_side(load, bins=BINS, *, board=True):
    image, draw = card()
    scale = 2.22
    ox, base = 86, 361
    if board:
        draw.rounded_rectangle((ox, base-1, ox+249*scale, base+26), radius=7,
                               fill=WOOD, outline=INK, width=5)
        draw.ellipse((350, 364, 370, 384), fill=MARK, outline=INK, width=2)
    for name, section in bins.items():
        x = ox+section.x*scale
        w = section.width*scale
        y = base-section.height*1.74
        oval = min(16, section.height/2)
        draw.rounded_rectangle((x-w/2, y, x+w/2, base), radius=11,
                               fill=section.outside, outline=INK, width=4)
        draw.ellipse((x-w/2, y-oval, x+w/2, y+oval), fill=section.inside, outline=INK, width=4)
        for piece in load:
            if piece.bin == name:
                _draw_upright(draw, piece, x+piece.offset*scale, base)
        # Redraw the front after the tools so the rim really occludes a short tool.
        draw.rounded_rectangle((x-w/2, y+2, x+w/2, base), radius=11,
                               fill=section.outside, outline=INK, width=4)
        draw.arc((x-w/2, y-oval, x+w/2, y+oval), start=0, end=180, fill=INK, width=4)
        draw.line((x-w/2+15, base-9, x+w/2-15, base-9), fill=section.inside, width=4)
    return image


def _item(draw, x, y, kind, *, neutral=False):
    if kind == 'base':
        draw.rounded_rectangle((x-67, y-16, x+67, y+26), radius=7, fill=WOOD, outline=INK, width=4)
        draw.line((x-49, y+12, x+47, y+12), fill='#ac8154', width=3)
    elif kind == 'divider':
        draw.polygon(((x-49, y-44), (x+50, y-61), (x+50, y+38), (x-49, y+53)), fill='#d8b988', outline=INK, width=4)
    elif kind == 'tape':
        draw.ellipse((x-43, y-43, x+43, y+43), fill='#e6ba68', outline=INK, width=4)
        draw.ellipse((x-22, y-22, x+22, y+22), fill=PAPER_LIGHT, outline=INK, width=3)
    elif kind == 'pencil':
        draw.rounded_rectangle((x-56, y-12, x+48, y+12), radius=5,
                               fill='#de664f', outline=INK, width=4)
        draw.polygon(((x+48, y-11), (x+63, y), (x+48, y+11)),
                     fill='#e7bc87', outline=INK, width=3)
    else:
        section = BINS[kind]
        height = {'tall': 119, 'low': 70, 'tray': 38}[kind]
        outside, inside = ('#c29770', '#f1d9b5') if neutral else (section.outside, section.inside)
        draw.rounded_rectangle((x-59, y-height//2, x+59, y+height//2), radius=11,
                               fill=outside, outline=INK, width=4)
        draw.ellipse((x-59, y-height//2-16, x+59, y-height//2+16),
                     fill=inside, outline=INK, width=4)


def parts(tokens):
    image, draw = card()
    for i, token in enumerate(tokens):
        if len(tokens) > 3:
            x, y = (150, 360, 570)[i % 3], 144+(i//3)*176
        else:
            x, y = 360+(i-(len(tokens)-1)/2)*191, 230
        _item(draw, x, y, token)
    return image


def compact_part(kind):
    image, draw = card((196, 196))
    _item(draw, 98, 106, kind, neutral=True)
    return image


def compact_use(kind):
    """Purpose pictures fill their small dock tile without a matching color key."""
    image, draw = card((196, 196))
    if kind == 'tall':
        draw.rectangle((90, 24, 106, 117), fill='#17988d', outline=INK, width=3)
        for y in (30, 40, 50):
            draw.line((91, y, 99, y), fill=PAPER_LIGHT, width=2)
        _item(draw, 98, 119, kind, neutral=True)
        draw.rectangle((90, 24, 106, 55), fill='#17988d', outline=INK, width=3)
    elif kind == 'low':
        _item(draw, 98, 120, kind, neutral=True)
        draw.rounded_rectangle((87, 48, 109, 87), radius=4, fill='#de664f', outline=INK, width=3)
    elif kind == 'tray':
        _item(draw, 98, 126, kind, neutral=True)
        draw.rounded_rectangle((66, 90, 130, 115), radius=6, fill='#d88ba5', outline=INK, width=3)
    elif kind == 'base':
        _item(draw, 98, 144, kind)
        for x, h in ((70, 62), (124, 39)):
            draw.rounded_rectangle((x-23, 135-h, x+23, 135), radius=5,
                                   fill='#c29770', outline=INK, width=3)
    else:
        draw.rounded_rectangle((31, 52, 165, 150), radius=11, fill='#f1d9b5', outline=INK, width=5)
        draw.line((98, 54, 98, 147), fill=INK, width=8)
        draw.rounded_rectangle((47, 85, 80, 114), radius=5, fill='#d88ba5', outline=INK, width=3)
        draw.ellipse((114, 77, 147, 110), fill='#c77545', outline=INK, width=3)
    return image


def _circle_person(draw, x, y, large, color):
    r = 29 if large else 22
    draw.ellipse((x-r, y-r, x+r, y+r), fill='#edb884', outline=INK, width=3)
    draw.rounded_rectangle((x-r-8, y+r+4, x+r+8, y+r+85), radius=18, fill=color, outline=INK, width=4)
    draw.ellipse((x+5, y-3, x+10, y+2), fill=INK)


def adult_choice(mode):
    image, draw = card()
    draw.rounded_rectangle((92, 300, 633, 370), radius=14, fill=WOOD, outline=INK, width=5)
    _circle_person(draw, 202, 198, False, '#5f9d98')
    if mode == 'ask-adult':
        _circle_person(draw, 524, 144, True, '#8172aa')
        draw.line((220, 255, 322, 317), fill='#edb884', width=15)
        draw.line((500, 225, 401, 306), fill='#edb884', width=17)
        draw.rounded_rectangle((298, 305, 408, 352), radius=4, fill=PAPER_LIGHT, outline=INK, width=3)
        draw.rectangle((331, 315, 374, 341), outline='#639276', width=3)
        draw.line((351, 315, 351, 341), fill='#639276', width=3)
        draw.ellipse((353, 313, 377, 339), outline='#b85a47', width=3)
    elif mode == 'child-tool':
        draw.line((226, 259, 320, 313), fill='#edb884', width=13)
        draw.rectangle((391, 302, 551, 350), fill='#767d87', outline=INK, width=4)
        draw.ellipse((308, 308, 330, 330), outline='#b46b8f', width=6)
        draw.ellipse((316, 330, 338, 352), outline='#b46b8f', width=6)
        draw.line((328, 329, 377, 323), fill=INK, width=6)
    else:
        draw.line((224, 259, 350, 309), fill='#edb884', width=13)
        _item(draw, 450, 285, 'low')
        draw.rounded_rectangle((490, 321, 605, 357), radius=3, fill=PAPER_LIGHT, outline=INK, width=3)
        draw.line((526, 330, 575, 346), fill='#a5886b', width=3)
    return image


def design_plan():
    image = from_top(TRIALS[0])
    draw = ImageDraw.Draw(image)
    for x, color in ((195, '#637da4'), (361, '#c77545'), (536, '#639276')):
        draw.line((x, 86, x, 151), fill=color, width=6)
        draw.polygon(((x, 164), (x-11, 148), (x+11, 148)), fill=color)
    # A reserved second pencil footprint is distinct from the first tool.
    for angle in range(0, 360, 45):
        draw.arc((387, 218, 418, 249), angle, angle+25, fill='#825b44', width=3)
    # The small sheet and rolled paper identify the chosen materials.
    draw.rounded_rectangle((132, 394, 218, 425), radius=5,
                           fill=WOOD, outline=INK, width=3)
    for y in (404, 412, 419):
        draw.line((143, y, 202, y), fill='#af8254', width=2)
    draw.line((174, 394, 174, 371), fill=INK, width=3)
    draw.polygon(((174, 365), (168, 376), (180, 376)), fill=INK)
    draw.rounded_rectangle((277, 397, 322, 425), radius=6,
                           fill='#b2c5dd', outline=INK, width=3)
    draw.ellipse((292, 399, 319, 423), fill=PAPER_LIGHT, outline=INK, width=3)
    draw.line((301, 396, 343, 298), fill=INK, width=3)
    draw.polygon(((345, 290), (337, 301), (348, 303)), fill=INK)
    # A marking pencil and tape are shown at the edge of the work plan.
    draw.rounded_rectangle((476, 404, 554, 419), radius=4,
                           fill='#de664f', outline=INK, width=3)
    draw.polygon(((552, 404), (567, 412), (552, 419)), fill=WOOD, outline=INK)
    draw.ellipse((586, 391, 625, 430), fill='#e6ba68', outline=INK, width=3)
    draw.ellipse((596, 401, 615, 420), fill=PAPER_LIGHT, outline=INK, width=3)
    return image


def high_bin_cutaway():
    """Show the wax pencil behind a schematic window below the high rim."""
    image = from_side((), {'tall': BINS['tall']})
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((154, 221, 231, 353), radius=9,
                           fill='#b2c5dd', outline=INK, width=3)
    _draw_upright(draw, Piece('wax', 'tall'), 192, 348)
    for x in (155, 230):
        for y in range(234, 347, 17):
            draw.line((x, y, x, y+8), fill=PAPER_LIGHT, width=3)
    return image


def focus_bin(image, bin_name):
    x = round(86+BINS[bin_name].x*2.22)
    crop = image.crop((x-110, 129, x+110, 403))
    crop = crop.resize((330, 411), Image.Resampling.LANCZOS)
    choice, _ = card((430, 450))
    choice.paste(crop, (50, 18))
    return choice


def wax_on_board():
    image, draw = card((430, 450))
    draw.rounded_rectangle((81, 233, 350, 297), radius=10,
                           fill=WOOD, outline=INK, width=5)
    draw.rounded_rectangle((126, 207, 311, 238), radius=8,
                           fill=TOOLS['wax'][0], outline=INK, width=4)
    return image


def badge(kind):
    image, draw = card((180, 180))
    if kind == 'camera':
        draw.rounded_rectangle((33, 52, 147, 130), radius=12, fill='#72a58f', outline=INK, width=5)
        draw.rectangle((49, 39, 81, 55), fill='#72a58f', outline=INK, width=4)
        draw.ellipse((69, 63, 125, 119), fill='#53799d', outline=INK, width=5)
        draw.ellipse((86, 79, 107, 100), fill='#a7d9d5')
    elif kind == 'cart':
        draw.rounded_rectangle((33, 58, 148, 122), radius=12, fill='#cc925b', outline=INK, width=5)
        draw.line((33, 70, 20, 42), fill=INK, width=8)
        draw.ellipse((46, 115, 76, 145), fill=INK)
        draw.ellipse((106, 115, 136, 145), fill=INK)
    else:
        draw.ellipse((48, 48, 132, 132), fill=MARK, outline=INK, width=5)
        draw.line((70, 89, 84, 104, 113, 75), fill=PAPER_LIGHT, width=9, joint='curve')
    return image


def images():
    exact = {
        'part-wall-study': from_side((Piece('ruler', 'tall'),), {'tall': BINS['tall']}, board=False),
        'holder-front-study': from_side(TRIALS[0]),
        'design-plan': design_plan(),
        'materials-kit': parts(('tall', 'low', 'tray', 'base', 'tape', 'pencil')),
        'assembled-empty': from_side(()),
        'family-check': from_top(TRIALS[0]),
        'parts-cart': badge('cart'),
        'camera-badge': badge('camera'),
        'green-mark': badge('mark'),
    }
    for role in BINS.keys() | {'base', 'divider'}:
        exact['part-'+role] = compact_part(role)
        exact['use-'+role] = compact_use(role)
    for i, load in enumerate(TRIALS, 1):
        exact[f'trial-{i}-top'] = from_top(load)
        exact[f'trial-{i}-side'] = from_side(load)
    quiz_load = (Piece('brush', 'tall'), Piece('small-wax', 'low'))
    q_bins = {k:BINS[k] for k in ('tall','low')}
    exact.update({
        'q1-single': from_side((), {'tall': BINS['tall']}),
        'q1-split': from_side((), q_bins),
        'q1-tray': from_side((), {'tray': BINS['tray']}),
        'q2-low': focus_bin(from_side((Piece('wax','low'),), {'low': BINS['low']}), 'low'),
        'q2-high': focus_bin(high_bin_cutaway(), 'tall'),
        'q2-flat': wax_on_board(),
        'q3-both-low': parts(('base','low','low')),
        'q3-no-base': parts(('tall','low')),
        'q3-complete': parts(('base','tall','low')),
        'q4-child-tool': adult_choice('child-tool'),
        'q4-ask-adult': adult_choice('ask-adult'),
        'q4-guess': adult_choice('guess'),
        'q5-top': from_top(quiz_load,q_bins),
        'q5-side': from_side(quiz_load,q_bins),
        'q5-empty': from_top((),q_bins),
    })
    return exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    diagrams = images()
    for name, image in diagrams.items():
        path = args.out/(name+'.png')
        with path.open('xb') as output:
            image.save(output, format='PNG', optimize=True)
    print(f'Drew {len(diagrams)} precise diagrams.')


if __name__ == '__main__':
    main()
