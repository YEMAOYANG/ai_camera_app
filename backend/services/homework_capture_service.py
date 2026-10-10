"""Explicitly authorized, non-disruptive document capture; existing snapshot untouched."""
import uuid
import hashlib
from core.errors import ApiError
from integrations.camera_runtime.document_capture import DocumentCaptureRequest,require_document_capture,validate_document_receipt
from services.homework_assets import normalize_image
from services.homework_service import canonical,digest,identifier


class HomeworkCaptureService:
    def __init__(self,homework,*,runtime_resolver,approved_evidence_ids=()):
        self.homework=homework
        self.resolver=runtime_resolver
        self.approved=frozenset(approved_evidence_ids)

    def _availability(self,family,device):
        if not self.homework.processing_enabled:
            return {'available':False,'unavailableReason':'AI分析尚未启用，请使用家长App保存照片'}
        try:
            resolved=self.resolver.resolve(family_id=family,device_id=device,require_device=True)
            require_document_capture(resolved.bridge.adapter,device,self.approved)
            return {'available':True}
        except Exception:
            return {'available':False,'unavailableReason':'请使用家长App拍照；设备暂未通过作业拍摄验收'}

    def parent_authorizations(self,token,child_id):
        svc=self.homework
        context=svc._parent(token)
        with svc.repository.transaction() as conn:
            family=svc._permit(conn,context,True)
            if svc.repository.child(conn,family,child_id) is None:
                raise ApiError('child_not_found','没有找到孩子',404)
            grants=conn.execute('SELECT * FROM homework_capture_authorizations WHERE family_id=? AND child_id=?',(family,child_id)).fetchall()
            tasks=conn.execute('SELECT id,title FROM tasks WHERE family_id=? AND child_id=? AND type=? AND status NOT IN (?,?)',(family,child_id,'learning','completed','cancelled')).fetchall()
            devices=conn.execute('SELECT id,name FROM devices WHERE family_id=? AND status!=?',(family,'unbound')).fetchall()
        return {'ok':True,'authorizations':[{'taskId':g['task_id'],'deviceId':g['device_id'],'revision':g['revision'],
            'enabled':bool(g['enabled']),'expiresAt':g['expires_at']} for g in grants],
            'learningTasks':[dict(t) for t in tasks],
            'devices':[{**dict(d),**self._availability(family,d['id'])} for d in devices]}

    def student_tasks(self,principal):
        svc=self.homework
        with svc.repository.transaction() as conn:
            rows=conn.execute("""SELECT a.task_id,a.device_id,t.title FROM homework_capture_authorizations a
                JOIN tasks t ON t.id=a.task_id AND t.child_id=a.child_id AND t.family_id=a.family_id
                JOIN devices d ON d.id=a.device_id AND d.family_id=a.family_id
                WHERE a.family_id=? AND a.child_id=? AND a.enabled=1 AND a.expires_at>?
                AND t.type=? AND t.status NOT IN (?,?) AND d.status!=?""",
                (principal['family_id'],principal['child_id'],svc.clock(),'learning','completed','cancelled','unbound')).fetchall()
        return [{'taskId':r['task_id'],'title':r['title'],**self._availability(principal['family_id'],r['device_id'])} for r in rows]

    def authorize(self,token,child_id,data):
        svc=self.homework
        context=svc._parent(token)
        task_id=identifier(data.get('taskId'))
        device_id=identifier(data.get('deviceId'))
        now=svc.clock()
        if type(data.get('enabled')) is not bool or type(data.get('expiresAt')) is not int or not now<data['expiresAt']<=now+7*86400000:
            raise ApiError('homework_capture_authorization_invalid','授权最长7天，请选择有效的到期时间',400)
        with svc.repository.transaction() as conn:
            family=svc._permit(conn,context,True)
            child=svc.repository.child(conn,family,child_id,lock=True)
            if child is None:
                raise ApiError('child_not_found','没有找到孩子',404)
            if child['grade_code'] not in {f'primary_{n}' for n in range(1,7)}:
                raise ApiError('homework_grade_unsupported','此年级尚未开放作业检查',409)
            self._bound(conn,family,child_id,task_id,device_id)
            old=conn.execute('SELECT * FROM homework_capture_authorizations WHERE child_id=? AND task_id=? FOR UPDATE',(child_id,task_id)).fetchone()
            rev=old['revision'] if old else 0
            if data.get('revision')!=rev:
                raise ApiError('homework_revision_conflict','拍摄授权已更新，请刷新',409)
            if old:
                conn.execute('UPDATE homework_capture_authorizations SET device_id=?,revision=?,enabled=?,expires_at=?,granted_by=?,updated_at=? WHERE child_id=? AND task_id=?',(device_id,rev+1,int(data['enabled']),data['expiresAt'],context['user']['id'],now,child_id,task_id))
            else:
                conn.execute('INSERT INTO homework_capture_authorizations (child_id,task_id,family_id,device_id,revision,enabled,expires_at,granted_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',(child_id,task_id,family,device_id,1,int(data['enabled']),data['expiresAt'],context['user']['id'],now))
        return {'ok':True,'authorization':{'childId':child_id,'taskId':task_id,'deviceId':device_id,'revision':rev+1,'enabled':data['enabled'],'expiresAt':data['expiresAt']}}

    def _bound(self,conn,family,child,task,device):
        task_row=conn.execute('SELECT * FROM tasks WHERE family_id=? AND child_id=? AND id=?',(family,child,task)).fetchone()
        device_row=conn.execute('SELECT * FROM devices WHERE family_id=? AND id=?',(family,device)).fetchone()
        if task_row is None or task_row['type']!='learning' or task_row['status'] in {'completed','cancelled'}:
            raise ApiError('homework_capture_task_invalid','当前任务不可拍摄作业',409)
        if device_row is None or device_row['status']=='unbound':
            raise ApiError('homework_capture_device_invalid','设备已解绑或不属于这个家庭',409)
        return task_row,device_row

    def capture(self,token,data):
        svc=self.homework
        principal=svc._student(token)
        if not svc.processing_enabled:
            raise ApiError('homework_analysis_paused','AI分析尚未启用，请使用家长App保存照片',503)
        if set(data)-{'taskId','idempotencyKey'}:
            raise ApiError('homework_capture_request_invalid','拍摄请求不能选择任意设备',400)
        task_id=identifier(data.get('taskId'))
        key=identifier(data.get('idempotencyKey'))
        family,child=principal['family_id'],principal['child_id']
        now=svc.clock()
        with svc.repository.transaction() as conn:
            child_row=svc.repository.child(conn,family,child,lock=True)
            if child_row is None:
                raise ApiError('child_not_found','没有找到孩子',404)
            grant=conn.execute('SELECT * FROM homework_capture_authorizations WHERE child_id=? AND task_id=? AND family_id=?',(child,task_id,family)).fetchone()
            if grant is None or not grant['enabled'] or grant['expires_at']<=now:
                raise ApiError('homework_capture_consent_required','请先由家长授权本次作业拍摄',403)
            self._bound(conn,family,child,task_id,grant['device_id'])
            previous=conn.execute('SELECT * FROM homework_capture_requests WHERE family_id=? AND child_id=? AND idempotency_key=?',(family,child,key)).fetchone()
            if previous:
                if previous['task_id']!=task_id:
                    raise ApiError('homework_idempotency_conflict','拍摄编号已用于另一项作业',409)
                if previous['status']=='succeeded':
                    return svc._view(conn,svc.repository.submission(conn,family,previous['submission_id'],child=child),student=True)
                raise ApiError('homework_capture_unknown','上次拍摄结果待核对，不会重复拍摄',409)
        # Resolve only an explicitly bound device; never invoke snapshot/recovery.
        resolved=self.resolver.resolve(family_id=family,device_id=grant['device_id'],require_device=True)
        capture=require_document_capture(resolved.bridge.adapter,grant['device_id'],self.approved)
        request=DocumentCaptureRequest('hwcap_'+uuid.uuid4().hex,grant['device_id'],child,task_id,now+30000)
        with svc.repository.transaction() as conn:
            svc.repository.child(conn,family,child,lock=True)
            current=conn.execute('SELECT * FROM homework_capture_authorizations WHERE child_id=? AND task_id=? FOR UPDATE',(child,task_id)).fetchone()
            self._bound(conn,family,child,task_id,grant['device_id'])
            if not current['enabled'] or current['revision']!=grant['revision'] or current['expires_at']<=svc.clock():
                raise ApiError('homework_capture_consent_required','拍摄授权已变化',403)
            if conn.execute('SELECT id FROM homework_capture_requests WHERE family_id=? AND child_id=? AND idempotency_key=?',(family,child,key)).fetchone():
                raise ApiError('homework_capture_unknown','这次拍摄正在处理，请查询已有结果',409)
            conn.execute('INSERT INTO homework_capture_requests (id,family_id,child_id,task_id,device_id,idempotency_key,authorization_revision,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(request.request_id,family,child,task_id,grant['device_id'],key,grant['revision'],'dispatched',now,now))
        try:
            receipt=validate_document_receipt(capture(request),request,svc.clock())
            body,width,height=normalize_image(receipt.body,svc.policy)
        except Exception:
            with svc.repository.transaction() as conn:
                conn.execute('UPDATE homework_capture_requests SET status=?,error_code=?,updated_at=? WHERE id=?',('unknown','homework_capture_unknown',svc.clock(),request.request_id))
            raise ApiError('homework_capture_unknown','设备未返回可用拍摄结果，请使用App补拍',409)
        identity='hw_'+uuid.uuid4().hex
        page_id='hwp_'+uuid.uuid4().hex
        storage=svc.store.put(body,namespace=identity)
        try:
            with svc.repository.transaction() as conn:
                current=conn.execute('SELECT * FROM homework_capture_authorizations WHERE child_id=? AND task_id=? FOR UPDATE',(child,task_id)).fetchone()
                self._bound(conn,family,child,task_id,grant['device_id'])
                if not current['enabled'] or current['revision']!=grant['revision'] or current['expires_at']<=svc.clock():
                    svc.store.delete(storage)
                    raise ApiError('homework_capture_consent_required','拍摄授权已撤销，图片未提交',403)
                now=svc.clock()
                conn.execute('INSERT INTO homework_submissions (id,family_id,child_id,grade_code,subject,title,source,idempotency_key,request_sha256,revision,status,consent_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,family,child,child_row['grade_code'],'math','拍摄的数学作业','document_camera',request.request_id,digest({'capture':request.request_id}),1,'queued',grant['updated_at'],now,now))
                conn.execute('INSERT INTO homework_pages (id,submission_id,upload_key,content_sha256,storage_key,mime_type,width,height,page_order,rotation,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(page_id,identity,request.request_id,hashlib.sha256(body).hexdigest(),storage,'image/png',width,height,0,receipt.orientation,'received',now))
                conn.execute('INSERT INTO homework_jobs (id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',('hwj_'+uuid.uuid4().hex,identity,1,'queued','quality_check',now,now))
                conn.execute('UPDATE homework_capture_requests SET status=?,submission_id=?,receipt_json=?,updated_at=? WHERE id=?',('succeeded',identity,canonical({'requestId':request.request_id,'capturedAt':receipt.captured_at,'sha256':receipt.sha256,'width':width,'height':height,'orientation':receipt.orientation}),now,request.request_id))
                return svc._view(conn,svc.repository.submission(conn,family,identity),student=True)
        except Exception:
            svc.store.delete(storage)
            with svc.repository.transaction() as conn:
                conn.execute('UPDATE homework_capture_requests SET status=?,error_code=?,updated_at=? WHERE id=?',('rejected','homework_capture_consent_changed',svc.clock(),request.request_id))
            raise
