"""Prepare an exact preview binding or explicitly save a built lesson to OpenMAIC.

Use --binding-only to write a private expectation for browser verification without contacting or writing to the
runtime. The file identifies the expected classroom and does not create a playable preview.
The existing --classrooms mode copies media and POSTs to the runtime's save route. If runtime archiving is enabled,
that save can enqueue the classroom and media for upload to the configured MinIO bucket. Use a fresh preview alias.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager, nullcontext
from pathlib import Path


class PreviewError(Exception):
    pass


PREVIEW_BINDING_SCHEMA = 'mira.courseware.preview-binding.v1'
NATIVE_ENDPOINT = 'http://127.0.0.1:3100'
RUNTIME_ROOT = Path(__file__).resolve().parents[2] / 'openmaic-runtime'


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


def _prepare_preview(build, stage_id, *, bind):
    try:
        raw = (build / 'body.json').read_bytes()
        body = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError) as exc:
        raise PreviewError('body_unreadable', str(exc)) from exc
    source_stage = body.get('stage', {}).get('id')
    stage = source_stage if stage_id is None else stage_id
    if (not isinstance(source_stage, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', source_stage)
            or not isinstance(stage, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', stage)):
        raise PreviewError('stage_id_invalid', repr(stage))
    binding = None
    if bind:
        from courseware.tools.check import body_hash

        if stage_id is None or stage == source_stage or stage.startswith(('tbpub_', 'tbprev_', 'omclass_')):
            raise PreviewError('binding_alias_invalid', 'Use a fresh direct preview alias distinct from the build id')
        binding = {'schemaVersion': PREVIEW_BINDING_SCHEMA, 'classroomId': stage,
                   'bodyFileSha256': hashlib.sha256(raw).hexdigest(), 'bodySha256': body_hash(body)}
    if stage != source_stage:
        body = _retarget(body, source_stage, stage)
        body['stage']['id'] = stage
        if source_stage in json.dumps(body, ensure_ascii=False):
            raise PreviewError('stage_retarget_incomplete', source_stage)
    text = json.dumps(body, ensure_ascii=False)
    names = sorted(set(re.findall(r'/api/classroom-media/' + re.escape(stage) + r'/media/([A-Za-z0-9_.\-]+)', text)))
    projection = {'stage': body['stage'], 'scenes': body['scenes']}
    if binding is not None:
        binding['projection'] = projection
    return stage, projection, names, binding


def _check_media(build, names, target=None):
    for name in names:
        source = build / 'media' / name
        if not source.is_file():
            raise PreviewError('media_missing', name)
        data = source.read_bytes()
        claimed = re.search(r'([0-9a-f]{64})', name)
        if claimed and hashlib.sha256(data).hexdigest() != claimed.group(1):
            raise PreviewError('media_hash_mismatch', name)
        if target is not None and (target / name).exists() and (target / name).read_bytes() != data:
            raise PreviewError('media_conflict', name)


@contextmanager
def _binding_output(path, binding):
    try:
        stream = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=Path(path).parent)
    except OSError as exc:
        raise PreviewError('binding_output_invalid', 'The private binding parent must be writable') from exc
    with stream:
        try:
            json.dump(binding, stream, ensure_ascii=False)
            stream.flush()
        except OSError as exc:
            raise PreviewError('binding_output_failed', 'Could not write the private preview binding') from exc
        yield
        try:
            os.link(stream.name, path)
        except OSError as exc:
            raise PreviewError('binding_output_failed', 'Could not write the private preview binding') from exc


def write_preview_binding(build_dir, *, stage_id, binding_out):
    """Write an expected binding in a private local directory without staging a classroom."""
    build = Path(build_dir)
    stage, _, names, binding = _prepare_preview(build, stage_id, bind=True)
    path = Path(binding_out)
    try:
        parent = path.parent.resolve(strict=True)
        info = parent.stat()
    except OSError as exc:
        raise PreviewError('binding_output_invalid', 'Use an existing private output directory') from exc
    if (not parent.is_dir() or info.st_mode & 0o077 or info.st_uid != os.getuid()
            or parent.is_relative_to(RUNTIME_ROOT.resolve())):
        raise PreviewError('binding_output_invalid', 'Use a private output directory outside the runtime')
    path = parent / path.name
    if os.path.lexists(path):
        raise PreviewError('binding_output_invalid', 'Use a new private binding file')
    _check_media(build, names)
    with _binding_output(path, binding):
        pass
    return stage


def stage_preview(build_dir, classrooms_dir, *, endpoint=NATIVE_ENDPOINT, post=default_post,
                  stage_id=None, binding_out=None):
    build, classrooms = Path(build_dir), Path(classrooms_dir)
    stage, projection, names, binding = _prepare_preview(build, stage_id, bind=binding_out is not None)
    alias_dir, alias_file = classrooms / stage, classrooms / f'{stage}.json'
    if binding is not None:
        if os.path.lexists(alias_dir) or os.path.lexists(alias_file):
            raise PreviewError('binding_alias_conflict', 'The direct preview alias already exists locally')
        if os.path.lexists(binding_out):
            raise PreviewError('binding_output_invalid', 'Use a new private binding file')
    target = alias_dir / 'media'
    _check_media(build, names, target)
    with (_binding_output(binding_out, binding) if binding is not None else nullcontext()):
        if binding is not None:
            # Reserve the alias directory before any copy in verified mode.
            try:
                alias_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError as exc:
                raise PreviewError('binding_alias_conflict', 'The direct preview alias already exists locally') from exc
        target.mkdir(parents=True, exist_ok=True)
        for name in names:
            if not (target / name).exists():
                shutil.copyfile(build / 'media' / name, target / name)
        if binding is not None and os.path.lexists(alias_file):
            raise PreviewError('binding_alias_conflict', 'The direct preview alias already exists locally')
        status, answer = post(endpoint.rstrip('/') + '/api/classroom', projection)
        if not 200 <= status < 300:
            raise PreviewError('save_failed', f'HTTP {status}: {answer[:200]!r}')
    return {'stage': stage, 'media': len(names), 'url': f'http://localhost:3100/classroom/{stage}'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, help="the lane's work folder (body.json and media/)")
    parser.add_argument('--binding-only', action='store_true', help='write only the private browser binding')
    parser.add_argument('--classrooms', help='explicitly save to this runtime data folder; can trigger configured archiving')
    parser.add_argument('--endpoint', help=f'native save endpoint (default: {NATIVE_ENDPOINT})')
    parser.add_argument('--stage-id', help='fresh preview id when the build id was already staged')
    parser.add_argument('--binding-out', help='new private temporary file for verified browser playback')
    args = parser.parse_args(argv)
    if args.binding_only:
        if args.classrooms is not None or args.endpoint is not None:
            parser.error('--binding-only cannot be combined with --classrooms or --endpoint')
        if not args.stage_id or not args.binding_out:
            parser.error('--binding-only requires --stage-id and --binding-out')
    elif args.classrooms is None:
        parser.error('choose --binding-only or specify --classrooms for an explicit runtime save')
    try:
        if args.binding_only:
            stage = write_preview_binding(args.build, stage_id=args.stage_id, binding_out=args.binding_out)
            print(f'Private preview binding written for {stage}')
            return 0
        endpoint = NATIVE_ENDPOINT if args.endpoint is None else args.endpoint
        result = stage_preview(args.build, args.classrooms, endpoint=endpoint, stage_id=args.stage_id,
                               binding_out=args.binding_out)
    except PreviewError as exc:
        print(f'PreviewError: {exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    print(f"media copied: {result['media']} files\nplay: {result['url']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
