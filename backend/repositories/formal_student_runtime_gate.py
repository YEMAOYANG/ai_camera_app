from __future__ import annotations

import json
import re


CURRENT_RUNTIME_MANIFEST_SCHEMA = "mira.openmaic.runtime-features.v2"
CURRENT_RUNTIME_SOURCE_VERSION = "openmaic@1.0.0"
CURRENT_RUNTIME_SOURCE_COMMIT = "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5"
CURRENT_RUNTIME_CONTRACT_VERSION = (
    "mira.openmaic.formal-runtime.v4-deepseek-professional"
)
CURRENT_RUNTIME_BINDING_CONTRACT_VERSION = (
    "mira.learning.candidate-runtime-binding.v1"
)
CURRENT_COURSEWARE_AUTHORITY_SCHEMA = (
    "mira.openmaic.courseware-authority.v2-professional"
)
CURRENT_PROFESSIONAL_POLICY_SCHEMA = "mira.openmaic.professional-creation.v1"
CURRENT_PROFESSIONAL_RECEIPT_SCHEMA = (
    "mira.openmaic.professional-creation-receipt.v1"
)
CURRENT_RESEARCH_RECEIPT_SCHEMA = (
    "mira.openmaic.professional-research-receipt.v1"
)
CURRENT_ARTIFACT_PUBLICATION_CONTRACT_VERSION = (
    "mira.learning.formal-artifact-publication.v1"
)


def with_parsed_runtime_manifests(query: str) -> str:
    """Parse each Runtime manifest once within a single student read query.

    The stored manifest is LONGTEXT. Repeated JSON_EXTRACT predicates otherwise
    reparse the entire classroom for every expression, row and gate branch.
    A non-mergeable CTE materializes MySQL's binary JSON representation while
    retaining every existing predicate and identity column. Every caller already
    excludes retired runtimes in its joins, so do not parse historical manifests.
    It is not a cache:
    every request still reads current publication, retirement and asset state.
    Invalid manifests remain NULL and fail the existing JSON_VALID gate.
    """
    relation = 'student_runtime_manifests'
    rewritten, count = re.subn(r'\blearning_openmaic_runtime_classrooms\s+AS\s+',
                               relation + ' AS ', query)
    if not count or re.match(r'\s*SELECT\b', query, re.IGNORECASE) is None:
        raise ValueError('parsed Runtime manifests require a student SELECT with Runtime aliases')
    return f"""WITH {relation} AS (
      SELECT id, candidate_binding_contract_version, candidate_build_item_id,
        candidate_grade_code, candidate_release_id, candidate_target_fingerprint,
        course_id, course_version, package_id, package_version, quality_status,
        request_id, retired_at, status, upstream_classroom_id,
        CAST(IF(JSON_VALID(feature_manifest_json), feature_manifest_json, NULL) AS JSON)
          AS feature_manifest_json
      FROM learning_openmaic_runtime_classrooms
      WHERE retired_at IS NULL
      LIMIT 18446744073709551615
    ) {rewritten}"""


def _formal_video_sql(alias: str) -> str:
    """Require the new video receipt while preserving image-only classrooms."""
    def raw(key: str) -> str:
        return f"JSON_EXTRACT({alias}.feature_manifest_json, '$.{key}')"
    def text(key: str) -> str:
        return f"JSON_UNQUOTE({raw(key)})"
    absent = " AND ".join(f"{raw(key)} IS NULL" for key in (
        "generationContract.professionalCreationPolicy.video", "professionalCreation.videoGenerationEnabled",
        "professionalCreation.videoPolicyId", "video", "formalEvidence.video"))
    checks = [
        f"{text('generationContract.professionalCreationPolicy.video.policyId')} = 'mira-formal-happyhorse-video.v1'",
        f"{text('generationContract.generation.enableVideoGeneration')} = 'true'",
        f"{text('professionalCreation.videoGenerationEnabled')} = 'true'",
        f"{text('professionalCreation.videoPolicyId')} = 'mira-formal-happyhorse-video.v1'",
        f"{text('video.schemaVersion')} = 'mira.openmaic.formal-video-receipt.v1'",
        f"{text('video.status')} = 'succeeded'",
        f"{text('video.policyId')} = 'mira-formal-happyhorse-video.v1'",
        f"{text('video.providerId')} = 'happyhorse'",
        f"{text('video.modelId')} = 'happyhorse-1.0-t2v'",
        f"{text('video.runtimeRequestId')} = {alias}.request_id",
        f"{text('video.buildItemId')} = {alias}.candidate_build_item_id",
        f"{text('video.classroomId')} = {alias}.upstream_classroom_id",
        f"{text('video.sessionId')} = {text('professionalCreation.sessionId')}",
        f"{text('video.receiptSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text('formalEvidence.video.verified')} = 'true'",
        f"{text('formalEvidence.video.receiptSha256')} = {text('video.receiptSha256')}",
        f"JSON_TYPE({raw('video.assets')}) = 'ARRAY'",
        f"JSON_TYPE({raw('video.videoCount')}) = 'INTEGER'",
        f"JSON_LENGTH({raw('video.assets')}) BETWEEN 0 AND 1",
        f"CAST({text('video.videoCount')} AS UNSIGNED) = JSON_LENGTH({raw('video.assets')})",
        f"CAST({text('formalEvidence.video.verifiedAssetCount')} AS UNSIGNED) = JSON_LENGTH({raw('video.assets')})",
    ]
    return f"(({absent}) OR ({' AND '.join(checks)}))"


