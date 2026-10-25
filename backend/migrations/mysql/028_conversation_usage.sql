CREATE TABLE IF NOT EXISTS conversation_sessions (
  id VARCHAR(64) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL,
  session_type VARCHAR(32) NOT NULL,
  started_at BIGINT NOT NULL,
  ended_at BIGINT NULL,
  duration_seconds INT NOT NULL DEFAULT 0,
  date_key VARCHAR(16) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CONSTRAINT fk_conversation_sessions_family
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
);

CREATE INDEX idx_conversation_sessions_family_date
  ON conversation_sessions(family_id, date_key);

CREATE TABLE IF NOT EXISTS conversation_daily_usage (
  family_id VARCHAR(64) NOT NULL,
  date_key VARCHAR(16) NOT NULL,
  free_chat_seconds INT NOT NULL DEFAULT 0,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, date_key),
  CONSTRAINT fk_conversation_daily_usage_family
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
);
