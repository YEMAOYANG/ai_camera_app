-- PostgreSQL baseline generated from the 89 legacy MySQL migrations (backend/migrations/mysql).
-- Tables live in the schema on the connection's search_path (app).

-- MySQL JSON_TYPE / JSON_LENGTH semantics, used by CHECK constraints below.
CREATE FUNCTION mysql_json_type(value jsonb) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE jsonb_typeof(value)
    WHEN 'object' THEN 'OBJECT' WHEN 'array' THEN 'ARRAY' WHEN 'string' THEN 'STRING'
    WHEN 'boolean' THEN 'BOOLEAN' WHEN 'null' THEN 'NULL'
    ELSE CASE WHEN value::text ~ '^-?[0-9]+$' THEN 'INTEGER' ELSE 'DOUBLE' END END
$$;
CREATE FUNCTION mysql_json_length(value jsonb) RETURNS integer LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT CASE jsonb_typeof(value)
    WHEN 'array' THEN jsonb_array_length(value)
    WHEN 'object' THEN (SELECT count(*)::integer FROM jsonb_object_keys(value))
    ELSE 1 END
$$;

CREATE TABLE account_deletion_requests (
  id varchar(255) NOT NULL,
  user_id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  reason varchar(255),
  requested_at bigint NOT NULL,
  completed_at bigint,
  cancelled_at bigint,
  PRIMARY KEY (id)
);

CREATE TABLE app_option_items (
  catalog_key varchar(255) NOT NULL,
  item_key varchar(255) NOT NULL,
  parent_key varchar(255),
  label varchar(255) NOT NULL,
  description varchar(1024),
  image_asset varchar(512),
  metadata_json text,
  sort_order integer DEFAULT 0 NOT NULL,
  enabled smallint DEFAULT 1 NOT NULL,
  updated_at bigint DEFAULT 0 NOT NULL,
  PRIMARY KEY (catalog_key, item_key)
);
CREATE INDEX idx_app_option_items_parent ON app_option_items (catalog_key, parent_key, sort_order);

CREATE TABLE app_settings (
  family_id varchar(255) NOT NULL,
  setting_key varchar(255) NOT NULL,
  value text NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, setting_key)
);

CREATE TABLE audit_events (
  id varchar(255) NOT NULL,
  audit_domain varchar(64) NOT NULL,
  actor_type varchar(64) DEFAULT 'internal_service' NOT NULL,
  actor_id varchar(128),
  route varchar(128) NOT NULL,
  source_ip varchar(128),
  source_name varchar(128),
  accepted smallint DEFAULT 0 NOT NULL,
  reason varchar(255) NOT NULL,
  payload_ref varchar(255),
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_audit_events_route_created ON audit_events (audit_domain, route, created_at);
CREATE INDEX idx_audit_events_source_created ON audit_events (source_ip, created_at);

CREATE TABLE behavior_signals (
  id varchar(255) NOT NULL,
  observation_event_id varchar(64) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  signal_type varchar(128) NOT NULL,
  signal_value varchar(128) NOT NULL,
  confidence numeric(5,4) DEFAULT 0.0000 NOT NULL,
  duration_seconds integer DEFAULT 0 NOT NULL,
  metadata_json text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_behavior_signals_family_child ON behavior_signals (family_id, child_id, scenario, created_at);
CREATE INDEX idx_behavior_signals_observation ON behavior_signals (observation_event_id);

CREATE TABLE camera_commands (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  device_id varchar(255),
  task_id varchar(255),
  command_type varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  message text,
  request_payload text,
  response_payload text,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  completed_at bigint,
  PRIMARY KEY (id)
);
CREATE INDEX idx_camera_commands_family_created ON camera_commands (family_id, created_at);
CREATE INDEX idx_camera_commands_task_created ON camera_commands (task_id, created_at);

CREATE TABLE camera_observation_events (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  observed_at bigint NOT NULL,
  confidence numeric(5,4) DEFAULT 0.0000 NOT NULL,
  evidence_type varchar(128) DEFAULT 'none' NOT NULL,
  parent_summary text,
  raw_detail_json text,
  source varchar(128) DEFAULT 'camera_adapter' NOT NULL,
  source_event_id varchar(128),
  source_type varchar(64),
  source_id varchar(128),
  task_id varchar(64),
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uniq_camera_observation_source_event UNIQUE (family_id, source, source_event_id)
);
CREATE INDEX idx_camera_observations_device_created ON camera_observation_events (device_id, created_at);
CREATE INDEX idx_camera_observations_family_child ON camera_observation_events (family_id, child_id, scenario, created_at);
CREATE INDEX idx_camera_observations_source ON camera_observation_events (source_type, source_id);

CREATE TABLE care_capability_configs (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  enabled smallint DEFAULT 1 NOT NULL,
  day_types text NOT NULL,
  time_windows text NOT NULL,
  min_observation_seconds integer DEFAULT 20 NOT NULL,
  confidence_threshold numeric(5,4) DEFAULT 0.7200 NOT NULL,
  cooldown_seconds integer DEFAULT 900 NOT NULL,
  daily_limit integer DEFAULT 4 NOT NULL,
  parent_notify_threshold integer DEFAULT 3 NOT NULL,
  allow_speaker smallint DEFAULT 1 NOT NULL,
  record_only smallint DEFAULT 0 NOT NULL,
  prompt_id varchar(128) NOT NULL,
  prompt_version varchar(32) DEFAULT 'v1' NOT NULL,
  fallback_templates text NOT NULL,
  last_reminded_at bigint,
  daily_reminder_count integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uniq_care_capability_target UNIQUE (family_id, child_id, device_id, scenario)
);
CREATE INDEX idx_care_capability_family_child ON care_capability_configs (family_id, child_id, enabled);

CREATE TABLE care_routine_windows (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  day_type varchar(64) NOT NULL,
  window_type varchar(128) NOT NULL,
  start_time varchar(16) NOT NULL,
  end_time varchar(16) NOT NULL,
  enabled smallint DEFAULT 1 NOT NULL,
  timezone varchar(64) DEFAULT 'Asia/Shanghai' NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uniq_care_routine_window_child_type UNIQUE (family_id, child_id, day_type, window_type)
);
CREATE INDEX idx_care_routine_windows_family_child ON care_routine_windows (family_id, child_id, day_type, enabled);

CREATE TABLE children (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  nickname varchar(255),
  gender varchar(255) DEFAULT 'unspecified' NOT NULL,
  age_stage varchar(255),
  birthday varchar(255),
  sleep_time varchar(255),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  education_stage varchar(255),
  grade varchar(255),
  grade_code varchar(64),
  grade_school_year_start integer,
  grade_confirmed_at bigint,
  grade_selection_revision integer DEFAULT 0 NOT NULL,
  school_name varchar(255),
  interests text,
  task_preferences text,
  PRIMARY KEY (id),
  CONSTRAINT uq_children_formal_family_child UNIQUE (family_id, id)
);

CREATE TABLE conversation_daily_usage (
  family_id varchar(64) NOT NULL,
  date_key varchar(16) NOT NULL,
  free_chat_seconds integer DEFAULT 0 NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, date_key)
);

CREATE TABLE conversation_sessions (
  id varchar(64) NOT NULL,
  family_id varchar(64) NOT NULL,
  device_id varchar(64) NOT NULL,
  session_type varchar(32) NOT NULL,
  started_at bigint NOT NULL,
  ended_at bigint,
  duration_seconds integer DEFAULT 0 NOT NULL,
  date_key varchar(16) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_conversation_sessions_family_date ON conversation_sessions (family_id, date_key);

CREATE TABLE course_storage_files (
  storage_id varchar(64) NOT NULL,
  source_path_sha256 varchar(64) NOT NULL,
  content_sha256 varchar(64) NOT NULL,
  source_path text NOT NULL,
  byte_size bigint NOT NULL,
  mime_type varchar(128) NOT NULL,
  locator_json text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (storage_id, source_path_sha256, content_sha256),
  CONSTRAINT chk_course_storage_file_size CHECK (byte_size >= 0),
  CONSTRAINT chk_course_storage_locator CHECK (pg_input_is_valid(locator_json, 'jsonb') and (octet_length(locator_json) <= 16384))
);

CREATE TABLE course_storage_heads (
  storage_id varchar(64) NOT NULL,
  source_path_sha256 varchar(64) NOT NULL,
  content_sha256 varchar(64) NOT NULL,
  scope_key varchar(64) NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (storage_id, source_path_sha256)
);
CREATE INDEX fk_course_storage_head_file ON course_storage_heads (storage_id, source_path_sha256, content_sha256);
CREATE INDEX fk_course_storage_head_scope ON course_storage_heads (storage_id, scope_key);

CREATE TABLE course_storage_scopes (
  storage_id varchar(64) NOT NULL,
  scope_key varchar(64) NOT NULL,
  preview_key varchar(64),
  content_key varchar(64),
  classroom_id varchar(255),
  course_id varchar(255),
  course_version varchar(255),
  scope_json text NOT NULL,
  bindings_json text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (storage_id, scope_key),
  CONSTRAINT chk_course_storage_scope CHECK (pg_input_is_valid(scope_json, 'jsonb') and pg_input_is_valid(bindings_json, 'jsonb') and ((octet_length(scope_json) + octet_length(bindings_json)) <= 8388608))
);
CREATE INDEX idx_course_storage_classroom ON course_storage_scopes (storage_id, classroom_id);
CREATE INDEX idx_course_storage_content ON course_storage_scopes (storage_id, content_key);
CREATE INDEX idx_course_storage_course ON course_storage_scopes (storage_id, course_id, course_version);
CREATE INDEX idx_course_storage_preview ON course_storage_scopes (storage_id, preview_key);

CREATE TABLE current_behavior_states (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  state varchar(128) NOT NULL,
  status varchar(64) DEFAULT 'active' NOT NULL,
  started_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  last_observed_at bigint NOT NULL,
  confidence numeric(5,4) DEFAULT 0.0000 NOT NULL,
  consecutive_seconds integer DEFAULT 0 NOT NULL,
  parent_summary text,
  raw_detail_json text,
  PRIMARY KEY (id),
  CONSTRAINT uniq_current_behavior_state_active UNIQUE (family_id, child_id, device_id, scenario, state)
);
CREATE INDEX idx_current_behavior_states_family_child ON current_behavior_states (family_id, child_id, scenario, status, updated_at);

CREATE TABLE device_runtime_configs (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  device_id varchar(255) NOT NULL,
  provider varchar(64) NOT NULL,
  config_json text,
  secret_ref varchar(255),
  status varchar(64) DEFAULT 'active' NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_device_runtime_configs_family_device UNIQUE (family_id, device_id)
);
CREATE INDEX fk_device_runtime_configs_device ON device_runtime_configs (device_id);
CREATE INDEX idx_device_runtime_configs_provider ON device_runtime_configs (provider);
CREATE INDEX idx_device_runtime_configs_status ON device_runtime_configs (status);

CREATE TABLE devices (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  binding_code varchar(255),
  name varchar(255) NOT NULL,
  wake_name varchar(255),
  location varchar(255),
  status varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  unbound_at bigint,
  PRIMARY KEY (id)
);

CREATE TABLE emergency_contacts (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  phone varchar(255) NOT NULL,
  relationship varchar(255),
  relationship_key varchar(255),
  priority integer NOT NULL,
  created_at bigint NOT NULL,
  default_notify smallint DEFAULT 1 NOT NULL,
  updated_at bigint,
  PRIMARY KEY (id)
);

CREATE TABLE families (
  id varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  family_code varchar(32),
  family_code_updated_at bigint,
  created_at bigint NOT NULL,
  CONSTRAINT idx_families_family_code UNIQUE (family_code),
  PRIMARY KEY (id)
);

CREATE TABLE family_default_devices (
  family_id varchar(255) NOT NULL,
  device_id varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id)
);
CREATE INDEX idx_family_default_devices_device ON family_default_devices (device_id);

CREATE TABLE family_invitations (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  name varchar(255) NOT NULL,
  relationship_key varchar(255),
  phone varchar(255) NOT NULL,
  role varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  accepted_by varchar(255),
  accepted_at bigint,
  declined_at bigint,
  created_by varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  expires_at bigint,
  delivery_status varchar(255),
  delivery_message varchar(1024),
  PRIMARY KEY (id)
);
CREATE INDEX idx_family_invitations_family ON family_invitations (family_id, status, created_at);
CREATE INDEX idx_family_invitations_phone ON family_invitations (phone, status);

CREATE TABLE family_members (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  user_id varchar(255),
  name varchar(255) NOT NULL,
  relationship_key varchar(255),
  phone varchar(255),
  role varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  notify_enabled smallint DEFAULT 1 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_family_members_family ON family_members (family_id, status);

CREATE TABLE feedback_items (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  user_id varchar(255) NOT NULL,
  category varchar(255) NOT NULL,
  content text NOT NULL,
  status varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_feedback_items_family_created ON feedback_items (family_id, created_at);

CREATE TABLE firmware_jobs (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  device_id varchar(255) NOT NULL,
  package_id varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE firmware_packages (
  id varchar(255) NOT NULL,
  version varchar(255) NOT NULL,
  channel varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  notes text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE homework_actions (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  item_id varchar(80) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  result_json jsonb NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_action UNIQUE (submission_id, item_id, idempotency_key)
);

CREATE TABLE homework_audio_receipts (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  item_id varchar(80) NOT NULL,
  revision integer NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  character_count integer NOT NULL,
  result_json jsonb,
  error_code varchar(80),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_homework_audio_submission ON homework_audio_receipts (submission_id, status);

CREATE TABLE homework_capture_authorizations (
  child_id varchar(255) NOT NULL,
  task_id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  device_id varchar(255) NOT NULL,
  revision integer NOT NULL,
  enabled smallint NOT NULL,
  expires_at bigint NOT NULL,
  granted_by varchar(255) NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (child_id, task_id)
);

CREATE TABLE homework_capture_requests (
  id varchar(80) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  task_id varchar(255) NOT NULL,
  device_id varchar(255) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  authorization_revision integer NOT NULL,
  status varchar(32) NOT NULL,
  submission_id varchar(80),
  receipt_json jsonb,
  error_code varchar(80),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_capture UNIQUE (family_id, child_id, idempotency_key)
);

CREATE TABLE homework_file_deletions (
  storage_key varchar(255) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (storage_key)
);

CREATE TABLE homework_item_revisions (
  item_id varchar(80) NOT NULL,
  revision integer NOT NULL,
  submission_id varchar(80) NOT NULL,
  result_json jsonb NOT NULL,
  reason varchar(40) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (item_id, revision)
);
CREATE INDEX idx_homework_revision_submission ON homework_item_revisions (submission_id);

CREATE TABLE homework_items (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  page_id varchar(80) NOT NULL,
  revision integer NOT NULL,
  analysis_revision integer NOT NULL,
  item_order integer NOT NULL,
  result_json jsonb NOT NULL,
  media_json jsonb NOT NULL,
  correction_json jsonb NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_homework_items ON homework_items (submission_id, page_id, item_order);

CREATE TABLE homework_jobs (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  revision integer NOT NULL,
  status varchar(32) NOT NULL,
  lease_token varchar(80),
  lease_until bigint,
  stage varchar(32) NOT NULL,
  error_code varchar(80),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_job UNIQUE (submission_id, revision)
);
CREATE INDEX idx_homework_jobs ON homework_jobs (status, created_at);

CREATE TABLE homework_pages (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  upload_key varchar(128) NOT NULL,
  content_sha256 varchar(64) NOT NULL,
  storage_key varchar(255) NOT NULL,
  mime_type varchar(40) NOT NULL,
  width integer NOT NULL,
  height integer NOT NULL,
  page_order integer NOT NULL,
  rotation integer NOT NULL,
  crop_json jsonb,
  status varchar(32) NOT NULL,
  error_code varchar(80),
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_page_upload UNIQUE (submission_id, upload_key)
);
CREATE INDEX idx_homework_pages ON homework_pages (submission_id, page_order);

CREATE TABLE homework_provider_calls (
  id varchar(80) NOT NULL,
  submission_id varchar(80) NOT NULL,
  page_id varchar(80) NOT NULL,
  child_id varchar(255) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  provider varchar(80) NOT NULL,
  model varchar(160) NOT NULL,
  prompt_version varchar(40) NOT NULL,
  result_json jsonb,
  receipt_json jsonb,
  error_code varchar(80),
  dispatched_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_call UNIQUE (submission_id, page_id, request_sha256)
);
CREATE INDEX idx_homework_call_cache ON homework_provider_calls (child_id, request_sha256, status);

CREATE TABLE homework_submissions (
  id varchar(80) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  grade_code varchar(32) NOT NULL,
  subject varchar(32) NOT NULL,
  title varchar(160) NOT NULL,
  source varchar(32) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  revision integer NOT NULL,
  status varchar(32) NOT NULL,
  consent_at bigint NOT NULL,
  error_code varchar(80),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  deleted_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_homework_create UNIQUE (family_id, child_id, idempotency_key)
);
CREATE INDEX idx_homework_child ON homework_submissions (family_id, child_id, created_at);

CREATE TABLE learning_answer_events (
  id varchar(64) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  source_kind varchar(32) NOT NULL,
  source_id varchar(255) NOT NULL,
  event_key varchar(255) NOT NULL,
  knowledge_id varchar(255) NOT NULL,
  knowledge_label varchar(255) NOT NULL,
  subject varchar(32) NOT NULL,
  grade_code varchar(32) NOT NULL,
  question_fingerprint varchar(64) NOT NULL,
  question_json jsonb NOT NULL,
  answer_json jsonb NOT NULL,
  correct smallint,
  independent smallint,
  hint_used smallint,
  adult_help smallint,
  attempt integer NOT NULL,
  confirmed smallint NOT NULL,
  confidence double precision,
  diagnosis_json jsonb,
  payload_sha256 varchar(64) NOT NULL,
  occurred_at bigint NOT NULL,
  revoked_at bigint,
  revoke_reason varchar(255),
  PRIMARY KEY (id)
);
CREATE INDEX idx_answer_child ON learning_answer_events (family_id, child_id, occurred_at);
CREATE INDEX idx_answer_knowledge ON learning_answer_events (child_id, knowledge_id, revoked_at);
CREATE INDEX idx_answer_source ON learning_answer_events (family_id, child_id, source_kind, source_id);

CREATE TABLE learning_budget_authorizations (
  id varchar(64) NOT NULL,
  scope_json text NOT NULL,
  limits_json text NOT NULL,
  price_keys_json text NOT NULL,
  policy_sha256 varchar(64) NOT NULL,
  expires_at bigint NOT NULL,
  created_at bigint NOT NULL,
  revoked_at bigint,
  PRIMARY KEY (id)
);

CREATE TABLE learning_budget_control (
  id integer NOT NULL,
  revision bigint DEFAULT 0 NOT NULL,
  halted integer DEFAULT 0 NOT NULL,
  reason_code varchar(128),
  PRIMARY KEY (id),
  CONSTRAINT learning_budget_control_chk_1 CHECK (id = 1),
  CONSTRAINT learning_budget_control_chk_2 CHECK (halted in (0,1))
);

CREATE TABLE learning_budget_events (
  id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL,
  reservation_id varchar(64) NOT NULL,
  event_type varchar(32) NOT NULL,
  evidence_json text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX reservation_id ON learning_budget_events (reservation_id);

CREATE TABLE learning_budget_reservations (
  id varchar(64) NOT NULL,
  authorization_id varchar(64) NOT NULL,
  dispatch_id varchar(160) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  request_identity_sha256 varchar(64) NOT NULL,
  purpose varchar(32) NOT NULL,
  user_key varchar(64) NOT NULL,
  course_key varchar(64) NOT NULL,
  policy_sha256 varchar(64) NOT NULL,
  price_json text NOT NULL,
  max_units_json text NOT NULL,
  actual_units_json text,
  state varchar(20) NOT NULL,
  settlement_sha256 varchar(64),
  provider_request_id varchar(255),
  created_at bigint NOT NULL,
  charge_at bigint NOT NULL,
  dispatched_at bigint,
  settled_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT chk_learning_budget_purpose CHECK (purpose in ('production','required_teaching','optional_interaction','homework')),
  CONSTRAINT learning_budget_reservations_chk_2 CHECK (state in ('reserved','dispatched','unknown','settled','released'))
);
CREATE INDEX idx_learning_budget_authorization ON learning_budget_reservations (authorization_id);
CREATE INDEX idx_learning_budget_course ON learning_budget_reservations (course_key);
CREATE INDEX idx_learning_budget_pending ON learning_budget_reservations (state, charge_at);

CREATE TABLE learning_catalog_build_items (
  id varchar(128) NOT NULL,
  build_job_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  skill_id varchar(128) NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  boundary_version varchar(255) NOT NULL,
  variant_ordinal integer DEFAULT 1 NOT NULL,
  status varchar(32) NOT NULL,
  attempt_count integer DEFAULT 0 NOT NULL,
  package_attempt_count integer DEFAULT 0 NOT NULL,
  claim_origin_status varchar(32),
  generation_request_id varchar(128) NOT NULL,
  active_generation_request_id varchar(128),
  active_package_request_id varchar(128),
  course_id varchar(255),
  course_version varchar(64),
  package_id varchar(128),
  package_version integer,
  error_code varchar(128),
  error_message_safe varchar(512),
  started_at bigint,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  execution_mode_snapshot varchar(32) DEFAULT 'full_pipeline' NOT NULL,
  content_manifest_version_snapshot varchar(128),
  subject_ordinal integer,
  boundary_ordinal integer,
  content_phase varchar(64) DEFAULT 'legacy_full_pipeline' NOT NULL,
  content_gate_status varchar(32) DEFAULT 'not_applicable' NOT NULL,
  content_gate_attempt_count integer DEFAULT 0 NOT NULL,
  content_gate_passed_at bigint,
  content_validation_contract_version varchar(128),
  content_receipt_hash varchar(64),
  content_lease_token varchar(128),
  content_lease_expires_at bigint,
  content_heartbeat_at bigint,
  content_attempt_started_at bigint,
  content_provider_attempt_hard_deadline_at bigint,
  content_work_unit_deadline_at bigint,
  content_claim_attempt_ordinal integer,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_build_item_formal_course UNIQUE (id, course_id, course_version),
  CONSTRAINT uq_learning_build_item_formal_package UNIQUE (id, package_id, package_version),
  CONSTRAINT uq_learning_build_item_formal_release UNIQUE (id, release_id, grade_code),
  CONSTRAINT uq_learning_catalog_build_target UNIQUE (build_job_id, grade_code, subject, skill_id, variant_ordinal),
  CONSTRAINT chk_learning_catalog_item_content_state CHECK ((case when (curriculum_version = 'mira.primary.progressive.v1') then coalesce(((execution_mode_snapshot = 'content_only') and (content_manifest_version_snapshot = 'mira.learning.preparation-target.progressive.v1') and (grade_code ~* '^primary_[1-6]$') and (subject in ('chinese','math','english')) and (skill_id <> '') and (boundary_version <> '') and (subject_ordinal >= 1) and (boundary_ordinal >= 1) and (variant_ordinal between 1 and 2) and (package_attempt_count = 0) and (active_package_request_id is null) and (package_id is null) and (package_version is null) and (content_gate_attempt_count = 0) and (content_claim_attempt_ordinal is null) and (content_attempt_started_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null) and (((status = 'pending') and (content_phase = 'not_started') and (attempt_count = 0) and (active_generation_request_id is null) and (content_gate_status = 'not_started') and (course_id is null) and (course_version is null) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null)) or ((status = 'processing') and (content_phase = 'progressive_generation') and (attempt_count = 1) and (active_generation_request_id = generation_request_id) and (content_gate_status = 'not_started') and (course_id is null) and (course_version is null) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is not null) and (content_lease_expires_at is not null) and (content_heartbeat_at is not null)) or ((status = 'course_ready') and (content_phase = 'course_ready') and (attempt_count = 1) and (active_generation_request_id = generation_request_id) and (content_gate_status = 'passed') and (course_id is not null) and (course_id <> '') and (course_version is not null) and (course_version <> '') and (content_gate_passed_at is not null) and (content_gate_passed_at > 0) and (content_validation_contract_version = 'mira.learning.progressive-host-validation.v1') and (content_receipt_hash ~* '^[0-9a-f]{64}$') and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null)) or ((status = 'failed') and (content_phase = 'failed') and (attempt_count = 1) and (active_generation_request_id = generation_request_id) and (content_gate_status = 'failed') and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (error_code is not null) and (error_message_safe is not null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null)))),false) else (((execution_mode_snapshot = 'full_pipeline') and (content_phase = 'legacy_full_pipeline') and (content_gate_status = 'not_applicable') and (content_gate_attempt_count = 0) and ((content_manifest_version_snapshot is null) or ((content_manifest_version_snapshot is not null) and (content_manifest_version_snapshot <> ''))) and ((subject_ordinal is null) or ((subject_ordinal is not null) and (subject_ordinal >= 1))) and ((boundary_ordinal is null) or ((boundary_ordinal is not null) and (boundary_ordinal >= 1))) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null) and (content_attempt_started_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null) and (content_claim_attempt_ordinal is null)) or ((execution_mode_snapshot = 'content_only') and (content_manifest_version_snapshot is not null) and (content_manifest_version_snapshot <> '') and (subject_ordinal is not null) and (subject_ordinal >= 1) and (boundary_ordinal is not null) and (boundary_ordinal >= 1) and (content_phase is not null) and (content_phase in ('not_started','outline','raw_candidate','candidate_repair','candidate_repair_retry','lesson_text','reconciliation','reconciliation_retry','practice_leak_repair_1','practice_leak_repair_2','choice_prompt_repair','independent_verification','consistency_repair','consistency_repair_retry','verification_after_repair','host_gate_pending','host_gate_running','course_ready','failed')) and (content_gate_status is not null) and (content_gate_status in ('not_started','pending','retry_wait','passed','failed_deterministic')) and (content_gate_attempt_count between 0 and 3) and (package_attempt_count = 0) and (active_package_request_id is null) and (package_id is null) and (package_version is null) and (((content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null)) or ((content_lease_token is not null) and (content_lease_expires_at is not null) and (content_heartbeat_at is not null))) and ((content_claim_attempt_ordinal is null) or ((content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal between 1 and 2))) and ((content_receipt_hash is null) or ((content_receipt_hash is not null) and (content_receipt_hash ~* '^[0-9a-f]{64}$'))) and (((content_phase = 'not_started') and (status = 'pending') and (attempt_count = 0) and (active_generation_request_id is null) and (content_claim_attempt_ordinal is null) and (content_gate_status = 'not_started') and (content_gate_attempt_count = 0) and (course_id is null) and (course_version is null) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null) and (content_attempt_started_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null)) or ((content_phase in ('outline','raw_candidate','candidate_repair','candidate_repair_retry','lesson_text','reconciliation','reconciliation_retry','practice_leak_repair_1','practice_leak_repair_2','choice_prompt_repair','independent_verification','consistency_repair','consistency_repair_retry','verification_after_repair')) and (status = 'processing') and (attempt_count between 1 and 2) and (content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal = attempt_count) and (active_generation_request_id is not null) and (content_gate_status = 'not_started') and (content_gate_attempt_count = 0) and (content_attempt_started_at is not null) and (content_provider_attempt_hard_deadline_at is not null) and (content_work_unit_deadline_at is not null) and (content_attempt_started_at <= content_work_unit_deadline_at) and (content_work_unit_deadline_at <= content_provider_attempt_hard_deadline_at) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null)) or ((content_phase = 'host_gate_pending') and (status = 'processing') and (attempt_count between 1 and 2) and (content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal = attempt_count) and (active_generation_request_id is not null) and (course_id is not null) and (course_version is not null) and (content_gate_status in ('pending','retry_wait')) and (content_gate_attempt_count between 0 and 3) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null)) or ((content_phase = 'host_gate_running') and (status = 'processing') and (attempt_count between 1 and 2) and (content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal = attempt_count) and (active_generation_request_id is not null) and (course_id is not null) and (course_version is not null) and (content_gate_status in ('pending','retry_wait')) and (content_gate_attempt_count between 1 and 3) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (content_lease_token is not null) and (content_lease_expires_at is not null) and (content_heartbeat_at is not null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is not null)) or ((content_phase = 'course_ready') and (status = 'course_ready') and (attempt_count between 1 and 2) and (content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal = attempt_count) and (active_generation_request_id is not null) and (course_id is not null) and (course_version is not null) and (content_gate_status = 'passed') and (content_gate_attempt_count between 1 and 3) and (content_gate_passed_at is not null) and (content_validation_contract_version is not null) and (content_validation_contract_version <> '') and (content_receipt_hash is not null) and (content_receipt_hash ~* '^[0-9a-f]{64}$') and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null)) or ((content_phase = 'failed') and (status = 'failed') and (attempt_count between 1 and 2) and (content_claim_attempt_ordinal is not null) and (content_claim_attempt_ordinal = attempt_count) and (active_generation_request_id is not null) and (((content_gate_status = 'not_started') and (content_gate_attempt_count = 0)) or ((content_gate_status = 'failed_deterministic') and (content_gate_attempt_count between 1 and 3))) and (content_gate_passed_at is null) and (content_validation_contract_version is null) and (content_receipt_hash is null) and (error_code is not null) and (error_message_safe is not null) and (content_lease_token is null) and (content_lease_expires_at is null) and (content_heartbeat_at is null) and (content_provider_attempt_hard_deadline_at is null) and (content_work_unit_deadline_at is null))))) end) = true)
);
CREATE INDEX fk_learning_catalog_build_item_release ON learning_catalog_build_items (release_id);
CREATE INDEX idx_learning_catalog_build_items_next ON learning_catalog_build_items (build_job_id, status, grade_code, subject, skill_id, variant_ordinal);
CREATE INDEX idx_learning_catalog_build_items_stage ON learning_catalog_build_items (build_job_id, status, package_attempt_count, updated_at);
CREATE INDEX idx_learning_catalog_item_content_claim ON learning_catalog_build_items (build_job_id, execution_mode_snapshot, status, subject_ordinal, boundary_ordinal, variant_ordinal);

