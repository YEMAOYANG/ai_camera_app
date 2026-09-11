"""Explicit difficulty authority; variant is an identity, never a difficulty label."""
from __future__ import annotations
import ast
import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from fractions import Fraction

DIFFICULTY_POLICY_VERSION = 'mira.learning.difficulty-policy.v1'
DIFFICULTY_CODES = ('basic', 'standard', 'challenge')
# Versioned allocation data. Consumers look up the declared slot, not ordinal rank.
DIFFICULTY_SLOT_MANIFEST = ({'variantOrdinal':1,'difficultyCode':'standard'}, {'variantOrdinal':2,'difficultyCode':'basic'}, {'variantOrdinal':3,'difficultyCode':'challenge'})

def require_difficulty(code):
    if code not in DIFFICULTY_CODES: raise ValueError('explicit registered difficultyCode is required')
    return code

def _text(s): return unicodedata.normalize('NFKC',str(s)).strip()
def _decimal(v): return format(Decimal(v).normalize(),'f')

_READING = {
 ('chinese','short_reading'):'zh_event_sequence',
 ('chinese','reading_evidence'):'zh_plan_revision',
 ('chinese','reading_inference'):'zh_condition_chain',
 ('chinese','narrative_logic'):'zh_cause_chain',
 ('chinese','integrated_reading'):'zh_sources_intersection',
 ('chinese','argument_evidence'):'zh_claim_counterexample',
 ('english','short_reading'):'en_event_sequence',
 ('english','informational_reading'):'en_cause_chain',
 ('english','reading_evidence'):'en_sources_intersection',
 ('english','grammar_in_context'):'en_tense_contrast',
 ('chinese','context_words'):'zh_context_relation',
}

def reading_mode(subject,skill): return _READING.get((subject,skill))

CONTEXT_WORDS = (
 ('忽然','突然','事件发生得出乎预料'),('开心','快乐','心情愉快而高兴'),('美丽','漂亮','样子好看让人喜欢'),('立刻','马上','没有等待就去行动'),('暖和','温暖','感觉不冷而很舒适'),('明白','清楚','已经理解一件事情'),
 ('寻找','寻觅','为了找到目标而到处察看'),('保护','爱护','用行动让事物免受损害'),('帮助','协助','和别人一起解决困难'),('迅速','快速','行动所用的时间很短'),('整洁','干净','物品摆放有序而没有污迹'),('安静','宁静','周围没有喧闹的声音'),
 ('仔细','认真','做事注意细节而不马虎'),('宽广','辽阔','眼前空间延伸得很远'),('喜欢','喜爱','对某件事物感到亲近'),('勇敢','勇猛','面对困难仍敢于行动'),('坚固','牢固','受到外力仍然不易损坏'),('珍惜','爱惜','认为事物宝贵而不浪费'),
)

