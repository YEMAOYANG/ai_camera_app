"""Immutable, pre-generated textbook releases. No model calls on delivery."""
from copy import deepcopy
import hashlib
import re

from content.textbook_catalog import canonical, digest, lesson_by_id
from core.errors import ApiError

INPUT_SCHEMA = 'mira.textbook.saved-classroom-input.v1'
RELEASE_SCHEMA = 'mira.textbook.saved-classroom-release.v1'
KEY = re.compile(r'^[a-f0-9]{64}$')
MEDIA = re.compile(r'(?:https?://[^/\s"\x27<>\\]+)?/api/classroom-media/([A-Za-z0-9_-]+)/((?:audio|media)/[A-Za-z0-9_.-]+)')


def fail(message='这节课的发布资料不完整，请稍后再来'):
    raise ApiError('textbook_release_unavailable', message, 409)


def questions(classroom):
    return [q for s in classroom['scenes'] if s['type'] == 'quiz' for q in s['content']['questions']]


def single_answer(question):
    """Read Native's string or singleton-list key without changing frozen data."""
    answer = question.get('answer')
    if isinstance(answer, list) and len(answer) == 1:
        answer = answer[0]
    if not isinstance(answer, str) or not answer.strip():
        fail('每道题需要唯一有效答案')
    return answer


def check_questions(classroom):
    items = questions(classroom)
    if not items or len(items) > 30 or len({q['id'] for q in items}) != len(items):
        fail('题目数量或身份无效')
    for q in items:
        options = q.get('options', [])
        values = {o.get('value') for o in options}
        answer = single_answer(q)
        if (q.get('type') != 'single' or not 2 <= len(options) <= 6
                or len(values) != len(options)
                or answer not in values
                or not q.get('questionAudioUrl') or not q.get('analysis')
                or type(q.get('points', 1)) is not int or not 1 <= q.get('points', 1) <= 100):
            fail('每道题需要唯一答案、解析和已生成的听题音频')
        feedback = q.get('optionFeedback')
        if feedback is not None:
            if not isinstance(feedback, dict) or set(feedback) != values:
                fail('每个选项都需要一份专属反馈')
            for value, item in feedback.items():
                visual = item.get('visual') if isinstance(item, dict) else None
                relationship_valid = False
                if isinstance(visual, dict) and visual.get('kind') == 'relationship':
                    actors = visual.get('actors')
                    links = visual.get('links')
                    actor_ids = {actor.get('id') for actor in actors if isinstance(actor.get('id'), str)} if isinstance(actors, list) and all(isinstance(actor, dict) for actor in actors) else set()
                    relationship_valid = (
                        isinstance(visual.get('alt'), str) and visual['alt'].strip()
                        and isinstance(actors, list) and 1 <= len(actors) <= 3
                        and len(actor_ids) == len(actors)
                        and all(isinstance(actor.get('id'), str) and actor['id'].strip()
                            and isinstance(actor.get('src'), str) and MEDIA.fullmatch(actor['src'])
                            and isinstance(actor.get('alt'), str) and actor['alt'].strip()
                            and actor.get('cue') in {'speaking', 'listening', 'observer'} for actor in actors)
                        and isinstance(links, list) and 1 <= len(links) <= 3
                        and all(isinstance(link, dict)
                            and link.get('kind') in {'speaks-to', 'voice-match', 'mismatch', 'corrects-name', 'farewell'}
                            and link.get('fromId') in actor_ids and link.get('toId') in actor_ids for link in links))
                image_valid = (isinstance(visual, dict) and visual.get('kind') == 'image'
                    and isinstance(visual.get('src'), str) and MEDIA.fullmatch(visual['src'])
                    and isinstance(visual.get('alt'), str) and visual['alt'].strip())
                if (not isinstance(item, dict)
                        or set(item) - {'text', 'visual', 'audioUrl', 'audioBinding'}
                        or not isinstance(item.get('text'), str) or not item['text'].strip()
                        or not (image_valid or relationship_valid)
                        or ('audioUrl' in item and (not isinstance(item['audioUrl'], str)
                            or not MEDIA.fullmatch(item['audioUrl']) or '/audio/' not in item['audioUrl']))
                        or ('audioBinding' in item and (not isinstance(item['audioBinding'], dict)
                            or item['audioBinding'].get('schemaVersion') != 'mira.learning.quiz-feedback-audio-binding.v1'
                            or item['audioBinding'].get('questionId') != q['id']
                            or item['audioBinding'].get('optionValue') != value))):
                    fail('选项专属反馈需要有效的图片、文字和已保存录音绑定')
    return items


