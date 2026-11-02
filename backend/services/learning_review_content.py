"""Offline review-pack production; student reads never dispatch provider work.

Original files, paid-call intents/results, approvals and pack versions are
immutable. An interrupted/unknown dispatch is a fence, not permission to retry.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import io
import wave
import zipfile

from content.learning_review_content import (PACK_SCHEMA, SHA, MEDIA_TOKEN, ReviewContentError,
    canonical, digest, media_token, public_question, require, reviewed_at, text, validate_media, validate_questions, validate_source)
from services.course_file_store import CourseFileStore, course_bytes, course_glob


ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = ROOT / 'output/learning-review-content'
PROMPTS = ROOT / 'backend/prompts'
MAX_BYTES = 32 * 1024 * 1024


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(course_bytes(Path(path), max_bytes=MAX_BYTES))


def checked_file(path, expected=None):
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    require('..' not in path.parts and path.absolute().is_relative_to(ROOT)
        and not path.is_symlink(), 'review_source_path_invalid')
    current = path
    while current != ROOT:
        require(not current.is_symlink(), 'review_source_path_invalid')
        require(not re.fullmatch(r'(?i)(?:\.env(?:\..*)?|owner\.cookies|.*\.pem|.*\.key)', current.name),
            'review_source_path_invalid')
        current = current.parent
    raw = course_bytes(path, expected_sha256=expected, max_bytes=MAX_BYTES)
    require(0 < len(raw) <= MAX_BYTES, 'review_source_size_invalid')
    return path, raw


def checked_media(asset):
    path, raw = checked_file(asset['path'], asset['sha256'])
    if asset['mimeType'].startswith('image/'):
        from PIL import Image
        try:
            with Image.open(io.BytesIO(raw)) as image:
                require(image.format == {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}[asset['mimeType']]
                    and 64 <= image.width <= 4096 and 64 <= image.height <= 4096, 'review_image_invalid')
                image.verify()
        except (OSError, ValueError):
            raise ReviewContentError('review_image_invalid') from None
    elif asset['mimeType'].startswith('audio/'):
        # New packs use the existing Qwen PCM WAV output, never system/browser speech.
        require(asset['mimeType'] == 'audio/wav', 'review_teacher_audio_format_invalid')
        try:
            with wave.open(io.BytesIO(raw), 'rb') as wav:
                require(wav.getnchannels() == 1 and wav.getsampwidth() == 2
                    and 16000 <= wav.getframerate() <= 48000
                    and 0.3 <= wav.getnframes() / wav.getframerate() <= 120, 'review_teacher_audio_format_invalid')
        except (wave.Error, EOFError):
            raise ReviewContentError('review_teacher_audio_format_invalid') from None
    return path, raw


def immutable(path, value, *, raw=False):
    path = Path(path)
    data = value if raw else (canonical(value) + '\n').encode()
    if path.exists() or CourseFileStore().resolve(path) is not None:
        require(course_bytes(path, max_bytes=MAX_BYTES) == data, 'review_immutable_conflict')
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
    except BaseException:
        # A partial intent remains a fence; never erase a possibly dispatched call.
        raise


def validate_release_identity(conn, source):
    identity, binding = source['sourceIdentity'], source['binding']
    row = conn.execute('SELECT b.*,c.subject,c.grade_code,c.status AS course_status '
        'FROM learning_textbook_course_builds b JOIN learning_courses c '
        'ON c.id=b.course_id AND c.version=b.course_version WHERE b.content_key=?',
        (identity['contentKey'],)).fetchone()
    require(row is not None, 'review_published_source_missing')
    row = dict(row)
    review = json.loads(row['review_json']) if isinstance(row['review_json'], str) else row['review_json']
    require(row['status'] == 'published' and row['course_status'] == 'published'
        and all(row[k] == identity[v] for k, v in [('course_id', 'courseId'), ('course_version', 'courseVersion')])
        and all(row[k] == binding[v] for k, v in [('edition_id', 'editionId'), ('revision_id', 'revisionId'),
            ('node_id', 'nodeId'), ('subject', 'subject'), ('grade_code', 'gradeCode')])
        and (review.get('release') or {}).get('sha256') == identity['releaseSha256'],
        'review_published_source_mismatch')


def source_from_assignment_record(path, *, source_identity, media, reviewer, target_texts=None):
    """Bind our actual reviewed assignment record; never invent a downloaded PDF SHA."""
    path, raw = checked_file(path)
    record = json.loads(raw)
    require(record.get('schemaVersion') == 'mira.textbook.post-class-practice.v1'
        and text(reviewer) and isinstance(record.get('sources'), list) and record['sources'],
        'review_assignment_record_invalid')
    references = record['sources']
    require(all(r.get('sourceKind') == 'reviewed-official-assignment-record'
        and r.get('originalFileDownloaded') is False for r in references), 'review_official_download_claim_invalid')
    target_texts = target_texts or {}
    objectives = []
    binding = deepcopy(record['binding'])
    for goal in record.get('goals', []):
        target = goal['targetId']
        objectives.append({'id': target, 'label': goal['objective'],
            'knowledgeId': ':'.join((binding['subject'], binding['gradeCode'], binding['editionId'], binding['nodeId'], target)),
            **({'targetTexts': target_texts[target]} if target in target_texts else {})})
    source = {'schemaVersion': 'mira.learning.review-source.v1', 'binding': binding,
        'sourceIdentity': deepcopy(source_identity), 'objectives': objectives, 'media': deepcopy(media),
        'officialExercise': {'path': str(path), 'sha256': raw_sha(raw),
            'sourceKind': 'reviewed-official-assignment-record', 'originalFileDownloaded': False,
            'sourceUrl': references[0]['sourceUrl'], 'references': deepcopy(references),
            'locations': [r['classHourId'] + ': ' + p for r in references for p in r['locations']],
            'findings': [f for r in references for f in r['findings']],
            'reviewer': reviewer, 'reviewedAt': record['reviewedAt'],
            'exerciseText': '\n'.join(r['classHourId'] + ': ' + '；'.join(r['findings']) for r in references)},
        'originalScope': {'allowed': [g['objective'] for g in record['goals']],
            'excluded': ['不扩展到未学目标，不复制官方题目或版式。',
                '图片选择不推断未知口语、发音、背诵或纸笔书写；这些目标的证据不足须保留缺口。']}}
    return validate_source(source)


def configured_provider():
    """The existing App AI configuration is the sole provider authority."""
    from core.config import AppConfig
    from services.ai_text_provider import OpenAICompatibleTextProvider
    c = AppConfig.from_env()
    require(all(text(v) for v in (c.AI_PROVIDER, c.AI_MODEL, c.AI_API_KEY, c.AI_BASE_URL)),
        'review_ai_unconfigured')
    return OpenAICompatibleTextProvider(provider_name=c.AI_PROVIDER, api_key=c.AI_API_KEY,
        base_url=c.AI_BASE_URL, model_name=c.AI_MODEL, timeout_seconds=c.AI_TIMEOUT_SECONDS,
        disable_thinking=c.AI_PROVIDER in {'kimi', 'moonshot'})


class ReviewPackProducer:
    def __init__(self, *, root=PACK_ROOT, provider=None):
        self.root = Path(root)
        self.provider = provider

    def _provider(self):
        return self.provider or configured_provider()

    def prepare(self, source, *, request_id, question_count=5, conn=None):
        validate_source(source)
        require(len(canonical(source).encode()) <= 120000, 'review_source_context_too_large')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', str(request_id))
            and type(question_count) is int and 1 <= question_count <= 30, 'review_request_invalid')
        if conn is not None:
            validate_release_identity(conn, source)
        # A new request name must not reset the charge/ambiguity fence for the
        # exact same reviewed source. Resolve the original paid receipt first.
        for original in (self.root / 'jobs').glob('*/input.json'):
            if original.parent.name == request_id:
                continue
            prior = read_json(original)
            if prior.get('sourceSha256') != digest(source):
                continue
            unresolved = any((original.parent / (phase + '-intent.json')).exists()
                and not (original.parent / (phase + '-result.json')).exists()
                for phase in ('generation', 'verification'))
            unresolved |= any(not (p.parent / 'response.json').exists()
                for p in (original.parent / 'audio').glob('*/intent.json'))
            require(not unresolved, 'review_source_dispatch_ambiguous')
        checked_file(source['officialExercise']['path'], source['officialExercise']['sha256'])
        for asset in source['media']:
            checked_media(asset)
        provider = self._provider()
        require(all(text(getattr(provider, k, None), 255) for k in ('provider_name', 'model_name')),
            'review_ai_unconfigured')
        from services.prompt_registry import PromptRegistry
        prompts = PromptRegistry(PROMPTS)
        generation = prompts.get_prompt('learning.review-variants', 'v1')
        verification = prompts.get_prompt('learning.review-verification', 'v1')
        require(generation is not None and verification is not None, 'review_prompt_missing')
        from content.teacher_profiles import get_formal_subject_qwen_voice_identity
        teacher = get_formal_subject_qwen_voice_identity(source['binding']['subject']).to_target_payload()
        frozen = {'schemaVersion': 'mira.learning.review-generation.v1', 'requestId': request_id,
            'source': deepcopy(source), 'sourceSha256': digest(source), 'questionCount': question_count,
            'provider': provider.provider_name, 'model': provider.model_name,
            'generationPrompt': generation.body, 'generationPromptSha256': raw_sha(generation.body.encode()),
            'verificationPrompt': verification.body, 'verificationPromptSha256': raw_sha(verification.body.encode()),
            'promptVersion': 'learning.review-variants:v1', 'teacherContract': teacher, 'maximumProviderCalls': 2}
        job = self.root / 'jobs' / request_id
        immutable(job / 'input.json', frozen)
        return {'requestId': request_id, 'inputSha256': digest(frozen), 'path': str(job), 'status': 'prepared'}

    def _call(self, job, frozen, phase, system, user):
        result_path, intent = job / (phase + '-result.json'), job / (phase + '-intent.json')
        if result_path.exists():
            record = read_json(result_path)
            require(record['inputSha256'] == digest(frozen) and record['requestSha256'] == digest(user),
                'review_provider_result_mismatch')
            return record['output']
        require(not intent.exists(), 'review_provider_dispatch_ambiguous')
        provider = self._provider()
        require((provider.provider_name, provider.model_name) == (frozen['provider'], frozen['model']),
            'review_provider_changed')
        immutable(intent, {'inputSha256': digest(frozen), 'requestSha256': digest(user),
            'systemSha256': raw_sha(system.encode()), 'provider': frozen['provider'], 'model': frozen['model']})
        # Exactly one attempt; even a missing response keeps the dispatch fence.
        response = provider.complete(system_prompt=system, user_prompt=canonical(user), max_tokens=12000, temperature=0.2)
        require(response is not None, 'review_provider_dispatch_ambiguous')
        require((response.provider, response.model) == (frozen['provider'], frozen['model']),
            'review_provider_changed')
        # Preserve original text before decoding/validation; invalid paid output is never silently repeated.
        immutable(job / (phase + '-response.txt'), response.text.encode(), raw=True)
        try:
            output = json.loads(response.text)
        except (ValueError, TypeError):
            raise ReviewContentError('review_provider_json_invalid') from None
        immutable(result_path, {'inputSha256': digest(frozen), 'requestSha256': digest(user), 'output': output,
            'responseSha256': raw_sha(response.text.encode()), 'provider': response.provider, 'model': response.model})
        return output

    def generate(self, request_id):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', str(request_id)), 'review_request_invalid')
        job = self.root / 'jobs' / request_id
        require(job.is_dir() and not job.is_symlink(), 'review_job_missing')
        with (job / '.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (job / 'draft.json').exists():
                return read_json(job / 'draft.json')
            frozen = read_json(job / 'input.json'); source = frozen['source']; validate_source(source)
            require(digest(source) == frozen['sourceSha256'], 'review_source_changed')
            # File integrity is rechecked at dispatch, outside any DB transaction.
            checked_file(source['officialExercise']['path'], source['officialExercise']['sha256'])
            for asset in source['media']:
                checked_media(asset)
            public_source = deepcopy(source)
            public_source['officialExercise'].pop('path', None)
            public_source['officialExercise'].pop('reviewer', None)
            public_source['media'] = [{k: a[k] for k in ('id', 'sha256', 'mimeType', 'meaning', 'text') if k in a}
                for a in source['media']]
            output = self._call(job, frozen, 'generation', frozen['generationPrompt'],
                {'source': public_source, 'questionCount': frozen['questionCount']})
            questions = validate_questions(output.get('questions') if isinstance(output, dict) else None, source)
            require(len(questions) == frozen['questionCount'], 'review_question_count_mismatch')
            public = [{k: deepcopy(v) for k, v in q.items() if k not in ('correctAnswer', 'explanation', 'hints', 'fingerprint')}
                for q in questions]
            verified = self._call(job, frozen, 'verification', frozen['verificationPrompt'],
                {'source': public_source, 'questions': public})
            answers = verified.get('answers') if isinstance(verified, dict) else None
            require(isinstance(answers, list) and len(answers) == len(questions)
                and all(isinstance(a, dict) and a.get('id') == q['id'] and a.get('accepted') is True
                    and a.get('answer') == q['correctAnswer'] and text(a.get('reason'))
                    for a, q in zip(answers, questions)), 'review_independent_verification_failed')
            draft = {'schemaVersion': PACK_SCHEMA, 'source': source, 'questions': questions,
                'generation': {k: frozen[k] for k in ('requestId', 'sourceSha256', 'provider', 'model',
                    'promptVersion', 'generationPromptSha256', 'verificationPromptSha256')},
                'verificationSha256': digest(verified), 'status': 'needs_media_and_review'}
            draft['teacherContract'] = deepcopy(frozen['teacherContract'])
            immutable(job / 'draft.json', draft)
            return draft

    def narrate(self, request_id, *, transport=None):
        """Pre-record exact neutral instructions through the existing server Qwen registry.

        This is a separate explicitly executed operator/worker step. Chinese
        Latin/pinyin requires already verified lesson-specific audio, never a
        guessed pronunciation sent through plain Chinese TTS.
        """
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', str(request_id)), 'review_request_invalid')
        job = self.root / 'jobs' / request_id
        draft = read_json(job / 'draft.json')
        teacher = draft['teacherContract']
        spoken = list(dict.fromkeys(t for q in draft['questions'] for t in [q['prompt'], *q['hints'], q['explanation']]))
        require(0 < len(spoken) <= 128 and sum(len(t) for t in spoken) <= 30000
            and all(0 < len(t) <= 1000 for t in spoken), 'review_audio_budget_exceeded')
        require(draft['source']['binding']['subject'] != 'chinese'
            or not any(re.search(r'[A-Za-z]', t) for t in spoken), 'review_audio_pronunciation_review_required')
        if transport is None:
            from core.config import AppConfig
            from services.homework_audio_service import HomeworkAudioService
            config = AppConfig.from_env()
            require(config.OPENMAIC_FULL_RUNTIME_ENABLED and text(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL),
                'review_audio_unconfigured')
            # Reuse only the existing configured HTTP transport. No homework
            # submission, classroom authority or student record is fabricated.
            transport = HomeworkAudioService(None, asset_store=None,
                runtime_base_url=config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL)._request
        plan = {'schemaVersion': 'mira.learning.review-audio-plan.v1', 'draftSha256': digest(draft),
            'teacherContract': teacher, 'texts': spoken, 'maximumCalls': 128, 'maximumCharacters': 30000}
        immutable(job / 'audio-plan.json', plan)
        assets = []
        with (job / '.audio-lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            for spoken_text in spoken:
                text_sha = raw_sha(spoken_text.encode())
                audio_id = 'reviewtts_' + digest([digest(plan), text_sha])
                folder = job / 'audio' / text_sha
                payload = {'text': spoken_text, 'audioId': audio_id, 'ttsProviderId': teacher['tts']['providerId'],
                    'ttsModelId': teacher['tts']['modelId'], 'ttsVoice': teacher['voiceId'], 'ttsSpeed': 1.0}
                response_path = folder / 'response.json'
                if response_path.exists():
                    result = read_json(response_path)
                else:
                    require(not (folder / 'intent.json').exists(), 'review_audio_dispatch_ambiguous')
                    immutable(folder / 'intent.json', {'planSha256': digest(plan), 'request': payload})
                    try:
                        result = transport(payload, {})
                    except Exception:
                        raise ReviewContentError('review_audio_dispatch_ambiguous') from None
                    immutable(response_path, result)
                require(isinstance(result, dict) and result.get('success') is True
                    and result.get('audioId') == audio_id and result.get('format') == 'wav',
                    'review_audio_response_invalid')
                try:
                    raw = base64.b64decode(result['base64'], validate=True)
                except (ValueError, KeyError, TypeError):
                    raise ReviewContentError('review_audio_response_invalid') from None
                audio_path = folder / 'audio.wav'
                immutable(audio_path, raw, raw=True)
                proof = {'schemaVersion': 'mira.learning.review-audio-receipt.v1',
                    'providerId': teacher['tts']['providerId'], 'modelId': teacher['tts']['modelId'],
                    'voiceId': teacher['voiceId'], 'teacherProfileId': teacher['teacherProfile']['id'],
                    'teacherProfileSha256': teacher['teacherProfile']['contentHash'], 'fallbackUsed': False,
                    'textSha256': text_sha, 'sha256': raw_sha(raw), 'requestId': audio_id,
                    'requestSha256': digest(payload), 'planSha256': digest(plan),
                    'responsePath': str(response_path), 'responseSha256': raw_sha(course_bytes(response_path))}
                receipt_path = folder / 'receipt.json'; immutable(receipt_path, proof)
                asset = {'id': 'audio-' + text_sha, 'path': str(audio_path), 'sha256': raw_sha(raw),
                    'mimeType': 'audio/wav', 'meaning': spoken_text, 'text': spoken_text,
                    'providerId': proof['providerId'], 'voiceId': proof['voiceId'], 'fallbackUsed': False,
                    'teacherProfileId': proof['teacherProfileId'], 'providerReceiptPath': str(receipt_path),
                    'providerReceiptSha256': raw_sha(course_bytes(receipt_path))}
                checked_media(asset)
                assets.append(asset)
        immutable(job / 'audio-media.json', assets)
        return {'status': 'audio_recorded_needs_review', 'segments': len(assets), 'mediaPath': str(job / 'audio-media.json')}

    def approve(self, request_id, *, media, review, conn):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', str(request_id)), 'review_request_invalid')
        job = self.root / 'jobs' / request_id
        draft = read_json(job / 'draft.json'); source = validate_source(draft['source'])
        validate_release_identity(conn, source)
        require(isinstance(review, dict) and review.get('draftSha256') == digest(draft)
            and review.get('reviewKind') in {'ai', 'maintainer', 'user'}
            and all(review.get(k) is True for k in ('sourceScopeConfirmed', 'originalExpressionConfirmed',
                'imagesConfirmed', 'teacherAudioConfirmed', 'independentAnswersConfirmed', 'approvedForStudent'))
            and all(text(review.get(k)) for k in ('reviewer', 'reviewedAt', 'basis')),
            'review_pack_approval_required')
        require(review.get('humanListeningVerified', False) is False or review['reviewKind'] in {'maintainer', 'user'},
            'review_listening_evidence_misrepresented')
        reviewed_at(review['reviewedAt'])
        require('humanListeningVerified' not in review or type(review['humanListeningVerified']) is bool,
            'review_listening_evidence_misrepresented')
        require(isinstance(media, list), 'review_pack_media_invalid')
        assets = deepcopy(source['media']) + deepcopy(media)
        ids, audio_texts = set(), {}
        for asset in assets:
            validate_media(asset)
            require(asset['id'] not in ids, 'review_media_duplicate'); ids.add(asset['id'])
            _, raw = checked_media(asset)
            if asset['mimeType'].startswith('audio/'):
                require(asset.get('providerId') == 'qwen-tts' and asset.get('fallbackUsed') is False
                    and text(asset.get('text')) and text(asset.get('voiceId'))
                    and text(asset.get('teacherProfileId')) and SHA.fullmatch(str(asset.get('providerReceiptSha256', '')))
                    and text(asset.get('providerReceiptPath')), 'review_teacher_audio_unverified')
                require(asset['voiceId'] == draft['teacherContract']['voiceId']
                    and asset['teacherProfileId'] == draft['teacherContract']['teacherProfile']['id'],
                    'review_teacher_identity_mismatch')
                require(asset['sha256'] not in audio_texts or audio_texts[asset['sha256']] == asset['text'],
                    'review_audio_text_conflict')
                audio_texts[asset['sha256']] = asset['text']
                _, receipt = checked_file(asset['providerReceiptPath'], asset['providerReceiptSha256'])
                proof = json.loads(receipt)
                require(proof.get('providerId') == 'qwen-tts' and proof.get('fallbackUsed') is False
                    and proof.get('textSha256') == raw_sha(asset['text'].encode())
                    and proof.get('sha256') == raw_sha(raw) and proof.get('voiceId') == asset['voiceId']
                    and proof.get('teacherProfileId') == asset['teacherProfileId'], 'review_teacher_audio_unverified')
        pack = {**draft, 'assets': assets, 'review': deepcopy(review), 'status': 'approved'}
        pack_sha = digest(pack)
        for q in pack['questions']:
            public_question(q, source, assets, pack_sha)  # Every prompt/hint/explanation needs exact real audio.
        directory = self.root / 'packs' / pack_sha
        immutable(directory / 'pack.json', pack)
        immutable(directory / 'approval.json', {'schemaVersion': 'mira.learning.review-approval.v1',
            'packSha256': pack_sha, 'sourceSha256': digest(source), 'reviewSha256': digest(review)})
        return {'status': 'approved', 'packSha256': pack_sha, 'path': str(directory / 'pack.json')}


def _learned(conn, child, source, target, knowledge):
    identity = source['sourceIdentity']
    # A completed authority establishes learning exposure, never mastery. Merely
    # opening a classroom, calendar placement or a task timer is insufficient.
    completed = conn.execute("SELECT id FROM learning_sessions WHERE family_id=? AND child_id=? "
        "AND course_id=? AND course_version=? AND status='completed' AND completed_at IS NOT NULL LIMIT 1",
        (child['family_id'], child['id'], identity['courseId'], identity['courseVersion'])).fetchone()
    if completed:
        return True
    rows = conn.execute("SELECT question_json FROM learning_answer_events WHERE family_id=? AND child_id=? "
        "AND grade_code=? AND source_kind IN ('classroom','textbook_play') AND revoked_at IS NULL "
        "AND confirmed=1 AND correct IS NOT NULL", (child['family_id'], child['id'], child['grade_code'])).fetchall()
    for row in rows:
        q = json.loads(row['question_json']) if isinstance(row['question_json'], str) else row['question_json']
        if (q.get('courseId'), q.get('courseVersion')) == (identity['courseId'], identity['courseVersion']) \
                and (q.get('targetId') == target or q.get('knowledgeId') == knowledge):
            return True
    return False


def approved_question_pool(conn, child):
    result, gaps = [], []
    for marker in course_glob(PACK_ROOT / 'packs', '*/approval.json'):
        try:
            approval = read_json(marker); sha = approval['packSha256']
            require(SHA.fullmatch(sha) and marker.parent.name == sha, 'review_pack_identity_invalid')
            pack = read_json(marker.parent / 'pack.json')
            require(digest(pack) == sha and pack.get('status') == 'approved'
                and approval['sourceSha256'] == digest(pack['source'])
                and approval['reviewSha256'] == digest(pack['review']), 'review_pack_integrity_failed')
            require_archived_pack(marker.parent, sha)
            source = validate_source(pack['source'])
            if source['binding']['gradeCode'] != child['grade_code']:
                continue
            validate_release_identity(conn, source)
            for asset in pack['assets']:
                checked_media(asset)
            for raw in validate_questions(pack['questions'], source):
                q = public_question(raw, source, pack['assets'], sha)
                if _learned(conn, child, source, q['targetId'], q['knowledgeId']):
                    q['learnedScopeVerified'] = True
                    result.append(q)
        except (ValueError, OSError, KeyError, TypeError):
            gaps.append('一份教材复习题包来源或媒体暂不可用')
    return result, sorted(set(gaps))


def require_archived_pack(directory, pack_sha):
    """Approval is not delivery: only a verified, registry-readable pack is eligible."""
    from core.course_storage_config import CourseStorageConfig
    from repositories.course_storage_repository import storage_id_for, storage_identity
    config = CourseStorageConfig.from_env()
    store = CourseFileStore()
    try:
        receipt = read_json(Path(directory) / 'archive-receipt.json')
    except FileNotFoundError:
        # The upload proof cannot be inside its own ZIP. Preserve it in the
        # existing immutable registry metadata so local-source eviction does
        # not make an otherwise verified remote pack disappear.
        storage_id = storage_id_for(config.endpoint, config.bucket, config.region)
        scope = store.repository.scope(digest(['review_question_pack', pack_sha]), storage_id)
        require(scope is not None, 'review_pack_not_registered')
        receipt = scope['metadata'].get('archiveVerification')
    require(isinstance(receipt, dict), 'review_pack_not_archived')
    require(config.mode == 'registry' and receipt.get('schemaVersion') == 'mira.course-archive.verification.v1'
        and receipt.get('complete') is True and receipt.get('sourceDigest') == pack_sha
        and receipt.get('archiveId') == 'review-' + pack_sha[:24]
        and receipt.get('storage') == storage_identity(config.endpoint, config.bucket, config.region),
        'review_pack_not_archived')
    path = Path(directory) / 'pack.json'
    entry = store.resolve(path)
    require(entry is not None, 'review_pack_not_registered')
    checked_file(path, entry['sha256'])


def review_pack_media_file(token):
    require(MEDIA_TOKEN.fullmatch(str(token)), 'review_media_token_invalid')
    broken = False
    for marker in course_glob(PACK_ROOT / 'packs', '*/approval.json'):
        try:
            approval = read_json(marker); pack = read_json(marker.parent / 'pack.json')
            require(digest(pack) == approval['packSha256'] == marker.parent.name
                and pack.get('status') == 'approved', 'review_pack_integrity_failed')
            require_archived_pack(marker.parent, approval['packSha256'])
        except (OSError, ValueError, TypeError, KeyError):
            broken = True
            continue
        for asset in pack['assets']:
            if asset['mimeType'].split('/')[0] in {'audio', 'image'} and media_token(asset) == token:
                _, raw = checked_media(asset)
                # CourseFileStore may have verified remote bytes while a stale
                # local original still exists. Serve those exact verified bytes;
                # reopening the local filename would break that guarantee.
                return io.BytesIO(raw)
    if broken:
        raise ReviewContentError('review_pack_integrity_failed')
    raise FileNotFoundError('review_pack_media_not_found')


def archive_pack(pack_sha, *, root=PACK_ROOT, client=None, repository=None, config=None):
    """Use the existing conditional uploader + full readback + registry, no course rows."""
    from core.course_storage_config import CourseStorageConfig
    from repositories.course_storage_repository import storage_id_for
    from services.course_archive_queue import NodeArchiveClient
    require(SHA.fullmatch(str(pack_sha)), 'review_pack_identity_invalid')
    directory = Path(root) / 'packs' / pack_sha
    pack_path = directory / 'pack.json'; pack = read_json(pack_path)
    require(digest(pack) == pack_sha, 'review_pack_integrity_failed')
    approval = read_json(directory / 'approval.json')
    require(pack.get('status') == 'approved' and approval.get('packSha256') == pack_sha
        and approval.get('sourceSha256') == digest(pack['source'])
        and approval.get('reviewSha256') == digest(pack['review']), 'review_pack_integrity_failed')
    source = pack['source']; validate_source(source)
    checked_file(source['officialExercise']['path'], source['officialExercise']['sha256'])
    for asset in pack['assets']:
        checked_media(asset)
        if asset.get('providerReceiptPath'):
            checked_file(asset['providerReceiptPath'], asset['providerReceiptSha256'])
    config = config or CourseStorageConfig.from_env()
    require(config.mode == 'registry' and repository is not None, 'review_archive_registry_required')
    storage = {'endpoint': config.endpoint.rstrip('/'), 'bucket': config.bucket, 'region': config.region}
    entries = [pack_path, directory / 'approval.json', Path(source['officialExercise']['path'])]
    job = Path(root) / 'jobs' / pack['generation']['requestId']
    for name in ('input.json', 'draft.json', 'generation-intent.json', 'generation-result.json',
                 'generation-response.txt', 'verification-intent.json', 'verification-result.json',
                 'verification-response.txt', 'audio-plan.json', 'audio-media.json'):
        if (job / name).exists() or CourseFileStore().resolve(job / name) is not None:
            entries.append(job / name)
    for a in pack['assets']:
        entries.append(Path(a['path']))
        if a.get('providerReceiptPath'):
            entries.append(Path(a['providerReceiptPath']))
            proof = read_json(a['providerReceiptPath'])
            if proof.get('responsePath'):
                checked_file(proof['responsePath'], proof['responseSha256'])
                entries.append(Path(proof['responsePath']))
    files = {}
    total_bytes = 0
    for entry in entries:
        path, raw = checked_file(entry)
        relative = path.relative_to(ROOT).as_posix()
        if relative not in files:
            total_bytes += len(raw)
        require(total_bytes <= 256 * 1024 * 1024, 'review_archive_too_large')
        files[relative] = (raw, 'application/json' if path.suffix == '.json' else
            next((a['mimeType'] for a in pack['assets'] if Path(a['path']).resolve() == path.resolve()),
                'application/pdf' if path.suffix.lower() == '.pdf' else 'text/plain'))
    archive_id = 'review-' + pack_sha[:24]
    stage = ROOT / 'backend/data/course-storage/archives' / archive_id
    stage.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Date comes from approval, so retrying tomorrow cannot create a new identity.
    date = reviewed_at(pack['review']['reviewedAt']).date().isoformat()
    b = source['binding']; object_directory = '/'.join((b['subject'], b['editionId'], b['gradeCode'], date,
        b['nodeId'] + '-review-' + pack_sha[:12]))
    manifest = {'schemaVersion': 'mira.learning.review-archive.v1', 'packSha256': pack_sha,
        'files': [{'sourcePath': p, 'sha256': raw_sha(v[0]), 'byteSize': len(v[0]), 'mimeType': v[1]}
            for p, v in sorted(files.items())]}
    immutable(stage / 'manifest.json', manifest)
    zip_path = stage / 'review-pack.zip'
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_STORED) as archive:
            for path, (raw, _) in sorted(files.items()):
                info = zipfile.ZipInfo('files/' + path, date_time=(1980, 1, 1, 0, 0, 0))
                archive.writestr(info, raw)
    generated = []
    for path in (stage / 'manifest.json', zip_path):
        raw = path.read_bytes()
        generated.append({'localPath': str(path), 'relativePath': object_directory + '/' + path.name,
            'sha256': raw_sha(raw), 'byteSize': len(raw),
            'mimeType': 'application/zip' if path.suffix == '.zip' else 'application/json'})
    index = {'schemaVersion': 'mira.course-archive.export.v1', 'archiveId': archive_id,
        'sourceKind': 'review_question_pack', 'sourceDigest': pack_sha, 'complete': True,
        'missingSources': [], 'generatedPublicFiles': generated}
    immutable(stage / 'index.json', index)
    receipt = (client or NodeArchiveClient(project_root=ROOT,
        node=os.getenv('COURSE_ARCHIVE_NODE') or os.getenv('MIRA_NODE_BINARY') or 'node')).upload(stage / 'index.json')
    expected = {(e['relativePath'], e['sha256'], e['byteSize']) for e in generated}
    require(receipt.get('schemaVersion') == 'mira.course-archive.verification.v1'
        and receipt.get('complete') is True and receipt.get('storage') == storage
        and receipt.get('archiveId') == archive_id and receipt.get('indexSha256') == raw_sha((stage / 'index.json').read_bytes())
        and receipt.get('sourceDigest') == pack_sha
        and len(receipt.get('objects', [])) == len(expected)
        and {(o['objectKey'], o['sha256'], o['byteSize']) for o in receipt.get('objects', [])} == expected,
        'review_archive_not_verified')
    zip_entry = next(e for e in generated if e['mimeType'] == 'application/zip')
    proof = next(o for o in receipt['objects'] if o['objectKey'] == zip_entry['relativePath'])
    records = []
    for path, (raw, mime) in sorted(files.items()):
        records.append({'sourcePath': path, 'sha256': raw_sha(raw), 'byteSize': len(raw), 'mimeType': mime,
            'locator': {'kind': 'zip_member', 'objectKey': proof['objectKey'], 'etag': proof['etag'],
                **({'versionId': proof['versionId']} if proof.get('versionId') else {}),
                'archiveSha256': zip_entry['sha256'], 'archiveByteSize': zip_entry['byteSize'], 'memberPath': 'files/' + path}})
    storage_id = storage_id_for(**storage)
    scope = {'scopeKey': digest(['review_question_pack', pack_sha]), 'sourceKind': 'review_question_pack',
        'sourceDigest': pack_sha, 'contentKey': source['sourceIdentity']['contentKey'],
        'courseId': source['sourceIdentity']['courseId'], 'courseVersion': source['sourceIdentity']['courseVersion'],
        'storageDirectory': object_directory, 'packSha256': pack_sha, 'archiveVerification': receipt}
    repository.register_scope(scope, records, storage_id, activate=False)
    repository.activate_missing_heads(scope['scopeKey'], storage_id)
    immutable(directory / 'archive-receipt.json', receipt)
    return {'status': 'archived', 'packSha256': pack_sha, 'registeredFiles': len(records)}
