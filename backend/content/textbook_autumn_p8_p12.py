"""Recompute supported Autumn activity operations; never infer oral mastery.

These inputs are client reported, not proof of a child's identity or unaided skill.
"""
import copy
import math
from core.errors import ApiError

VALIDATORS = {'scene-p8': 'autumn-geese.v1', 'scene-p9': 'autumn-yitone.v1',
              'scene-p10': 'autumn-strokes-ren-da.v1', 'scene-p11': 'autumn-practice.v1',
              'scene-p12': 'autumn-observation.v1'}
_MAX = 128
_SCATTER = [(175,150),(475,330),(775,160),(300,425),(640,455),(840,355),(420,145)]
_SPECS = {'ren': [((.58,.12),(.20,.82)), ((.45,.38),(.82,.84))],
          'da': [((.28,.37),(.72,.37)), ((.53,.12),(.20,.84)), ((.50,.37),(.82,.84))]}
_COLORS = {'weather':['#B5C8D8','#6E9DB5','#E8DCC8'], 'plant':['#C96A35','#B44A42','#658052'], 'animal':['#8B6B4E','#4F6D5A','#A0583B']}


def _fail(message='互动操作无效，请继续当前练习'):
    raise ApiError('textbook_interaction_operation_invalid', message, 409)


def _record(s, v):
    if len(s['attempts']) >= _MAX: _fail('本页练习次数已达到上限')
    s['attempts'].append(v)


def _number(value, lo, hi):
    try:
        return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi
    except (OverflowError, TypeError):
        return False


def _common(s, op):
    if op == {'name':'start'} and s['phase'] == 'ready': s['phase'] = 'playing'; return True
    if s['phase'] == 'ready': _fail('请先开始当前练习')
    if op == {'name':'hint'}:
        if s['helpCount'] >= _MAX: _fail('本页帮助次数已达到上限')
        s['helpCount'] += 1; return True
    return False


def _draft():
    return {'selectedObject':None,'color':None,'quantity':0,'direction':'right','action':'still','positions':[]}


def initial_page(validator):
    s = {'phase':'ready','completed':False,'attempts':[],'helpCount':0}
    if validator == VALIDATORS['scene-p8']:
        return {**s,'order':['人','一'],'level':1,'flightAngle':-90,'leader':0,'positions':[list(p) for p in _SCATTER], 'previousLegs':[]}
    if validator == VALIDATORS['scene-p9']:
        return {**s,'context':0,'tone':None,'completedContexts':[],'helped':[]}
    if validator == VALIDATORS['scene-p10']:
        return {**s,'character':'ren','strokes':[],'versions':{'ren':[], 'da':[]},'completedChars':[]}
    if validator == VALIDATORS['scene-p11']:
        return {**s,'mode':0,'saved':[],'supports':[{'picture':True,'text':True},{'picture':False,'text':False},{'picture':False,'text':False}], 'examples':[], 'evidenceBoundary':'child_self_report_no_oral_assessment'}
    if validator == VALIDATORS['scene-p12']:
        return {**s,'page':'a','drafts':{'a':_draft(),'b':_draft()},'versions':{'a':None,'b':None},'history':[]}
    _fail('互动验证器不可用')


def _formation(s):
    p=s['positions']; leader=p[s['leader']]; angle=s['flightAngle']
    if any(not (40 <= x <= 984 and 45 <= y <= 531) for x,y in p): return False
    if any(math.dist(p[i],p[j]) < 90 for i in range(7) for j in range(i+1,7)): return False
    if s['order'][s['level']-1]=='一':
        ordered=sorted(range(7),key=lambda i:p[i][0]); avg=sum(x[1] for x in p)/7
        if any(abs(v[1]-avg)>27 for v in p) or p[ordered[-1]][0]-p[ordered[0]][0]<550: return False
        gaps=[p[ordered[i+1]][0]-p[ordered[i]][0] for i in range(6)]
        return all(90<=g<=200 for g in gaps) and max(gaps)<=min(gaps)*1.65 and ((angle==180 and s['leader']==ordered[0]) or (angle==0 and s['leader']==ordered[-1]))
    if angle != -90: return False
    left=sorted([x for i,x in enumerate(p) if i!=s['leader'] and x[0]<leader[0]-35],key=lambda x:x[1])
    right=sorted([x for i,x in enumerate(p) if i!=s['leader'] and x[0]>leader[0]+35],key=lambda x:x[1])
    if len(left)!=3 or len(right)!=3: return False
    for arm,sign in ((left,-1),(right,1)):
        prev=leader; lengths=[]
        for g in arm:
            dx=sign*(g[0]-prev[0]);dy=g[1]-prev[1];dist=math.hypot(dx,dy)
            if dx<50 or dy<48 or not .45<=dy/dx<=2.1 or dist>235: return False
            lengths.append(dist);prev=g
        vx=arm[-1][0]-leader[0];vy=arm[-1][1]-leader[1];length=math.hypot(vx,vy)
        if not length or any(abs(vx*(g[1]-leader[1])-vy*(g[0]-leader[0]))/length>35 for g in arm):return False
        if max(lengths)>min(lengths)*1.65:return False
    return abs((leader[0]-left[-1][0])-(right[-1][0]-leader[0]))<=95 and abs(left[-1][1]-right[-1][1])<=80