def validate_release(build, manifest, course=None):
    """Validate exact hashes and the separate saved-artifact publication contract.

    A release review covers one lesson, not every pending lesson in its book.
    Historical generator/whole-catalog releases retain their existing gates.
    """
    from repositories.textbook_repository import TextbookRepository
    parse = TextbookRepository.parse
    frozen, review = parse(build['input_json']), parse(build['review_json'])
    from content.textbook_batch_release import INPUT_SCHEMA as ACTIVITY_INPUT, validate_activity_release
    if isinstance(frozen, dict) and frozen.get('schemaVersion') == ACTIVITY_INPUT:
        return validate_activity_release(build, manifest, course)
    if not isinstance(frozen, dict) or frozen.get('schemaVersion') != INPUT_SCHEMA:
        return None
    release = (review or {}).get('release')
    if not isinstance(release, dict) or release.get('schemaVersion') != RELEASE_SCHEMA:
        fail()
    receipt = {k: v for k, v in release.items() if k != 'sha256'}
    binding = frozen.get('textbookBinding', {})
    if (build['status'] != 'published' or digest(receipt) != release.get('sha256')
            or digest({k: v for k, v in frozen.items() if k != 'contentKey'}) != build['content_key']
            or frozen.get('contentKey') != build['content_key']
            or binding != {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'alignmentManifestSha256': digest(manifest), 'nodeId': build['node_id'], 'partIndex': 1,
                'teachingRevision': build['teaching_revision']}
            or release.get('contentKey') != build['content_key']
            or release.get('classroomId') != 'tbpub_' + build['content_key'][:24]
            or digest(release.get('classroom')) != release.get('classroomSha256')
            or review.get('alignmentConfirmed') is not True or review.get('originalExpressionConfirmed') is not True
            or review.get('sourceUsageConfirmed') is not True or review.get('publicationAuthorized') is not True
            or not review.get('reviewer') or not review.get('basis')):
        fail()
    _, node = lesson_by_id(manifest, build['node_id'])
    if frozen.get('knowledgeBrief') != node['brief'] or frozen.get('gradeCode') != manifest['gradeCode']:
        fail()
    if course is not None and (course['status'] != 'published' or course['quality_status'] != 'released'
            or course.get('retired_at') is not None or course['id'] != build['course_id']
            or course['version'] != build['course_version'] or digest(parse(course['content_json'])) != build['course_content_sha256']):
        fail()
    if (not release.get('media') or not release.get('audioAudit', {}).get('passed')
            or release['audioAudit'].get('segments') != sum(a.get('type') == 'speech' for s in release['classroom']['scenes'] for a in s.get('actions', []))):
        fail()
    quality_sha = frozen.get('wholeCourseQualityReviewSha256')
    if quality_sha is not None and (not isinstance(quality_sha, str) or not KEY.fullmatch(quality_sha)
            or not isinstance(review.get('coursewareQuality'), dict)
            or digest(review['coursewareQuality']) != quality_sha):
        fail('课件本体质量审核与发布冻结身份不一致')
    complete_scene_followup = frozen.get('completeSceneReviewFollowup')
    if complete_scene_followup is not None:
        try:
            from content.textbook_review_followup import validate_complete_scene_review_followup
            validate_complete_scene_review_followup(
                complete_scene_followup,
                candidate_source_sha256=frozen.get('authoringSourceSha256'))
        except ValueError:
            fail('完整场景修订追踪与发布冻结身份不一致')
        quality = review.get('coursewareQuality')
        if (quality_sha is None or not isinstance(quality, dict)
                or quality.get('schemaVersion') != 'mira.textbook.whole-course-quality-review.v1'
                or quality.get('status') != 'passed'
                or quality.get('policySha256') != complete_scene_followup['currentInteractionPolicySha256']
                or quality.get('sourceSha256') != frozen.get('sourceSha256')):
            fail('完整场景修订缺少对应规则和课件的本体质量证据')
    if 'audioContract' in frozen:
        from content.textbook_preview_audio_contract import audit_contract_identity, resolve_audio_contract
        plan = frozen['audioContract']
        contract = resolve_audio_contract(plan, {'editionId': binding['editionId'],
            'alignmentRevisionId': binding['alignmentRevisionId'], 'manifestSha256': digest(manifest),
            'nodeId': binding['nodeId'], 'gradeCode': frozen['gradeCode'], 'subject': frozen['subject']})
        if (contract['legacy'] or plan['previewKey'] != frozen['previewKey']
                or release['audioAudit'].get('contract') != audit_contract_identity(plan)):
            fail('发布配音合同与学科或审核身份不一致')
        from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA, validate_listening_review
        if 'visualAudioInheritanceSha256' in frozen or 'visualAudioInheritance' in release['audioAudit']:
            from content.textbook_operator_revision import validate_visual_audio_acceptance
            audit = release['audioAudit']
            evidence = audit.get('visualAudioInheritance', {})
            raw = audit.get('literalAudit', {})
            if (plan.get('schemaVersion') != PINYIN_SCHEMA
                    or frozen.get('visualAudioInheritanceSha256') != evidence.get('sha256')
                    or frozen.get('audioAuditSha256') != raw.get('sha256')
                    or audit.get('sha256') != raw.get('sha256')
                    or raw.get('sourceSha256') != frozen['sourceSha256']
                    or audit.get('literalPassed') is not raw.get('passed')
                    or audit.get('acceptanceMethod') != 'unchanged-published-audio'
                    or any(k in audit for k in ('pronunciationReview', 'listeningReview', 'reconciliation'))
                    or any(k in frozen for k in ('pronunciationReviewSha256', 'audioAcceptance'))
                    or audit.get('minSimilarityBps') != min((e.get('similarityBps', -1) for e in raw.get('segments', [])), default=-1)):
                fail('纯视觉拼音继承没有保持原审核与明确的证据边界')
            validate_visual_audio_acceptance(evidence, plan=plan, provenance=frozen.get('operatorParent'),
                classroom=release['classroom'], audit=raw, media=release['media'])
        elif plan.get('schemaVersion') == PINYIN_SCHEMA:
            from core.security import now_ms
            audit = release['audioAudit']
            operator_review = audit.get('pronunciationReview')
            if operator_review is not None or 'pronunciationReviewSha256' in frozen:
                from content.textbook_pinyin_operator_review import validate_operator_review, operator_acceptance_method
                if (not isinstance(operator_review, dict)
                        or frozen.get('pronunciationReviewSha256') != operator_review.get('sha256')
                        or not isinstance(frozen.get('sourceClassroomId'), str) or not frozen['sourceClassroomId']
                        or any(k in audit for k in ('listeningReview', 'reconciliation'))
                        or 'audioAcceptance' in frozen):
                    fail('自动审核记录与冻结身份不一致或混用了人工证据')
                heard = validate_operator_review(operator_review, plan=plan, classroom=release['classroom'],
                    audit=audit.get('literalAudit'), expected_source_sha256=frozen['sourceSha256'], now_ms=now_ms(),
                    expected_source_classroom_id=frozen['sourceClassroomId'])
            else:
                heard = validate_listening_review(plan, release['classroom'],
                    audit.get('listeningReview'), now_ms=now_ms())
            media = {item['path']: item for item in release['media']}
            for scene in release['classroom']['scenes']:
                for action in scene.get('actions', []):
                    item = heard.get((scene['id'], action['id']))
                    if item:
                        asset = media.get(action.get('audioUrl'), {})
                        if item['audioSha256'] != asset.get('sourceSha256', asset.get('sha256')):
                            fail('已发布拼音听验没有对应的审核原音频')
            acceptance = frozen.get('audioAcceptance')
            raw = audit.get('literalAudit', {})
            from content.textbook_preview_audio_contract import validate_v2_audit_segment
            origin_audit = (isinstance(operator_review, dict)
                and operator_review.get('schemaVersion') in (
                    'mira.textbook.pinyin-operator-review.v4-asr-origin',
                    'mira.textbook.pinyin-operator-review.v5-explicit-acceptance')
                and raw.get('schemaVersion') == 'mira.textbook.audio-audit.v3-asr-origin')
            observation_audit = (isinstance(operator_review, dict)
                and operator_review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v7-explicit-observation-acceptance'
                and raw.get('schemaVersion') == 'mira.textbook.audio-audit.v4-same-wav-observations')
            if (not isinstance(raw, dict) or (raw.get('schemaVersion') != 'mira.textbook.audio-audit.v2' and not origin_audit and not observation_audit)
                    or raw.get('sha256') != digest({k: v for k, v in raw.items() if k != 'sha256'})
                    or frozen.get('audioAuditSha256') != raw.get('sha256')
                    or audit.get('sha256') != raw.get('sha256')
                    or raw.get('sourceSha256') != frozen['sourceSha256']
                    or raw.get('previewKey') != frozen['previewKey']
                    or raw.get('contract') != audit_contract_identity(plan)
                    or raw.get('listeningReview') != audit.get('listeningReview')
                    or not isinstance(raw.get('segments'), list)):
                fail('正式拼音发布缺少冻结的完整原始音频审核')
            raw_segments = {}
            for entry in raw['segments']:
                if not isinstance(entry, dict) or type(entry.get('similarityBps')) is not int:
                    fail('正式拼音原始审核段落格式无效')
                key = (entry.get('sceneId'), entry.get('actionId'))
                if not all(isinstance(k, str) for k in key) or key in raw_segments:
                    fail('正式拼音音频审核段落身份重复或无效')
                raw_segments[key] = entry
            literal_results = []
            for scene in release['classroom']['scenes']:
                for action in scene.get('actions', []):
                    if action.get('type') != 'speech':
                        continue
                    entry = raw_segments.pop((scene['id'], action['id']), {})
                    if origin_audit or observation_audit:
                        # The origin-review validator rebuilt the complete source proof;
                        # retain its original literal result, never relabel receipts.
                        literal_results.append(entry['comparison']['passed'])
                    else:
                        literal_results.append(validate_v2_audit_segment(plan, action, entry, scene_id=scene['id']))
                    asset = media.get(action.get('audioUrl'), {})
                    if entry.get('audioSha256') != asset.get('sourceSha256', asset.get('sha256')):
                        fail('原始识别审核与已发布音频不一致')
            if (raw_segments or not literal_results or raw.get('passed') is not all(literal_results)
                    or audit.get('literalPassed') is not raw.get('passed')
                    or audit.get('minSimilarityBps') != min(item['similarityBps'] for item in raw['segments'])):
                fail('正式拼音原始识别结果与发布摘要不一致')
            if operator_review is not None:
                expected_method = operator_acceptance_method(operator_review)
                if (acceptance is not None or 'reconciliation' in audit
                        or audit.get('acceptanceMethod') != expected_method):
                    fail('自动审核接受方式与独立 ASR 证据不一致')
            elif raw['passed'] is False:
                from content.textbook_pinyin_asr_reconciliation import validate_reconciliation
                reconciled = audit.get('reconciliation', {})
                if (acceptance != {'method': 'human-listening-reconciliation',
                        'literalAuditSha256': raw.get('sha256'),
                        'reconciliationSha256': reconciled.get('sha256')}
                        or audit.get('literalPassed') is not False
                        or audit.get('acceptanceMethod') != 'human-listening-reconciliation'
                        or audit.get('sha256') != raw.get('sha256')
                        or audit.get('minSimilarityBps') != min(
                            (item.get('similarityBps', 0) for item in raw.get('segments', [])), default=-1)):
                    fail('拼音人工复核与原始识别审核未绑定')
                validate_reconciliation(reconciled, plan=plan, classroom=release['classroom'],
                    audit=raw, listening_review=audit.get('listeningReview'),
                    expected_source_sha256=frozen['sourceSha256'], now_ms=now_ms())
            elif (acceptance is not None or 'reconciliation' in audit
                    or audit.get('acceptanceMethod') != 'literal-asr'):
                fail('正式拼音音频接受方式与原始审核不一致')
        elif (frozen.get('subject') == 'english'
                and ('audioAcceptance' in frozen or 'reconciliation' in release['audioAudit'])):
            from content.textbook_english_asr_reconciliation import (
                METHOD as ENGLISH_RECONCILIATION_METHOD,
                validate_reconciliation as validate_english_reconciliation,
            )
            from content.textbook_preview_audio_contract import validate_v2_audit_segment
            from core.security import now_ms
            audit = release['audioAudit']
            raw = audit.get('literalAudit', {})
            reconciliation = audit.get('reconciliation', {})
            acceptance = frozen.get('audioAcceptance')
            if (not isinstance(frozen.get('sourceClassroomId'), str)
                    or not frozen['sourceClassroomId']
                    or raw.get('sha256') != digest({k: v for k, v in raw.items() if k != 'sha256'})
                    or frozen.get('audioAuditSha256') != raw.get('sha256')
                    or raw.get('sourceSha256') != frozen['sourceSha256']
                    or raw.get('previewKey') != frozen['previewKey']
                    or raw.get('contract') != audit_contract_identity(plan)
                    or raw.get('passed') is not False
                    or audit.get('sha256') != raw.get('sha256')
                    or audit.get('literalPassed') is not False
                    or audit.get('acceptanceMethod') != ENGLISH_RECONCILIATION_METHOD
                    or audit.get('minSimilarityBps') != min(
                        (item.get('similarityBps', -1) for item in raw.get('segments', [])), default=-1)
                    or acceptance != {'method': ENGLISH_RECONCILIATION_METHOD,
                        'literalAuditSha256': raw.get('sha256'),
                        'reconciliationSha256': reconciliation.get('sha256')}
                    or any(k in frozen for k in ('pronunciationReviewSha256', 'visualAudioInheritanceSha256'))
                    or any(k in audit for k in ('pronunciationReview', 'visualAudioInheritance', 'listeningReview'))):
                fail('英语正字法复核没有保持完整原始审核和冻结身份')
            validate_english_reconciliation(reconciliation, plan=plan,
                classroom=release['classroom'], audit=raw,
                expected_source_sha256=frozen['sourceSha256'], now_ms=now_ms(),
                expected_source_classroom_id=frozen['sourceClassroomId'])
            raw_segments = {(item.get('sceneId'), item.get('actionId')): item
                            for item in raw.get('segments', []) if isinstance(item, dict)}
            if len(raw_segments) != len(raw.get('segments', [])):
                fail('英语原始审核段落身份重复或无效')
            media = {item['path']: item for item in release['media']}
            for scene in release['classroom']['scenes']:
                for action in scene.get('actions', []):
                    if action.get('type') != 'speech':
                        continue
                    entry = raw_segments.pop((scene['id'], action['id']), {})
                    validate_v2_audit_segment(plan, action, entry, scene_id=scene['id'])
                    asset = media.get(action.get('audioUrl'), {})
                    if entry.get('audioSha256') != asset.get('sourceSha256', asset.get('sha256')):
                        fail('英语原始识别审核与已发布音频不一致')
            if raw_segments:
                fail('英语原始审核包含额外段落')
        elif ('audioAcceptance' in frozen or 'pronunciationReviewSha256' in frozen
                or 'pronunciationReview' in release['audioAudit']
                or 'reconciliation' in release['audioAudit']):
            fail('配音复核不能用于其他学科或合同')
    elif ('audioAcceptance' in frozen or 'pronunciationReviewSha256' in frozen
            or 'visualAudioInheritanceSha256' in frozen
            or 'visualAudioInheritance' in release.get('audioAudit', {})
            or 'pronunciationReview' in release.get('audioAudit', {})):
        fail('人工拼音复核缺少配音合同')
    if 'operatorParent' in frozen:
        from content.textbook_operator_revision import validate_published_inheritance, validate_quiz_revision_binding
        validate_published_inheritance(frozen, release)
        if course is not None:
            validate_quiz_revision_binding(frozen['operatorParent'], release['classroom'], media=release['media'],
                                          course_questions=parse(course['content_json']).get('questions', []))
    return release


