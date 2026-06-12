CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(255) PRIMARY KEY,
  applied_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS families (
  id VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(255) PRIMARY KEY,
  phone VARCHAR(255) NOT NULL UNIQUE,
  family_id VARCHAR(255) NOT NULL,
  display_name VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS sms_codes (
  phone VARCHAR(255) PRIMARY KEY,
  code_hash VARCHAR(255) NOT NULL,
  expires_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_sent_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id VARCHAR(255) PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  access_hash VARCHAR(255) NOT NULL UNIQUE,
  refresh_hash VARCHAR(255) NOT NULL UNIQUE,
  access_expires_at BIGINT NOT NULL,
  refresh_expires_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  rotated_at BIGINT,
  revoked_at BIGINT
);

CREATE TABLE IF NOT EXISTS setup_progress (
  family_id VARCHAR(255) PRIMARY KEY,
  completed TINYINT NOT NULL DEFAULT 0,
  parent_identity_status VARCHAR(255) NOT NULL DEFAULT 'pending',
  device_binding_status VARCHAR(255) NOT NULL DEFAULT 'pending',
  wifi_status VARCHAR(255) NOT NULL DEFAULT 'pending',
  child_profile_status VARCHAR(255) NOT NULL DEFAULT 'pending',
  contacts_status VARCHAR(255) NOT NULL DEFAULT 'pending',
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  completed_at BIGINT
);

CREATE TABLE IF NOT EXISTS parent_identities (
  family_id VARCHAR(255) PRIMARY KEY,
  display_name VARCHAR(255) NOT NULL,
  relationship VARCHAR(255) NOT NULL,
  relationship_key VARCHAR(255),
  confirmed_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  binding_code VARCHAR(255),
  name VARCHAR(255) NOT NULL,
  location VARCHAR(255),
  status VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS wifi_configs (
  family_id VARCHAR(255) PRIMARY KEY,
  ssid VARCHAR(255) NOT NULL,
  auth_type VARCHAR(255) NOT NULL,
  password_set TINYINT NOT NULL,
  saved_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS children (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  nickname VARCHAR(255),
  age_stage VARCHAR(255),
  birthday VARCHAR(255),
  sleep_time VARCHAR(255),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS emergency_contacts (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(255) NOT NULL,
  relationship VARCHAR(255),
  relationship_key VARCHAR(255),
  priority INTEGER NOT NULL,
  created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  type VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  scheduled_date VARCHAR(255) NOT NULL,
  scheduled_start VARCHAR(255),
  scheduled_end VARCHAR(255),
  reward_points INTEGER NOT NULL DEFAULT 0,
  requires_parent_confirmation TINYINT NOT NULL DEFAULT 1,
  evidence_summary TEXT,
  rejection_reason TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  completed_at BIGINT,
  confirmed_at BIGINT,
  rejected_at BIGINT,
  points_granted_at BIGINT
);

CREATE TABLE IF NOT EXISTS point_accounts (
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  balance INTEGER NOT NULL DEFAULT 0,
  stage_notice_handled_balance INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id)
);

CREATE TABLE IF NOT EXISTS point_ledger (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  delta INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  type VARCHAR(255) NOT NULL,
  source_type VARCHAR(255),
  source_id VARCHAR(255),
  note TEXT,
  created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS reward_items (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  points_cost INTEGER NOT NULL,
  category VARCHAR(255),
  status VARCHAR(255) NOT NULL,
  icon VARCHAR(255),
  created_by VARCHAR(255),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS reward_redemptions (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  reward_item_id VARCHAR(255) NOT NULL,
  reward_title VARCHAR(255) NOT NULL,
  points_cost INTEGER NOT NULL,
  status VARCHAR(255) NOT NULL,
  requested_by VARCHAR(255) NOT NULL,
  fulfilled_by VARCHAR(255),
  cancelled_by VARCHAR(255),
  requested_at BIGINT NOT NULL,
  fulfilled_at BIGINT,
  cancelled_at BIGINT
);

CREATE TABLE IF NOT EXISTS firmware_packages (
  id VARCHAR(255) PRIMARY KEY,
  version VARCHAR(255) NOT NULL,
  channel VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  notes TEXT,
  created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS firmware_jobs (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  device_id VARCHAR(255) NOT NULL,
  package_id VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);
