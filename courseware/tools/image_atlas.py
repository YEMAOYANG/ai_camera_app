"""Prepare one imagegen atlas prompt, cut the returned image and record provenance.

Plan fields: atlasId, rows, columns, background (transparent or cream), and
assets (6–9 entries in row-major order with assetKey, description and usedBy).
Each entry may override its pixel crop as [left, top, right, bottom].

1. Run `prompt PLAN` and pass the text to the built-in imagegen tool.
2. Keep the original sheet under LESSON/art-source. Run
   `split PLAN LESSON SHEET --prompt-file SENT_PROMPT` with the exact prompt.
3. Run `contact OUTPUT ASSET...` inside a private task workspace, then verify
   the assets' subjects, colors and cropping in context before recording G6.

This tool makes no generation calls and never marks a visual review passed.
"""

import argparse
from contextlib import contextmanager
import fcntl
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageDraw, ImageFont


PROMPT = Path(__file__).with_name('prompts') / 'image_atlas.v1.md'
KEY = re.compile(r'[a-z0-9][a-z0-9_-]{0,59}\Z')
SOURCE = 'Codex built-in image_gen'
BACKGROUNDS = {
    'transparent': 'Use true transparent alpha for the background, including the margins. Do not draw a checkerboard.',
    'cream': 'Use one flat, uniform warm cream background across the atlas.',
}


def validate_plan(plan):
    atlas_id = plan.get('atlasId') if isinstance(plan, dict) else None
    if not isinstance(atlas_id, str) or not KEY.fullmatch(atlas_id):
        raise ValueError('atlasId must be a lowercase filename key')
    rows, columns, assets = plan.get('rows'), plan.get('columns'), plan.get('assets')
    if ((rows, columns) not in ((2, 3), (3, 2), (3, 3)) or type(rows) is not int or type(columns) is not int
            or not isinstance(assets, list) or not 6 <= len(assets) <= rows * columns):
        raise ValueError('use a 2×3, 3×2 or 3×3 layout with 6–9 assets')
    if plan.get('background') not in tuple(BACKGROUNDS):
        raise ValueError('background must be transparent or cream')
    keys = set()
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get('assetKey'), str):
            raise ValueError('each asset needs a lowercase assetKey')
        key, description, uses = asset['assetKey'], asset.get('description'), asset.get('usedBy')
        if not KEY.fullmatch(key) or key in keys:
            raise ValueError(f'invalid or duplicate assetKey: {key}')
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f'missing picture description for {key}')
        if not isinstance(uses, list) or not uses or not all(isinstance(use, str) and use.strip() for use in uses):
            raise ValueError(f'missing page or quiz references for {key}')
        crop = asset.get('crop')
        if 'crop' in asset and (not isinstance(crop, list) or len(crop) != 4 or not all(type(x) is int for x in crop)):
            raise ValueError(f'{key}: crop must have four integer pixel coordinates')
        keys.add(key)


def render_prompt(plan):
    validate_plan(plan)
    columns = plan['columns']
    cells = '\n'.join(f'Row {i // columns + 1}, column {i % columns + 1}: {asset["description"].strip()}'
                      for i, asset in enumerate(plan['assets']))
    return PROMPT.read_text(encoding='utf-8').format(rows=plan['rows'], columns=columns, cells=cells,
                                                    background=BACKGROUNDS[plan['background']])


def crop_boxes(plan, size, inset):
    width, height = size
    rows, columns = plan['rows'], plan['columns']
    boxes = []
    for i, asset in enumerate(plan['assets']):
        row, column = divmod(i, columns)
        default = (column * width // columns + inset, row * height // rows + inset,
                   (column + 1) * width // columns - inset, (row + 1) * height // rows - inset)
        box = tuple(asset.get('crop', default))
        left, top, right, bottom = box
        key = asset['assetKey']
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(f'{key}: crop is empty or outside the sheet: {box}')
        if any(left < r and l < right and top < b and t < bottom for l, t, r, b in boxes):
            raise ValueError(f'{key}: crop overlaps a previous crop: {box}')
        boxes.append(box)
    return boxes


def png_bytes(image, max_edge):
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()


def check_destination(path, data):
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != data)):
        raise ValueError(f'refusing to replace existing output: {path}')


def write_new(path, data):
    # Publishing via a hard link makes a new file visible only after writing all its bytes.
    # Re-running the same split repairs interrupted writes without replacing existing files.
    check_destination(path, data)
    if path.exists():
        return
    with tempfile.NamedTemporaryFile(dir=path.parent) as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
        try:
            os.link(output.name, path)
        except FileExistsError:
            check_destination(path, data)


