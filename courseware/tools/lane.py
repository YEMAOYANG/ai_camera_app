"""Run one lesson through the factory: pictures, build with voices, static gates, page audit, random play.

The lesson source is courseware/lessons/<slug> (lesson.json, pages/, pictures.json, official-notes.json); everything the run
generates goes to a work folder outside git. Every step is cached and repeatable. The result lists the issues of the gates;
exit code 0 only when no step failed and there is no error issue.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from courseware.tools import audit, autoplay, build, check, picture, voice

STEPS = ('pictures', 'build', 'check', 'audit', 'play')


class LaneError(Exception):
    pass


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise LaneError('source_invalid', f'{path}: {exc}') from exc


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def run_lesson(lesson_dir, work_dir, *, stage_id, steps=STEPS, endpoint='http://127.0.0.1:3100', jobs=4,
               post=voice.default_post, fetch=picture.default_fetch, run_audit=audit.audit_body, run_play=autoplay.play_body, now_ms=None,
               sleep=time.sleep, teaching=True):
    lesson, work = Path(lesson_dir), Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise LaneError('steps_invalid', ', '.join(sorted(unknown)))
    result = {'stageId': stage_id, 'steps': {}, 'issues': []}

    if 'pictures' in steps:
        requests = _load(lesson / 'pictures.json') if (lesson / 'pictures.json').exists() else []
        if requests:
            made = picture.generate_pictures(requests, lesson / 'assets', post=post, fetch=fetch, cache_path=work / 'picture-cache.json',
                                             endpoint=endpoint, sleep=sleep)
            result['steps']['pictures'] = {'made': made['made'], 'reused': made['reused']}
        else:
            result['steps']['pictures'] = {'made': 0, 'reused': 0}

    body = None
    if 'build' in steps:
        draft = build.prepare(lesson, work, stage_id=stage_id, now_ms=now_ms)
        clips = voice.voice_lines(draft['lines'], work / 'media', post=post, cache_path=work / 'voice-cache.json', endpoint=endpoint,
                                  jobs=jobs, sleep=sleep)
        body = build.finish(draft, work, clips['files'])
        result['steps']['build'] = {'scenes': len(body['scenes']), 'lines': len(draft['lines']), 'voiced': clips['voiced'], 'reused': clips['reused']}
        result['roster'], result['grade'] = draft['roster'], draft['grade']
    elif {'check', 'audit', 'play'} & set(steps):
        body = _load(work / 'body.json')
        result['roster'], result['grade'] = _load(work / 'roster.json'), _load(work / 'draft.json')['grade']

    receipt = None
    if 'audit' in steps:
        receipt = run_audit(body, work / 'media')
        _save(work / 'audit-receipt.json', receipt)
        result['steps']['audit'] = {'ok': receipt['ok'], 'pages': len(receipt['pages'])}
    elif (work / 'audit-receipt.json').exists():
        receipt = _load(work / 'audit-receipt.json')

    play = None
    if 'play' in steps:
        play = run_play(body, work / 'media')
        _save(work / 'play-receipt.json', play)
        result['steps']['play'] = {'ok': play['ok'], 'pages': len(play['pages']), 'failed': sum(not p['ok'] for p in play['pages'])}
    elif (work / 'play-receipt.json').exists():
        play = _load(work / 'play-receipt.json')

    if 'check' in steps or 'audit' in steps or 'play' in steps:
        notes_path = lesson / 'official-notes.json'
        notes = _load(notes_path) if notes_path.exists() else None
        issues = check.check_classroom(body, work / 'media', notes=notes, roster=result['roster'], receipt=receipt, grade=result['grade'], teaching=teaching)
        if notes is None:
            issues.append(dict(gate='G0', code='notes_missing', scene=None, detail='official-notes.json is required', severity='error'))
        brief_path = lesson / 'brief.json'
        bad = check.traditional(brief_path.read_text(encoding='utf-8')) if brief_path.exists() else ''
        if bad:
            # The brief is what the authors copy from; Traditional characters in it end up in the lesson.
            issues.append(dict(gate='G0', code='traditional_chinese', scene=None, detail='brief.json: ' + bad, severity='error'))
        if receipt is None:
            issues.append(dict(gate='G6', code='receipt_missing', scene=None, detail='the play-through audit has not run', severity='error'))
        if play is not None:
            if play.get('bodySha256') == check.body_hash(body):
                issues += autoplay.issues(play)
            else:
                issues.append(dict(gate='G6', code='play_receipt_stale', scene=None, detail='the random-play receipt belongs to another build', severity='warn'))
        result['issues'] = issues
        _save(work / 'check.json', issues)
        result['steps']['check'] = {'errors': sum(i['severity'] == 'error' for i in issues), 'warnings': sum(i['severity'] == 'warn' for i in issues)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesson', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--stage-id', required=True)
    parser.add_argument('--steps', default=','.join(STEPS), help='comma separated subset of ' + ', '.join(STEPS))
    parser.add_argument('--endpoint', default='http://127.0.0.1:3100')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args(argv)
    try:
        result = run_lesson(args.lesson, args.work, stage_id=args.stage_id, steps=[s for s in args.steps.split(',') if s],
                            endpoint=args.endpoint, jobs=args.jobs)
    except (LaneError, build.BuildError, voice.VoiceError, picture.PictureError) as exc:
        print(f'{type(exc).__name__}: {exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    for name, info in result['steps'].items():
        print(name, json.dumps(info, ensure_ascii=False))
    for issue in result['issues']:
        print('{gate} {severity} {code} scene={scene}: {detail}'.format(**issue))
    return int(any(issue['severity'] == 'error' for issue in result['issues']))


if __name__ == '__main__':
    raise SystemExit(main())
