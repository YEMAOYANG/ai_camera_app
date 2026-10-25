CREATE TABLE learning_openmaic_provider_circuits (
  circuit_key VARCHAR(128) PRIMARY KEY,
  provider_id VARCHAR(64) NOT NULL,
  model_id VARCHAR(128) NOT NULL,
  status VARCHAR(16) NOT NULL,
  reason_code VARCHAR(128),
  opened_by_runtime_id VARCHAR(128),
  opened_at BIGINT,
  last_probe_at BIGINT,
  probe_succeeded_at BIGINT,
  closed_at BIGINT,
  revision INT NOT NULL DEFAULT 1,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CONSTRAINT chk_openmaic_provider_circuit_status
    CHECK (status IN ('open', 'closed')),
  CONSTRAINT chk_openmaic_provider_circuit_revision
    CHECK (revision >= 1),
  CONSTRAINT fk_openmaic_provider_circuit_runtime
    FOREIGN KEY (opened_by_runtime_id)
    REFERENCES learning_openmaic_runtime_classrooms(id)
    ON DELETE RESTRICT
);

CREATE INDEX idx_openmaic_provider_circuit_status
  ON learning_openmaic_provider_circuits(status, updated_at);