def public_classroom(release):
    """Project a verified release for playback without changing its signed bytes."""
    content = deepcopy(release['classroom'])
    allowed_stage = {'id', 'name', 'style', 'createdAt', 'updatedAt', 'agentIds'}
    content['stage'] = {k: v for k, v in content['stage'].items() if k in allowed_stage}
    content['stage']['fixedTextbook'] = True
    if release.get('assessmentMode') == 'ungraded':
        content['stage']['miraUngradedActivity'] = True
    for scene in content['scenes']:
        # Older revision archives can retain an internal preview stage alias.
        # Scene IDs remain the learning-progress identity; their playback owner
        # is always this already-verified published classroom, not that alias.
        scene['stageId'] = release['classroomId']
        if scene['type'] == 'quiz':
            # Reviewed pictures carry no answer: a child who cannot read the
            # option labels still needs them to tell the choices apart.
            scene['content']['questions'] = [{k: v for k, v in q.items()
                if k in {'id', 'type', 'question', 'options', 'points', 'questionAudioUrl', 'visual', 'optionVisuals'}}
                for q in scene['content']['questions']]
        elif scene['type'] == 'interactive':
            html = scene['content'].get('html', '')
            # The reviewed role game queues named narration clips. Resolve its
            # original dynamic filename expression to the audited speech IDs,
            # so the gateway can embed the exact published assets for srcdoc.
            queued_audio = r"player\.src='/api/classroom-media/[A-Za-z0-9_-]+/audio/'\+queue\.shift\(\)\+'\.wav'"
            if re.search(queued_audio, html):
                aliases = {a['id'][7:]: a['audioUrl'] for a in scene.get('actions', [])
                           if a.get('type') == 'speech' and a.get('id', '').startswith('review_')
                           and isinstance(a.get('audioUrl'), str)}
                required = {'speaker-teal', 'speaker-coral', 'cue-me', 'cue-you', 'cue-he'}
                allowed = {m['path'] for m in release['media'] if m.get('mimeType', '').startswith('audio/')}
                if not required.issubset(aliases) or any(aliases[key] not in allowed for key in required):
                    fail('互动听题素材不完整')
                sources = canonical({key: aliases[key] for key in sorted(required)})
                scene['content']['html'] = re.sub(queued_audio, lambda _: f'player.src=({sources})[queue.shift()]', html)
    return content