def _formal_quality_model_sql(alias: str) -> str:
    """Bind QA to a complete frozen creation identity, not a model-name allowlist.

    The complete model policy is already locked by the callers' preparation
    target/fingerprint joins. Runtime receipts carry its versioned creation
    identity; legacy receipts intentionally have neither new identity field.
    Their original hashes and old reviewer must remain unchanged.
    """
    from integrations.openmaic_formal_media import (
        PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY, INTERACTIVE_PROFESSIONAL_POLICY,
        MULTISTATE_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
        REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY, FLASH_CANDIDATE_PROFESSIONAL_POLICY,
        PRO_CURRENT_FLASH_PROFESSIONAL_POLICY, PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY,
    )

    def raw(path: str) -> str:
        return f"JSON_EXTRACT({alias}.feature_manifest_json, '$.{path}')"

    def text(path: str) -> str:
        return f"JSON_UNQUOTE({raw(path)})"

    def frozen(value: object) -> str:
        # These are registry constants, never user-supplied SQL. JSON equality
        # compares the entire object (including types/unknown keys), unlike
        # JSON_CONTAINS or a handful of policy fields.
        value_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        escaped = value_json.replace("\\", "\\\\").replace("'", "''")
        return f"JSON_EXTRACT('{escaped}', '$')"

    policy = raw("generationContract.professionalCreationPolicy")
    model_id = text("professionalCreation.modelPolicyId")
    scene_policy = raw("professionalCreation.sceneLearningPolicy")
    reviewer = text("professionalCreation.teachingQuality.review.modelId")
    legacy = (PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY, INTERACTIVE_PROFESSIONAL_POLICY,
              MULTISTATE_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
              REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY)
    legacy_branch = " AND ".join([
        "(" + " OR ".join(f"{policy} = {frozen(value)}" for value in legacy) + ")",
        f"{raw('professionalCreation.modelPolicyId')} IS NULL",
        f"{scene_policy} IS NULL",
        f"{reviewer} = 'deepseek-v4-flash'",
    ])
    current_branch = " AND ".join([
        "(" + " OR ".join(f"{policy} = {frozen(value)}" for value in
            (PRO_CURRENT_FLASH_PROFESSIONAL_POLICY, PRO_CURRENT_FLASH_3D_PROFESSIONAL_POLICY)) + ")",
        f"{model_id} = 'deepseek-v4-pro-current-flash-v1'",
        f"{scene_policy} IS NULL",
        f"{reviewer} = 'deepseek-flash'",
    ])
    candidate_branch = " AND ".join([
        f"{policy} = {frozen(FLASH_CANDIDATE_PROFESSIONAL_POLICY)}",
        f"{model_id} = 'deepseek-v4.1-flash-candidate-v1'",
        f"{scene_policy} = {frozen(FLASH_CANDIDATE_PROFESSIONAL_POLICY['sceneLearningPolicy'])}",
        f"{reviewer} = 'deepseek-flash'",
    ])
    # The audit projection omits modelPolicyId but locks the entire raw parent
    # receipt by SHA. Do not invent a new historical audit field/hash.
    return "(" + " AND ".join([
        f"{text('professionalCreation.receiptSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text('professionalCreation.receiptSha256')} = {text('formalEvidence.professionalCreation.receiptSha256')}",
        f"(({legacy_branch}) OR ({current_branch}) OR ({candidate_branch}))",
    ]) + ")"


