"""Durable blind image review; its evidence authorizes guidance, never grades."""
from __future__ import annotations
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from core.errors import ApiError
from integrations.ai.unavailable_vision_provider import UnavailableVisionProvider
from services.homework_assets import crop_region

ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'content/homework_source_review_policy.v3.json').read_text())
SCHEMA='mira.homework-tutor-source-review.v1'
PHASE='source_review'
REVIEW_VERSIONS=('v1','v2','v3')


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def parsed(value):
    return json.loads(value) if isinstance(value,str) else deepcopy(value or {})


def primary_digest(reply):
    """Only the immutable primary teaching content, before quality projection."""
    return digest({key:reply.get(key) for key in
        ('teacherText','steps','assessment','sourceCheck','sourceImageContract','mode','message')})


def review_call_id(turn_id,version=None):
    # Share the existing prefix: each phase consumes its own provider-call slot.
    version=version or POLICY['prompt']['version']
    if version not in REVIEW_VERSIONS: raise ValueError('unsupported source review version')
    identity={'turnId':turn_id,'phase':PHASE}
    if version!='v1': identity['reviewVersion']=version
    return 'hwtcall_'+digest(identity)[:56]


def _receipt_version(receipt):
    return receipt.get('reviewVersion','v1')


def _answer_agrees(primary,proof):
    from services.homework_answer_quality import _numeric_answer
    import re
    first=(primary.get('assessment') or {}).get('expectedAnswer','')
    second=proof.get('expectedAnswer','')
    if not isinstance(first,str) or not isinstance(second,str) or not first.strip() or not second.strip():
        return False
    a,b=_numeric_answer(first),_numeric_answer(second)
    return a==b if a is not None and b is not None else re.sub(r'\s+','',first)==re.sub(r'\s+','',second)


def _model_image_input(contract):
    """Expose one local coordinate frame; keep source provenance server-only."""
    from services.homework_tutor_image_target import region_to_target_input
    target=contract['targetReference']
    question=region_to_target_input(target['questionRegionInOriginalPage'],contract)
    if question is None: raise ApiError('homework_tutor_review_input_invalid','复核题目范围尚未确认',409)
    return {'schemaVersion':contract['schemaVersion'],'inputGeometry':deepcopy(contract['inputGeometry']),
        'sourceContentPixelBoundsInInput':deepcopy(contract['sourceContentPixelBoundsInInput']),
        'targetReference':{'ordinal':target['ordinal'],'count':target['count'],
            'regionInInput':deepcopy(target['regionInInput']),'questionRegionInInput':question}}


def _owned_journals(host,call,receipt,binding,version):
    """A known returned result needs exact owned request and response bytes."""
    if (receipt.get('schemaVersion')!=SCHEMA or receipt.get('phase')!=PHASE
            or _receipt_version(receipt)!=version or call['prompt_version']!=version
            or call['id']!=review_call_id(binding['turnId'],version)
            or call['submission_id']!=binding['scope']['submissionId']
            or call['page_id']!=binding['scope']['pageId']
            or call['child_id']!=binding['scope']['childId']):
        raise ValueError('source review receipt owner/version mismatch')
    request_body=host.store.read(receipt['requestJournalKey'])
    response_body=host.store.read(receipt['responseJournalKey'])
    if (receipt.get('requestJournalSha256')!=hashlib.sha256(request_body).hexdigest()
            or receipt.get('responseSha256')!=hashlib.sha256(response_body).hexdigest()
            or receipt.get('responseReceived') is not True):
        raise ValueError('source review journal hash mismatch')
    request=parsed(request_body.decode());saved=parsed(response_body.decode())
    expected={key:value for key,value in binding.items() if key!='reviewVersion'}
    if version!='v1' or 'reviewVersion' in receipt: expected['reviewVersion']=version
    expected.update(callId=call['id'],requestSha256=call['request_sha256'])
    if any(receipt.get(key)!=value for key,value in expected.items() if key not in {'callId','requestSha256'}):
        raise ValueError('source review receipt source mismatch')
    if any(request.get(key)!=value or saved.get(key)!=value for key,value in expected.items()):
        raise ValueError('source review journal owner/source mismatch')
    if request.get('provider')!=call['provider'] or request.get('model')!=call['model']:
        raise ValueError('source review journal provider mismatch')
    return request,saved