CREATE TABLE learning_catalog_build_jobs (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  target_spec_json text NOT NULL,
  total_item_count integer DEFAULT 0 NOT NULL,
  ready_item_count integer DEFAULT 0 NOT NULL,
  failed_item_count integer DEFAULT 0 NOT NULL,
  error_code varchar(128),
  error_message_safe varchar(512),
  started_at bigint,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  execution_mode varchar(32) DEFAULT 'full_pipeline' NOT NULL,
  content_manifest_version varchar(128),
  canary_manifest_json text,
  stage_ceiling varchar(64) DEFAULT 'active_release' NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_catalog_build_release UNIQUE (release_id),
  CONSTRAINT uq_learning_catalog_build_request UNIQUE (request_id),
  CONSTRAINT chk_learning_catalog_build_content_mode CHECK (((execution_mode = 'full_pipeline') and (stage_ceiling = 'active_release') and ((content_manifest_version is null) or ((content_manifest_version is not null) and (content_manifest_version <> ''))) and ((canary_manifest_json is null) or ((canary_manifest_json is not null) and (pg_input_is_valid(canary_manifest_json, 'jsonb'))))) or ((execution_mode = 'content_only') and (content_manifest_version is not null) and (content_manifest_version <> '') and (canary_manifest_json is not null) and (pg_input_is_valid(canary_manifest_json, 'jsonb')) and (mysql_json_type((canary_manifest_json)::jsonb) = 'OBJECT') and (stage_ceiling = 'content_ready')))
);
CREATE INDEX idx_learning_catalog_build_content_mode ON learning_catalog_build_jobs (execution_mode, status, updated_at);
CREATE INDEX idx_learning_catalog_build_status ON learning_catalog_build_jobs (status, updated_at);

CREATE TABLE learning_catalog_release_items (
  release_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  skill_id varchar(128) NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  boundary_version varchar(255) NOT NULL,
  variant_ordinal integer DEFAULT 1 NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  status varchar(32) NOT NULL,
  quality_status varchar(32) NOT NULL,
  published_at bigint,
  retired_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (release_id, course_id, course_version),
  CONSTRAINT uq_learning_catalog_release_boundary_variant UNIQUE (release_id, boundary_version, variant_ordinal),
  CONSTRAINT uq_learning_release_item_formal_binding UNIQUE (release_id, grade_code, course_id, course_version, package_id, package_version)
);
CREATE INDEX fk_learning_catalog_release_item_course ON learning_catalog_release_items (course_id, course_version);
CREATE INDEX fk_learning_catalog_release_item_package ON learning_catalog_release_items (package_id, package_version);
CREATE INDEX idx_learning_catalog_release_recommendation ON learning_catalog_release_items (release_id, grade_code, subject, skill_id, status, quality_status);
CREATE INDEX idx_learning_catalog_release_runtime_queue ON learning_catalog_release_items (release_id, status, quality_status, retired_at, variant_ordinal, course_id);

CREATE TABLE learning_catalog_releases (
  id varchar(128) NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  title varchar(255) NOT NULL,
  status varchar(32) NOT NULL,
  quality_status varchar(32) NOT NULL,
  required_boundary_count integer DEFAULT 0 NOT NULL,
  ready_item_count integer DEFAULT 0 NOT NULL,
  activated_at bigint,
  retired_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_learning_catalog_releases_active ON learning_catalog_releases (curriculum_version, status, quality_status, activated_at);

CREATE TABLE learning_classroom_generation_jobs (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  generator varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  source_artifact_id varchar(128),
  package_id varchar(128),
  package_version integer,
  error_code varchar(128),
  error_message_safe varchar(512),
  started_at bigint,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_classroom_jobs_request UNIQUE (request_id)
);
CREATE INDEX idx_learning_classroom_jobs_course ON learning_classroom_generation_jobs (course_id, course_version, status, created_at);

CREATE TABLE learning_classroom_source_artifacts (
  id varchar(128) NOT NULL,
  job_id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  source_format varchar(128) NOT NULL,
  source_package_version varchar(64),
  dsl_version varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  source_hash varchar(64) NOT NULL,
  payload_json text NOT NULL,
  validation_report_json text,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_classroom_source_job UNIQUE (job_id)
);
CREATE INDEX idx_learning_classroom_source_hash ON learning_classroom_source_artifacts (source_hash);

CREATE TABLE learning_content_enrichment_drafts (
  id varchar(128) NOT NULL,
  job_id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  schema_version varchar(128) NOT NULL,
  generator varchar(64) NOT NULL,
  provider varchar(128) NOT NULL,
  model varchar(255) NOT NULL,
  status varchar(32) NOT NULL,
  content_hash varchar(64) NOT NULL,
  payload_json text NOT NULL,
  elapsed_ms integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_content_drafts_job UNIQUE (job_id),
  CONSTRAINT uq_learning_content_drafts_request UNIQUE (request_id)
);
CREATE INDEX idx_learning_content_drafts_course ON learning_content_enrichment_drafts (course_id, course_version, status, created_at);

CREATE TABLE learning_content_generation_jobs (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  generator varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  error_code varchar(128),
  error_message varchar(512),
  draft_id varchar(128),
  started_at bigint NOT NULL,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_content_jobs_request UNIQUE (request_id)
);
CREATE INDEX idx_learning_content_jobs_course ON learning_content_generation_jobs (course_id, course_version, status, created_at);

CREATE TABLE learning_course_generation_candidates (
  id varchar(128) NOT NULL,
  job_id varchar(128) NOT NULL,
  ordinal integer NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  node_code varchar(128) NOT NULL,
  curriculum_version varchar(128),
  boundary_version varchar(255),
  title varchar(255) NOT NULL,
  objective text NOT NULL,
  status varchar(32) NOT NULL,
  content_hash varchar(64) NOT NULL,
  content_json text NOT NULL,
  validation_json text,
  error_code varchar(128),
  error_message_safe varchar(512),
  published_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_course_candidate_ordinal UNIQUE (job_id, ordinal)
);
CREATE INDEX idx_learning_course_candidates_job ON learning_course_generation_candidates (job_id, status, ordinal);
CREATE INDEX idx_learning_course_candidates_target ON learning_course_generation_candidates (course_id, course_version, status);

CREATE TABLE learning_course_generation_jobs (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  request_fingerprint varchar(64) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  node_code varchar(128) NOT NULL,
  curriculum_version varchar(128),
  boundary_version varchar(255),
  generator varchar(64) NOT NULL,
  provider varchar(128) NOT NULL,
  model varchar(255) NOT NULL,
  prompt_version varchar(128) NOT NULL,
  requested_candidate_count integer DEFAULT 1 NOT NULL,
  status varchar(32) NOT NULL,
  error_code varchar(128),
  error_message_safe varchar(512),
  started_at bigint,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_course_generation_request UNIQUE (request_id)
);
CREATE INDEX idx_learning_course_generation_target ON learning_course_generation_jobs (grade_code, subject, node_code, status, created_at);

CREATE TABLE learning_course_lesson_package_bindings (
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (course_id, course_version)
);
CREATE INDEX fk_learning_course_lesson_package_binding ON learning_course_lesson_package_bindings (package_id, package_version);

CREATE TABLE learning_course_provider_dispatches (
  id varchar(128) NOT NULL,
  build_item_id varchar(128) NOT NULL,
  logical_attempt integer NOT NULL,
  phase varchar(64) NOT NULL,
  phase_ordinal integer NOT NULL,
  generation_request_id varchar(128) NOT NULL,
  item_lease_token varchar(128) NOT NULL,
  provider varchar(128) NOT NULL,
  model varchar(128) NOT NULL,
  profile varchar(128) NOT NULL,
  input_sha256 varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  checkpoint_json text,
  output_sha256 varchar(64),
  attempt_started_at bigint NOT NULL,
  attempt_hard_deadline_at bigint NOT NULL,
  provider_request_id_hash varchar(64),
  input_tokens integer,
  output_tokens integer,
  billing_evidence varchar(32),
  safe_error_code varchar(128),
  dispatched_at bigint NOT NULL,
  completed_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_provider_dispatch_ordinal UNIQUE (build_item_id, logical_attempt, phase_ordinal),
  CONSTRAINT uq_learning_provider_dispatch_phase UNIQUE (build_item_id, logical_attempt, phase),
  CONSTRAINT chk_learning_provider_dispatch_attempt CHECK (logical_attempt between 1 and 2),
  CONSTRAINT chk_learning_provider_dispatch_evidence CHECK ((input_sha256 ~* '^[0-9a-f]{64}$') and (attempt_started_at <= dispatched_at) and (dispatched_at <= attempt_hard_deadline_at) and ((provider_request_id_hash is null) or ((provider_request_id_hash is not null) and (provider_request_id_hash ~* '^[0-9a-f]{64}$'))) and ((input_tokens is null) or ((input_tokens is not null) and (input_tokens >= 0))) and ((output_tokens is null) or ((output_tokens is not null) and (output_tokens >= 0))) and ((completed_at is null) or ((completed_at is not null) and (completed_at <= attempt_hard_deadline_at))) and (((status = 'dispatched') and (checkpoint_json is null) and (output_sha256 is null) and (provider_request_id_hash is null) and (input_tokens is null) and (output_tokens is null) and (billing_evidence is null) and (safe_error_code is null) and (completed_at is null)) or ((status = 'succeeded') and (checkpoint_json is not null) and (pg_input_is_valid(checkpoint_json, 'jsonb')) and (mysql_json_type((checkpoint_json)::jsonb) = 'OBJECT') and (output_sha256 is not null) and (output_sha256 ~* '^[0-9a-f]{64}$') and (billing_evidence is not null) and (billing_evidence in ('reported','unknown')) and (safe_error_code is null) and (completed_at is not null) and (completed_at >= dispatched_at)) or ((status in ('failed_safe','ambiguous')) and (checkpoint_json is null) and (output_sha256 is null) and (billing_evidence is not null) and (billing_evidence in ('reported','unknown')) and (safe_error_code is not null) and (safe_error_code ~* '^[a-z0-9_]{1,128}$') and (completed_at is not null) and (completed_at >= dispatched_at)))),
  CONSTRAINT chk_learning_provider_dispatch_phase CHECK (((phase = 'outline') and (phase_ordinal = 1)) or ((phase = 'raw_candidate') and (phase_ordinal = 2)) or ((phase = 'candidate_repair') and (phase_ordinal = 3)) or ((phase = 'candidate_repair_retry') and (phase_ordinal = 4)) or ((phase = 'lesson_text') and (phase_ordinal = 5)) or ((phase = 'reconciliation') and (phase_ordinal = 6)) or ((phase = 'reconciliation_retry') and (phase_ordinal = 7)) or ((phase = 'practice_leak_repair_1') and (phase_ordinal = 8)) or ((phase = 'practice_leak_repair_2') and (phase_ordinal = 9)) or ((phase = 'choice_prompt_repair') and (phase_ordinal = 10)) or ((phase = 'independent_verification') and (phase_ordinal = 11)) or ((phase = 'consistency_repair') and (phase_ordinal = 12)) or ((phase = 'consistency_repair_retry') and (phase_ordinal = 13)) or ((phase = 'verification_after_repair') and (phase_ordinal = 14)))
);
CREATE INDEX idx_learning_provider_dispatch_item_status ON learning_course_provider_dispatches (build_item_id, status, phase_ordinal);

CREATE TABLE learning_course_reuse_slots (
  identity_key varchar(64) NOT NULL,
  course_key varchar(64) NOT NULL,
  edition_id varchar(80) NOT NULL,
  node_id varchar(80) NOT NULL,
  part_index integer NOT NULL,
  teaching_revision varchar(80) NOT NULL,
  identity_json jsonb NOT NULL,
  lesson_scope_sha256 varchar(64) NOT NULL,
  preview_key varchar(64),
  published_content_key varchar(64),
  regeneration_json jsonb,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (identity_key),
  CONSTRAINT uq_course_reuse_preview UNIQUE (preview_key),
  CONSTRAINT uq_course_reuse_version UNIQUE (course_key, teaching_revision),
  CONSTRAINT chk_course_reuse_part CHECK (part_index between 1 and 20)
);
CREATE INDEX fk_course_reuse_edition ON learning_course_reuse_slots (edition_id);
CREATE INDEX fk_course_reuse_publication ON learning_course_reuse_slots (published_content_key);
CREATE INDEX idx_course_reuse_lookup ON learning_course_reuse_slots (course_key, created_at);

CREATE TABLE learning_course_supply_incidents (
  build_item_id varchar(128) NOT NULL,
  stage varchar(64) NOT NULL,
  reason_code varchar(128) NOT NULL,
  blocked_at bigint NOT NULL,
  last_observed_at bigint NOT NULL,
  resolved_at bigint,
  failure_runtime_id varchar(255),
  PRIMARY KEY (build_item_id)
);

CREATE TABLE learning_course_supply_requests (
  target_fingerprint varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  skill_id varchar(128) NOT NULL,
  variant_ordinal integer NOT NULL,
  priority integer NOT NULL,
  purpose varchar(32) NOT NULL,
  enabled smallint DEFAULT 1 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (target_fingerprint, subject, skill_id, variant_ordinal),
  CONSTRAINT chk_learning_supply_priority CHECK (priority >= 0),
  CONSTRAINT chk_learning_supply_purpose CHECK (purpose in ('canary','core','review','forward')),
  CONSTRAINT chk_learning_supply_variant CHECK (variant_ordinal between 1 and 3)
);

CREATE TABLE learning_courses (
  id varchar(255) NOT NULL,
  version varchar(64) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  node_code varchar(128) NOT NULL,
  curriculum_version varchar(128),
  boundary_version varchar(255),
  title varchar(255) NOT NULL,
  objective text NOT NULL,
  status varchar(32) NOT NULL,
  quality_status varchar(32) DEFAULT 'legacy_unreviewed' NOT NULL,
  content_origin varchar(64) DEFAULT 'legacy_seed' NOT NULL,
  generator varchar(64),
  generation_request_id varchar(128),
  generation_content_hash varchar(64),
  content_json text NOT NULL,
  published_at bigint,
  retired_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id, version),
  CONSTRAINT uq_learning_courses_generation_content_hash UNIQUE (generation_content_hash)
);
CREATE INDEX idx_learning_courses_catalog_candidate ON learning_courses (curriculum_version, grade_code, subject, node_code, boundary_version, quality_status, status, retired_at);
CREATE INDEX idx_learning_courses_dynamic_supply ON learning_courses (grade_code, subject, status, content_origin, node_code);
CREATE INDEX idx_learning_courses_recommendation ON learning_courses (grade_code, subject, status, published_at);