def _reading_example(mode,band):
    level=DIFFICULTY_CODES.index(band); count=level+2
    if mode=='zh_event_sequence':
        places=['图书馆','公园','博物馆','体育馆'][:count]
        return '短文：'+'。'.join('小林'+('先去' if i==0 else '接着去')+p for i,p in enumerate(places))+'。问题：小林去'+places[-1]+'之前去了哪里？'
    if mode=='en_event_sequence':
        places=['the library','the park','the museum','the pool'][:count]
        return ' '.join('Tom '+('first' if i==0 else 'then')+' went to '+p+'.' for i,p in enumerate(places))+' Where did Tom go before '+places[-1]+'?'
    if mode=='zh_plan_revision':
        plans=['周一去公园','周二去图书馆','周三去博物馆','周四去体育馆'][:count]
        return '短文：小林原计划'+plans[0]+'。'+''.join('通知'+str(i)+'改为'+p+'，并替代之前的安排。' for i,p in enumerate(plans[1:],1))+'问题：按照最后有效的通知，小林在什么时候去哪里？'
    if mode in {'zh_condition_chain','zh_cause_chain','en_cause_chain'}:
        zh=['下雨','地面湿滑','道路封闭','活动取消','改为室内阅读'][:count+1]
        en=['it rains','the ground is wet','the road is closed','the trip is cancelled','the class stays indoors'][:count+1]
        if mode=='zh_condition_chain': return '规则：'+''.join('如果'+a+'，就'+b+'。' for a,b in zip(zh,zh[1:]))+'事实：'+zh[0]+'。问题：按这些规则，最后会怎样？'
        if mode=='zh_cause_chain': return '短文：'+''.join('因为'+a+'，所以'+b+'。' for a,b in zip(zh,zh[1:]))+'问题：导致'+zh[-1]+'的最初原因是什么？'
        return ' '.join(b[0].upper()+b[1:]+' because '+a+'.' for a,b in zip(en,en[1:]))+' What is the earliest cause of '+en[-1]+'?'
    if mode in {'zh_sources_intersection','en_sources_intersection'}:
        if mode=='zh_sources_intersection':
            rows=[(day, ['运动']+[v for j,v in enumerate(['阅读','美术','音乐','科学'][:count]) if j!=i]) for i,day in enumerate(['周一','周二','周三','周四'][:count])]
            return ''.join('资料'+str(i+1)+'：'+day+'开放'+'、'.join(vals)+'。' for i,(day,vals) in enumerate(rows))+'问题：综合所有资料，哪项活动每天都开放？'
        rows=[(day, ['sport']+[v for j,v in enumerate(['reading','art','music','science'][:count]) if j!=i]) for i,day in enumerate(['Monday','Tuesday','Wednesday','Thursday'][:count])]
        return ' '.join('Notice '+str(i+1)+': '+day+' offers '+', '.join(vals)+'.' for i,(day,vals) in enumerate(rows))+' Which activity is offered on every listed day?'
    if mode=='zh_claim_counterexample':
        rows=[('甲组','未使用新纸','完成作品'),('乙组','使用新纸','完成作品'),('丙组','未使用新纸','完成作品'),('丁组','使用新纸','未完成作品')][:count]
        return '观点：只有使用新纸才能完成作品。调查：'+''.join(a+':'+b+'，'+c+'。' for a,b,c in rows)+'问题：哪些组的事实可以直接反驳观点？按调查顺序用顿号列出组名。'
    if mode=='en_tense_contrast':
        rows=['Yesterday she ____ (walk).','Every day she ____ (read).','Tomorrow she ____ (swim).'][:level+1]
        if band=='basic': rows+=['Today she reads at home.']
        return 'Context: '+' '.join(rows)+' Fill the blanks in order, separated by ;.'
    if mode=='zh_context_relation':
        a,b,meaning=CONTEXT_WORDS[level*6]
        return '语境：'+meaning+'。原词：'+a+'。候选：'+b+'、快乐、温暖。问题：哪个词替换原词后仍符合语境？'
    raise ValueError('unregistered reading mode')


