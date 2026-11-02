from copy import deepcopy
import unittest
from content import textbook_science_fruit as f
from content import textbook_course_interaction as c
from core.errors import ApiError


def work(p):
    d={2:[],3:[],4:[],5:{k:[] for k in ['vision','probe','smell','taste']},
       6:{'positions':{'left':'apple','right':'tomato'},'mode':'angle','force':'light'},
       7:dict.fromkeys(f.VENN),8:{},9:dict.fromkeys(f.TRANSFER),10:None,11:{'F1':1,'F2':1}}[p]
    x={4:{'force':1},6:{'swaps':0,'fruits':{k:{'angle':0,'force':None} for k in ['apple','tomato']}},
       8:{'standard':None},9:{'standard':None},10:{'phase':'judge','tool':None,'top':False,'bottom':False,'count':0},
       11:{'phase':1,'senses':[],'force':'light','view':'front','probes':{'F1':None,'F2':None},'exchanged':False,'standard':None}}.get(p,{})
    return {'started':True,'decision':d,'domain':x,'help':0,'first':None,'response':None}


def begin(p):
    v=f.VALIDATORS[f'scene-p{p}'];s=f.initial_page(v);w=work(p)
    f.apply_page(v,s,{'name':'work','action':'start','work':w})
    return v,s,w


def act(v,s,w,action='picture'):
    f.apply_page(v,s,{'name':'submit','action':action,'work':deepcopy(w)})


