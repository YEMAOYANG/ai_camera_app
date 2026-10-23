"""Read-only native archive adapter for v4 published revision adoption."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from content.textbook_authoring_candidate import (CANDIDATE_FILE, _read_json, _safe_child,
    _find_job, validate_authoring_candidate)
from content.textbook_catalog import digest
from content.textbook_operator_revision import fail
from content.textbook_preview import operator_media
from content.textbook_review_followup import _revision_entry
from services.course_file_store import course_bytes, course_text, course_glob


def read_complete_scene_evidence(parent, root, authoring, output_root, runtime_origin):
    """Read the applied stage ledger, never the stale exported classroom file."""
    root, output_root = Path(root).resolve(), Path(output_root).resolve()
    stage, session = authoring['stageId'], authoring['sessionId']
    ledger_path = _safe_child(root, root / stage / CANDIDATE_FILE)
    ledger = _read_json(ledger_path)
    manifest, node = parent['manifest'], parent['preview']['node_id']
    found = _find_job(output_root, manifest['editionId'], manifest['revisionId'], node, session, stage, True)
    if found is None:
        fail('v4 完整场景入口需要真实原生 v3 冻结任务')
    job, frozen, _ = found
    stage_root = root.parent / 'textbook-current-review-revisions' / hashlib.sha256(session.encode()).hexdigest() / stage
    matches = []
    for folder in course_glob(stage_root):
        entry = _revision_entry(folder, stage_root, session, stage, frozen['sceneContract']['sha256'])
        if entry['plan']['afterCandidateSha256'] == ledger['sha256']:
            matches.append((folder, entry))
    if len(matches) != 1:
        fail('当前候选必须唯一匹配已执行的正式完整场景回执')
    folder, _ = matches[0]
    before = _read_json(folder / 'original-document.json')
    classroom = {'id': stage, 'stage': before['stage'],
                 'scenes': [json.loads(s['canonicalJson']) for s in ledger['scenes']]}
    summary = validate_authoring_candidate(classroom, root, authoring, manifest, node,
        output_root=output_root, runtime_origin=runtime_origin)
    if not summary or not summary.get('completeSceneReviewFollowup'):
        fail('完整场景需要通过原生候选及当前规则追踪核验')
    revision_files = {}
    for path in course_glob(folder, '*.json'):
        _safe_child(stage_root, path)
        revision_files[path.name] = course_text(path)
    media = operator_media(classroom, root, authoring['imageProvenance'])
    evidence = {'authoring': deepcopy(authoring), 'summary': summary,
        'draftJson': course_text(job / 'draft.json'), 'frozenJson': course_text(job / 'frozen.json'),
        'stateJson': course_text(job / 'state.json'), 'ledgerJson': course_text(ledger_path),
        'revisionFiles': revision_files, 'media': media}
    from content.textbook_complete_scene_revision import validate_evidence
    rebuilt, _ = validate_evidence(parent, evidence, unpublished='build' not in parent)
    if rebuilt != classroom:
        fail('完整场景不能由正式原始证据准确重建')
    files = {}
    for asset in media['assets']:
        path = root / '/'.join(asset['mediaPath'].split('/')[3:])
        _safe_child(root, path)
        raw = course_bytes(path)
        if hashlib.sha256(raw).hexdigest() != asset['sha256']:
            fail('完整场景图片原字节变化')
        files['complete-scene-media/' + asset['sha256'] + path.suffix] = raw
    return evidence, files