def _solve_reading(mode,band,prompt):
    p=_text(prompt); level=DIFFICULTY_CODES.index(band); count=level+2; han=r'([\u3400-\u9fff]{1,20})'
    if mode=='zh_event_sequence':
        m=re.fullmatch(r'短文:(.+)。问题:'+han+r'去'+han+r'之前去了哪里\?',p)
        if m:
            rows=re.findall(han+r'(先去|接着去)'+han,m[1]); places=[r[2] for r in rows]
            if '。'.join(a+b+c for a,b,c in rows)==m[1] and len(rows)==count and len({r[0] for r in rows})==1 and rows[0][0]==m[2] and rows[0][1]=='先去' and all(r[1]=='接着去' for r in rows[1:]) and len(set(places))==count and places[-1]==m[3]: return places[-2]
    if mode=='en_event_sequence':
        m=re.fullmatch(r'(.+) Where did ([A-Za-z]+) go before (the [a-z]+)\?',p)
        if m:
            rows=re.findall(r'([A-Za-z]+) (first|then) went to (the [a-z]+)\.',m[1]); places=[r[2] for r in rows]
            if ' '.join(a+' '+b+' went to '+c+'.' for a,b,c in rows)==m[1] and len(rows)==count and len({r[0] for r in rows})==1 and rows[0][0]==m[2] and rows[0][1]=='first' and all(r[1]=='then' for r in rows[1:]) and len(set(places))==count and places[-1]==m[3]: return places[-2]
    if mode=='zh_plan_revision':
        m=re.fullmatch(r'短文:'+han+r'原计划(周[一二三四五六日])去'+han+r'。(.+)问题:按照最后有效的通知,'+han+r'在什么时候去哪里\?',p)
        if m:
            rows=re.findall(r'通知(\d+)改为(周[一二三四五六日])去'+han+r',并替代之前的安排。',m[4])
            if m[1]==m[5] and len(rows)==count-1 and [int(r[0]) for r in rows]==list(range(1,count)) and ''.join('通知'+a+'改为'+b+'去'+c+',并替代之前的安排。' for a,b,c in rows)==m[4] and len({(m[2],m[3]),*((r[1],r[2]) for r in rows)})==count: return rows[-1][1]+'去'+rows[-1][2]
    if mode in {'zh_condition_chain','zh_cause_chain','en_cause_chain'}:
        if mode=='zh_condition_chain':
            m=re.fullmatch(r'规则:(.+)事实:'+han+r'。问题:按这些规则,最后会怎样\?',p)
            rows=re.findall(r'如果'+han+r',就'+han+r'。',m[1]) if m else []; rebuilt=''.join('如果'+a+',就'+b+'。' for a,b in rows); initial=m[2] if m else ''; final=None
        elif mode=='zh_cause_chain':
            m=re.fullmatch(r'短文:(.+)问题:导致'+han+r'的最初原因是什么\?',p)
            rows=re.findall(r'因为'+han+r',所以'+han+r'。',m[1]) if m else []; rebuilt=''.join('因为'+a+',所以'+b+'。' for a,b in rows); initial=None; final=m[2] if m else ''
        else:
            m=re.fullmatch(r'(.+) What is the earliest cause of ([a-z ]+)\?',p)
            raw=re.findall(r'([A-Z][a-z ]+) because ([a-z ]+)\.',m[1]) if m else []; rows=[(a,b[0].lower()+b[1:]) for b,a in raw]; rebuilt=' '.join(b+' because '+a+'.' for b,a in raw); initial=None; final=m[2] if m else ''
        if m and rebuilt==m[1] and len(rows)==count and all(rows[i][1]==rows[i+1][0] for i in range(len(rows)-1)) and len({rows[0][0],*(b for a,b in rows)})==count+1 and (initial is None or initial==rows[0][0]) and (final is None or final==rows[-1][1]): return rows[-1][1] if mode=='zh_condition_chain' else rows[0][0]
    if mode in {'zh_sources_intersection','en_sources_intersection'}:
        if mode=='zh_sources_intersection':
            m=re.fullmatch(r'(.+)问题:综合所有资料,哪项活动每天都开放\?',p); rows=re.findall(r'资料(\d+):(周[一二三四五六日])开放([\u3400-\u9fff、]+)。',m[1]) if m else []; rebuilt=''.join('资料'+a+':'+b+'开放'+c+'。' for a,b,c in rows); sep='、'
        else:
            m=re.fullmatch(r'(.+) Which activity is offered on every listed day\?',p); rows=re.findall(r'Notice (\d+): (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) offers ([a-z, ]+)\.',m[1]) if m else []; rebuilt=' '.join('Notice '+a+': '+b+' offers '+c+'.' for a,b,c in rows); sep=', '
        sets=[set(r[2].split(sep)) for r in rows]
        if m and rebuilt==m[1] and len(rows)==count and [int(r[0]) for r in rows]==list(range(1,count+1)) and len({r[1] for r in rows})==count and all(2<=len(s)<=5 and len(s)==len(rows[i][2].split(sep)) for i,s in enumerate(sets)):
            common=set.intersection(*sets)
            if len(common)==1 and all(len(s-common)>=1 for s in sets) and all(len(set.intersection(*(s for j,s in enumerate(sets) if j!=i)))>1 for i in range(count)): return next(iter(common))
    if mode=='zh_claim_counterexample':
        m=re.fullmatch(r'观点:只有'+han+r'才能'+han+r'。调查:(.+)问题:哪些组的事实可以直接反驳观点\?按调查顺序用顿号列出组名。',p)
        if m:
            rows=re.findall(han+r':'+han+r','+han+r'。',m[3])
            if ''.join(a+':'+b+','+c+'。' for a,b,c in rows)==m[3] and len(rows)==count and len({r[0] for r in rows})==count:
                evidence=[a for a,b,c in rows if b!=m[1] and c==m[2]]
                if evidence and any(b==m[1] for a,b,c in rows) and all(b in {m[1],'未'+m[1]} and c in {m[2],'未'+m[2]} for a,b,c in rows): return '、'.join(evidence)
    if mode=='en_tense_contrast':
        from content.formal_objective_rules import VERBS
        m=re.fullmatch(r'Context: (.+) Fill the blanks in order, separated by ;\.',p)
        if m:
            rows=re.findall(r'(Yesterday|Every day|Tomorrow) (he|she|they|we) ____ \(([a-z]+)\)\.',m[1]); rebuilt=' '.join(a+' '+b+' ____ ('+c+').' for a,b,c in rows)
            if band=='basic': rebuilt+=' Today she reads at home.'
            if rebuilt==m[1] and len(rows)==level+1 and len({r[0] for r in rows})==len(rows) and all(r[2] in VERBS for r in rows): return ';'.join(VERBS[v][2] if t=='Yesterday' else 'will '+v if t=='Tomorrow' else VERBS[v][0] if who in {'he','she'} else v for t,who,v in rows)
    if mode=='zh_context_relation':
        contexts={a:(meaning,b) for a,b,meaning in CONTEXT_WORDS[level*6:(level+1)*6]}
        m=re.fullmatch(r'语境:'+han+r'。原词:'+han+r'。候选:([\u3400-\u9fff、]+)。问题:哪个词替换原词后仍符合语境\?',p)
        if m and m[2] in contexts and m[1]==contexts[m[2]][0] and m[3].split('、').count(contexts[m[2]][1])==1 and len(set(m[3].split('、')))==3: return contexts[m[2]][1]
    raise ValueError(f'difficulty {band}: prompt does not satisfy {mode} evidence grammar')

