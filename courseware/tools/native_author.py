"""Freeze, dispatch, and fetch a private OpenMAIC draft with recorded requests."""

import argparse
import hashlib
from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit

from courseware.tools.media_dispatch import DispatchError, _atomic_record, work_lock


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/packages/@openmaic/generation/templates'
GENERATION = '/api/generate-classroom'
INPUT_SCHEMA = 'mira.courseware.openmaic-generation-input.v1'
IDENTIFIER = re.compile(r'[a-zA-Z0-9_-]{1,128}')
BALANCE_ERROR = re.compile(r'(?:AI_APICallError: )?Insufficient Balance(?: \(request_id: [a-zA-Z0-9_-]+\))?')
TEMPLATE_ERROR = re.compile(r"EPERM: operation not permitted, open '([^']+)'")
RETRY_ACTIONS = ('retry-after-balance', 'retry-after-template-error', 'retry-after-answer-error')
REVIEW_RESOURCES = ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise')
SCOPE_FIELDS = ('objectives', 'coveredOfficialHours', 'videoStatus', 'excludedTopics')
PROMPT_FIELDS = ('binding', 'qualityRules', 'pagePlan', 'assessmentBlueprint', 'assetPlan')


def local_request(method, path, body=None):
    connection = HTTPConnection('127.0.0.1', 3100, timeout=45)
    try:
        connection.request(method, path, body=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                           headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read(32 * 1024 * 1024 + 1)
        if response.status not in (200, 202) or len(raw) > 32 * 1024 * 1024:
            raise ValueError(f'OpenMAIC returned HTTP {response.status} or an oversized result')
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('success') is not True:
            raise ValueError('OpenMAIC did not return a successful result')
        return value
    finally:
        connection.close()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def readable_failed_template(error):
    match = TEMPLATE_ERROR.fullmatch(error)
    if not match:
        return False
    path = Path(match[1])
    try:
        relative = path.resolve().relative_to(TEMPLATE_ROOT.resolve())
    except ValueError:
        return False
    if len(relative.parts) != 2 or relative.name not in ('system.md', 'user.md'):
        return False
    return bool(path.read_bytes().strip())


def verify_textbook_only_review(notes_path, draft, binding):
    if notes_path is None:
        raise ValueError('Textbook-only generation requires the exact official notes')
    raw = notes_path.read_bytes()
    notes = json.loads(raw)
    if (draft['sourceInput'].get('officialNotesSha256') != digest(raw)
            or any(notes['binding'].get(key) != binding[key] for key in ('editionId', 'revisionId', 'nodeId'))):
        raise ValueError('Textbook-only review must match the frozen input and lesson')
    completeness = notes['sourceCompleteness']
    listing = notes['officialListingSearch']
    resources = notes['resources']
    listing_url = urlsplit(listing['listingUrl'])
    if (completeness.get('status') != 'complete_textbook_with_official_resource_absence'
            or completeness.get('generationAllowed') is not True or completeness.get('officialClassHours') != []
            or completeness.get('textbookReviewed') is not True
            or not str(completeness.get('absenceEvidence') or '').strip()
            or not str(completeness.get('objectiveBasis') or '').strip()
            or listing.get('chapterIdQuery') != binding['nodeId'] or listing.get('exactLessonMatches') != 0
            or listing_url.scheme != 'https' or not listing_url.hostname
            or not re.fullmatch(r'[a-f0-9]{64}', str(listing.get('listingSha256')))
            or not isinstance(listing.get('partCount'), int) or listing['partCount'] < 1
            or not str(listing.get('normalizedTitleQuery') or '').strip()):
        raise ValueError('Textbook-only review requires a complete official listing and documented absence')
    textbook = resources.get('textbook', {})
    if (textbook.get('status') != 'reviewed' or not textbook.get('pageRefs') or not textbook.get('findings')
            or not all(notes.get('textbookBoundary', {}).get(key) for key in ('start', 'end'))
            or any(resources.get(key, {}).get('status') != 'not_provided'
                   or not str(resources[key].get('evidence') or '').strip() for key in REVIEW_RESOURCES)):
        raise ValueError('Textbook-only review requires full lesson pages and all four resource results')


def freeze(source, standard, notes_path=None):
    raw = source.read_bytes()
    draft = json.loads(raw)
    if draft.get('schemaVersion') != INPUT_SCHEMA:
        raise ValueError('Use a reviewed courseware generation input')
    binding = draft['binding']
    for key in ('editionId', 'revisionId', 'nodeId', 'unitId'):
        if not isinstance(binding.get(key), str) or not IDENTIFIER.fullmatch(binding[key]):
            raise ValueError(f'Missing exact lesson binding {key}')
    hours = binding['classHours']
    if (not isinstance(hours, list) or len(set(hours)) != len(hours)
            or draft['scopeReview'].get('status') != 'current-standard-g0-reviewed'
            or draft['scopeReview'].get('coveredOfficialHours') != hours):
        raise ValueError('Bind each reviewed official hour once')
    if not hours:
        verify_textbook_only_review(notes_path, draft, binding)
    if draft['sourceInput']['standardSha256'] != digest(standard.read_bytes()):
        raise ValueError('Draft does not bind the current courseware standard')
    controls = draft['generationControls']
    if (controls.get('serverRoutedDeepSeekRequired') is not True
            or any(controls.get(key) is not False for key in
                   ('automaticImageGeneration', 'automaticVideoGeneration', 'automaticTts', 'publication'))):
        raise ValueError('Draft requires the server text model and separate media and publication')
    prompt = {key: draft[key] for key in PROMPT_FIELDS}
    prompt['officialScope'] = {key: draft['scopeReview'][key] for key in SCOPE_FIELDS}
    prompt['teachingFacts'] = draft.get('teachingFacts', {})
    requirement = ('为指定教材节点创作一门原创完整课件，将列出的全部官方课时合并。'
                   '按所附规则生成讲解、可操作互动、原创图题和总结。用简体中文。'
                   '以已审读资料为范围。图片由 Codex 提供，按素材标识引用；'
                   '待制图片描述语义和精确数量，禁止外链、实时讨论和浏览器语音。'
                   '老师先操作画面，再讲解。交付草稿，供后续公共互动框架和发布检查。\n'
                   + draft['request'] + '\n' + json.dumps(prompt, ensure_ascii=False, sort_keys=True))
    return {'draftSha256': digest(raw), 'binding': binding, 'sourceInput': draft['sourceInput'],
            'request': {'requirement': requirement, 'agentMode': 'generate', 'enableWebSearch': False,
                        'enableImageGeneration': False, 'enableVideoGeneration': False, 'enableTTS': False}}


def native_job(work, action, source, standard, *, request=local_request, failed_job=None, notes_path=None):
    frozen_path = work / 'input.json'
    claim = work / 'dispatch-claim.json'
    submitted = work / 'dispatch-response.json'
    if action == 'prepare':
        frozen = freeze(source, standard, notes_path)
        if frozen_path.exists():
            if read_json(frozen_path) != frozen:
                raise ValueError('Existing request differs from the reviewed input')
        else:
            _atomic_record(frozen_path, frozen)
        return {'status': 'prepared', 'draftSha256': frozen['draftSha256']}

    frozen = read_json(frozen_path)
    attempts = [(claim, submitted)]
    for name in ('balance', 'template', 'answer'):
        attempts.append((work / f'{name}-retry-claim.json', work / f'{name}-retry-response.json'))
    original = None
    if action in RETRY_ACTIONS:
        if not failed_job or not IDENTIFIER.fullmatch(failed_job):
            raise ValueError('Specify the original failed OpenMAIC job id')
        index = RETRY_ACTIONS.index(action) + 1
        if any(record.exists() for record, _ in attempts[index + 1:]):
            raise ValueError('A later retry is already recorded')
        claim, submitted = next((pair for pair in reversed(attempts[:index]) if pair[0].exists()), attempts[0])
        if not submitted.exists() or read_json(submitted)['jobId'] != failed_job:
            raise ValueError('Failed job does not match the preceding recorded dispatch')
        original = read_json(claim)
        if original['draftSha256'] != frozen['draftSha256']:
            raise ValueError('Original dispatch does not match the reviewed input')
        claim, submitted = attempts[index]
    else:
        claim, submitted = next((pair for pair in reversed(attempts) if pair[0].exists()), attempts[0])
        if claim != attempts[0][0] and not submitted.exists():
            raise ValueError('Retry outcome unknown; reconcile the recorded retry before proceeding')

    if action == 'start' or action in RETRY_ACTIONS:
        if submitted.exists():
            return read_json(submitted)
        if claim.exists():
            raise ValueError('Dispatch outcome unknown; reconcile the existing request before proceeding')
        reviewed = freeze(source, standard, notes_path)
        if action == 'retry-after-answer-error':
            if (reviewed['binding'] != frozen['binding'] or reviewed['sourceInput'] != frozen['sourceInput']
                    or reviewed['request'] == frozen['request']):
                raise ValueError('Answer repair requires a changed prompt for the same reviewed lesson')
        elif reviewed != frozen:
            raise ValueError('Reviewed input changed since preparation')
        policy = request('GET', '/api/health')['runtimePolicy']['modelPolicy']
        author = policy['coursewareCreator']
        if author['providerId'] != 'deepseek' or author['modelId'] != policy['structuredScene']['modelId']:
            raise ValueError('Local OpenMAIC text and scene policies do not match the DeepSeek route')
        dispatch = {'draftSha256': frozen['draftSha256'], 'modelPolicyId': policy['policyId'],
                    'providerId': author['providerId'], 'modelId': author['modelId']}
        if original is not None:
            if any(original.get(key) != value for key, value in dispatch.items()):
                raise ValueError('DeepSeek route changed since the original dispatch')
            if (work / 'classroom.json').exists():
                raise ValueError('The original lesson already has a saved classroom')
            terminal = request('GET', f'{GENERATION}/{failed_job}')
            error = str(terminal.get('error'))
            if action == 'retry-after-balance':
                reason = 'balance failure'
                terminal_error_matches = BALANCE_ERROR.fullmatch(error)
            elif action == 'retry-after-template-error':
                reason = 'readable template error'
                terminal_error_matches = readable_failed_template(error)
            else:
                reason = 'answer cardinality failure'
                terminal_error_matches = error == 'LEARNING_SCENE_ANSWER_CARDINALITY_INVALID'
            if (terminal.get('jobId') != failed_job or terminal.get('status') != 'failed'
                    or not terminal.get('completedAt') or terminal.get('result') is not None
                    or not terminal_error_matches):
                raise ValueError(f'Original job is not a confirmed terminal {reason}')
            dispatch.update(originalJobId=failed_job, originalTerminalResponse=terminal)
        if action == 'retry-after-answer-error':
            corrected_input = work / 'answer-retry-input.json'
            if corrected_input.exists():
                if read_json(corrected_input) != reviewed:
                    raise ValueError('The recorded answer repair input differs')
            else:
                _atomic_record(corrected_input, reviewed)
            dispatch.update(originalDraftSha256=frozen['draftSha256'], draftSha256=reviewed['draftSha256'])
        _atomic_record(claim, dispatch)
        response = request('POST', GENERATION, reviewed['request'])
        job_id = response['jobId']
        if not IDENTIFIER.fullmatch(job_id) or job_id == failed_job:
            raise ValueError('OpenMAIC returned an invalid job id; reconcile the original request')
        result = {'jobId': job_id, 'status': response['status']}
        _atomic_record(submitted, result)
        return result

    job_id = read_json(submitted)['jobId']
    if not IDENTIFIER.fullmatch(job_id):
        raise ValueError('Invalid saved OpenMAIC job id')
    response = request('GET', f'{GENERATION}/{job_id}')
    if response['jobId'] != job_id:
        raise ValueError('OpenMAIC returned a different job')
    result = {key: response.get(key) for key in ('jobId', 'status', 'step', 'progress', 'scenesGenerated')}
    if response['status'] == 'succeeded':
        classroom_id = response['result']['classroomId']
        if not IDENTIFIER.fullmatch(classroom_id):
            raise ValueError('Invalid classroom id')
        room = request('GET', '/api/classroom?' + urlencode({'id': classroom_id}))['classroom']
        if room['id'] != classroom_id or room['stage']['id'] != classroom_id or not room['scenes']:
            raise ValueError('Saved classroom identity or scenes are incomplete')
        room_path = work / 'classroom.json'
        if not room_path.exists():
            _atomic_record(room_path, room)
        elif read_json(room_path) != room:
            raise ValueError('Saved classroom changed since the first readback')
        result.update(classroomId=classroom_id, draftPath=str(room_path),
                      classroomSha256=digest(room_path.read_bytes()), publicationAllowed=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'poll', *RETRY_ACTIONS))
    parser.add_argument('--lesson', required=True)
    parser.add_argument('--draft', type=Path)
    parser.add_argument('--failed-job')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.lesson):
        parser.error('Use a courseware lesson slug')
    if (args.action != 'poll') != (args.draft is not None):
        parser.error('prepare, start and retries require --draft; poll uses the saved request')
    if (args.action in RETRY_ACTIONS) != (args.failed_job is not None):
        parser.error('--failed-job is required only for a retry')
    work = ROOT / 'output/courseware-lessons' / args.lesson / 'native-authoring-v1'
    notes_path = ROOT / 'courseware/lessons' / args.lesson / 'official-notes.json'
    try:
        with work_lock(work, args.lesson) as directory:
            result = native_job(directory, args.action, args.draft, ROOT / 'docs/learning/courseware-standard.md',
                                failed_job=args.failed_job, notes_path=notes_path)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DispatchError, HTTPException, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
