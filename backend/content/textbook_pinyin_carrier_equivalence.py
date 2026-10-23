"""Exact orthographic evidence, never audio perception.

Pure validation; no I/O, network, score mutation or human approval.
Full original ASR and one same-WAV recheck remain required and unchanged.
"""
from copy import deepcopy
from functools import lru_cache
import unicodedata
from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import policy_for_plan, pronunciation_symbols
from content.textbook_audio_recheck import raw_entries, validate_asr_recheck
from content.textbook_pinyin_operator_review import validate_operator_authorization

SCHEMA = 'mira.textbook.pinyin-carrier-orthographic-evidence.v1'
METHOD = 'exact-context-and-registered-carrier-both-asr-attempts'
LIMIT = 'Exact written representation only; not human listening, phonetic accuracy or perceptual tone verification.'


def reject(message):
    from core.errors import ApiError
    raise ApiError('textbook_pinyin_carrier_equivalence_invalid', message, 409)


def separator(char):
    return char.isspace() or unicodedata.category(char).startswith('P')


def checked_text(value):
    if (not isinstance(value, str) or not value or len(value) > 8000
            or any(unicodedata.category(c).startswith('C') and c not in '\t\n\r' for c in value)):
        reject('Invalid text/control characters')
    return value


def exact_representation(source, transcript, policy):
    """Each target is one contiguous literal or exact carrier; CJK stays exact.

    Only whitespace and Unicode punctuation are ignored in contextual prose and
    between complete targets. No tone removal, Unicode normalization, casefold,
    numbers/word substitution, phonetic dictionary, substring search or score.
    Splitting a literal with punctuation and merging adjacent Latin runs fail.
    Reject an ambiguous alignment instead of selecting a convenient one.
    """
    checked_text(source); checked_text(transcript)
    if policy.get('words') != {}:
        reject('Chinese overrides are outside this narrowly defined evidence')
    if source in policy.get('exactTextSsml', {}):
        reject('An exact alias request is not per-token phoneme/carrier evidence')
    tokens = pronunciation_symbols(source, policy_version=policy['policyVersion'])
    if not tokens or any(t['symbol'] not in policy['symbols'] for t in tokens):
        reject('An exact registered Latin target is required')
    units=[]; previous=0
    for token in tokens:
        units.append(('context', ''.join(c for c in source[previous:token['index']] if not separator(c))))
        units.append(('target',token));previous=token['index']+len(token['symbol'])
    units.append(('context',''.join(c for c in source[previous:] if not separator(c))))
    ranges=policy['textHandling']['latinRunRanges']
    def latin(c): return any(a <= ord(c) <= b for a,b in ranges)
    def skip(pos):
        while pos<len(transcript) and separator(transcript[pos]): pos+=1
        return pos
    @lru_cache(None)
    def walk(index,pos):
        if index==len(units): return (1,()) if skip(pos)==len(transcript) else (0,())
        kind,value=units[index];pos=skip(pos)
        if kind=='context':
            for expected in value:
                pos=skip(pos)
                if pos==len(transcript) or transcript[pos]!=expected:return 0,()
                pos+=1
            return walk(index+1,pos)
        paths=0;chosen=()
        for form,label in ((value['symbol'],'literal'),(value['carrier'],'carrier')):
            if not transcript.startswith(form,pos):continue
            end=pos+len(form)
            if label=='literal' and ((pos and latin(transcript[pos-1])) or (end<len(transcript) and latin(transcript[end]))):continue
            count,rest=walk(index+1,end)
            if count:
                paths+=count
                chosen=({'sourceIndex':value['index'],'symbol':value['symbol'],'ph':value['ph'],
                         'carrier':value['carrier'],'representation':label,
                         'transcriptStart':pos,'transcriptEnd':end},)+rest
            if paths>1:return 2,()
        return paths,chosen
    count,matches=walk(0,0)
    if count!=1:reject('No unique full-sentence exact context/target match')
    return {'orthographicEquivalent':True,'contextCharactersIdentical':True,
            'normalization':'punctuation-and-whitespace-between-whole-targets-only',
            'targets':[dict(x) for x in matches]}


