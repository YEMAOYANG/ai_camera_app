"""Place approved single-object illustrations into countable groups for this lesson."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
PAPER = '#fff7e8'
INK = '#244f46'
LINE = '#ddd4be'
DIGIT_FONT = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'

FOUR_BOATS = ((100, 112), (230, 136), (347, 118), (540, 139))
HARBOR_BOATS = ((170, 224), (403, 256), (623, 227))
SHELL_POSITIONS = {
    4: ((175, 70), (345, 78), (158, 170), (365, 175)),
    5: ((140, 72), (275, 80), (420, 71), (203, 174), (351, 167)),
    6: ((103, 70), (269, 77), (433, 68), (116, 176), (280, 172), (429, 176)),
    7: ((95, 74), (207, 74), (319, 74), (431, 74), (147, 174), (264, 174), (381, 174)),
    8: ((95, 74), (207, 74), (319, 74), (431, 74), (95, 174), (207, 174), (319, 174), (431, 174)),
    9: ((82, 74), (173, 74), (264, 74), (355, 74), (446, 74), (126, 174), (217, 174), (308, 174), (399, 174)),
    10: ((82, 74), (173, 74), (264, 74), (355, 74), (446, 74), (82, 174), (173, 174), (264, 174), (355, 174), (446, 174)),
}


def _sprite(path):
    with Image.open(path) as source:
        if source.format != 'PNG' or 'A' not in source.getbands():
            raise ValueError(f'{path.name} needs a transparent imagegen PNG')
        rgba = source.convert('RGBA')
        alpha = rgba.getchannel('A')
        minimum, maximum = alpha.getextrema()
        if minimum != 0 or maximum < 250:
            raise ValueError(f'{path.name} needs a visible object on a transparent background')
        # Imagegen's nearly invisible alpha noise outside the object must not set its displayed size.
        visible = alpha.point(lambda value: 255 if value >= 8 else 0)
        return rgba.crop(visible.getbbox())


def _canvas(size):
    return Image.new('RGBA', size, PAPER)


def _place(canvas, sprite, centers, box):
    tile = ImageOps.contain(sprite, box, Image.Resampling.LANCZOS)
    for x, y in centers:
        canvas.alpha_composite(tile, (x - tile.width // 2, y - tile.height // 2))


def _boat_rows(boat, quantities):
    image = _canvas((840, 600))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(DIGIT_FONT, 44)
    row_height = image.height // len(quantities)
    for row, quantity in enumerate(quantities):
        y = row_height * row + row_height // 2
        if row:
            draw.line((25, row_height * row, 815, row_height * row), fill=LINE, width=3)
        draw.text((55, y), str(quantity), font=font, fill=INK, anchor='mm')
        _place(image, boat, [(132 + 70 * i, y) for i in range(quantity)], (59, 86))
    return image


def compositions(source):
    source = Path(source)
    boat = _sprite(source / 'wooden-boat-single.png')
    shell = _sprite(source / 'scallop-shell-single.png')
    with Image.open(source / 'harbor-backdrop.png') as background:
        harbor = ImageOps.fit(background.convert('RGBA'), (800, 350), Image.Resampling.LANCZOS)
    _place(harbor, boat, HARBOR_BOATS, (155, 118))

    four = _canvas((640, 310))
    _place(four, boat, FOUR_BOATS, (100, 112))
    tagged = four.copy()
    draw = ImageDraw.Draw(tagged)
    font = ImageFont.truetype(DIGIT_FONT, 31)
    for index, (x, y) in enumerate(FOUR_BOATS, 1):
        y += 82
        draw.ellipse((x - 23, y - 23, x + 23, y + 23), fill='#d26d43' if index == 4 else INK)
        draw.text((x, y), str(index), font=font, fill='white', anchor='mm')

    line = _canvas((640, 315))
    pairs = _canvas((640, 315))
    _place(line, boat, [(90 + 92 * i, 157) for i in range(6)], (80, 87))
    _place(pairs, boat, [(270 + 100 * col, 57 + 100 * row) for row in range(3) for col in range(2)], (80, 87))

    result = {
        'harbor-three': harbor,
        'four-boats': four,
        'four-boats-tagged': tagged,
        'boats-one-four': _boat_rows(boat, (1, 2, 3, 4)),
        'boats-five-seven': _boat_rows(boat, (5, 6, 7)),
        'boats-eight-ten': _boat_rows(boat, (8, 9, 10)),
        'six-boats-line': line,
        'six-boats-pairs': pairs,
    }
    for quantity, positions in SHELL_POSITIONS.items():
        tray = _canvas((528, 248))
        _place(tray, shell, positions, (71, 76))
        result[f'shells-{quantity}'] = tray
    return result


def main():
    images = compositions(ROOT / 'art-source')
    target = ROOT / 'assets'
    target.mkdir(exist_ok=True)
    for key, image in images.items():
        image.save(target / f'{key}.png', optimize=True)


if __name__ == '__main__':
    main()