_ARITHMETIC_EXAMPLES={
 'integer_add_sub_100':('计算：12+5。','计算：27+18。','计算：45+28-16。'),
 'table_multiply_divide':('计算：2*3。','计算：7*8。','计算：72/8。'),
 'integer_operations_1000':('计算：123+214。','计算：367+458。','计算：345+278-196。'),
 'large_integer_operations':('计算：1200+2300。','计算：321*24。','计算：(321*24)+1876。'),
 'decimal_add_sub':('计算：1.2+2.3。','计算：3.25+1.6。','计算：8.25+3.76-2.18。'),
 'decimal_multiply_divide':('计算：1.2*3。','计算：3.2*1.5。','计算：7.2/1.5*2.4。'),
 'fraction_percentage':('把分数3/4化成百分数是多少？','某活动共有80人，其中3/5参加阅读。参加阅读的有多少人，占总人数的百分之几？按“人数;百分数”回答。','一件商品原价200元，先降价20%，再按降价后价格上涨10%。最终价格比原价降低百分之几？'),
}

def difficulty_spec(grade,subject,skill,band,legacy_mode,legacy_example):
    require_difficulty(band); level=DIFFICULTY_CODES.index(band); mode=reading_mode(subject,skill) or legacy_mode
    example=_reading_example(mode,band) if reading_mode(subject,skill) else _ARITHMETIC_EXAMPLES.get(mode,(legacy_example,)*3)[level]
    if not reading_mode(subject,skill) and mode not in _ARITHMETIC_EXAMPLES and band != 'basic':
        example=_diagnostic_example(grade,subject,skill,mode,band)
    diagnostic = mode not in _ARITHMETIC_EXAMPLES and not reading_mode(subject,skill) and band != 'basic'
    facts = level+2 if reading_mode(subject,skill) else level+1 if diagnostic else 1
    if mode == 'zh_context_relation': facts = 1
    if mode == 'en_tense_contrast': facts = level+1
    steps = facts if reading_mode(subject,skill) or diagnostic else 2 if band=='challenge' else 1
    if mode == 'fraction_percentage': steps = level+1
    complexity={'reasoningSteps':steps,'minEvidenceFacts':facts,'maxEvidenceFacts':facts,'grammarVersion':'mira.learning.banded-objective-grammar.v1', 'assessmentOperation':('compare_claims' if band=='standard' else 'diagnose_errors') if diagnostic else mode}
    if mode == 'fraction_percentage':
        complexity['operandBounds']={'totalPeople':[10,1000],'denominator':[2,100],'numerator':'positive and less than denominator','participants':'integer','percentDecimalPlacesMax':1} if band=='standard' else {'denominatorMax':100} if band=='basic' else {'originalPrice':[10,10000],'firstDecreasePercent':[1,50],'secondIncreasePercent':[1,30],'finalPrice':'less than original price'}
    if diagnostic:
        complexity['requirements']=['distinct public items', 'both true and false proposed claims', 'independently verify every claim']
    return mode,example,complexity

