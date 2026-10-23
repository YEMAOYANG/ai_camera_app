"""Optional same-WAV ASR lane. prepare is provider-free; run dispatches at most once.

Explicit original library and managed history roots are required. Never changes
the classroom, original receipts, old audit/recheck files or publication state.

--failed-recovery-selection is an explicit list of sceneId, actionId,
failedRequestId, sourceSha256, planSha256, audioSha256, failedJobSha256 and
failedCacheSha256. --routine-cache-directory retains the original failed bytes.
Only terminal provider_rejected routines with no transcript qualify. Their one
domain-separated recovery consumes the second and final PCM attempt.
--recover-failures-only saves recovered-origins.json without collecting other
targets or producing a complete/passed audit. prepare never calls a provider.
"""
import argparse
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.textbook_catalog import digest
from content.textbook_asr_source_reuse import (target_evidence, verify_origin_library, validate_audit,
    build_failed_recovery_origin, FAILED_RECOVERY_SELECTION_FIELDS, LIBRARY_SCHEMA_V2, sha)
from services.textbook_asr_source_reuse import read, immutable, PcmLedger, collect, recover_failed_origins
from services.textbook_preview_audio import verify_segment_receipt
from core.config import AppConfig
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient


def prepare(classroom_path, audio_directory, library_path, source_sha):
    classroom = read(classroom_path); folder = Path(audio_directory)
    if digest(classroom) != source_sha: raise RuntimeError('Current source changed')
    plan = read(folder / 'textbook-preview-audio/plan.json')
    receipts = read(folder / 'textbook-preview-audio/receipts.json')
    by_id = {r['requestId']: r for r in receipts}
    if len(by_id) != len(receipts): raise RuntimeError('Duplicate TTS receipt identity')
    targets = []
    for scene in classroom['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') != 'speech': continue
            receipt = by_id[action['audioId']]
            verify_segment_receipt(plan, receipt, scene, action, folder / 'textbook-preview-audio')
            child = None
            if receipt.get('narrationRevisionId') is not None:
                child = read(folder / 'textbook-preview-audio/narration-revisions' / receipt['narrationRevisionId'] / 'plan.json')
            target = {'sceneId': scene['id'], 'sceneOrder': scene.get('order', 0), 'action': action,
                'ttsReceipt': receipt, 'requestPlan': child,
                'audioBase64': base64.b64encode((folder / 'audio' / (action['audioId'] + '.wav')).read_bytes()).decode()}
            target_evidence(target, plan); targets.append(target)
    library = read(library_path)
    verify_origin_library(library, plan)
    return plan, classroom, targets, library


