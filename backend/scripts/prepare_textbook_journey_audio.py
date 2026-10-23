"""Prepare shared narration using OpenMAIC's existing Chinese teacher TTS.

Operator-only: every paid request has a frozen identity and a durable checkpoint.
Interrupted/ambiguous calls are reconciled, never automatically resubmitted.
The active manifest changes only after the entire voice pack has been verified.
"""
import argparse
import concurrent.futures
import fcntl
import hashlib
import io
import json
from pathlib import Path
import wave
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content import textbook_journey as journey
from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import digest
from core.config import AppConfig
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError

WORK = Path(__file__).resolve().parents[2] / 'output/textbook-journey-audio-20260929'


def texts(*, plan=None, flow=None):
    plan = journey.PLAN if plan is None else plan
    flow = journey.FLOW if flow is None else flow
    values = set()
    for bank in list(flow['bank'].values()) + [[p] for p in flow['probes'].values()]:
        for q in bank:
            values.add(q['prompt'] + ''.join(o['value'] + '，' + o['label'] + '。' for o in q['options']))
            values.update(q['hints'])
            values.add(q['explanation'])
    for skill, value in plan['skills'].items():
        prompt = f'把“{value["word"]}”送到图里。'
        if skill in ('me', 'you', 'he'):
            for lead in ('蓝衣男孩在说话，红衣女孩在听。', '红衣女孩在说话，蓝衣男孩在听。'):
                values.add(lead + prompt)
        else:
            values.add(prompt)
        values.update(value['hints'])
        values.add(value['explanation'])
    return values


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def validate_audio(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Audio differs from the original TTS receipt')
    with wave.open(io.BytesIO(data)) as clip:
        duration = clip.getnframes() / clip.getframerate()
        if not .3 < duration < 120 or clip.getnchannels() != 1 or clip.getsampwidth() != 2:
            raise ValueError('Invalid teacher narration WAV')
    return round(duration, 3)


def request_id(frozen, text):
    return 'tbjourney_' + digest({'plan': digest(frozen), 'text': text})


def active_request_id(work, frozen, text):
    original = request_id(frozen, text)
    repair = work / (original + '.repair.json')
    if not repair.exists():
        return original
    evidence = json.loads(repair.read_text())
    if (evidence['original']['requestId'] != original or evidence['original']['state'] != 'failed'
            or evidence['original']['safeErrorCode'] != 'provider_rejected'
            or evidence['requestId'] != original + '_repair1'):
        raise ValueError('Invalid controlled repair evidence')
    return evidence['requestId']


def prepare_failed_repair(runtime, work, frozen, identity):
    authored = {request_id(frozen, text): text for text in frozen['texts']}
    if identity not in authored:
        raise ValueError('Repair must belong to this exact narration pack')
    # Operator opt-in only. A provider rejection is definitive; timeout or an
    # ambiguous outcome never authorizes another paid synthesis.
    original = runtime._request_formal_audio_json('GET', '/api/mira/formal-audio/tts?requestId=' + identity)
    if (original.get('requestId') != identity or original.get('state') != 'failed'
            or original.get('safeErrorCode') != 'provider_rejected'
            or original.get('textSha256') != hashlib.sha256(authored[identity].encode()).hexdigest()
            or original.get('classroomContentSha256') != digest(frozen)):
        raise ValueError('Original provider rejection is not proven; no repair dispatched')
    target = work / (identity + '.repair.json')
    evidence = {'requestId': identity + '_repair1', 'original': original}
    if target.exists() and json.loads(target.read_text()) != evidence:
        raise ValueError('Original repair evidence changed')
    save(target, evidence)


def synthesize_one(runtime, work, frozen, teacher, text):
    identity = active_request_id(work, frozen, text)
    checkpoint = work / (identity + '.json')
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    wav = work / (identity + '.wav')
    if previous and previous.get('receipt', {}).get('status') == 'succeeded' and wav.exists():
        validate_audio(wav.read_bytes(), previous['receipt']['audioSha256'])
        return identity
    try:
        receipt = runtime.get_formal_audio_tts(identity)
    except OpenMaicFullRuntimeError as exc:
        if exc.status_code != 404:
            raise
        if previous:
            raise RuntimeError(f'Uncertain prior dispatch: {identity}; reconcile before continuing') from exc
        save(checkpoint, {'requestId': identity, 'state': 'dispatching'})
        segment = journey.audio_id(text)
        receipt = runtime.start_formal_audio_tts(
            request_id=identity, classroom_id='tbjourney_' + digest(frozen)[:32],
            classroom_content_sha256=digest(frozen), subject='chinese',
            teacher_profile_id=teacher.teacher_profile_id, teacher_profile_version=teacher.teacher_profile_version,
            teacher_profile_sha256=teacher.teacher_profile_hash, teacher_gender=teacher.teacher_gender,
            scene_id='journey-narration', scene_order=0, action_id=segment, narration_segment_id=segment,
            text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
    save(checkpoint, {'requestId': identity, 'receipt': receipt})
    if receipt['status'] != 'succeeded':
        raise RuntimeError(f"Original TTS job is {receipt['status']}: {identity}; no retry dispatched")
    audio = runtime.download_formal_audio_tts(identity, expected_sha256=receipt['audioSha256'])
    duration = validate_audio(audio, receipt['audioSha256'])
    temporary = wav.with_suffix('.tmp')
    temporary.write_bytes(audio)
    temporary.replace(wav)
    save(checkpoint, {'requestId': identity, 'receipt': receipt, 'durationSeconds': duration})
    return identity


def compile_pack(work, frozen, folder):
    # Versioned files make the final manifest replacement atomic for live readers.
    pack_name = 'qwen-' + digest(frozen)[:16]
    pack = folder / pack_name
    pack.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for text in frozen['texts']:
        identity = active_request_id(work, frozen, text)
        record = json.loads((work / (identity + '.json')).read_text())
        receipt = record['receipt']
        if receipt['status'] != 'succeeded':
            raise ValueError('Cannot install a partially synthesized voice pack')
        data = (work / (identity + '.wav')).read_bytes()
        duration = validate_audio(data, receipt['audioSha256'])
        name = journey.audio_id(text) + '.wav'
        (pack / name).write_bytes(data)
        manifest[name] = {'text': text, 'file': f'{pack_name}/{name}', 'sha256': receipt['audioSha256'],
            'bytes': len(data), 'durationSeconds': duration, 'requestId': identity,
            'voice': frozen['teacher']['voiceId'], 'providerId': frozen['teacher']['tts']['providerId'],
            'modelId': frozen['teacher']['tts']['modelId'], 'teacher': frozen['teacher']['teacherProfile'],
            'fallbackUsed': False}
    save(folder / 'manifest.json', manifest)
    return len(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthesize', action='store_true')
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=2)
    parser.add_argument('--repair-failed', action='append', default=[], help='Explicitly repair one proven provider rejection once')
    args = parser.parse_args()
    if not args.synthesize and not args.compile:
        parser.error('choose --synthesize and/or --compile')
    teacher = get_formal_subject_qwen_voice_identity('chinese')
    frozen = {'schemaVersion': 'mira.textbook.journey-audio.v1',
        'teacher': teacher.to_target_payload(), 'texts': sorted(texts())}
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / 'operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = WORK / 'plan.json'
        if plan.exists():
            if json.loads(plan.read_text()) != frozen:
                raise ValueError('Narration or teacher identity changed after dispatch; use a new pack version')
        else:
            save(plan, frozen)
        if args.synthesize:
            config = AppConfig.from_env()
            runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                formal_audio_internal_token=config.INTERNAL_API_TOKEN)
            for identity in args.repair_failed:
                prepare_failed_repair(runtime, WORK, frozen, identity)
            # Produce the reported question first; all later runs reuse its receipt.
            ordered = sorted(frozen['texts'], key=lambda t: (journey.audio_id(t) != 'f7d49ffe41b0dde3e18b789c', t))
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                jobs = [pool.submit(synthesize_one, runtime, WORK, frozen, teacher, text) for text in ordered]
                try:
                    for n, job in enumerate(concurrent.futures.as_completed(jobs), 1):
                        identity = job.result()
                        print(json.dumps({'completed': n, 'total': len(jobs), 'requestId': identity}), flush=True)
                except Exception:
                    for job in jobs:
                        job.cancel()
                    raise
        if args.compile:
            total = compile_pack(WORK, frozen, journey.ROOT / 'audio-v2')
            print(json.dumps({'installed': total, 'voice': teacher.voice_id, 'model': teacher.tts_model_id}), flush=True)

if __name__ == '__main__':
    main()
