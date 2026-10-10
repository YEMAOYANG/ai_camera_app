"""One explicit reupload permission, separate from rerunning an old job.

The internal operator records the human's approval. The regular parent upload
and analyze routes still create the new work. A consumed approval remains on
the old submission, so deleting the new work cannot renew the paid permission.
"""
from __future__ import annotations

import hashlib
import json
from core.errors import ApiError

SCHEMA='mira.homework-reupload-approval.v1'
CONTRACT='durable-vision-response.v3'
APPROVAL='我确认好了我要重新上传一次'
MARKER='__operator_recognition_reupload__'
USE_MARKER='__operator_recognition_reupload_use__'
TTL=24*60*60*1000

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def parsed(value):
    return json.loads(value) if isinstance(value,str) else value

def invalid():
    raise ApiError('homework_reupload_authorization_invalid','重传授权或照片已变化，不会重复调用',409)

def response_input(service,page):
    from services.homework_recognition_recovery import _input
    return _input(service,page)

def authorize_reupload(service,conn,scope,*,approved_at,execute=False,approval_text=None):
    """The caller owns the transaction; default preflight never writes."""
    from services.homework_recognition_recovery import authorize_recovery
    # Reuse the exact owner, two original pages, old call/job and image-v3
    # preflight, but never execute it or enqueue the previous submission.
    preflight=authorize_recovery(service,conn,scope)
    if preflight.get('alreadyAuthorized'):
        invalid()
    if execute and approval_text!=APPROVAL:
        raise ApiError('homework_repair_approval_required','需要本次重传的明确授权',409)
    now=service.clock()
    if type(approved_at) is not int or not 0<=now-approved_at<TTL:
        invalid()
    row=service.repository.submission(conn,scope['familyId'],scope['submissionId'],child=scope['childId'],lock=execute)
    old_call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(scope['unknownCallId'],)).fetchone()
    old_job=conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?',(row['id'],row['revision'])).fetchone()
    user=conn.execute('SELECT id FROM users WHERE phone=? AND family_id=?',(scope['phone'],scope['familyId'])).fetchone()
    pages=service.repository.pages(conn,row['id'])
    inputs=[response_input(service,page) for page in pages]
    selected=next(value for value in inputs if value['pageId']==old_call['page_id'])
    identity='hwreupload_'+digest([SCHEMA,row['id'],old_call['id']])[:56]
    existing=conn.execute('SELECT * FROM homework_actions WHERE id=?',(identity,)).fetchone()
    if existing:
        saved=parsed(existing['result_json'])
        if existing['request_sha256']!=digest(saved) or saved.get('scopeSha256')!=digest(scope):
            invalid()
        return {'ok':True,'authorizationId':identity,'authorized':True,'alreadyAuthorized':True,
            'maximumNewVisionCalls':1,'expiresAt':saved['expiresAt'],'oldTaskQueued':False}
    grant={'schema':SCHEMA,'authorizationId':identity,'scopeSha256':digest(scope),
        'familyId':row['family_id'],'childId':row['child_id'],'submissionId':row['id'],
        'approvedByUserId':user['id'],'approvedAt':approved_at,'recordedAt':now,'expiresAt':approved_at+TTL,
        'approvalText':APPROVAL,'oldCallId':old_call['id'],'oldCallSha256':digest(dict(old_call)),
        'oldJobId':old_job['id'],'oldJobSha256':digest(dict(old_job)),
        'input':selected,'allOriginalInputs':inputs,'baseRequestSha256':old_call['request_sha256'],
        'wireContract':CONTRACT,'maximumNewVisionCalls':1}
    if execute:
        service._processing_enabled()
        conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
            (identity,row['id'],MARKER,old_call['id'],digest(grant),canonical(grant),now))
    return {'ok':True,'authorizationId':identity,'authorized':execute,'alreadyAuthorized':False,
        'maximumNewVisionCalls':1,'expiresAt':grant['expiresAt'],'oldTaskQueued':False}

def reupload_grant(service,conn,job,row,page,image,base_sha):
    """Claim the approval for one new owned submission, under the child lock."""
    if row['source']!='parent_app' or not getattr(service.provider,'capture_received_response',False):
        return None
    if conn.execute('SELECT c.id FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id WHERE c.child_id=? AND s.family_id=? AND s.deleted_at IS NULL AND c.request_sha256=? AND c.status=? LIMIT 1',
            (row['child_id'],row['family_id'],base_sha,'succeeded')).fetchone():
        return None
    records=conn.execute('SELECT a.* FROM homework_actions a JOIN homework_submissions s ON s.id=a.submission_id WHERE s.family_id=? AND s.child_id=? AND s.deleted_at IS NULL AND a.item_id=?',
        (row['family_id'],row['child_id'],MARKER)).fetchall()
    for record in records:
        grant=parsed(record['result_json'])
        if grant.get('baseRequestSha256')!=base_sha or grant.get('submissionId')==row['id']:
            continue
        if (record['request_sha256']!=digest(grant) or grant.get('schema')!=SCHEMA
                or grant.get('authorizationId')!=record['id'] or grant.get('approvalText')!=APPROVAL
                or grant.get('familyId')!=row['family_id'] or grant.get('childId')!=row['child_id']
                or grant.get('wireContract')!=CONTRACT or grant.get('maximumNewVisionCalls')!=1
                or row['created_at']<grant.get('approvedAt',0) or row['consent_at']<grant.get('approvedAt',0)):
            invalid()
        old=service.repository.submission(conn,row['family_id'],grant['submissionId'],child=row['child_id'])
        old_call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(grant['oldCallId'],)).fetchone()
        old_job=conn.execute('SELECT * FROM homework_jobs WHERE id=?',(grant['oldJobId'],)).fetchone()
        if (not old_call or not old_job or digest(dict(old_call))!=grant['oldCallSha256']
                or digest(dict(old_job))!=grant['oldJobSha256']
                or grant['allOriginalInputs']!=[response_input(service,p) for p in service.repository.pages(conn,old['id'])]
                or hashlib.sha256(image).hexdigest()!=grant['input']['imageSha256']):
            invalid()
        binding=response_input(service,page)
        if (binding['baseRequestSha256']!=base_sha or binding['wire']!=grant['input']['wire']
                or binding['imageSha256']!=grant['input']['imageSha256']):
            invalid()
        use_id='hwreupload_use_'+digest(record['id'])[:48]
        use=conn.execute('SELECT * FROM homework_actions WHERE id=?',(use_id,)).fetchone()
        if use:
            claim=parsed(use['result_json'])
            if use['request_sha256']!=digest(claim):
                invalid()
            if claim.get('newSubmissionId')!=row['id'] or claim.get('newPageId')!=page['id']:
                continue
            if claim.get('revision')!=job['revision'] or claim.get('input')!=binding:
                invalid()
        else:
            if service.clock()>=grant['expiresAt']:
                continue
            claim={'authorizationId':record['id'],'newSubmissionId':row['id'],'newPageId':page['id'],
                'revision':job['revision'],'input':binding,'claimedAt':service.clock()}
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (use_id,old['id'],USE_MARKER,record['id'],digest(claim),canonical(claim),service.clock()))
        return {'id':record['id'],'sha256':record['request_sha256'],'expiresAt':grant['expiresAt'],
            'wire':{**binding['wire'],'responseContract':CONTRACT,'captureReceivedResponse':True},
            'wireContract':CONTRACT,'maximumNewVisionCalls':1}
    return None
