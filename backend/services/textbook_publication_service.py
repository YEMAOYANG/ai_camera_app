"""Publish reviewed saved OpenMAIC content without regenerating it.

This is the fixed-textbook artifact release path. It does not manufacture
receipts for the older curriculum generator or change that generator's gates.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_preview import preview_checks
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA, MEDIA, check_questions, fail, validate_release
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from core.errors import ApiError
from core.security import now_ms


class TextbookPublicationService:
    def __init__(self, preview_service):
        self.preview = preview_service
        self.repository = preview_service.repository

    def prepare(self, *, key, edition, revision, node, teaching_revision, review, audio_audit, classroom_directory):
        row = self.preview.get(key)
        if row['status'] != 'preview_ready':
            fail('课件尚未完成检查')
        source = self.repository.parse(row['classroom_json'])
        if digest(source) != row['classroom_sha256']:
            fail('课件摘要已改变')
        with self.repository.transaction() as conn:
            target = self.repository.get_revision(conn, edition, revision)
        if target is None:
            fail('教材目录不存在')
        manifest = self.repository.manifest(target)
        if digest(manifest) != target['manifest_sha256'] or row['edition_id'] != edition or row['node_id'] != node:
            fail('课件与教材身份不一致')
        _, lesson = lesson_by_id(manifest, node)
        original_input = self.repository.parse(row['input_json'])
        if preview_checks(source, original_input['previewPrompt']['expectedSceneCount'], original_input.get('originalMedia'), original_input['previewPrompt'].get('expectedQuestionCount', 6))['issues']:
            fail('课件结构或插画检查未通过')
        check_questions(source)
        if (audio_audit.get('sha256') != digest({k: v for k, v in audio_audit.items() if k != 'sha256'})
                or audio_audit.get('previewKey') != key or audio_audit.get('sourceSha256') != row['classroom_sha256']
                or audio_audit.get('passed') is not True):
            fail('配音识别审核未通过')
        speech = [a for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
        audit_segments = {s['actionId']: s for s in audio_audit['segments']}
        if len(audit_segments) != len(speech):
            fail('配音审核段落不完整')
        receipts = {r['requestId']: r for r in self.repository.parse(row['result_json'])['audioReceipts']}
        for a in speech:
            audit = audit_segments.get(a['id'], {})
            tts = receipts.get(a.get('audioId'), {})
            if (audit.get('ttsRequestId') != a.get('audioId') or audit.get('audioSha256') != tts.get('audioSha256')
                    or audit.get('textSha256') != hashlib.sha256(a['text'].strip().encode()).hexdigest()
                    or audit.get('similarityBps', 0) < 8500 or audit.get('asr', {}).get('status') != 'succeeded'):
                fail('配音审核与当前讲解不一致')
        required = ('alignmentConfirmed', 'originalExpressionConfirmed', 'sourceUsageConfirmed', 'publicationAuthorized')
        if (any(review.get(k) is not True for k in required) or not review.get('reviewer') or not review.get('basis')
                or review.get('sourceSha256') != row['classroom_sha256']
                or type(review.get('reviewedAt')) is not int or not 0 < review['reviewedAt'] <= now_ms()):
            fail('需要本课的对齐、原创表达、素材来源和发布审核记录')
        if (not isinstance(teaching_revision, str) or not 1 <= len(teaching_revision) <= 80):
            fail('教学修订号无效')
        frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': key, 'sourceSha256': row['classroom_sha256'],
            'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'], 'knowledgeBrief': lesson['brief'],
            'textbookBinding': {'editionId': edition, 'alignmentRevisionId': revision,
                'alignmentManifestSha256': digest(manifest), 'nodeId': node, 'partIndex': 1,
                'teachingRevision': teaching_revision}}
        content_key = digest(frozen)
        frozen['contentKey'] = content_key
        classroom_id = 'tbpub_' + content_key[:24]
        course_id = 'textbook_' + content_key[:40]
        root = Path(classroom_directory).resolve()
        if urlparse(self.preview.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
            fail('本机发布工具不能写入其他运行环境')
        original_file = root / (row['classroom_id'] + '.json')
        if not original_file.is_file() or digest(json.loads(original_file.read_text())) != digest(source):
            fail('本机保存的课件与审核快照不一致')
        media = {}

        def replace_asset(match):
            old = match.group(0)
            if old.startswith('http') and urlparse(old).netloc != urlparse(self.preview.runtime.base_url).netloc:
                fail('存在未审核的外部素材')
            source_path = (root / match.group(1) / match.group(2)).resolve()
            if root not in source_path.parents or not source_path.is_file():
                fail('课件素材丢失')
            if not 0 < source_path.stat().st_size <= MAX_MEDIA_BYTES:
                fail('课件素材格式或大小无效')
            raw = source_path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            suffix = source_path.suffix.lower()
            mime_type = media_mime_type(suffix, raw)
            kind = 'audio' if mime_type.startswith('audio/') else 'media'
            relative = f'{kind}/{sha}{suffix}'
            url = f'/api/classroom-media/{classroom_id}/{relative}'
            target_path = root / classroom_id / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and target_path.read_bytes() != raw:
                fail('已归档的素材发生变化')
            if not target_path.exists():
                with target_path.open('xb') as output:
                    output.write(raw)
            media[url] = {'path': url, 'sha256': sha, 'byteSize': len(raw), 'mimeType': mime_type}
            return url

        def convert(value):
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, str):
                return classroom_id if value == row['classroom_id'] else MEDIA.sub(replace_asset, value)
            return value

        classroom = convert(deepcopy(source))
        # Every speech must be backed by exactly the audited byte artifact.
        for a in [a for s in classroom['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']:
            if media.get(a.get('audioUrl'), {}).get('sha256') != audit_segments[a['id']]['audioSha256']:
                fail('归档语音与审核音频不一致')
        release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': content_key, 'classroomId': classroom_id,
            'classroom': classroom, 'classroomSha256': digest(classroom), 'media': list(media.values()),
            'audioAudit': {'passed': True, 'segments': len(speech), 'sha256': audio_audit['sha256'],
                'minSimilarityBps': min(s['similarityBps'] for s in audit_segments.values())}}
        release['sha256'] = digest(release)
        course_content = {'schemaVersion': 'mira.learning.fixed-textbook-course.v1',
            'textbookBinding': frozen['textbookBinding'], 'title': classroom['stage']['name'],
            'objectives': original_input['knowledgeBrief']['objectives'] if original_input.get('sourceScope') else lesson['brief']['objectives'], 'estimatedMinutes': 10,
            'questions': [{'id': q['id'], 'type': 'single_choice', 'prompt': q['question'],
                'choices': [{'id': o['value'], 'text': o['label']} for o in q['options']],
                'answer': q['answer'][0], 'explanation': q['analysis'], 'skill': original_input['previewPrompt'].get('targets', ['天地人、你我他'] * len(questions_for(classroom)))[i]} for i, q in enumerate(questions_for(classroom))],
            'releaseSha256': release['sha256']}
        return {'frozen': frozen, 'release': release, 'review': {**review, 'release': release},
            'course': {'id': course_id, 'version': teaching_revision, 'grade_code': manifest['gradeCode'],
                'subject': manifest['subject'], 'node_code': f'textbook:{edition}:{node}',
                'title': classroom['stage']['name'], 'objective': '；'.join(lesson['brief']['objectives']),
                'content_json': canonical(course_content)}, 'manifest': manifest}

    def publish(self, prepared):
        frozen, course, review = prepared['frozen'], prepared['course'], prepared['review']
        with self.repository.transaction() as conn:
            current = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (frozen['previewKey'],)).fetchone()
            if current['classroom_sha256'] != frozen['sourceSha256'] or current['status'] != 'preview_ready':
                fail('预览已被编辑，请重新审核')
            binding = frozen['textbookBinding']
            directory = self.repository.get_revision(conn, binding['editionId'], binding['alignmentRevisionId'])
            if directory is None or directory['manifest_sha256'] != binding['alignmentManifestSha256']:
                fail('教材目录已变化')
            timestamp = now_ms()
            build, _ = self.repository.reserve_build(conn, frozen, timestamp)
            old = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=? FOR UPDATE', (course['id'], course['version'])).fetchone()
            if old:
                if old['content_json'] != course['content_json']:
                    fail('已存在同版本的不同课件，不能覆盖')
            else:
                conn.execute("INSERT INTO learning_courses (id,version,grade_code,subject,node_code,title,objective,status,content_json,content_origin,quality_status,published_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'published',?,'openmaic_generated','released',?,?,?)",
                    (course['id'], course['version'], course['grade_code'], course['subject'], course['node_code'], course['title'], course['objective'], course['content_json'], timestamp, timestamp, timestamp))
            created = self.repository.bind_published(conn, build, course, review, timestamp)
            saved = self.repository.get_build(conn, frozen['contentKey'])
            validate_release(saved, prepared['manifest'])
        return {'ok': True, 'created': created, 'status': 'published', 'contentKey': frozen['contentKey'],
            'courseId': course['id'], 'courseVersion': course['version'], 'classroomId': prepared['release']['classroomId'],
            'sceneCount': len(prepared['release']['classroom']['scenes']), 'audioCount': prepared['release']['audioAudit']['segments'],
            'questionCount': len(questions_for(prepared['release']['classroom'])), 'releaseSha256': prepared['release']['sha256']}


def questions_for(classroom):
    return check_questions(classroom)
