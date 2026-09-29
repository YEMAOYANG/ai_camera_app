"""Bundle only allowlisted original media; synthesize new directions locally."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from services.textbook_sample_service import LESSON, LESSON_HASH


def prepare(destination):
    release = json.loads((ROOT / 'output/textbook-publication-20260924/prepared-release.json').read_text())['release']
    if release['sha256'] != LESSON['provenance']['sourceReleaseSha256']:
        raise ValueError('Source release changed; review before preparing this sample.')
    source_root = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms'
    destination.mkdir(parents=True, exist_ok=True)
    assets_dir = destination / 'assets'
    assets_dir.mkdir(exist_ok=True)
    assets = {}

    def register(key, source, mime, expected=None, provenance=None):
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if expected and digest != expected:
            raise ValueError(f'Media hash mismatch: {key}')
        target = assets_dir / (digest + source.suffix)
        if target != source:
            shutil.copyfile(source, target)
        assets[key] = {'file': str(target.relative_to(destination)), 'sha256': digest, 'mimeType': mime,
                       'bytes': len(data), 'provenance': provenance or 'previously reviewed original lesson media'}
        if mime == 'audio/wav':
            with wave.open(str(target)) as audio:
                duration = audio.getnframes() / audio.getframerate()
                if duration < .2:
                    raise ValueError(f'Empty audio: {key}')
                assets[key]['durationSeconds'] = round(duration, 3)

    media = {m['path']: m for m in release['media']}
    for scene in release['classroom']['scenes']:
        for action in scene.get('actions', []):
            if action['type'] != 'speech':
                continue
            item = media[action['audioUrl']]
            source = source_root / item['path'].split('/api/classroom-media/')[1]
            register(action['id'], source, item['mimeType'], item['sha256'])
    art = json.loads((ROOT / 'backend/content/textbooks/lesson-media-v1/tiandiren.json').read_text())['assets'][0]
    register('garden', ROOT / 'backend/content/textbooks/lesson-media-v1' / art['file'], 'image/webp', art['sha256'], 'original imagegen illustration, 2026-09-24')
    voice_dir = destination / 'local-voice'
    voice_dir.mkdir(exist_ok=True)
    voice = 'Tingting (中文（中国大陆）)'
    for key, text in LESSON['spoken'].items():
        cache = hashlib.sha256((voice + ':145:' + text).encode()).hexdigest()
        aiff, wav = voice_dir / f'{cache}.aiff', voice_dir / f'{cache}.wav'
        cached = False
        if wav.exists():
            with wave.open(str(wav)) as existing:
                cached = existing.getnframes() / existing.getframerate() >= .2
        if not cached:
            subprocess.run(['say', '-v', voice, '-r', '145', '-o', str(aiff), text], check=True, capture_output=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(aiff), '-ar', '24000', '-ac', '1', str(wav)], check=True, capture_output=True)
        register(key, wav, 'audio/wav', provenance={'engine': 'macOS local speech', 'voice': voice, 'text': text, 'formalVoiceReview': 'pending'})
    manifest = {'schemaVersion': 'mira.textbook.sample-assets.v1', 'lessonHash': LESSON_HASH, 'assets': assets,
                'originalAudioCount': sum(m['provenance'] == 'previously reviewed original lesson media' for m in assets.values()),
                'newLocalAudioCount': len(LESSON['spoken']), 'publicationAllowed': False}
    (destination / 'assets.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'bundle': str(destination), 'assets': len(assets), 'localVoice': len(LESSON['spoken']), 'paidCalls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/tiandiren-play-v2')
    prepare(parser.parse_args().output.resolve())
