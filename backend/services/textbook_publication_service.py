"""Publish reviewed saved OpenMAIC content without regenerating it.

This is the fixed-textbook artifact release path. It does not manufacture
receipts for the older curriculum generator or change that generator's gates.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_preview import preview_checks
from content.textbook_preview_audio_contract import (audit_contract_identity, check_receipt_language_policy,
    resolve_audio_contract, valid_tts_request_id, validate_v2_audit_segment)
from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA, validate_listening_review, validate_receipt_wav
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA, MEDIA, check_questions, fail, single_answer, validate_release
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from content.textbook_review_followup import (discover_complete_scene_review_followup,
    validate_complete_scene_review_followup)
from content.textbook_whole_course_quality import validate_whole_course_quality_review
from core.errors import ApiError
from core.security import now_ms
from services.textbook_preview_audio import verify_segment_receipt
from services.course_media_object_store import CourseMediaObjectStore, CourseMediaStorageError
from services.course_file_store import (MAX_FILE_BYTES, CourseFileStore, CourseFileStorageError,
    course_bytes, course_exists, course_text)


class TextbookPublicationService:
    def __init__(self, preview_service, delivery_copy=None, *, course_media_store=None, course_file_store=None):
        self.preview = preview_service
        self.repository = preview_service.repository
        # Optional smaller copy of a reviewed picture or narration file.
        self.delivery_copy = delivery_copy
        self.course_media_store = course_media_store or CourseMediaObjectStore()
        self._course_file_store = course_file_store

    def _verify_publication_source(self, current, frozen, prepared):
        """Read the committed head while holding only the preview business lock.

        CourseFileStore uses fresh, ordinary registry SELECTs on its own read
        transactions. Taking a head lock here would reverse the writer's
        head -> preview lock order; resolving a historical SHA would hide a
        remote update whose SQL preview snapshot has not caught up yet.
        """
        store = self._course_file_store or CourseFileStore()
        classroom_id = current.get('classroom_id')
        if not isinstance(classroom_id, str) or re.fullmatch(r'[A-Za-z0-9_-]+', classroom_id) is None:
            fail('课件来源身份无效，请重新审核')
        root = store.project_root / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms'
        paths = ([root / classroom_id / 'artifact/classroom.json'] if classroom_id.startswith('omclass_') else
                 [root / (classroom_id + '.json'), root / classroom_id / 'classroom.json'])
        # prepare supports an explicit local classroom directory. Keep this
        # operator path outside the frozen/public release identities, and still
        # check the standard registered paths first so it cannot hide a head.
        source_path = prepared.get('sourceClassroomPath')
        if source_path is not None:
            path = Path(source_path)
            if not path.is_absolute() or path.name != classroom_id + '.json':
                fail('课件来源路径无效，请重新审核')
            if path not in paths:
                paths.append(path)
        try:
            selected = None
            # Native checks all registered spellings before any local draft,
            # then selects only the first registered spelling. A secondary
            # historical alias must not veto the actual current classroom.
            for path in paths:
                entry = store.resolve(path)  # Current head; intentionally no expected/historical SHA.
                if entry is not None:
                    raw = store.read_bytes(path, expected_sha256=entry['sha256'], expected_bytes=entry['byteSize'])
                    if raw is None:
                        raise CourseFileStorageError('Registered publication source unavailable')
                    selected = raw
                    break
            if selected is None:
                for path in paths:
                    if not path.exists():
                        continue
                    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                        raise CourseFileStorageError('Local publication source invalid')
                    selected = path.read_bytes()
                    break
            if selected is None:
                raise CourseFileStorageError('Publication source unavailable')
            checksum = digest(json.loads(selected))
            if checksum != frozen['sourceSha256'] or checksum != current['classroom_sha256']:
                fail('课件来源版本已被编辑，请重新审核')
        except (CourseFileStorageError, OSError, ValueError, KeyError, TypeError):
            fail('课件来源校验失败，请稍后重试')

    def prepare(self, *, key, edition, revision, node, teaching_revision, review, audio_audit, classroom_directory,
                asr_reconciliation=None, pronunciation_review=None):
        row = self.preview.get(key)
        if row['status'] != 'preview_ready':
            fail('课件尚未完成检查')
        source = self.repository.parse(row['classroom_json'])
        if digest(source) != row['classroom_sha256']:
            fail('课件摘要已改变')
        from services.textbook_preview_visual_revision import verify_quantity_visual_revisions
        verify_quantity_visual_revisions(row, classroom_directory)
        with self.repository.transaction() as conn:
            target = self.repository.get_revision(conn, edition, revision)
        if target is None:
            fail('教材目录不存在')
        manifest = self.repository.manifest(target)
        if digest(manifest) != target['manifest_sha256'] or row['edition_id'] != edition or row['node_id'] != node:
            fail('课件与教材身份不一致')
        _, lesson = lesson_by_id(manifest, node)
        original_input = self.repository.parse(row['input_json'])
        root = Path(classroom_directory).resolve()
        plan = json.loads(course_text(root / row['classroom_id'] / 'textbook-preview-audio/plan.json'))
        contract = resolve_audio_contract(plan, original_input)
        from services.textbook_operator_revision_service import _same_parent, checked_bytes, load_inheritance, media_path
        inheritance = load_inheritance(root / row['classroom_id'] / 'textbook-preview-audio', plan, frozen=original_input)
        if inheritance:
            with self.repository.transaction() as conn:
                _same_parent(self.preview, inheritance['parent'], conn)
            for asset in inheritance['candidate']['parent']['originalMedia']['assets']:
                checked_bytes(media_path(root, asset['mediaPath']), asset['sha256'])
            for asset in inheritance['candidate'].get('derivedImages', []):
                checked_bytes(media_path(root, asset['mediaPath']), asset['sha256'])
            for alias in inheritance['candidate']['parent'].get('audioAliases', []):
                checked_bytes(root / row['classroom_id'] / 'audio' / alias['sourcePath'].rsplit('/', 1)[-1], alias['audioSha256'])
            from content.textbook_operator_revision import validate_quiz_revision_binding, validate_visual_candidate_content, VISUAL_PATCH_SCHEMA
            validate_quiz_revision_binding(inheritance['provenance'], source)
            if inheritance['candidate']['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA:
                validate_visual_candidate_content(inheritance['candidate'], source)
            if (teaching_revision != original_input['teachingRevision']
                    or audio_audit.get('operatorParentProvenanceSha256') != inheritance['provenance']['sha256']):
                fail('修订发布必须保持已准备的教学版本和父来源审核')
        if plan['previewKey'] != key or original_input['subject'] != manifest['subject']:
            fail('配音合同与当前教材学科不一致')
        if not contract['legacy']:
            resolve_audio_contract(plan, {'editionId': edition, 'alignmentRevisionId': revision,
                'manifestSha256': digest(manifest), 'nodeId': node,
                'gradeCode': manifest['gradeCode'], 'subject': manifest['subject']})
        origin_audit = (audio_audit.get('schemaVersion') == 'mira.textbook.audio-audit.v3-asr-origin'
                        and isinstance(pronunciation_review, dict)
                        and pronunciation_review.get('schemaVersion') in (
                            'mira.textbook.pinyin-operator-review.v4-asr-origin',
                            'mira.textbook.pinyin-operator-review.v5-explicit-acceptance'))
        observation_audit = (audio_audit.get('schemaVersion') == 'mira.textbook.audio-audit.v4-same-wav-observations'
            and isinstance(pronunciation_review, dict)
            and pronunciation_review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v7-explicit-observation-acceptance')
        if observation_audit and inheritance:
            fail('Same-WAV observation acceptance cannot impersonate published audio inheritance')
        if not contract['legacy'] and ((audio_audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2' and not origin_audit and not observation_audit)
                or audio_audit.get('contract') != audit_contract_identity(plan)):
            fail('配音审核未绑定当前冻结的语言与比较策略')
        if preview_checks(source, original_input['previewPrompt']['expectedSceneCount'], original_input.get('originalMedia'), original_input['previewPrompt'].get('expectedQuestionCount', 6))['issues']:
            fail('课件结构或插画检查未通过')
        check_questions(source)
        if (audio_audit.get('sha256') != digest({k: v for k, v in audio_audit.items() if k != 'sha256'})
                or audio_audit.get('previewKey') != key or audio_audit.get('sourceSha256') != row['classroom_sha256']):
            fail('配音识别审核未通过')
        speech = [a for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
        audit_segments = {s['actionId']: s for s in audio_audit['segments']}
        if len(audit_segments) != len(speech):
            fail('配音审核段落不完整')
        receipts = {r['requestId']: r for r in self.repository.parse(row['result_json'])['audioReceipts']}
        listening = None
        reconciled = {}
        reconciliation_method = None
        automatically_reviewed = {}
        visual_acceptance = None
        if (inheritance and inheritance['candidate']['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA
                and plan.get('schemaVersion') == PINYIN_SCHEMA):
            from content.textbook_operator_revision import visual_audio_acceptance, validate_visual_audio_acceptance
            if pronunciation_review is not None or asr_reconciliation is not None or 'listeningReview' in audio_audit:
                fail('原发布音频继承不能冒充目标课件的新听验或自动复核')
            visual_acceptance = visual_audio_acceptance(inheritance['parent'], inheritance['candidate'], plan, inheritance['provenance'])
            validate_visual_audio_acceptance(visual_acceptance, plan=plan, provenance=inheritance['provenance'],
                                             classroom=source, audit=audio_audit)
        if pronunciation_review is not None:
            from content.textbook_pinyin_operator_review import validate_operator_review, operator_acceptance_method
            if asr_reconciliation is not None or 'listeningReview' in audio_audit:
                fail('自动审核不能与人工听验或人工低分豁免混用')
            automatically_reviewed = validate_operator_review(pronunciation_review, plan=plan,
                classroom=source, audit=audio_audit, expected_source_sha256=row['classroom_sha256'], now_ms=now_ms())
            if observation_audit:
                from services.textbook_asr_observation import verify_live_observation_audit
                probe_root = getattr(self.preview, 'authoring_output_root', None)
                probe_roots = [probe_root] if isinstance(probe_root, (str, Path)) else []
                verify_live_observation_audit(audio_audit, plan=plan, classroom=source,
                    expected_source_sha256=row['classroom_sha256'],
                    native_audio_directory=root.parent / 'formal-audio', probe_history_roots=probe_roots)
            for item in automatically_reviewed.values():
                if item['ttsReceipt'] != receipts.get(item['ttsRequestId']):
                    fail('自动审核中的正式 TTS 回执不是当前实际回执')
            for request_plan in pronunciation_review['requestPlans']:
                path = root / row['classroom_id'] / 'textbook-preview-audio' / 'narration-revisions' / request_plan['revisionId'] / 'plan.json'
                if not course_exists(path) or json.loads(course_text(path)) != request_plan:
                    fail('自动审核中的旁白修订计划没有对应实际归档')
        elif plan.get('schemaVersion') == PINYIN_SCHEMA and visual_acceptance is None:
            listening = audio_audit.get('listeningReview')
            heard = validate_listening_review(plan, source, listening, now_ms=now_ms())
            if any(item['audioSha256'] != receipts.get(item['ttsRequestId'], {}).get('audioSha256') for item in heard.values()):
                fail('拼音听验没有绑定当前正式音频字节')
        if asr_reconciliation is not None:
            from content.textbook_english_asr_reconciliation import (
                SCHEMA as ENGLISH_RECONCILIATION_SCHEMA,
                METHOD as ENGLISH_RECONCILIATION_METHOD,
            )
            if asr_reconciliation.get('schemaVersion') == ENGLISH_RECONCILIATION_SCHEMA:
                from content.textbook_english_asr_reconciliation import validate_reconciliation
                reconciled = validate_reconciliation(asr_reconciliation, plan=plan,
                    classroom=source, audit=audio_audit,
                    expected_source_sha256=row['classroom_sha256'], now_ms=now_ms())
                reconciliation_method = ENGLISH_RECONCILIATION_METHOD
            else:
                from content.textbook_pinyin_asr_reconciliation import (
                    ACCEPTANCE_METHOD as PINYIN_RECONCILIATION_METHOD,
                    validate_reconciliation,
                )
                reconciled = validate_reconciliation(asr_reconciliation, plan=plan, classroom=source,
                    audit=audio_audit, listening_review=listening,
                    expected_source_sha256=row['classroom_sha256'], now_ms=now_ms())
                reconciliation_method = PINYIN_RECONCILIATION_METHOD
        if audio_audit.get('passed') is not True and not reconciled and not automatically_reviewed and visual_acceptance is None:
            fail('配音识别审核未通过')
        scene_for_action = {a['id']: s for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
        for a in speech:
            audit = audit_segments.get(a['id'], {})
            tts = receipts.get(a.get('audioId'), {})
            if not valid_tts_request_id(plan, a.get('audioId')) or tts.get('status') != 'succeeded':
                fail('配音收据与冻结的学科身份不一致')
            inherited = verify_segment_receipt(plan, tts, scene_for_action[a['id']], a,
                root / row['classroom_id'] / 'textbook-preview-audio', inheritance=inheritance)
            if plan.get('schemaVersion') == PINYIN_SCHEMA:
                asset = root / row['classroom_id'] / 'audio' / (a['audioId'] + '.wav')
                if not course_exists(asset):
                    fail('正式拼音 WAV 缺失')
                validate_receipt_wav(tts, course_bytes(asset))
            if inherited is not None and audit != inherited:
                fail('继承段落的审核必须可逐项重建自原始 ASR 收据')
            if inherited is None and 'operatorParent' in audit:
                fail('新配音不能标记为父音频继承')
            inherited_approved = visual_acceptance is not None and inherited is not None
            reconciliation_accepted = (scene_for_action[a['id']]['id'], a['id']) in reconciled
            automatic_item = automatically_reviewed.get((scene_for_action[a['id']]['id'], a['id']), {})
            auto_rechecked = (automatic_item.get('asrRecheckEntrySha256') is not None
                              or automatic_item.get('exactAliasEntrySha256') is not None)
            # Origin review validates every target/origin and its separate acceptance.
            # v5 additionally binds any unresolved item to an explicit user decision.
            # Supplying an origin SHA alone never accepts an unresolved result.
            origin_accepted = (origin_audit and automatic_item.get('asrOriginEntrySha256') == audit.get('originSha256')
                               and automatic_item.get('acceptanceMethod') in ('literal-asr', 'independent-asr-recheck',
                                   'exact-carrier-orthography-both-asr', 'exact-natural-alias-content',
                                   'historical-excess-all-literal-asr',
                                   'explicit-user-accepted-unresolved-asr'))
            from content.textbook_pinyin_operator_review_v6 import accepts_validated_routine_segment
            routine_accepted = accepts_validated_routine_segment(pronunciation_review, automatic_item, audit)
            from content.textbook_pinyin_operator_review_v7 import accepts_validated_observation_segment
            observation_accepted = (observation_audit
                and accepts_validated_observation_segment(pronunciation_review, automatic_item, audit))
            if (inherited is None and not contract['legacy'] and not origin_accepted
                    and not observation_accepted
                    and not validate_v2_audit_segment(plan, a, audit, scene_id=scene_for_action[a['id']]['id'])
                    and not reconciliation_accepted and not auto_rechecked and not inherited_approved
                    and not routine_accepted):
                fail('配音中的数字、运算或英语词语识别未通过')
            if (audit.get('ttsRequestId') != a.get('audioId') or audit.get('audioSha256') != tts.get('audioSha256')
                    or audit.get('textSha256') != hashlib.sha256(a['text'].strip().encode()).hexdigest()
                    or (audit.get('similarityBps', 0) < 8500 and not reconciliation_accepted and not auto_rechecked and not inherited_approved and not origin_accepted and not routine_accepted and not observation_accepted)
                    or audit.get('asr', {}).get('status') != 'succeeded'):
                fail('配音审核与当前讲解不一致')
        required = ('alignmentConfirmed', 'originalExpressionConfirmed', 'sourceUsageConfirmed', 'publicationAuthorized')
        if (any(review.get(k) is not True for k in required) or not review.get('reviewer') or not review.get('basis')
                or review.get('sourceSha256') != row['classroom_sha256']
                or type(review.get('reviewedAt')) is not int or not 0 < review['reviewedAt'] <= now_ms()):
            fail('需要本课的对齐、原创表达、素材来源和发布审核记录')
        quality_receipt = None
        complete_scene_followup = None
        candidate = original_input.get('authoringCandidate')
        if candidate is not None:
            if (not isinstance(candidate, dict)
                    or type(candidate.get('interactionPolicyVersion')) is not int
                    or candidate['interactionPolicyVersion'] < 1
                    or not isinstance(candidate.get('interactionPolicySha256'), str)):
                fail('课件作者候选的互动规则身份无效')
            current_policy = freeze_interaction_policy()
            complete_scene_followup = candidate.get('completeSceneReviewFollowup')
            if complete_scene_followup is not None or candidate['interactionPolicyVersion'] < current_policy['policy']['version']:
                authoring = original_input.get('authoring')
                if (not isinstance(authoring, dict) or not isinstance(authoring.get('sessionId'), str)
                        or not isinstance(authoring.get('stageId'), str)):
                    fail('旧冻结课缺少可核验的完整场景修订身份')
                try:
                    archived_followup = discover_complete_scene_review_followup(
                        None, classroom_directory, session_id=authoring['sessionId'],
                        stage_id=authoring['stageId'],
                        base_policy_version=candidate['interactionPolicyVersion'],
                        base_policy_sha256=candidate['interactionPolicySha256'],
                        candidate_source_sha256=original_input.get('sourceSha256'))
                    if archived_followup != complete_scene_followup:
                        raise ValueError('frozen follow-up differs from the immutable archive')
                    if complete_scene_followup is not None:
                        validate_complete_scene_review_followup(
                            complete_scene_followup,
                            candidate_source_sha256=original_input.get('sourceSha256'),
                            candidate=candidate, current_policy=current_policy)
                except ValueError:
                    fail('完整场景修订追踪缺失、已改变，或未绑定当前互动规则')
            if complete_scene_followup is not None:
                try:
                    quality_receipt = validate_whole_course_quality_review(
                        review.get('coursewareQuality'), classroom=source,
                        policy_sha256=complete_scene_followup['currentInteractionPolicySha256'],
                        source_sha256=row['classroom_sha256'])
                except ValueError:
                    fail('完整场景修订后的课件本体质量审核未通过')
            elif candidate['interactionPolicyVersion'] >= 2:
                try:
                    quality_receipt = validate_whole_course_quality_review(
                        review.get('coursewareQuality'), classroom=source,
                        policy_sha256=candidate['interactionPolicySha256'],
                        source_sha256=row['classroom_sha256'])
                except ValueError:
                    fail('课件本体质量审核未通过')
        if (not isinstance(teaching_revision, str) or not 1 <= len(teaching_revision) <= 80):
            fail('教学修订号无效')
        frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': key, 'sourceSha256': row['classroom_sha256'],
            'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'], 'knowledgeBrief': lesson['brief'],
            'textbookBinding': {'editionId': edition, 'alignmentRevisionId': revision,
                'alignmentManifestSha256': digest(manifest), 'nodeId': node, 'partIndex': 1,
                'teachingRevision': teaching_revision}}
        if not contract['legacy']:
            # Preserve the complete immutable contract for later publication
            # reads; legacy release hashes and their JSON remain unchanged.
            frozen['audioContract'] = deepcopy(plan)
        if visual_acceptance is not None:
            frozen['visualAudioInheritanceSha256'] = visual_acceptance['sha256']
        if listening is not None or automatically_reviewed or visual_acceptance is not None or reconciled:
            frozen['audioAuditSha256'] = audio_audit['sha256']
        if automatically_reviewed:
            frozen['pronunciationReviewSha256'] = pronunciation_review['sha256']
            frozen['sourceClassroomId'] = source['id']
        if reconciled:
            frozen['audioAcceptance'] = {'method': reconciliation_method,
                'literalAuditSha256': audio_audit['sha256'],
                'reconciliationSha256': asr_reconciliation['sha256']}
            if reconciliation_method == 'exact-registered-full-sentence-orthography':
                frozen['sourceClassroomId'] = source['id']
        if inheritance:
            frozen['operatorParent'] = deepcopy(inheritance['provenance'])
            if inheritance.get('restorations'):
                if self.repository.parse(row['result_json']).get('parentAudioRestorations') != inheritance['restorations']:
                    fail('原音频恢复归档与当前预览登记不同')
                frozen['operatorParentAudioRestorations'] = deepcopy(inheritance['restorations'])
        if quality_receipt is not None:
            frozen['wholeCourseQualityReviewSha256'] = quality_receipt['sha256']
        if complete_scene_followup is not None:
            frozen['completeSceneReviewFollowup'] = deepcopy(complete_scene_followup)
            frozen['authoringSourceSha256'] = original_input['sourceSha256']
        content_key = digest(frozen)
        frozen['contentKey'] = content_key
        classroom_id = 'tbpub_' + content_key[:24]
        course_id = 'textbook_' + content_key[:40]
        root = Path(classroom_directory).resolve()
        if urlparse(self.preview.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
            fail('本机发布工具不能写入其他运行环境')
        original_file = root / (row['classroom_id'] + '.json')
        if not course_exists(original_file) or digest(json.loads(course_text(original_file))) != digest(source):
            fail('本机保存的课件与审核快照不一致')
        media, delivered = {}, {}

        def replace_asset(match):
            old = match.group(0)
            if old.startswith('http') and urlparse(old).netloc != urlparse(self.preview.runtime.base_url).netloc:
                fail('存在未审核的外部素材')
            source_path = (root / match.group(1) / match.group(2)).resolve()
            if root not in source_path.parents or not course_exists(source_path):
                fail('课件素材丢失')
            if source_path in delivered:
                return delivered[source_path]
            raw = course_bytes(source_path, max_bytes=MAX_MEDIA_BYTES)
            if not raw:
                fail('课件素材格式或大小无效')
            suffix = source_path.suffix.lower()
            media_mime_type(suffix, raw)
            reviewed_sha = hashlib.sha256(raw).hexdigest()
            if self.delivery_copy:
                suffix, raw = self.delivery_copy(suffix, raw)
            sha = hashlib.sha256(raw).hexdigest()
            mime_type = media_mime_type(suffix, raw)
            kind = 'audio' if mime_type.startswith('audio/') else 'media'
            relative = f'{kind}/{sha}{suffix}'
            url = f'/api/classroom-media/{classroom_id}/{relative}'
            target_path = root / classroom_id / relative
            try:
                migrated = self.course_media_store.read(target_path, expected_sha256=sha,
                    expected_bytes=len(raw), max_bytes=MAX_MEDIA_BYTES)
            except CourseMediaStorageError:
                fail('已归档的素材发生变化')
            if migrated is not None:
                if migrated != raw:
                    fail('已归档的素材发生变化')
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.exists() and target_path.read_bytes() != raw:
                    fail('已归档的素材发生变化')
                if not target_path.exists():
                    with target_path.open('xb') as output:
                        output.write(raw)
            media[url] = {'path': url, 'sha256': sha, 'byteSize': len(raw), 'mimeType': mime_type}
            if sha != reviewed_sha:
                media[url]['sourceSha256'] = reviewed_sha
            delivered[source_path] = url
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
        # A revision may carry scene.stageId from an earlier preview alias,
        # which the source-classroom string replacement cannot recognize.
        # Bind delivery ownership explicitly, leaving the reviewed source and
        # frozen identities untouched.
        for scene in classroom['scenes']:
            scene['stageId'] = classroom_id
        # Every speech must be backed by exactly the audited byte artifact,
        # or by a delivery copy encoded from it.
        for a in [a for s in classroom['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']:
            item = media.get(a.get('audioUrl'), {})
            if item.get('sourceSha256', item.get('sha256')) != audit_segments[a['id']]['audioSha256']:
                fail('归档语音与审核音频不一致')
        release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': content_key, 'classroomId': classroom_id,
            'classroom': classroom, 'classroomSha256': digest(classroom), 'media': list(media.values()),
            'audioAudit': {'passed': True, 'segments': len(speech), 'sha256': audio_audit['sha256'],
                'minSimilarityBps': min(s['similarityBps'] for s in audit_segments.values())}}
        if not contract['legacy']:
            release['audioAudit']['contract'] = audit_contract_identity(plan)
        if listening is not None:
            release['audioAudit']['listeningReview'] = deepcopy(listening)
            release['audioAudit'].update(literalPassed=audio_audit['passed'],
                acceptanceMethod='literal-asr', literalAudit=deepcopy(audio_audit))
        if automatically_reviewed:
            release['audioAudit'].update(pronunciationReview=deepcopy(pronunciation_review),
                literalPassed=audio_audit['passed'],
                acceptanceMethod=operator_acceptance_method(pronunciation_review),
                literalAudit=deepcopy(audio_audit))
        if visual_acceptance is not None:
            release['audioAudit'].update(visualAudioInheritance=deepcopy(visual_acceptance),
                literalPassed=audio_audit['passed'], acceptanceMethod='unchanged-published-audio',
                literalAudit=deepcopy(audio_audit))
        if reconciled:
            release['audioAudit'].update(literalPassed=False, acceptanceMethod=reconciliation_method,
                literalAudit=deepcopy(audio_audit), reconciliation=deepcopy(asr_reconciliation))
        if inheritance:
            release['audioAudit']['operatorParentProvenanceSha256'] = inheritance['provenance']['sha256']
            if inheritance.get('restorations'):
                release['audioAudit']['operatorParentAudioRestorationsSha256'] = digest(inheritance['restorations'])
        release['sha256'] = digest(release)
        course_content = {'schemaVersion': 'mira.learning.fixed-textbook-course.v1',
            'textbookBinding': frozen['textbookBinding'], 'title': classroom['stage']['name'],
            'objectives': original_input['knowledgeBrief']['objectives'] if original_input.get('sourceScope') else lesson['brief']['objectives'], 'estimatedMinutes': 10,
            'questions': [{'id': q['id'], 'type': 'single_choice', 'prompt': q['question'],
                'choices': [{'id': o['value'], 'text': o['label']} for o in q['options']],
                'answer': single_answer(q), 'explanation': q['analysis'], 'skill': original_input['previewPrompt'].get('targets', ['天地人、你我他'] * len(questions_for(classroom)))[i]} for i, q in enumerate(questions_for(classroom))],
            'releaseSha256': release['sha256']}
        if inheritance and inheritance['candidate'].get('assessmentEvidence'):
            course_content['assessmentEvidence'] = inheritance['candidate']['assessmentEvidence']
        return {'frozen': frozen, 'release': release, 'review': {**review, 'release': release},
            'course': {'id': course_id, 'version': teaching_revision, 'grade_code': manifest['gradeCode'],
                'subject': manifest['subject'], 'node_code': f'textbook:{edition}:{node}',
                'title': classroom['stage']['name'], 'objective': '；'.join(course_content['objectives']),
                'content_json': canonical(course_content)}, 'manifest': manifest,
            'sourceClassroomPath': str(original_file)}

    def publish(self, prepared):
        frozen, course, review = prepared['frozen'], prepared['course'], prepared['review']
        with self.repository.transaction() as conn:
            current = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (frozen['previewKey'],)).fetchone()
            if current is None or current['classroom_sha256'] != frozen['sourceSha256'] or current['status'] != 'preview_ready':
                fail('预览已被编辑，请重新审核')
            self._verify_publication_source(current, frozen, prepared)
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