def formal_difficulty_policy(grade_code,subject,skill_id,difficulty_code):
    from content.formal_objective_rules import objective_question_policy,OBJECTIVE_RULE_VERSION
    p=objective_question_policy(grade_code,subject,skill_id,difficulty_code)
    value={'schemaVersion':DIFFICULTY_POLICY_VERSION,'gradeCode':grade_code,'subject':subject,'skillId':skill_id,'difficultyCode':difficulty_code,'objectiveRuleVersion':OBJECTIVE_RULE_VERSION,'mode':p['mode'],'complexity':p['complexity'],'publicPromptExample':p['publicPromptExample']}
    value['policySha256']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value

def _fraction_activity_label(value):
    """A repeated context noun is not an operand or an extra condition.

    The public example uses reading, but its name is illustrative. Accept a
    bounded Han activity label while rejecting prose that changes membership,
    quantities, conjunctions, negation, or the arithmetic being assessed.
    """
    if not re.fullmatch(r'[\u3400-\u9fff]{1,16}', value):
        return False
    if re.search(r'并|且|或|但|若|如果|增加|减少|增至|减至|降至|多于|少于|剩余|剩下|每人|每组|共有|总共|其中|另有|另外|至少|至多|只有|未参加|不参加|退出|转入|转出|人数|百分|分之|同时', value):
        return False
    # A count assertion is forbidden; a lexical name such as 三人篮球 or
    # 二人转 is still just an activity and introduces no extra equation.
    return not re.search(r'[零〇一二两三四五六七八九十百千万亿]+(?:人|个|名|组|次|份|成)$', value)


