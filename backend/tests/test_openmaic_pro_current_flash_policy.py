from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient as Client, OpenMaicFullRuntimeError, _canonical_sha256
from integrations.openmaic_formal_media import (PRO_CURRENT_FLASH_PROFESSIONAL_POLICY as Creation,
    PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
    compatible_preparation_targets, professional_policy, professional_scene_learning_fields)
from integrations.openmaic_formal_quality import _quality_verifier_model
from tests.test_formal_provider_readiness_client import _request, _response, _sha
from content.single_course_budget import build_single_course_policy, with_single_teaching_scope
ID = 'deepseek-v4-pro-current-flash-v1'

class ProCurrentFlashPolicyTest(unittest.TestCase):
    def test_registry_and_explicit_selection_only_change_verifier(self):
        registry=json.loads((Path(__file__).parents[1]/'content/openmaic_formal_pro_current_flash.v1.json').read_text())
        with patch.dict('os.environ', {'MIRA_FORMAL_MODEL_POLICY':ID,'MIRA_FORMAL_PLAYFUL_REQUIRE_3D':''}):
            model=Client.selected_professional_model_policy()
            self.assertEqual(model,registry['modelPolicy'])
            for role in ('agentDriver','coursewareCreator','structuredScene'):self.assertEqual(model[role]['modelId'],'deepseek-v4-pro')
            self.assertEqual(model['coursewareVerifier']['modelId'],'deepseek-flash')
            self.assertFalse(model['fallbackAllowed'])
            self.assertEqual(Client.selected_professional_creation_policy(),Creation)
            self.assertEqual({k:v for k,v in Creation.items() if k!='modelPolicyId'},PLAYFUL_PROFESSIONAL_POLICY)
            self.assertNotIn('sceneLearningPolicy',Creation)
        self.assertEqual(_canonical_sha256(Client.FORMAL_PROFESSIONAL_MODEL_POLICY),registry['legacyModelPolicySha256'])
        self.assertEqual(Client.selected_professional_model_policy('deepseek-v4-pro-flash-v1'),Client.FORMAL_PROFESSIONAL_MODEL_POLICY)

    def test_new_receipt_requires_exact_identity_and_preserves_legacy(self):
        contract={'professionalCreationPolicy':Creation};expected={'modelPolicyId':ID}
        self.assertEqual(professional_scene_learning_fields(expected,generation_contract=contract),expected)
        for bad in ({},{'modelPolicyId':'deepseek-v4.1-flash-candidate-v1'},{**expected,'sceneLearningPolicy':{'enforced':True}}):
            with self.assertRaises(ValueError):professional_scene_learning_fields(bad,generation_contract=contract)
        self.assertEqual(professional_scene_learning_fields({},generation_contract={'professionalCreationPolicy':PLAYFUL_PROFESSIONAL_POLICY}),{})
        changed=deepcopy(Creation);changed['supportingSkillIds']=[]
        with self.assertRaises(ValueError):professional_policy(changed)
        self.assertEqual(_quality_verifier_model(contract),'deepseek-flash')
        self.assertEqual(_quality_verifier_model({'professionalCreationPolicy':PLAYFUL_PROFESSIONAL_POLICY}),'deepseek-v4-flash')

    def test_target_reuse_preserves_old_identity_without_relabeling_receipts(self):
        target={'schemaVersion':'mira.learning.preparation-target.v1','formalRuntimePolicy':{
            'professionalCreationPolicy':Creation,'professionalModelPolicy':Client.selected_professional_model_policy(ID)}}
        targets=compatible_preparation_targets(target)
        self.assertEqual(targets[0],target)
        self.assertTrue(any(t['formalRuntimePolicy']['professionalCreationPolicy']==PLAYFUL_PROFESSIONAL_POLICY and t['formalRuntimePolicy']['professionalModelPolicy']==Client.FORMAL_PROFESSIONAL_MODEL_POLICY for t in targets))
        for value in (Client.FORMAL_PROFESSIONAL_MODEL_POLICY,Client.FLASH_CANDIDATE_PROFESSIONAL_MODEL_POLICY):
            changed=deepcopy(target);changed['formalRuntimePolicy']['professionalModelPolicy']=value
            with self.assertRaises(ValueError):compatible_preparation_targets(changed)
        changed=deepcopy(target);changed['formalRuntimePolicy']['professionalCreationPolicy']=PLAYFUL_PROFESSIONAL_POLICY
        with self.assertRaises(ValueError):compatible_preparation_targets(changed)

    def test_required_3d_selection_is_preserved(self):
        with patch.dict('os.environ',{'MIRA_FORMAL_MODEL_POLICY':ID,'MIRA_FORMAL_PLAYFUL_REQUIRE_3D':'1'}):self.assertEqual(Client.selected_professional_creation_policy(),PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY)

    def test_readiness_keeps_pro_with_new_identity(self):
        request=_request();request['modelPolicyId']=ID
        response=_response(request);response['modelPolicyId']=ID
        result=Client._validate_formal_provider_readiness_response(response,request_id=request['requestId'],expected_request_sha256=_sha(request))
        self.assertEqual(result['modelPolicyId'],ID);self.assertEqual(result['calls'][0]['modelId'],'deepseek-v4-pro')
        client=Client('http://127.0.0.1:3100');client._request_formal_audio_json=Mock(return_value=response)
        with patch.dict('os.environ',{'MIRA_FORMAL_MODEL_POLICY':ID}):client.start_formal_provider_readiness(**_request())
        self.assertEqual(client._request_formal_audio_json.call_args.args[2],request)
        for wrong in ('deepseek-flash','deepseek-v4-flash'):
            invalid=deepcopy(response);invalid['calls'][0]['modelId']=wrong
            with self.assertRaises(OpenMaicFullRuntimeError):Client._validate_formal_provider_readiness_response(invalid,request_id=request['requestId'],expected_request_sha256=_sha(request))

    def test_prices_are_unambiguous_keep_caps_and_do_not_reuse_old_scope(self):
        opts=dict(grade='primary_6',subject='math',skill='fraction_ratio_percentage',ordinal=1,now=1000)
        with patch.dict('os.environ',{'MIRA_FORMAL_MODEL_POLICY':''}):old,oldidentity=build_single_course_policy(**opts)
        with patch.dict('os.environ',{'MIRA_FORMAL_MODEL_POLICY':ID}):new,newidentity=build_single_course_policy(**opts)
        self.assertEqual(old.raw['limits'],new.raw['limits']);self.assertNotEqual(oldidentity['scope'],newidentity['scope']);self.assertNotEqual(old.sha256,new.sha256)
        self.assertNotIn('deepseek-current-flash-peak',old.raw['prices'])
        current=[p for p in new.raw['prices'].values() if p['provider']=='deepseek' and p['model']=='deepseek-flash']
        self.assertEqual(len(current),1)
        self.assertEqual(current[0]['perCallMax'],old.raw['prices']['deepseek-flash-peak']['perCallMax'])
        self.assertEqual(current[0]['microsPerMillionUnits'],old.raw['prices']['deepseek-flash-peak']['microsPerMillionUnits'])
        scope={**newidentity['scope'],'purpose':'required_teaching','courseId':'published-course','courseVersion':'v1','userId':'child','sessionId':'learning-session','productionJobId':None}
        teaching=with_single_teaching_scope(new,identity=newidentity,scope=scope,now=2000)
        self.assertIn('deepseek-current-flash-peak',teaching.raw['authorizationTemplates']['required_teaching']['priceKeys'])
        self.assertEqual(teaching.raw['authorizationWindow']['expiresAt'],new.raw['authorizationWindow']['expiresAt'])
        with patch.dict('os.environ',{'MIRA_FORMAL_MODEL_POLICY':ID}),self.assertRaises(ValueError):build_single_course_policy(**opts,vision_provider='openai')
