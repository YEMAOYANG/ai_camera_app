import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


class PictureError(Exception):
    pass


def default_post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.status, response.read()


def default_fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, response.read()


def _png(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if min(image.size) < 256:
                raise ValueError('image must be at least 256 x 256')
            image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue(), image.width / image.height
    except Exception as exc:
        raise PictureError('image_invalid', str(exc)) from exc


def _image_bytes(body, fetch):
    try:
        answer = json.loads(body)
        if not isinstance(answer, dict):
            raise ValueError('response must be an object')
        if answer.get('success') is not True:
            raise ValueError(str(answer.get('error', 'image generation failed')))
        result = answer['result']
        if 'base64' in result:
            try:
                return base64.b64decode(result['base64'], validate=True)
            except (ValueError, TypeError) as exc:
                raise PictureError('image_invalid', str(exc)) from exc
        url = result['url']
        if not isinstance(url, str) or urlparse(url).scheme.lower() not in ('http', 'https') or not urlparse(url).netloc:
            raise PictureError('image_invalid', 'invalid image URL')
        status, data = fetch(url)
        if status != 200:
            raise ValueError(f'HTTP {status}')
        return data
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'invalid image response: {exc}') from exc


def generate_pictures(requests, assets_dir, *, post, fetch, cache_path,
                      endpoint='http://127.0.0.1:3100', jobs=2, sleep=time.sleep):
    if not isinstance(requests, list) or not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise PictureError('request_invalid', 'requests must be a list and jobs must be positive')
    seen = set()
    for request in requests:
        if not isinstance(request, dict):
            raise PictureError('request_invalid', 'request must be an object')
        key, prompt, aspect = request.get('key'), request.get('prompt'), request.get('aspect', '16:9')
        if (set(request) - {'key', 'prompt', 'aspect'} or not isinstance(key, str)
                or not re.fullmatch(r'[a-z0-9-]+', key) or key in seen
                or not isinstance(prompt, str) or not prompt.strip()
                or aspect not in ('16:9', '4:3', '1:1', '3:4', '9:16')):
            raise PictureError('request_invalid', f'invalid or duplicate request: {key}')
        seen.add(key)

    style = (Path(__file__).parent / 'prompts' / 'picture_style.v1.md').read_text(encoding='utf-8').strip()
    assets_dir, cache_path = Path(assets_dir), Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    files, aspects, pending = {}, {}, []
    for request in requests:
        key = request['key']
        aspect = request.get('aspect', '16:9')
        fingerprint = hashlib.sha256(json.dumps([style, request['prompt'], aspect], ensure_ascii=False).encode('utf-8')).hexdigest()
        entry = cache.get(key)
        try:
            data = (assets_dir / f'{key}.png').read_bytes()
            valid = (isinstance(entry, dict) and entry.get('fingerprint') == fingerprint
                     and entry.get('file') == f'{key}.png'
                     and entry.get('sha256') == hashlib.sha256(data).hexdigest())
            if valid:
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
                    aspects[key] = image.width / image.height
        except (OSError, ValueError, ZeroDivisionError):
            valid = False
        if valid:
            files[key] = f'assets/{key}.png'
        else:
            cache.pop(key, None)
            pending.append((request, fingerprint))
    reused = len(files)

    def record(item):
        request, fingerprint = item
        key = request['key']
        payload = {'prompt': style + '\n' + request['prompt'], 'aspectRatio': request.get('aspect', '16:9')}
        for attempt in range(3):
            try:
                status, body = post(endpoint.rstrip('/') + '/api/generate/image', payload)
                if status != 200:
                    raise ValueError(f'HTTP {status}')
                data, aspect = _png(_image_bytes(body, fetch))
                assets_dir.mkdir(parents=True, exist_ok=True)
                name = f'{key}.png'
                path = None
                try:
                    with tempfile.NamedTemporaryFile(dir=assets_dir, delete=False) as stream:
                        path = stream.name
                        stream.write(data)
                    os.replace(path, assets_dir / name)
                finally:
                    if path and os.path.exists(path):
                        os.unlink(path)
                return {'fingerprint': fingerprint, 'file': name,
                        'sha256': hashlib.sha256(data).hexdigest()}, aspect, None
            except Exception as exc:
                error = f'{exc.args[0]}: {exc.args[1]}' if isinstance(exc, PictureError) else str(exc)
                if 'SensitiveContent' in error or 'sensitive information' in error.lower():
                    break
                if attempt < 2:
                    sleep(2 ** attempt)
        return None, None, error

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        outcomes = list(executor.map(record, pending))
    failures = []
    for (request, _), (entry, aspect, error) in zip(pending, outcomes):
        key = request['key']
        if error is not None:
            failures.append(f'{key}: {error}')
        else:
            cache[key] = entry
            files[key] = f'assets/{key}.png'
            aspects[key] = aspect
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True, indent=1) + '\n', encoding='utf-8')
    if failures:
        raise PictureError('image_failed', '; '.join(failures))
    return {'made': len(pending), 'reused': reused,
            'files': {request['key']: files[request['key']] for request in requests},
            'aspects': {request['key']: aspects[request['key']] for request in requests}}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate lesson pictures as PNG files')
    parser.add_argument('--requests', required=True)
    parser.add_argument('--assets', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:3100')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        try:
            requests = json.loads(Path(args.requests).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise PictureError('request_invalid', str(exc)) from exc
        result = generate_pictures(requests, args.assets, post=default_post, fetch=default_fetch,
                                   cache_path=args.cache, endpoint=args.endpoint, jobs=args.jobs)
    except PictureError as exc:
        print(f'{exc.args[0]}: {exc.args[1]}', file=sys.stderr)
        return 1
    print(f"made {result['made']}, reused {result['reused']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