CREATE TABLE learning_curriculum_classroom_item_receipts (
  build_item_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  binding_contract_version varchar(128) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  classroom_status varchar(32) DEFAULT 'pending' NOT NULL,
  classroom_receipt_hash varchar(64),
  classroom_completed_at bigint,
  tts_status varchar(32) DEFAULT 'pending' NOT NULL,
  tts_receipt_hash varchar(64),
  tts_completed_at bigint,
  asr_roundtrip_status varchar(32) DEFAULT 'pending' NOT NULL,
  asr_roundtrip_receipt_hash varchar(64),
  asr_roundtrip_completed_at bigint,
  conversation_provider_status varchar(32) DEFAULT 'pending' NOT NULL,
  conversation_provider_receipt_hash varchar(64),
  conversation_provider_completed_at bigint,
  auto_validated smallint DEFAULT 0 NOT NULL,
  auto_validation_contract_version varchar(128),
  auto_validation_receipt_hash varchar(64),
  auto_validated_at bigint,
  approved smallint DEFAULT 0 NOT NULL,
  approved_by varchar(128),
  approval_receipt_hash varchar(64),
  approved_at bigint,
  publication_status varchar(32) DEFAULT 'pending' NOT NULL,
  publication_receipt_hash varchar(64),
  published_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (build_item_id),
  CONSTRAINT uq_learning_classroom_receipt_provider_binding UNIQUE (build_item_id, release_id, runtime_classroom_id),
  CONSTRAINT uq_learning_classroom_receipt_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_learning_receipt_formal_binding UNIQUE (build_item_id, release_id, runtime_classroom_id),
  CONSTRAINT chk_learning_classroom_receipt_evidence CHECK ((((classroom_status = 'pending') and (classroom_receipt_hash is null) and (classroom_completed_at is null)) or ((classroom_status in ('passed','failed')) and (classroom_receipt_hash is not null) and (classroom_receipt_hash ~* '^[0-9a-f]{64}$') and (classroom_completed_at is not null) and (classroom_completed_at > 0))) and (((tts_status = 'pending') and (tts_receipt_hash is null) and (tts_completed_at is null)) or ((tts_status in ('passed','failed')) and (tts_receipt_hash is not null) and (tts_receipt_hash ~* '^[0-9a-f]{64}$') and (tts_completed_at is not null) and (tts_completed_at > 0))) and (((asr_roundtrip_status = 'pending') and (asr_roundtrip_receipt_hash is null) and (asr_roundtrip_completed_at is null)) or ((asr_roundtrip_status in ('passed','failed')) and (asr_roundtrip_receipt_hash is not null) and (asr_roundtrip_receipt_hash ~* '^[0-9a-f]{64}$') and (asr_roundtrip_completed_at is not null) and (asr_roundtrip_completed_at > 0))) and (((conversation_provider_status = 'pending') and (conversation_provider_receipt_hash is null) and (conversation_provider_completed_at is null)) or ((conversation_provider_status in ('passed','failed')) and (conversation_provider_receipt_hash is not null) and (conversation_provider_receipt_hash ~* '^[0-9a-f]{64}$') and (conversation_provider_completed_at is not null) and (conversation_provider_completed_at > 0))) and (((auto_validated = 0) and (auto_validation_contract_version is null) and (auto_validation_receipt_hash is null) and (auto_validated_at is null)) or ((auto_validated = 1) and (auto_validation_contract_version is not null) and (auto_validation_contract_version <> '') and (auto_validation_receipt_hash is not null) and (auto_validation_receipt_hash ~* '^[0-9a-f]{64}$') and (auto_validated_at is not null) and (auto_validated_at > 0))) and (((approved = 0) and (approved_by is null) and (approval_receipt_hash is null) and (approved_at is null)) or ((approved = 1) and (approved_by is not null) and (approved_by <> '') and (approval_receipt_hash is not null) and (approval_receipt_hash ~* '^[0-9a-f]{64}$') and (approved_at is not null) and (approved_at > 0))) and (((publication_status = 'pending') and (publication_receipt_hash is null) and (published_at is null)) or ((publication_status = 'failed') and (publication_receipt_hash is not null) and (publication_receipt_hash ~* '^[0-9a-f]{64}$') and (published_at is not null) and (published_at > 0)) or ((publication_status = 'published') and (publication_receipt_hash is not null) and (publication_receipt_hash ~* '^[0-9a-f]{64}$') and (published_at is not null) and (published_at > 0) and (classroom_status = 'passed') and (tts_status = 'passed') and (asr_roundtrip_status = 'passed') and (conversation_provider_status = 'passed') and (auto_validated = 1)))),
  CONSTRAINT chk_learning_classroom_receipt_identity CHECK ((grade_code <> '') and (target_fingerprint ~* '^[0-9a-f]{64}$') and (binding_contract_version <> '') and (package_version > 0)),
  CONSTRAINT chk_learning_classroom_receipt_timeline CHECK ((created_at > 0) and (updated_at >= created_at) and ((classroom_completed_at is null) or ((classroom_completed_at >= created_at) and (classroom_completed_at <= updated_at))) and ((tts_completed_at is null) or ((tts_completed_at >= created_at) and (tts_completed_at <= updated_at))) and ((asr_roundtrip_completed_at is null) or ((asr_roundtrip_completed_at >= created_at) and (asr_roundtrip_completed_at <= updated_at))) and ((conversation_provider_completed_at is null) or ((conversation_provider_completed_at >= created_at) and (conversation_provider_completed_at <= updated_at))) and ((auto_validated_at is null) or ((auto_validated_at >= created_at) and (auto_validated_at <= updated_at))) and ((approved_at is null) or ((approved_at >= created_at) and (approved_at <= updated_at))) and ((published_at is null) or ((published_at >= created_at) and (published_at <= updated_at))) and ((auto_validated = 0) or ((classroom_status = 'passed') and (tts_status = 'passed') and (asr_roundtrip_status = 'passed') and (conversation_provider_status = 'passed') and (auto_validated_at >= classroom_completed_at) and (auto_validated_at >= tts_completed_at) and (auto_validated_at >= asr_roundtrip_completed_at) and (auto_validated_at >= conversation_provider_completed_at))) and ((publication_status <> 'published') or ((auto_validated = 1) and (published_at >= auto_validated_at))))
);
CREATE INDEX fk_learning_classroom_receipt_course ON learning_curriculum_classroom_item_receipts (course_id, course_version);
CREATE INDEX fk_learning_classroom_receipt_package ON learning_curriculum_classroom_item_receipts (package_id, package_version);
CREATE INDEX idx_learning_classroom_receipt_release ON learning_curriculum_classroom_item_receipts (release_id, grade_code, publication_status, auto_validated);

CREATE TABLE learning_curriculum_grade_release_history (
  id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  pointer_revision integer NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  contract_version varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  previous_history_id varchar(128),
  previous_release_id varchar(128),
  activation_source varchar(32) NOT NULL,
  publication_request_id varchar(128),
  publication_receipt_hash varchar(64),
  activated_at bigint NOT NULL,
  superseded_at bigint,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_grade_history_formal_binding UNIQUE (id, grade_code, pointer_revision, target_fingerprint, contract_version, release_id),
  CONSTRAINT uq_learning_grade_release_history_exact UNIQUE (id, grade_code, pointer_revision, target_fingerprint, contract_version, release_id, activated_at),
  CONSTRAINT uq_learning_grade_release_history_plan_exact UNIQUE (id, grade_code, target_fingerprint, contract_version, release_id, publication_receipt_hash),
  CONSTRAINT uq_learning_grade_release_history_previous_exact UNIQUE (id, grade_code, release_id),
  CONSTRAINT uq_learning_grade_release_history_release UNIQUE (grade_code, release_id),
  CONSTRAINT uq_learning_grade_release_history_request UNIQUE (publication_request_id),
  CONSTRAINT uq_learning_grade_release_history_revision UNIQUE (grade_code, pointer_revision),
  CONSTRAINT chk_learning_grade_release_history_evidence CHECK (((activation_source = 'legacy_backfill') and (publication_request_id is null) and (publication_receipt_hash is null)) or ((activation_source = 'formal_publication') and (publication_request_id is not null) and (publication_request_id <> '') and (publication_receipt_hash is not null) and (publication_receipt_hash ~* '^[0-9a-f]{64}$'))),
  CONSTRAINT chk_learning_grade_release_history_identity CHECK ((grade_code <> '') and (pointer_revision >= 1) and (target_fingerprint ~* '^[0-9a-f]{64}$') and (contract_version <> '') and (activated_at > 0) and ((superseded_at is null) or (superseded_at >= activated_at)) and (((pointer_revision = 1) and (previous_history_id is null) and (previous_release_id is null)) or ((pointer_revision > 1) and (previous_history_id is not null) and (previous_release_id is not null) and (previous_release_id <> release_id))))
);
CREATE INDEX fk_learning_grade_release_history_previous_exact ON learning_curriculum_grade_release_history (previous_history_id, grade_code, previous_release_id);
CREATE INDEX fk_learning_grade_release_history_release ON learning_curriculum_grade_release_history (release_id);
CREATE INDEX idx_learning_grade_release_history_timeline ON learning_curriculum_grade_release_history (grade_code, activated_at, superseded_at);

CREATE TABLE learning_curriculum_grade_release_pointers (
  grade_code varchar(64) NOT NULL,
  pointer_revision integer DEFAULT 0 NOT NULL,
  target_fingerprint varchar(64),
  contract_version varchar(128),
  release_id varchar(128),
  history_id varchar(128),
  activated_at bigint,
  updated_at bigint NOT NULL,
  PRIMARY KEY (grade_code),
  CONSTRAINT uq_learning_grade_release_pointer_history UNIQUE (history_id),
  CONSTRAINT chk_learning_grade_release_pointer_identity CHECK ((grade_code <> '') and (updated_at > 0) and (((pointer_revision = 0) and (target_fingerprint is null) and (contract_version is null) and (release_id is null) and (history_id is null) and (activated_at is null)) or ((pointer_revision >= 1) and (target_fingerprint is not null) and (target_fingerprint ~* '^[0-9a-f]{64}$') and (contract_version is not null) and (contract_version <> '') and (release_id is not null) and (history_id is not null) and (activated_at is not null) and (activated_at > 0) and (updated_at >= activated_at))))
);
CREATE INDEX fk_learning_grade_release_pointer_history_exact ON learning_curriculum_grade_release_pointers (history_id, grade_code, pointer_revision, target_fingerprint, contract_version, release_id, activated_at);
CREATE INDEX fk_learning_grade_release_pointer_release ON learning_curriculum_grade_release_pointers (release_id);

CREATE TABLE learning_curriculum_preparation_events (
  id varchar(128) NOT NULL,
  plan_id varchar(128) NOT NULL,
  event_type varchar(64) NOT NULL,
  stage varchar(64) NOT NULL,
  payload_json text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT chk_learning_prep_event_json CHECK (pg_input_is_valid(payload_json, 'jsonb'))
);
CREATE INDEX idx_learning_prep_events ON learning_curriculum_preparation_events (plan_id, created_at);