def _adaptive_skill_quality_sql(alias: str) -> str:
    """Early fail-closed visibility gate; Python checks exact nested receipts."""

    def text(path: str) -> str:
        return f"JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json, '$.{path}'))"
    def count(path: str) -> str:
        return f"JSON_LENGTH(JSON_EXTRACT({alias}.feature_manifest_json, '$.{path}'))"
    skill = "professionalCreation.skillOrchestration"
    plan = skill + ".selectionPlan"
    quality = "professionalCreation.teachingQuality"
    scene_count = f"CAST({text('sceneCount')} AS UNSIGNED)"
    conditions = [
        f"{text('generationContract.professionalCreationPolicy.skillOrchestration.schemaVersion')} = 'mira.openmaic.skill-orchestration.v2'",
        f"{text('generationContract.professionalCreationPolicy.skillOrchestration.profileId')} = 'mira-primary-adaptive.v2'",
        f"{text('generationContract.professionalCreationPolicy.teachingQuality.policyId')} = 'mira-primary-quality.v1'",
        f"{text(skill + '.schemaVersion')} = 'mira.openmaic.skill-orchestration-receipt.v2'",
        f"{text(skill + '.profileId')} = 'mira-primary-adaptive.v2'",
        f"{text(skill + '.status')} = 'succeeded'",
        f"{text(skill + '.receiptSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text(skill + '.receiptSha256')} = {text('formalEvidence.' + skill + '.receiptSha256')}",
        f"{count(skill + '.skillReads')} BETWEEN 7 AND 23",
        f"{count(skill + '.skillReads')} = {count(plan + '.selectedSkillIds')}",
        f"{count(skill + '.referenceReads')} = 2",
        f"{count(skill + '.sceneContexts')} = {scene_count}",
        f"{count(plan + '.decisions')} = 23",
        f"{text(plan + '.planSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text('generationContract.gradeBoundarySha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"JSON_TYPE(JSON_EXTRACT({alias}.feature_manifest_json, '$.generationContract.gradeBoundary')) = 'OBJECT'",
        f"{text(plan + '.gradeBoundarySha256')} = {text('generationContract.gradeBoundarySha256')}",
        f"{text(quality + '.schemaVersion')} = 'mira.openmaic.teaching-quality-receipt.v1'",
        f"{text(quality + '.policyId')} = 'mira-primary-quality.v1'",
        f"{text(quality + '.status')} = 'passed'",
        f"{text(quality + '.sessionId')} = {text('professionalCreation.sessionId')}",
        f"{text(quality + '.stageId')} = {alias}.upstream_classroom_id",
        f"{text(quality + '.gradeBoundarySha256')} = {text('generationContract.gradeBoundarySha256')}",
        f"{text(quality + '.selectionPlanSha256')} = {text(plan + '.planSha256')}",
        f"{text(quality + '.teachingBriefSha256')} = {text('generationContract.teachingBriefSha256')}",
        f"{text(quality + '.snapshotSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text(quality + '.receiptSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text(quality + '.receiptSha256')} = {text('formalEvidence.' + quality + '.receiptSha256')}",
        f"{text(quality + '.receiptSha256')} = {text('formalEvidence.teachingQuality.receiptSha256')}",
        f"{text(quality + '.snapshotSha256')} = {text('formalEvidence.teachingQuality.snapshotSha256')}",
        f"{text('formalEvidence.teachingQuality.verified')} = 'true'",
        f"{count(quality + '.sceneHashes')} = {scene_count}",
        f"{count('formalEvidence.teachingQuality.sceneHashes')} = {scene_count}",
        f"{count(quality + '.renderChecks')} = 2 * {scene_count}",
        f"{text(quality + '.review.providerId')} = 'deepseek'",
        _formal_quality_model_sql(alias),
        f"{text(quality + '.review.inputSha256')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{text(quality + '.review.requestIdHash')} REGEXP '^[0-9a-f]{{64}}$'",
        f"{count(quality + '.review.dimensions')} = 7",
        f"{count(quality + '.review.objectives')} = {count('generationContract.gradeBoundary.learningObjectives')}",
    ]
    return " AND ".join(conditions)


