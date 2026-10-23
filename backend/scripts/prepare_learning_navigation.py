"""Build an original picture navigation pack with the existing Qwen teacher.

Reuses durable formal-audio receipts. Does not retry an ambiguous paid request.
Only installs the public manifest after every WAV has been verified.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import digest
from core.config import AppConfig
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from scripts.prepare_textbook_journey_audio import save, synthesize_one, compile_pack
from content.textbook_journey import audio_id

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backend/content/learning_navigation.v1.json'
WORK = ROOT / 'output/learning-navigation-audio-v1'
PUBLIC = ROOT / 'student-web/public/textbooks/navigation-v1'
TARGET = ROOT / 'backend/content/textbooks/activities/navigation-audio-v1'


def texts(source):
    return set(source['cues'].values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthesize', action='store_true')
    args = parser.parse_args()
    source = json.loads(SOURCE.read_text())
    teacher = get_formal_subject_qwen_voice_identity('chinese')
    frozen = {'schemaVersion': source['schemaVersion'], 'teacher': teacher.to_target_payload(),
              'texts': sorted(texts(source))}
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / 'operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = WORK / 'plan.json'
        if plan.exists() and json.loads(plan.read_text()) != frozen:
            raise ValueError('Frozen narration changed; create a new pack version')
        save(plan, frozen)
        if args.synthesize:
            config = AppConfig.from_env()
            runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                formal_audio_internal_token=config.INTERNAL_API_TOKEN)
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(synthesize_one, runtime, WORK, frozen, teacher, text) for text in frozen['texts']]
                try:
                    for n, job in enumerate(as_completed(jobs), 1):
                        job.result()
                        print(json.dumps({'verified': n, 'total': len(jobs)}), flush=True)
                except Exception:
                    for job in jobs:
                        job.cancel()
                    raise
        compile_pack(WORK, frozen, TARGET)
        manifest = json.loads((TARGET / 'manifest.json').read_text())
        PUBLIC.mkdir(parents=True, exist_ok=True)
        cues = {}
        for name, text in source['cues'].items():
            asset = audio_id(text) + '.wav'
            record = manifest[asset]
            shutil.copyfile(TARGET / record['file'], PUBLIC / asset)
            cues[name] = {'text': text, 'src': f'/textbooks/navigation-v1/{asset}',
                         'sha256': record['sha256'], 'durationSeconds': record['durationSeconds']}
        save(ROOT / 'student-web/src/features/learning/navigation-audio.json',
             {'schemaVersion': source['schemaVersion'], 'planSha256': digest(frozen),
              'voice': teacher.voice_id, 'cues': cues})
        print(json.dumps({'installed': len(cues), 'voice': teacher.voice_id}), flush=True)


if __name__ == '__main__':
    main()