def solve_banded_question(grade,subject,skill,band,prompt,legacy_solver,legacy_mode):
    require_difficulty(band); p=_text(prompt); mode=reading_mode(subject,skill)
    if mode: return _solve_reading(mode,band,prompt)
    if legacy_mode=='fraction_percentage' and band!='basic':
        if band=='standard':
            m=re.fullmatch(r'某活动共有(\d+)人,其中(\d+)/(\d+)参加(?P<activity>[\u3400-\u9fff]{1,16})。参加(?P=activity)的有多少人,占总人数的百分之几\?按[“"]人数;百分数[”"]回答。',p)
            if m and _fraction_activity_label(m['activity']):
                total,a,b=map(int,m.group(1,2,3)); ratio=Fraction(a,b) if b else Fraction(0); participants=total*ratio; percent=ratio*100
                if 10<=total<=1000 and 0<a<b<=100 and participants.denominator==1 and percent.denominator in {1,2,5,10}: return str(participants.numerator)+';'+_decimal(Decimal(percent.numerator)/Decimal(percent.denominator))+'%'
        else:
            m=re.fullmatch(r'一件商品原价(\d+)元,先降价(\d+)%,再按降价后价格上涨(\d+)%。最终价格比原价降低百分之几\?',p)
            if m:
                price,down,up=map(int,m.groups()); reduction=Fraction(100)-(100-down)*Fraction(100+up,100)
                if 10<=price<=10000 and 1<=down<=50 and 1<=up<=30 and 0<reduction<100: return _decimal(Decimal(reduction.numerator)/Decimal(reduction.denominator))+'%'
        raise ValueError(f'difficulty {band}: fraction percentage requires the registered multi-step application')
    if legacy_mode not in _ARITHMETIC_EXAMPLES and band != 'basic':
        return _solve_diagnostic(grade,subject,skill,band,prompt,legacy_solver)
    answer=legacy_solver(grade,subject,skill,prompt)
    if legacy_mode in set(_ARITHMETIC_EXAMPLES)-{'fraction_percentage','table_multiply_divide'}:
        m=re.fullmatch(r'计算:([0-9. +*/()×÷\-]+)[。?]?',p)
        if not m: raise ValueError('difficulty arithmetic grammar mismatch')
        tree=ast.parse(m[1].replace('×','*').replace('÷','/'),mode='eval'); ops=[n for n in ast.walk(tree) if isinstance(n,ast.BinOp)]; vals=[str(n.value) for n in ast.walk(tree) if isinstance(n,ast.Constant)]
        if (band=='challenge') != (len(ops)>=2): raise ValueError('difficulty requires distinct arithmetic step count')
        if band!='challenge':
            if legacy_mode in {'integer_add_sub_100','integer_operations_1000'}:
                a,b=map(int,vals[:2]); carry=(a%10+b%10>=10) if isinstance(ops[0].op,ast.Add) else (a%10<b%10) if isinstance(ops[0].op,ast.Sub) else True
                if carry != (band=='standard'): raise ValueError('difficulty carry/borrow requirement mismatch')
            if legacy_mode=='large_integer_operations' and isinstance(ops[0].op,(ast.Mult,ast.Div)) != (band=='standard'): raise ValueError('difficulty operation family mismatch')
            if legacy_mode=='decimal_add_sub' and any(len(v.split('.')[-1])>=2 for v in vals if '.' in v) != (band=='standard'): raise ValueError('difficulty decimal precision mismatch')
            if legacy_mode=='decimal_multiply_divide' and (sum('.' in v for v in vals)>=2)!=(band=='standard'): raise ValueError('difficulty decimal operand count mismatch')
    if legacy_mode=='table_multiply_divide':
        m=re.fullmatch(r'计算:(\d+)([*/×÷])(\d+)[。?]?',p); a,op,b=int(m[1]),m[2],int(m[3])
        if band=='basic' and (op not in {'*','×'} or max(a,b)>5): raise ValueError('basic multiplication bound')
        if band=='standard' and (op not in {'*','×'} or min(a,b)<6): raise ValueError('standard multiplication bound')
        if band=='challenge' and op not in {'/','÷'}: raise ValueError('challenge requires inverse table operation')
    return answer