def current_formal_validation_authority_sql(
    *, receipt_alias: str, provider_alias: str
) -> str:
    """Accept either real artifact receipts or the legacy five-call probe.

    New professional classrooms already carry immutable OpenMAIC creation,
    research, classroom and audio receipts.  Their local publication receipt
    is identified by ``auto_validation_contract_version`` and does not require
    another paid Provider-readiness run.  The second branch intentionally
    preserves historical releases that used the five-call readiness contract.
    """

    receipt = str(receipt_alias or "").strip()
    provider = str(provider_alias or "").strip()
    for alias in (receipt, provider):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) is None:
            raise ValueError("invalid formal validation SQL alias")
    return f"""
      AND (
        (
          {receipt}.conversation_provider_status = 'passed'
          AND {receipt}.conversation_provider_receipt_hash
            REGEXP '^[0-9a-f]{{64}}$'
          AND {receipt}.auto_validated = 1
          AND {receipt}.auto_validation_contract_version =
            '{CURRENT_ARTIFACT_PUBLICATION_CONTRACT_VERSION}'
          AND {receipt}.auto_validation_receipt_hash
            REGEXP '^[0-9a-f]{{64}}$'
        )
        OR (
          {provider}.state = 'auto_validated'
          AND {provider}.expected_provider_call_count = 5
          AND {provider}.provider_attempted_count = 5
          AND {provider}.provider_passed_count = 5
          AND {provider}.provider_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
          AND {provider}.route_session_provider_call = 0
          AND {provider}.route_session_status = 'passed'
        )
      )
    """