def _geese(s, op):
    if _common(s,op):return
    n=op.get('name')
    if n=='move' and set(op)=={'name','bird','x','y'} and type(op['bird']) is int and 0<=op['bird']<7 and _number(op['x'],40,984) and _number(op['y'],45,531):
        s['positions'][op['bird']]=[op['x'],op['y']];s['phase']='playing'
    elif n=='leader' and set(op)=={'name','bird'} and type(op['bird']) is int and 0<=op['bird']<7: s['leader']=op['bird'];s['phase']='playing'
    elif op=={'name':'rotate'}: s['flightAngle']={-90:0,0:90,90:180,180:-90}[s['flightAngle']];s['phase']='playing'
    elif op=={'name':'reverseOrder'} and not s['previousLegs']: s['order'].reverse()
    elif op=={'name':'reset'}: s['positions']=[list(p) for p in _SCATTER];s['phase']='playing'
    elif op=={'name':'submit'}:
        passed=_formation(s);_record(s,{'formation':s['order'][s['level']-1],'passed':passed,'helpCount':s['helpCount']})
        if passed:
            s['previousLegs']=s['previousLegs'][:s['level']-1]
            s['previousLegs'].append({'formation':s['order'][s['level']-1],'positions':copy.deepcopy(s['positions']),'leader':s['leader']})
            if s['level']==1:s['level']=2;s['phase']='playing'
            else:s.update(completed=True,phase='complete')
        else:s['phase']='feedback'
    else:_fail()
    if n in ('move','leader','rotate','reset'):s['completed']=False


def _tone(s,op):
    if _common(s,op):return
    n=op.get('name')
    if n=='context' and set(op)=={'name','index'} and type(op['index']) is int and 0<=op['index']<4:
        s.update(context=op['index'],tone=None,phase='playing')
    elif n=='choose' and set(op)=={'name','tone'} and type(op['tone']) is int and op['tone'] in (1,2,4) and not s['completed']:
        s['tone']=op['tone'];s['phase']='playing'
    elif op=={'name':'submit'} and s['tone'] is not None and s['context'] not in s['completedContexts']:
        passed=s['tone']==(2,4,2,1)[s['context']];_record(s,{'context':s['context'],'tone':s['tone'],'passed':passed,'helpCount':s['helpCount']})
        if passed:s['completedContexts'].append(s['context'])
        s['completed']=len(s['completedContexts'])==4;s['phase']='complete' if s['completed'] else 'feedback'
    elif op=={'name':'next'}:
        todo=next((i for i in range(4) if i not in s['completedContexts']),None)
        if todo is not None:s.update(context=todo,tone=None,phase='playing')
    elif op=={'name':'reset'}:
        s['completedContexts']=[i for i in s['completedContexts'] if i!=s['context']];s.update(tone=None,completed=False,phase='playing')
    else:_fail()


def _stroke_valid(trace,spec):
    if len(trace)<8:return False
    a,b=trace[0],trace[-1];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
    if length<.12:return False
    turns=0
    for p,q,r in zip(trace,trace[1:],trace[2:]):
        u=(q[0]-p[0],q[1]-p[1]);v=(r[0]-q[0],r[1]-q[1]);m=math.hypot(*u)*math.hypot(*v)
        if m:turns+=math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/m)))
    ex=spec[1][0]-spec[0][0];ey=spec[1][1]-spec[0][1];direction=(dx*ex+dy*ey)/(length*math.hypot(ex,ey))
    if turns/max(1,len(trace)-2)>1.1 or direction<.2 or math.dist(a,spec[0])>.18 or math.dist(b,spec[1])>.18:return False
    return all(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length<=.10 for p in trace)