# For elementary single-operation skills, the higher bands assess comparison
# and error diagnosis rather than relabelling the same direct recall question.
# Candidate statements are ordinary public exercise data, not trusted answers.
_DIAGNOSTIC_EXAMPLES = {
 'length_conversion':('换算：3米=多少厘米？','换算：500厘米=多少米？','换算：12米=多少厘米？'),
 'fraction_representation':('把一个整体平均分成8份，取其中3份，用分数表示是多少？','把一个整体平均分成6份，取其中5份，用分数表示是多少？','把一个整体平均分成4份，取其中1份，用分数表示是多少？'),
 'rectangle_perimeter':('长方形长8厘米，宽3厘米，周长是多少厘米？','长方形长9厘米，宽4厘米，周长是多少厘米？','长方形长12厘米，宽5厘米，周长是多少厘米？'),
 'rectangle_area':('长方形长8厘米，宽3厘米，面积是多少平方厘米？','长方形长9厘米，宽4厘米，面积是多少平方厘米？','长方形长12厘米，宽5厘米，面积是多少平方厘米？'),
 'fraction_add_sub':('计算分数：1/3+1/6。','计算分数：3/4-1/8。','计算分数：2/5+1/10。'),
 'cuboid_volume':('长方体长8厘米，宽3厘米，高2厘米，体积是多少立方厘米？','长方体长9厘米，宽4厘米，高3厘米，体积是多少立方厘米？','长方体长12厘米，宽5厘米，高4厘米，体积是多少立方厘米？'),
 'ratio_distribution':('把60个物品按2:3分给甲和乙，甲得到多少个？','把80个物品按3:5分给甲和乙，甲得到多少个？','把96个物品按1:3分给甲和乙，甲得到多少个？'),
 'circle_measure':('圆的半径是3厘米，圆周率取3.14，面积是多少平方厘米？','圆的半径是4厘米，圆周率取3.14，周长是多少厘米？','圆的半径是5厘米，圆周率取3.14，面积是多少平方厘米？'),
 'word_relation':('“开心”的近义词是什么？','“高”的反义词是什么？','“寻找”的近义词是什么？'),
 'sentence_punctuation':('给句子选择句末标点：你要去哪里','给句子选择句末标点：小林正在读书','给句子选择句末标点：多么美丽的花啊'),
 'connective':('选择关联词：____下雨了，所以我们带伞。','选择关联词：____下雨了，但是我们仍出发。','选择关联词：____明天下雨，就改为室内活动。'),
 'paragraph_structure':('判断段落结构：总的来说，校园很美。花坛有花，草地很绿。','判断段落结构：花坛有花，草地很绿。总的来说，校园很美。','判断段落结构：总的来说，公园景色宜人。小河很清，树木很多。'),
 'sentence_revision':('修改不恰当的表达：一只铅笔','修改不恰当的表达：十分非常开心','修改不恰当的表达：增加水平'),
 'simile':('判断修辞：月亮像小船。','判断修辞：湖面像镜子。','判断修辞：雪花像蝴蝶。'),
 'explanation_method':('判断说明方法：这棵树高12米。','判断说明方法：例如，松树四季常青。','判断说明方法：这条河长25米。'),
 'polite_response':('选择得体表达，情境：请求借笔','选择得体表达，情境：打断谈话','选择得体表达，情境：拒绝邀请'),
 'english_vocabulary':None,
 'can_verb':('填空：She can ____ (swim).','填空：They can\'t ____ (fly).','填空：He can ____ (write).'),
 'self_information':('My name is Lily. What is my name?','I am 9 years old. How old am I?','My name is Tom. What is my name?'),
 'present_simple':('填空：He ____ (walk) every day.','填空：They ____ (read) every day.','填空：She ____ (go) every day.'),
 'clock_order':('Tom starts at 08:30. Lily starts at 09:00. Who starts earlier?','Amy starts at 10:15. Ben starts at 09:45. Who starts earlier?','Sam starts at 14:20. Eve starts at 14:10. Who starts earlier?'),
 'wh_word':('填空：____ is Tom? He is at home.','填空：____ is Lily? She is a teacher.','填空：____ is Amy? She is at school.'),
 'there_be':('填空：There ____ 3 books on the desk.','填空：There ____ 1 book on the desk.','填空：There ____ 5 rulers on the desk.'),
 'present_tense':('填空：He ____ (run) now.','填空：They ____ (read) every day.','填空：I ____ (swim) now.'),
 'height_comparison':('Tom is 120 cm tall. Lily is 130 cm tall. Who is taller?','Amy is 135 cm tall. Ben is 128 cm tall. Who is taller?','Sam is 141 cm tall. Eve is 145 cm tall. Who is taller?'),
 'past_future':('填空：She ____ (walk) yesterday.','填空：They ____ (swim) tomorrow.','填空：He ____ (write) yesterday.'),
}

