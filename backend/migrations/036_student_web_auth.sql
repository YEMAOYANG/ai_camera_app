CREATE TABLE IF NOT EXISTS student_principals (
  id VARCHAR(128) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  pin_hash CHAR(64) NOT NULL,
  pin_salt VARCHAR(64) NOT NULL,
  pin_iterations INTEGER NOT NULL,
  pin_updated_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_student_principals_child(family_id, child_id),
  INDEX idx_student_principals_status(family_id, status)
);

CREATE TABLE IF NOT EXISTS student_pairing_codes (
  id VARCHAR(128) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  created_by_user_id VARCHAR(128) NOT NULL,
  code_hash CHAR(64) NOT NULL,
  pin_hash CHAR(64) NOT NULL,
  pin_salt VARCHAR(64) NOT NULL,
  pin_iterations INTEGER NOT NULL,
  expires_at BIGINT NOT NULL,
  consumed_at BIGINT,
  revoked_at BIGINT,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_student_pairing_codes_hash(code_hash),
  INDEX idx_student_pairing_codes_child(family_id, child_id, created_at)
);

CREATE TABLE IF NOT EXISTS student_trusted_devices (
  id VARCHAR(128) PRIMARY KEY,
  principal_id VARCHAR(128) NOT NULL,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  device_token_hash CHAR(64) NOT NULL,
  device_label VARCHAR(255) NOT NULL,
  device_type VARCHAR(64) NOT NULL,
  device_model VARCHAR(255),
  device_hardware VARCHAR(255),
  platform VARCHAR(64) NOT NULL,
  os_version VARCHAR(64),
  app_version VARCHAR(64),
  status VARCHAR(32) NOT NULL DEFAULT 'trusted',
  failed_pin_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until BIGINT,
  expires_at BIGINT NOT NULL,
  last_active_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  revoked_at BIGINT,
  UNIQUE KEY uq_student_trusted_devices_token(device_token_hash),
  INDEX idx_student_trusted_devices_principal(principal_id, status, last_active_at)
);

CREATE TABLE IF NOT EXISTS student_sessions (
  id VARCHAR(128) PRIMARY KEY,
  principal_id VARCHAR(128) NOT NULL,
  device_id VARCHAR(128) NOT NULL,
  access_hash CHAR(64) NOT NULL,
  refresh_hash CHAR(64) NOT NULL,
  access_expires_at BIGINT NOT NULL,
  refresh_expires_at BIGINT NOT NULL,
  last_active_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  rotated_at BIGINT,
  revoked_at BIGINT,
  UNIQUE KEY uq_student_sessions_access(access_hash),
  UNIQUE KEY uq_student_sessions_refresh(refresh_hash),
  INDEX idx_student_sessions_principal(principal_id, last_active_at),
  INDEX idx_student_sessions_device(device_id, revoked_at)
);