def _da_structure(strokes):
    h,l,r=strokes; a,b=h[0],h[-1]; lf,rf=l[-1],r[-1]; width=b[0]-a[0];foot=rf[0]-lf[0];y=(a[1]+b[1])/2
    if any(sum(math.dist(x,z) for x,z in zip(t,t[1:]))>math.dist(t[0],t[-1])*2.1 for t in strokes):return False
    if width<=0 or abs(b[1]-a[1])>.08 or foot<.35 or width>foot*.82 or width<foot*.42 or l[0][1]>y-.10 or lf[1]<y+.28 or rf[1]<y+.28 or lf[0]>=rf[0]:return False
    junction=None
    for h0,h1 in zip(h,h[1:]):
        rx,ry=h1[0]-h0[0],h1[1]-h0[1]
        for p0,p1 in zip(l,l[1:]):
            sx,sy=p1[0]-p0[0],p1[1]-p0[1];den=rx*sy-ry*sx
            if abs(den)<1e-8:continue
            qx,qy=p0[0]-h0[0],p0[1]-h0[1];t=(qx*sy-qy*sx)/den;u=(qx*ry-qy*rx)/den
            if 0<=t<=1 and 0<=u<=1:junction=(h0[0]+t*rx,h0[1]+t*ry);break
        if junction:break
    return bool(junction and .18<=(junction[0]-a[0])/width<=.82 and math.dist(r[0],junction)<=.085)


def _writing(s,op):
    if _common(s,op):return
    n=op.get('name')
    if n=='character' and set(op)=={'name','character'} and isinstance(op['character'],str) and op['character'] in _SPECS:
        s['versions'][s['character']]=copy.deepcopy(s['strokes']);s['character']=op['character'];s['strokes']=copy.deepcopy(s['versions'][s['character']]);s['phase']='playing'
    elif op=={'name':'undo'}:
        if s['strokes']:
            s['strokes'].pop();s['completedChars']=[v for v in s['completedChars'] if v!=s['character']];s['completed']=False
        s['phase']='playing'
    elif op=={'name':'retry'}:
        s['strokes']=[];s['completedChars']=[v for v in s['completedChars'] if v!=s['character']];s['completed']=False;s['phase']='playing'
    elif n=='stroke' and set(op)=={'name','character','points'} and op['character']==s['character'] and isinstance(op['points'],list) and 2<=len(op['points'])<=256:
        if len(s['strokes'])>=len(_SPECS[s['character']]):_fail('请先撤回或重试')
        points=[]
        for p in op['points']:
            if not isinstance(p,dict) or set(p)!={'x','y'} or not _number(p['x'],0,1) or not _number(p['y'],0,1):_fail('笔画坐标无效')
            points.append((p['x'],p['y']))
        s['strokes'].append(points);spec=_SPECS[s['character']]
        if len(s['strokes'])==len(spec):
            passed=all(_stroke_valid(t,e) for t,e in zip(s['strokes'],spec)) and (s['character']!='da' or _da_structure(s['strokes']))
            _record(s,{'character':s['character'],'passed':passed,'helpCount':s['helpCount']})
            if passed:
                if s['character'] not in s['completedChars']:s['completedChars'].append(s['character'])
                if len(s['completedChars'])==2:s.update(completed=True,phase='complete')
                elif s['character']=='ren':
                    s['versions']['ren']=copy.deepcopy(s['strokes']);s.update(character='da',strokes=copy.deepcopy(s['versions']['da']),phase='playing')
                else:s['phase']='feedback'
            else:s['phase']='feedback'
    else:_fail()
    s['versions'][s['character']]=copy.deepcopy(s['strokes'])


