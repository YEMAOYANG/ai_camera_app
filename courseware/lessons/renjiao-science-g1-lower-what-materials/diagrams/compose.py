"""Arrange registered artwork into the lesson's comparable pictures."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
PAPER = '#fff6e4'
CARD = '#f0e8d4'
EDGE = '#6e8771'
SIGNAL = '#d65d22'
IMAGE_FILES = json.loads((ROOT / 'lesson.json').read_text())['images']


def artwork_path(key):
    return ROOT / IMAGE_FILES.get(key, {'file': f'assets/{key}.png'})['file']


def artwork(key):
    with Image.open(artwork_path(key)) as source:
        return source.convert('RGBA')


def visible_bounds(image):
    return image.getchannel('A').point(lambda alpha: 255 if alpha >= 16 else 0).getbbox()


def place(board, key, box):
    source = artwork(key)
    picture = ImageOps.contain(source.crop(visible_bounds(source)), (box[2], box[3]))
    left = box[0] + (box[2] - picture.width) // 2
    top = box[1] + (box[3] - picture.height) // 2
    board.paste(picture, (left, top), picture)


def card(board, box):
    ImageDraw.Draw(board).rounded_rectangle(box, 22, fill=CARD, outline=EDGE, width=4)


def paired(keys, *, size=(760, 420), badge=None, reserve_empty=False):
    width, height = size
    board = Image.new('RGB', size, PAPER)
    columns = len(keys) + int(reserve_empty)
    panel_width = (width - 36) // columns
    top = 120 if badge else 30
    for index in range(columns):
        left = 18 + index * panel_width
        card(board, (left, top, left + panel_width - 12, height - 25))
    for index, key in enumerate(keys):
        left = 18 + index * panel_width
        place(board, key, (left + 24, top + 20, panel_width - 60, height - top - 66))
    if badge:
        place(board, badge, (width // 2 - 60, 13, 120, 94))
    return board


def samples():
    board = Image.new('RGB', (800, 475), PAPER)
    for top, keys in ((14, ('wood', 'cloth', 'paper')), (168, ('glass', 'plastic')), (322, ('metal', 'stone'))):
        card(board, (34, top, 766, top + 139))
        for index, key in enumerate(keys):
            center = 400 + (index - (len(keys) - 1) / 2) * 215
            place(board, f'swatch-{key}', (int(center) - 85, top + 16, 170, 106))
    return board


def snap_stimulus():
    board = Image.new('RGB', (500, 345), PAPER)
    card(board, (12, 12, 487, 332))
    place(board, 'cloth-pouch', (101, 24, 298, 290))
    # This point is the measured center of the silver snap in its registered atlas crop.
    source_center = (341, 177)
    strap = artwork('quiz-snap-base')
    left, top, right, bottom = visible_bounds(strap)
    width = 255
    height = round(width * (bottom - top) / (right - left))
    picture = strap.crop((left, top, right, bottom)).resize((width, height), Image.Resampling.LANCZOS)
    x, y = 124, 145
    board.paste(picture, (x, y), picture)
    center_x = x + round((source_center[0] - left) * width / (right - left))
    center_y = y + round((source_center[1] - top) * height / (bottom - top))
    radius = 41
    draw = ImageDraw.Draw(board)
    draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                 outline='#773b23', width=10)
    draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                 outline=SIGNAL, width=6)
    return board


def compositions():
    return {
        'wood-object-comparison': paired(('wood-tray', 'wood-frame')),
        'seven-material-samples': samples(),
        'two-trays-compare': paired(('wood-tray', 'plastic-tray')),
        'stool-detail': paired(('material-side-stool', 'material-top-stool')),
        'photo-start-cover': paired(('material-top-stool', 'material-side-stool'), size=(720, 410),
                                    badge='material-camera'),
        'material-record-example': paired(('material-top-case', 'material-side-case'), reserve_empty=True),
        'quiz-fabric-snap-stimulus': snap_stimulus(),
        'quiz-wood-and-plastic-rulers': paired(('quiz-wood-ruler', 'quiz-plastic-ruler'), size=(590, 300)),
        'quiz-wood-and-gear': paired(('quiz-wood-ruler', 'quiz-wooden-gear'), size=(590, 300)),
    }


def render():
    plan = json.loads((ROOT / 'art-plan.json').read_text())['compositions']
    manifest_path = ROOT / 'asset-sources.json'
    manifest = json.loads(manifest_path.read_text())
    source = Path(__file__).resolve()
    source_sha = sha256(source.read_bytes()).hexdigest()
    for key, image in compositions().items():
        relative = f'assets/{key}.png'
        path = ROOT / relative
        output = BytesIO()
        image.save(output, format='PNG', optimize=True)
        data = output.getvalue()
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError(f'Existing lesson artwork differs: {relative}')
        else:
            path.write_bytes(data)
        inputs = list(plan[key]['sources'])
        if key == 'quiz-fabric-snap-stimulus':
            inputs.append('cloth-pouch')
        manifest['assets'][key] = {
            'file': relative,
            'sha256': sha256(data).hexdigest(),
            'kind': 'composition-of-registered-artwork',
            'source': source.relative_to(ROOT).as_posix(),
            'sourceSha256': source_sha,
            'inputs': {item: sha256(artwork_path(item).read_bytes()).hexdigest() for item in inputs},
            'usedBy': plan[key]['uses'],
        }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    render()
