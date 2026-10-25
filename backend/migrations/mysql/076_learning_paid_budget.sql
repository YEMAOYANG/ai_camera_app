-- New accounting only. This migration creates no spending authorization.
CREATE TABLE learning_budget_control (
    id INTEGER PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 0,
    halted INTEGER NOT NULL DEFAULT 0,
    reason_code VARCHAR(128) NULL,
    CHECK (id = 1), CHECK (halted IN (0, 1))
) ENGINE=InnoDB;
INSERT INTO learning_budget_control (id, revision, halted) VALUES (1, 0, 0);

CREATE TABLE learning_budget_authorizations (
    id VARCHAR(64) PRIMARY KEY,
    scope_json LONGTEXT NOT NULL,
    limits_json LONGTEXT NOT NULL,
    price_keys_json LONGTEXT NOT NULL,
    policy_sha256 VARCHAR(64) NOT NULL,
    expires_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    revoked_at BIGINT NULL
) ENGINE=InnoDB;

CREATE TABLE learning_budget_reservations (
    id VARCHAR(64) PRIMARY KEY,
    authorization_id VARCHAR(64) NOT NULL,
    dispatch_id VARCHAR(160) NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    request_identity_sha256 VARCHAR(64) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    user_key VARCHAR(64) NOT NULL,
    course_key VARCHAR(64) NOT NULL,
    policy_sha256 VARCHAR(64) NOT NULL,
    price_json LONGTEXT NOT NULL,
    max_units_json LONGTEXT NOT NULL,
    actual_units_json LONGTEXT NULL,
    state VARCHAR(20) NOT NULL,
    settlement_sha256 VARCHAR(64) NULL,
    provider_request_id VARCHAR(255) NULL,
    created_at BIGINT NOT NULL,
    charge_at BIGINT NOT NULL,
    dispatched_at BIGINT NULL,
    settled_at BIGINT NULL,
    CHECK (purpose IN ('production', 'required_teaching', 'optional_interaction')),
    CHECK (state IN ('reserved', 'dispatched', 'unknown', 'settled', 'released')),
    FOREIGN KEY (authorization_id) REFERENCES learning_budget_authorizations(id)
) ENGINE=InnoDB;
CREATE INDEX idx_learning_budget_pending ON learning_budget_reservations(state, charge_at);
CREATE INDEX idx_learning_budget_course ON learning_budget_reservations(course_key);
CREATE INDEX idx_learning_budget_authorization ON learning_budget_reservations(authorization_id);

CREATE TABLE learning_budget_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    reservation_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    evidence_json LONGTEXT NOT NULL,
    created_at BIGINT NOT NULL,
    FOREIGN KEY (reservation_id) REFERENCES learning_budget_reservations(id)
) ENGINE=InnoDB;