def _practice(s,op):
    if _common(s,op):return
    n=op.get('name');m=s['mode']
    if n=='mode' and set(op)=={'name','index'} and type(op['index']) is int and 0<=op['index']<3:s['mode']=op['index'];s['phase']='playing'
    elif n=='example' and set(op)=={'name','index'} and type(op['index']) is int and 0<=op['index']<3:
        if len(s['examples'])>=_MAX:_fail()
        s['examples'].append({'mode':m,'index':op['index']})
    elif op=={'name':'hide'}:s['supports'][m]={'picture':False,'text':False}
    elif op=={'name':'restore'}:s['supports'][m]={'picture':True,'text':True};s['helpCount']+=1
    elif op=={'name':'restoreText'}:s['supports'][m]['text']=True;s['helpCount']+=1
    elif op=={'name':'save'} and m not in s['saved']:
        _record(s,{'mode':m,'supports':copy.deepcopy(s['supports'][m]),'basis':'child_self_report_no_oral_assessment'});s['saved'].append(m);s['completed']=len(s['saved'])==3;s['phase']='complete' if s['completed'] else 'feedback'
    elif op=={'name':'next'}:
        todo=next((i for i in range(3) if i not in s['saved']),None)
        if todo is not None:s['mode']=todo;s['phase']='playing'
    elif op=={'name':'retry'}:
        s['saved']=[v for v in s['saved'] if v!=m];s['completed']=False;s['phase']='playing'
    else:_fail()
    if s['helpCount']>_MAX:_fail()


def _positions(d):
    while len(d['positions'])<d['quantity']:
        i=len(d['positions']);d['positions'].append({'x':18+(i%3)*30,'y':28+(i//3)*42})
    del d['positions'][d['quantity']:]


def _observation(s,op):
    if _common(s,op):return
    n=op.get('name');d=s['drafts'][s['page']];before=copy.deepcopy(d)
    if n=='page' and set(op)=={'name','page'} and op['page'] in ('a','b'):s['page']=op['page'];s['phase']='playing';return
    if n=='object' and set(op)=={'name','object'} and isinstance(op['object'],str) and op['object'] in _COLORS:
        d.update(selectedObject=op['object'],color=_COLORS[op['object']][0],quantity=max(1,d['quantity']),action='still');_positions(d)
    elif n=='quantity' and set(op)=={'name','delta'} and type(op['delta']) is int and op['delta'] in (-1,1) and d['selectedObject']:
        d['quantity']=max(0,min(6,d['quantity']+op['delta']));_positions(d)
    elif n=='color' and set(op)=={'name','color'} and d['selectedObject'] and op['color'] in _COLORS[d['selectedObject']]:d['color']=op['color']
    elif n=='direction' and set(op)=={'name','direction'} and d['selectedObject'] and op['direction'] in ('left','up','right','down'):d['direction']=op['direction']
    elif n=='action' and set(op)=={'name','action'} and d['selectedObject'] and op['action'] in ('still','moving'):d['action']=op['action']
    elif n=='move' and set(op)=={'name','index','x','y'} and type(op['index']) is int and 0<=op['index']<len(d['positions']) and _number(op['x'],0,100) and _number(op['y'],0,100):d['positions'][op['index']]={'x':op['x'],'y':op['y']}
    elif op=={'name':'reset'}:s['drafts'][s['page']]=_draft()
    elif op=={'name':'undo'}:
        index=next((i for i in range(len(s['history'])-1,-1,-1) if s['history'][i]['page']==s['page']),None)
        if index is None:return
        s['drafts'][s['page']]=s['history'].pop(index)['before'];s['completed']=False;s['phase']='playing';return
    elif op=={'name':'save'}:
        valid=bool(d['selectedObject'] and d['quantity']>0 and len(d['positions'])==d['quantity']);_record(s,{'page':s['page'],'saved':valid,'helpCount':s['helpCount']})
        if valid:
            key=s['page'];s['versions'][key]=copy.deepcopy(d)
            if key=='a' and s['versions']['b'] is None:s['page']='b'
            current=s['versions'][s['page']]
            s['completed']=bool(s['versions']['a'] and s['versions']['b'] and s['versions']['a']!=s['versions']['b'] and current==s['drafts'][s['page']])
            s['phase']='complete' if s['completed'] else 'playing'
        else:s['phase']='feedback'
        return
    else:_fail()
    s['history'].append({'page':s['page'],'before':before});s['history']=s['history'][-50:]
    s['completed']=False;s['phase']='playing'


def apply_page(validator,state,operation):
    if not isinstance(operation,dict) or not isinstance(operation.get('name'),str):_fail()
    fn={VALIDATORS['scene-p8']:_geese,VALIDATORS['scene-p9']:_tone,VALIDATORS['scene-p10']:_writing,VALIDATORS['scene-p11']:_practice,VALIDATORS['scene-p12']:_observation}.get(validator)
    if not fn:_fail('互动验证器不可用')
    fn(state,operation)