def grade_answers(release, answers, *, partial=False):
    """Grade a lesson's answers; ``partial`` grades one in-class check at a time."""
    items = check_questions(release['classroom'])
    known = {q['id'] for q in items}
    if not isinstance(answers, dict) or not answers or (set(answers) != known and not (partial and set(answers) < known)):
        raise ApiError('textbook_answers_invalid', '请完成每道题再提交', 400)
    results = []
    for q in items:
        if q['id'] not in answers:
            continue
        answer = answers[q['id']]
        if not isinstance(answer, str) or answer not in {o['value'] for o in q['options']}:
            raise ApiError('textbook_answers_invalid', '选项无效，请重新选择', 400)
        expected = single_answer(q)
        correct = answer == expected
        results.append({'questionId': q['id'], 'response': answer, 'correct': correct,
            'score': q.get('points', 1) if correct else 0, 'maxScore': q.get('points', 1),
            'explanation': q['analysis'], 'correctAnswer': expected,
            **({'feedback': deepcopy(q['optionFeedback'][answer])} if q.get('optionFeedback') else {})})
    return {'results': results, 'score': sum(r['score'] for r in results),
            'maxScore': sum(r['maxScore'] for r in results),
            'correctCount': sum(r['correct'] for r in results), 'totalQuestions': len(results)}
