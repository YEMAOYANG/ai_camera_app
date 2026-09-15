from copy import deepcopy
import json
import unittest

from integrations.openmaic_formal_quality import quality_sha, quality_snapshot
from services.learning_saved_stage_reconciliation import validate_learner_discussion_repair


class SavedStageLearnerDiscussionRepairTest(unittest.TestCase):
    def fixture(self):
        prepared = {'stage': {'id': 'stage-1', 'name': 'Fractions'}, 'scenes': [
            {'id': f'scene-p{i}', 'type': 'quiz' if i == 7 else 'slide',
             'title': f'Page {i}', 'order': i - 1,
             'content': {'html': f'<p>Frozen page {i}</p>', 'questions': [{'answer': '3/5'}] if i == 7 else []},
             'actions': [{'id': f'speech-{i}', 'type': 'speech', 'text': f'Frozen narration {i}'}]}
            for i in range(1, 9)]}
        result = deepcopy(prepared)
        result['stage'].update(agentIds=['teacher-1', 'peer-1'],
            generatedAgentConfigs=[{'id': 'teacher-1', 'role': 'teacher'}, {'id': 'peer-1', 'role': 'student'}])
        insertions = []
        for index in (0, 7):
            action = {'id': f'learner-discussion-{index}', 'type': 'discussion',
                'topic': 'Explain your thinking', 'prompt': 'Tell us what changed in your explanation.',
                'agentId': 'teacher-1'}
            insertions.append({'sceneId': prepared['scenes'][index]['id'],
                'afterActionCount': 1, 'action': action})
            result['scenes'][index]['actions'].append(deepcopy(action))
        # Quality projection intentionally excludes only speech playback fields.
        result['scenes'][3]['actions'][0]['audioUrl'] = '/verified-audio.wav'
        receipt = {'schemaVersion': 'mira.openmaic.learner-discussion-repair.v1',
            'promptVersion': 'mira.formal-learner-discussion-repair.v1',
            'sessionId': 'session-1', 'stageId': 'stage-1', 'sourceSnapshotSha256': 'a' * 64,
            'inputSnapshotSha256': quality_sha(prepared), 'outputSnapshotSha256': quality_sha(quality_snapshot(result)),
            'frozenContextSha256': 'b' * 64, 'rejectedReviewSha256': 'c' * 64,
            'requestSha256': 'd' * 64, 'providerResponseSha256': 'e' * 64,
            'providerRequestIdHash': 'f' * 64, 'providerId': 'deepseek', 'modelId': 'deepseek-v4-flash',
            'authorizationId': '1' * 64, 'namespace': 'session-1:completion',
            'repairReference': '2' * 64, 'insertions': insertions}
        receipt['receiptSha256'] = quality_sha(receipt)
        completion = {'sessionId': 'session-1', 'stageId': 'stage-1', 'sourceSnapshotSha256': 'a' * 64,
            'repairSnapshotSha256': quality_sha(prepared), 'result': result, 'learnerDiscussionRepair': receipt}
        return completion, prepared

    def resign(self, completion):
        receipt = completion['learnerDiscussionRepair']
        receipt['outputSnapshotSha256'] = quality_sha(quality_snapshot(completion['result']))
        receipt.pop('receiptSha256', None)
        receipt['receiptSha256'] = quality_sha(receipt)

    def audit_fixture(self):
        completion, prepared = self.fixture()
        receipt = completion['learnerDiscussionRepair']
        context = {'gradeBoundary': {'gradeCode': 'primary_6'},
            'selectionPlan': {'primaryMethod': 'feynman-learning'}, 'teachingBrief': {'goal': 'Understand fractions'}}
        context['selectionPlan']['planSha256'] = quality_sha(context['selectionPlan'])
        rejection = {'status': 'needs_revision', 'snapshotSha256': quality_sha(prepared),
            'issues': [{'sceneId': 'scene-p3', 'problem': 'Feynman learner explanation missing'}]}
        receipt['frozenContextSha256'] = quality_sha(context)
        receipt['rejectedReviewSha256'] = quality_sha(rejection)
        identity = {key: receipt[key] for key in ('sessionId', 'stageId', 'sourceSnapshotSha256',
            'inputSnapshotSha256', 'frozenContextSha256', 'rejectedReviewSha256')}
        request = {'schemaVersion': 'mira.openmaic.courseware-provider-call.v1',
            'phase': 'learner_discussion_repair', 'requestId': 'learner-repair-' + quality_sha(identity),
            'systemPrompt': 'Generate discussion actions only.',
            'userPrompt': json.dumps({**context, 'snapshot': prepared, 'rejectedReview': rejection,
                'promptVersion': receipt['promptVersion']})}
        response = {key: request[key] for key in ('schemaVersion', 'phase', 'requestId')}
        response.update(providerRequestIdHash=receipt['providerRequestIdHash'],
            content=json.dumps({'insertions': receipt['insertions']}))
        receipt['requestSha256'] = quality_sha(request)
        receipt['providerResponseSha256'] = quality_sha(response)
        completion['result']['professionalCreation'] = {'teachingQuality': {
            'status': 'passed', 'snapshotSha256': receipt['outputSnapshotSha256'],
            **{key + 'Sha256': quality_sha(value) for key, value in context.items()},
            'selectionPlanSha256': context['selectionPlan']['planSha256']}}
        self.resign(completion)
        claim = {**identity, **{key: receipt[key] for key in ('authorizationId', 'namespace', 'repairReference', 'requestSha256')},
                 'startedAt': 1}
        audit = {'input': {**identity, 'frozenContext': context, 'snapshot': deepcopy(prepared),
                         'sourceScenes': deepcopy(prepared['scenes'])},
            'request': request, 'provider-response': response, 'rejected-review': rejection,
            'completion': {'scenes': deepcopy(completion['result']['scenes']), 'receipt': deepcopy(receipt)},
            'dispatch.claim': claim}
        return completion, prepared, audit

    def test_only_two_ai_discussions_and_verified_speech_audio_are_accepted(self):
        completion, prepared = self.fixture()
        before = deepcopy(completion)
        self.assertEqual(validate_learner_discussion_repair(completion, prepared),
                         completion['learnerDiscussionRepair']['receiptSha256'])
        self.assertEqual(completion, before, 'validation must not mutate the signed completion')

    def test_missing_frozen_input_or_receipt_and_unknown_fields_are_rejected(self):
        for case in ('missing_input', 'null_receipt', 'extra_field', 'unsigned_change'):
            completion, prepared = self.fixture()
            with self.subTest(case=case), self.assertRaises(ValueError):
                if case == 'missing_input': prepared = None
                if case == 'null_receipt': completion['learnerDiscussionRepair'] = None
                if case == 'extra_field':
                    completion['learnerDiscussionRepair']['generatedPass'] = True
                    self.resign(completion)
                if case == 'unsigned_change': completion['learnerDiscussionRepair']['repairReference'] = '3' * 64
                validate_learner_discussion_repair(completion, prepared)

    def test_rehashed_provenance_identity_drift_is_rejected(self):
        for key, value in (('inputSnapshotSha256', '3' * 64), ('sourceSnapshotSha256', '3' * 64),
                           ('sessionId', 'different'), ('stageId', 'different'),
                           ('namespace', 'session-1:creator'), ('providerId', 'other'),
                           ('modelId', 'deepseek-v4-pro'), ('providerRequestIdHash', 'request-1'),
                           ('repairReference', 'not-a-digest')):
            completion, prepared = self.fixture()
            receipt = completion['learnerDiscussionRepair']
            receipt[key] = value
            self.resign(completion)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared)

    def test_rehashed_changes_to_html_narration_quiz_or_scene_order_are_rejected(self):
        for case in ('html', 'narration', 'quiz', 'title', 'order', 'extra_action', 'extra_scene'):
            completion, prepared = self.fixture()
            scenes = completion['result']['scenes']
            if case == 'html': scenes[2]['content']['html'] += '<button>Added game</button>'
            if case == 'narration': scenes[3]['actions'][0]['text'] += 'new answer'
            if case == 'quiz': scenes[6]['content']['questions'][0]['answer'] = '1/2'
            if case == 'title': scenes[4]['title'] = 'A changed page'
            if case == 'order': scenes[3]['order'], scenes[4]['order'] = scenes[4]['order'], scenes[3]['order']
            if case == 'extra_action': scenes[2]['actions'].append({'id': 'new', 'type': 'speech', 'text': 'new'})
            if case == 'extra_scene': scenes.append({**deepcopy(scenes[3]), 'id': 'scene-extra', 'order': 8})
            self.resign(completion)
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared)

    def test_rehashed_wrong_discussion_positions_and_action_shapes_are_rejected(self):
        for case in ('reverse', 'wrong_count_type', 'prepend', 'third_discussion', 'wrong_type',
                     'extra_action_field', 'duplicate_id', 'existing_id', 'different_final_action'):
            completion, prepared = self.fixture()
            receipt = completion['learnerDiscussionRepair']
            if case == 'reverse': receipt['insertions'].reverse()
            if case == 'wrong_count_type': receipt['insertions'][0]['afterActionCount'] = True
            if case == 'prepend': completion['result']['scenes'][0]['actions'].reverse()
            if case == 'third_discussion': receipt['insertions'].append(deepcopy(receipt['insertions'][0]))
            if case == 'wrong_type': receipt['insertions'][0]['action']['type'] = 'speech'
            if case == 'extra_action_field': receipt['insertions'][0]['action']['answer'] = '60%'
            if case in ('duplicate_id', 'existing_id'):
                changed_id = receipt['insertions'][0]['action']['id'] if case == 'duplicate_id' else 'speech-7'
                receipt['insertions'][1]['action']['id'] = changed_id
                completion['result']['scenes'][7]['actions'][-1]['id'] = changed_id
            if case == 'different_final_action': completion['result']['scenes'][0]['actions'][-1]['prompt'] = 'Another prompt'
            self.resign(completion)
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared)

    def test_repair_cannot_add_a_second_discussion_to_an_existing_discussion_page(self):
        completion, prepared = self.fixture()
        old = {'id': 'old-discussion', 'type': 'discussion', 'topic': 'Old', 'prompt': 'Old', 'agentId': 'teacher-1'}
        prepared['scenes'][0]['actions'].append(old)
        completion['result']['scenes'][0]['actions'].insert(1, deepcopy(old))
        completion['repairSnapshotSha256'] = quality_sha(prepared)
        completion['learnerDiscussionRepair']['inputSnapshotSha256'] = quality_sha(prepared)
        completion['learnerDiscussionRepair']['insertions'][0]['afterActionCount'] = 2
        self.resign(completion)
        with self.assertRaises(ValueError):
            validate_learner_discussion_repair(completion, prepared)

    def test_teacher_must_be_the_unique_actual_stage_teacher(self):
        for case in ('missing_roster', 'multiple_teachers', 'not_in_agent_ids', 'discussion_uses_peer'):
            completion, prepared = self.fixture()
            stage = completion['result']['stage']
            if case == 'missing_roster': stage.pop('generatedAgentConfigs')
            if case == 'multiple_teachers': stage['generatedAgentConfigs'][1]['role'] = 'teacher'
            if case == 'not_in_agent_ids': stage['agentIds'].remove('teacher-1')
            if case == 'discussion_uses_peer':
                completion['learnerDiscussionRepair']['insertions'][0]['action']['agentId'] = 'peer-1'
                completion['result']['scenes'][0]['actions'][-1]['agentId'] = 'peer-1'
            self.resign(completion)
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared)

    def test_exact_native_provider_audit_and_final_quality_context_are_accepted(self):
        completion, prepared, audit = self.audit_fixture()
        self.assertEqual(validate_learner_discussion_repair(completion, prepared, repair_audit=audit),
                         completion['learnerDiscussionRepair']['receiptSha256'])

    def test_native_provider_audit_and_final_quality_drift_are_rejected(self):
        for case in ('missing_file', 'frozen_context', 'source_scene', 'raw_response', 'provider_request',
                     'rejected_review', 'dispatch_grant', 'derived_scene', 'derived_receipt',
                     'final_review_context', 'final_review_full_plan_hash', 'final_review_snapshot'):
            completion, prepared, audit = self.audit_fixture()
            if case == 'missing_file': audit.pop('provider-response')
            if case == 'frozen_context': audit['input']['frozenContext']['teachingBrief']['goal'] = 'Another goal'
            if case == 'source_scene': audit['input']['sourceScenes'][3]['actions'][0]['text'] = 'Different speech'
            if case == 'raw_response': audit['provider-response']['providerRequestIdHash'] = '3' * 64
            if case == 'provider_request': audit['request']['phase'] = 'create_game'
            if case == 'rejected_review': audit['rejected-review']['status'] = 'passed'
            if case == 'dispatch_grant': audit['dispatch.claim']['authorizationId'] = '3' * 64
            if case == 'derived_scene': audit['completion']['scenes'][2]['content']['html'] = '<p>Edited</p>'
            if case == 'derived_receipt': audit['completion']['receipt']['repairReference'] = '3' * 64
            if case == 'final_review_context':
                completion['result']['professionalCreation']['teachingQuality']['selectionPlanSha256'] = '3' * 64
            if case == 'final_review_full_plan_hash':
                completion['result']['professionalCreation']['teachingQuality']['selectionPlanSha256'] = quality_sha(
                    audit['input']['frozenContext']['selectionPlan'])
            if case == 'final_review_snapshot':
                completion['result']['professionalCreation']['teachingQuality']['snapshotSha256'] = '3' * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared, repair_audit=audit)

    def test_rehashed_provider_output_and_prompt_cannot_change_frozen_provenance(self):
        for case in ('generated_action', 'prompt_context'):
            completion, prepared, audit = self.audit_fixture()
            if case == 'generated_action':
                generated = json.loads(audit['provider-response']['content'])
                generated['insertions'][0]['action']['prompt'] = 'Unrelated task'
                audit['provider-response']['content'] = json.dumps(generated)
                completion['learnerDiscussionRepair']['providerResponseSha256'] = quality_sha(audit['provider-response'])
            else:
                prompt = json.loads(audit['request']['userPrompt'])
                prompt['teachingBrief'] = {'goal': 'Another task'}
                audit['request']['userPrompt'] = json.dumps(prompt)
                completion['learnerDiscussionRepair']['requestSha256'] = quality_sha(audit['request'])
                audit['dispatch.claim']['requestSha256'] = quality_sha(audit['request'])
            self.resign(completion)
            audit['completion']['receipt'] = deepcopy(completion['learnerDiscussionRepair'])
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_learner_discussion_repair(completion, prepared, repair_audit=audit)


if __name__ == '__main__':
    unittest.main()
