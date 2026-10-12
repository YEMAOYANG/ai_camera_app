"""Publish an explicitly reviewed private activity without regenerating media."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest
from content.textbook_release import MEDIA, fail, questions, validate_release
from content.textbook_batch_release import (INPUT_SCHEMA, RELEASE_SCHEMA, REVIEW_SCHEMA,
    REVIEW_FLAGS, node_key, validate_input)
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from core.security import now_ms
from scripts.narrate_textbook_batch import load_candidate
from scripts.private_textbook_preview_snapshot import verify_complete_audio
from services.textbook_batch_audio import build_audio_plan, audio_language_policy_from_plan
from content.textbook_deepseek_release import validate_new_authoring, validate_new_release_admission


def knowledge_brief(original, review):
    """Older designs need an explicit bounded teaching brief in their review."""
    knowledge = original.get('reviewedLessonScope') or original.get('activityDesign') or {}
    fields = ('objectives', 'knowledgePoints', 'priorKnowledge', 'excludedTopics')
    brief = {k: deepcopy(knowledge.get(k, [])) for k in fields}
    if not brief['objectives']:
        brief['objectives'] = [entry['draftIntent'] for entry in knowledge.get('proposedObservationGoals', [])]
        brief['excludedTopics'] = deepcopy(knowledge.get('pedagogy', {}).get('excludedTopics', []))
    reviewed = review.get('knowledgeBrief')
    if reviewed is not None:
        if (not isinstance(reviewed, dict) or set(reviewed) != set(fields)
                or any(not isinstance(reviewed[k], list) or any(not isinstance(s, str) or not s.strip()
                    for s in reviewed[k]) for k in fields) or not reviewed['objectives']):
            fail('教学范围审核必须包含明确目标和范围列表')
        if brief['objectives'] and reviewed != brief:
            fail('发布审核不能改写已有的冻结教学范围')
        brief = deepcopy(reviewed)
    if not brief['objectives']:
        fail('旧版课件需在本份发布审核中补充具体教学范围')
    return brief


def normalize_interactive_content(room):
    """Fill the old missing discriminator without changing teaching content."""
    for scene in room.get('scenes', []):
        if scene.get('type') != 'interactive':
            continue
        content = scene.get('content')
        if not isinstance(content, dict) or not isinstance(content.get('html'), str) or not content['html'].strip():
            fail('交互课件缺少实际内容')
        if content.get('type') not in (None, 'interactive'):
            fail('交互场景内容类型不一致')
        content['type'] = 'interactive'
    return room


def reviewed_estimated_minutes(review):
    """Use the author-reviewed estimate; old receipts retain their old default."""
    minutes = review.get('estimatedMinutes', 10)
    if type(minutes) is not int or not 1 <= minutes <= 120:
        fail('课程预计时长必须是审核过的 1 至 120 分钟整数')
    return minutes


class TextbookActivityPublicationService:
    def __init__(self, repository, runtime_origin, classroom_directory):
        self.repository = repository
        self.origin = runtime_origin.rstrip('/')
        self.root = Path(classroom_directory).resolve()
        if urlparse(self.origin).hostname not in {'localhost', '127.0.0.1', '::1'}:
            fail('本机发布工具不能写入其他运行环境')

    def prepare(self, candidate_directory, audio_directory, review, teaching_revision):
        original, state, classroom = load_candidate(candidate_directory)
        audio_directory = Path(audio_directory).resolve()
        if not audio_directory.is_relative_to(Path(candidate_directory).resolve()):
            fail('音频审核须属于当前课件')
        plan, audit, narrated = [json.loads((audio_directory / name).read_text())
                                for name in ('plan.json', 'audit.json', 'narrated-classroom.json')]
        if (state['runtimeOrigin'] != self.origin or plan != build_audio_plan(classroom, original['binding'], self.origin,
                audio_language_policy=audio_language_policy_from_plan(plan))):
            fail('配音与当前课件任务不一致')
        assets = verify_complete_audio(classroom, narrated, plan, audit, self.root)
        if (review.get('schemaVersion') != REVIEW_SCHEMA or any(review.get(k) is not True for k in REVIEW_FLAGS)
                or not review.get('reviewer') or not review.get('basis') or not review.get('evidence')
                or review.get('sourceInputSha256') != original['inputSha256']
                or review.get('sourceSha256') != digest(classroom) or review.get('audioAuditSha256') != audit['sha256']
                or type(review.get('reviewedAt')) is not int or not 0 < review['reviewedAt'] <= now_ms()
                or 'release' in review):
            fail('需要本份课件的知识范围、图画操作、旁白状态和素材发布审核')
        if questions(narrated):
            fail('本发布契约只提供不评分的探索、导学和教学活动')
        admission = validate_new_authoring(original, classroom, review)
        review = {**review, 'deepseekAuthoringAdmission': admission}
        manifest, binding = original['manifest'], original['binding']
        scope = {'kind': original['kind'], 'unitId': binding['unitId'], 'nodeId': binding['nodeId']}
        brief = knowledge_brief(original, review)
        estimated_minutes = reviewed_estimated_minutes(review)
        # Pending private input stays intact. Approval is a new immutable receipt.
        frozen = {'schemaVersion': INPUT_SCHEMA, 'taskId': original['taskId'],
            'sourceInputSha256': original['inputSha256'], 'sourceSha256': digest(classroom),
            'audioAuditSha256': audit['sha256'], 'reviewSha256': digest(review),
            'deepseekAuthoringAdmissionSha256': digest(admission),
            'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'],
            'teacher': plan['teacher'], 'knowledgeBrief': brief, 'assessmentMode': 'ungraded', 'activityScope': scope,
            'textbookBinding': {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'alignmentManifestSha256': digest(manifest), 'nodeId': node_key(original['kind'], binding['unitId'], binding['nodeId']),
                'partIndex': 1, 'teachingRevision': teaching_revision}}
        frozen['contentKey'] = digest(frozen)
        validate_input(frozen, manifest)
        with self.repository.transaction() as conn:
            row = self.repository.get_revision(conn, manifest['editionId'], manifest['revisionId'])
            if row is None or row['manifest_sha256'] != digest(manifest):
                fail('数据库教材与冻结任务书不一致')
        key = frozen['contentKey']
        classroom_id = 'tbpub_' + key[:24]
        media = {}
        audio_hashes = {a['audioSha256'] for a in assets}

        def archive(match):
            old = match.group(0)
            if old.startswith('http') and urlparse(old).netloc != urlparse(self.origin).netloc:
                fail('存在未审核的外部素材')
            source = (self.root / match.group(1) / match.group(2)).resolve()
            if not source.is_relative_to(self.root) or not source.is_file() or not 0 < source.stat().st_size <= MAX_MEDIA_BYTES:
                fail('课件媒体丢失或格式大小无效')
            raw = source.read_bytes()
            sha, suffix = hashlib.sha256(raw).hexdigest(), source.suffix.lower()
            mime = media_mime_type(suffix, raw)
            if mime.startswith('audio/') and sha not in audio_hashes:
                fail('语音未列入本课配音审核')
            relative = ('audio/' if mime.startswith('audio/') else 'media/') + sha + suffix
            url = f'/api/classroom-media/{classroom_id}/{relative}'
            target = self.root / classroom_id / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != raw:
                    fail('已发布的媒体不能覆盖')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
            media[url] = {'path': url, 'sha256': sha, 'byteSize': len(raw), 'mimeType': mime}
            return url

        def convert(value):
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, str):
                return classroom_id if value == classroom['id'] else MEDIA.sub(archive, value)
            return value

        room = normalize_interactive_content(convert(narrated))
        # Only fields used for playback belong in the release, not production paths.
        room['stage'].pop('videoManifest', None)
        # Recompute after dropping private stage fields to avoid unused allowlist entries.
        paths = {m.group(0) for m in MEDIA.finditer(canonical(room))}
        media = {p: m for p, m in media.items() if p in paths}
        if {m['sha256'] for m in media.values() if m['mimeType'].startswith('audio/')} != audio_hashes:
            fail('发布配音清单不完整')
        release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': key, 'classroomId': classroom_id,
            'classroom': room, 'classroomSha256': digest(room), 'assessmentMode': 'ungraded', 'activityScope': scope,
            'media': sorted(media.values(), key=lambda m: m['path']),
            'audioAudit': {'passed': True, 'segments': audit['expectedSegments'], 'sha256': audit['sha256'],
                'minSimilarityBps': min(s['similarityBps'] for s in audit['segments'])}}
        release['sha256'] = digest(release)
        content = {'schemaVersion': 'mira.learning.textbook-activity-course.v1',
            'textbookBinding': frozen['textbookBinding'], 'title': room['stage']['name'],
            'objectives': brief['objectives'], 'estimatedMinutes': estimated_minutes, 'questions': [],
            'assessmentMode': 'ungraded', 'activityScope': scope, 'releaseSha256': release['sha256']}
        course = {'id': 'textbook_' + key[:40], 'version': teaching_revision, 'grade_code': manifest['gradeCode'],
            'subject': manifest['subject'], 'node_code': 'textbook:' + key[:40], 'title': content['title'],
            'objective': '；'.join(brief['objectives']), 'content_json': canonical(content)}
        return {'frozen': frozen, 'release': release, 'review': {**review, 'release': release},
                'course': course, 'manifest': manifest}

    def publish(self, prepared):
        frozen, course = prepared['frozen'], prepared['course']
        validate_new_release_admission(frozen, prepared['review'])
        # Re-validate the complete proposed artifact before a database write.
        binding = frozen['textbookBinding']
        proposed = {'content_key': frozen['contentKey'], 'status': 'published', 'input_json': frozen,
            'review_json': prepared['review'], 'course_id': course['id'], 'course_version': course['version'],
            'course_content_sha256': digest(json.loads(course['content_json'])), 'edition_id': binding['editionId'],
            'revision_id': binding['alignmentRevisionId'], 'node_id': binding['nodeId'], 'part_index': 1,
            'teaching_revision': binding['teachingRevision']}
        validate_release(proposed, prepared['manifest'], {**course, 'status': 'published', 'quality_status': 'released'})
        for asset in prepared['release']['media']:
            match = MEDIA.fullmatch(asset['path'])
            path = self.root / match.group(1) / match.group(2)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
                fail('发布媒体已变化')
        with self.repository.transaction() as conn:
            row = self.repository.get_revision(conn, binding['editionId'], binding['alignmentRevisionId'])
            if row is None or row['manifest_sha256'] != binding['alignmentManifestSha256']:
                fail('教材修订已变化')
            now = now_ms()
            build, _ = self.repository.reserve_build(conn, frozen, now)
            old = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=? FOR UPDATE',
                               (course['id'], course['version'])).fetchone()
            if old:
                if self.repository.parse(old['content_json']) != self.repository.parse(course['content_json']):
                    fail('不能覆盖已有课程')
            else:
                conn.execute("INSERT INTO learning_courses (id,version,grade_code,subject,node_code,title,objective,status,content_json,content_origin,quality_status,published_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'published',?,'openmaic_generated','released',?,?,?)",
                    (course['id'], course['version'], course['grade_code'], course['subject'], course['node_code'],
                     course['title'], course['objective'], course['content_json'], now, now, now))
            created = self.repository.bind_published(conn, build, course, prepared['review'], now)
            saved = self.repository.get_build(conn, frozen['contentKey'])
            stored = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?', (course['id'], course['version'])).fetchone()
            validate_release(saved, prepared['manifest'], stored)
        return {'ok': True, 'created': created, 'status': 'published', 'contentKey': frozen['contentKey'],
            'courseId': course['id'], 'courseVersion': course['version'], 'classroomId': prepared['release']['classroomId'],
            'kind': frozen['activityScope']['kind'], 'assessmentMode': 'ungraded',
            'releaseSha256': prepared['release']['sha256']}
