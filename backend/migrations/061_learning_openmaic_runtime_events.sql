CREATE TABLE IF NOT EXISTS learning_openmaic_runtime_event_streams (
  runtime_session_id VARCHAR(128) PRIMARY KEY,
  learning_session_id VARCHAR(255) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  upstream_classroom_id VARCHAR(255) NOT NULL,
  principal_id VARCHAR(128) NOT NULL,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  expected_scene_count INTEGER NOT NULL,
  last_sequence INTEGER NOT NULL DEFAULT 0,
  completed_at BIGINT,
  report_id VARCHAR(255),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_openmaic_runtime_stream_learning(
    runtime_session_id, learning_session_id, family_id, child_id
  ),
  UNIQUE KEY uq_openmaic_runtime_stream_classroom(
    runtime_session_id, runtime_classroom_id, upstream_classroom_id
  ),
  INDEX idx_openmaic_runtime_stream_learning(
    family_id, child_id, learning_session_id(96), updated_at
  ),
  CONSTRAINT fk_openmaic_runtime_stream_session
    FOREIGN KEY (runtime_session_id)
      REFERENCES student_openmaic_runtime_sessions(id),
  CONSTRAINT fk_openmaic_runtime_stream_classroom
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_openmaic_runtime_stream_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT chk_openmaic_runtime_stream_state CHECK (
    target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND expected_scene_count = 10
    AND last_sequence >= 0
    AND (
      (completed_at IS NULL AND report_id IS NULL)
      OR (completed_at IS NOT NULL AND completed_at > 0 AND report_id IS NOT NULL)
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_openmaic_runtime_events (
  id VARCHAR(128) PRIMARY KEY,
  runtime_session_id VARCHAR(128) NOT NULL,
  sequence INTEGER NOT NULL,
  idempotency_key CHAR(64) NOT NULL,
  request_sha256 CHAR(64) NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  scene_index INTEGER NOT NULL,
  scene_id VARCHAR(128) NOT NULL,
  action_id VARCHAR(128),
  question_id VARCHAR(128),
  attempt_number INTEGER,
  payload_json LONGTEXT NOT NULL,
  authoritative_json LONGTEXT,
  response_json LONGTEXT NOT NULL,
  receipt_sha256 CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_openmaic_runtime_event_sequence(runtime_session_id, sequence),
  UNIQUE KEY uq_openmaic_runtime_event_idempotency(
    runtime_session_id, idempotency_key
  ),
  UNIQUE KEY uq_openmaic_runtime_event_receipt(runtime_session_id, receipt_sha256),
  INDEX idx_openmaic_runtime_event_scene(
    runtime_session_id, event_type, scene_index, sequence
  ),
  CONSTRAINT fk_openmaic_runtime_event_stream
    FOREIGN KEY (runtime_session_id)
      REFERENCES learning_openmaic_runtime_event_streams(runtime_session_id),
  CONSTRAINT chk_openmaic_runtime_event_identity CHECK (
    sequence >= 1
    AND idempotency_key REGEXP '^[0-9a-f]{64}$'
    AND request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND receipt_sha256 REGEXP '^[0-9a-f]{64}$'
    AND event_type IN (
      'scene_entered', 'action_completed',
      'answer_submitted', 'classroom_completed'
    )
    AND scene_index >= 0 AND scene_index < 10
    AND (
      (event_type = 'scene_entered' AND action_id IS NULL
        AND question_id IS NULL AND attempt_number IS NULL)
      OR (event_type = 'action_completed' AND action_id IS NOT NULL
        AND question_id IS NULL AND attempt_number IS NULL)
      OR (event_type = 'answer_submitted' AND action_id IS NULL
        AND question_id IS NOT NULL AND attempt_number = 1)
      OR (event_type = 'classroom_completed' AND action_id IS NULL
        AND question_id IS NULL AND attempt_number IS NULL)
    )
  )
);