def _diagnostic_examples(mode,skill):
    if mode=='english_vocabulary':
        words=('爸爸','姐姐','朋友') if skill=='family_people' else ('书','铅笔','字典')
        return tuple('选择英语词语：'+w for w in words)
    return _DIAGNOSTIC_EXAMPLES[mode]

def _diagnostic_example(grade,subject,skill,mode,band):
    from content.formal_objective_rules import _solve_legacy_objective_question
    count=2 if band=='standard' else 3
    prompts=_diagnostic_examples(mode,skill)[:count]
    answers=[_solve_legacy_objective_question(grade,subject,skill,p) for p in prompts]
    # A plausible answer from a different item supplies a distractor. If all
    # answers coincide (e.g. similes), a registered contrasting category is used.
    wrong=next((a for a in answers if a!=answers[-1]), '不是'+answers[-1] if subject=='chinese' else 'incorrect')
    answers[-1]=wrong
    return '辨析任务：'+''.join(label+'题【'+p+'】说法【'+a+'】。' for label,p,a in zip('ABC' if subject=='english' else '甲乙丙',prompts,answers))+('问题：哪些说法正确？' if band=='standard' else '问题：哪些说法错误？')+('按ABC顺序用分号列出；没有则回答none。' if subject=='english' else '按甲乙丙顺序用顿号列出；没有则回答无。')

def _solve_diagnostic(grade,subject,skill,band,prompt,legacy_solver):
    p=_text(prompt); count=2 if band=='standard' else 3
    suffix='问题:哪些说法'+('正确' if band=='standard' else '错误')+'\?'+('按ABC顺序用分号列出;没有则回答none。' if subject=='english' else '按甲乙丙顺序用顿号列出;没有则回答无。')
    m=re.fullmatch('辨析任务:(.+)'+suffix,p)
    rows=re.findall(r'([甲乙丙ABC])题【([^【】]+)】说法【([^【】]+)】。',m[1]) if m else []
    if not m or len(rows)!=count or [r[0] for r in rows]!=list(('ABC' if subject=='english' else '甲乙丙')[:count]) or len({r[1] for r in rows})!=count or ''.join(a+'题【'+b+'】说法【'+c+'】。' for a,b,c in rows)!=m[1]: raise ValueError(f'difficulty {band}: requires {count} distinct independently checked claims')
    normalize=lambda s:_text(s).casefold().replace(' ','')
    truth=[normalize(claim)==normalize(legacy_solver(grade,subject,skill,question)) for _,question,claim in rows]
    # All-true/all-false sets are guessing-prone, so a contrast is mandatory.
    if len(set(truth))!=2: raise ValueError('diagnostic task requires both supported and refutable claims')
    selected=[label for (label,_,_),correct in zip(rows,truth) if correct==(band=='standard')]
    return (';' if subject=='english' else '、').join(selected) if selected else ('none' if subject=='english' else '无')