def _source_result(result):
    value=deepcopy(result)
    value.pop('_confirmedGuidanceReviews',None)
    value.pop('_confirmedAnswerReview',None)
    value.pop('_confirmedTencentReferenceTurns',None)
    value.pop('_referenceAnswerLayout',None)
    return value


def _scope(host,conn,row,item,result):
    page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',
        (item['page_id'],row['id'])).fetchone()
    if page is None: raise ApiError('homework_job_superseded','原题图片已经变化',409)
    return {'familyId':row['family_id'],'childId':row['child_id'],'submissionId':row['id'],
        'submissionRevision':row['revision'],'itemId':item['id'],'itemRevision':item['revision'],
        'pageId':page['id'],'sourceAssetSha256':page['content_sha256'],
        'rotation':page['rotation'],'crop':parsed(page['crop_json']),
        'resultSha256':digest(_source_result(result))}


def _text(value,limit,*,empty=False):
    if not isinstance(value,str) or len(value)>limit or not empty and not value.strip():
        raise ValueError('invalid review text')
    value.encode('utf-8',errors='strict')
    return value.strip()


def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            # Preserve exact raw bytes in the durable journal. An identical
            # repeat is deterministic; a different type or value is ambiguous.
            # JSON equality alone is unsafe because Python treats True == 1.
            if type(value[key]) is not type(item) or encoded(value[key])!=encoded(item):
                raise ValueError('conflicting duplicate review field')
            continue
        value[key]=item
    return value


