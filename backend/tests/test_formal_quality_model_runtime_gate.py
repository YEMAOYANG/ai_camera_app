"""Execute the actual student QA SQL predicate against isolated JSON fixtures."""
from copy import deepcopy
import json
import re
import sqlite3
import unittest

from integrations.openmaic_formal_media import (
    FLASH_CANDIDATE_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
    PROFESSIONAL_POLICY, PRO_CURRENT_FLASH_PROFESSIONAL_POLICY,
    PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY, REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY,
    canonical_sha256,
)
from repositories.formal_student_runtime_gate import (
    _adaptive_skill_quality_sql, current_formal_runtime_sql,
)
from tests.test_openmaic_formal_quality import adaptive_quality_fixture


def _json_extract(value, path):
    if value is None:
        return None
    value = json.loads(value)
    if path != '$':
        for field in path[2:].split('.'):
            if not isinstance(value, dict) or field not in value:
                return None
            value = value[field]
    # Typed canonical JSON preserves MySQL JSON object equality, including the
    # difference between true and 1. A missing path is SQL NULL; JSON null is not.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _json_unquote(value):
    if value is None:
        return None
    parsed = json.loads(value)
    return parsed if isinstance(parsed, str) else value


def _json_length(value):
    if value is None:
        return None
    parsed = json.loads(value)
    return len(parsed) if isinstance(parsed, (dict, list)) else 1


def _json_type(value):
    if value is None:
        return None
    parsed = json.loads(value)
    if isinstance(parsed, dict): return 'OBJECT'
    if isinstance(parsed, list): return 'ARRAY'
    if isinstance(parsed, str): return 'STRING'
    if parsed is None: return 'NULL'
    if type(parsed) is bool: return 'BOOLEAN'
    return 'INTEGER' if type(parsed) is int else 'DOUBLE'


def _unsigned(raw):  # migrations/103 mysql_unsigned
    if raw is None:
        return None
    digits = re.match(r"\s*\+?([0-9]+)", str(raw))
    return int(digits.group(1)) if digits else 0


