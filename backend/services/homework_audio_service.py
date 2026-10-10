"""Pre-generate teacher clips through OpenMAIC's existing server TTS registry.

This domain owns its durable, capped call receipts; it does not pretend homework
is a published classroom. No browser voice, direct provider credentials or blind
paid retries. Existing OpenMAIC TTS behavior is unchanged.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import wave
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from core.errors import ApiError
from core.security import now_ms
from services.teacher_speech import normalize_teacher_speech


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


class HomeworkAudioService:
    def __init__(self,database,*,asset_store,runtime_base_url,enabled=False,max_calls=200,max_characters=30000,transport=None,paid_budget_service=None,internal_token=""):
        self.database=database
        self.store=asset_store
        self.url=str(runtime_base_url or '').rstrip('/')
        self.enabled=enabled
        self.max_calls=max(1,min(int(max_calls),1000))
        self.max_characters=max(1,min(int(max_characters),100000))
        self.transport=transport or self._request
        self.budget=paid_budget_service
        self.internal_token=str(internal_token or "")

    def _request(self,payload,headers):
        # Server-configured origin, never a user supplied destination. No redirects.
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                return None
        request=Request(self.url+'/api/generate/tts',data=encoded(payload).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json',**headers})
        opener=urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(request,timeout=45) as response:
                body=response.read(24*1024*1024+1)
                if len(body)>24*1024*1024:
                    raise ValueError('audio too large')
                return json.loads(body)
        except HTTPError as exc:
            try:
                error=json.loads(exc.read(8192))
                code=error.get('errorCode',error.get('error',{}))
                code=code.get('code') if isinstance(code,dict) else code
            except Exception:
                code=None
            if code in {'MISSING_API_KEY','PROVIDER_DISABLED','MISSING_REQUIRED_FIELD','TTS_MODEL_NOT_ALLOWED'}:
                raise ApiError('homework_audio_unconfigured','Qwen老师语音服务尚未配置',503)
            raise

    def ensure(self,*,request_id,text,subject,submission_id,item_id,revision):
        if not self.enabled or not self.url:
            raise ApiError('homework_audio_unconfigured','Qwen老师语音服务尚未配置',503)
        origin=urlparse(self.url)
        if origin.scheme not in {'http','https'} or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment:
            raise ApiError('homework_audio_unconfigured','老师语音服务地址无效',503)
        if not isinstance(text,str) or not 1<=len(text)<=1000:
            raise ApiError('homework_audio_text_invalid','老师语音文本无效',400)
        try:
            text=normalize_teacher_speech(text,maximum_characters=1000)
        except ValueError:
            raise ApiError('homework_audio_text_invalid','老师语音文本无效',400) from None
        teacher=get_formal_subject_qwen_voice_identity(subject)
        payload={'text':text,'audioId':request_id,'ttsProviderId':teacher.tts_provider_id,
            'ttsModelId':teacher.tts_model_id,'ttsVoice':teacher.voice_id,'ttsSpeed':1.0}
        sha=hashlib.sha256(encoded({'schema':'mira.homework-audio.v1','teacher':teacher.to_target_payload(),'request':{k:v for k,v in payload.items() if k!='audioId'}}).encode()).hexdigest()
        now=now_ms()
        with self.database.transaction() as conn:
            submission=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(submission_id,)).fetchone()
            if submission is None or submission['deleted_at'] is not None:
                raise ApiError('homework_not_found','作业已删除',404)
            validation=submission['source']=='paid_validation'
            maximum_calls=min(self.max_calls,5) if validation else self.max_calls
            current=conn.execute('SELECT * FROM homework_audio_receipts WHERE id=? FOR UPDATE',(request_id,)).fetchone()
            if current:
                if current['request_sha256']!=sha:
                    raise ApiError('homework_audio_conflict','老师语音请求已变化',409)
                if current['status']=='succeeded':
                    result=json.loads(current['result_json'])
                    if hashlib.sha256(self.store.read(result['storageKey'])).hexdigest()!=result['sha256']:
                        raise ApiError('homework_audio_missing','已生成的音频损坏，需要恢复原文件',409)
                    return result
                if current['status']!='unconfigured':
                    raise ApiError('homework_audio_unknown','此前语音请求结果待核对，不会重复调用',409)
            cached=conn.execute('SELECT * FROM homework_audio_receipts WHERE submission_id=? AND request_sha256=? AND status=? LIMIT 1',(submission_id,sha,'succeeded')).fetchone()
            if cached:
                result=json.loads(cached['result_json'])
                # Same submission only; no cross-family private speech reuse.
                if hashlib.sha256(self.store.read(result['storageKey'])).hexdigest()!=result['sha256']:
                    raise ApiError('homework_audio_missing','已生成的音频损坏',409)
                return result
            uncertain=conn.execute('SELECT id FROM homework_audio_receipts WHERE submission_id=? AND request_sha256=? AND status IN (?,?) LIMIT 1',(submission_id,sha,'dispatched','unknown')).fetchone()
            if uncertain:
                raise ApiError('homework_audio_unknown','相同语音此前的结果仍待核对，不会再次调用',409)
            if validation and conn.execute('SELECT id FROM homework_audio_receipts WHERE submission_id=? AND status IN (?,?) LIMIT 1',(submission_id,'dispatched','unknown')).fetchone():
                raise ApiError('homework_audio_unknown','验收语音此前的结果仍待核对，已停止后续调用',409)
            # A deleted/stale result still consumed a dispatch in this bounded
            # validation. Changing a page or item cannot reset its paid limit.
            excluded='unconfigured' if validation else 'deleted'
            used=conn.execute('SELECT COUNT(*) AS calls, COALESCE(SUM(character_count),0) AS characters FROM homework_audio_receipts WHERE submission_id=? AND status NOT IN (?,?)',(submission_id,'unconfigured',excluded)).fetchone()
            if used['calls']>=maximum_calls or used['characters']+len(text)>self.max_characters:
                raise ApiError('homework_audio_budget_exceeded','作业语音已达到本份额度，已保留完成部分',409)
            if current:
                conn.execute('UPDATE homework_audio_receipts SET status=?,updated_at=? WHERE id=?',('dispatched',now,request_id))
            else:
                conn.execute('INSERT INTO homework_audio_receipts (id,submission_id,item_id,revision,request_sha256,status,character_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',(request_id,submission_id,item_id,revision,sha,'dispatched',len(text),now,now))
        try:
            if self.budget is None or not self.internal_token:
                raise ApiError('homework_audio_unconfigured','作业老师语音预算服务尚未配置',503)
            try:
                binding=self.budget.issue_homework_authorization(submission_id=submission_id,item_id=item_id,revision=revision)
            except ApiError as error:
                # No external call happened. Preserve the precise safe budget reason for operators.
                raise ApiError('homework_audio_unconfigured','作业老师语音预算未通过：'+error.code,503)
            if not isinstance(binding,dict) or binding.get('required') is not True or not isinstance(binding.get('authorizationId'),str) or len(binding['authorizationId'])!=64:
                raise ApiError('homework_audio_unconfigured','作业老师语音预算尚未授权',503)
            headers={'X-Mira-Paid-Budget-Required':'1','X-Mira-Paid-Budget-Authorization':binding['authorizationId'],'X-Mira-Internal-Token':self.internal_token}
            response=self.transport(payload,headers)
            response_sha=hashlib.sha256(encoded(response).encode()).hexdigest()
            saved={'schemaVersion':'mira.homework-audio-response.v1','capturedAt':now_ms(),
                'requestId':request_id,'submissionId':submission_id,'itemId':item_id,'itemRevision':revision,
                'requestSha256':sha,'responseSha256':response_sha,'transportResponse':response,
                'teacher':{'providerId':teacher.tts_provider_id,'modelId':teacher.tts_model_id,'voiceId':teacher.voice_id},
                'budget':{'scope':'homework.v1','characters':len(text),'maximumCalls':maximum_calls,'maximumCharacters':self.max_characters}}
            # Persist returned bytes before decoding audio. The DB only receives
            # a small reference, independent of MySQL max_allowed_packet. The
            # private envelope retains its owner/request if the DB write fails.
            saved_bytes=encoded(saved).encode()
            if len(saved_bytes)>25*1024*1024:
                raise ValueError('audio response too large')
            response_key=self.store.put(saved_bytes,namespace='homework-response:'+request_id,suffix='json')
            reference={'schemaVersion':'mira.homework-audio-response-ref.v1','savedResponseKey':response_key,
                'savedResponseSha256':hashlib.sha256(saved_bytes).hexdigest(),'requestSha256':sha}
            stale=False
            with self.database.transaction() as conn:
                submission=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(submission_id,)).fetchone()
                item=conn.execute('SELECT revision FROM homework_items WHERE id=? AND submission_id=?',(item_id,submission_id)).fetchone()
                current=conn.execute('SELECT * FROM homework_audio_receipts WHERE id=? FOR UPDATE',(request_id,)).fetchone()
                if submission is None or submission['deleted_at'] is not None or item is None or item['revision']!=revision or current is None or current['status']=='deleted':
                    conn.execute('UPDATE homework_audio_receipts SET status=?,result_json=NULL WHERE id=?',('deleted',request_id))
                    self._queue_file_delete(conn,response_key)
                    stale=True
                else:
                    conn.execute('UPDATE homework_audio_receipts SET result_json=?,updated_at=? WHERE id=? AND status=?',(encoded(reference),now_ms(),request_id,'dispatched'))
            if stale:
                raise ApiError('homework_job_superseded','作业已删除或题目已变化',409)
            return self._materialize_saved_response(request_id=request_id,submission_id=submission_id,item_id=item_id,revision=revision,saved=saved)
        except Exception as error:
            if isinstance(error,ApiError) and error.code=='homework_job_superseded':
                raise
            safe=isinstance(error,ApiError) and error.code=='homework_audio_unconfigured'
            with self.database.transaction() as conn:
                conn.execute('UPDATE homework_audio_receipts SET status=?,error_code=?,updated_at=? WHERE id=? AND status=?',('unconfigured' if safe else 'unknown','homework_audio_unconfigured' if safe else 'homework_audio_unknown',now_ms(),request_id,'dispatched'))
            if safe:
                raise
            raise ApiError('homework_audio_unknown','语音结果未确认，已保留请求且停止重复调用',409)

    def recover_saved_response(self,*,request_id,submission_id,item_id,revision):
        """Internal explicit reconciliation of received bytes; NEVER dispatches.

        The caller must authorize the owned submission before invoking this
        service boundary. This is deliberately not an unauthenticated HTTP API.
        Missing response evidence stays unknown, including pre-fix receipts.
        """
        with self.database.transaction() as conn:
            submission=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(submission_id,)).fetchone()
            item=conn.execute('SELECT revision FROM homework_items WHERE id=? AND submission_id=?',(item_id,submission_id)).fetchone()
            current=conn.execute('SELECT * FROM homework_audio_receipts WHERE id=? FOR UPDATE',(request_id,)).fetchone()
            if (submission is None or submission['deleted_at'] is not None or item is None or item['revision']!=revision
                    or current is None or current['submission_id']!=submission_id or current['item_id']!=item_id or current['revision']!=revision):
                raise ApiError('homework_audio_recovery_scope_invalid','作业语音恢复范围已失效',409)
            reference=json.loads(current['result_json']) if current['result_json'] else None
            if current['status']=='succeeded':
                if hashlib.sha256(self.store.read(reference['storageKey'])).hexdigest()!=reference['sha256']:
                    raise ApiError('homework_audio_missing','老师音频校验失败，需要恢复原文件',409)
                return reference
            if current['status'] not in {'unknown','dispatched'} or not isinstance(reference,dict) or reference.get('schemaVersion')!='mira.homework-audio-response-ref.v1':
                raise ApiError('homework_audio_response_missing','没有保存的语音响应，不能恢复或再次调用',409)
            try:
                saved_bytes=self.store.read(reference['savedResponseKey'])
                if len(saved_bytes)>25*1024*1024 or hashlib.sha256(saved_bytes).hexdigest()!=reference['savedResponseSha256']:
                    raise ValueError('response hash mismatch')
                saved=json.loads(saved_bytes)
            except Exception:
                raise ApiError('homework_audio_response_invalid','保存的语音响应校验失败，已停止恢复',409)
            if (saved.get('schemaVersion')!='mira.homework-audio-response.v1' or saved.get('requestId')!=request_id
                    or saved.get('submissionId')!=submission_id or saved.get('itemId')!=item_id or saved.get('itemRevision')!=revision
                    or reference.get('requestSha256')!=current['request_sha256'] or saved.get('requestSha256')!=current['request_sha256']
                    or saved.get('responseSha256')!=hashlib.sha256(encoded(saved.get('transportResponse')).encode()).hexdigest()):
                raise ApiError('homework_audio_response_invalid','保存的语音响应校验失败，已停止恢复',409)
        try:
            receipt=self._materialize_saved_response(request_id=request_id,submission_id=submission_id,item_id=item_id,revision=revision,saved=saved)
        except ApiError:
            raise
        except Exception:
            raise ApiError('homework_audio_response_invalid','保存的语音尚不能完成校验或落盘，没有再次调用',409)
        # Reconciliation itself never enqueues or dispatches. Once every unknown
        # audio outcome is reconciled, a parent may explicitly resume media work.
        with self.database.transaction() as conn:
            submission=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(submission_id,)).fetchone()
            item=conn.execute('SELECT revision FROM homework_items WHERE id=? AND submission_id=?',(item_id,submission_id)).fetchone()
            pending=conn.execute('SELECT id FROM homework_audio_receipts WHERE submission_id=? AND status IN (?,?) LIMIT 1',(submission_id,'dispatched','unknown')).fetchone()
            vision_pending=conn.execute('SELECT id FROM homework_provider_calls WHERE submission_id=? AND status IN (?,?) LIMIT 1',(submission_id,'dispatched','unknown')).fetchone()
            job=conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=? FOR UPDATE',(submission_id,submission['revision'])).fetchone() if submission else None
            if (submission and submission['deleted_at'] is None and item and item['revision']==revision and pending is None and vision_pending is None
                    and job and job['status']=='failed' and job['error_code']=='homework_audio_unknown'):
                conn.execute('UPDATE homework_jobs SET error_code=?,updated_at=? WHERE id=?',('homework_media_pending',now_ms(),job['id']))
                conn.execute('UPDATE homework_submissions SET status=?,error_code=?,updated_at=? WHERE id=?',('media_preparing','homework_media_pending',now_ms(),submission_id))
        return receipt

    def _materialize_saved_response(self,*,request_id,submission_id,item_id,revision,saved):
        response=saved['transportResponse']
        # Native apiSuccess spreads fields at the top level; no data envelope.
        result=response if isinstance(response,dict) and response.get('success') is True else None
        if not isinstance(result,dict) or result.get('audioId')!=request_id or result.get('format') not in {'wav','mp3'}:
            raise ValueError('invalid TTS receipt')
        audio=base64.b64decode(result['base64'],validate=True)
        if not 44<=len(audio)<=16*1024*1024:
            raise ValueError('invalid audio length')
        fmt=result['format']
        if fmt=='wav':
            with wave.open(io.BytesIO(audio),'rb') as wav:
                if wav.getnframes()<=0 or wav.getframerate()<=0:
                    raise ValueError('empty WAV')
                duration=round(wav.getnframes()/wav.getframerate()*1000)
        else:
            if not (audio.startswith(b'ID3') or audio[:2] in {b'\xff\xfb',b'\xff\xf3',b'\xff\xf2'}):
                raise ValueError('invalid MP3')
            duration=None
        key=self.store.put(audio,namespace=submission_id,suffix=fmt)
        receipt={'status':'ready','storageKey':key,'mimeType':'audio/wav' if fmt=='wav' else 'audio/mpeg',
            'sha256':hashlib.sha256(audio).hexdigest(),'durationMs':duration,**saved['teacher'],
            'receiptId':request_id,'budget':saved['budget'],'responseSha256':saved['responseSha256']}
        stale=False
        with self.database.transaction() as conn:
            submission=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(submission_id,)).fetchone()
            item=conn.execute('SELECT revision FROM homework_items WHERE id=? AND submission_id=?',(item_id,submission_id)).fetchone()
            current=conn.execute('SELECT * FROM homework_audio_receipts WHERE id=? FOR UPDATE',(request_id,)).fetchone()
            response_key=json.loads(current['result_json']).get('savedResponseKey') if current and current['result_json'] else None
            if (submission is None or submission['deleted_at'] is not None or item is None or item['revision']!=revision
                    or current is None or current['submission_id']!=submission_id or current['item_id']!=item_id
                    or current['revision']!=revision or current['status']=='deleted'):
                # In-flight result is discarded after deletion/correction; never republish it.
                self._queue_file_delete(conn,key)
                conn.execute('UPDATE homework_audio_receipts SET status=?,result_json=NULL WHERE id=?',('deleted',request_id))
                stale=True
            else:
                conn.execute('UPDATE homework_audio_receipts SET status=?,result_json=?,error_code=NULL,updated_at=? WHERE id=?',('succeeded',encoded(receipt),now_ms(),request_id))
            if response_key:
                self._queue_file_delete(conn,response_key)
        if stale:
            raise ApiError('homework_job_superseded','作业已删除或题目已变化',409)
        return receipt

    @staticmethod
    def _queue_file_delete(conn,key):
        if conn.execute('SELECT storage_key FROM homework_file_deletions WHERE storage_key=?',(key,)).fetchone() is None:
            conn.execute('INSERT INTO homework_file_deletions (storage_key,created_at) VALUES (?,?)',(key,now_ms()))

    def revoke_submission(self,conn,submission_id):
        rows=conn.execute('SELECT result_json FROM homework_audio_receipts WHERE submission_id=? AND result_json IS NOT NULL',(submission_id,)).fetchall()
        for row in rows:
            saved=json.loads(row['result_json'])
            for key in (saved.get('storageKey'),saved.get('savedResponseKey')):
                if key:
                    self._queue_file_delete(conn,key)
        conn.execute('UPDATE homework_audio_receipts SET status=?,result_json=NULL WHERE submission_id=?',('deleted',submission_id))
