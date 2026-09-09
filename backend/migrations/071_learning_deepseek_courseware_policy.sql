-- Preserve immutable v1 Kimi readiness receipts while making every new v2
-- readiness receipt identify the server-owned DeepSeek professional policy.

SET @add_071_call_contract_version = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_provider_readiness_call_receipts ADD COLUMN provider_contract_version VARCHAR(128) NULL AFTER readiness_id',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_call_receipts'
    AND COLUMN_NAME = 'provider_contract_version'
);
PREPARE add_071_call_contract_version_stmt
  FROM @add_071_call_contract_version;
EXECUTE add_071_call_contract_version_stmt;
DEALLOCATE PREPARE add_071_call_contract_version_stmt;

UPDATE learning_openmaic_provider_readiness_call_receipts AS call_receipt
JOIN learning_openmaic_provider_readiness_jobs AS readiness
  ON readiness.id = call_receipt.readiness_id
SET call_receipt.provider_contract_version = readiness.provider_contract_version
WHERE call_receipt.provider_contract_version IS NULL;

SET @require_071_call_contract_version = (
  SELECT IF(COUNT(*) = 1 AND MAX(IS_NULLABLE) = 'YES',
    'ALTER TABLE learning_openmaic_provider_readiness_call_receipts MODIFY COLUMN provider_contract_version VARCHAR(128) NOT NULL AFTER readiness_id',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_call_receipts'
    AND COLUMN_NAME = 'provider_contract_version'
);
PREPARE require_071_call_contract_version_stmt
  FROM @require_071_call_contract_version;
EXECUTE require_071_call_contract_version_stmt;
DEALLOCATE PREPARE require_071_call_contract_version_stmt;

SET @add_071_job_contract_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_provider_readiness_jobs ADD UNIQUE INDEX uq_openmaic_provider_readiness_job_contract(id, provider_contract_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_jobs'
    AND INDEX_NAME = 'uq_openmaic_provider_readiness_job_contract'
);
PREPARE add_071_job_contract_index_stmt FROM @add_071_job_contract_index;
EXECUTE add_071_job_contract_index_stmt;
DEALLOCATE PREPARE add_071_job_contract_index_stmt;

SET @add_071_call_contract_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_provider_readiness_call_receipts ADD INDEX idx_openmaic_provider_readiness_call_contract(readiness_id, provider_contract_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_call_receipts'
    AND INDEX_NAME = 'idx_openmaic_provider_readiness_call_contract'
);
PREPARE add_071_call_contract_index_stmt FROM @add_071_call_contract_index;
EXECUTE add_071_call_contract_index_stmt;
DEALLOCATE PREPARE add_071_call_contract_index_stmt;

SET @add_071_call_contract_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_provider_readiness_call_receipts ADD CONSTRAINT fk_openmaic_provider_readiness_call_contract FOREIGN KEY (readiness_id, provider_contract_version) REFERENCES learning_openmaic_provider_readiness_jobs(id, provider_contract_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_call_receipts'
    AND CONSTRAINT_NAME = 'fk_openmaic_provider_readiness_call_contract'
    AND REFERENCED_TABLE_NAME = 'learning_openmaic_provider_readiness_jobs'
);
PREPARE add_071_call_contract_fk_stmt FROM @add_071_call_contract_fk;
EXECUTE add_071_call_contract_fk_stmt;
DEALLOCATE PREPARE add_071_call_contract_fk_stmt;

SET @drop_071_readiness_identity_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_openmaic_provider_readiness_jobs DROP CHECK chk_openmaic_provider_readiness_identity',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_jobs'
    AND CONSTRAINT_NAME = 'chk_openmaic_provider_readiness_identity'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_071_readiness_identity_check_stmt
  FROM @drop_071_readiness_identity_check;
EXECUTE drop_071_readiness_identity_check_stmt;
DEALLOCATE PREPARE drop_071_readiness_identity_check_stmt;

ALTER TABLE learning_openmaic_provider_readiness_jobs
  ADD CONSTRAINT chk_openmaic_provider_readiness_identity CHECK (
    request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND grade_code <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND classroom_content_sha256 REGEXP '^[0-9a-f]{64}$'
    AND audio_job_terminal_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND audio_job_state = 'auto_validated'
    AND validation_scene_order BETWEEN 0 AND 239
    AND validation_audio_sha256 REGEXP '^[0-9a-f]{64}$'
    AND validation_audio_machine_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND validation_segment_state = 'auto_validated'
    AND route_session_contract_version = 'mira.openmaic.conversation-proof.v1'
    AND route_session_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND route_session_provider_call = 0
    AND route_session_status = 'passed'
    AND route_session_completed_at > 0
    AND provider_contract_version IN (
      'mira.openmaic.formal-provider-readiness.v1',
      'mira.openmaic.formal-provider-readiness.v2'
    )
  );

SET @drop_071_call_identity_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_openmaic_provider_readiness_call_receipts DROP CHECK chk_openmaic_provider_readiness_call_identity',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_call_receipts'
    AND CONSTRAINT_NAME = 'chk_openmaic_provider_readiness_call_identity'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_071_call_identity_check_stmt
  FROM @drop_071_call_identity_check;
EXECUTE drop_071_call_identity_check_stmt;
DEALLOCATE PREPARE drop_071_call_identity_check_stmt;

ALTER TABLE learning_openmaic_provider_readiness_call_receipts
  ADD CONSTRAINT chk_openmaic_provider_readiness_call_identity CHECK (
    call_ordinal BETWEEN 1 AND 5
    AND fallback_used = 0
    AND provider_call = 1
    AND request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND (
      (
        provider_contract_version =
          'mira.openmaic.formal-provider-readiness.v1'
        AND call_ordinal = 1 AND kind = 'kimi_text' AND subject IS NULL
        AND provider_id = 'kimi' AND model_id = 'kimi-k2.6'
        AND voice_id IS NULL AND language_code IS NULL
      )
      OR (
        provider_contract_version =
          'mira.openmaic.formal-provider-readiness.v2'
        AND call_ordinal = 1 AND kind = 'deepseek_text'
        AND subject IS NULL AND provider_id = 'deepseek'
        AND model_id = 'deepseek-v4-pro'
        AND voice_id IS NULL AND language_code IS NULL
      )
      OR (
        provider_contract_version IN (
          'mira.openmaic.formal-provider-readiness.v1',
          'mira.openmaic.formal-provider-readiness.v2'
        )
        AND call_ordinal = 2 AND kind = 'qwen_asr'
        AND subject IN ('chinese', 'math', 'english')
        AND provider_id = 'qwen-asr' AND model_id = 'qwen3-asr-flash'
        AND voice_id IS NULL
        AND ((subject IN ('chinese', 'math') AND language_code = 'zh-CN')
          OR (subject = 'english' AND language_code = 'en-US'))
      )
      OR (
        provider_contract_version IN (
          'mira.openmaic.formal-provider-readiness.v1',
          'mira.openmaic.formal-provider-readiness.v2'
        )
        AND call_ordinal = 3 AND kind = 'qwen_tts'
        AND subject = 'chinese' AND provider_id = 'qwen-tts'
        AND model_id = 'qwen3-tts-flash' AND voice_id = 'Serena'
        AND language_code = 'zh-CN'
      )
      OR (
        provider_contract_version IN (
          'mira.openmaic.formal-provider-readiness.v1',
          'mira.openmaic.formal-provider-readiness.v2'
        )
        AND call_ordinal = 4 AND kind = 'qwen_tts'
        AND subject = 'math' AND provider_id = 'qwen-tts'
        AND model_id = 'qwen3-tts-flash' AND voice_id = 'Ethan'
        AND language_code = 'zh-CN'
      )
      OR (
        provider_contract_version IN (
          'mira.openmaic.formal-provider-readiness.v1',
          'mira.openmaic.formal-provider-readiness.v2'
        )
        AND call_ordinal = 5 AND kind = 'qwen_tts'
        AND subject = 'english' AND provider_id = 'qwen-tts'
        AND model_id = 'qwen3-tts-flash' AND voice_id = 'Jennifer'
        AND language_code = 'en-US'
      )
    )
  );