def context(*,plan,classroom,audit,recheck,authorization,expected_source_sha256,now_ms,expected_source_classroom_id=None):
    # These existing validators preserve/recompute every raw score and every
    # recheck's bytes/body/request, but do not accept still-failed comparisons.
    validate_operator_authorization(authorization,binding=plan['binding'],recorded_at=now_ms)
    scenes,actions,raw=raw_entries(plan=plan,classroom=classroom,audit=audit,
                                  expected_source_sha256=expected_source_sha256)
    checked=validate_asr_recheck(recheck,plan=plan,classroom=classroom,audit=audit,
                               expected_source_sha256=expected_source_sha256,now_ms=now_ms,
                               expected_source_classroom_id=expected_source_classroom_id)
    return actions,raw,checked


def evidence_for(key,*,plan,actions,raw,checked):
    old,new,action=raw.get(key),checked.get(key),actions.get(key)
    if (old is None or new is None or action is None or old['comparison']['passed'] is not False
            or new['comparison']['passed'] is not False):
        reject('Only unchanged failures from both complete audits are in scope')
    request_plan=new.get('requestPlan',plan);policy=policy_for_plan(request_plan)
    first=exact_representation(action['text'].strip(),old['asr']['transcript'],policy)
    second=exact_representation(action['text'].strip(),new['asr']['transcript'],policy)
    return {**{k:old[k] for k in ('sceneId','actionId','textSha256','ttsRequestId','audioSha256')},
        'pcmSha256':new['ttsReceipt']['pcmSha256'],'requestPlanSha256':digest(request_plan),
        'policySha256':digest(policy),'ttsReceiptSha256':digest(new['ttsReceipt']),
        'auditSegmentSha256':digest(old),'originalAsrReceiptSha256':digest(old['asr']),
        'recheckEntrySha256':digest(new),'recheckAsrReceiptSha256':digest(new['asr']),
        'originalLiteralPassed':False,'recheckLiteralPassed':False,
        'originalSimilarityBps':old['similarityBps'],'recheckSimilarityBps':new['comparison']['similarityBps'],
        'originalRepresentation':first,'recheckRepresentation':second}


def build_evidence(*,selections,plan,classroom,audit,recheck,authorization,expected_source_sha256,now_ms,expected_source_classroom_id=None):
    actions,raw,checked=context(plan=plan,classroom=classroom,audit=audit,recheck=recheck,
        authorization=authorization,expected_source_sha256=expected_source_sha256,now_ms=now_ms,
        expected_source_classroom_id=expected_source_classroom_id)
    if not isinstance(selections,list) or not selections:reject('No explicit selected set')
    entries=[];seen=set()
    for item in selections:
        if not isinstance(item,dict) or set(item)!={'sceneId','actionId'}:reject('Unknown selection fields')
        key=item['sceneId'],item['actionId']
        if key in seen:reject('Duplicate selected identity')
        seen.add(key);entries.append(evidence_for(key,plan=plan,actions=actions,raw=raw,checked=checked))
    value={'schemaVersion':SCHEMA,'method':METHOD,'previewKey':plan['previewKey'],
        'sourceClassroomId':classroom['id'],'sourceSha256':expected_source_sha256,
        'coreSha256':plan['coreSha256'],'planSha256':digest(plan),'auditSha256':digest(audit),
        'recheckSha256':digest(recheck),'authorizationSha256':digest(authorization),'recordedAt':now_ms,
        'minimumSimilarityBpsUnchanged':8500,'humanListeningVerified':False,
        'phoneticAccuracyVerified':False,'perceptualToneVerified':False,'evidenceLimit':LIMIT,
        'segments':entries}
    value['sha256']=digest(value);return value


def validate_evidence(value,**context_args):
    if (not isinstance(value,dict) or not isinstance(value.get('segments'),list)
            or any(not isinstance(e,dict) for e in value['segments'])):reject('Invalid manifest')
    now=context_args.pop('now_ms')
    if type(value.get('recordedAt')) is not int or not 0<value['recordedAt']<=now:reject('Invalid time')
    # Recompute the entire evidence from authenticated inputs, not caller-supplied
    # match flags, target lists, substitutions, scores or transcript fragments.
    selections=[{k:e.get(k) for k in ('sceneId','actionId')} for e in value['segments']]
    expected=build_evidence(selections=selections,now_ms=value['recordedAt'],**context_args)
    if value!=expected:reject('Evidence mismatch or extra fields')
    return {(e['sceneId'],e['actionId']):deepcopy(e) for e in value['segments']}