def parse_review(text):
    value=json.loads(text,object_pairs_hook=_unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite review')))
    if not isinstance(value,dict): raise ValueError('invalid source review')
    check=value.get('sourceCheck')
    if not isinstance(check,dict) or check.get('status') not in {'matched','mismatch','unclear'} or check.get('basis')!='original_image':
        raise ValueError('invalid review observation')
    clean={key:check[key] for key in ('status','basis')}
    for key in ('questionLocated','questionReadable','answerLocated'):
        if type(check.get(key)) is not bool: raise ValueError('invalid review flag')
        clean[key]=check[key]
    ordinal=check.get('answerOrdinal')
    if type(ordinal) is not int or not 1<=ordinal<=200: raise ValueError('invalid review target')
    clean['answerOrdinal']=ordinal
    clean['reason']=_text(check.get('reason',''),300,empty=True)
    clean['prompt']=_text(check.get('prompt',''),1800,empty=True)
    if check.get('questionRegion') is not None:
        clean['questionRegion']=crop_region(check['questionRegion'])
    evidence=value.get('printedEvidence',[])
    if not isinstance(evidence,list) or len(evidence)>12: raise ValueError('invalid printed evidence')
    evidence=[_text(entry,300) for entry in evidence]
    answer=_text(value.get('expectedAnswer',''),1000,empty=True)
    clear=all(clean[key] for key in ('questionLocated','questionReadable','answerLocated')) and clean['status']!='unclear'
    if not clear: answer=''
    return {'sourceCheck':clean,'expectedAnswer':answer,
        'reason':_text(value.get('reason',''),600,empty=True),'printedEvidence':evidence}


def _remap_saved(text,contract):
    """Read-time replay of the same one-time input-to-page coordinate mapping."""
    value=json.loads(text,object_pairs_hook=_unique)
    check=value.get('sourceCheck') if isinstance(value,dict) else None
    if isinstance(check,dict) and check.get('questionRegion') is not None:
        from services.homework_tutor_image_target import region_from_target_input
        region=region_from_target_input(check['questionRegion'],contract)
        if region is None: raise ValueError('review source region crosses its input content')
        check['questionRegion']=region
    return encoded(value)


def run_source_review(host,record,turn,row,item,result,image,image_contract,primary_reply,*,
        current_callback,remap_callback,provider=None,reconcile_conflict=False):
    """Reserve, journal and execute one independent review for this owned turn.

    Callers supply the existing transaction/ownership guard and image remapper.
    Recovery reads the exact saved response; a missing dispatched response never
    calls a model again. No student grade, item or ability evidence is written.
    """
    from services.homework_tutor_image_target import target_contract_valid
    if (image_contract.get('schemaVersion')!=POLICY['requiredImageContract']
            or not target_contract_valid(image_contract,input_image_bytes=image)
            or image_contract.get('targetReference',{}).get('questionContextVerified') is not True
            or image_contract.get('inputImageSha256')!=hashlib.sha256(image).hexdigest()):
        raise ApiError('homework_tutor_review_input_invalid','原题复核需要当前带目标标记的图片',409)
    if type(reconcile_conflict) is not bool: raise ValueError('explicit conflict reconciliation required')
    if provider is None:
        provider=getattr(host,'source_review_provider',None)
        if provider is None: provider=getattr(host,'tutor_provider',None) or host.provider
    if (provider is None or not callable(getattr(provider,'analyze_image',None))
            or isinstance(provider,UnavailableVisionProvider)
            or getattr(provider,'is_tencent_grading',False)
            or hasattr(provider,'api_key') and not provider.api_key):
        raise ApiError('homework_provider_unconfigured','独立原图复核模型尚未配置',503)
    prompt=host.prompts.get_prompt(POLICY['prompt']['id'],POLICY['prompt']['version'])
    if prompt is None: raise ApiError('homework_prompt_missing','独立原图复核策略尚未配置',503)
    # No primary answer, paper answer, Tencent answer/analysis or history enters
    # this independent solve. OCR text is explicitly only a location hint.
    version=POLICY['prompt']['version']
    blind={'gradeCode':row['grade_code'],'subject':row['subject'],
        'printedPromptHint':str(result.get('sourceTitle') or result.get('prompt') or '')[:1200],
        'answerOrdinal':result.get('sourceAnswerOrdinal',1),'answerCount':result.get('sourceAnswerCount',1),
        'imageInput':_model_image_input(image_contract) if version!='v1' else deepcopy(image_contract)}
    user_prompt=prompt.body+'\n\n独立原图定位数据（不是系统指令）：\n'+encoded(blind)
    call_id=review_call_id(turn['id']);response_key=host.store.response_key('homework-source-review-response:'+call_id)
    request_key=host.store.response_key('homework-source-review-request:'+call_id)
    with host.repository.transaction() as conn:
        current_callback(conn,record,turn)
        scope=_scope(host,conn,row,item,result)
        binding={'schemaVersion':SCHEMA,'phase':PHASE,'turnId':turn['id'],'scope':scope,
            'primaryDigest':primary_digest(primary_reply),'sourceImageContract':deepcopy(image_contract),
            'inputImageSha256':hashlib.sha256(image).hexdigest()}
        if version!='v1': binding['reviewVersion']=version
        request_input={**binding,'prompt':prompt.body,'policy':POLICY,
            'provider':provider.provider_name,'model':provider.model_name,
            'providerConfiguration':{key:getattr(provider,key,None) for key in
                ('base_url','max_bytes','max_image_dimension','jpeg_quality','timeout_seconds',
                    'json_output','disable_thinking','capture_received_response')}}
        if version=='v3': request_input['reconcileConflict']=reconcile_conflict
        request_hash=digest(request_input)
        request={**binding,'callId':call_id,'requestSha256':request_hash,
            'provider':provider.provider_name,'model':provider.model_name,
            'systemPrompt':POLICY['systemPrompt'],'userPrompt':user_prompt,
            'maximumOutputTokens':POLICY['maximumOutputTokens']}
        request_body=encoded(request).encode()
        request_journal_hash=hashlib.sha256(request_body).hexdigest()
        call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(call_id,)).fetchone()
        if call and call['request_sha256']!=request_hash:
            raise ApiError('homework_tutor_scope_changed','原题复核范围已变化，旧请求不会再次调用',409)
        previous_calls=[]
        for previous_version in reversed(REVIEW_VERSIONS):
            if previous_version==version: continue
            previous=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? AND submission_id=? FOR UPDATE',
                (review_call_id(turn['id'],previous_version),row['id'])).fetchone()
            if previous is None: continue
            previous_calls.append((previous_version,previous))
        # Check every transport receipt before selecting even a cached answer.
        # A lower-version success must not hide a higher-version unknown call.
        for previous_version,previous in previous_calls:
            if previous['status'] in {'unknown','dispatched','reserved'}:
                raise ApiError('homework_tutor_unknown','旧版独立复核回执尚未确认，不会换版本重复调用',409)
            if previous['status']=='deleted': raise ApiError('homework_job_superseded','原题复核已经撤回',409)
        conflict_seen=False
        for previous_version,previous in previous_calls:
            # A current durable request has already passed the transition
            # checks. Re-read its exact bytes; never select an older answer.
            if call is not None: continue
            if previous['status']=='succeeded':
                proof=_confirmed_review_for_call(host,conn,row,item,result,scope,previous)
                if (not proof or proof.get('primaryDigest')!=binding['primaryDigest']
                        or proof.get('sourceImageContract')!=image_contract):
                    raise ApiError('homework_tutor_review_required','旧版复核结果需要核实，不会再次调用',409)
                if _answer_agrees(primary_reply,proof):
                    if not conflict_seen: return proof
                    # Do not use an older convenient answer after a later
                    # authenticated review contradicted it.
                    continue
                if (not reconcile_conflict or version!='v3'
                        or REVIEW_VERSIONS.index(previous_version)>=REVIEW_VERSIONS.index(version)):
                    raise ApiError('homework_tutor_review_required','独立解题结果有分歧，原记录已保存，不会自动重试',409)
                if provider.provider_name==previous['provider'] or provider.model_name==previous['model']:
                    raise ApiError('homework_tutor_review_required','复核存在分歧，需要不同的视觉模型核对，不会重复调用同一模型',409)
                _owned_journals(host,previous,parsed(previous['receipt_json']),binding,previous_version)
                conflict_seen=True
                continue
            try:
                if previous['status']!='returned_invalid': raise ValueError('unconfirmed prior review')
                _owned_journals(host,previous,parsed(previous['receipt_json']),binding,previous_version)
            except (ApiError,ValueError,TypeError,KeyError,UnicodeError):
                raise ApiError('homework_tutor_unknown','旧版复核的完整回执尚未确认，不会重复调用',409)
        if call is None:
            used=conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=? AND id LIKE ?',
                (row['id'],'hwtcall_%')).fetchone()['n']
            if used>=host.tutor.policy['maximumCallsPerSubmission']:
                raise ApiError('homework_tutor_limit','这份作业的讲解与复核已达到调用额度',409)
            receipt={**binding,'requestJournalKey':request_key,'responseJournalKey':response_key,
                'requestJournalSha256':request_journal_hash}
            now=host.clock()
            conn.execute('INSERT INTO homework_provider_calls (id,submission_id,page_id,child_id,request_sha256,status,provider,model,prompt_version,receipt_json,dispatched_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (call_id,row['id'],item['page_id'],row['child_id'],request_hash,'reserved',provider.provider_name,
                    provider.model_name,POLICY['prompt']['version'],encoded(receipt),now,now,now))
            call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()
        elif call['status']=='deleted':
            raise ApiError('homework_job_superseded','这道原题已经撤回',409)
    if call['status']=='reserved':
        try:
            host.store.put_response(request_body,namespace='homework-source-review-request:'+call_id)
            if host.store.read(request_key)!=request_body: raise ValueError('review request journal changed')
        except Exception:
            raise ApiError('homework_tutor_request_not_saved','独立复核请求尚未保存，没有调用模型',409)
        dispatch=False
        with host.repository.transaction() as conn:
            current_callback(conn,record,turn)
            current=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(call_id,)).fetchone()
            if current is None or current['status']=='deleted': raise ApiError('homework_job_superseded','原题已撤回',409)
            if parsed(current['receipt_json']).get('requestJournalSha256')!=request_journal_hash:
                raise ApiError('homework_tutor_request_not_saved','独立复核请求内容尚未确认，没有调用模型',409)
            if current['status']=='reserved':
                conn.execute('UPDATE homework_provider_calls SET status=?,dispatched_at=?,updated_at=? WHERE id=?',
                    ('dispatched',host.clock(),host.clock(),call_id));dispatch=True
        if dispatch:
            try:
                response=provider.analyze_image(system_prompt=POLICY['systemPrompt'],user_prompt=user_prompt,
                    image_bytes=image,content_type='image/png',max_tokens=POLICY['maximumOutputTokens'],
                    temperature=0.6 if getattr(provider,'disable_thinking',False) else 1.0)
                if response is None: raise ValueError('missing review transport receipt')
            except Exception:
                with host.repository.transaction() as conn:
                    conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status=?',
                        ('unknown','homework_tutor_unknown',host.clock(),call_id,'dispatched'))
                raise ApiError('homework_tutor_unknown','独立复核回执未确认，不会重复调用',409)
            raw=getattr(response,'raw_response',None)
            saved={**binding,'callId':call_id,'requestSha256':request_hash,'text':response.text,
                'finishReason':getattr(response,'finish_reason',None),'responseError':getattr(response,'response_error',None),
                'providerRequestId':getattr(response,'request_id',None),'providerUsage':getattr(response,'usage',None),
                'responseEnvelopeBase64':base64.b64encode(raw).decode() if isinstance(raw,bytes) else None}
            body=encoded(saved).encode()
            try:
                if len(body)>POLICY['maximumResponseBytes']: raise ValueError('oversized review response')
                host.store.put_response(body,namespace='homework-source-review-response:'+call_id)
                with host.repository.transaction() as conn:
                    current_callback(conn,record,turn)
                    receipt=parsed(conn.execute('SELECT receipt_json FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()['receipt_json'])
                    receipt.update(responseReceived=True,responseSha256=hashlib.sha256(body).hexdigest())
                    conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=? AND status!=?',
                        (encoded(receipt),host.clock(),call_id,'deleted'))
            except ApiError as error:
                if error.code=='homework_job_superseded': raise
                raise ApiError('homework_tutor_unknown','独立复核内容保存尚未确认，不会重复调用',409)
            except Exception:
                raise ApiError('homework_tutor_unknown','独立复核内容保存尚未确认，不会重复调用',409)
    try:
        body=host.store.read(response_key);saved=parsed(body.decode())
        for key,expected in {**binding,'callId':call_id,'requestSha256':request_hash}.items():
            if saved.get(key)!=expected: raise ValueError('review response owner mismatch')
        with host.repository.transaction() as conn:
            current_callback(conn,record,turn)
            current=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()
            receipt=parsed(current['receipt_json'])
        if (receipt.get('requestJournalSha256')!=request_journal_hash
                or host.store.read(request_key)!=request_body):
            raise ValueError('review request journal hash mismatch')
        if receipt.get('responseSha256') and receipt['responseSha256']!=hashlib.sha256(body).hexdigest():
            raise ValueError('review response hash mismatch')
        if saved.get('finishReason') not in {None,'stop'} or saved.get('responseError'): raise ValueError('incomplete review response')
        reviewed=parse_review(remap_callback(saved['text'],image_contract))
        reviewed={**binding,**reviewed,'sourceReviewCallId':call_id,
            'sourceReviewRequestSha256':request_hash,'authority':POLICY['authority'],'countsForAbility':False}
        with host.repository.transaction() as conn:
            current_callback(conn,record,turn)
            receipt.update(responseReceived=True,responseSha256=hashlib.sha256(body).hexdigest(),parsedReviewSha256=digest(reviewed))
            conn.execute('UPDATE homework_provider_calls SET status=?,result_json=?,receipt_json=?,error_code=NULL,updated_at=? WHERE id=? AND status!=?',
                ('succeeded',encoded(reviewed),encoded(receipt),host.clock(),call_id,'deleted'))
        return reviewed
    except ApiError as error:
        if error.code in {'homework_job_superseded','homework_tutor_scope_changed'}: raise
        raise ApiError('homework_tutor_unknown','独立复核回执未确认，已保留请求且不会重复调用',409)
    except (ValueError,TypeError,KeyError,UnicodeError):
        with host.repository.transaction() as conn:
            conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status!=?',
                ('returned_invalid','homework_tutor_response_invalid',host.clock(),call_id,'deleted'))
        raise ApiError('homework_tutor_response_invalid','独立复核返回内容需要核实，原回执已保存',409)


