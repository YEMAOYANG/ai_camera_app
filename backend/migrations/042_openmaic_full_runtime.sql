CREATE TABLE IF NOT EXISTS learning_openmaic_runtime_classrooms (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  upstream_job_id VARCHAR(128),
  upstream_classroom_id VARCHAR(255),
  status VARCHAR(32) NOT NULL,
  quality_status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
  feature_manifest_json LONGTEXT NOT NULL,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  ready_at BIGINT,
  reviewed_by VARCHAR(128),
  reviewed_at BIGINT,
  review_notes VARCHAR(1000),
  retired_at BIGINT,
  UNIQUE KEY uq_learning_openmaic_runtime_request(request_id),
  UNIQUE KEY uq_learning_openmaic_runtime_package(package_id, package_version),
  UNIQUE KEY uq_learning_openmaic_runtime_upstream(upstream_classroom_id),
  INDEX idx_learning_openmaic_runtime_course(
    course_id(96), course_version, status, updated_at
  ),
  INDEX idx_learning_openmaic_runtime_quality(
    status, quality_status, updated_at
  ),
  CONSTRAINT fk_learning_openmaic_runtime_package
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version)
);

CREATE TABLE IF NOT EXISTS student_openmaic_launch_tickets (
  id VARCHAR(128) PRIMARY KEY,
  token_hash CHAR(64) NOT NULL,
  principal_id VARCHAR(128) NOT NULL,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  learning_session_id VARCHAR(255) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  expires_at BIGINT NOT NULL,
  consumed_at BIGINT,
  revoked_at BIGINT,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_student_openmaic_launch_token(token_hash),
  INDEX idx_student_openmaic_launch_principal(
    principal_id, expires_at, consumed_at
  ),
  INDEX idx_student_openmaic_launch_session(
    learning_session_id(96), created_at
  ),
  CONSTRAINT fk_student_openmaic_launch_principal
    FOREIGN KEY (principal_id) REFERENCES student_principals(id),
  CONSTRAINT fk_student_openmaic_launch_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id)
);

CREATE TABLE IF NOT EXISTS student_openmaic_runtime_sessions (
  id VARCHAR(128) PRIMARY KEY,
  token_hash CHAR(64) NOT NULL,
  launch_ticket_id VARCHAR(128) NOT NULL,
  principal_id VARCHAR(128) NOT NULL,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  learning_session_id VARCHAR(255) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  expires_at BIGINT NOT NULL,
  last_active_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  revoked_at BIGINT,
  UNIQUE KEY uq_student_openmaic_runtime_token(token_hash),
  UNIQUE KEY uq_student_openmaic_runtime_ticket(launch_ticket_id),
  INDEX idx_student_openmaic_runtime_principal(
    principal_id, expires_at, revoked_at
  ),
  INDEX idx_student_openmaic_runtime_learning_session(
    learning_session_id(96), created_at
  ),
  CONSTRAINT fk_student_openmaic_runtime_ticket
    FOREIGN KEY (launch_ticket_id)
      REFERENCES student_openmaic_launch_tickets(id),
  CONSTRAINT fk_student_openmaic_runtime_principal
    FOREIGN KEY (principal_id) REFERENCES student_principals(id),
  CONSTRAINT fk_student_openmaic_runtime_classroom
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id)
);