class FruitInteractionTests(unittest.TestCase):
    def test_exact_binding_and_all_interactive_pages_required(self):
        room={'scenes':[{'id':f'scene-p{p}','order':p,'type':'interactive' if 2<=p<=11 else 'slide','content':{'html':'<p>fruit</p>'}} for p in range(1,13)]}
        contract=c.build_contract(room,f.BINDING)
        assert len(contract['scenes'])==10
        assert not c.completion_ready({}, {'classroom':room,'textbookBinding':f.BINDING,'interactionCompletionContract':contract})
        room['scenes'].pop(3)
        with self.assertRaises(ApiError):c.build_contract(room,f.BINDING)
        assert f.validators({**f.BINDING,'nodeId':'other'}) is None


    def test_no_completion_from_start_or_client_flags(self):
        for p in range(2,12):
            v,s,w=begin(p);assert not s['completed']
            original=deepcopy(s);w['completed']=True
            with self.assertRaises(ApiError):act(v,s,w)
            assert s==original


    def test_safe_channels_and_supported_evidence_not_mastery(self):
        v,s,w=begin(2);w['decision']=['nose','eyes','hand','tongue'];act(v,s,w);assert not s['completed']
        w['decision']=['eyes','hand','nose','tongue'];w['help']=1;act(v,s,w)
        assert s['completed'] and s['helpCount']==1 and s['firstWork']['decision'][0]=='nose'
        assert 'not_real_sensory' in s['evidenceBoundary']


    def test_unique_multiregion_observation(self):
        v,s,w=begin(3)
        w['decision']=[{'label':x,'region':'顶部','rotation':0} for x in ['果蒂','橙色','接近球形']]
        act(v,s,w);assert not s['completed']
        w['decision'][-1]={'label':'表面有小点','region':'侧面','rotation':30};act(v,s,w);assert s['completed']
        w['decision'].append(w['decision'][0]);before=deepcopy(s)
        with self.assertRaises(ApiError):act(v,s,w)
        assert s==before


    def test_press_and_texture_and_source_mapping(self):
        v,s,w=begin(4);w['decision']=[{'kind':'press','text':'软硬·轻压回弹 (弹性)'}];act(v,s,w);assert not s['completed']
        w['decision'].append({'kind':'texture','text':'纹理·小凸点/粗糙 (表面)'});act(v,s,w);assert s['completed']
        v,s,w=begin(5)
        for k,b in f.SOURCES.items():w['decision'][b].append(k)
        w['decision']['vision'].remove('ev-color');w['decision']['taste'].append('ev-color');act(v,s,w);assert not s['completed']
        w['decision']['taste'].remove('ev-color');w['decision']['vision'].append('ev-color');act(v,s,w);assert s['completed']


    def test_fair_comparison_requires_observed_swap_and_remeasurement(self):
        v,s,w=begin(6)
        for fruit in w['domain']['fruits'].values():fruit['force']='light'
        act(v,s,w);assert not s['completed']
        w['domain']['swaps']=1;w['decision']['positions']={'left':'tomato','right':'apple'}
        act(v,s,w);assert not s['completed'] # cannot just increment the swap flag
        w['domain']['swaps']=0;w['decision']['positions']={'left':'apple','right':'tomato'};act(v,s,w)
        w['domain']['swaps']=1;w['decision']['positions']={'left':'tomato','right':'apple'}
        for fruit in w['domain']['fruits'].values():fruit['force']=None
        act(v,s,w)
        w['domain']['fruits']['apple']['force']='light';act(v,s,w);assert not s['completed']
        w['domain']['fruits']['tomato']['force']='light';act(v,s,w);assert s['completed']

    def test_legacy_page_six_first_input_is_recovered_without_inventing_completion(self):
        validator=f.VALIDATORS['scene-p6']; state=f.initial_page(validator)
        start=work(6); del start['started']
        original=deepcopy(start)
        f.apply_page(validator,state,{'name':'work','action':'startExploreBtn','work':start})
        assert start == original and state['lastWork']['started'] is True
        assert not state['completed'] and not state['attempts'] and not state['milestones']

        state=f.initial_page(validator); first=deepcopy(start)
        first['domain']['fruits']['apple']['angle']=1
        first['first']={'type':'angle','fruit':'apple','from':0,'to':1}
        f.apply_page(validator,state,{'name':'work','action':'leftCard','work':first})
        assert state['lastWork']['started'] is True and state['firstAnswer']==first['first']
        assert not state['completed'] and not state['attempts'] and not state['milestones']

        for change in ('unknown-action','completed-first','malformed','wrong-name'):
            state=f.initial_page(validator); bad=deepcopy(start); action='startExploreBtn'
            name='work'
            if change=='unknown-action': action='fabricated'
            if change=='completed-first':
                bad['domain']['fruits']['apple']['force']='light'
                bad['domain']['fruits']['tomato']['force']='light'
            if change=='malformed': bad['decision']['positions']={'left':'tomato','right':'tomato'}
            if change=='wrong-name': name='submit'
            with self.subTest(change=change), self.assertRaises(ApiError):
                f.apply_page(validator,state,{'name':name,'action':action,'work':bad})
            assert state['lastWork'] is None


    def test_venn_classification_and_transfer_recompute_all_items(self):
        v,s,w=begin(7);w['decision']=dict(f.VENN);w['decision']['ev-round']='apple';act(v,s,w);assert not s['completed']
        w['decision']=dict(f.VENN);act(v,s,w);assert s['completed']
        v,s,w=begin(8);w['domain']['standard']='shape';w['decision']={k:'left' if a[1]=='round' else 'right' for k,a in f.FRUITS.items()}
        act(v,s,w);assert s['completed']
        v,s,w=begin(9);w['domain']['standard']='surface';w['decision']={'seedpod':'A','shell':'B','cork':'A'}
        act(v,s,w);assert not s['completed']
        act(v,s,w,'shakeBtn');assert s['completed']


    def test_measurement_cannot_finish_with_magnifier_or_unconfirmed_answer(self):
        v,s,w=begin(10);w['decision']='top';w['domain'].update(count=1,phase='tool');act(v,s,w)
        w['domain'].update(tool='magnifier',top=True,bottom=True,phase='done')
        with self.assertRaises(ApiError):act(v,s,w,'applyReviseBtn')
        assert not s['completed']
        w['domain'].update(tool='ruler',top=True,bottom=False,phase='measure');act(v,s,w)
        w['domain'].update(bottom=True,phase='revise');act(v,s,w);assert not s['completed']
        act(v,s,w,'applyReviseBtn');assert s['completed'] and s['firstWork']['decision']=='top'


    def test_integrated_investigation_cannot_skip_phases(self):
        v,s,w=begin(11);w['domain']['phase']=3;before=deepcopy(s)
        with self.assertRaises(ApiError):act(v,s,w)
        assert s==before
        w['domain'].update(phase=1,senses=['eye','hand']);act(v,s,w)
        w['domain']['phase']=2;act(v,s,w)
        w['domain']['probes']={k:{'force':'light','view':'front'} for k in ['F1','F2']};act(v,s,w)
        w['domain'].update(exchanged=True,probes={'F1':None,'F2':None});act(v,s,w)
        w['domain']['probes']={k:{'force':'light','view':'front'} for k in ['F1','F2']};act(v,s,w)
        w['domain'].update(phase=3,standard='color');act(v,s,w);assert not s['completed']
        w['decision']['F1']=0;act(v,s,w);assert s['completed']
