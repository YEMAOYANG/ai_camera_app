"""Assemble the registered metal illustrations and mark the exact quiz regions."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from courseware.tools.image_atlas import write_new


ASSETS = Path(__file__).resolve().parents[1] / 'assets'
PAPER = '#fff4df'
FRAME = '#e4ead4'
EDGE = '#57755a'
COPPER_POLISH_START = 272
WIRE_REGIONS = {'coating': (150, 122), 'core': (356, 122), 'gap': (356, 205)}
WIRE_RING_RADIUS = 33


def asset(key):
    with Image.open(ASSETS / (key + '.png')) as image:
        return image.convert('RGBA')


def panel(canvas, box, image=None):
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, 15, fill=FRAME, outline=EDGE, width=2)
    if image is not None:
        paste(canvas, image, (box[0] + 8, box[1] + 8, box[2] - 8, box[3] - 8))


def paste(canvas, image, box):
    left, top, right, bottom = box
    picture = ImageOps.contain(image, (right - left, bottom - top))
    canvas.paste(picture, (left + (right - left - picture.width) // 2,
                           top + (bottom - top - picture.height) // 2), picture)


def copper_before_polishing(after):
    """Reuse the sample's matte surface while keeping its exact outer shape."""
    before = after.copy()
    for y in range(after.height):
        for x in range(COPPER_POLISH_START, after.width):
            matte = after.getpixel((2 * COPPER_POLISH_START - x - 1, y))
            before.putpixel((x, y), (*matte[:3], after.getpixel((x, y))[3]))
    return before


def known_samples():
    canvas = Image.new('RGB', (454, 307), PAPER)
    for row, material in enumerate(('copper', 'iron', 'aluminum')):
        y = 8 + row * 99
        panel(canvas, (14, y, 440, y + 88), asset('metal-top-' + material))
    return canvas


def polishing():
    canvas = Image.new('RGB', (710, 412), PAPER)
    copper = asset('metal-top-copper')
    panel(canvas, (16, 26, 408, 185), copper_before_polishing(copper))
    panel(canvas, (16, 227, 408, 386), copper)
    draw = ImageDraw.Draw(canvas)
    draw.line((212, 191, 212, 216), fill=EDGE, width=5)
    draw.polygon(((202, 210), (222, 210), (212, 222)), fill=EDGE)
    panel(canvas, (426, 66, 694, 346), asset('station-polish'))
    return canvas


def station_cover():
    canvas = Image.new('RGB', (722, 311), PAPER)
    for x, key in zip((18, 196, 374, 552), (
            'metal-trolley-idle', 'station-polish', 'result-polished', 'station-tap')):
        panel(canvas, (x, 55, x + 151, 256), asset(key))
    return canvas


def photo_cover():
    canvas = Image.new('RGB', (630, 282), PAPER)
    paste(canvas, asset('metal-observation-camera'), (264, 6, 366, 82))
    for x, view in ((19, 'top'), (324, 'side')):
        panel(canvas, (x, 91, x + 286, 263), asset('metal-' + view + '-copper'))
    return canvas


def notes_card():
    canvas = Image.new('RGB', (702, 430), PAPER)
    for column, material in enumerate(('copper', 'iron', 'aluminum')):
        x = 12 + 230 * column
        panel(canvas, (x, 19, x + 218, 141), asset('metal-top-' + material))
        panel(canvas, (x, 154, x + 218, 276), asset('metal-side-' + material))
        panel(canvas, (x, 289, x + 218, 411))
    return canvas


def wire_choice(region=None):
    canvas = Image.new('RGB', (480, 254), PAPER)
    paste(canvas, asset('quiz-wire-stimulus'), (42, 68, 438, 176))
    if region is not None:
        x, y = WIRE_REGIONS[region]
        radius = WIRE_RING_RADIUS
        draw = ImageDraw.Draw(canvas)
        box = (x - radius, y - radius, x + radius, y + radius)
        draw.ellipse(box, outline='#fffdf5', width=8)
        draw.ellipse((box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2),
                     outline='#265146', width=4)
    return canvas


def render():
    pictures = {
        'three-known-metals': known_samples(),
        'polish-before-after': polishing(),
        'metal-station-cover': station_cover(),
        'metal-photo-cover': photo_cover(),
        'metal-observation-notes': notes_card(),
        **{'quiz-wire-' + region: wire_choice(region) for region in WIRE_REGIONS},
    }
    for key, image in pictures.items():
        data = BytesIO()
        image.save(data, format='PNG', optimize=True)
        write_new(ASSETS / (key + '.png'), data.getvalue())


if __name__ == '__main__':
    render()
