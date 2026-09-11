"""No providers: registered mechanisms and snapshot-bound visual review."""
from copy import deepcopy
import unittest
from integrations.openmaic_formal_quality import quality_sha, QUALITY_VIEWPORTS
from integrations.openmaic_formal_interaction import interaction_design_receipt
from integrations.openmaic_formal_exploration import validate_exploration, validate_exploration_checks
from integrations.openmaic_formal_visual import visual_review_receipt
from tests.test_openmaic_formal_interaction import interaction_fixture, signed


def model():
    return dict(schemaVersion='mira.openmaic.multistate-exploration.v1',
        mechanism=dict(kind='fraction-ratio-percentage.v1',numeratorSelector='#n',denominatorSelector='#d',decimalSelector='#decimal',percentSelector='#percent',wholeSelector='#whole',partSelector='#part'),
        diagramSelector='#diagram',feedbackSelector='#result',reset=dict(selector='#reset',stateId='s0'),
        states=[dict(id=f's{i}',operations=[dict(selector=f'#s{i}',action='click')],numerator=n,denominator=d,
                     resultText=f'{n}/{d} = {100*n/d}%',explanationText=f'平均分成{d}份取{n}份。') for i,(n,d) in enumerate(((1,4),(2,5),(3,4)))])


def receipt():
    manifest,_=interaction_fixture()
    old=manifest['professionalCreation']['interactionDesign']
    old.update(schemaVersion='mira.openmaic.interaction-design-receipt.v2',policyId='mira-primary-multistate-interaction.v2',explorationChecks=[])
    for goal in old['objectives']:
        goal['exploration']=model()
        for i,v in enumerate(QUALITY_VIEWPORTS):
            states=[dict(stateId=s['id'],diagramSha256=quality_sha('diagram'+s['id']),feedbackSha256=quality_sha('feedback'+s['id']),numeric=dict(numerator=s['numerator'],denominator=s['denominator'],decimal=s['numerator']/s['denominator'],percent=100*s['numerator']/s['denominator'],diagramRatio=s['numerator']/s['denominator'])) for s in model()['states']]
            old['explorationChecks'].append(dict(objectiveIndex=goal['objectiveIndex'],viewport=v,evidence=dict(mechanism='fraction-ratio-percentage.v1',verification='independent_numeric_svg',inputMode='pointer' if i==0 else 'touch',resetPassed=True,states=states)))
    old['planSha256']=quality_sha(dict(schemaVersion='mira.openmaic.interaction-design-plan.v2',objectives=[{k:v for k,v in o.items() if k!='checks'} for o in old['objectives']]))
    q=manifest['professionalCreation']['teachingQuality']
    old['visualReview']=signed(dict(schemaVersion='mira.openmaic.visual-review.v1',reviewerKind='vision_model',status='passed',rubricVersion='mira.primary-teaching-visual.v1',snapshotSha256=q['snapshotSha256'],teachingQualityContextSha256=quality_sha({k:q[k] for k in ('snapshotSha256','gradeBoundarySha256','selectionPlanSha256','teachingBriefSha256')}),sceneReviews=[{k:r[k] for k in ('sceneId','sceneSha256','viewport','screenshotSha256')}|dict(legibility='passed',layout='passed',teachingGraphic='passed',interactionAffordance='passed',notes='Test fixture only; no model call.') for r in q['renderChecks']],providerId='deepseek',modelId='deepseek-v4-flash-vision-exp',providerResponseModelId='deepseek-flash',providerRequestIdHash='c'*64))
    return signed(old),q


class FormalMultistateTest(unittest.TestCase):
    def test_v2_receipt_preserves_plan_and_two_device_proofs(self):
        r,q=receipt()
        interaction_design_receipt(r)
        visual_review_receipt(r['visualReview'],q)

    def test_wrong_numeric_reset_and_touch_are_rejected_after_rehash(self):
        for mutate in (
            lambda r:r['explorationChecks'][0]['evidence']['states'][1]['numeric'].update(percent=25),
            lambda r:r['explorationChecks'][0]['evidence']['states'][1]['numeric'].update(diagramRatio=0.9),
            lambda r:r['explorationChecks'][1]['evidence'].update(inputMode='pointer'),
            lambda r:r['explorationChecks'][1]['evidence'].update(resetPassed=False),
        ):
            r,_=receipt();mutate(r)
            with self.assertRaises(ValueError):interaction_design_receipt(signed(r))

    def test_visual_wrong_snapshot_incomplete_review_or_text_model_fails(self):
        for mutate in (
            lambda v:v.update(snapshotSha256='0'*64),
            lambda v:v['sceneReviews'][0].update(teachingGraphic='needs_revision'),
            lambda v:v['sceneReviews'].pop(),
            lambda v:v.update(modelId='deepseek-v4-flash'),
        ):
            r,q=receipt();v=r['visualReview'];mutate(v)
            with self.assertRaises(ValueError):visual_review_receipt(signed(v),q)

    def test_numeric_skill_cannot_downgrade(self):
        m=model();m['mechanism']={'kind':'semantic-state-model.v1'}
        for s in m['states']:s.pop('numerator');s.pop('denominator')
        validate_exploration(m,skill_id='language_organization')
        with self.assertRaises(ValueError):validate_exploration(m,skill_id='fraction_ratio_percentage')