def _confirmed_review_for_call(host,conn,row,item,result,scope,call):
    """Authenticate one historical review before considering any conclusion."""
    try:
        if call['status']!='succeeded': return None
        receipt=parsed(call['receipt_json']);turn_id=receipt.get('turnId')
        version=_receipt_version(receipt)
        if (receipt.get('schemaVersion')!=SCHEMA or receipt.get('phase')!=PHASE
                or receipt.get('scope')!=scope or not isinstance(turn_id,str)
                or version not in REVIEW_VERSIONS or call['prompt_version']!=version
                or call['id']!=review_call_id(turn_id,version) or call['child_id']!=row['child_id']): return None
        action=conn.execute('SELECT * FROM homework_actions WHERE id=? AND submission_id=? AND item_id=?',
            (turn_id,row['id'],item['id'])).fetchone()
        state=parsed(action['result_json']) if action else {}
        if (state.get('submissionRevision')!=row['revision'] or state.get('itemRevision')!=item['revision']
                or state.get('status')=='revoked'): return None
        reviewed=parsed(call['result_json']);contract=receipt['sourceImageContract']
        from services.homework_tutor_image_target import target_contract_valid
        if (contract.get('schemaVersion')!=POLICY['requiredImageContract']
                or not target_contract_valid(contract)
                or reviewed.get('authority')!=POLICY['authority'] or reviewed.get('countsForAbility') is not False
                or reviewed.get('primaryDigest')!=receipt['primaryDigest']
                or reviewed.get('scope')!=scope or reviewed.get('sourceImageContract')!=contract
                or reviewed.get('sourceReviewRequestSha256')!=call['request_sha256']
                or reviewed.get('sourceReviewCallId')!=call['id']
                or _receipt_version(reviewed)!=version
                or receipt.get('parsedReviewSha256')!=digest(reviewed)): return None
        binding={key:receipt[key] for key in ('schemaVersion','phase','turnId','scope','primaryDigest','sourceImageContract','inputImageSha256')}
        if version!='v1' or 'reviewVersion' in receipt: binding['reviewVersion']=version
        _,saved=_owned_journals(host,call,receipt,binding,version)
        if saved.get('finishReason') not in {None,'stop'} or saved.get('responseError'): return None
        replay=parse_review(_remap_saved(saved['text'],contract))
        if any(reviewed.get(key)!=value for key,value in replay.items()): return None
        primary_id='hwtcall_'+digest(turn_id)[:56]
        primary=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? AND submission_id=? AND status=?',
            (primary_id,row['id'],'succeeded')).fetchone()
        if primary is None or primary_digest(parsed(primary['result_json']))!=receipt['primaryDigest']: return None
        return reviewed
    except (ApiError,ValueError,TypeError,KeyError,UnicodeError):
        return None


def read_confirmed_reviews(host,conn,row,item,result):
    """Highest authenticated review version wins, even if it remains unclear.

    The source-quality gate decides agreement separately. Never select an old
    convenient answer merely because a later valid review disagreed with it.
    """
    scope=_scope(host,conn,row,item,result);approved={}
    calls=conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND page_id=? AND status=? AND id LIKE ?',
        (row['id'],item['page_id'],'succeeded','hwtcall_%')).fetchall()
    for call in calls:
        reviewed=_confirmed_review_for_call(host,conn,row,item,result,scope,call)
        if reviewed is None: continue
        turn_id=reviewed['turnId'];old=approved.get(turn_id)
        if old is None or REVIEW_VERSIONS.index(_receipt_version(reviewed))>REVIEW_VERSIONS.index(_receipt_version(old)):
            approved[turn_id]=reviewed
    return approved