@contextmanager
def lock_source_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def split_atlas(plan, lesson, sheet, prompt_bytes, *, inset=0, max_edge=512):
    validate_plan(plan)
    if not 0 <= inset <= 100 or not 128 <= max_edge <= 1024:
        raise ValueError('inset must be 0–100 and max-edge must be 128–1024 pixels')
    prompt = prompt_bytes.decode('utf-8')
    if not prompt.strip():
        raise ValueError('the exact sent prompt is required')
    lesson, sheet = lesson.resolve(strict=True), sheet.resolve(strict=True)
    source_dir, assets_dir = lesson / 'art-source', lesson / 'assets'
    if source_dir.is_symlink() or not sheet.is_relative_to(source_dir) or not sheet.is_file():
        raise ValueError('keep the original sheet in the lesson art-source directory')
    if assets_dir.is_symlink():
        raise ValueError('lesson assets directory must not be a symbolic link')

    raw = sheet.read_bytes()
    with Image.open(BytesIO(raw)) as original:
        transparent = plan['background'] == 'transparent'
        image = original.convert('RGBA')
        if not transparent:
            if image.getchannel('A').getextrema() != (255, 255):
                raise ValueError('cream atlas needs an opaque background')
            image = image.convert('RGB')
    boxes = crop_boxes(plan, image.size, inset)
    source = sheet.relative_to(lesson).as_posix()
    source_hash = sha256(raw).hexdigest()
    prompt_hash = sha256(prompt_bytes).hexdigest()
    assets, pending = [], []
    for asset, box in zip(plan['assets'], boxes):
        key = asset['assetKey']
        crop = image.crop(box)
        if transparent:
            # Ignore faint antialiasing or matte noise when checking for clipped subjects.
            bounds = crop.getchannel('A').point(lambda alpha: 255 if alpha >= 16 else 0).getbbox()
            if bounds is None or 0 in bounds[:2] or bounds[2] == crop.width or bounds[3] == crop.height:
                raise ValueError(f'{key}: transparent crop is empty, opaque or touches its border')
        payload = png_bytes(crop, max_edge)
        file = assets_dir / f'{key}.png'
        pending.append((file, payload))
        assets.append({'assetKey': key, 'path': file.relative_to(lesson).as_posix(),
                       'sha256': sha256(payload).hexdigest(), 'width': crop.width, 'height': crop.height,
                       'source': SOURCE, 'generatedSource': source, 'generatedSourceSha256': source_hash,
                       'prompt': prompt, 'promptSha256': prompt_hash, 'sourceCrop': list(box),
                       'usedBy': asset['usedBy'], 'visualReview': 'pending'})
    receipt = source_dir / f'{plan["atlasId"]}.receipt.json'
    document = {'schemaVersion': 'mira.courseware.image-atlas-receipt.v1', 'atlasId': plan['atlasId'],
                'background': plan['background'], 'sheetPixels': list(image.size), 'assets': assets}
    pending.append((receipt, (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')))
    # Validate the entire batch before writing the first output; publish the receipt last.
    with lock_source_directory(source_dir):
        for path, data in pending:
            check_destination(path, data)
        assets_dir.mkdir(exist_ok=True)
        for path, data in pending:
            write_new(path, data)
    return receipt


def contact_sheet(paths):
    if not 1 <= len(paths) <= 12:
        raise ValueError('review 1–12 images per contact sheet')
    columns = min(4, len(paths))
    rows = (len(paths) + columns - 1) // columns
    tile = 400
    canvas = Image.new('RGB', (columns * tile, rows * tile), '#f6eedc')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for i, path in enumerate(paths):
        row, column = divmod(i, columns)
        left, top = column * tile, row * tile
        draw.rectangle((left, top, left + tile - 1, top + tile - 1), outline='#baae96')
        with Image.open(path) as original:
            image = original.convert('RGBA')
        image.thumbnail((tile - 32, tile - 52), Image.Resampling.LANCZOS)
        canvas.paste(image, (left + (tile - image.width) // 2, top + (tile - 26 - image.height) // 2), image)
        label = path.stem
        while draw.textlength(label, font=font) > tile - 24:
            label = label[:-1]
        draw.text((left + 12, top + tile - 25), label, fill='#23382b', font=font)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', required=True)
    prompt = subparsers.add_parser('prompt', help='print the imagegen prompt')
    prompt.add_argument('plan', type=Path)
    split = subparsers.add_parser('split', help='cut one sheet into PNGs and register hashes and provenance')
    split.add_argument('plan', type=Path)
    split.add_argument('lesson', type=Path)
    split.add_argument('sheet', type=Path)
    split.add_argument('--prompt-file', type=Path, required=True)
    split.add_argument('--inset', type=int, default=0)
    split.add_argument('--max-edge', type=int, default=512)
    contact = subparsers.add_parser('contact', help='render one captioned review JPEG, at most 12 images and 1600 px')
    contact.add_argument('output', type=Path)
    contact.add_argument('images', nargs='+', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'contact':
            if args.output.suffix.lower() not in ('.jpg', '.jpeg'):
                raise ValueError('contact output must use .jpg or .jpeg')
            image = contact_sheet(args.images)
            output = BytesIO()
            image.save(output, format='JPEG', quality=88, optimize=True)
            write_new(args.output, output.getvalue())
            return
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
        if args.command == 'prompt':
            print(render_prompt(plan), end='')
            return
        print(split_atlas(plan, args.lesson, args.sheet, args.prompt_file.read_bytes(),
                          inset=args.inset, max_edge=args.max_edge))
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        parser.exit(1, f'Image atlas: {error}\n')


if __name__ == '__main__':
    main()
