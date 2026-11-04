"""Put a built lesson into the local OpenMAIC player so it can be played BEFORE anything is published.

The lesson's media are copied next to the saved classroom (hash names are verified first) and the classroom is saved
through the runtime's own save route. Nothing here touches the database, the student catalogue or MinIO, and a lesson
that is already staged under the same stage id is never overwritten with different bytes.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


class PreviewError(Exception):
    pass


def default_post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _retarget(value, source, target):
    if isinstance(value, dict):
        return {key: (target if key == 'stageId' and item == source else _retarget(item, source, target))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_retarget(item, source, target) for item in value]
    if isinstance(value, str):
        return value.replace(f'/api/classroom-media/{source}/', f'/api/classroom-media/{target}/')
    return value


def stage_preview(build_dir, classrooms_dir, *, endpoint='http://127.0.0.1:3100', post=default_post,
                  stage_id=None):
    build, classrooms = Path(build_dir), Path(classrooms_dir)
    try:
        body = json.loads((build / 'body.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PreviewError('body_unreadable', str(exc)) from exc
    source_stage = body.get('stage', {}).get('id')
    stage = source_stage if stage_id is None else stage_id
    if (not isinstance(source_stage, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', source_stage)
            or not isinstance(stage, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', stage)):
        raise PreviewError('stage_id_invalid', repr(stage))
    if stage != source_stage:
        body = _retarget(body, source_stage, stage)
        body['stage']['id'] = stage
        if source_stage in json.dumps(body, ensure_ascii=False):
            raise PreviewError('stage_retarget_incomplete', source_stage)
    text = json.dumps(body, ensure_ascii=False)
    names = sorted(set(re.findall(r'/api/classroom-media/' + re.escape(stage) + r'/media/([A-Za-z0-9_.\-]+)', text)))
    target = classrooms / stage / 'media'
    for name in names:
        source = build / 'media' / name
        if not source.is_file():
            raise PreviewError('media_missing', name)
        data = source.read_bytes()
        claimed = re.search(r'([0-9a-f]{64})', name)
        if claimed and hashlib.sha256(data).hexdigest() != claimed.group(1):
            raise PreviewError('media_hash_mismatch', name)
        if (target / name).exists() and (target / name).read_bytes() != data:
            raise PreviewError('media_conflict', name)
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        if not (target / name).exists():
            shutil.copyfile(build / 'media' / name, target / name)
    status, answer = post(endpoint.rstrip('/') + '/api/classroom', {'stage': body['stage'], 'scenes': body['scenes']})
    if not 200 <= status < 300:
        raise PreviewError('save_failed', f'HTTP {status}: {answer[:200]!r}')
    return {'stage': stage, 'media': len(names), 'url': f'http://localhost:3100/classroom/{stage}'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, help="the lane's work folder (body.json and media/)")
    parser.add_argument('--classrooms', required=True, help='the runtime data folder that holds the saved classrooms')
    parser.add_argument('--endpoint', default='http://127.0.0.1:3100')
    parser.add_argument('--stage-id', help='new immutable preview id when the build id was already staged')
    args = parser.parse_args(argv)
    try:
        result = stage_preview(args.build, args.classrooms, endpoint=args.endpoint, stage_id=args.stage_id)
    except PreviewError as exc:
        print(f'PreviewError: {exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    print(f"media copied: {result['media']} files\nplay: {result['url']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