CREATE TABLE learning_curriculum_preparation_plans (
  id varchar(128) NOT NULL,
  family_id varchar(255),
  child_id varchar(255),
  grade_code varchar(64) NOT NULL,
  school_year_start_year integer NOT NULL,
  grade_selection_revision integer NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  preparation_contract_version varchar(128) NOT NULL,
  target_spec_json text NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  request_id varchar(128) NOT NULL,
  shared_build_request_id varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  stage varchar(64) NOT NULL,
  catalog_build_id varchar(128),
  catalog_release_id varchar(128),
  total_course_count integer NOT NULL,
  ready_course_count integer DEFAULT 0 NOT NULL,
  failed_course_count integer DEFAULT 0 NOT NULL,
  progress_percent integer DEFAULT 0 NOT NULL,
  subject_progress_json text NOT NULL,
  retry_of_plan_id varchar(128),
  retry_ordinal integer DEFAULT 0 NOT NULL,
  resume_stage varchar(64),
  lease_token varchar(128),
  lease_expires_at bigint,
  heartbeat_at bigint,
  next_run_at bigint,
  hard_deadline_at bigint,
  error_code varchar(128),
  error_message_safe varchar(512),
  last_progress_at bigint,
  started_at bigint,
  completed_at bigint,
  superseded_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  content_target_count integer DEFAULT 0 NOT NULL,
  content_candidate_count integer DEFAULT 0 NOT NULL,
  content_failed_count integer DEFAULT 0 NOT NULL,
  content_canary_target_count integer DEFAULT 0 NOT NULL,
  content_canary_candidate_count integer DEFAULT 0 NOT NULL,
  content_canary_failed_count integer DEFAULT 0 NOT NULL,
  content_canary_passed_at bigint,
  content_generation_completed_at bigint,
  retry_reason_code varchar(128),
  retry_message_safe varchar(512),
  work_unit_kind varchar(32),
  bound_catalog_item_id varchar(128),
  bound_content_attempt_ordinal integer,
  bound_content_phase varchar(64),
  stage_progress_json text NOT NULL,
  classroom_ready_count integer DEFAULT 0 NOT NULL,
  speech_ready_count integer DEFAULT 0 NOT NULL,
  validation_ready_count integer DEFAULT 0 NOT NULL,
  published_course_count integer DEFAULT 0 NOT NULL,
  formal_contract_version varchar(128),
  formal_publication_history_id varchar(128),
  formal_publication_receipt_hash varchar(64),
  formal_ready_at bigint,
  library_target_fingerprint varchar(64),
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_library_owner UNIQUE (library_target_fingerprint),
  CONSTRAINT uq_learning_prep_identity UNIQUE (child_id, grade_selection_revision, target_fingerprint, retry_ordinal),
  CONSTRAINT uq_learning_prep_request UNIQUE (request_id),
  CONSTRAINT uq_learning_prep_retry_source UNIQUE (retry_of_plan_id),
  CONSTRAINT chk_learning_library_owner CHECK (((library_target_fingerprint is null) and (family_id is not null) and (child_id is not null)) or ((library_target_fingerprint is not null) and (library_target_fingerprint = target_fingerprint) and (family_id is null) and (child_id is null) and (grade_selection_revision = 0))),
  CONSTRAINT chk_learning_prep_content_counts CHECK ((case when (((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.progressive.v1') then coalesce(((curriculum_version = 'mira.primary.progressive.v1') and (preparation_contract_version = 'mira.learning.grade-preparation.progressive.v1') and (grade_code ~* '^primary_[1-6]$') and (pg_input_is_valid(target_spec_json, 'jsonb')) and (((target_spec_json)::jsonb #>> '{curriculumVersion}') = curriculum_version) and (((target_spec_json)::jsonb #>> '{preparationContractVersion}') = preparation_contract_version) and (((target_spec_json)::jsonb #>> '{gradeCode}') = grade_code) and (((target_spec_json)::jsonb #>> '{granularity}') = 'lesson') and (mysql_json_type(((target_spec_json)::jsonb #> '{assessmentBatchOrdinal}')) = 'INTEGER') and ((((target_spec_json)::jsonb #>> '{assessmentBatchOrdinal}'))::bigint >= 1) and (mysql_json_type(((target_spec_json)::jsonb #> '{variantsPerBoundary}')) = 'INTEGER') and ((((target_spec_json)::jsonb #>> '{variantsPerBoundary}'))::bigint = 2) and (mysql_json_type(((target_spec_json)::jsonb #> '{totalCourseCount}')) = 'INTEGER') and ((((target_spec_json)::jsonb #>> '{totalCourseCount}'))::bigint = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{boundaryCount}')) = 'INTEGER') and (((((target_spec_json)::jsonb #>> '{boundaryCount}'))::bigint * 2) = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{boundaries}')) = 'ARRAY') and ((mysql_json_length(((target_spec_json)::jsonb #> '{boundaries}')) * 2) = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{lessonIds}')) = 'ARRAY') and ((mysql_json_length(((target_spec_json)::jsonb #> '{lessonIds}')) * 2) = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{courseTargets}')) = 'ARRAY') and (mysql_json_length(((target_spec_json)::jsonb #> '{courseTargets}')) = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{canaryManifest,targets}')) = 'ARRAY') and (mysql_json_length(((target_spec_json)::jsonb #> '{canaryManifest,targets}')) = content_canary_target_count) and (content_target_count = total_course_count) and (content_target_count > 0) and (content_candidate_count >= 0) and (content_failed_count >= 0) and ((content_candidate_count + content_failed_count) <= content_target_count) and (content_canary_target_count between 1 and 3) and (content_canary_target_count <= content_target_count) and (content_canary_candidate_count >= 0) and (content_canary_failed_count >= 0) and ((content_canary_candidate_count + content_canary_failed_count) <= content_canary_target_count) and (content_canary_candidate_count <= content_candidate_count) and (content_canary_failed_count <= content_failed_count) and ((content_canary_passed_at is null) or ((content_canary_candidate_count = content_canary_target_count) and (content_canary_failed_count = 0))) and ((content_generation_completed_at is null) or ((content_candidate_count = content_target_count) and (content_failed_count = 0) and (content_canary_passed_at is not null)))),false) else ((content_target_count >= 0) and (content_candidate_count >= 0) and (content_failed_count >= 0) and ((content_candidate_count + content_failed_count) <= content_target_count) and (content_canary_target_count >= 0) and (content_canary_candidate_count >= 0) and (content_canary_failed_count >= 0) and (content_canary_target_count <= content_target_count) and ((content_canary_candidate_count + content_canary_failed_count) <= content_canary_target_count) and (content_canary_candidate_count <= content_candidate_count) and (content_canary_failed_count <= content_failed_count) and ((content_canary_passed_at is null) or ((content_canary_passed_at is not null) and (content_canary_target_count = 3) and (content_canary_candidate_count = 3) and (content_canary_failed_count = 0))) and ((content_generation_completed_at is null) or ((content_generation_completed_at is not null) and (content_target_count = (case grade_code when 'primary_1' then 30 when 'primary_2' then 27 when 'primary_3' then 27 when 'primary_4' then 27 when 'primary_5' then 27 when 'primary_6' then 27 else 0 end)) and (content_candidate_count = (case grade_code when 'primary_1' then 30 when 'primary_2' then 27 when 'primary_3' then 27 when 'primary_4' then 27 when 'primary_5' then 27 when 'primary_6' then 27 else 0 end)) and (content_failed_count = 0) and (content_canary_passed_at is not null))) and (((target_spec_json)::jsonb #>> '{schemaVersion}') is not null) and (((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v1') and (content_target_count = 0) and (content_candidate_count = 0) and (content_failed_count = 0) and (content_canary_target_count = 0) and (content_canary_candidate_count = 0) and (content_canary_failed_count = 0) and (content_canary_passed_at is null) and (content_generation_completed_at is null)) or ((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v2') and (content_target_count = (case grade_code when 'primary_1' then 30 when 'primary_2' then 27 when 'primary_3' then 27 when 'primary_4' then 27 when 'primary_5' then 27 when 'primary_6' then 27 else 0 end)) and (content_canary_target_count = 3))) and ((((target_spec_json)::jsonb #>> '{schemaVersion}') <> 'mira.learning.preparation-target.v2') or ((grade_code in ('primary_1','primary_2','primary_3','primary_4','primary_5','primary_6')) and (mysql_json_type(((target_spec_json)::jsonb #> '{gradeCode}')) = 'STRING') and (((target_spec_json)::jsonb #>> '{gradeCode}') is not null) and (((target_spec_json)::jsonb #>> '{gradeCode}') = grade_code) and (mysql_json_type(((target_spec_json)::jsonb #> '{totalCourseCount}')) = 'INTEGER') and (((target_spec_json)::jsonb #> '{totalCourseCount}') is not null) and ((((target_spec_json)::jsonb #>> '{totalCourseCount}'))::bigint = total_course_count) and (content_target_count = total_course_count) and (mysql_json_type(((target_spec_json)::jsonb #> '{courseTargets}')) = 'ARRAY') and (((target_spec_json)::jsonb #> '{courseTargets}') is not null) and (mysql_json_length(((target_spec_json)::jsonb #> '{courseTargets}')) = total_course_count)))) end) = true),
  CONSTRAINT chk_learning_prep_counts CHECK ((total_course_count > 0) and (ready_course_count >= 0) and (failed_course_count >= 0) and ((ready_course_count + failed_course_count) <= total_course_count) and (progress_percent between 0 and 100)),
  CONSTRAINT chk_learning_prep_formal_publication CHECK ((case when (((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.progressive.v1') then coalesce(((classroom_ready_count between 0 and total_course_count) and (speech_ready_count between 0 and classroom_ready_count) and (validation_ready_count between 0 and speech_ready_count) and (published_course_count between 0 and validation_ready_count) and (((status = 'ready') and (stage = 'completed') and (classroom_ready_count = total_course_count) and (speech_ready_count = total_course_count) and (validation_ready_count = total_course_count) and (published_course_count = total_course_count) and (catalog_release_id is not null) and (formal_contract_version = 'mira.learning.formal-publication.v1') and (formal_publication_history_id is not null) and (formal_publication_receipt_hash ~* '^[0-9a-f]{64}$') and (formal_ready_at is not null) and (formal_ready_at > 0)) or ((status <> 'ready') and (formal_contract_version is null) and (formal_publication_history_id is null) and (formal_publication_receipt_hash is null) and (formal_ready_at is null)))),false) else ((classroom_ready_count between 0 and total_course_count) and (speech_ready_count between 0 and classroom_ready_count) and (validation_ready_count between 0 and speech_ready_count) and (published_course_count between 0 and validation_ready_count) and (((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v2') and (status = 'ready') and (stage = 'completed') and (classroom_ready_count = total_course_count) and (speech_ready_count = total_course_count) and (validation_ready_count = total_course_count) and (published_course_count = total_course_count) and (catalog_release_id is not null) and (formal_contract_version is not null) and (formal_contract_version <> '') and (formal_publication_history_id is not null) and (formal_publication_receipt_hash is not null) and (formal_publication_receipt_hash ~* '^[0-9a-f]{64}$') and (formal_ready_at is not null) and (formal_ready_at > 0)) or (((((target_spec_json)::jsonb #>> '{schemaVersion}') <> 'mira.learning.preparation-target.v2') or (status <> 'ready')) and (formal_contract_version is null) and (formal_publication_history_id is null) and (formal_publication_receipt_hash is null) and (formal_ready_at is null)))) end) = true),
  CONSTRAINT chk_learning_prep_formal_state_evidence CHECK ((case when (((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.progressive.v1') then coalesce(((preparation_contract_version = 'mira.learning.grade-preparation.progressive.v1') and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (((status = 'queued') and (stage = 'queued') and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (work_unit_kind is null) and (resume_stage is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('planning','generating_content')) and (next_run_at is not null) and (resume_stage is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (work_unit_kind is null)) or ((lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (work_unit_kind = 'coordinator')))) or ((status = 'running') and (stage in ('building_classrooms','generating_speech','validating','publishing')) and (catalog_build_id is not null) and (catalog_release_id is not null) and (content_target_count = total_course_count) and (content_candidate_count = total_course_count) and (content_failed_count = 0) and (content_canary_candidate_count = content_canary_target_count) and (content_canary_failed_count = 0) and (content_canary_passed_at is not null) and (content_generation_completed_at is not null) and (resume_stage is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((stage = 'building_classrooms') and (progress_percent = 35) and (ready_course_count = 0) and (failed_course_count = 0) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (next_run_at is null) and (work_unit_kind is null)) or ((next_run_at is not null) and (((stage = 'building_classrooms') and (progress_percent between 40 and 64)) or ((stage = 'generating_speech') and (progress_percent between 65 and 84)) or ((stage = 'validating') and (progress_percent between 85 and 94)) or ((stage = 'publishing') and (progress_percent between 95 and 99))) and (((lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (work_unit_kind is null)) or ((lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (work_unit_kind = 'coordinator')))))) or ((status = 'queued') and (stage = 'retry_wait') and (next_run_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (work_unit_kind = 'coordinator') and (resume_stage in ('planning','generating_content','building_classrooms','generating_speech','validating','publishing')) and (retry_reason_code is not null) and (retry_message_safe is not null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and ((resume_stage in ('planning','generating_content')) or ((catalog_build_id is not null) and (catalog_release_id is not null) and (content_target_count = total_course_count) and (content_candidate_count = total_course_count) and (content_failed_count = 0) and (content_canary_candidate_count = content_canary_target_count) and (content_canary_failed_count = 0) and (content_canary_passed_at is not null) and (content_generation_completed_at is not null)))) or ((stage = 'completed') and (completed_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (work_unit_kind is null) and (resume_stage is null) and (retry_reason_code is null) and (retry_message_safe is null) and (((status = 'ready') and (superseded_at is null) and (progress_percent = 100) and (ready_course_count = total_course_count) and (failed_course_count = 0) and (error_code is null) and (error_message_safe is null) and (catalog_build_id is not null) and (catalog_release_id is not null) and (content_target_count = total_course_count) and (content_candidate_count = total_course_count) and (content_failed_count = 0) and (content_canary_candidate_count = content_canary_target_count) and (content_canary_failed_count = 0) and (content_canary_passed_at is not null) and (content_generation_completed_at is not null)) or ((status = 'failed') and (superseded_at is null) and (error_code is not null) and (error_message_safe is not null)) or ((status = 'superseded') and (superseded_at is not null) and (error_code is null) and (error_message_safe is null)))))),false) else ((preparation_contract_version = 'mira.learning.grade-preparation.v1') and (target_spec_json is not null) and (pg_input_is_valid(target_spec_json, 'jsonb')) and (((target_spec_json)::jsonb #>> '{schemaVersion}') is not null) and (((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v1') and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (((status = 'queued') and (stage = 'queued') and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('planning','generating_content','building_classrooms','generating_speech','validating','publishing')) and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('planning','generating_content','building_classrooms','generating_speech','validating','publishing')) and (next_run_at is not null) and (lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (resume_stage is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'queued') and (stage = 'retry_wait') and (next_run_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (resume_stage is not null) and (resume_stage in ('planning','generating_content','building_classrooms','generating_speech','validating','publishing')) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((retry_reason_code is null) and (retry_message_safe is null)) or ((retry_reason_code is not null) and (retry_message_safe is not null)))) or ((status = 'ready') and (stage = 'completed') and (completed_at is not null) and (superseded_at is null) and (progress_percent = 100) and (ready_course_count = total_course_count) and (failed_course_count = 0) and (error_code is null) and (error_message_safe is null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null)) or ((status = 'failed') and (stage = 'completed') and (completed_at is not null) and (superseded_at is null) and (error_code is not null) and (error_message_safe is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null)) or ((status = 'superseded') and (stage = 'completed') and (completed_at is not null) and (superseded_at is not null) and (error_code is null) and (error_message_safe is null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null)))) or ((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v2') and (((status = 'queued') and (stage = 'queued') and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('planning','generating_content')) and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('planning','generating_content')) and (next_run_at is not null) and (lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (resume_stage is null) and (work_unit_kind is not null) and (work_unit_kind = 'coordinator') and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage = 'generating_content') and (next_run_at is not null) and (lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (resume_stage is null) and (work_unit_kind is not null) and (work_unit_kind in ('provider_phase','host_gate')) and (bound_catalog_item_id is not null) and (bound_content_attempt_ordinal is not null) and (bound_content_attempt_ordinal between 1 and 2) and (bound_content_phase is not null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'queued') and (stage = 'retry_wait') and (next_run_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (resume_stage is not null) and (resume_stage in ('planning','generating_content')) and (retry_reason_code is not null) and (retry_message_safe is not null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((work_unit_kind is not null) and (work_unit_kind = 'coordinator') and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null)) or ((work_unit_kind is not null) and (work_unit_kind in ('provider_phase','host_gate')) and (bound_catalog_item_id is not null) and (bound_content_attempt_ordinal is not null) and (bound_content_attempt_ordinal between 1 and 2) and (bound_content_phase is not null)))) or ((status = 'failed') and (stage = 'completed') and (completed_at is not null) and (superseded_at is null) and (error_code is not null) and (error_message_safe is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null)) or ((status = 'superseded') and (stage = 'completed') and (completed_at is not null) and (superseded_at is not null) and (error_code is null) and (error_message_safe is null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null)))) or ((((target_spec_json)::jsonb #>> '{schemaVersion}') = 'mira.learning.preparation-target.v2') and (catalog_build_id is not null) and (catalog_release_id is not null) and (content_target_count = (case grade_code when 'primary_1' then 30 when 'primary_2' then 27 when 'primary_3' then 27 when 'primary_4' then 27 when 'primary_5' then 27 when 'primary_6' then 27 else 0 end)) and (content_candidate_count = (case grade_code when 'primary_1' then 30 when 'primary_2' then 27 when 'primary_3' then 27 when 'primary_4' then 27 when 'primary_5' then 27 when 'primary_6' then 27 else 0 end)) and (content_failed_count = 0) and (content_canary_target_count = 3) and (content_canary_candidate_count = 3) and (content_canary_failed_count = 0) and (content_canary_passed_at is not null) and (content_generation_completed_at is not null) and (((status = 'running') and (stage = 'building_classrooms') and (ready_course_count = 0) and (failed_course_count = 0) and (progress_percent = 35) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'running') and (stage in ('building_classrooms','generating_speech','validating','publishing')) and (next_run_at is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((stage = 'building_classrooms') and (progress_percent between 40 and 64)) or ((stage = 'generating_speech') and (progress_percent between 65 and 84)) or ((stage = 'validating') and (progress_percent between 85 and 94)) or ((stage = 'publishing') and (progress_percent between 95 and 99)))) or ((status = 'running') and (stage in ('building_classrooms','generating_speech','validating','publishing')) and (next_run_at is not null) and (lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (resume_stage is null) and (work_unit_kind is not null) and (work_unit_kind = 'coordinator') and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null) and (((stage = 'building_classrooms') and (progress_percent between 40 and 64)) or ((stage = 'generating_speech') and (progress_percent between 65 and 84)) or ((stage = 'validating') and (progress_percent between 85 and 94)) or ((stage = 'publishing') and (progress_percent between 95 and 99)))) or ((status = 'queued') and (stage = 'retry_wait') and (next_run_at is not null) and (hard_deadline_at is not null) and (next_run_at <= hard_deadline_at) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (resume_stage is not null) and (resume_stage in ('building_classrooms','generating_speech','validating','publishing')) and (work_unit_kind is not null) and (work_unit_kind = 'coordinator') and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is not null) and (retry_message_safe is not null) and (completed_at is null) and (superseded_at is null) and (error_code is null) and (error_message_safe is null)) or ((status = 'ready') and (stage = 'completed') and (completed_at is not null) and (superseded_at is null) and (progress_percent = 100) and (ready_course_count = total_course_count) and (failed_course_count = 0) and (error_code is null) and (error_message_safe is null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null)) or ((status = 'failed') and (stage = 'completed') and (completed_at is not null) and (superseded_at is null) and (error_code is not null) and (error_message_safe is not null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null)) or ((status = 'superseded') and (stage = 'completed') and (completed_at is not null) and (superseded_at is not null) and (error_code is null) and (error_message_safe is null) and (lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null) and (next_run_at is null) and (hard_deadline_at is null) and (resume_stage is null) and (work_unit_kind is null) and (bound_catalog_item_id is null) and (bound_content_attempt_ordinal is null) and (bound_content_phase is null) and (retry_reason_code is null) and (retry_message_safe is null)))))) end) = true),
  CONSTRAINT chk_learning_prep_json CHECK ((pg_input_is_valid(target_spec_json, 'jsonb')) and (pg_input_is_valid(subject_progress_json, 'jsonb'))),
  CONSTRAINT chk_learning_prep_lease_group CHECK (((lease_token is null) and (lease_expires_at is null) and (heartbeat_at is null)) or ((lease_token is not null) and (lease_expires_at is not null) and (heartbeat_at is not null))),
  CONSTRAINT chk_learning_prep_retry CHECK (((retry_ordinal = 0) and (retry_of_plan_id is null)) or ((retry_ordinal = 1) and (retry_of_plan_id is not null))),
  CONSTRAINT chk_learning_prep_retry_ordinal CHECK (retry_ordinal between 0 and 1),
  CONSTRAINT chk_learning_prep_stage CHECK (stage in ('queued','planning','generating_content','building_classrooms','generating_speech','validating','publishing','retry_wait','completed')),
  CONSTRAINT chk_learning_prep_stage_progress_json CHECK ((stage_progress_json is not null) and (pg_input_is_valid(stage_progress_json, 'jsonb')) and (mysql_json_type((stage_progress_json)::jsonb) = 'OBJECT') and (mysql_json_length((stage_progress_json)::jsonb) = 6) and (((stage_progress_json)::jsonb #> '{candidateCount}') is not null) and (((stage_progress_json)::jsonb #> '{canaryCandidateCount}') is not null) and (((stage_progress_json)::jsonb #> '{canaryFailedCount}') is not null) and (((stage_progress_json)::jsonb #> '{canaryTargetCount}') is not null) and (((stage_progress_json)::jsonb #> '{failedCount}') is not null) and (((stage_progress_json)::jsonb #> '{targetCount}') is not null) and (mysql_json_type(((stage_progress_json)::jsonb #> '{candidateCount}')) = 'INTEGER') and (mysql_json_type(((stage_progress_json)::jsonb #> '{canaryCandidateCount}')) = 'INTEGER') and (mysql_json_type(((stage_progress_json)::jsonb #> '{canaryFailedCount}')) = 'INTEGER') and (mysql_json_type(((stage_progress_json)::jsonb #> '{canaryTargetCount}')) = 'INTEGER') and (mysql_json_type(((stage_progress_json)::jsonb #> '{failedCount}')) = 'INTEGER') and (mysql_json_type(((stage_progress_json)::jsonb #> '{targetCount}')) = 'INTEGER') and ((((stage_progress_json)::jsonb #>> '{candidateCount}'))::bigint = content_candidate_count) and ((((stage_progress_json)::jsonb #>> '{canaryCandidateCount}'))::bigint = content_canary_candidate_count) and ((((stage_progress_json)::jsonb #>> '{canaryFailedCount}'))::bigint = content_canary_failed_count) and ((((stage_progress_json)::jsonb #>> '{canaryTargetCount}'))::bigint = content_canary_target_count) and ((((stage_progress_json)::jsonb #>> '{failedCount}'))::bigint = content_failed_count) and ((((stage_progress_json)::jsonb #>> '{targetCount}'))::bigint = content_target_count)),
  CONSTRAINT chk_learning_prep_status CHECK (status in ('queued','running','ready','failed','superseded'))
);
CREATE INDEX fk_learning_prep_family ON learning_curriculum_preparation_plans (family_id);
CREATE INDEX fk_learning_prep_formal_history_exact ON learning_curriculum_preparation_plans (formal_publication_history_id, grade_code, target_fingerprint, formal_contract_version, catalog_release_id, formal_publication_receipt_hash);
CREATE INDEX idx_learning_prep_claim ON learning_curriculum_preparation_plans (status, stage, next_run_at, lease_expires_at);
CREATE INDEX idx_learning_prep_content_claim ON learning_curriculum_preparation_plans (status, stage, next_run_at, work_unit_kind);

CREATE TABLE learning_formal_qwen_audio_jobs (
  build_item_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  runtime_request_id varchar(128) NOT NULL,
  upstream_classroom_id varchar(255) NOT NULL,
  classroom_content_sha256 varchar(64) NOT NULL,
  subject varchar(16) NOT NULL,
  language_code varchar(16) NOT NULL,
  teacher_profile_id varchar(128) NOT NULL,
  teacher_profile_version integer NOT NULL,
  teacher_profile_hash varchar(64) NOT NULL,
  teacher_name varchar(128) NOT NULL,
  teacher_gender varchar(16) NOT NULL,
  voice_gender varchar(16) NOT NULL,
  voice_contract_version varchar(128) NOT NULL,
  tts_provider_id varchar(32) NOT NULL,
  tts_model_id varchar(64) NOT NULL,
  tts_voice_id varchar(64) NOT NULL,
  tts_fallback_allowed smallint DEFAULT 0 NOT NULL,
  asr_provider_id varchar(32) NOT NULL,
  asr_model_id varchar(64) NOT NULL,
  asr_fallback_allowed smallint DEFAULT 0 NOT NULL,
  audio_contract_version varchar(128) NOT NULL,
  pcm_validation_contract_version varchar(128) NOT NULL,
  asr_roundtrip_contract_version varchar(128) NOT NULL,
  speech_manifest_sha256 varchar(64) NOT NULL,
  expected_segment_count integer NOT NULL,
  legacy_media_job_id varchar(128),
  state varchar(32) DEFAULT 'pending' NOT NULL,
  tts_attempted_count integer DEFAULT 0 NOT NULL,
  tts_completed_count integer DEFAULT 0 NOT NULL,
  audio_validated_count integer DEFAULT 0 NOT NULL,
  asr_attempted_count integer DEFAULT 0 NOT NULL,
  asr_passed_count integer DEFAULT 0 NOT NULL,
  claim_token varchar(128),
  claim_deadline_at bigint,
  heartbeat_at bigint,
  safe_error_code varchar(128),
  terminal_receipt_version varchar(128),
  terminal_receipt_hash varchar(64),
  started_at bigint,
  terminal_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (build_item_id),
  CONSTRAINT uq_formal_qwen_audio_job_provider_binding UNIQUE (build_item_id, runtime_classroom_id, terminal_receipt_hash, state),
  CONSTRAINT uq_formal_qwen_audio_job_release_item UNIQUE (release_id, build_item_id),
  CONSTRAINT uq_formal_qwen_audio_job_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_formal_qwen_audio_job_runtime_request UNIQUE (runtime_request_id),
  CONSTRAINT uq_formal_qwen_audio_job_upstream UNIQUE (upstream_classroom_id),
  CONSTRAINT chk_formal_qwen_audio_job_counts CHECK ((expected_segment_count between 1 and 240) and (0 <= asr_passed_count) and (asr_passed_count <= asr_attempted_count) and (asr_attempted_count <= audio_validated_count) and (audio_validated_count <= tts_completed_count) and (tts_completed_count <= tts_attempted_count) and (tts_attempted_count <= expected_segment_count)),
  CONSTRAINT chk_formal_qwen_audio_job_identity CHECK ((grade_code <> '') and (package_version > 0) and (target_fingerprint ~* '^[0-9a-f]{64}$') and (classroom_content_sha256 ~* '^[0-9a-f]{64}$') and (teacher_profile_hash ~* '^[0-9a-f]{64}$') and (speech_manifest_sha256 ~* '^[0-9a-f]{64}$') and (audio_contract_version = 'mira.learning.formal-qwen-audio.v1') and (pcm_validation_contract_version = 'mira.learning.formal-pcm-validation.v1') and (asr_roundtrip_contract_version = 'mira.learning.formal-qwen-asr-roundtrip.v1')),
  CONSTRAINT chk_formal_qwen_audio_job_terminal CHECK ((state in ('pending','processing','auto_validated','failed','ambiguous')) and (created_at > 0) and (updated_at >= created_at) and (((state = 'pending') and (claim_token is null) and (claim_deadline_at is null) and (heartbeat_at is null) and (safe_error_code is null) and (terminal_receipt_version is null) and (terminal_receipt_hash is null) and (started_at is null) and (terminal_at is null)) or ((state = 'processing') and (claim_token is not null) and (claim_token <> '') and (claim_deadline_at is not null) and (claim_deadline_at > 0) and (heartbeat_at is not null) and (heartbeat_at > 0) and (safe_error_code is null) and (terminal_receipt_version is null) and (terminal_receipt_hash is null) and (started_at is not null) and (started_at > 0) and (terminal_at is null)) or ((state = 'auto_validated') and (tts_attempted_count = expected_segment_count) and (tts_completed_count = expected_segment_count) and (audio_validated_count = expected_segment_count) and (asr_attempted_count = expected_segment_count) and (asr_passed_count = expected_segment_count) and (claim_token is null) and (claim_deadline_at is null) and (safe_error_code is null) and (terminal_receipt_version is not null) and (terminal_receipt_version <> '') and (terminal_receipt_hash ~* '^[0-9a-f]{64}$') and (terminal_at is not null) and (terminal_at > 0)) or ((state in ('failed','ambiguous')) and (claim_token is null) and (claim_deadline_at is null) and (safe_error_code is not null) and (safe_error_code <> '') and (terminal_receipt_version is not null) and (terminal_receipt_version <> '') and (terminal_receipt_hash ~* '^[0-9a-f]{64}$') and (terminal_at is not null) and (terminal_at > 0)))),
  CONSTRAINT chk_formal_qwen_audio_job_voice CHECK ((voice_contract_version = 'mira.openmaic.formal-subject-qwen3-voice.v1') and (tts_provider_id = 'qwen-tts') and (tts_model_id = 'qwen3-tts-flash') and (tts_fallback_allowed = 0) and (asr_provider_id = 'qwen-asr') and (asr_model_id = 'qwen3-asr-flash') and (asr_fallback_allowed = 0) and (((subject = 'chinese') and (language_code = 'zh-CN') and (teacher_profile_id = 'mira_chinese_gentle') and (teacher_profile_version = 2) and (teacher_profile_hash = 'a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8') and (teacher_name = '小语老师') and (teacher_gender = 'female') and (voice_gender = 'female') and (tts_voice_id = 'Serena')) or ((subject = 'math') and (language_code = 'zh-CN') and (teacher_profile_id = 'mira_math_clear') and (teacher_profile_version = 2) and (teacher_profile_hash = '4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb') and (teacher_name = '小数老师') and (teacher_gender = 'male') and (voice_gender = 'male') and (tts_voice_id = 'Ethan')) or ((subject = 'english') and (language_code = 'en-US') and (teacher_profile_id = 'mira_english_standard') and (teacher_profile_version = 2) and (teacher_profile_hash = '4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040') and (teacher_name = 'Mia 老师') and (teacher_gender = 'female') and (voice_gender = 'female') and (tts_voice_id = 'Jennifer'))))
);
CREATE INDEX fk_formal_qwen_audio_job_course ON learning_formal_qwen_audio_jobs (course_id, course_version);
CREATE INDEX fk_formal_qwen_audio_job_legacy_media ON learning_formal_qwen_audio_jobs (legacy_media_job_id);
CREATE INDEX fk_formal_qwen_audio_job_package ON learning_formal_qwen_audio_jobs (package_id, package_version);
CREATE INDEX idx_formal_qwen_audio_jobs_claim ON learning_formal_qwen_audio_jobs (state, claim_deadline_at, created_at);
CREATE INDEX idx_formal_qwen_audio_jobs_release ON learning_formal_qwen_audio_jobs (release_id, grade_code, state);

CREATE TABLE learning_formal_qwen_audio_segment_receipts (
  build_item_id varchar(128) NOT NULL,
  scene_order integer NOT NULL,
  scene_id varchar(128) NOT NULL,
  action_id varchar(128) NOT NULL,
  narration_segment_id varchar(128) NOT NULL,
  source_text_sha256 varchar(64) NOT NULL,
  tts_request_id varchar(128) NOT NULL,
  tts_request_sha256 varchar(64) NOT NULL,
  asr_request_id varchar(128) NOT NULL,
  asr_request_sha256 varchar(64),
  state varchar(32) DEFAULT 'pending' NOT NULL,
  tts_attempted_at bigint,
  tts_completed_at bigint,
  provider_audio_result_sha256 varchar(64),
  provider_media_url_sha256 varchar(64),
  runtime_audio_sha256 varchar(64),
  download_sha256 varchar(64),
  streamed_sha256 varchar(64),
  storage_key varchar(512),
  write_completed_at bigint,
  readback_sha256 varchar(64),
  readback_completed_at bigint,
  asset_id varchar(128),
  mime_type varchar(64),
  byte_size bigint,
  pcm_format integer,
  channel_count integer,
  bits_per_sample integer,
  sample_rate_hz integer,
  block_align integer,
  byte_rate integer,
  frame_count bigint,
  duration_ms bigint,
  normalized_peak_bps integer,
  overall_rms_bps integer,
  active_window_bps integer,
  audio_validated_at bigint,
  asr_attempted_at bigint,
  asr_completed_at bigint,
  asr_result_sha256 varchar(64),
  normalized_transcript_sha256 varchar(64),
  asr_similarity_bps integer,
  machine_receipt_version varchar(128),
  machine_receipt_hash varchar(64),
  safe_error_code varchar(128),
  terminal_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (build_item_id, scene_order),
  CONSTRAINT uq_formal_qwen_audio_segment_action UNIQUE (build_item_id, action_id),
  CONSTRAINT uq_formal_qwen_audio_segment_asr_request UNIQUE (asr_request_id),
  CONSTRAINT uq_formal_qwen_audio_segment_asset UNIQUE (asset_id),
  CONSTRAINT uq_formal_qwen_audio_segment_narration UNIQUE (narration_segment_id),
  CONSTRAINT uq_formal_qwen_audio_segment_provider_binding UNIQUE (build_item_id, scene_order, tts_request_id, runtime_audio_sha256, machine_receipt_hash, state),
  CONSTRAINT uq_formal_qwen_audio_segment_tts_request UNIQUE (tts_request_id),
  CONSTRAINT chk_formal_qwen_audio_segment_asr CHECK (((asr_attempted_at is null) and (asr_request_sha256 is null) and (asr_result_sha256 is null) and (normalized_transcript_sha256 is null) and (asr_similarity_bps is null)) or ((asr_attempted_at is not null) and (asr_request_sha256 ~* '^[0-9a-f]{64}$'))),
  CONSTRAINT chk_formal_qwen_audio_segment_identity CHECK ((scene_order between 0 and 239) and (scene_id <> '') and (action_id <> '') and (narration_segment_id <> '') and (source_text_sha256 ~* '^[0-9a-f]{64}$') and (tts_request_id <> '') and (tts_request_sha256 ~* '^[0-9a-f]{64}$')),
  CONSTRAINT chk_formal_qwen_audio_segment_pcm CHECK (((audio_validated_at is null) and (asset_id is null) and (mime_type is null) and (byte_size is null) and (pcm_format is null) and (channel_count is null) and (bits_per_sample is null) and (sample_rate_hz is null) and (block_align is null) and (byte_rate is null) and (frame_count is null) and (duration_ms is null) and (normalized_peak_bps is null) and (overall_rms_bps is null) and (active_window_bps is null)) or ((audio_validated_at is not null) and (asset_id is not null) and (mime_type = 'audio/wav') and (byte_size between 45 and 16777216) and (pcm_format = 1) and (channel_count = 1) and (bits_per_sample = 16) and (sample_rate_hz between 16000 and 48000) and (block_align = 2) and (byte_rate = (sample_rate_hz * 2)) and (frame_count > 0) and (duration_ms between 300 and 120000) and (normalized_peak_bps between 100 and 10000) and (overall_rms_bps between 30 and 10000) and (active_window_bps between 500 and 10000) and (runtime_audio_sha256 ~* '^[0-9a-f]{64}$') and (download_sha256 = runtime_audio_sha256) and (streamed_sha256 = runtime_audio_sha256) and (readback_sha256 = runtime_audio_sha256) and (write_completed_at is not null) and (readback_completed_at is not null))),
  CONSTRAINT chk_formal_qwen_audio_segment_state CHECK ((state in ('pending','tts_attempted','tts_completed','audio_validated','asr_attempted','auto_validated','failed','ambiguous')) and (created_at > 0) and (updated_at >= created_at) and ((tts_completed_at is null) or (tts_attempted_at is not null)) and ((audio_validated_at is null) or (tts_completed_at is not null)) and ((asr_attempted_at is null) or (audio_validated_at is not null)) and ((asr_completed_at is null) or (asr_attempted_at is not null)) and (((state = 'pending') and (tts_attempted_at is null) and (terminal_at is null)) or ((state = 'tts_attempted') and (tts_attempted_at is not null) and (tts_completed_at is null) and (terminal_at is null)) or ((state = 'tts_completed') and (tts_completed_at is not null) and (audio_validated_at is null) and (terminal_at is null)) or ((state = 'audio_validated') and (audio_validated_at is not null) and (asr_attempted_at is null) and (terminal_at is null)) or ((state = 'asr_attempted') and (asr_attempted_at is not null) and (asr_completed_at is null) and (terminal_at is null)) or ((state = 'auto_validated') and (asr_completed_at is not null) and (asr_similarity_bps between 8500 and 10000) and (machine_receipt_version is not null) and (machine_receipt_hash ~* '^[0-9a-f]{64}$') and (safe_error_code is null) and (terminal_at is not null)) or ((state in ('failed','ambiguous')) and (safe_error_code is not null) and (safe_error_code <> '') and (terminal_at is not null))))
);
CREATE INDEX idx_formal_qwen_audio_segment_scene ON learning_formal_qwen_audio_segment_receipts (build_item_id, scene_id);
CREATE INDEX idx_formal_qwen_audio_segments_state ON learning_formal_qwen_audio_segment_receipts (build_item_id, state, scene_order);

CREATE TABLE learning_lesson_package_assets (
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  asset_id varchar(128) NOT NULL,
  scene_id varchar(128) NOT NULL,
  usage_kind varchar(64) NOT NULL,
  required_asset smallint DEFAULT 1 NOT NULL,
  PRIMARY KEY (package_id, package_version, asset_id, scene_id, usage_kind)
);
CREATE INDEX fk_learning_lesson_package_asset_asset ON learning_lesson_package_assets (asset_id);

CREATE TABLE learning_lesson_package_private (
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  schema_version varchar(128) NOT NULL,
  payload_json text NOT NULL,
  content_hash varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (package_id, package_version)
);

CREATE TABLE learning_lesson_packages (
  id varchar(128) NOT NULL,
  version integer NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  source_course_content_hash varchar(64),
  schema_version varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  source_artifact_id varchar(128) NOT NULL,
  compiler_version varchar(128) NOT NULL,
  public_content_hash varchar(64) NOT NULL,
  private_content_hash varchar(64) NOT NULL,
  public_payload_json text NOT NULL,
  validation_report_json text NOT NULL,
  created_at bigint NOT NULL,
  published_at bigint,
  retired_at bigint,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id, version),
  CONSTRAINT uq_learning_lesson_package_public_hash UNIQUE (public_content_hash),
  CONSTRAINT uq_learning_package_formal_binding UNIQUE (id, version, course_id, course_version, public_content_hash)
);
CREATE INDEX fk_learning_lesson_package_source ON learning_lesson_packages (source_artifact_id);
CREATE INDEX idx_learning_lesson_packages_course ON learning_lesson_packages (course_id, course_version, status, published_at);

CREATE TABLE learning_mastery_states (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  node_code varchar(128) NOT NULL,
  subject varchar(64) NOT NULL,
  grade_code varchar(64) NOT NULL,
  attempts integer DEFAULT 0 NOT NULL,
  correct_count integer DEFAULT 0 NOT NULL,
  independent_correct_count integer DEFAULT 0 NOT NULL,
  hint_count integer DEFAULT 0 NOT NULL,
  latest_score integer DEFAULT 0 NOT NULL,
  mastery_level varchar(32) NOT NULL,
  last_practiced_at bigint NOT NULL,
  next_review_date varchar(10) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, grade_code, node_code, subject)
);
CREATE INDEX idx_learning_mastery_review ON learning_mastery_states (family_id, child_id, next_review_date, mastery_level);

CREATE TABLE learning_media_asset_variants (
  asset_id varchar(128) NOT NULL,
  variant_key varchar(64) NOT NULL,
  storage_key varchar(512) NOT NULL,
  content_hash varchar(64) NOT NULL,
  mime_type varchar(128) NOT NULL,
  byte_size bigint NOT NULL,
  duration_ms bigint,
  status varchar(32) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (asset_id, variant_key),
  CONSTRAINT uq_learning_media_variant_storage UNIQUE (storage_key)
);
CREATE INDEX idx_learning_media_variant_hash ON learning_media_asset_variants (content_hash);
CREATE INDEX idx_learning_media_variant_status ON learning_media_asset_variants (status, updated_at);

CREATE TABLE learning_media_assets (
  id varchar(128) NOT NULL,
  kind varchar(32) NOT NULL,
  storage_key varchar(512),
  content_hash varchar(64),
  mime_type varchar(128),
  byte_size bigint,
  width integer,
  height integer,
  duration_ms bigint,
  scan_status varchar(32) DEFAULT 'pending' NOT NULL,
  moderation_status varchar(32) DEFAULT 'pending' NOT NULL,
  transcode_status varchar(32) DEFAULT 'pending' NOT NULL,
  status varchar(32) DEFAULT 'pending' NOT NULL,
  source_type varchar(64),
  source_ref varchar(512),
  metadata_json text,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE learning_media_generation_jobs (
  id varchar(128) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(64) NOT NULL,
  package_id varchar(128),
  package_version integer,
  course_id varchar(255),
  course_version varchar(64),
  subject varchar(64) NOT NULL,
  language_code varchar(32) NOT NULL,
  pronunciation_kind varchar(32) NOT NULL,
  teacher_profile_id varchar(128) NOT NULL,
  teacher_profile_version integer NOT NULL,
  provider_id varchar(64) NOT NULL,
  provider_model varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  segment_count integer DEFAULT 0 NOT NULL,
  asset_count integer DEFAULT 0 NOT NULL,
  error_code varchar(128),
  error_message_safe varchar(512),
  started_at bigint,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_media_job_idempotency UNIQUE (idempotency_key)
);
CREATE INDEX fk_learning_media_job_teacher ON learning_media_generation_jobs (teacher_profile_id, teacher_profile_version);
CREATE INDEX idx_learning_media_jobs_course ON learning_media_generation_jobs (course_id, course_version, status, created_at);
CREATE INDEX idx_learning_media_jobs_package ON learning_media_generation_jobs (package_id, package_version, status, created_at);
CREATE INDEX idx_learning_media_jobs_queue ON learning_media_generation_jobs (status, created_at, id);

CREATE TABLE learning_media_quality_reviews (
  id varchar(128) NOT NULL,
  asset_id varchar(128) NOT NULL,
  review_kind varchar(64) NOT NULL,
  required_review smallint DEFAULT 1 NOT NULL,
  status varchar(32) NOT NULL,
  reviewer_type varchar(32),
  reviewer_id varchar(255),
  findings_json text NOT NULL,
  notes text,
  reviewed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_media_review_kind UNIQUE (asset_id, review_kind)
);
CREATE INDEX idx_learning_media_review_asset ON learning_media_quality_reviews (asset_id, status);
CREATE INDEX idx_learning_media_review_queue ON learning_media_quality_reviews (required_review, status, review_kind, created_at);

CREATE TABLE learning_narration_segments (
  id varchar(128) NOT NULL,
  job_id varchar(128) NOT NULL,
  segment_index integer NOT NULL,
  scene_id varchar(128),
  action_id varchar(128),
  source_text text NOT NULL,
  subtitle_text text NOT NULL,
  text_hash varchar(64) NOT NULL,
  language_code varchar(32) NOT NULL,
  pronunciation_kind varchar(32) NOT NULL,
  review_policy varchar(32) NOT NULL,
  status varchar(32) NOT NULL,
  asset_id varchar(128),
  audio_checksum varchar(64),
  duration_ms bigint,
  error_code varchar(128),
  error_message_safe varchar(512),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_narration_job_index UNIQUE (job_id, segment_index)
);
CREATE INDEX idx_learning_narration_asset ON learning_narration_segments (asset_id);
CREATE INDEX idx_learning_narration_job_status ON learning_narration_segments (job_id, status, segment_index);

CREATE TABLE learning_openmaic_conversation_probes (
  id varchar(128) NOT NULL,
  ticket_hash varchar(64) NOT NULL,
  runtime_token_hash varchar(64),
  runtime_session_id varchar(128),
  runtime_classroom_id varchar(128) NOT NULL,
  upstream_classroom_id varchar(255) NOT NULL,
  candidate_kind varchar(32) DEFAULT 'release' NOT NULL,
  deterministic_recovery_id varchar(128),
  tts_credential_recovery_id varchar(128),
  challenge varchar(128) NOT NULL,
  expires_at bigint NOT NULL,
  consumed_at bigint,
  revoked_at bigint,
  chat_receipt_json text,
  transcription_receipt_json text,
  finalized_at bigint,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_probe_provider_binding UNIQUE (id, runtime_classroom_id),
  CONSTRAINT uq_openmaic_probe_runtime_classroom UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_openmaic_probe_runtime_session UNIQUE (runtime_session_id),
  CONSTRAINT uq_openmaic_probe_runtime_token UNIQUE (runtime_token_hash),
  CONSTRAINT uq_openmaic_probe_ticket UNIQUE (ticket_hash),
  CONSTRAINT uq_openmaic_probe_tts_credential_child UNIQUE (tts_credential_recovery_id),
  CONSTRAINT chk_openmaic_probe_candidate_kind CHECK (candidate_kind in ('release','generation','recovery','tts_credential_recovery')),
  CONSTRAINT chk_openmaic_probe_recovery_binding CHECK (((candidate_kind = 'tts_credential_recovery') and (deterministic_recovery_id is not null) and (tts_credential_recovery_id is not null)) or ((candidate_kind = 'recovery') and (deterministic_recovery_id is not null) and (tts_credential_recovery_id is null)) or ((candidate_kind in ('release','generation')) and (deterministic_recovery_id is null) and (tts_credential_recovery_id is null)))
);
CREATE INDEX fk_openmaic_probe_recovery ON learning_openmaic_conversation_probes (deterministic_recovery_id);
CREATE INDEX idx_openmaic_probe_runtime ON learning_openmaic_conversation_probes (runtime_classroom_id, expires_at);

CREATE TABLE learning_openmaic_deterministic_recoveries (
  id varchar(128) NOT NULL,
  recovery_request_id varchar(128) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  mode varchar(64) NOT NULL,
  kind varchar(96) NOT NULL,
  status varchar(32) NOT NULL,
  dispatch_count integer DEFAULT 1 NOT NULL,
  first_dispatch_error_code varchar(128),
  first_dispatch_error_message_safe varchar(512),
  first_dispatch_rejected_at bigint,
  source_runtime_status varchar(32) NOT NULL,
  source_runtime_error_code varchar(128) NOT NULL,
  source_runtime_error_message_safe varchar(512),
  source_upstream_job_id varchar(128) NOT NULL,
  source_job_status varchar(32) NOT NULL,
  source_job_error varchar(128) NOT NULL,
  source_scenes_generated integer NOT NULL,
  source_total_scenes integer NOT NULL,
  source_completed_at varchar(64) NOT NULL,
  source_job_snapshot_sha256 varchar(64) NOT NULL,
  source_generation_contract_sha256 varchar(64) NOT NULL,
  expected_upstream_recovery_id varchar(128) NOT NULL,
  upstream_recovery_id varchar(128),
  policy_id varchar(128),
  policy_version varchar(128),
  canonical_spec_sha256 varchar(64),
  code_patch_sha256 varchar(64),
  llm_call_count integer DEFAULT 0 NOT NULL,
  web_search_call_count integer DEFAULT 0 NOT NULL,
  image_generation_call_count integer DEFAULT 0 NOT NULL,
  video_generation_call_count integer DEFAULT 0 NOT NULL,
  tts_expected_call_count integer DEFAULT 10 NOT NULL,
  tts_attempted_call_count integer DEFAULT 0 NOT NULL,
  tts_completed_call_count integer DEFAULT 0 NOT NULL,
  tts_provider_id varchar(64) NOT NULL,
  tts_model_id varchar(128) NOT NULL,
  tts_voice_id varchar(128) NOT NULL,
  tts_fallback_used smallint DEFAULT 0 NOT NULL,
  tts_verified_asset_count integer,
  upstream_classroom_id varchar(255),
  scene_count integer,
  content_sha256 varchar(64),
  final_artifact_sha256 varchar(64),
  artifact_created_at varchar(64),
  static_contract_verified smallint DEFAULT 0 NOT NULL,
  conversation_probe_verified smallint DEFAULT 0 NOT NULL,
  verified_at bigint,
  receipt_json text,
  error_code varchar(128),
  error_message_safe varchar(512),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  terminal_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_recovery_classroom UNIQUE (upstream_classroom_id),
  CONSTRAINT uq_openmaic_recovery_expected_upstream UNIQUE (expected_upstream_recovery_id),
  CONSTRAINT uq_openmaic_recovery_request UNIQUE (recovery_request_id),
  CONSTRAINT uq_openmaic_recovery_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_openmaic_recovery_upstream UNIQUE (upstream_recovery_id),
  CONSTRAINT chk_openmaic_recovery_call_counts CHECK ((llm_call_count = 0) and (web_search_call_count = 0) and (image_generation_call_count = 0) and (video_generation_call_count = 0) and (tts_expected_call_count = 10) and (tts_attempted_call_count >= 0) and (tts_attempted_call_count <= tts_expected_call_count) and (tts_completed_call_count >= 0) and (tts_completed_call_count <= tts_attempted_call_count) and (tts_provider_id = 'qwen-tts') and (tts_model_id = 'qwen3-tts-flash') and (tts_voice_id = 'Serena') and (tts_fallback_used = 0)),
  CONSTRAINT chk_openmaic_recovery_dispatch_count CHECK (((dispatch_count = 1) and (first_dispatch_error_code is null) and (first_dispatch_error_message_safe is null) and (first_dispatch_rejected_at is null)) or ((dispatch_count = 2) and (first_dispatch_error_code = 'openmaic_recovery_upstream_rejected') and (first_dispatch_error_message_safe is not null) and (first_dispatch_rejected_at is not null))),
  CONSTRAINT chk_openmaic_recovery_kind CHECK (kind = 'mira_sample_deterministic_no_llm_v1'),
  CONSTRAINT chk_openmaic_recovery_mode CHECK (mode = 'deterministic_no_llm'),
  CONSTRAINT chk_openmaic_recovery_source CHECK ((source_runtime_status = 'failed') and (source_runtime_error_code = 'openmaic_generation_failed') and (source_job_status = 'failed') and (source_job_error = 'structured_output_exhausted') and (source_total_scenes = 10) and (source_scenes_generated = 4)),
  CONSTRAINT chk_openmaic_recovery_status CHECK (status in ('recovering','validating','succeeded','failed')),
  CONSTRAINT chk_openmaic_recovery_success_complete CHECK ((status <> 'succeeded') or ((upstream_recovery_id is not null) and (upstream_recovery_id = expected_upstream_recovery_id) and (source_job_snapshot_sha256 is not null) and (policy_id is not null) and (policy_version is not null) and (canonical_spec_sha256 is not null) and (code_patch_sha256 is not null) and (upstream_classroom_id is not null) and (scene_count = 10) and (content_sha256 is not null) and (final_artifact_sha256 is not null) and (tts_attempted_call_count = 10) and (tts_completed_call_count = 10) and (tts_verified_asset_count = 10) and (static_contract_verified = 1) and (conversation_probe_verified = 1) and (verified_at is not null) and (receipt_json is not null) and (terminal_at is not null))),
  CONSTRAINT chk_openmaic_recovery_upstream_identity CHECK ((left(expected_upstream_recovery_id,6) = 'omrec_') and ((upstream_recovery_id is null) or (upstream_recovery_id = expected_upstream_recovery_id)))
);
CREATE INDEX idx_openmaic_recovery_status ON learning_openmaic_deterministic_recoveries (status, updated_at);

CREATE TABLE learning_openmaic_formal_citation_recoveries (
  id varchar(128) NOT NULL,
  recovery_request_id varchar(128) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  build_item_id varchar(128) NOT NULL,
  status varchar(32) NOT NULL,
  recovery_policy_version varchar(128) NOT NULL,
  source_runtime_status varchar(32) NOT NULL,
  source_quality_status varchar(32) NOT NULL,
  source_runtime_error_code varchar(128) NOT NULL,
  source_runtime_error_message_safe varchar(512),
  source_attempt_ordinal integer NOT NULL,
  source_provider_attempt_ordinal integer NOT NULL,
  source_runtime_request_id varchar(128) NOT NULL,
  source_upstream_job_id varchar(128) NOT NULL,
  source_formal_input_sha256 varchar(64) NOT NULL,
  source_job_status varchar(32) NOT NULL,
  source_job_error varchar(128) NOT NULL,
  source_job_completed_at varchar(64),
  source_job_snapshot_sha256 varchar(64),
  upstream_recovery_id varchar(128),
  response_schema_version varchar(128),
  response_kind varchar(64),
  llm_call_count integer,
  web_search_call_count integer,
  fetch_url_call_count integer,
  image_generation_call_count integer,
  video_generation_call_count integer,
  repair_policy_version varchar(128),
  repair_before_scenes_sha256 varchar(64),
  repair_after_scenes_sha256 varchar(64),
  repair_sha256 varchar(64),
  repair_json text,
  upstream_classroom_id varchar(255),
  result_scene_count integer,
  result_speech_action_count integer,
  formal_audio_receipt_sha256 varchar(64),
  professional_creation_receipt_sha256 varchar(64),
  research_receipt_sha256 varchar(64),
  result_json text,
  response_receipt_json text,
  response_receipt_sha256 varchar(64),
  error_code varchar(128),
  error_message_safe varchar(512),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  terminal_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_formal_citation_classroom UNIQUE (upstream_classroom_id),
  CONSTRAINT uq_openmaic_formal_citation_item UNIQUE (build_item_id),
  CONSTRAINT uq_openmaic_formal_citation_request UNIQUE (recovery_request_id),
  CONSTRAINT uq_openmaic_formal_citation_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_openmaic_formal_citation_upstream UNIQUE (upstream_recovery_id),
  CONSTRAINT chk_openmaic_formal_citation_source CHECK ((source_runtime_status = 'failed') and (source_quality_status = 'rejected') and (source_runtime_error_code = 'openmaic_formal_generation_failed') and (source_attempt_ordinal = 2) and (source_provider_attempt_ordinal = 2) and (source_job_status = 'failed') and (source_job_error = 'FORMAL_PROFESSIONAL_RESEARCH_CITATION_MISSING') and (source_formal_input_sha256 ~* '^[0-9a-f]{64}$')),
  CONSTRAINT chk_openmaic_formal_citation_status CHECK ((status in ('reserving','running','succeeded','failed')) and (recovery_policy_version = 'mira-formal-citation-recovery.v1')),
  CONSTRAINT chk_openmaic_formal_citation_success CHECK ((status <> 'succeeded') or ((upstream_recovery_id is not null) and (response_schema_version = 'mira.openmaic.formal-citation-recovery.v1') and (response_kind = 'formal_citation_recovery') and (source_job_completed_at is not null) and (source_job_snapshot_sha256 is not null) and (repair_policy_version = 'mira-formal-citation-footer-canonicalize.v1') and (repair_before_scenes_sha256 is not null) and (repair_after_scenes_sha256 is not null) and (repair_sha256 is not null) and (repair_json is not null) and (upstream_classroom_id is not null) and (result_scene_count between 1 and 60) and (result_speech_action_count >= result_scene_count) and (result_speech_action_count <= 240) and (formal_audio_receipt_sha256 is not null) and (professional_creation_receipt_sha256 is not null) and (research_receipt_sha256 is not null) and (result_json is not null) and (response_receipt_json is not null) and (response_receipt_sha256 is not null) and (error_code is null) and (error_message_safe is null))),
  CONSTRAINT chk_openmaic_formal_citation_terminal CHECK (((status in ('reserving','running')) and (terminal_at is null)) or ((status in ('succeeded','failed')) and (terminal_at is not null))),
  CONSTRAINT chk_openmaic_formal_citation_zero_calls CHECK (((status = 'reserving') and (llm_call_count is null) and (web_search_call_count is null) and (fetch_url_call_count is null) and (image_generation_call_count is null) and (video_generation_call_count is null)) or ((status <> 'reserving') and (llm_call_count = 0) and (web_search_call_count = 0) and (fetch_url_call_count = 0) and (image_generation_call_count = 0) and (video_generation_call_count = 0)))
);
CREATE INDEX idx_openmaic_formal_citation_status ON learning_openmaic_formal_citation_recoveries (status, updated_at);

CREATE TABLE learning_openmaic_provider_circuits (
  circuit_key varchar(128) NOT NULL,
  provider_id varchar(64) NOT NULL,
  model_id varchar(128) NOT NULL,
  status varchar(16) NOT NULL,
  reason_code varchar(128),
  opened_by_runtime_id varchar(128),
  opened_at bigint,
  last_probe_at bigint,
  probe_succeeded_at bigint,
  closed_at bigint,
  revision integer DEFAULT 1 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (circuit_key),
  CONSTRAINT chk_openmaic_provider_circuit_revision CHECK (revision >= 1),
  CONSTRAINT chk_openmaic_provider_circuit_status CHECK (status in ('open','closed'))
);
CREATE INDEX fk_openmaic_provider_circuit_runtime ON learning_openmaic_provider_circuits (opened_by_runtime_id);
CREATE INDEX idx_openmaic_provider_circuit_status ON learning_openmaic_provider_circuits (status, updated_at);

CREATE TABLE learning_openmaic_provider_readiness_call_receipts (
  readiness_id varchar(128) NOT NULL,
  provider_contract_version varchar(128) NOT NULL,
  call_ordinal integer NOT NULL,
  kind varchar(32) NOT NULL,
  subject varchar(16),
  provider_id varchar(32) NOT NULL,
  model_id varchar(64) NOT NULL,
  voice_id varchar(64),
  language_code varchar(16),
  fallback_used smallint DEFAULT 0 NOT NULL,
  provider_call smallint DEFAULT 1 NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  response_sha256 varchar(64),
  state varchar(32) DEFAULT 'attempted' NOT NULL,
  attempted_at bigint NOT NULL,
  completed_at bigint,
  safe_error_code varchar(128),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (readiness_id, call_ordinal),
  CONSTRAINT uq_openmaic_provider_readiness_call_kind UNIQUE (readiness_id, kind, subject),
  CONSTRAINT chk_openmaic_provider_readiness_call_identity CHECK ((call_ordinal between 1 and 5) and (fallback_used = 0) and (provider_call = 1) and (request_sha256 ~* '^[0-9a-f]{64}$') and (((provider_contract_version = 'mira.openmaic.formal-provider-readiness.v1') and (call_ordinal = 1) and (kind = 'kimi_text') and (subject is null) and (provider_id = 'kimi') and (model_id = 'kimi-k2.6') and (voice_id is null) and (language_code is null)) or ((provider_contract_version = 'mira.openmaic.formal-provider-readiness.v2') and (call_ordinal = 1) and (kind = 'deepseek_text') and (subject is null) and (provider_id = 'deepseek') and (model_id = 'deepseek-v4-pro') and (voice_id is null) and (language_code is null)) or ((provider_contract_version in ('mira.openmaic.formal-provider-readiness.v1','mira.openmaic.formal-provider-readiness.v2')) and (call_ordinal = 2) and (kind = 'qwen_asr') and (subject in ('chinese','math','english')) and (provider_id = 'qwen-asr') and (model_id = 'qwen3-asr-flash') and (voice_id is null) and (((subject in ('chinese','math')) and (language_code = 'zh-CN')) or ((subject = 'english') and (language_code = 'en-US')))) or ((provider_contract_version in ('mira.openmaic.formal-provider-readiness.v1','mira.openmaic.formal-provider-readiness.v2')) and (call_ordinal = 3) and (kind = 'qwen_tts') and (subject = 'chinese') and (provider_id = 'qwen-tts') and (model_id = 'qwen3-tts-flash') and (voice_id = 'Serena') and (language_code = 'zh-CN')) or ((provider_contract_version in ('mira.openmaic.formal-provider-readiness.v1','mira.openmaic.formal-provider-readiness.v2')) and (call_ordinal = 4) and (kind = 'qwen_tts') and (subject = 'math') and (provider_id = 'qwen-tts') and (model_id = 'qwen3-tts-flash') and (voice_id = 'Ethan') and (language_code = 'zh-CN')) or ((provider_contract_version in ('mira.openmaic.formal-provider-readiness.v1','mira.openmaic.formal-provider-readiness.v2')) and (call_ordinal = 5) and (kind = 'qwen_tts') and (subject = 'english') and (provider_id = 'qwen-tts') and (model_id = 'qwen3-tts-flash') and (voice_id = 'Jennifer') and (language_code = 'en-US')))),
  CONSTRAINT chk_openmaic_provider_readiness_call_state CHECK ((state in ('attempted','passed','failed','ambiguous')) and (created_at > 0) and (updated_at >= created_at) and (attempted_at >= created_at) and (attempted_at <= updated_at) and (((state = 'attempted') and (completed_at is null) and (response_sha256 is null) and (safe_error_code is null)) or ((state = 'passed') and (completed_at is not null) and (completed_at >= attempted_at) and (response_sha256 ~* '^[0-9a-f]{64}$') and (safe_error_code is null)) or ((state in ('failed','ambiguous')) and (completed_at is not null) and (completed_at >= attempted_at) and (response_sha256 ~* '^[0-9a-f]{64}$') and (safe_error_code is not null) and (safe_error_code <> ''))))
);
CREATE INDEX idx_openmaic_provider_readiness_call_contract ON learning_openmaic_provider_readiness_call_receipts (readiness_id, provider_contract_version);
CREATE INDEX idx_openmaic_provider_readiness_calls ON learning_openmaic_provider_readiness_call_receipts (readiness_id, state, call_ordinal);

CREATE TABLE learning_openmaic_provider_readiness_jobs (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  build_item_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  runtime_request_id varchar(128) NOT NULL,
  upstream_classroom_id varchar(255) NOT NULL,
  classroom_content_sha256 varchar(64) NOT NULL,
  audio_job_terminal_receipt_hash varchar(64) NOT NULL,
  audio_job_state varchar(32) DEFAULT 'auto_validated' NOT NULL,
  validation_scene_order integer NOT NULL,
  validation_tts_request_id varchar(128) NOT NULL,
  validation_audio_sha256 varchar(64) NOT NULL,
  validation_audio_machine_receipt_hash varchar(64) NOT NULL,
  validation_segment_state varchar(32) DEFAULT 'auto_validated' NOT NULL,
  conversation_probe_id varchar(128) NOT NULL,
  route_session_contract_version varchar(128) NOT NULL,
  route_session_receipt_hash varchar(64) NOT NULL,
  route_session_provider_call smallint DEFAULT 0 NOT NULL,
  route_session_status varchar(32) DEFAULT 'passed' NOT NULL,
  route_session_completed_at bigint NOT NULL,
  provider_contract_version varchar(128) NOT NULL,
  expected_provider_call_count integer DEFAULT 5 NOT NULL,
  provider_attempted_count integer DEFAULT 0 NOT NULL,
  provider_passed_count integer DEFAULT 0 NOT NULL,
  provider_receipt_hash varchar(64),
  state varchar(32) DEFAULT 'pending' NOT NULL,
  claim_token varchar(128),
  claim_deadline_at bigint,
  heartbeat_at bigint,
  safe_error_code varchar(128),
  started_at bigint,
  terminal_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_provider_readiness_item UNIQUE (build_item_id),
  CONSTRAINT uq_openmaic_provider_readiness_job_contract UNIQUE (id, provider_contract_version),
  CONSTRAINT uq_openmaic_provider_readiness_release_canary UNIQUE (release_id, grade_code, target_fingerprint),
  CONSTRAINT uq_openmaic_provider_readiness_request UNIQUE (request_id),
  CONSTRAINT uq_openmaic_provider_readiness_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT chk_openmaic_provider_readiness_counts CHECK ((expected_provider_call_count = 5) and (0 <= provider_passed_count) and (provider_passed_count <= provider_attempted_count) and (provider_attempted_count <= expected_provider_call_count)),
  CONSTRAINT chk_openmaic_provider_readiness_identity CHECK ((request_sha256 ~* '^[0-9a-f]{64}$') and (grade_code <> '') and (target_fingerprint ~* '^[0-9a-f]{64}$') and (classroom_content_sha256 ~* '^[0-9a-f]{64}$') and (audio_job_terminal_receipt_hash ~* '^[0-9a-f]{64}$') and (audio_job_state = 'auto_validated') and (validation_scene_order between 0 and 239) and (validation_audio_sha256 ~* '^[0-9a-f]{64}$') and (validation_audio_machine_receipt_hash ~* '^[0-9a-f]{64}$') and (validation_segment_state = 'auto_validated') and (route_session_contract_version = 'mira.openmaic.conversation-proof.v1') and (route_session_receipt_hash ~* '^[0-9a-f]{64}$') and (route_session_provider_call = 0) and (route_session_status = 'passed') and (route_session_completed_at > 0) and (provider_contract_version in ('mira.openmaic.formal-provider-readiness.v1','mira.openmaic.formal-provider-readiness.v2'))),
  CONSTRAINT chk_openmaic_provider_readiness_state CHECK ((state in ('pending','processing','auto_validated','failed','ambiguous')) and (created_at > 0) and (updated_at >= created_at) and (((state = 'pending') and (provider_attempted_count = 0) and (provider_passed_count = 0) and (provider_receipt_hash is null) and (claim_token is null) and (claim_deadline_at is null) and (heartbeat_at is null) and (safe_error_code is null) and (started_at is null) and (terminal_at is null)) or ((state = 'processing') and (provider_receipt_hash is null) and (claim_token is not null) and (claim_token <> '') and (claim_deadline_at is not null) and (claim_deadline_at > 0) and (heartbeat_at is not null) and (heartbeat_at > 0) and (safe_error_code is null) and (started_at is not null) and (started_at > 0) and (terminal_at is null)) or ((state = 'auto_validated') and (provider_attempted_count = 5) and (provider_passed_count = 5) and (route_session_status = 'passed') and (route_session_provider_call = 0) and (provider_receipt_hash ~* '^[0-9a-f]{64}$') and (claim_token is null) and (claim_deadline_at is null) and (safe_error_code is null) and (terminal_at is not null) and (terminal_at >= route_session_completed_at)) or ((state in ('failed','ambiguous')) and (provider_receipt_hash ~* '^[0-9a-f]{64}$') and (claim_token is null) and (claim_deadline_at is null) and (safe_error_code is not null) and (safe_error_code <> '') and (terminal_at is not null) and (terminal_at > 0))))
);
CREATE INDEX fk_openmaic_provider_readiness_audio_job ON learning_openmaic_provider_readiness_jobs (build_item_id, runtime_classroom_id, audio_job_terminal_receipt_hash, audio_job_state);
CREATE INDEX fk_openmaic_provider_readiness_audio_segment ON learning_openmaic_provider_readiness_jobs (build_item_id, validation_scene_order, validation_tts_request_id, validation_audio_sha256, validation_audio_machine_receipt_hash, validation_segment_state);
CREATE INDEX fk_openmaic_provider_readiness_item_binding ON learning_openmaic_provider_readiness_jobs (build_item_id, release_id, runtime_classroom_id);
CREATE INDEX fk_openmaic_provider_readiness_probe_binding ON learning_openmaic_provider_readiness_jobs (conversation_probe_id, runtime_classroom_id);
CREATE INDEX idx_openmaic_provider_readiness_claim ON learning_openmaic_provider_readiness_jobs (state, claim_deadline_at, created_at);
CREATE INDEX idx_openmaic_provider_readiness_release ON learning_openmaic_provider_readiness_jobs (release_id, grade_code, state);

CREATE TABLE learning_openmaic_runtime_classrooms (
  id varchar(128) NOT NULL,
  request_id varchar(128) NOT NULL,
  attempt_ordinal integer DEFAULT 1 NOT NULL,
  provider_attempt_ordinal integer,
  retry_of_runtime_id varchar(128),
  retry_reason varchar(64),
  expected_previous_job_id varchar(128),
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  upstream_job_id varchar(128),
  upstream_classroom_id varchar(255),
  status varchar(32) NOT NULL,
  quality_status varchar(32) DEFAULT 'pending_review' NOT NULL,
  feature_manifest_json text NOT NULL,
  error_code varchar(128),
  error_message_safe varchar(512),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  ready_at bigint,
  reviewed_by varchar(128),
  reviewed_at bigint,
  review_notes varchar(1000),
  retired_at bigint,
  candidate_build_item_id varchar(128),
  candidate_release_id varchar(128),
  candidate_grade_code varchar(64),
  candidate_target_fingerprint varchar(64),
  candidate_binding_contract_version varchar(128),
  candidate_bound_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_openmaic_candidate_item_attempt UNIQUE (candidate_build_item_id, attempt_ordinal),
  CONSTRAINT uq_learning_openmaic_candidate_provider_attempt UNIQUE (candidate_build_item_id, provider_attempt_ordinal),
  CONSTRAINT uq_learning_openmaic_runtime_package_attempt UNIQUE (package_id, package_version, attempt_ordinal),
  CONSTRAINT uq_learning_openmaic_runtime_request UNIQUE (request_id),
  CONSTRAINT uq_learning_openmaic_runtime_retry_of UNIQUE (retry_of_runtime_id),
  CONSTRAINT uq_learning_openmaic_runtime_upstream UNIQUE (upstream_classroom_id),
  CONSTRAINT uq_learning_openmaic_runtime_upstream_job UNIQUE (upstream_job_id),
  CONSTRAINT uq_learning_runtime_formal_candidate UNIQUE (id, candidate_build_item_id, candidate_release_id, candidate_grade_code, candidate_target_fingerprint, candidate_binding_contract_version),
  CONSTRAINT uq_learning_runtime_formal_course UNIQUE (id, course_id, course_version),
  CONSTRAINT uq_learning_runtime_formal_package UNIQUE (id, package_id, package_version),
  CONSTRAINT uq_learning_runtime_formal_upstream UNIQUE (id, upstream_classroom_id),
  CONSTRAINT chk_learning_openmaic_candidate_binding CHECK (((candidate_build_item_id is null) and (candidate_release_id is null) and (candidate_grade_code is null) and (candidate_target_fingerprint is null) and (candidate_binding_contract_version is null) and (candidate_bound_at is null)) or ((candidate_build_item_id is not null) and (candidate_release_id is not null) and (candidate_grade_code is not null) and (candidate_grade_code <> '') and (candidate_target_fingerprint is not null) and (candidate_target_fingerprint ~* '^[0-9a-f]{64}$') and (candidate_binding_contract_version is not null) and (candidate_binding_contract_version <> '') and (candidate_bound_at is not null) and (candidate_bound_at > 0))),
  CONSTRAINT chk_learning_openmaic_runtime_candidate_attempt CHECK (((candidate_build_item_id is null) and (provider_attempt_ordinal is null) and (((attempt_ordinal = 1) and (retry_of_runtime_id is null) and (retry_reason is null) and (expected_previous_job_id is null)) or ((attempt_ordinal = 2) and (retry_of_runtime_id is not null) and (retry_reason = 'approved_stage2_retry') and (expected_previous_job_id is not null)) or ((attempt_ordinal = 3) and (retry_of_runtime_id is not null) and (retry_reason = 'approved_stage2_retry_3') and (expected_previous_job_id is not null)))) or ((candidate_build_item_id is not null) and (attempt_ordinal >= 1) and (attempt_ordinal <= 16) and ((provider_attempt_ordinal is null) or ((provider_attempt_ordinal >= 1) and (provider_attempt_ordinal <= 3))) and (((attempt_ordinal = 1) and (retry_of_runtime_id is null) and (retry_reason is null) and (expected_previous_job_id is null)) or ((attempt_ordinal >= 2) and (retry_of_runtime_id is not null) and (retry_reason = concat('formal_candidate_retry_',attempt_ordinal)) and (expected_previous_job_id is not null)))))
);
CREATE INDEX fk_learning_openmaic_candidate_release ON learning_openmaic_runtime_classrooms (candidate_release_id);
CREATE INDEX idx_learning_openmaic_runtime_course ON learning_openmaic_runtime_classrooms (course_id, course_version, status, updated_at);
CREATE INDEX idx_learning_openmaic_runtime_quality ON learning_openmaic_runtime_classrooms (status, quality_status, updated_at);

CREATE TABLE learning_openmaic_runtime_event_streams (
  runtime_session_id varchar(128) NOT NULL,
  learning_session_id varchar(255) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  upstream_classroom_id varchar(255) NOT NULL,
  principal_id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  release_id varchar(128) NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  expected_scene_count integer NOT NULL,
  last_sequence integer DEFAULT 0 NOT NULL,
  completed_at bigint,
  report_id varchar(255),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (runtime_session_id),
  CONSTRAINT uq_openmaic_runtime_stream_classroom UNIQUE (runtime_session_id, runtime_classroom_id, upstream_classroom_id),
  CONSTRAINT uq_openmaic_runtime_stream_learning UNIQUE (runtime_session_id, learning_session_id, family_id, child_id),
  CONSTRAINT chk_openmaic_runtime_stream_state CHECK ((target_fingerprint ~* '^[0-9a-f]{64}$') and (expected_scene_count between 1 and 60) and (last_sequence >= 0) and (((completed_at is null) and (report_id is null)) or ((completed_at is not null) and (completed_at > 0) and (report_id is not null))))
);
CREATE INDEX fk_openmaic_runtime_stream_classroom ON learning_openmaic_runtime_event_streams (runtime_classroom_id);
CREATE INDEX fk_openmaic_runtime_stream_release ON learning_openmaic_runtime_event_streams (release_id);
CREATE INDEX idx_openmaic_runtime_stream_learning ON learning_openmaic_runtime_event_streams (family_id, child_id, learning_session_id, updated_at);

CREATE TABLE learning_openmaic_runtime_events (
  id varchar(128) NOT NULL,
  runtime_session_id varchar(128) NOT NULL,
  sequence integer NOT NULL,
  idempotency_key varchar(64) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  event_type varchar(32) NOT NULL,
  scene_index integer NOT NULL,
  scene_id varchar(128) NOT NULL,
  action_id varchar(128),
  question_id varchar(128),
  attempt_number integer,
  payload_json text NOT NULL,
  authoritative_json text,
  response_json text NOT NULL,
  receipt_sha256 varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_runtime_event_idempotency UNIQUE (runtime_session_id, idempotency_key),
  CONSTRAINT uq_openmaic_runtime_event_receipt UNIQUE (runtime_session_id, receipt_sha256),
  CONSTRAINT uq_openmaic_runtime_event_sequence UNIQUE (runtime_session_id, sequence),
  CONSTRAINT chk_openmaic_runtime_event_identity CHECK ((sequence >= 1) and (idempotency_key ~* '^[0-9a-f]{64}$') and (request_sha256 ~* '^[0-9a-f]{64}$') and (receipt_sha256 ~* '^[0-9a-f]{64}$') and (event_type in ('scene_entered','action_completed','answer_submitted','asr_transcribed','interaction_completed','classroom_completed')) and (scene_index >= 0) and (scene_index < 60) and (((event_type = 'scene_entered') and (action_id is null) and (question_id is null) and (attempt_number is null)) or ((event_type = 'action_completed') and (action_id is not null) and (question_id is null) and (attempt_number is null)) or ((event_type = 'answer_submitted') and (action_id is null) and (question_id is not null) and (attempt_number = 1)) or ((event_type = 'asr_transcribed') and (action_id is null) and (question_id is null) and (attempt_number is null)) or ((event_type = 'interaction_completed') and (action_id is null) and (question_id is null) and (attempt_number is null)) or ((event_type = 'classroom_completed') and (action_id is null) and (question_id is null) and (attempt_number is null))))
);
CREATE INDEX idx_openmaic_runtime_event_scene ON learning_openmaic_runtime_events (runtime_session_id, event_type, scene_index, sequence);

CREATE TABLE learning_openmaic_tts_credential_recoveries (
  id varchar(128) NOT NULL,
  recovery_request_id varchar(128) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  parent_recovery_id varchar(128) NOT NULL,
  mode varchar(64) NOT NULL,
  kind varchar(96) NOT NULL,
  status varchar(32) NOT NULL,
  parent_status varchar(32) NOT NULL,
  parent_dispatch_count integer NOT NULL,
  parent_error_code varchar(128) NOT NULL,
  parent_error_message_safe varchar(512) NOT NULL,
  parent_terminal_at bigint NOT NULL,
  parent_expected_upstream_recovery_id varchar(128) NOT NULL,
  parent_upstream_recovery_id varchar(128) NOT NULL,
  parent_db_snapshot_sha256 varchar(64) NOT NULL,
  parent_receipt_sha256 varchar(64) NOT NULL,
  parent_runtime_snapshot_sha256 varchar(64) NOT NULL,
  source_upstream_job_id varchar(128) NOT NULL,
  source_job_snapshot_sha256 varchar(64) NOT NULL,
  source_generation_contract_sha256 varchar(64) NOT NULL,
  parent_policy_id varchar(128) NOT NULL,
  parent_policy_version varchar(128) NOT NULL,
  parent_canonical_spec_sha256 varchar(64) NOT NULL,
  parent_code_patch_sha256 varchar(64) NOT NULL,
  parent_tts_expected_call_count integer NOT NULL,
  parent_tts_attempted_call_count integer NOT NULL,
  parent_tts_completed_call_count integer NOT NULL,
  expected_upstream_child_id varchar(128) NOT NULL,
  upstream_child_id varchar(128),
  expected_upstream_classroom_id varchar(255) NOT NULL,
  upstream_classroom_id varchar(255),
  policy_version varchar(128),
  classroom_policy_version varchar(128),
  canonical_spec_sha256 varchar(64),
  parent_patch_sha256 varchar(64),
  code_patch_sha256 varchar(64),
  llm_call_count integer DEFAULT 0 NOT NULL,
  web_search_call_count integer DEFAULT 0 NOT NULL,
  image_generation_call_count integer DEFAULT 0 NOT NULL,
  video_generation_call_count integer DEFAULT 0 NOT NULL,
  tts_expected_call_count integer DEFAULT 10 NOT NULL,
  tts_attempted_call_count integer DEFAULT 0 NOT NULL,
  tts_completed_call_count integer DEFAULT 0 NOT NULL,
  tts_provider_id varchar(64) NOT NULL,
  tts_model_id varchar(128) NOT NULL,
  tts_voice_id varchar(128) NOT NULL,
  tts_fallback_used smallint DEFAULT 0 NOT NULL,
  tts_verified_asset_count integer,
  scene_count integer,
  audio_count integer,
  content_sha256 varchar(64),
  final_artifact_sha256 varchar(64),
  artifact_created_at varchar(64),
  static_contract_verified smallint DEFAULT 0 NOT NULL,
  conversation_probe_verified smallint DEFAULT 0 NOT NULL,
  conversation_probe_id varchar(128),
  verified_at bigint,
  receipt_json text,
  error_code varchar(128),
  error_message_safe varchar(512),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  terminal_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_openmaic_tts_child_classroom UNIQUE (upstream_classroom_id),
  CONSTRAINT uq_openmaic_tts_child_expected UNIQUE (expected_upstream_child_id),
  CONSTRAINT uq_openmaic_tts_child_expected_classroom UNIQUE (expected_upstream_classroom_id),
  CONSTRAINT uq_openmaic_tts_child_parent UNIQUE (parent_recovery_id),
  CONSTRAINT uq_openmaic_tts_child_probe UNIQUE (conversation_probe_id),
  CONSTRAINT uq_openmaic_tts_child_request UNIQUE (recovery_request_id),
  CONSTRAINT uq_openmaic_tts_child_runtime UNIQUE (runtime_classroom_id),
  CONSTRAINT uq_openmaic_tts_child_upstream UNIQUE (upstream_child_id),
  CONSTRAINT chk_openmaic_tts_child_calls CHECK ((llm_call_count = 0) and (web_search_call_count = 0) and (image_generation_call_count = 0) and (video_generation_call_count = 0) and (tts_expected_call_count = 10) and (tts_attempted_call_count >= 0) and (tts_attempted_call_count <= tts_expected_call_count) and (tts_completed_call_count >= 0) and (tts_completed_call_count <= tts_attempted_call_count) and (tts_provider_id = 'qwen-tts') and (tts_model_id = 'qwen3-tts-flash') and (tts_voice_id = 'Serena') and (tts_fallback_used = 0)),
  CONSTRAINT chk_openmaic_tts_child_identity CHECK ((left(expected_upstream_child_id,6) = 'omtts_') and (left(expected_upstream_classroom_id,8) = 'omclass_') and ((upstream_child_id is null) or (upstream_child_id = expected_upstream_child_id)) and ((upstream_classroom_id is null) or (upstream_classroom_id = expected_upstream_classroom_id))),
  CONSTRAINT chk_openmaic_tts_child_kind CHECK (kind = 'mira_sample_deterministic_tts_credential_recovery_v1'),
  CONSTRAINT chk_openmaic_tts_child_mode CHECK (mode = 'deterministic_no_llm_qwen_tts_only'),
  CONSTRAINT chk_openmaic_tts_child_parent CHECK ((parent_status = 'failed') and (parent_dispatch_count = 2) and (parent_error_code = 'openmaic_deterministic_recovery_failed') and (parent_expected_upstream_recovery_id = parent_upstream_recovery_id) and (parent_tts_expected_call_count = 10) and (parent_tts_attempted_call_count = 1) and (parent_tts_completed_call_count = 0) and (source_upstream_job_id = 'uKQl3vMr4d') and (parent_upstream_recovery_id = 'omrec_383729f8f7f637dc1cdc65d4')),
  CONSTRAINT chk_openmaic_tts_child_state_evidence CHECK (((status = 'recovering') and (error_code is null) and (error_message_safe is null) and (terminal_at is null) and (static_contract_verified = 0) and (conversation_probe_verified = 0) and (upstream_classroom_id is null) and (tts_verified_asset_count is null) and (scene_count is null) and (audio_count is null) and (content_sha256 is null) and (final_artifact_sha256 is null) and (artifact_created_at is null) and (conversation_probe_id is null) and (verified_at is null)) or ((status = 'validating') and (upstream_child_id is not null) and (upstream_child_id = expected_upstream_child_id) and (policy_version is not null) and (classroom_policy_version is not null) and (canonical_spec_sha256 is not null) and (parent_patch_sha256 is not null) and (code_patch_sha256 is not null) and (tts_attempted_call_count = 10) and (tts_completed_call_count = 10) and (conversation_probe_verified = 0) and (conversation_probe_id is null) and (verified_at is null) and (receipt_json is not null) and (error_code is null) and (error_message_safe is null) and (terminal_at is null) and (((static_contract_verified = 0) and (upstream_classroom_id is null) and (tts_verified_asset_count is null) and (scene_count is null) and (audio_count is null) and (content_sha256 is null) and (final_artifact_sha256 is null) and (artifact_created_at is null)) or ((static_contract_verified = 1) and (upstream_classroom_id is not null) and (upstream_classroom_id = expected_upstream_classroom_id) and (tts_verified_asset_count is not null) and (tts_verified_asset_count = 10) and (scene_count is not null) and (scene_count = 10) and (audio_count is not null) and (audio_count = 10) and (content_sha256 is not null) and (final_artifact_sha256 is not null) and (artifact_created_at is not null)))) or ((status = 'publishing') and (upstream_child_id is not null) and (upstream_child_id = expected_upstream_child_id) and (upstream_classroom_id is not null) and (upstream_classroom_id = expected_upstream_classroom_id) and (policy_version is not null) and (classroom_policy_version is not null) and (canonical_spec_sha256 is not null) and (parent_patch_sha256 is not null) and (code_patch_sha256 is not null) and (tts_attempted_call_count = 10) and (tts_completed_call_count = 10) and (tts_verified_asset_count is not null) and (tts_verified_asset_count = 10) and (scene_count is not null) and (scene_count = 10) and (audio_count is not null) and (audio_count = 10) and (content_sha256 is not null) and (final_artifact_sha256 is not null) and (artifact_created_at is not null) and (static_contract_verified = 1) and (conversation_probe_verified = 0) and (conversation_probe_id is null) and (verified_at is null) and (receipt_json is not null) and (error_code is null) and (error_message_safe is null) and (terminal_at is null)) or ((status = 'succeeded') and (error_code is null) and (error_message_safe is null) and (terminal_at is not null)) or ((status = 'failed') and (error_code is not null) and (error_message_safe is not null) and (terminal_at is not null) and (conversation_probe_verified = 0) and (conversation_probe_id is null) and (verified_at is null) and (((static_contract_verified = 0) and (upstream_classroom_id is null) and (tts_verified_asset_count is null) and (scene_count is null) and (audio_count is null) and (content_sha256 is null) and (final_artifact_sha256 is null) and (artifact_created_at is null)) or ((static_contract_verified = 1) and (upstream_child_id is not null) and (upstream_child_id = expected_upstream_child_id) and (upstream_classroom_id is not null) and (upstream_classroom_id = expected_upstream_classroom_id) and (policy_version is not null) and (classroom_policy_version is not null) and (canonical_spec_sha256 is not null) and (parent_patch_sha256 is not null) and (code_patch_sha256 is not null) and (tts_attempted_call_count = 10) and (tts_completed_call_count = 10) and (tts_verified_asset_count is not null) and (tts_verified_asset_count = 10) and (scene_count is not null) and (scene_count = 10) and (audio_count is not null) and (audio_count = 10) and (content_sha256 is not null) and (final_artifact_sha256 is not null) and (artifact_created_at is not null) and (receipt_json is not null))))),
  CONSTRAINT chk_openmaic_tts_child_status CHECK (status in ('recovering','validating','publishing','succeeded','failed')),
  CONSTRAINT chk_openmaic_tts_child_success CHECK ((status <> 'succeeded') or ((upstream_child_id is not null) and (upstream_child_id = expected_upstream_child_id) and (upstream_classroom_id is not null) and (upstream_classroom_id = expected_upstream_classroom_id) and (policy_version is not null) and (classroom_policy_version is not null) and (canonical_spec_sha256 is not null) and (parent_patch_sha256 is not null) and (code_patch_sha256 is not null) and (tts_attempted_call_count = 10) and (tts_completed_call_count = 10) and (tts_verified_asset_count is not null) and (tts_verified_asset_count = 10) and (scene_count is not null) and (scene_count = 10) and (audio_count is not null) and (audio_count = 10) and (content_sha256 is not null) and (final_artifact_sha256 is not null) and (artifact_created_at is not null) and (static_contract_verified = 1) and (conversation_probe_verified = 1) and (conversation_probe_id is not null) and (verified_at is not null) and (receipt_json is not null) and (error_code is null) and (terminal_at is not null)))
);
CREATE INDEX idx_openmaic_tts_child_status ON learning_openmaic_tts_credential_recoveries (status, updated_at);

CREATE TABLE learning_placement_attempts (
  id varchar(80) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  curriculum_version varchar(64) NOT NULL,
  grade_code varchar(32) NOT NULL,
  grade_revision integer NOT NULL,
  subject varchar(32) NOT NULL,
  lesson_id varchar(128) NOT NULL,
  policy_json jsonb NOT NULL,
  status varchar(24) NOT NULL,
  total_questions integer NOT NULL,
  current_index integer DEFAULT 0 NOT NULL,
  correct_count integer DEFAULT 0 NOT NULL,
  passed integer,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  completed_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_placement_opportunity UNIQUE (family_id, child_id, curriculum_version, lesson_id),
  CONSTRAINT chk_placement_state CHECK ((status in ('in_progress','completed','invalidated')) and (total_questions >= 5) and (current_index between 0 and total_questions) and (correct_count between 0 and current_index) and (grade_revision >= 1) and (((status = 'in_progress') and (current_index < total_questions) and (passed is null) and (completed_at is null)) or ((status = 'completed') and (current_index = total_questions) and (passed is not null) and (passed in (0,1)) and (completed_at is not null)) or ((status = 'invalidated') and (passed is null) and (completed_at is not null))))
);

CREATE TABLE learning_placement_questions (
  attempt_id varchar(80) NOT NULL,
  ordinal integer NOT NULL,
  question_id varchar(80) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  source_question_id varchar(128) NOT NULL,
  assessment_set_id varchar(128) NOT NULL,
  question_fingerprint varchar(64) NOT NULL,
  source_content_sha256 varchar(64) NOT NULL,
  authority_sha256 varchar(64) NOT NULL,
  snapshot_sha256 varchar(64) NOT NULL,
  snapshot_json jsonb NOT NULL,
  response_sha256 varchar(64),
  correct integer,
  answered_at bigint,
  PRIMARY KEY (attempt_id, ordinal),
  CONSTRAINT uq_placement_fingerprint UNIQUE (attempt_id, question_fingerprint),
  CONSTRAINT uq_placement_question UNIQUE (question_id),
  CONSTRAINT chk_placement_question CHECK ((ordinal >= 0) and (((response_sha256 is null) and (correct is null) and (answered_at is null)) or ((response_sha256 is not null) and (response_sha256 ~* '^[0-9a-f]{64}$') and (correct is not null) and (correct in (0,1)) and (answered_at is not null))))
);
CREATE INDEX idx_placement_exposure ON learning_placement_questions (question_fingerprint);

CREATE TABLE learning_practice_exposures (
  id varchar(64) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  dedupe_sha256 varchar(64) NOT NULL,
  session_id varchar(80) NOT NULL,
  question_id varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX fk_practice_exposure_question ON learning_practice_exposures (question_id);
CREATE INDEX fk_practice_exposure_session ON learning_practice_exposures (session_id);
CREATE INDEX idx_practice_seen ON learning_practice_exposures (child_id, dedupe_sha256);

CREATE TABLE learning_practice_questions (
  id varchar(64) NOT NULL,
  source_key_sha256 varchar(64) NOT NULL,
  grade_code varchar(32) NOT NULL,
  subject varchar(32) NOT NULL,
  skill_id varchar(128) NOT NULL,
  release_id varchar(255) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  source_question_id varchar(128) NOT NULL,
  source_content_sha256 varchar(64) NOT NULL,
  contract_sha256 varchar(64) NOT NULL,
  dedupe_sha256 varchar(64) NOT NULL,
  question_json jsonb NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT source_key_sha256 UNIQUE (source_key_sha256),
  CONSTRAINT chk_practice_question_identity CHECK ((id ~* '^[0-9a-f]{64}$') and (contract_sha256 ~* '^[0-9a-f]{64}$') and (source_content_sha256 ~* '^[0-9a-f]{64}$') and (dedupe_sha256 ~* '^[0-9a-f]{64}$'))
);
CREATE INDEX idx_practice_question_scope ON learning_practice_questions (grade_code, subject, skill_id);

CREATE TABLE learning_practice_session_questions (
  session_id varchar(80) NOT NULL,
  ordinal integer NOT NULL,
  question_id varchar(64) NOT NULL,
  contract_sha256 varchar(64) NOT NULL,
  snapshot_json jsonb NOT NULL,
  response_sha256 varchar(64),
  feedback_json jsonb,
  answered_at bigint,
  PRIMARY KEY (session_id, ordinal),
  CONSTRAINT uq_practice_session_question UNIQUE (session_id, question_id),
  CONSTRAINT chk_practice_attempt CHECK ((ordinal between 0 and 4) and (contract_sha256 ~* '^[0-9a-f]{64}$') and (((response_sha256 is null) and (feedback_json is null) and (answered_at is null)) or ((response_sha256 ~* '^[0-9a-f]{64}$') and (feedback_json is not null) and (answered_at is not null))))
);
CREATE INDEX fk_practice_question ON learning_practice_session_questions (question_id);

CREATE TABLE learning_practice_sessions (
  id varchar(80) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  grade_code varchar(32) NOT NULL,
  grade_revision integer NOT NULL,
  subject varchar(32) NOT NULL,
  skill_id varchar(128),
  request_key_sha256 varchar(64) NOT NULL,
  request_sha256 varchar(64) NOT NULL,
  status varchar(24) NOT NULL,
  total_questions integer NOT NULL,
  current_index integer DEFAULT 0 NOT NULL,
  correct_count integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  completed_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT request_key_sha256 UNIQUE (request_key_sha256),
  CONSTRAINT chk_practice_session_state CHECK ((status in ('in_progress','completed')) and (total_questions between 1 and 5) and (current_index between 0 and total_questions) and (correct_count between 0 and current_index) and (grade_revision >= 1) and (((status = 'in_progress') and (current_index < total_questions) and (completed_at is null)) or ((status = 'completed') and (current_index = total_questions) and (completed_at is not null))))
);
CREATE INDEX idx_practice_student ON learning_practice_sessions (child_id, subject, status);

CREATE TABLE learning_progressive_course_bindings (
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  curriculum_version varchar(64) NOT NULL,
  lesson_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  assessment_set_id varchar(128) NOT NULL,
  content_sha256 varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  retired_at bigint,
  PRIMARY KEY (course_id, course_version)
);
CREATE INDEX idx_progressive_bound_lesson ON learning_progressive_course_bindings (curriculum_version, lesson_id, retired_at);

CREATE TABLE learning_progressive_evidence (
  id varchar(64) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  curriculum_version varchar(64) NOT NULL,
  lesson_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  source_kind varchar(32) NOT NULL,
  source_session_id varchar(255) NOT NULL,
  source_question_id varchar(255) NOT NULL,
  question_fingerprint varchar(64) NOT NULL,
  assessment_set_id varchar(128) NOT NULL,
  attempt_number integer NOT NULL,
  independent integer NOT NULL,
  hint_count_before_answer integer NOT NULL,
  correct integer,
  actor_role varchar(16),
  actor_id varchar(128),
  occurred_at bigint NOT NULL,
  evidence_sha256 varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_progressive_evidence_scope ON learning_progressive_evidence (family_id, child_id, curriculum_version, lesson_id, occurred_at);
CREATE INDEX idx_progressive_evidence_subject ON learning_progressive_evidence (family_id, child_id, curriculum_version, subject, occurred_at);

CREATE TABLE learning_progressive_lesson_progress (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  curriculum_version varchar(64) NOT NULL,
  lesson_id varchar(128) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  mastery_status varchar(32) NOT NULL,
  independent_count integer DEFAULT 0 NOT NULL,
  independent_correct_count integer DEFAULT 0 NOT NULL,
  distinct_assessment_sets integer DEFAULT 0 NOT NULL,
  total_evidence_count integer DEFAULT 0 NOT NULL,
  accuracy double precision,
  mastered_at bigint,
  stable_at bigint,
  last_evidence_at bigint,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, curriculum_version, lesson_id)
);
CREATE INDEX idx_progressive_progress_subject ON learning_progressive_lesson_progress (family_id, child_id, curriculum_version, subject, mastery_status);

CREATE TABLE learning_reports (
  id varchar(255) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  task_id varchar(128) NOT NULL,
  session_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  learning_date varchar(10) NOT NULL,
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  score integer NOT NULL,
  correct_count integer NOT NULL,
  independent_correct_count integer NOT NULL,
  hint_count integer NOT NULL,
  total_questions integer NOT NULL,
  mastery_level varchar(32) NOT NULL,
  summary text NOT NULL,
  strengths_json text NOT NULL,
  next_step text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_reports_session UNIQUE (family_id, session_id)
);
CREATE INDEX idx_learning_reports_latest ON learning_reports (family_id, child_id, created_at);

CREATE TABLE learning_review_items (
  run_id varchar(80) NOT NULL,
  ordinal integer NOT NULL,
  question_id varchar(64) NOT NULL,
  snapshot_json jsonb NOT NULL,
  snapshot_sha256 varchar(64) NOT NULL,
  knowledge_id varchar(255) NOT NULL,
  evidence_mode varchar(32) NOT NULL,
  exposure_at bigint,
  hint_level integer DEFAULT 0 NOT NULL,
  explanation_seen smallint DEFAULT 0 NOT NULL,
  answer_json jsonb,
  answer_sha256 varchar(64),
  feedback_json jsonb,
  answered_at bigint,
  PRIMARY KEY (run_id, ordinal),
  CONSTRAINT uq_review_question UNIQUE (run_id, question_id)
);

CREATE TABLE learning_review_preferences (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  preferences_json jsonb NOT NULL,
  revision integer NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id)
);

CREATE TABLE learning_review_reminders (
  run_id varchar(80) NOT NULL,
  appointment_revision integer NOT NULL,
  local_day varchar(10) NOT NULL,
  status varchar(40) NOT NULL,
  receipt_json jsonb,
  attempted_at bigint NOT NULL,
  PRIMARY KEY (run_id, appointment_revision)
);
CREATE INDEX idx_review_reminder_day ON learning_review_reminders (local_day, run_id);

CREATE TABLE learning_review_requests (
  run_id varchar(80) NOT NULL,
  request_id varchar(128) NOT NULL,
  payload_sha256 varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (run_id, request_id)
);

CREATE TABLE learning_review_runs (
  id varchar(80) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  week_start varchar(10) NOT NULL,
  task_type varchar(32) DEFAULT 'weekend_review' NOT NULL,
  task_id varchar(255) NOT NULL,
  grade_code varchar(32) NOT NULL,
  grade_revision integer NOT NULL,
  status varchar(32) NOT NULL,
  revision integer DEFAULT 0 NOT NULL,
  appointment_revision integer DEFAULT 0 NOT NULL,
  scheduled_at bigint,
  reminder_expires_at bigint,
  reminder_status varchar(40) NOT NULL,
  current_index integer DEFAULT 0 NOT NULL,
  total_questions integer NOT NULL,
  correct_count integer DEFAULT 0 NOT NULL,
  independent_correct_count integer DEFAULT 0 NOT NULL,
  estimated_seconds integer NOT NULL,
  coverage_json jsonb NOT NULL,
  policy_json jsonb NOT NULL,
  created_at bigint NOT NULL,
  started_at bigint,
  completed_at bigint,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT task_id UNIQUE (task_id),
  CONSTRAINT uq_review_week UNIQUE (family_id, child_id, week_start, task_type)
);
CREATE INDEX idx_review_active ON learning_review_runs (family_id, child_id, status);
CREATE INDEX idx_review_due ON learning_review_runs (status, scheduled_at);

CREATE TABLE learning_session_runtime_records (
  id varchar(128) NOT NULL,
  session_id varchar(255) NOT NULL,
  seq integer NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  scene_id varchar(128),
  action_id varchar(128),
  record_type varchar(64) NOT NULL,
  payload_json text NOT NULL,
  response_json text NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_runtime_record_idempotency UNIQUE (session_id, idempotency_key),
  CONSTRAINT uq_learning_runtime_record_seq UNIQUE (session_id, seq)
);
CREATE INDEX idx_learning_runtime_records_session ON learning_session_runtime_records (session_id, created_at);

CREATE TABLE learning_sessions (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  task_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  status varchar(32) NOT NULL,
  current_question_index integer DEFAULT 0 NOT NULL,
  correct_count integer DEFAULT 0 NOT NULL,
  attempted_count integer DEFAULT 0 NOT NULL,
  answers_json text NOT NULL,
  started_at bigint NOT NULL,
  completed_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  lesson_package_id varchar(128),
  lesson_package_version integer,
  lesson_package_content_hash varchar(64),
  current_scene_index integer DEFAULT 0 NOT NULL,
  current_action_index integer DEFAULT 0 NOT NULL,
  cursor_revision integer DEFAULT 0 NOT NULL,
  runtime_state_json text,
  classroom_completed_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_learning_sessions_formal_course UNIQUE (id, course_id, course_version),
  CONSTRAINT uq_learning_sessions_formal_package UNIQUE (id, lesson_package_id, lesson_package_version, lesson_package_content_hash),
  CONSTRAINT uq_learning_sessions_formal_subject UNIQUE (id, family_id, child_id),
  CONSTRAINT uq_learning_sessions_task UNIQUE (family_id, task_id)
);
CREATE INDEX idx_learning_sessions_child ON learning_sessions (family_id, child_id, updated_at);
CREATE INDEX idx_learning_sessions_package ON learning_sessions (lesson_package_id, lesson_package_version);

CREATE TABLE learning_skill_boundaries (
  grade_code varchar(64) NOT NULL,
  subject varchar(64) NOT NULL,
  skill_id varchar(128) NOT NULL,
  curriculum_version varchar(128) NOT NULL,
  boundary_version varchar(255) NOT NULL,
  title varchar(255) NOT NULL,
  payload_json text NOT NULL,
  quality_status varchar(32) NOT NULL,
  status varchar(32) NOT NULL,
  retired_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (curriculum_version, boundary_version)
);
CREATE INDEX idx_learning_skill_boundaries_current ON learning_skill_boundaries (grade_code, subject, skill_id, status, quality_status, retired_at);
CREATE INDEX idx_learning_skill_boundary_node ON learning_skill_boundaries (curriculum_version, grade_code, subject, skill_id);

CREATE TABLE learning_student_formal_session_bindings (
  learning_session_id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  grade_code varchar(64) NOT NULL,
  authority_kind varchar(32) NOT NULL,
  pointer_history_id varchar(128),
  pointer_revision integer,
  preparation_plan_id varchar(128),
  grade_selection_revision integer,
  release_id varchar(128) NOT NULL,
  target_fingerprint varchar(64) NOT NULL,
  publication_contract_version varchar(128) NOT NULL,
  runtime_binding_contract_version varchar(128) NOT NULL,
  build_item_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  package_id varchar(128) NOT NULL,
  package_version integer NOT NULL,
  package_content_hash varchar(64) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  upstream_classroom_id varchar(255) NOT NULL,
  bound_at bigint NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (learning_session_id),
  CONSTRAINT chk_lsfsb_identity CHECK ((learning_session_id <> '') and (family_id <> '') and (child_id <> '') and (grade_code ~* '^primary_[1-6]$') and (authority_kind in ('active_pointer','progressive_plan','progressive_course')) and (release_id <> '') and (target_fingerprint ~* '^[0-9a-f]{64}$') and (publication_contract_version = 'mira.learning.formal-publication.v1') and (build_item_id <> '') and (course_id <> '') and (course_version <> '') and (package_id <> '') and (package_version > 0) and (package_content_hash ~* '^[0-9a-f]{64}$') and (runtime_classroom_id <> '') and (upstream_classroom_id <> '') and (bound_at > 0) and (created_at = bound_at) and (((authority_kind = 'active_pointer') and (pointer_history_id is not null) and (pointer_history_id <> '') and (pointer_revision is not null) and (pointer_revision >= 1) and (preparation_plan_id is null) and (grade_selection_revision is null)) or ((authority_kind = 'progressive_plan') and (pointer_history_id is null) and (pointer_revision is null) and (preparation_plan_id is not null) and (preparation_plan_id <> '') and (grade_selection_revision is not null) and (grade_selection_revision >= 1)) or ((authority_kind = 'progressive_course') and (pointer_history_id is null) and (pointer_revision is null) and (preparation_plan_id is null) and (grade_selection_revision is not null) and (grade_selection_revision >= 1)))),
  CONSTRAINT chk_lsfsb_immutable_timeline CHECK ((bound_at > 0) and (created_at = bound_at)),
  CONSTRAINT chk_lsfsb_runtime_binding_contract CHECK (runtime_binding_contract_version = 'mira.learning.candidate-runtime-binding.v1')
);
CREATE INDEX fk_lsfsb_build_course ON learning_student_formal_session_bindings (build_item_id, course_id, course_version);
CREATE INDEX fk_lsfsb_build_release ON learning_student_formal_session_bindings (build_item_id, release_id, grade_code);
CREATE INDEX fk_lsfsb_history ON learning_student_formal_session_bindings (pointer_history_id, grade_code, pointer_revision, target_fingerprint, publication_contract_version, release_id);
CREATE INDEX fk_lsfsb_package ON learning_student_formal_session_bindings (package_id, package_version, course_id, course_version, package_content_hash);
CREATE INDEX fk_lsfsb_publication_receipt ON learning_student_formal_session_bindings (build_item_id, release_id, runtime_classroom_id);
CREATE INDEX fk_lsfsb_release_item ON learning_student_formal_session_bindings (release_id, grade_code, course_id, course_version, package_id, package_version);
CREATE INDEX fk_lsfsb_runtime_candidate ON learning_student_formal_session_bindings (runtime_classroom_id, build_item_id, release_id, grade_code, target_fingerprint, runtime_binding_contract_version);
CREATE INDEX fk_lsfsb_runtime_course ON learning_student_formal_session_bindings (runtime_classroom_id, course_id, course_version);
CREATE INDEX fk_lsfsb_runtime_package ON learning_student_formal_session_bindings (runtime_classroom_id, package_id, package_version);
CREATE INDEX fk_lsfsb_runtime_upstream ON learning_student_formal_session_bindings (runtime_classroom_id, upstream_classroom_id);
CREATE INDEX fk_lsfsb_session_course ON learning_student_formal_session_bindings (learning_session_id, course_id, course_version);
CREATE INDEX fk_lsfsb_session_package ON learning_student_formal_session_bindings (learning_session_id, package_id, package_version, package_content_hash);
CREATE INDEX fk_lsfsb_session_subject ON learning_student_formal_session_bindings (learning_session_id, family_id, child_id);
CREATE INDEX idx_lsfsb_progressive_plan ON learning_student_formal_session_bindings (preparation_plan_id, grade_selection_revision, bound_at);
CREATE INDEX idx_student_formal_binding_child ON learning_student_formal_session_bindings (family_id, child_id, bound_at);
CREATE INDEX idx_student_formal_binding_release ON learning_student_formal_session_bindings (release_id, grade_code, bound_at);
CREATE INDEX idx_student_formal_binding_runtime ON learning_student_formal_session_bindings (runtime_classroom_id, bound_at);

CREATE TABLE learning_student_teacher_preferences (
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  subject varchar(64) NOT NULL,
  teacher_profile_id varchar(128) NOT NULL,
  teacher_profile_version integer NOT NULL,
  updated_by_user_id varchar(255),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, subject)
);
CREATE INDEX fk_learning_teacher_preference_profile ON learning_student_teacher_preferences (teacher_profile_id, teacher_profile_version);
CREATE INDEX idx_learning_teacher_preferences_child ON learning_student_teacher_preferences (child_id, subject);

CREATE TABLE learning_task_carryovers (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  source_task_id varchar(255) NOT NULL,
  origin_date varchar(10) NOT NULL,
  target_date varchar(10) NOT NULL,
  target_slot varchar(32) NOT NULL,
  reason varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_learning_task_carryover_child_date ON learning_task_carryovers (family_id, child_id, target_date, target_slot);
CREATE INDEX idx_learning_task_carryover_source ON learning_task_carryovers (source_task_id, target_date);

CREATE TABLE learning_teacher_profiles (
  id varchar(128) NOT NULL,
  version integer NOT NULL,
  display_name varchar(128) NOT NULL,
  avatar_path varchar(255) NOT NULL,
  subject varchar(64) NOT NULL,
  language_code varchar(32) NOT NULL,
  teaching_style varchar(64) NOT NULL,
  provider_id varchar(64) NOT NULL,
  provider_model varchar(128) NOT NULL,
  voice_mode varchar(32) NOT NULL,
  voice_prompt text NOT NULL,
  capabilities_json text NOT NULL,
  clone_allowed smallint DEFAULT 0 NOT NULL,
  status varchar(32) NOT NULL,
  content_hash varchar(64) NOT NULL,
  published_at bigint,
  retired_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id, version),
  CONSTRAINT uq_learning_teacher_profile_hash UNIQUE (content_hash)
);
CREATE INDEX idx_learning_teacher_profile_catalog ON learning_teacher_profiles (subject, language_code, status, version);

CREATE TABLE learning_textbook_course_builds (
  content_key varchar(64) NOT NULL,
  edition_id varchar(80) NOT NULL,
  revision_id varchar(80) NOT NULL,
  node_id varchar(80) NOT NULL,
  part_index integer NOT NULL,
  teaching_revision varchar(80) NOT NULL,
  input_json jsonb NOT NULL,
  status varchar(24) NOT NULL,
  course_id varchar(255),
  course_version varchar(64),
  course_content_sha256 varchar(64),
  review_json jsonb,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (content_key),
  CONSTRAINT uq_textbook_course_version UNIQUE (course_id, course_version),
  CONSTRAINT uq_textbook_lesson_build UNIQUE (edition_id, revision_id, node_id, part_index, teaching_revision),
  CONSTRAINT chk_textbook_build CHECK ((part_index between 1 and 20) and (status in ('prepared','published','retired')) and ((status <> 'published') or ((course_id is not null) and (course_version is not null) and (course_content_sha256 is not null) and (review_json is not null))))
);

CREATE TABLE learning_textbook_course_previews (
  preview_key varchar(64) NOT NULL,
  edition_id varchar(80) NOT NULL,
  revision_id varchar(80) NOT NULL,
  node_id varchar(80) NOT NULL,
  input_json jsonb NOT NULL,
  runtime_origin varchar(255) NOT NULL,
  status varchar(32) NOT NULL,
  runtime_job_id varchar(128),
  classroom_id varchar(255),
  classroom_sha256 varchar(64),
  classroom_json jsonb,
  result_json jsonb,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (preview_key),
  CONSTRAINT uq_textbook_preview_runtime_job UNIQUE (runtime_origin, runtime_job_id),
  CONSTRAINT chk_textbook_preview_status CHECK ((status in ('queued','dispatching','generating','preview_ready','review_required','failed','dispatch_unknown')) and ((status <> 'preview_ready') or ((runtime_job_id is not null) and (classroom_id is not null) and (classroom_sha256 is not null) and (classroom_json is not null))))
);
CREATE INDEX fk_textbook_preview_revision ON learning_textbook_course_previews (edition_id, revision_id);

CREATE TABLE learning_textbook_editions (
  edition_id varchar(80) NOT NULL,
  identity_sha256 varchar(64) NOT NULL,
  identity_json jsonb NOT NULL,
  imported_at bigint NOT NULL,
  PRIMARY KEY (edition_id)
);

CREATE TABLE learning_textbook_revisions (
  edition_id varchar(80) NOT NULL,
  revision_id varchar(80) NOT NULL,
  grade_code varchar(32) NOT NULL,
  subject varchar(32) NOT NULL,
  manifest_sha256 varchar(64) NOT NULL,
  manifest_json jsonb NOT NULL,
  imported_at bigint NOT NULL,
  retired_at bigint,
  PRIMARY KEY (edition_id, revision_id)
);
CREATE INDEX idx_textbook_grade ON learning_textbook_revisions (grade_code, subject, retired_at);

CREATE TABLE learning_textbook_selection_events (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  school_year_start integer NOT NULL,
  semester varchar(16) NOT NULL,
  subject varchar(32) NOT NULL,
  selection_revision integer NOT NULL,
  selection_json jsonb NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, school_year_start, semester, subject, selection_revision)
);

CREATE TABLE learning_textbook_selections (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  school_year_start integer NOT NULL,
  semester varchar(16) NOT NULL,
  subject varchar(32) NOT NULL,
  edition_id varchar(80) NOT NULL,
  revision_id varchar(80) NOT NULL,
  grade_revision integer NOT NULL,
  selection_revision integer NOT NULL,
  current_node_id varchar(80),
  confirmed_by varchar(128) NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, school_year_start, semester, subject),
  CONSTRAINT chk_textbook_selection CHECK ((selection_revision >= 1) and (grade_revision >= 1) and (semester in ('upper','lower')) and (subject in ('chinese','math','english','science')))
);
CREATE INDEX fk_textbook_selection_revision ON learning_textbook_selections (edition_id, revision_id);

CREATE TABLE onvif_discovery_sessions (
  id varchar(255) NOT NULL,
  token_hash varchar(64) NOT NULL,
  family_id varchar(255) NOT NULL,
  user_id varchar(255) NOT NULL,
  binding_code varchar(255) NOT NULL,
  metadata_json text NOT NULL,
  expires_at bigint NOT NULL,
  consumed_at bigint,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_onvif_discovery_sessions_token_hash UNIQUE (token_hash)
);
CREATE INDEX fk_onvif_discovery_sessions_user ON onvif_discovery_sessions (user_id);
CREATE INDEX idx_onvif_discovery_sessions_binding ON onvif_discovery_sessions (binding_code, expires_at);
CREATE INDEX idx_onvif_discovery_sessions_family ON onvif_discovery_sessions (family_id, expires_at);

CREATE TABLE parent_identities (
  family_id varchar(255) NOT NULL,
  display_name varchar(255) NOT NULL,
  relationship varchar(255) NOT NULL,
  relationship_key varchar(255),
  confirmed_at bigint NOT NULL,
  PRIMARY KEY (family_id)
);

CREATE TABLE point_accounts (
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  balance integer DEFAULT 0 NOT NULL,
  stage_notice_handled_balance integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id)
);

CREATE TABLE point_ledger (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  delta integer NOT NULL,
  balance_after integer NOT NULL,
  type varchar(255) NOT NULL,
  source_type varchar(255),
  source_id varchar(255),
  note text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE reminder_decisions (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  observation_event_id varchar(64),
  behavior_state_id varchar(64),
  source_type varchar(64),
  source_id varchar(128),
  task_id varchar(64),
  decision varchar(128) NOT NULL,
  reason varchar(255) NOT NULL,
  reminder_level varchar(64) DEFAULT 'gentle' NOT NULL,
  cooldown_until bigint,
  should_speak smallint DEFAULT 0 NOT NULL,
  should_notify_parent smallint DEFAULT 0 NOT NULL,
  policy_snapshot_json text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_reminder_decisions_family_child ON reminder_decisions (family_id, child_id, scenario, created_at);
CREATE INDEX idx_reminder_decisions_observation ON reminder_decisions (observation_event_id);
CREATE INDEX idx_reminder_decisions_source ON reminder_decisions (source_type, source_id);

CREATE TABLE reminder_events (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64) NOT NULL,
  device_id varchar(64) DEFAULT '' NOT NULL,
  scenario varchar(64) NOT NULL,
  reminder_decision_id varchar(64),
  event_source varchar(64) DEFAULT 'care_policy' NOT NULL,
  is_test smallint DEFAULT 0 NOT NULL,
  source_type varchar(64),
  source_id varchar(128),
  task_id varchar(64),
  prompt_id varchar(128),
  prompt_version varchar(32),
  text text NOT NULL,
  tone varchar(64) DEFAULT 'warm' NOT NULL,
  text_source varchar(64) DEFAULT 'fallback' NOT NULL,
  delivery_status varchar(128) DEFAULT 'generated' NOT NULL,
  command_id varchar(64),
  fallback_used smallint DEFAULT 0 NOT NULL,
  generated_at bigint NOT NULL,
  delivered_at bigint,
  failure_reason text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_reminder_events_delivery ON reminder_events (scenario, delivery_status, generated_at);
CREATE INDEX idx_reminder_events_family_child ON reminder_events (family_id, child_id, scenario, is_test, created_at);
CREATE INDEX idx_reminder_events_source ON reminder_events (source_type, source_id);

CREATE TABLE review_items (
  id varchar(255) NOT NULL,
  family_id varchar(64) NOT NULL,
  child_id varchar(64),
  device_id varchar(64) DEFAULT '' NOT NULL,
  domain varchar(64) NOT NULL,
  scenario varchar(64),
  item_type varchar(128) NOT NULL,
  source_type varchar(64),
  source_id varchar(128),
  priority varchar(32) DEFAULT 'normal' NOT NULL,
  status varchar(64) DEFAULT 'pending' NOT NULL,
  summary text NOT NULL,
  related_observation_id varchar(64),
  related_reminder_id varchar(64),
  task_id varchar(64),
  due_at bigint,
  created_at bigint NOT NULL,
  resolved_at bigint,
  resolved_by varchar(255),
  PRIMARY KEY (id)
);
CREATE INDEX idx_review_items_family_child ON review_items (family_id, child_id, status, created_at);
CREATE INDEX idx_review_items_source ON review_items (domain, source_type, source_id);

CREATE TABLE reward_items (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  title varchar(255) NOT NULL,
  description text,
  points_cost integer NOT NULL,
  category varchar(255),
  status varchar(255) NOT NULL,
  icon varchar(255),
  created_by varchar(255),
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE reward_redemptions (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  reward_item_id varchar(255) NOT NULL,
  reward_title varchar(255) NOT NULL,
  points_cost integer NOT NULL,
  status varchar(255) NOT NULL,
  requested_by varchar(255) NOT NULL,
  fulfilled_by varchar(255),
  cancelled_by varchar(255),
  requested_at bigint NOT NULL,
  fulfilled_at bigint,
  cancelled_at bigint,
  PRIMARY KEY (id)
);

CREATE TABLE sessions (
  id varchar(255) NOT NULL,
  user_id varchar(255) NOT NULL,
  device_label varchar(255),
  device_type varchar(255),
  device_model varchar(255),
  device_hardware varchar(255),
  platform varchar(255),
  os_version varchar(255),
  app_version varchar(255),
  last_active_at bigint,
  access_hash varchar(255) NOT NULL,
  refresh_hash varchar(255) NOT NULL,
  access_expires_at bigint NOT NULL,
  refresh_expires_at bigint NOT NULL,
  created_at bigint NOT NULL,
  rotated_at bigint,
  revoked_at bigint,
  CONSTRAINT access_hash UNIQUE (access_hash),
  PRIMARY KEY (id),
  CONSTRAINT refresh_hash UNIQUE (refresh_hash)
);

CREATE TABLE setup_progress (
  family_id varchar(255) NOT NULL,
  completed smallint DEFAULT 0 NOT NULL,
  parent_identity_status varchar(255) DEFAULT 'pending' NOT NULL,
  device_binding_status varchar(255) DEFAULT 'pending' NOT NULL,
  wifi_status varchar(255) DEFAULT 'pending' NOT NULL,
  child_profile_status varchar(255) DEFAULT 'pending' NOT NULL,
  camera_name_status varchar(255) DEFAULT 'pending' NOT NULL,
  camera_name_intro_status varchar(255) DEFAULT 'pending' NOT NULL,
  camera_name_intro_at bigint,
  contacts_status varchar(255) DEFAULT 'pending' NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  completed_at bigint,
  PRIMARY KEY (family_id)
);

CREATE TABLE sms_codes (
  phone varchar(255) NOT NULL,
  code_hash varchar(255) NOT NULL,
  expires_at bigint NOT NULL,
  created_at bigint NOT NULL,
  attempt_count integer DEFAULT 0 NOT NULL,
  last_sent_at bigint NOT NULL,
  PRIMARY KEY (phone)
);

CREATE TABLE student_learning_course_favorites (
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  course_id varchar(255) NOT NULL,
  course_version varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (family_id, child_id, course_id, course_version)
);
CREATE INDEX idx_student_learning_favorites_recent ON student_learning_course_favorites (family_id, child_id, updated_at);

CREATE TABLE student_openmaic_launch_tickets (
  id varchar(128) NOT NULL,
  token_hash varchar(64) NOT NULL,
  principal_id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  learning_session_id varchar(255) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  expires_at bigint NOT NULL,
  consumed_at bigint,
  revoked_at bigint,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_openmaic_launch_token UNIQUE (token_hash)
);
CREATE INDEX fk_student_openmaic_launch_runtime ON student_openmaic_launch_tickets (runtime_classroom_id);
CREATE INDEX idx_student_openmaic_launch_principal ON student_openmaic_launch_tickets (principal_id, expires_at, consumed_at);
CREATE INDEX idx_student_openmaic_launch_session ON student_openmaic_launch_tickets (learning_session_id, created_at);

CREATE TABLE student_openmaic_runtime_sessions (
  id varchar(128) NOT NULL,
  token_hash varchar(64) NOT NULL,
  launch_ticket_id varchar(128) NOT NULL,
  principal_id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  learning_session_id varchar(255) NOT NULL,
  runtime_classroom_id varchar(128) NOT NULL,
  expires_at bigint NOT NULL,
  last_active_at bigint NOT NULL,
  created_at bigint NOT NULL,
  revoked_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_openmaic_runtime_ticket UNIQUE (launch_ticket_id),
  CONSTRAINT uq_student_openmaic_runtime_token UNIQUE (token_hash)
);
CREATE INDEX fk_student_openmaic_runtime_classroom ON student_openmaic_runtime_sessions (runtime_classroom_id);
CREATE INDEX idx_student_openmaic_runtime_learning_session ON student_openmaic_runtime_sessions (learning_session_id, created_at);
CREATE INDEX idx_student_openmaic_runtime_principal ON student_openmaic_runtime_sessions (principal_id, expires_at, revoked_at);

CREATE TABLE student_pairing_challenge_rate_buckets (
  bucket_kind varchar(16) NOT NULL,
  bucket_hash varchar(64) NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (bucket_kind, bucket_hash)
);
CREATE INDEX idx_student_pairing_challenge_rate_buckets_updated ON student_pairing_challenge_rate_buckets (updated_at);

CREATE TABLE student_pairing_challenges (
  id varchar(128) NOT NULL,
  challenge_hash varchar(64) NOT NULL,
  verifier_hash varchar(64) NOT NULL,
  display_code varchar(4) NOT NULL,
  status varchar(32) DEFAULT 'pending' NOT NULL,
  device_label varchar(255) NOT NULL,
  device_type varchar(64) NOT NULL,
  device_model varchar(255),
  device_hardware varchar(255),
  platform varchar(64) NOT NULL,
  os_version varchar(64),
  browser_name varchar(64),
  os_name varchar(64),
  app_version varchar(64),
  client_fingerprint_hash varchar(64) NOT NULL,
  request_ip_hash varchar(64),
  family_id varchar(128),
  child_id varchar(128),
  approved_by_user_id varchar(128),
  rejected_by_user_id varchar(128),
  pin_hash varchar(64),
  pin_salt varchar(64),
  pin_iterations integer,
  expires_at bigint NOT NULL,
  approved_expires_at bigint,
  approved_at bigint,
  consumed_at bigint,
  rejected_at bigint,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_pairing_challenges_hash UNIQUE (challenge_hash)
);
CREATE INDEX idx_student_pairing_challenges_family ON student_pairing_challenges (family_id, child_id, created_at);
CREATE INDEX idx_student_pairing_challenges_fingerprint ON student_pairing_challenges (client_fingerprint_hash, created_at);
CREATE INDEX idx_student_pairing_challenges_ip ON student_pairing_challenges (request_ip_hash, created_at);
CREATE INDEX idx_student_pairing_challenges_status ON student_pairing_challenges (status, expires_at);

CREATE TABLE student_pairing_codes (
  id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  created_by_user_id varchar(128) NOT NULL,
  code_hash varchar(64) NOT NULL,
  pin_hash varchar(64) NOT NULL,
  pin_salt varchar(64) NOT NULL,
  pin_iterations integer NOT NULL,
  expires_at bigint NOT NULL,
  consumed_at bigint,
  revoked_at bigint,
  created_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_pairing_codes_hash UNIQUE (code_hash)
);
CREATE INDEX idx_student_pairing_codes_child ON student_pairing_codes (family_id, child_id, created_at);

CREATE TABLE student_principals (
  id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  status varchar(32) DEFAULT 'active' NOT NULL,
  pin_hash varchar(64) NOT NULL,
  pin_salt varchar(64) NOT NULL,
  pin_iterations integer NOT NULL,
  pin_updated_at bigint NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_principals_child UNIQUE (family_id, child_id)
);
CREATE INDEX idx_student_principals_status ON student_principals (family_id, status);

CREATE TABLE student_sessions (
  id varchar(128) NOT NULL,
  principal_id varchar(128) NOT NULL,
  device_id varchar(128) NOT NULL,
  access_hash varchar(64) NOT NULL,
  refresh_hash varchar(64) NOT NULL,
  access_expires_at bigint NOT NULL,
  refresh_expires_at bigint NOT NULL,
  last_active_at bigint NOT NULL,
  created_at bigint NOT NULL,
  rotated_at bigint,
  revoked_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_sessions_access UNIQUE (access_hash),
  CONSTRAINT uq_student_sessions_refresh UNIQUE (refresh_hash)
);
CREATE INDEX idx_student_sessions_device ON student_sessions (device_id, revoked_at);
CREATE INDEX idx_student_sessions_principal ON student_sessions (principal_id, last_active_at);

CREATE TABLE student_trusted_devices (
  id varchar(128) NOT NULL,
  principal_id varchar(128) NOT NULL,
  family_id varchar(128) NOT NULL,
  child_id varchar(128) NOT NULL,
  device_token_hash varchar(64) NOT NULL,
  device_label varchar(255) NOT NULL,
  device_type varchar(64) NOT NULL,
  device_model varchar(255),
  device_hardware varchar(255),
  platform varchar(64) NOT NULL,
  os_version varchar(64),
  app_version varchar(64),
  status varchar(32) DEFAULT 'trusted' NOT NULL,
  failed_pin_attempts integer DEFAULT 0 NOT NULL,
  locked_until bigint,
  expires_at bigint NOT NULL,
  last_active_at bigint NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  revoked_at bigint,
  PRIMARY KEY (id),
  CONSTRAINT uq_student_trusted_devices_token UNIQUE (device_token_hash)
);
CREATE INDEX idx_student_trusted_devices_principal ON student_trusted_devices (principal_id, status, last_active_at);

CREATE TABLE task_events (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  task_id varchar(255) NOT NULL,
  event_type varchar(255) NOT NULL,
  message text,
  payload text,
  created_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_task_events_family_created ON task_events (family_id, created_at);
CREATE INDEX idx_task_events_task_created ON task_events (task_id, created_at);

CREATE TABLE task_template_items (
  id varchar(255) NOT NULL,
  template_id varchar(255) NOT NULL,
  start_time varchar(16) NOT NULL,
  end_time varchar(16) NOT NULL,
  task_type varchar(64) NOT NULL,
  title varchar(255) NOT NULL,
  reward_points integer DEFAULT 0 NOT NULL,
  requires_parent_confirmation smallint DEFAULT 0 NOT NULL,
  sort_order integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id)
);
CREATE INDEX idx_task_template_items_template ON task_template_items (template_id, sort_order);

CREATE TABLE task_templates (
  id varchar(255) NOT NULL,
  template_key varchar(255) NOT NULL,
  title varchar(255) NOT NULL,
  subtitle varchar(255) NOT NULL,
  grade varchar(32) NOT NULL,
  age_group varchar(64) NOT NULL,
  schedule_type varchar(64) NOT NULL,
  day_type varchar(64) NOT NULL,
  tags_json text NOT NULL,
  status varchar(64) DEFAULT 'active' NOT NULL,
  sort_order integer DEFAULT 0 NOT NULL,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT uq_task_templates_template_key UNIQUE (template_key)
);
CREATE INDEX idx_task_templates_day_type ON task_templates (day_type, status, sort_order);
CREATE INDEX idx_task_templates_grade ON task_templates (grade, status, sort_order);

CREATE TABLE tasks (
  id varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  child_id varchar(255) NOT NULL,
  title varchar(255) NOT NULL,
  description text,
  type varchar(255) NOT NULL,
  status varchar(255) NOT NULL,
  scheduled_date varchar(255) NOT NULL,
  scheduled_start varchar(255),
  scheduled_end varchar(255),
  reward_points integer DEFAULT 0 NOT NULL,
  requires_parent_confirmation smallint DEFAULT 1 NOT NULL,
  evidence_summary text,
  rejection_reason text,
  created_at bigint NOT NULL,
  updated_at bigint NOT NULL,
  completed_at bigint,
  confirmed_at bigint,
  rejected_at bigint,
  points_granted_at bigint,
  schedule_type varchar(255) DEFAULT 'one_time' NOT NULL,
  start_at varchar(255),
  due_at varchar(255),
  repeat_rule text,
  priority integer DEFAULT 3 NOT NULL,
  completion_source varchar(255),
  evidence text,
  ai_observation_summary text,
  created_by varchar(255),
  reminder_minutes_before integer DEFAULT 5 NOT NULL,
  reminder_status varchar(255) DEFAULT 'pending' NOT NULL,
  started_at bigint,
  ended_at bigint,
  missed_at bigint,
  delayed_at bigint,
  last_reminder_at bigint,
  next_reminder_at bigint,
  delay_reminder_count integer DEFAULT 0 NOT NULL,
  camera_observation_status varchar(255) DEFAULT 'unknown' NOT NULL,
  device_id varchar(255),
  timezone varchar(255) DEFAULT 'Asia/Shanghai' NOT NULL,
  learning_course_id varchar(255),
  learning_course_version varchar(64),
  learning_assignment_key varchar(64),
  learning_slot varchar(32),
  PRIMARY KEY (id),
  CONSTRAINT uq_tasks_learning_assignment_key UNIQUE (learning_assignment_key)
);
CREATE INDEX idx_tasks_learning_course ON tasks (family_id, child_id, scheduled_date, learning_course_id);
CREATE INDEX idx_tasks_learning_daily_slot ON tasks (family_id, child_id, scheduled_date, learning_slot);
CREATE INDEX idx_tasks_scheduler_runtime ON tasks (scheduled_date, status, scheduled_start);
CREATE INDEX idx_tasks_student_learning_library ON tasks (family_id, child_id, type, updated_at, id);

CREATE TABLE users (
  id varchar(255) NOT NULL,
  phone varchar(255) NOT NULL,
  family_id varchar(255) NOT NULL,
  display_name varchar(255) NOT NULL,
  account_status varchar(255) DEFAULT 'active' NOT NULL,
  created_at bigint NOT NULL,
  deletion_requested_at bigint,
  deleted_at bigint,
  CONSTRAINT phone UNIQUE (phone),
  PRIMARY KEY (id)
);

CREATE TABLE wifi_configs (
  family_id varchar(255) NOT NULL,
  ssid varchar(255) NOT NULL,
  auth_type varchar(255) NOT NULL,
  password_set smallint NOT NULL,
  saved_at bigint NOT NULL,
  PRIMARY KEY (family_id)
);
