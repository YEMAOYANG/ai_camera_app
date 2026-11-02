import unittest
from copy import deepcopy
from content import textbook_math_interaction as m, textbook_course_interaction as ci
from core.errors import ApiError


def release(kind):
    binding = {'editionId':m.EDITION,'revisionId':m.REVISION,
               'nodeId':next(k for k,v in m.NODES.items() if v == kind)}
    room = {'scenes':[{'id':f'scene-p{i}','order':i,'type':'interactive' if 2 <= i <= 8 else 'slide',
                      'content':{'html':f'<main>{kind}-{i}</main>'}} for i in range(1,10)]}
    return {'classroom':room,'textbookBinding':binding,'interactionCompletionContract':ci.build_contract(room,binding)}


class MathInteractionTest(unittest.TestCase):
    def test_all_pages_server_recompute_and_recovery(self):
        cases = {
          'compare':{
            2:[{'preset':0,'assignments':['p0','p1','p2']},{'preset':1,'assignments':['p0','p1',None,None]}],
            3:[{'pairs':[{'left':f'L{i}','right':f'R{i}'} for i in range(1,5)]}],
            4:[{'leftCount':5,'rightCount':3,'openSide':'left'},{'leftCount':3,'rightCount':5,'openSide':'right'}],
            5:[{'round':i,'left':l,'right':r} for i,(l,r) in enumerate([(2,2),(3,1),(1,4)])],
            6:[{'index':i,'strokes':[[s[:2],s[2:]] for s in shape]} for i,shape in enumerate(m.INK)],
            7:[{'round':i,'marked':[f'l{n}' for n in range(1,l+1)]+[f'r{n}' for n in range(1,r+1)],'sign':sign}
               for i,(l,r,sign) in enumerate([(4,4,'='),(3,5,'<'),(5,2,'>')])],
            8:[{'relation':'eq','left':[{'uid':1,'type':'cup'}],'right':[{'uid':2,'type':'box'}]}]},
          'ordinal':{
            2:[{'phase':'quantity','inside':m.ROLES},{'phase':'ordinal','inside':['r2']}],
            3:[{'mode':'practice','task':i,'atDoor':r} for i,r in enumerate(['r5','r1','r2'])],
            4:[{'round':0,'left':1,'right':5},{'round':1,'left':3,'right':3}],
            5:[{'phase':0,'order':['compass','telescope','magnifier','ruler','tweezers']},
               {'phase':1,'order':['tweezers','telescope','magnifier','ruler','compass']}],
            6:[{'direction':'left','answer':'r2'},{'direction':'right','answer':'r4'}],
            7:[{'round':i,'opened':opened,'direction':d,'rank':r} for i,(opened,d,r) in enumerate([
               (['w3'],None,None),(['w4'],None,None),([],'right',1),([],'left',3)])],
            8:[{'phase':'ordinal','departure':'boat-2','docked':[]},{'phase':'quantity','departure':None,'docked':['boat-0','boat-2','boat-4']}]}}
        for kind,pages in cases.items():
            rel = release(kind); progress = {}; n = 0
            for page, works in pages.items():
                for work in works:
                    n += 1
                    ci.apply_operation(progress,release=rel,scene_id=f'scene-p{page}',scene_index=page-1,
                      contract_sha256=rel['interactionCompletionContract']['sha256'],operation_id=f'op-{n}',operation={'name':'submit','work':work})
            self.assertTrue(ci.completion_ready(progress,rel))
            self.assertTrue(all(v['completed'] for v in ci.recovery_state(progress,rel)['scenes'].values()))

    def test_wrong_choices_and_help_are_not_mastery_or_completion(self):
        state=m.initial_page('math-ordinal-p6.v1')
        m.apply_page(state['validator'],state,{'name':'help','work':{'direction':'right','answer':None}})
        m.apply_page(state['validator'],state,{'name':'submit','work':{'direction':'right','answer':'r2'}})
        self.assertFalse(state['completed']);self.assertFalse(state['attempts'][0]['correct'])
        self.assertEqual(state['attempts'][0]['helpCount'],1)
        self.assertEqual(state['attempts'][0]['assistanceOutsideApp'],'unobserved')
        for op in [{'name':'submit','work':{'direction':'right','answer':'r4'},'completed':True},
                   {'name':'submit','work':{'direction':'right','answer':'r4','correct':True}},
                   {'name':'submit','work':{'direction':'right','answer':'outsider'}}]:
            with self.assertRaises(ApiError):m.apply_page(state['validator'],state,op)

    def test_missing_pages_foreign_binding_and_round_skip_fail(self):
        rel=release('compare'); rel['classroom']['scenes'].pop(4)
        with self.assertRaises(ApiError):ci.build_contract(rel['classroom'],rel['textbookBinding'])
        rel=release('ordinal');rel['textbookBinding']['revisionId']='another'
        with self.assertRaises(ApiError):ci.validate_contract(rel)
        state=m.initial_page('math-compare-p5.v1')
        with self.assertRaises(ApiError):m.apply_page(state['validator'],state,{'name':'submit','work':{'round':2,'left':1,'right':3}})

    def test_ink_shortcuts_and_extra_objects(self):
        self.assertFalse(m.ink_covered(0,[[[1,1],[399,279]]]))
        with self.assertRaises(ApiError):m.compare_work(2,{'preset':0,'assignments':['p0','p0',None]})
        self.assertFalse(m.compare_work(7,{'round':0,'marked':['ld2','rd2'],'sign':'='})[1])
