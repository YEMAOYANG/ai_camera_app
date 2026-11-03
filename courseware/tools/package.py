"""Assemble a built and verified lesson into the folder that backend/scripts/publish_courseware.py checks and publishes.

The folder holds body.json and media/ (from the lane's work folder), roster.json, audit-receipt.json and verification.json
(also from the work folder), official-notes.json and brief.json (from the lesson source) and identity.json. The catalog ids
(edition, revision, node) come from the textbook catalogue and are passed in; title, objective and length are derived.
Nothing is packaged while a gate of courseware/tools/check.py reports an error.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

from courseware.tools import check


class PackageError(Exception):
    pass


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


def package_lesson(lesson_dir, build_dir, out_dir, *, edition_id, revision_id, node_id, teacher_code, author_models,
                   teaching_revision='1'):
    lesson, build, out = Path(lesson_dir), Path(build_dir), Path(out_dir)
    if out.exists():
        raise PackageError('out_exists', str(out))
    body = _load(build / 'body.json')
    notes, brief = _load(lesson / 'official-notes.json'), _load(lesson / 'brief.json')
    roster, receipt = _load(build / 'roster.json'), _load(build / 'audit-receipt.json')
    verification = _load(build / 'verification.json')
    grade = _load(build / 'draft.json').get('grade')
    issues = [i for i in check.check_classroom(body, build / 'media', notes=notes, roster=roster, receipt=receipt,
                                               verification=verification, grade=grade) if i['severity'] == 'error']
    if issues:
        raise PackageError('gates_failed', '; '.join(f"{i['gate']} {i['code']}" for i in issues))
    verifier = str(verification.get('verifier', {}).get('model', '')).lower()
    if not verifier or verifier in {str(m).lower() for m in author_models}:
        raise PackageError('verifier_not_independent', verifier or 'no verifier recorded')
    goals = brief.get('goals')
    if not isinstance(goals, list) or not goals or not all(isinstance(g, str) and g.strip() for g in goals):
        raise PackageError('brief_goals_missing', 'brief.json needs a non-empty goals list')
    title = body.get('stage', {}).get('name')
    if not isinstance(title, str) or not title.strip():
        raise PackageError('title_missing', 'body.stage.name')
    identity = {'editionId': edition_id, 'revisionId': revision_id, 'nodeId': node_id, 'teachingRevision': str(teaching_revision),
                'title': title, 'objective': '；'.join(g.strip() for g in goals), 'teacherCode': teacher_code,
                'authorModels': list(author_models), 'estimatedMinutes': estimate_minutes(body)}
    out.mkdir(parents=True)
    shutil.copytree(build / 'media', out / 'media')
    for name in ('body.json', 'roster.json', 'audit-receipt.json', 'verification.json'):
        shutil.copyfile(build / name, out / name)
    for name in ('official-notes.json', 'brief.json'):
        shutil.copyfile(lesson / name, out / name)
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
    parser.add_argument('--author-model', action='append', required=True, help='every model that wrote pages, lines or questions')
    parser.add_argument('--teaching-revision', default='1')
    args = parser.parse_args(argv)
    try:
        identity = package_lesson(args.lesson, args.build, args.out, edition_id=args.edition_id, revision_id=args.revision_id,
                                  node_id=args.node_id, teacher_code=args.teacher_code, author_models=args.author_model,
                                  teaching_revision=args.teaching_revision)
    except PackageError as exc:
        print(f'PackageError: {exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    print(json.dumps(identity, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
