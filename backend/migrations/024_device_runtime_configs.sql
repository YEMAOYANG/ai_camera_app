CREATE TABLE IF NOT EXISTS device_runtime_configs (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  device_id VARCHAR(255) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  config_json TEXT,
  secret_ref VARCHAR(255),
  status VARCHAR(64) NOT NULL DEFAULT 'active',
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CONSTRAINT fk_device_runtime_configs_family
    FOREIGN KEY (family_id) REFERENCES families(id),
  CONSTRAINT fk_device_runtime_configs_device
    FOREIGN KEY (device_id) REFERENCES devices(id),
  CONSTRAINT uq_device_runtime_configs_family_device
    UNIQUE (family_id, device_id)
);

CREATE INDEX idx_device_runtime_configs_provider
  ON device_runtime_configs(provider);

CREATE INDEX idx_device_runtime_configs_status
  ON device_runtime_configs(status);
