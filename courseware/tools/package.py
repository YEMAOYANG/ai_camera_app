"""Assemble a built and verified lesson into the folder that backend/scripts/publish_courseware.py checks and publishes.

The folder holds body.json and media/ (from the lane's work folder), roster.json, audit-receipt.json, play-receipt.json and
verification.json (also from the work folder), official-notes.json and brief.json (from the lesson source) and identity.json. The catalog ids
(edition, revision, node) come from the textbook catalogue and are passed in; title, objective and length are derived.
Nothing is packaged while a gate of courseware/tools/check.py reports an error.
"""
import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path

from courseware.tools import check


class PackageError(Exception):
    pass


MEDIA_REFERENCE = re.compile(
    r'/api/classroom-media/[A-Za-z0-9_-]+/(?:audio|media)/([A-Za-z0-9_.-]+)'
)


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PackageError('input_unreadable', f'{path}: {exc}') from exc


def estimate_minutes(body):
    """Rough lesson length: speech at 4 characters a second, 100 seconds per interactive page, 60 per quiz question and
    20 per slide, rounded up to 5 minutes and kept between 10 and 60."""
    seconds = 0
    for scene in body.get('scenes', []):
        seconds += sum(len(a.get('text', '')) for a in scene.get('actions', []) if a.get('type') == 'speech') / 4
        kind = scene.get('type')
        if kind == 'interactive':
            seconds += 100
        elif kind == 'quiz':
            seconds += 60 * len(scene.get('content', {}).get('questions', []))
        else:
            seconds += 20
    return min(60, max(10, 5 * math.ceil(seconds / 60 / 5)))


def _copy_referenced_media(body, source, destination):
    """Incremental builds keep content-addressed files from earlier drafts; a release package must not carry them."""
    names = sorted(set(MEDIA_REFERENCE.findall(json.dumps(body, ensure_ascii=False))))
    # Valid built lessons always have namespaced media. Keeping this fallback makes the helper compatible with synthetic
    # callers whose checker is replaced in tests, while the real checker still rejects a lesson without bound media.
    if not names:
        shutil.copytree(source, destination)
        return
    missing = [name for name in names if not (source / name).is_file()]
    if missing:
        raise PackageError('media_missing', ', '.join(missing))
    destination.mkdir()
    for name in names:
        shutil.copyfile(source / name, destination / name)


def package_lesson(lesson_dir, build_dir, out_dir, *, edition_id, revision_id, node_id, teacher_code, author_models,
                   page_author_models=(), teaching_revision='1', g7_owner_quote=None,
                   g7_confirmed_at=None):
    """author_models wrote lines or questions and so may not verify them; page_author_models wrote only page code, which
    the verifier does not read, so one of them may verify. Both are recorded as authors."""
    lesson, build, out = Path(lesson_dir), Path(build_dir), Path(out_dir)
    if out.exists():
        raise PackageError('out_exists', str(out))
    body = _load(build / 'body.json')
    notes, brief = _load(lesson / 'official-notes.json'), _load(lesson / 'brief.json')
    roster, receipt = _load(build / 'roster.json'), _load(build / 'audit-receipt.json')
    play_receipt = _load(build / 'play-receipt.json')
    verification = _load(build / 'verification.json')
    if bool(g7_owner_quote) != bool(g7_confirmed_at):
        raise PackageError('g7_owner_waiver_invalid', 'owner quote and confirmation time are both required')
    waiver = None
    if g7_owner_quote:
        try:
            waiver = check.g7_owner_waiver(body, notes, verification,
                                            user_quote=g7_owner_quote, confirmed_at=g7_confirmed_at)
        except ValueError as exc:
            raise PackageError(str(exc), '') from exc
    grade = _load(build / 'draft.json').get('grade')
    checked = check.check_classroom(body, build / 'media', notes=notes, roster=roster, receipt=receipt,
                                    play_receipt=play_receipt, verification=verification, grade=grade,
                                    teaching=True, require_play=True)
    try:
        checked = check.apply_g7_owner_waiver(checked, waiver, body, notes, verification)
    except ValueError as exc:
        raise PackageError(str(exc), '') from exc
    issues = [i for i in checked if i['severity'] == 'error']
    if issues:
        raise PackageError('gates_failed', '; '.join(f"{i['gate']} {i['code']}" for i in issues))
    if waiver is None and (type(verification.get('goalsChecked')) is not int
                           or verification['goalsChecked'] < check.teaching_goal_count(notes)):
        raise PackageError('teaching_unchecked', 'the verification did not check that the narration teaches the learning goals')
    verifier = str(verification.get('verifier', {}).get('model', '')).lower()
    if waiver is None and (not verifier or verifier in {str(m).lower() for m in author_models}):
        raise PackageError('verifier_not_independent', verifier or 'no verifier recorded')
    goals = brief.get('goals')
    if not isinstance(goals, list) or not goals or not all(isinstance(g, str) and g.strip() for g in goals):
        raise PackageError('brief_goals_missing', 'brief.json needs a non-empty goals list')
    title = body.get('stage', {}).get('name')
    if not isinstance(title, str) or not title.strip():
        raise PackageError('title_missing', 'body.stage.name')
    identity = {'editionId': edition_id, 'revisionId': revision_id, 'nodeId': node_id, 'teachingRevision': str(teaching_revision),
                'title': title, 'objective': '；'.join(g.strip() for g in goals), 'teacherCode': teacher_code,
                'authorModels': list(author_models) + [m for m in page_author_models if m not in author_models], 'estimatedMinutes': estimate_minutes(body)}
    out.mkdir(parents=True)
    _copy_referenced_media(body, build / 'media', out / 'media')
    for name in ('body.json', 'roster.json', 'audit-receipt.json', 'play-receipt.json', 'verification.json'):
        shutil.copyfile(build / name, out / name)
    for name in ('official-notes.json', 'brief.json'):
        shutil.copyfile(lesson / name, out / name)
    if waiver is not None:
        (out / 'owner-waiver.json').write_text(
            json.dumps(waiver, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'identity.json').write_text(json.dumps(identity, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesson', required=True, help='lesson source folder (official-notes.json, brief.json)')
    parser.add_argument('--build', required=True, help="the lane's work folder")
    parser.add_argument('--out', required=True, help='new package folder (must not exist)')
    parser.add_argument('--edition-id', required=True)
    parser.add_argument('--revision-id', required=True)
    parser.add_argument('--node-id', required=True)
    parser.add_argument('--teacher-code', required=True)
    parser.add_argument('--author-model', action='append', required=True, help='every model that wrote lines or questions')
    parser.add_argument('--page-author-model', action='append', default=[], help='every model that wrote only page code')
    parser.add_argument('--teaching-revision', default='1')
    parser.add_argument('--waive-g7-owner-quote')
    parser.add_argument('--waive-g7-confirmed-at')
    args = parser.parse_args(argv)
    try:
        identity = package_lesson(args.lesson, args.build, args.out, edition_id=args.edition_id, revision_id=args.revision_id,
                                  node_id=args.node_id, teacher_code=args.teacher_code, author_models=args.author_model,
                                  page_author_models=args.page_author_model, teaching_revision=args.teaching_revision,
                                  g7_owner_quote=args.waive_g7_owner_quote,
                                  g7_confirmed_at=args.waive_g7_confirmed_at)
    except PackageError as exc:
        print(f'PackageError: {exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    print(json.dumps(identity, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
