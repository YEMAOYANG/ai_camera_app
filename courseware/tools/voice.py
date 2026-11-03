import argparse
import base64
import hashlib
import json
import re
import struct
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class VoiceError(Exception):
    pass


# Seconds to wait before each retry; the speech service answers 429 when several lessons are voiced at once.
RETRY_DELAYS = (1, 4, 10, 25)


def default_post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.status, response.read()


def _wav_bytes(body):
    try:
        answer = json.loads(body)
        encoded = answer['data']['base64'] if 'data' in answer else answer['base64']
        return base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f'invalid TTS response: {exc}') from exc


def _validate_wav(data):
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise VoiceError('wav_invalid', 'expected RIFF/WAVE header')
    offset = 12
    fmt = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        size = struct.unpack_from('<I', data, offset + 4)[0]
        start = offset + 8
        if chunk_id == b'data':
            if fmt is None:
                break
            tag, channels, rate, _, _, bits = struct.unpack_from('<HHIIHH', fmt)
            if tag == 0xfffe:
                if len(fmt) < 40 or fmt[24:40] != bytes.fromhex('0100000000001000800000aa00389b71'):
                    raise VoiceError('wav_invalid', 'expected PCM subformat')
            elif tag != 1:
                raise VoiceError('wav_invalid', 'expected PCM format')
            if channels not in (1, 2) or not 8000 <= rate <= 48000 or bits != 16:
                raise VoiceError('wav_invalid', 'unsupported PCM format')
            payload = min(size, len(data) - start)
            frame_size = channels * 2
            if payload % frame_size or not 0.3 <= payload / (rate * frame_size) <= 60:
                raise VoiceError('wav_invalid', 'invalid PCM payload length or duration')
            return
        if start + size > len(data):
            break
        if chunk_id == b'fmt ':
            if size < 16:
                raise VoiceError('wav_invalid', 'truncated fmt chunk')
            fmt = data[start:start + size]
        offset = start + size + (size & 1)
    raise VoiceError('wav_invalid', 'missing fmt or data chunk')


def voice_lines(lines, media_dir, *, post, cache_path,
                endpoint='http://127.0.0.1:3100', jobs=4, sleep=time.sleep):
    voices = json.loads(Path(__file__).with_name('voices.json').read_text(encoding='utf-8'))
    allowed = {voice for group in voices.values() for voice in group}
    if not isinstance(lines, list) or not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise VoiceError('line_invalid', 'lines must be a list and jobs must be positive')
    seen = set()
    for line in lines:
        if not isinstance(line, dict):
            raise VoiceError('line_invalid', 'line must be an object')
        line_id, text, voice = line.get('id'), line.get('text'), line.get('voice')
        if (not isinstance(line_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', line_id)
                or line_id in seen or not isinstance(text, str) or not text.strip()):
            raise VoiceError('line_invalid', f'invalid or duplicate line: {line_id}')
        if not isinstance(voice, str) or voice not in allowed:
            raise VoiceError('voice_unknown', str(voice))
        seen.add(line_id)

    media_dir, cache_path = Path(media_dir), Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    files, pending = {}, []
    for line in lines:
        key = f"{line['id']}|{line['voice']}|{line['text']}"
        name = cache.get(key)
        pattern = rf"tts-{re.escape(line['id'])}-([0-9a-f]{{64}})\.wav"
        match = re.fullmatch(pattern, name) if isinstance(name, str) else None
        try:
            valid = match and hashlib.sha256((media_dir / name).read_bytes()).hexdigest() == match.group(1)
        except OSError:
            valid = False
        if valid:
            files[line['id']] = name
        else:
            pending.append((line, key))
    reused = len(files)

    def record(item):
        line, key = item
        payload = {'text': line['text'], 'audioId': line['id'],
                   'ttsProviderId': 'qwen-tts', 'ttsModelId': 'qwen3-tts-flash',
                   'ttsVoice': line['voice']}
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                status, body = post(endpoint.rstrip('/') + '/api/generate/tts', payload)
                if status != 200:
                    raise ValueError(f'HTTP {status}')
                data = _wav_bytes(body)
                _validate_wav(data)
                name = f"tts-{line['id']}-{hashlib.sha256(data).hexdigest()}.wav"
                media_dir.mkdir(parents=True, exist_ok=True)
                (media_dir / name).write_bytes(data)
                for old in media_dir.glob(f"tts-{line['id']}-*.wav"):
                    if old.name != name and re.fullmatch(
                            rf"tts-{re.escape(line['id'])}-[0-9a-f]{{64}}\.wav", old.name):
                        old.unlink()
                return key, name, None
            except Exception as exc:
                error = f'{exc.args[0]}: {exc.args[1]}' if isinstance(exc, VoiceError) else str(exc)
                if attempt < len(RETRY_DELAYS):
                    sleep(RETRY_DELAYS[attempt])
        return key, None, error

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        outcomes = list(executor.map(record, pending))
    failures = []
    for (line, _), (key, name, error) in zip(pending, outcomes):
        if error is not None:
            failures.append(f"{line['id']}: {error}")
        else:
            cache[key] = name
            files[line['id']] = name
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True, indent=1) + '\n', encoding='utf-8')
    if failures:
        raise VoiceError('tts_failed', '; '.join(failures))
    return {'voiced': len(pending), 'reused': reused,
            'files': {line['id']: files[line['id']] for line in lines}}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Record lesson lines as WAV clips')
    parser.add_argument('--lines', required=True)
    parser.add_argument('--media-dir', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:3100')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    try:
        try:
            lines = json.loads(Path(args.lines).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise VoiceError('line_invalid', str(exc)) from exc
        result = voice_lines(lines, args.media_dir, post=default_post, cache_path=args.cache,
                             endpoint=args.endpoint, jobs=args.jobs)
    except VoiceError as exc:
        print(f'{exc.args[0]}: {exc.args[1]}', file=sys.stderr)
        return 1
    print(f"voiced {result['voiced']}, reused {result['reused']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
