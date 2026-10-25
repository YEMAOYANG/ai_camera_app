-- A probe is a short-lived, operator-only gateway verification session.  It is
-- deliberately not a student session and stores no principal, family or child.
CREATE TABLE IF NOT EXISTS learning_openmaic_conversation_probes (
  id VARCHAR(128) PRIMARY KEY,
  ticket_hash CHAR(64) NOT NULL,
  runtime_token_hash CHAR(64),
  runtime_session_id VARCHAR(128),
  runtime_classroom_id VARCHAR(128) NOT NULL,
  upstream_classroom_id VARCHAR(255) NOT NULL,
  challenge VARCHAR(128) NOT NULL,
  expires_at BIGINT NOT NULL,
  consumed_at BIGINT,
  revoked_at BIGINT,
  chat_receipt_json LONGTEXT,
  transcription_receipt_json LONGTEXT,
  finalized_at BIGINT,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_openmaic_probe_ticket(ticket_hash),
  UNIQUE KEY uq_openmaic_probe_runtime_token(runtime_token_hash),
  UNIQUE KEY uq_openmaic_probe_runtime_session(runtime_session_id),
  -- A generated runtime gets exactly one probe lifecycle.  The runtime row is
  -- also locked during issue, but this key closes the cross-worker race.
  UNIQUE KEY uq_openmaic_probe_runtime_classroom(runtime_classroom_id),
  INDEX idx_openmaic_probe_runtime(runtime_classroom_id, expires_at),
  CONSTRAINT fk_openmaic_probe_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id)
);
