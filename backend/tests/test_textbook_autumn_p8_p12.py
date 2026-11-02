import unittest
from core.errors import ApiError
from content.textbook_autumn_p8_p12 import VALIDATORS, initial_page, apply_page


def op(v,s,name,**kw): apply_page(v,s,{'name':name,**kw})
def line(a,b): return [{'x':a[0]+(b[0]-a[0])*i/12,'y':a[1]+(b[1]-a[1])*i/12} for i in range(13)]


class AutumnAdditionalPages(unittest.TestCase):
    def test_geese_failure_revision_and_both_real_formations(self):
        v=VALIDATORS['scene-p8'];s=initial_page(v);op(v,s,'start');op(v,s,'submit');self.assertFalse(s['completed'])
        for i,(x,y) in enumerate([(512,100),(412,200),(312,300),(212,400),(612,200),(712,300),(812,400)]):op(v,s,'move',bird=i,x=x,y=y)
        op(v,s,'submit');self.assertEqual(s['level'],2);op(v,s,'rotate');op(v,s,'leader',bird=6)
        for i in range(7):op(v,s,'move',bird=i,x=150+100*i,y=280)
        op(v,s,'submit');self.assertTrue(s['completed']);self.assertEqual([x['formation'] for x in s['previousLegs']],['人','一'])

    def test_tone_wrong_retry_and_no_forged_completion(self):
        v=VALIDATORS['scene-p9'];s=initial_page(v);op(v,s,'start');op(v,s,'choose',tone=1);op(v,s,'submit');self.assertFalse(s['completed'])
        for i,tone in enumerate((2,4,2,1)):
            op(v,s,'context',index=i);op(v,s,'choose',tone=tone);op(v,s,'submit')
        self.assertTrue(s['completed']);self.assertFalse(s['attempts'][0]['passed'])
        with self.assertRaises(ApiError):apply_page(v,s,{'name':'submit','completed':True})

    def test_writing_requires_actual_paths_and_crossing(self):
        v=VALIDATORS['scene-p10'];s=initial_page(v);op(v,s,'start')
        for a,b in [((.58,.12),(.20,.82)),((.45,.38),(.82,.84))]:op(v,s,'stroke',character='ren',points=line(a,b))
        self.assertEqual(s['completedChars'],['ren'])
        for a,b in [((.28,.37),(.72,.37)),((.53,.12),(.20,.84)),((.4154,.37),(.82,.84))]:op(v,s,'stroke',character='da',points=line(a,b))
        self.assertTrue(s['completed'])
        with self.assertRaises(ApiError):apply_page(v,s,{'name':'stroke','character':'da','points':[],'passed':True})

    def test_character_switch_keeps_each_version_and_retry_revokes_only_one(self):
        v=VALIDATORS['scene-p10'];s=initial_page(v);op(v,s,'start')
        op(v,s,'stroke',character='ren',points=line((.58,.12),(.20,.82)))
        op(v,s,'character',character='da');op(v,s,'character',character='ren')
        self.assertEqual(len(s['strokes']),1)
        op(v,s,'stroke',character='ren',points=line((.45,.38),(.82,.84)))
        self.assertEqual(s['completedChars'],['ren'])
        op(v,s,'character',character='ren');op(v,s,'undo')
        self.assertEqual(s['completedChars'],[]);self.assertEqual(len(s['strokes']),1)

    def test_practice_retry_and_observation_undo_restore(self):
        v=VALIDATORS['scene-p11'];s=initial_page(v);op(v,s,'start');op(v,s,'save');op(v,s,'retry')
        self.assertEqual(s['saved'],[]);op(v,s,'save');self.assertEqual(s['saved'],[0])
        v=VALIDATORS['scene-p12'];s=initial_page(v);op(v,s,'start');op(v,s,'object',object='plant')
        op(v,s,'quantity',delta=1);self.assertEqual(s['drafts']['a']['quantity'],2)
        op(v,s,'undo');self.assertEqual(s['drafts']['a']['quantity'],1)
        op(v,s,'reset');self.assertIsNone(s['drafts']['a']['selectedObject'])
        op(v,s,'undo');self.assertEqual(s['drafts']['a']['selectedObject'],'plant')

    def test_self_report_cannot_claim_oral_accuracy(self):
        v=VALIDATORS['scene-p11'];s=initial_page(v);op(v,s,'start')
        for i in range(3):op(v,s,'mode',index=i);op(v,s,'save')
        self.assertTrue(s['completed']);self.assertEqual(s['evidenceBoundary'],'child_self_report_no_oral_assessment')
        self.assertTrue(all(x['basis']=='child_self_report_no_oral_assessment' for x in s['attempts']))
        with self.assertRaises(ApiError):apply_page(v,s,{'name':'save','oralAccuracy':'correct'})

    def test_observation_requires_two_distinct_valid_pages_no_parent(self):
        v=VALIDATORS['scene-p12'];s=initial_page(v);op(v,s,'start');op(v,s,'save');self.assertFalse(s['completed'])
        op(v,s,'object',object='plant');op(v,s,'save');op(v,s,'object',object='plant');op(v,s,'save');self.assertFalse(s['completed'])
        op(v,s,'object',object='animal');op(v,s,'save');self.assertTrue(s['completed'])
        with self.assertRaises(ApiError):apply_page(v,s,{'name':'save','familyConfirmed':True})


if __name__=='__main__':unittest.main()
