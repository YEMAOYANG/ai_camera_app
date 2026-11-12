"""Render the controlled visibility comparison, preserving target geometry."""

from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SIZE = (510, 360)
TARGET = (255, 239)
TARGET_RADIUS = 29
ORANGE = '#d66b25'
BLUE = '#265e95'
PAPER = '#fff6e5'
SAMPLES = {
    'clear': ('#dcefe7', '#538775', True),
    'wood': ('#cb9163', '#855334', False),
    'metal': ('#929d9e', '#5c666d', False),
}


def ring(draw, center, radius=TARGET_RADIUS):
    x, y = center
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline=ORANGE, width=12)


def mark(draw, symbol, center, radius):
    if symbol == 'ring':
        ring(draw, center, radius)
    else:
        x, y = center
        draw.polygon(((x, y-radius), (x-radius, y+radius), (x+radius, y+radius)), fill=BLUE)


def controlled_view(kind, symbol='ring'):
    fill, edge, visible = SAMPLES[kind]
    image = Image.new('RGB', SIZE, PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((9, 9, 500, 350), 26, fill='#f0e7d5', outline='#657b63', width=4)
    draw.rounded_rectangle((202, 19, 308, 99), 15, fill=PAPER, outline='#98a38d', width=3)
    mark(draw, symbol, (255, 59), TARGET_RADIUS)
    draw.line((255, 111, 255, 147), fill='#56745e', width=6)
    draw.polygon(((240, 139), (270, 139), (255, 156)), fill='#56745e')

    # All panels cover the same target area. Only the clear panel shows its ring.
    draw.rounded_rectangle((107, 165, 403, 314), 16, fill=fill, outline=edge, width=5)
    if visible:
        mark(draw, symbol, TARGET, TARGET_RADIUS)
    draw.line((129, 185, 164, 185), fill='#fff7eb', width=5)
    return image


def comparison():
    image = Image.new('RGB', (1028, 368), PAPER)
    image.paste(controlled_view('clear'), (0, 4))
    image.paste(controlled_view('metal'), (518, 4))
    return image


def render():
    items = {
        'same-ring-comparison': (comparison(), ['same-method-fair-compare']),
        'window-clear': (controlled_view('clear', 'triangle'), ['picture-quiz']),
        'window-wood': (controlled_view('wood', 'triangle'), ['picture-quiz']),
        'window-metal': (controlled_view('metal', 'triangle'), ['picture-quiz']),
    }
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    source = Path(__file__).resolve()
    records = {}
    for key, (image, uses) in items.items():
        path = ROOT/'assets'/f'{key}.png'
        image.save(path, optimize=True)
        records[key] = {
            'file': path.relative_to(ROOT).as_posix(),
            'sha256': digest(path),
            'kind': 'deterministic-lesson-diagram',
            'source': source.relative_to(ROOT).as_posix(),
            'sourceSha256': digest(source),
            'usedBy': uses,
        }
    path = ROOT/'asset-sources.json'
    existing = json.loads(path.read_text()) if path.exists() else {
        'schemaVersion': 'mira.courseware.asset-sources.v1', 'assets': {},
    }
    existing['assets'].update(records)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    render()