def current_formal_runtime_sql(*, runtime_alias: str) -> str:
    """Return the shared SQL gate for a currently launchable formal Runtime.

    Publication/audio/provider rows prove that a classroom completed its
    release pipeline.  They do not, by themselves, distinguish a classroom
    produced by an older OpenMAIC contract.  This predicate binds student
    discovery, package selection and session binding to the same immutable
    OpenMAIC 1.0 professional + web-search authority consumed by launch.

    The launch service still performs the complete structural and receipt-hash
    validation.  This gate is the earlier fail-closed identity boundary that
    prevents a legacy runtime from being advertised as launchable.
    """

    alias = str(runtime_alias or "").strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) is None:
        raise ValueError("invalid runtime SQL alias")
    return f"""
      AND {alias}.candidate_binding_contract_version =
        '{CURRENT_RUNTIME_BINDING_CONTRACT_VERSION}'
      AND {alias}.quality_status IN ('pending_review', 'approved')
      AND JSON_VALID({alias}.feature_manifest_json)
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.schemaVersion'
      )) = '{CURRENT_RUNTIME_MANIFEST_SCHEMA}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.sourceVersion'
      )) = '{CURRENT_RUNTIME_SOURCE_VERSION}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.sourceCommit'
      )) = '{CURRENT_RUNTIME_SOURCE_COMMIT}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.generationContract.schemaVersion'
      )) = '{CURRENT_RUNTIME_CONTRACT_VERSION}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.formalRuntimeContract.schemaVersion'
      )) = '{CURRENT_RUNTIME_CONTRACT_VERSION}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.requiredClassroom.schemaVersion'
      )) = '{CURRENT_RUNTIME_CONTRACT_VERSION}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.generationContract.authority'
      )) = 'mira_backend_formal_candidate'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.generationContract.buildItemId'
      )) = {alias}.candidate_build_item_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.generationContract.targetFingerprint'
      )) = {alias}.candidate_target_fingerprint
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.generationContract.runtimeRequestId'
      )) = {alias}.request_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.course.id'
      )) = {alias}.course_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.course.version'
      )) = {alias}.course_version
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.course.packageId'
      )) = {alias}.package_id
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.course.packageVersion'
      )) AS UNSIGNED) = {alias}.package_version
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.coursewareAuthority.schemaVersion'
      )) = '{CURRENT_COURSEWARE_AUTHORITY_SCHEMA}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.coursewareAuthority.generationOwner'
      )) = 'openmaic'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.coursewareAuthority.providerInvocation'
      )) = 'professional_agent'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.coursewareAuthority.classroomCompilation'
      )) = 'professional_skill_workflow'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.professionalCreationPolicy.schemaVersion'
      )) = '{CURRENT_PROFESSIONAL_POLICY_SCHEMA}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.professionalCreationPolicy.mode'
      )) = 'professional_skill'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.professionalCreationPolicy.webSearch.enabled'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.professionalCreationPolicy.webSearch.citationsRequired'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.generation.mode'
      )) = 'professional_skill'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.generation.enableWebSearch'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.generation.webSearchRequired'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.generationContract.generation.providerInvocation'
      )) = 'openmaic_agent_managed'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.schemaVersion'
      )) = '{CURRENT_PROFESSIONAL_RECEIPT_SCHEMA}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.status'
      )) = 'succeeded'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.runtimeRequestId'
      )) = {alias}.request_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.buildItemId'
      )) = {alias}.candidate_build_item_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.classroomId'
      )) = {alias}.upstream_classroom_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.webSearchEnabled'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.receiptSha256'
      )) REGEXP '^[0-9a-f]{{64}}$'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.schemaVersion'
      )) = '{CURRENT_RESEARCH_RECEIPT_SCHEMA}'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.status'
      )) = 'succeeded'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.runtimeRequestId'
      )) = {alias}.request_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.buildItemId'
      )) = {alias}.candidate_build_item_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.classroomId'
      )) = {alias}.upstream_classroom_id
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.providerId'
      )) REGEXP '^[A-Za-z0-9_-]{{1,64}}$'
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.searchCount'
      )) AS UNSIGNED) >= 1
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.fetchedSourceCount'
      )) AS UNSIGNED) >= 1
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.citationCount'
      )) AS UNSIGNED) >= 1
      AND (
        (
          JSON_EXTRACT({alias}.feature_manifest_json,
            '$.generationContract.professionalCreationPolicy.image') IS NULL
          AND JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.imageGenerationEnabled') IS NULL
          AND JSON_EXTRACT({alias}.feature_manifest_json, '$.media') IS NULL
        )
        OR (
          JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.generationContract.professionalCreationPolicy.image.policyId')) = 'mira-formal-qwen-image.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.generationContract.generation.enableImageGeneration')) = 'true'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.imageGenerationEnabled')) = 'true'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.imagePolicyId')) = 'mira-formal-qwen-image.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.schemaVersion')) = 'mira.openmaic.formal-media-receipt.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.status')) = 'succeeded'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.runtimeRequestId')) = {alias}.request_id
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.buildItemId')) = {alias}.candidate_build_item_id
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.classroomId')) = {alias}.upstream_classroom_id
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.sessionId')) = JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.sessionId'))
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.receiptSha256')) REGEXP '^[0-9a-f]{{64}}$'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.formalEvidence.media.verified')) = 'true'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.formalEvidence.media.receiptSha256')) = JSON_UNQUOTE(JSON_EXTRACT(
            {alias}.feature_manifest_json, '$.media.receiptSha256'))
          AND CAST(JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.media.imageCount')) AS UNSIGNED) = JSON_LENGTH(JSON_EXTRACT(
            {alias}.feature_manifest_json, '$.media.assets'))
        )
      )
      AND {_formal_video_sql(alias)}
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.formalEvidence.professionalCreation.verified'
      )) = 'true'
      AND (
        (
          JSON_EXTRACT({alias}.feature_manifest_json,
            '$.generationContract.professionalCreationPolicy.skillOrchestration') IS NULL
          AND JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration') IS NULL
        )
        OR (
          JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.generationContract.professionalCreationPolicy.skillOrchestration.profileId')) = 'mira-primary-integrated.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.schemaVersion')) = 'mira.openmaic.skill-orchestration-receipt.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.profileId')) = 'mira-primary-integrated.v1'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.status')) = 'succeeded'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.receiptSha256')) REGEXP '^[0-9a-f]{{64}}$'
          AND JSON_UNQUOTE(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.formalEvidence.professionalCreation.skillOrchestration.receiptSha256')) = JSON_UNQUOTE(JSON_EXTRACT(
            {alias}.feature_manifest_json, '$.professionalCreation.skillOrchestration.receiptSha256'))
          AND JSON_LENGTH(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.skillReads')) = 6
          AND JSON_LENGTH(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.referenceReads')) = 2
          AND JSON_LENGTH(JSON_EXTRACT({alias}.feature_manifest_json,
            '$.professionalCreation.skillOrchestration.sceneContexts')) = CAST(JSON_UNQUOTE(JSON_EXTRACT(
            {alias}.feature_manifest_json, '$.sceneCount')) AS UNSIGNED)
        )
        OR ({_adaptive_skill_quality_sql(alias)})
      )
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.formalEvidence.professionalCreation.webSearchEnabled'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.formalEvidence.professionalCreation.receiptSha256'
      )) = JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.professionalCreation.receiptSha256'
      ))
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.formalEvidence.research.verified'
      )) = 'true'
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.formalEvidence.research.receiptSha256'
      )) = JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.receiptSha256'
      ))
      AND JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json,
        '$.formalEvidence.research.providerId'
      )) = JSON_UNQUOTE(JSON_EXTRACT(
        {alias}.feature_manifest_json, '$.research.providerId'
      ))
    """
