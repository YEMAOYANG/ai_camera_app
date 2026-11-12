"""Lay out approved organizer illustrations without changing their contents."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CREAM = '#fff2de'
CARD = '#f4e8cf'
EDGE = '#78917f'


def illustration(key):
    with Image.open(ROOT / 'assets' / f'{key}.png') as raw:
        source = raw.convert('RGBA')
    alpha = source.getchannel('A').point(lambda value: 255 if value >= 16 else 0)
    return source.crop(alpha.getbbox())


def place(image, key, bounds):
    left, top, width, height = bounds
    art = ImageOps.contain(illustration(key), (width, height), Image.Resampling.LANCZOS)
    image.paste(art, (left + (width - art.width) // 2, top + (height - art.height) // 2), art)


def cards(rows, *, size, top=18):
    image = Image.new('RGB', size, CREAM)
    draw = ImageDraw.Draw(image)
    width, height = size
    panel_width = (width - 24) // len(rows[0])
    panel_height = (height - top - 12) // len(rows)
    for row, keys in enumerate(rows):
        for column, key in enumerate(keys):
            x, y = 12 + column * panel_width, top + row * panel_height
            draw.rounded_rectangle((x + 5, y, x + panel_width - 5, y + panel_height - 10), 18,
                                   fill=CARD, outline=EDGE, width=3)
            place(image, key, (x + 20, y + 12, panel_width - 40, panel_height - 34))
    return image


def delivery_cover():
    backdrop = ImageOps.fit(illustration('pocket-road-background'), (720, 380))
    image = Image.new('RGB', backdrop.size, '#2c5647')
    image.paste(backdrop, (0, 0), backdrop)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((27, 175, 330, 351), 26, fill=CARD, outline=EDGE, width=4)
    draw.rounded_rectangle((429, 22, 693, 240), 26, fill=CARD, outline=EDGE, width=4)
    place(image, 'storage-cart-idle', (49, 198, 120, 128))
    place(image, 'delivery-album', (177, 201, 132, 120))
    place(image, 'pocket-main', (446, 40, 230, 180))
    return image


def badge():
    image = Image.new('RGBA', (280, 280))
    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 264, 264), fill=CREAM, outline='#c67b37', width=8)
    place(image, 'delivery-album', (59, 59, 162, 162))
    return image


def photo_cover():
    image = cards((('storage-top-bag', 'storage-side-bag'),), size=(760, 450), top=116)
    place(image, 'storage-observer-camera', (317, 12, 126, 91))
    return image


def compositions():
    return {
        'pocket-guide': cards((('pocket-main', 'pocket-zip', 'pocket-side'),), size=(900, 325)),
        'pocket-delivery-cover': delivery_cover(),
        'storage-badge': badge(),
        'storage-photo-cover': photo_cover(),
        'storage-record-example': cards((('storage-top-bag', 'storage-top-toybox', 'storage-top-tray'),
                                         ('storage-side-bag', 'storage-side-toybox', 'storage-side-tray')),
                                        size=(900, 575)),
    }


def render():
    manifest_path = ROOT / 'asset-sources.json'
    manifest = json.loads(manifest_path.read_text())
    plan = json.loads((ROOT / 'art-plan.json').read_text())['compositions']
    source = Path(__file__).resolve()
    source_sha = sha256(source.read_bytes()).hexdigest()
    for key, picture in compositions().items():
        path = ROOT / 'assets' / f'{key}.png'
        output = BytesIO()
        picture.save(output, format='PNG', optimize=True)
        content = output.getvalue()
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f'Existing lesson artwork differs: {path.name}')
        else:
            path.write_bytes(content)
        manifest['assets'][key] = {
            'file': path.relative_to(ROOT).as_posix(), 'sha256': sha256(content).hexdigest(),
            'kind': 'composition-of-registered-artwork', 'source': source.relative_to(ROOT).as_posix(),
            'sourceSha256': source_sha, 'usedBy': plan[key]['uses'],
            'inputs': {item: manifest['assets'][item]['sha256'] for item in plan[key]['sources']},
        }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    render()
