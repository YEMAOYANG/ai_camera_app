from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from content.formal_curriculum_registry import formal_content_contract, formal_registered_boundary
from integrations.openmaic_question_adapter import OpenMaicQuestionPhaseAdapter, _QUESTION_PHASE_SKILL_KEYS
from tests.test_openmaic_question_phase_adapter import _command

ROOT = Path(__file__).resolve().parents[2]


class MultigradePhaseBoundaryTest(unittest.TestCase):
    def requests(self):
        adapter = OpenMaicQuestionPhaseAdapter(provider_name='deepseek', model_name='deepseek-v4-pro', base_url='https://api.deepseek.com/v1')
        rows = []
        for number in range(2, 7):
            grade = f'primary_{number}'
            for subject in formal_content_contract(grade)['subjects']:
                for skill in subject['boundaries']:
                    raw = formal_registered_boundary(grade, subject['subject'], skill['skillId']).to_catalog_payload()
                    command = _command(grade_code=grade, subject=subject['subject'], target_language_code=subject['targetLanguageCode'],
                                       boundary={key: raw[key] for key in _QUESTION_PHASE_SKILL_KEYS})
                    rows.append(adapter.canonicalize_phase(command).request)
        return rows

    def test_all_45_boundaries_roundtrip_and_reject_policy_substitution(self):
        script = """
import {normalizeQuestionPhaseRequest,applyQuestionPhaseLanguageDirective} from './backend/openmaic-sidecar/src/question-contract.mjs';
let data=''; for await (const chunk of process.stdin) data+=chunk;
const rows=JSON.parse(data);
for (const row of rows) {
 const value=normalizeQuestionPhaseRequest(row);
 const prompt=applyQuestionPhaseLanguageDirective(value,{system:'Create a lesson',user:'Create practice'});
 if (!prompt.system.includes(value.objectivePolicy.promptPolicy)) throw Error('objective policy missing from prompt');
 for (const corrupt of [ {...row,gradeCode:'primary_7'}, {...row,objectivePolicy:{...row.objectivePolicy,closedAssessmentTypes:[]}} ]) {
  let rejected=false; try { normalizeQuestionPhaseRequest(corrupt); } catch { rejected=true; }
  if (!rejected) throw Error('forged grade policy accepted');
 }
}
process.stdout.write(String(rows.length));
"""
        result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                                input=json.dumps(self.requests(), ensure_ascii=False), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '45')

    def test_python_rejects_unregistered_boundary_before_dispatch(self):
        adapter = OpenMaicQuestionPhaseAdapter()
        with self.assertRaises(ValueError):
            adapter.canonicalize_phase(_command(grade_code='primary_2'))
