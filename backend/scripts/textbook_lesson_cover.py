"""Make the catalog cover of one published textbook lesson from its own picture.

Usage: textbook_lesson_cover.py <content-key> <classroom.json | prepared-release.json> [--store DIR] [--image FILE] [--alt TEXT]

By default the cover is the first picture on the lesson's first slide, centre
cropped to 16:9. It is written as a 960x540 WebP into Student Web's
`public/textbooks/course-pictures-v1/` and listed in
`src/features/learning/lesson-pictures.json`, so Student Web must be rebuilt
(restart the local stack) before the cover shows. Nothing is generated.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PICTURES = ROOT / 'student-web/public/textbooks/course-pictures-v1'
LISTING = ROOT / 'student-web/src/features/learning/lesson-pictures.json'
SIZE = (960, 540)


def first_slide_picture(classroom, store):
    for scene in classroom['scenes']:
        if scene.get('type') != 'slide':
            continue
        for element in scene.get('content', {}).get('canvas', {}).get('elements', []):
            found = re.search(r'/api/classroom-media/([\w-]+)/media/([\w.-]+)', element.get('src') or '')
            if element.get('type') == 'image' and found:
                return store / found.group(1) / 'media' / found.group(2), element.get('alt') or ''
    raise SystemExit('the lesson has no slide picture; pass --image')


def cover(picture):
    with Image.open(picture) as image:
        image = image.convert('RGB')
        width, height = image.size
        # Keep the full width when the picture is wide enough, else crop height.
        crop = min(width, height * SIZE[0] // SIZE[1]), min(height, width * SIZE[1] // SIZE[0])
        left, top = (width - crop[0]) // 2, (height - crop[1]) // 2
        output = io.BytesIO()
        image.crop((left, top, left + crop[0], top + crop[1])).resize(SIZE, Image.LANCZOS).save(
            output, 'WEBP', quality=86, method=6)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('content_key')
    parser.add_argument('classroom', type=Path)
    parser.add_argument('--store', type=Path, help='classroom store holding the media (default: next to the JSON)')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--alt')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{64}', args.content_key):
        raise SystemExit('content key must be 64 hex characters')
    saved = json.loads(args.classroom.read_text(encoding='utf-8'))
    classroom = saved.get('release', saved).get('classroom', saved)
    store = args.store or args.classroom.parent
    picture, alt = (args.image, '') if args.image else first_slide_picture(classroom, store)
    alt = args.alt or alt or classroom['stage']['name']
    raw = cover(picture)
    name = f'{args.content_key[:16]}-{hashlib.sha256(raw).hexdigest()[:16]}.webp'
    PICTURES.mkdir(parents=True, exist_ok=True)
    (PICTURES / name).write_bytes(raw)
    text = LISTING.read_text(encoding='utf-8')
    listing = json.loads(text)
    previous = listing.get(args.content_key, {}).get('src', '')
    listing[args.content_key] = {'src': '/textbooks/course-pictures-v1/' + name, 'alt': alt,
                                 'width': SIZE[0], 'height': SIZE[1]}
    LISTING.write_text(json.dumps(listing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    stale = PICTURES / Path(previous).name if previous else None
    if stale and stale.name != name and stale.is_file():
        stale.unlink()
    print(json.dumps({'cover': name, 'bytes': len(raw), 'alt': alt, 'source': str(picture)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