def prepare_failed_recoveries(*, selection, plan, classroom, targets, native_audio_directory, routine_cache_directory):
    """Read exact original files; no retries, relabelling, or provider calls."""
    if not isinstance(selection, list) or not selection:
        raise RuntimeError('Failed recovery requires a nonempty exact selection')
    result, seen = [], set()
    by_key = {(t['sceneId'], t['action']['id']): t for t in targets}
    for item in selection:
        if not isinstance(item, dict) or set(item) != FAILED_RECOVERY_SELECTION_FIELDS:
            raise RuntimeError('Invalid failed-recovery selection fields')
        key = item['sceneId'], item['actionId']
        if key in seen or key not in by_key:
            raise RuntimeError('Duplicate or unknown failed-recovery target')
        seen.add(key)
        rid = item['failedRequestId']
        if not isinstance(rid, str) or not rid.startswith('tbpasr1_') or len(rid) != 72 or any(c not in '0123456789abcdef' for c in rid[8:]):
            raise RuntimeError('Invalid original failed request identity')
        job = Path(native_audio_directory) / 'jobs/asr' / (sha(rid.encode()) + '.json')
        cache = Path(routine_cache_directory) / (rid + '.json')
        if job.is_symlink() or cache.is_symlink(): raise RuntimeError('Original failure evidence cannot be symlinked')
        result.append(build_failed_recovery_origin(source=by_key[key], plan=plan, classroom=classroom,
            selection=item, failed_job_raw=job.read_bytes(), failed_cache_raw=cache.read_bytes()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--classroom', type=Path, required=True)
    parser.add_argument('--audio-directory', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--origin-library', type=Path, required=True)
    parser.add_argument('--native-audio-directory', type=Path, required=True)
    parser.add_argument('--probe-history-root', type=Path, action='append', required=True)
    parser.add_argument('--recheck-selection', type=Path, help='Exact sceneId/actionId/reason list; one per PCM maximum')
    parser.add_argument('--failed-recovery-selection', type=Path,
        help='Explicit original failed request with source/plan/WAV/job/cache SHA fences; one recovery per PCM')
    parser.add_argument('--routine-cache-directory', type=Path,
        help='Original immutable raw ASR cache directory; required for failed recovery')
    parser.add_argument('--recover-failures-only', action='store_true',
        help='Recover only explicitly selected failures; save a separate origin library, never a full or passed audit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if bool(args.failed_recovery_selection) != bool(args.routine_cache_directory):
        parser.error('failed recovery requires both --failed-recovery-selection and --routine-cache-directory')
    if args.recover_failures_only and (not args.failed_recovery_selection or args.recheck_selection):
        parser.error('--recover-failures-only requires failed selection and cannot request independent rechecks')
    plan, classroom, targets, library = prepare(args.classroom, args.audio_directory, args.origin_library, args.source_sha256)
    recoveries = prepare_failed_recoveries(selection=read(args.failed_recovery_selection), plan=plan,
        classroom=classroom, targets=targets, native_audio_directory=args.native_audio_directory,
        routine_cache_directory=args.routine_cache_directory) if args.failed_recovery_selection else []
    selection = read(args.recheck_selection) if args.recheck_selection else []
    if (not isinstance(selection, list) or any(not isinstance(x, dict) or set(x) != {'sceneId', 'actionId', 'reason'}
            or not isinstance(x['reason'], str) or not x['reason'].strip() for x in selection)):
        raise RuntimeError('Recheck selection must have explicit original discrepancy reasons')
    scope = {'schemaVersion': 'mira.textbook.asr-origin-collection.v1', 'sourceSha256': args.source_sha256,
        'planSha256': digest(plan), 'targetsSha256': digest(targets), 'originLibrarySha256': digest(library),
        'nativeAudioDirectory': str(args.native_audio_directory.resolve()),
        'probeHistoryRoots': [str(p.resolve()) for p in args.probe_history_root], 'selection': selection,
        'maximumRoutineCallsPerPcm': 1, 'maximumRechecksPerPcm': 1, 'unknownConsumesAttempt': True}
    if recoveries:
        scope.update(failedRecoveries=[o['failureRecovery'] for o in recoveries],
                     maximumTotalAttemptsPerPcm=2, recoveryConsumesRecheckBudget=True)
    if args.recover_failures_only: scope['recoverFailuresOnly'] = True
    immutable(args.output / 'intent.json', scope)
    ledger = PcmLedger(args.audio_directory.resolve().parent, args.native_audio_directory, args.probe_history_root,
                       routine_cache_directory=args.routine_cache_directory)
    if args.mode == 'prepare':
        if args.recover_failures_only:
            recover_failed_origins(plan=plan, classroom=classroom, origins=recoveries, ledger=ledger)
        print(json.dumps({'prepared': True, 'targets': len(targets), 'intentSha256': digest(scope), 'providerCalls': 0})); return
    config = AppConfig.from_env()
    client = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
        formal_audio_internal_token=config.INTERNAL_API_TOKEN)
    if args.recover_failures_only:
        recovered = recover_failed_origins(plan=plan, classroom=classroom, origins=recoveries, ledger=ledger, client=client)
        immutable(args.output / 'recovered-origins.json', {'schemaVersion': LIBRARY_SCHEMA_V2,
            'origins': recovered, 'probeProtocol': None})
        print(json.dumps({'recoveredOrigins': len(recovered), 'completeAuditProduced': False,
                          'publicationAllowed': False})); return
    audit = collect(plan=plan, classroom=classroom, targets=targets, library=library, ledger=ledger, client=client,
        recheck_keys=[(x['sceneId'], x['actionId']) for x in selection], failed_recoveries=recoveries)
    validate_audit(audit, plan=plan, classroom=classroom, expected_source_sha256=args.source_sha256)
    immutable(args.output / 'audit.json', audit)
    print(json.dumps({'segments': len(audit['segments']), 'literalPassed': audit['passed'],
        'auditSha256': audit['sha256'], 'publicationAllowed': False}))


if __name__ == '__main__':
    main()