class FormalQualityModelRuntimeGateTest(unittest.TestCase):
    def setUp(self):
        # No server, disk DB, network or Provider. The production predicate is
        # executed rather than asserting that a model name occurs in its text.
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        for name, fn, argc in (
            ('JSON_EXTRACT', _json_extract, 2), ('JSON_UNQUOTE', _json_unquote, 1),
            ('JSON_LENGTH', _json_length, 1), ('JSON_TYPE', _json_type, 1),
            ('REGEXP', lambda pattern, value: value is not None and re.search(pattern, str(value)) is not None, 2),
            ('mysql_unsigned', _unsigned, 1),
        ):
            self.conn.create_function(name, argc, fn)
        self.conn.execute('CREATE TABLE runtime(feature_manifest_json TEXT, upstream_classroom_id TEXT)')
        self.gate_sql = _adaptive_skill_quality_sql('runtime')
        # SQLite spells PostgreSQL's regex match operators as REGEXP.
        self.predicate = self.gate_sql.replace(' ~* ', ' REGEXP ').replace(' ~ ', ' REGEXP ')

    def fixture(self, policy=PROFESSIONAL_POLICY):
        row, _ = adaptive_quality_fixture()
        manifest = row['feature_manifest_json']
        manifest['generationContract']['professionalCreationPolicy'] = deepcopy(policy)
        professional = manifest['professionalCreation']
        for key in ('modelPolicyId', 'sceneLearningPolicy'):
            professional.pop(key, None)
            if key in policy:
                professional[key] = deepcopy(policy[key])
        professional['teachingQuality']['review']['modelId'] = (
            'deepseek-flash' if 'modelPolicyId' in policy else 'deepseek-v4-flash')
        self.resign(manifest)
        return manifest

    def resign(self, manifest):
        professional = manifest['professionalCreation']
        quality = professional['teachingQuality']
        quality['receiptSha256'] = canonical_sha256({k: v for k, v in quality.items() if k != 'receiptSha256'})
        professional['receiptSha256'] = canonical_sha256({k: v for k, v in professional.items() if k != 'receiptSha256'})
        evidence = manifest['formalEvidence']
        evidence['professionalCreation'].update(teachingQuality=deepcopy(quality), receiptSha256=professional['receiptSha256'])
        evidence['teachingQuality'].update(receiptSha256=quality['receiptSha256'])

    def allows(self, manifest):
        self.conn.execute('DELETE FROM runtime')
        self.conn.execute('INSERT INTO runtime VALUES(?,?)',
            (json.dumps(manifest), manifest['professionalCreation']['classroomId']))
        return bool(self.conn.execute(f'SELECT CASE WHEN {self.predicate} THEN 1 ELSE 0 END FROM runtime').fetchone()[0])

    def test_old_new_and_candidate_receipts_use_their_own_frozen_contract(self):
        for policy in (PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
            REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY, PRO_CURRENT_FLASH_PROFESSIONAL_POLICY,
            PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY, FLASH_CANDIDATE_PROFESSIONAL_POLICY):
            with self.subTest(policy=policy.get('modelPolicyId', 'legacy')):
                self.assertTrue(self.allows(self.fixture(policy)))
        self.assertIn(self.gate_sql, current_formal_runtime_sql(runtime_alias='runtime'))

    def test_model_name_cannot_cross_old_new_or_candidate_identity(self):
        for policy in (PROFESSIONAL_POLICY, PRO_CURRENT_FLASH_PROFESSIONAL_POLICY,
                       FLASH_CANDIDATE_PROFESSIONAL_POLICY):
            manifest = self.fixture(policy)
            manifest['professionalCreation']['teachingQuality']['review']['modelId'] = (
                'deepseek-v4-flash' if 'modelPolicyId' in policy else 'deepseek-flash')
            self.resign(manifest)
            with self.subTest(policy=policy.get('modelPolicyId', 'legacy')):
                self.assertFalse(self.allows(manifest))

    def test_rehashed_policy_drift_unknown_fields_and_typed_values_fail_closed(self):
        for case in ('unknown', 'changed_creator_skill', 'bool_as_int', 'wrong_id', 'mixed_candidate', 'only_id'):
            manifest = self.fixture(PRO_CURRENT_FLASH_PROFESSIONAL_POLICY)
            policy = manifest['generationContract']['professionalCreationPolicy']
            if case == 'unknown': policy['safeFallback'] = True
            if case == 'changed_creator_skill': policy['supportingSkillIds'] = []
            if case == 'bool_as_int': policy['userPromptRequired'] = 0
            if case == 'wrong_id': policy['modelPolicyId'] = 'deepseek-v4.1-flash-candidate-v1'
            if case == 'mixed_candidate': policy['sceneLearningPolicy'] = deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY['sceneLearningPolicy'])
            if case == 'only_id': manifest['generationContract']['professionalCreationPolicy'] = {'modelPolicyId': policy['modelPolicyId']}
            self.resign(manifest)
            with self.subTest(case=case): self.assertFalse(self.allows(manifest))

    def test_raw_receipt_identity_must_match_the_exact_creation_policy(self):
        for case in ('missing', 'null', 'wrong', 'extra_scene_policy', 'missing_candidate_scene', 'changed_candidate_scene'):
            candidate = case.startswith('missing_candidate') or case.startswith('changed_candidate')
            manifest = self.fixture(FLASH_CANDIDATE_PROFESSIONAL_POLICY if candidate else PRO_CURRENT_FLASH_PROFESSIONAL_POLICY)
            professional = manifest['professionalCreation']
            if case == 'missing': professional.pop('modelPolicyId')
            if case == 'null': professional['modelPolicyId'] = None
            if case == 'wrong': professional['modelPolicyId'] = 'deepseek-v4.1-flash-candidate-v1'
            if case == 'extra_scene_policy': professional['sceneLearningPolicy'] = deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY['sceneLearningPolicy'])
            if case == 'missing_candidate_scene': professional.pop('sceneLearningPolicy')
            if case == 'changed_candidate_scene': professional['sceneLearningPolicy']['scriptSyntaxRequired'] = False
            self.resign(manifest)
            with self.subTest(case=case): self.assertFalse(self.allows(manifest))
        # A legacy receipt may not acquire an identity, even with an updated hash.
        manifest = self.fixture()
        manifest['professionalCreation']['modelPolicyId'] = PRO_CURRENT_FLASH_PROFESSIONAL_POLICY['modelPolicyId']
        self.resign(manifest)
        self.assertFalse(self.allows(manifest))

    def test_existing_parent_and_quality_audit_hashes_still_bind_new_receipts(self):
        for case in ('parent', 'quality_parent_copy', 'quality_audit', 'snapshot'):
            manifest = self.fixture(PRO_CURRENT_FLASH_PROFESSIONAL_POLICY)
            evidence = manifest['formalEvidence']
            if case == 'parent': evidence['professionalCreation']['receiptSha256'] = 'f' * 64
            if case == 'quality_parent_copy': evidence['professionalCreation']['teachingQuality']['receiptSha256'] = 'f' * 64
            if case == 'quality_audit': evidence['teachingQuality']['receiptSha256'] = 'f' * 64
            if case == 'snapshot': evidence['teachingQuality']['snapshotSha256'] = 'f' * 64
            with self.subTest(case=case): self.assertFalse(self.allows(manifest))


if __name__ == '__main__': unittest.main()
