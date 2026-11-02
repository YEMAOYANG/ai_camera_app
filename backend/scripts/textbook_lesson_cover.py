"""Make the catalog cover of one published textbook lesson from its own picture.

Usage: textbook_lesson_cover.py <content-key> <classroom.json | prepared-release.json> [--store DIR] [--image FILE] [--alt TEXT]

By default the cover is the first picture on the lesson's first slide, centre
cropped to 16:9. It is written as a 960x540 WebP into Student Web's
`public/textbooks/course-pictures-v1/` and listed in
`src/features/learning/lesson-pictures.json`, so Student Web must be rebuilt
(restart the local stack) before the cover shows. A prepared release adds the
source and release hashes required for new publication. Nothing is generated.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from content.textbook_catalog import digest  # noqa: E402
from services.textbook_cover_guard import SIZE, cover_bytes  # noqa: E402

PICTURES = ROOT / 'student-web/public/textbooks/course-pictures-v1'
LISTING = ROOT / 'student-web/src/features/learning/lesson-pictures.json'
LOCK = ROOT / '.local_backups/textbook-cover-v1/registration.lock'


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
    return cover_bytes(picture.read_bytes())


def register_cover(content_key, raw, alt, provenance):
    """Serialize parallel registrations and retain prior referenced artwork."""
    cover_sha = hashlib.sha256(raw).hexdigest()
    name = f'{content_key[:16]}-{cover_sha[:16]}.webp'
    PICTURES.mkdir(parents=True, exist_ok=True)
    LOCK.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = PICTURES / name
        if target.exists():
            if target.read_bytes() != raw:
                raise SystemExit('existing cover filename has different bytes')
        else:
            with target.open('xb') as output:
                output.write(raw)
        listing = json.loads(LISTING.read_text(encoding='utf-8'))
        previous = listing.get(content_key)
        entry = {'src': '/textbooks/course-pictures-v1/' + name, 'alt': alt,
                 'width': SIZE[0], 'height': SIZE[1], **provenance,
                 **({'coverSha256': cover_sha} if provenance else {})}
        if previous and previous.get('src') != entry['src']:
            history = previous.get('previous', [])
            entry['previous'] = [*history, {k: v for k, v in previous.items() if k != 'previous'}]
        elif previous and previous.get('previous'):
            entry['previous'] = previous['previous']
        listing[content_key] = entry
        tmp = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=LISTING.parent,
                    prefix='.lesson-pictures-', delete=False) as output:
                tmp = Path(output.name)
                output.write(json.dumps(listing, ensure_ascii=False, indent=2) + '\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, LISTING)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    return name


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
    source_raw = picture.read_bytes()
    source_sha = hashlib.sha256(source_raw).hexdigest()
    release = saved.get('release')
    provenance = {}
    if release is not None:
        if (release.get('contentKey') != args.content_key
                or release.get('sha256') != digest({k: v for k, v in release.items() if k != 'sha256'})):
            raise SystemExit('prepared release identity does not match this content key')
        classroom_text = json.dumps(classroom, ensure_ascii=False)
        matches = [m for m in release.get('media', []) if m.get('sha256') == source_sha
                   and m.get('byteSize') == len(source_raw) and str(m.get('mimeType', '')).startswith('image/')
                   and m.get('path', '') in classroom_text]
        if len(matches) != 1:
            raise SystemExit('choose a picture referenced by this prepared release')
        provenance = {'sourceMediaPath': matches[0]['path'], 'sourceSha256': source_sha,
                      'releaseSha256': release['sha256']}
    raw = cover_bytes(source_raw)
    name = register_cover(args.content_key, raw, alt, provenance)
    print(json.dumps({'cover': name, 'bytes': len(raw), 'alt': alt, 'source': str(picture)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
