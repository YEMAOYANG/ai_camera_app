CREATE TABLE IF NOT EXISTS onvif_discovery_sessions (
  id VARCHAR(255) PRIMARY KEY,
  token_hash CHAR(64) NOT NULL,
  family_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  binding_code VARCHAR(255) NOT NULL,
  metadata_json TEXT NOT NULL,
  expires_at BIGINT NOT NULL,
  consumed_at BIGINT,
  created_at BIGINT NOT NULL,
  CONSTRAINT fk_onvif_discovery_sessions_family
    FOREIGN KEY (family_id) REFERENCES families(id),
  CONSTRAINT fk_onvif_discovery_sessions_user
    FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT uq_onvif_discovery_sessions_token_hash
    UNIQUE (token_hash)
);

CREATE INDEX idx_onvif_discovery_sessions_family
  ON onvif_discovery_sessions(family_id, expires_at);

CREATE INDEX idx_onvif_discovery_sessions_binding
  ON onvif_discovery_sessions(binding_code, expires_at);
