"""Durable Tencent document jobs, separate from prompt-based recognition.

Reservations precede dispatch, raw receipts precede parsing, and only a saved
Tencent job identifier permits a query retry. No database migration is needed.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from PIL import Image
from core.errors import ApiError
from integrations.ai.tencent_homework_provider import MAX_RESPONSE_BYTES
from services.homework_tencent_normalizer import NORMALIZER_VERSION

SCHEMA = 'mira.homework-tencent-job.v1'
RECEIPT_SCHEMA = 'mira.homework-tencent-receipt.v1'
NORMALIZED_SCHEMA = 'mira.homework-tencent-normalized.v1'
MAX_RECEIPT_BYTES = MAX_RESPONSE_BYTES
POLICY = json.loads((Path(__file__).parents[1] / 'content/homework_tencent_grading_policy.v1.json').read_text())
QUERY_RETRY_ERRORS = {'homework_tencent_query_failed', 'homework_tencent_query_limit'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parsed(value, fallback=None):
    return json.loads(value) if isinstance(value, str) else value if value is not None else fallback


class TencentPending(Exception):
    def __init__(self, next_poll_at):
        self.next_poll_at = next_poll_at
        super().__init__('Tencent document job is awaiting a query')


class HomeworkTencentGrading:
    def __init__(self, homework):
        self.h = homework
        self.policy = {**POLICY, **homework.policy.get('tencentPolling', {})}

    def resume_saved_results(self, conn, row, *, execute=False):
        """Internal local repair of the same revision; never dispatch a submit.

        Preflight requires a bound saved submit for *every* page. Execution
        restores its original JobIds and queues the existing job atomically.
        The immutable call ID/request SHA remain valid across parser upgrades.
        No HTTP route or paid-retry permission is created by this operation.
        """
        h = self.h
        fresh = conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE', (row['id'],)).fetchone()
        invalid = {'resumable': False, 'resumed': False, 'queryOnly': True}
        if (not fresh or fresh['deleted_at'] is not None or fresh['revision'] != row['revision']
                or fresh['family_id'] != row['family_id'] or fresh['child_id'] != row['child_id']):
            return {**invalid, 'reason': 'submission_changed'}
        h.repository.child(conn, fresh['family_id'], fresh['child_id'], lock=execute)
        job = conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=? FOR UPDATE',
            (fresh['id'], fresh['revision'])).fetchone()
        if not job or job['status'] not in {'failed', 'queued', 'succeeded'}:
            return {**invalid, 'reason': 'job_unavailable'}
        pages = h.repository.pages(conn, fresh['id'])
        if not pages:
            return {**invalid, 'reason': 'pages_unavailable'}
        kind = h._analysis_kind(conn, fresh['id'])
        from integrations.ai.tencent_homework_provider import QUESTION_CONFIG, ESSAY_CONFIG
        provider_config = ESSAY_CONFIG if kind == 'essay' else QUESTION_CONFIG
        plans = []
        for page in pages:
            try:
                from services.homework_assets import transformed_image
                original = h.store.read(page['storage_key'])
                if hashlib.sha256(original).hexdigest() != page['content_sha256']:
                    return {**invalid, 'reason': 'source_asset_changed'}
                transformed, image = transformed_image(original, page['rotation'], parsed(page['crop_json']))
                width, height = image.size
                image.close()
                source_sha = digest({'image': hashlib.sha256(transformed).hexdigest(),
                    'analysisKind': kind, 'provider': 'tencent', 'contract': SCHEMA})
            except (ApiError, OSError, ValueError, TypeError):
                return {**invalid, 'reason': 'source_asset_unavailable'}
            calls = conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND page_id=? AND provider=? FOR UPDATE',
                (fresh['id'], page['id'], 'tencent')).fetchall()
            candidates = []
            for call in calls:
                receipt = parsed(call['receipt_json'], {})
                context = receipt.get('semanticContext', {})
                if (receipt.get('analysisRevision') == fresh['revision'] and receipt.get('analysisKind') == kind
                        and receipt.get('sourceSha256') == source_sha and receipt.get('width') == width and receipt.get('height') == height
                        and context.get('gradeCode') == fresh['grade_code'] and context.get('subject') == fresh['subject']
                        and context.get('providerConfig') == provider_config and context.get('normalizerVersion') == NORMALIZED_SCHEMA
                        and receipt.get('schemaVersion') == SCHEMA
                        and call['request_sha256'] == digest({'sourceSha256': receipt.get('sourceSha256'),
                            'grade': context.get('gradeCode'), 'subject': context.get('subject'),
                            'policySha256': context.get('policySha256'), 'normalizerVersion': context.get('normalizerVersion'),
                            'providerConfig': context.get('providerConfig'), 'providerConfigVersion': context.get('providerConfigVersion')})
                        and call['child_id'] == fresh['child_id'] and call['status'] in {'dispatched', 'unknown', 'submitted', 'query_failed', 'succeeded'}
                        and call['id'] == 'hwcall_' + digest([fresh['id'], page['id'], call['request_sha256']])[:56]):
                    candidates.append((call, receipt))
            if len(candidates) != 1:
                return {**invalid, 'reason': 'page_reservation_unavailable'}
            call, receipt = candidates[0]
            try:
                raw, envelope, data, raw_bytes = self._load_raw(job, fresh, page, call,
                    receipt['requestJournalKey'], include_envelope=True)
                response = raw.get('Response', {})
                if not isinstance(response, dict) or response.get('Error'):
                    return {**invalid, 'reason': 'submit_not_accepted'}
                ids = self._job_ids({'jobId': response.get('JobId'), 'jobIds': response.get('JobIds')})
                if receipt.get('jobIds') and receipt['jobIds'] != ids:
                    return {**invalid, 'reason': 'saved_job_identity_changed'}
                receipt = {**receipt, 'jobIds': ids,
                    'submitResponse': self._reference(receipt['requestJournalKey'], data, raw_bytes, 'submit')}
                if not receipt.get('submittedGeometry'):
                    metadata = envelope.get('metadata') or {}
                    receipt['submittedGeometry'] = {k: metadata.get(k) for k in ('inputWidth', 'inputHeight',
                        'submittedWidth', 'submittedHeight', 'submittedFormat', 'submittedSha256')}
                # An interrupted callback can already have written the DONE
                # journal before its DB linkage; recover that locally too.
                receipt = self._recover_completed(job, fresh, page, call, receipt)
                for completed in receipt.get('completedJobs', {}).values():
                    self._completed_raw(job, fresh, page, call, completed)
                if receipt.get('failedJobs'):
                    return {**invalid, 'reason': 'provider_job_failed'}
            except (ApiError, ValueError, KeyError, TypeError, OSError):
                return {**invalid, 'reason': 'saved_receipt_unavailable'}
            plans.append((call, receipt))
        value = {'resumable': True, 'resumed': False, 'queryOnly': True, 'jobId': job['id'],
            'callIds': [call['id'] for call, _ in plans],
            'completedJobCount': sum(len(receipt.get('completedJobs', {})) for _, receipt in plans)}
        if not execute:
            return value
        audit_id = 'hwtrepair_' + digest([fresh['id'], fresh['revision'], NORMALIZER_VERSION,
            [[call['id'], call['request_sha256']] for call, _ in plans]])[:52]
        if conn.execute('SELECT id FROM homework_actions WHERE id=?', (audit_id,)).fetchone():
            return {**value, 'alreadyResumed': True, 'auditId': audit_id}
        now = h.clock()
        for call, receipt in plans:
            receipt.update(nextPollAt=now, pollingStartedAt=now, windowPollCount=0,
                localRecoveryVersion=NORMALIZER_VERSION, localRecoveryAt=now, localRecoveryQueryOnly=True)
            conn.execute('UPDATE homework_provider_calls SET status=?,receipt_json=?,error_code=NULL,updated_at=? WHERE id=?',
                ('succeeded' if call['status'] == 'succeeded' else 'submitted', canonical(receipt), now, call['id']))
            self._record_journal_actions(conn, fresh, call, receipt)
        audit = {**value, 'schemaVersion': 'mira.homework-tencent-local-repair.v1',
            'revision': fresh['revision'], 'normalizerVersion': NORMALIZER_VERSION}
        conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
            (audit_id, fresh['id'], '__tencent_local_repair__', digest(audit_id), digest(audit), canonical(audit), now))
        conn.execute('UPDATE homework_jobs SET status=?,stage=?,error_code=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
            ('queued', 'recognizing', now, job['id']))
        conn.execute('UPDATE homework_submissions SET status=?,error_code=NULL,updated_at=? WHERE id=?', ('queued', now, fresh['id']))
        return {**value, 'resumed': True, 'auditId': audit_id}

    def resume_queries(self, conn, row):
        """An explicit analyze action can resume queries, never replay submit."""
        calls = conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND provider=? AND status=? FOR UPDATE',
            (row['id'], 'tencent', 'query_failed')).fetchall()
        resumed = False
        for call in calls:
            receipt = parsed(call['receipt_json'], {})
            ids = receipt.get('jobIds')
            if (call['error_code'] not in QUERY_RETRY_ERRORS or receipt.get('analysisRevision') != row['revision']
                    or not isinstance(ids, list) or not ids or any(not isinstance(v, str) or not v for v in ids)):
                continue
            receipt.update(nextPollAt=self.h.clock(), pollingStartedAt=self.h.clock(), windowPollCount=0,
                manualQueryResumes=int(receipt.get('manualQueryResumes', 0)) + 1)
            conn.execute('UPDATE homework_provider_calls SET status=?,error_code=NULL,receipt_json=?,updated_at=? WHERE id=?',
                ('submitted', canonical(receipt), self.h.clock(), call['id']))
            resumed = True
        return resumed

    def can_resume_queries(self, conn, row):
        calls = conn.execute('SELECT receipt_json,error_code FROM homework_provider_calls WHERE submission_id=? AND provider=? AND status=?',
            (row['id'], 'tencent', 'query_failed')).fetchall()
        return any(c['error_code'] in QUERY_RETRY_ERRORS and parsed(c['receipt_json'], {}).get('analysisRevision') == row['revision']
            and isinstance(parsed(c['receipt_json'], {}).get('jobIds'), list) and bool(parsed(c['receipt_json'], {}).get('jobIds'))
            and all(isinstance(v,str) and bool(v) for v in parsed(c['receipt_json'], {}).get('jobIds', [])) for c in calls)

    def recognize(self, job, row, page, image):
        h = self.h
        with Image.open(io.BytesIO(image)) as transformed:
            width, height = transformed.size
        with h.repository.transaction() as conn:
            h._current(conn, job)
            kind = h._analysis_kind(conn, row['id'])
            from integrations.ai.tencent_homework_provider import QUESTION_CONFIG, ESSAY_CONFIG
            provider_config = ESSAY_CONFIG if kind == 'essay' else QUESTION_CONFIG
            source_sha = digest({'image': hashlib.sha256(image).hexdigest(), 'analysisKind': kind,
                'provider': 'tencent', 'contract': SCHEMA})
            request_sha = digest({'sourceSha256': source_sha, 'grade': row['grade_code'], 'subject': row['subject'],
                'policySha256': digest(h.policy), 'normalizerVersion': NORMALIZED_SCHEMA,
                'providerConfig': provider_config, 'providerConfigVersion': 'tencent-ocr-2018-11-19.v1'})
            call_id = 'hwcall_' + digest([row['id'], page['id'], request_sha])[:56]
            call = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call_id,)).fetchone()
            if not call:
                # Local parser/policy changes cannot create a new paid submit
                # for this same immutable page/revision and accepted source.
                previous = conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND page_id=? AND provider=? ORDER BY created_at DESC',
                    (row['id'], page['id'], 'tencent')).fetchall()
                call = next((c for c in previous if self._same_source_reservation(c, source_sha, job, row, kind, provider_config)), None)
                if call:
                    call_id = call['id']
            if not call:
                repairs = conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=? AND item_id=?',
                    (row['id'], '__tencent_local_repair__')).fetchall()
                if any(parsed(r['result_json'], {}).get('revision') == job['revision'] for r in repairs):
                    # A local repair never creates a new reservation, including
                    # after a provider-config change between repair and worker.
                    raise ApiError('homework_provider_unknown', '本次仅恢复原批改任务，不会新增提交', 409)
                # Same live child/document can reuse a saved result. An ambiguous
                # submit with identical bytes cannot be bypassed by a new upload.
                prior = conn.execute('SELECT c.* FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id WHERE c.child_id=? AND s.family_id=? AND s.deleted_at IS NULL AND c.provider=? AND CAST(c.receipt_json AS TEXT) LIKE ? ORDER BY c.created_at DESC',
                    (row['child_id'], row['family_id'], 'tencent', '%' + source_sha + '%')).fetchall()
                prior = [c for c in prior if parsed(c['receipt_json'], {}).get('sourceSha256') == source_sha]
                cached = next((c for c in prior if c['status'] == 'succeeded' and c['request_sha256'] == request_sha), None)
                if cached:
                    value = self._cached_result(cached, row, page)
                    for item in value.get('items', []):
                        item['pageId'] = page['id']
                        for index, suggestion in enumerate(item.get('essaySuggestions', [])):
                            suggestion.update(pageId=page['id'], id=f'{page["id"]}:reused:{index}')
                    return value
                if any(c['status'] in {'dispatched', 'unknown', 'submitted', 'query_failed'} for c in prior):
                    raise ApiError('homework_provider_unknown', '相同照片已有未完成的批改请求，不会重复提交', 409)
                maximum = 1 if row['source'] == 'paid_validation' else h.policy['maxProviderCallsPerSubmission']
                count = conn.execute('SELECT COUNT(*) AS n FROM homework_provider_calls WHERE submission_id=?', (row['id'],)).fetchone()['n']
                if count >= maximum:
                    raise ApiError('homework_provider_budget_exhausted', '这份作业的分析次数已达上限', 409)
                receipt = {'schemaVersion': SCHEMA, 'analysisKind': kind, 'analysisRevision': job['revision'],
                    'width': width, 'height': height, 'pollCount': 0, 'windowPollCount': 0, 'jobIds': [], 'completedJobs': {},
                    'sourceSha256': source_sha, 'semanticContext': {'gradeCode': row['grade_code'], 'subject': row['subject'],
                        'policySha256': digest(h.policy), 'normalizerVersion': NORMALIZED_SCHEMA,
                        'providerConfig': provider_config, 'providerConfigVersion': 'tencent-ocr-2018-11-19.v1'},
                    'requestJournalKey': h.store.response_key('homework-tencent:' + call_id + ':submit')}
                now = h.clock()
                conn.execute('INSERT INTO homework_provider_calls (id,submission_id,page_id,child_id,request_sha256,status,provider,model,prompt_version,receipt_json,dispatched_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (call_id, row['id'], page['id'], row['child_id'], request_sha, 'dispatched', 'tencent',
                     'tencent-' + kind, 'tencent-job.v1', canonical(receipt), now, now, now))
                call = conn.execute('SELECT * FROM homework_provider_calls WHERE id=?', (call_id,)).fetchone()
                newly_reserved = True
            else:
                newly_reserved = False
            receipt = parsed(call['receipt_json'], {})
            if call['status'] == 'succeeded':
                value = parsed(call['result_json'])
                if not self._current_result(value, row):
                    value = self._normalize_saved(job, row, page, call, receipt)
                    conn.execute('UPDATE homework_provider_calls SET result_json=?,updated_at=? WHERE id=?',
                        (canonical(value), h.clock(), call['id']))
                return value
            if call['status'] == 'failed':
                if call['error_code'] == 'homework_provider_unconfigured' and not receipt.get('jobIds') and not receipt.get('submitResponse'):
                    # The adapter proved this reservation never dispatched.
                    conn.execute('UPDATE homework_provider_calls SET status=?,error_code=NULL,updated_at=? WHERE id=?',
                        ('dispatched', h.clock(), call_id))
                    newly_reserved = True
                else:
                    raise ApiError(call['error_code'] or 'homework_tencent_failed', '批改服务未能处理这张照片', 409)
            if call['status'] == 'query_failed':
                raise ApiError(call['error_code'] or 'homework_tencent_query_failed', '原批改任务查询已暂停，可以稍后继续查询', 409)
        if not receipt.get('jobIds'):
            if not newly_reserved:
                # A worker may have died after receiving the submit response but
                # before linking its JobId. Recover only the exact saved receipt.
                saved = self._recover_submit(job, row, page, call, receipt)
                if saved:
                    receipt = saved
                else:
                    self._failure(job, call_id, 'homework_provider_unknown', unknown=True)
                    raise ApiError('homework_provider_unknown', '提交结果未确认，已保留照片和回执，不会重复计费', 409)
            else:
                try:
                    h.store.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                    fd, path = tempfile.mkstemp(prefix='.tencent-input-', suffix='.png', dir=h.store.root)
                    try:
                        with os.fdopen(fd, 'wb') as output:
                            output.write(image)
                        submit = h.provider.submit_essay if kind == 'essay' else h.provider.submit_question
                        config_kw = {'essay_config': provider_config} if kind == 'essay' else {'question_config': provider_config}
                        response = submit(path, receipt_callback=self._callback(job, row, page, call, 'submit'), **config_kw)
                    finally:
                        os.unlink(path)
                    receipt = self._save_job_ids(job, call, response)
                except Exception as error:
                    self._handle_submit_error(job, call_id, error)
                raise TencentPending(receipt['nextPollAt'])
        if h.clock() < receipt.get('nextPollAt', 0):
            raise TencentPending(receipt['nextPollAt'])
        return self._poll(job, row, page, call, receipt)

    def _callback(self, job, row, page, call, attempt):
        h = self.h
        namespace = 'homework-tencent:' + call['id'] + ':' + attempt
        key = h.store.response_key(namespace)
        # Every query reservation has one recoverable immutable journal address.
        def save(action, raw, metadata):
            if not isinstance(raw, bytes) or len(raw) > MAX_RECEIPT_BYTES:
                raise ValueError('bounded Tencent receipt required')
            envelope = {'schemaVersion': RECEIPT_SCHEMA, 'callId': call['id'], 'submissionId': row['id'],
                'pageId': page['id'], 'childId': row['child_id'], 'analysisRevision': job['revision'],
                'requestSha256': call['request_sha256'], 'action': action, 'attempt': attempt,
                'rawBase64': base64.b64encode(raw).decode(), 'metadata': metadata}
            data = canonical(envelope).encode()
            storage = h.store.put_response(data, namespace=namespace)
            try:
                with h.repository.transaction() as conn:
                    h._current(conn, job)
                    latest = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call['id'],)).fetchone()
                    if not latest or latest['status'] == 'deleted':
                        raise ApiError('homework_job_superseded', '批改任务已撤销', 409)
                    receipt = parsed(latest['receipt_json'], {})
                    reference = self._reference(storage, data, raw, attempt)
                    receipt['receivedResponse'] = reference
                    if attempt == 'submit':
                        receipt['submitResponse'] = reference
                        receipt['submittedGeometry'] = {k: metadata.get(k) for k in ('inputWidth', 'inputHeight',
                            'submittedWidth', 'submittedHeight', 'submittedFormat', 'submittedSha256')}
                    self._record_journal_action(conn, row, call, reference)
                    conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?', (canonical(receipt), h.clock(), call['id']))
            except Exception:
                # A deleted source cannot retain paper data. A changed revision
                # still owns its historical reservation/journal for audit and
                # no-replay recovery, but cannot receive this JobId or result.
                with h.repository.transaction() as conn:
                    latest = conn.execute('SELECT deleted_at,revision FROM homework_submissions WHERE id=?', (row['id'],)).fetchone()
                    if not latest or latest['deleted_at'] is not None:
                        h._enqueue_delete(conn, key)
                raise
        return save

    @staticmethod
    def _reference(key, data, raw, attempt):
        return {'storageKey': key, 'sha256': hashlib.sha256(data).hexdigest(),
            'rawSha256': hashlib.sha256(raw).hexdigest(), 'attempt': attempt}

    def _record_journal_action(self, conn, row, call, reference):
        attempt = reference['attempt']
        receipt_id = 'hwtr_' + digest([call['id'], attempt])[:56]
        value = {'schemaVersion': RECEIPT_SCHEMA, 'status': 'received', 'storageKey': reference['storageKey'],
            'callId': call['id'], 'attempt': attempt, 'sha256': reference['sha256']}
        if not conn.execute('SELECT id FROM homework_actions WHERE id=?', (receipt_id,)).fetchone():
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (receipt_id, row['id'], '__tencent_receipt__', digest([call['id'], attempt]), digest(value), canonical(value), self.h.clock()))

    def _record_journal_actions(self, conn, row, call, receipt):
        for reference in [receipt.get('submitResponse'), *receipt.get('completedJobs', {}).values()]:
            if isinstance(reference, dict) and reference.get('storageKey'):
                self._record_journal_action(conn, row, call, reference)

    def _load_raw(self, job, row, page, call, key, *, attempt='submit', reference=None, include_envelope=False, allow_invalid_payload=False):
        data = self.h.store.read(key)
        if len(data) > MAX_RECEIPT_BYTES * 2:
            raise ValueError('bounded Tencent journal required')
        saved = json.loads(data)
        if not isinstance(saved, dict):
            raise ValueError('invalid Tencent journal structure')
        binding = {'schemaVersion': RECEIPT_SCHEMA, 'callId': call['id'], 'submissionId': row['id'],
            'pageId': page['id'], 'childId': row['child_id'], 'analysisRevision': job['revision'],
            'requestSha256': call['request_sha256']}
        actual_attempt = saved.get('attempt')
        if attempt is None:
            if not isinstance(actual_attempt, str) or not re.fullmatch(r'poll:\d+:\d+', actual_attempt):
                raise ValueError('invalid Tencent poll journal binding')
        elif actual_attempt != attempt:
            raise ValueError('invalid Tencent journal attempt')
        kind = parsed(call['receipt_json'], {}).get('analysisKind')
        action = ('SubmitMarkEssayAgentJob' if kind == 'essay' else 'SubmitQuestionMarkAgentJob') if actual_attempt == 'submit' else (
            'DescribeMarkEssayAgentJob' if kind == 'essay' else 'DescribeQuestionMarkAgentJob')
        if any(saved.get(k) != v for k, v in binding.items()) or saved.get('action') != action:
            raise ValueError('invalid Tencent journal binding')
        raw = base64.b64decode(saved['rawBase64'], validate=True)
        if len(raw) > MAX_RECEIPT_BYTES or reference and (
                reference.get('sha256') != hashlib.sha256(data).hexdigest()
                or reference.get('rawSha256') != hashlib.sha256(raw).hexdigest()):
            raise ValueError('invalid Tencent journal digest')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            if not allow_invalid_payload:
                raise
            value = None
        return (value, saved, data, raw) if include_envelope else value

    @staticmethod
    def _same_source_reservation(call, source_sha, job, row, kind, provider_config):
        receipt = parsed(call['receipt_json'], {})
        context = receipt.get('semanticContext', {})
        return (call['status'] != 'deleted' and receipt.get('sourceSha256') == source_sha
            and receipt.get('analysisRevision') == job['revision'] and receipt.get('analysisKind') == kind
            and context.get('gradeCode') == row['grade_code'] and context.get('subject') == row['subject']
            and context.get('providerConfig') == provider_config and call['child_id'] == row['child_id'])

    def _normalization_context(self, row):
        return digest({'normalizerVersion': NORMALIZER_VERSION, 'policySha256': digest(self.h.policy),
            'maxItemsPerPage': self.policy['maxItemsPerPage'], 'gradeCode': row['grade_code'], 'subject': row['subject']})

    def _current_result(self, value, row):
        return (isinstance(value, dict) and value.get('normalizerVersion') == NORMALIZER_VERSION
            and value.get('normalizationContextSha256') == self._normalization_context(row))

    def _cached_result(self, call, row, page):
        value = parsed(call['result_json'])
        if self._current_result(value, row):
            return value
        # Reparse an old cache locally with its original receipt bindings. The
        # request SHA already proves the target grade/subject/config match.
        receipt = parsed(call['receipt_json'], {})
        original_row = {'id': call['submission_id'], 'child_id': call['child_id'],
            'grade_code': row['grade_code'], 'subject': row['subject']}
        return self._normalize_saved({'revision': receipt.get('analysisRevision')}, original_row,
            {'id': call['page_id']}, call, receipt, output_page_id=page['id'])

    def _completed_raw(self, job, row, page, call, saved):
        if isinstance(saved, dict) and isinstance(saved.get('Response'), dict):
            # Old deployments saved the full DONE body in receipt_json.
            raw = saved
        elif isinstance(saved, dict) and isinstance(saved.get('storageKey'), str):
            attempt = saved.get('attempt')
            if not isinstance(attempt, str) or not re.fullmatch(r'poll:\d+:\d+', attempt):
                raise ValueError('invalid completed Tencent attempt')
            raw = self._load_raw(job, row, page, call, saved['storageKey'], attempt=attempt, reference=saved)
        else:
            raise ValueError('missing completed Tencent receipt')
        response = raw.get('Response', {})
        if not isinstance(response, dict) or response.get('Error') or response.get('JobStatus') != 'DONE':
            raise ValueError('invalid completed Tencent receipt status')
        return raw

    def _recover_completed(self, job, row, page, call, receipt):
        completed = dict(receipt.get('completedJobs', {}))
        if any(job_id not in receipt['jobIds'] for job_id in completed):
            raise ValueError('completed Tencent job identity changed')
        # A query response can be durable even when its callback's DB write was
        # interrupted. Its pre-reserved address and envelope bind it to one job.
        key = receipt.get('responseJournalKey')
        if key:
            try:
                raw, envelope, data, raw_bytes = self._load_raw(job, row, page, call, key, attempt=None,
                    include_envelope=True, allow_invalid_payload=True)
            except ApiError as error:
                if error.code != 'homework_asset_missing':
                    raise
            else:
                index, count = (int(v) for v in envelope['attempt'].split(':')[1:])
                if (index >= len(receipt['jobIds']) or count != receipt.get('pollCount')
                        or key != self.h.store.response_key('homework-tencent:' + call['id'] + ':' + envelope['attempt'])):
                    raise ValueError('invalid Tencent query reservation')
                response = raw.get('Response') if isinstance(raw, dict) else None
                field = 'SentenceSuggests' if receipt['analysisKind'] == 'essay' else 'MarkInfos'
                if (isinstance(response, dict) and not response.get('Error') and response.get('JobStatus') == 'DONE'
                        and isinstance(response.get(field), list) and all(isinstance(v, dict) for v in response[field])):
                    completed[receipt['jobIds'][index]] = self._reference(key, data, raw_bytes, envelope['attempt'])
        return {**receipt, 'completedJobs': completed}

    def _normalize_saved(self, job, row, page, call, receipt, *, output_page_id=None):
        try:
            return self._normalize_saved_checked(job, row, page, call, receipt, output_page_id=output_page_id)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise ApiError('homework_recognition_invalid_schema', '原批改回执需要核对，任务编号已保留，不会重新提交', 409) from error

    def _normalize_saved_checked(self, job, row, page, call, receipt, *, output_page_id=None):
        from services.homework_tencent_normalizer import normalize_question_page, normalize_essay_page
        completed = receipt.get('completedJobs', {})
        ids = self._job_ids({'jobIds': receipt.get('jobIds')})
        if any(job_id not in completed for job_id in ids) or receipt.get('failedJobs'):
            raise ApiError('homework_recognition_invalid_schema', '原批改结果尚未完整保存，不会重新提交', 409)
        raws = []
        for index, job_id in enumerate(ids):
            saved = completed[job_id]
            if saved.get('storageKey') and int(saved['attempt'].split(':')[1]) != index:
                raise ValueError('completed Tencent job identity changed')
            raws.append(self._completed_raw(job, row, page, call, saved))
        geometry = receipt.get('submittedGeometry', {})
        frame_matches = all(geometry.get(k) in (None, receipt[dimension]) for k, dimension in
            (('inputWidth', 'width'), ('submittedWidth', 'width'), ('inputHeight', 'height'), ('submittedHeight', 'height')))
        submit_raw = self._load_raw(job, row, page, call, receipt['requestJournalKey'])
        normalize = normalize_essay_page if receipt['analysisKind'] == 'essay' else normalize_question_page
        maximum = {'maximum_items': self.policy['maxItemsPerPage']} if receipt['analysisKind'] != 'essay' else {}
        result = normalize(raws, submit_receipts=[submit_raw], page_id=output_page_id or page['id'],
            width=receipt['width'] if frame_matches else 0, height=receipt['height'] if frame_matches else 0,
            grade=row['grade_code'], subject=row['subject'], policy=self.h.policy, **maximum)
        result['normalizationContextSha256'] = self._normalization_context(row)
        return result

    @staticmethod
    def _job_ids(response):
        ids = response.get('jobIds') or [response.get('jobId')]
        if (not isinstance(ids, list) or not ids or len(ids) > 20
                or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', v) for v in ids)):
            raise ValueError('no reliable Tencent JobId')
        return list(dict.fromkeys(ids))

    def _recover_submit(self, job, row, page, call, receipt):
        try:
            raw, envelope, data, raw_bytes = self._load_raw(job, row, page, call,
                receipt['requestJournalKey'], include_envelope=True)
            response = raw.get('Response', {})
            if response.get('Error'):
                self._failure(job, call['id'], 'homework_tencent_rejected')
                raise ApiError('homework_tencent_rejected', '批改服务未接受这张照片', 409)
            with self.h.repository.transaction() as conn:
                self.h._current(conn, job)
                latest = conn.execute('SELECT receipt_json FROM homework_provider_calls WHERE id=? FOR UPDATE', (call['id'],)).fetchone()
                saved_receipt = parsed(latest['receipt_json'], {})
                reference = self._reference(receipt['requestJournalKey'], data, raw_bytes, 'submit')
                saved_receipt['submitResponse'] = reference
                metadata = envelope.get('metadata') or {}
                if not saved_receipt.get('submittedGeometry'):
                    saved_receipt['submittedGeometry'] = {k: metadata.get(k) for k in ('inputWidth', 'inputHeight',
                        'submittedWidth', 'submittedHeight', 'submittedFormat', 'submittedSha256')}
                self._record_journal_action(conn, row, call, reference)
                conn.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(saved_receipt), call['id']))
            return self._save_job_ids(job, call, {'jobId': response.get('JobId'), 'jobIds': response.get('JobIds'), 'providerRequestId': response.get('RequestId')})
        except ApiError as error:
            if error.code == 'homework_asset_missing':
                return None
            raise
        except (ValueError, KeyError, TypeError):
            return None

    def _save_job_ids(self, job, call, response):
        ids = self._job_ids(response)
        h = self.h
        with h.repository.transaction() as conn:
            h._current(conn, job)
            latest = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call['id'],)).fetchone()
            if not latest or latest['status'] == 'deleted':
                raise ApiError('homework_job_superseded', '批改任务已撤销', 409)
            receipt = parsed(latest['receipt_json'], {})
            receipt.update(jobIds=list(dict.fromkeys(ids)), providerRequestId=response.get('providerRequestId'),
                nextPollAt=h.clock() + self.policy['firstPollMilliseconds'], externalStatus='WAIT', pollingStartedAt=h.clock())
            geometry = {k: response.get(k) for k in ('inputWidth', 'inputHeight', 'submittedWidth',
                'submittedHeight', 'submittedFormat', 'submittedSha256') if response.get(k) is not None}
            receipt['submittedGeometry'] = {**receipt.get('submittedGeometry', {}), **geometry}
            conn.execute('UPDATE homework_provider_calls SET status=?,receipt_json=?,error_code=NULL,updated_at=? WHERE id=?',
                ('submitted', canonical(receipt), h.clock(), call['id']))
            return receipt

    def _handle_submit_error(self, job, call_id, error):
        if isinstance(error, ApiError) and error.code == 'homework_job_superseded':
            raise error
        classification = getattr(error, 'classification', '')
        # Configuration errors are pre-dispatch and may resume safely after setup.
        if classification == 'configuration' or error.__class__.__name__ == 'TencentConfigurationError':
            code = 'homework_provider_unconfigured'
            self._failure(job, call_id, code)
        elif error.__class__.__name__ == 'TencentKnownError':
            code = 'homework_tencent_rejected'
            self._failure(job, call_id, code)
        else:
            code = 'homework_provider_unknown'
            self._failure(job, call_id, code, unknown=True)
        raise ApiError(code, '批改请求未完成，照片和请求记录已保存', 409)

    def _failure(self, job, call_id, code, *, unknown=False):
        with self.h.repository.transaction() as conn:
            self.h._current(conn, job)
            conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status<>?',
                ('unknown' if unknown else 'failed', code, self.h.clock(), call_id, 'deleted'))

    def _poll(self, job, row, page, call, receipt):
        h = self.h
        try:
            receipt = self._recover_completed(job, row, page, call, receipt)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise ApiError('homework_recognition_invalid_schema', '原批改回执需要核对，任务编号已保留，不会重新提交', 409) from error
        completed = receipt.get('completedJobs', {})
        with h.repository.transaction() as conn:
            h._current(conn, job)
            self._record_journal_actions(conn, row, call, receipt)
            conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?',
                (canonical(receipt), h.clock(), call['id']))
        failed_jobs = receipt.get('failedJobs', {})
        for index, job_id in enumerate(receipt['jobIds']):
            if job_id in completed or job_id in failed_jobs:
                continue
            if (int(receipt.get('windowPollCount', 0)) >= self.policy['maxQueriesPerPage']
                    or h.clock() - receipt.get('pollingStartedAt', call['dispatched_at']) >= self.policy['maxPollingMilliseconds']):
                self._stop_queries(job, call['id'], 'homework_tencent_query_limit', 'PollingDeadlineExceeded')
                raise ApiError('homework_tencent_query_limit', '批改任务等待较久，自动查询已暂停，可继续查询原任务', 409)
            with h.repository.transaction() as conn:
                h._current(conn, job)
                latest = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call['id'],)).fetchone()
                receipt = parsed(latest['receipt_json'], {})
                receipt['pollCount'] = int(receipt.get('pollCount', 0)) + 1
                receipt['windowPollCount'] = int(receipt.get('windowPollCount', 0)) + 1
                attempt = f'poll:{index}:{receipt["pollCount"]}'
                receipt.update(nextPollAt=h.clock() + min(self.policy['maxPollMilliseconds'], self.policy['firstPollMilliseconds'] * 2 ** min(receipt['windowPollCount'], 4)),
                    responseJournalKey=h.store.response_key('homework-tencent:' + call['id'] + ':' + attempt))
                conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?', (canonical(receipt), h.clock(), call['id']))
            try:
                query = h.provider.describe_essay if receipt['analysisKind'] == 'essay' else h.provider.describe_question
                response = query(job_id, receipt_callback=self._callback(job, row, page, call, attempt))
            except Exception as error:
                if isinstance(error, ApiError) and error.code == 'homework_job_superseded':
                    raise
                classification = getattr(error, 'classification', '')
                code = getattr(error, 'code', 'QueryUnavailable')
                known = classification == 'known_rejection' or error.__class__.__name__ == 'TencentKnownError'
                permanent = classification == 'not_dispatched' or known and (
                    any(str(code).startswith(prefix) for prefix in self.policy['permanentQueryErrorPrefixes'])
                    or not any(str(code).startswith(prefix) for prefix in self.policy['transientQueryErrorPrefixes']))
                if permanent:
                    self._stop_queries(job, call['id'], 'homework_tencent_query_failed', str(code)[:160])
                    raise ApiError('homework_tencent_query_failed', '批改任务查询失败，已停止自动查询，原任务编号已保留', 409)
                # Queries are repeatable; an HTTP timeout says nothing about a
                # previously accepted paid submit and must never resubmit it.
                with h.repository.transaction() as conn:
                    h._current(conn, job)
                raise TencentPending(receipt['nextPollAt'])
            status = response.get('status')
            with h.repository.transaction() as conn:
                h._current(conn, job)
                latest = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call['id'],)).fetchone()
                receipt = parsed(latest['receipt_json'], {})
                receipt['externalStatus'] = status if status in {'WAIT', 'RUN', 'DONE', 'FAIL'} else 'UNKNOWN'
                if status == 'DONE':
                    reference = receipt.get('receivedResponse', {})
                    if reference.get('attempt') != attempt:
                        raise ApiError('homework_recognition_invalid_schema', '批改回执未保存，原任务编号已保留', 409)
                    # Bounded raw files hold the provider body; the SQL row only
                    # stores an address and digests, including for large papers.
                    completed[job_id] = reference
                    receipt['completedJobs'] = completed
                elif status == 'FAIL':
                    failed_jobs[job_id] = {'errorCode': response.get('errorCode') or 'ProviderJobFailed'}
                    receipt['failedJobs'] = failed_jobs
                conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?', (canonical(receipt), h.clock(), call['id']))
            if status not in {'DONE', 'FAIL'}:
                raise TencentPending(receipt['nextPollAt'])
        if failed_jobs:
            # In particular a multi-job essay must reach a terminal state for
            # every accepted JobId; a failed first job cannot hide a running one.
            self._failure(job, call['id'], 'homework_tencent_failed')
            raise ApiError('homework_tencent_failed', '批改服务未能完成所有任务，请核对照片', 409)
        result = self._normalize_saved(job, row, page, call, receipt)
        with h.repository.transaction() as conn:
            h._current(conn, job)
            conn.execute('UPDATE homework_provider_calls SET status=?,result_json=?,error_code=NULL,updated_at=? WHERE id=?',
                ('succeeded', canonical(result), h.clock(), call['id']))
        return result

    def _stop_queries(self, job, call_id, error_code, provider_code):
        h = self.h
        with h.repository.transaction() as conn:
            h._current(conn, job)
            call = conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE', (call_id,)).fetchone()
            receipt = parsed(call['receipt_json'], {})
            receipt.update(queryErrorCode=provider_code, queryStoppedAt=h.clock())
            conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,receipt_json=?,updated_at=? WHERE id=? AND status<>?',
                ('query_failed', error_code, canonical(receipt), h.clock(), call_id, 'deleted'))
