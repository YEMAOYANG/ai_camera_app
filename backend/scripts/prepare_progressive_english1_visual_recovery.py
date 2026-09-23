"""Read-only budget preflight + immutable local evidence for one unsent visual collision."""
import hashlib
import json
from pathlib import Path

from core.config import AppConfig
from core.database import Database
from integrations.openmaic_formal_quality import quality_sha

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/progressive-preview/saved-stage-english-slot1-revision2'
NATIVE = ROOT / 'openmaic-runtime/.runtime/OpenMAIC'
JOB = 'omformal_35329ccda267db6155963636'
AUTH = 'd8eca649c6be4ccb5d19b8422b1333253d76bef3ef0b555b7027efb6471f74fc'
TARGET = '278de60ab4580431b84b6b8fe656a82cc25b4b8409871857a8217f172ece6983'
SOURCE = 'ce327bcb84a0836065def3bc20fcfe62ede100a099be5194df5b4c8014c2d8a9'
REVIEW = NATIVE / 'data/formal-quality-reviews/550b7f32a490d9374d2291c2de3077712d1e491819c1e771e03b0ec2aa9b382b'
RECOVERY = NATIVE / 'data/formal-saved-stage-recoveries' / JOB
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: json.loads(p.read_bytes())


def immutable(name, raw):
    p = BASE / name
    if p.exists():
        assert p.read_bytes() == raw, f'Existing audit differs: {name}'
    else:
        with p.open('xb') as f:
            p.chmod(0o600)
            f.write(raw)


def main():
    failure = (BASE / 'complete.log').read_bytes()
    assert failure.decode().rstrip().endswith('MIRA_PAID_BUDGET_DISPATCH_ALREADY_CLAIMED')
    claim_raw = (RECOVERY / f'complete-{TARGET}.claim').read_bytes()
    claim = json.loads(claim_raw)
    identity = {k: claim[k] for k in ('sourceJobSha256', 'sourceSnapshotSha256', 'repairSnapshotSha256', 'sessionId', 'stageId')}
    job_raw = (NATIVE / 'data/classroom-jobs' / f'{JOB}.json').read_bytes()
    assert sha(job_raw) == identity['sourceJobSha256']
    job = json.loads(job_raw)
    assert job['status'] == 'failed' and job['formalInput']['paidBudget']['authorizationId'] == AUTH
    c = Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        c.execute('START TRANSACTION READ ONLY')
        records = [dict(r) for r in c.execute('SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id', (AUTH,)).fetchall()]
        assert len(records) == 151 and all(r['state'] == 'settled' for r in records)
        collision = [r for r in records if r['id'] == 'b674d1c68c002534b5006bba33d76274a578a9ed68f1409f65324a483f414731']
        assert len(collision) == 1
        collision = collision[0]
        assert json.loads(collision['price_json'])['model'] == 'deepseek-v4-flash-vision-exp'
        auth = dict(c.execute('SELECT * FROM learning_budget_authorizations WHERE id=?', (AUTH,)).fetchone())
        assert not auth['revoked_at']
        from scripts.generate_progressive_preview import preview_identities
        exact = next(i for i in preview_identities('primary_6') if i['buildItemId'] == 'catalog_build_item_4b59d735f1373e60196aa25a')
        assert json.loads(auth['scope_json']) == exact['scope']
    finally:
        c.rollback()
        c.close()
    browser = read(REVIEW / f'{TARGET}-browser.json')
    old_browser = read(REVIEW / f'{SOURCE}-browser.json')
    assert len(browser) == len(old_browser) == 16
    assert all(a['passed'] and b['passed'] and a['screenshotSha256'] == b['screenshotSha256']
               and a['sceneId'] == b['sceneId'] and a['viewport'] == b['viewport'] for a, b in zip(browser, old_browser))
    evidence = {
        'schemaVersion': 'mira.english1.visual-predispatch-recovery.v1', 'jobId': JOB,
        'authorizationId': AUTH, 'identity': identity,
        'error': 'MIRA_PAID_BUDGET_DISPATCH_ALREADY_CLAIMED',
        'failureLog': failure.decode(), 'failureLogSha256': sha(failure),
        'priorClaimSha256': sha(claim_raw),
        'priorAttemptsSha256': quality_sha(read(REVIEW / 'attempts.json')),
        'priorInputSha256': sha((REVIEW / f'{TARGET}-input.json').read_bytes()),
        'browserSha256': quality_sha(browser),
        'sourceVisualReceiptSha256': read(REVIEW / f'{SOURCE}-visual.json')['receiptSha256'],
        'collisionReservation': collision, 'ledgerSha256': quality_sha(records),
        'authorizationSha256': quality_sha(auth), 'settledCount': 151,
        'reason': 'Only narration and speech action IDs changed. All 16 visual screenshots are identical. The old visual request omitted snapshot identity and collided with an already settled request. Add exact snapshot/context to the new request; keep every prior claim and reservation unchanged.',
        'approvalRef': 'User authorized all six grade-6 coursewares through completion including every required audio generation; this is one new review of the revised English1 snapshot within that scope.',
    }
    immutable('visual-collision-failure.log', failure)
    immutable('visual-collision-original-claim.json', claim_raw)
    immutable('visual-collision-ledger.json', (json.dumps(records, ensure_ascii=False, indent=2) + '\n').encode())
    immutable('visual-predispatch-evidence.json', (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode())
    manifest = read(BASE / 'manifest.json') | {'visualPredispatchEvidencePath': 'visual-predispatch-evidence.json'}
    immutable('visual-predispatch-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({'status': 'prepared', 'evidenceSha256': quality_sha(evidence), 'settledCount': 151, 'providerCalls': 0, 'databaseWrites': 0}))


if __name__ == '__main__':
    main()
