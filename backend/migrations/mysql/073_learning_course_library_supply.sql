-- A shared production owner survives child/profile changes and account deletion.
ALTER TABLE learning_curriculum_preparation_plans
  MODIFY COLUMN family_id VARCHAR(255) NULL,
  MODIFY COLUMN child_id VARCHAR(255) NULL,
  ADD COLUMN library_target_fingerprint CHAR(64) NULL,
  ADD UNIQUE KEY uq_learning_library_owner(library_target_fingerprint),
  ADD CONSTRAINT chk_learning_library_owner CHECK (
    (library_target_fingerprint IS NULL AND family_id IS NOT NULL AND child_id IS NOT NULL)
    OR (library_target_fingerprint IS NOT NULL AND library_target_fingerprint = target_fingerprint
      AND family_id IS NULL AND child_id IS NULL AND grade_selection_revision = 0)
  );

CREATE TABLE learning_course_supply_requests (
  target_fingerprint CHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  skill_id VARCHAR(128) NOT NULL,
  variant_ordinal INTEGER NOT NULL,
  priority INTEGER NOT NULL,
  purpose VARCHAR(32) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (target_fingerprint, subject, skill_id, variant_ordinal),
  CONSTRAINT fk_learning_supply_owner FOREIGN KEY (target_fingerprint)
    REFERENCES learning_curriculum_preparation_plans(library_target_fingerprint),
  CONSTRAINT chk_learning_supply_variant CHECK (variant_ordinal BETWEEN 1 AND 3),
  CONSTRAINT chk_learning_supply_priority CHECK (priority >= 0),
  CONSTRAINT chk_learning_supply_purpose CHECK (purpose IN ('canary', 'core', 'review', 'forward'))
);

CREATE TABLE learning_course_supply_incidents (
  build_item_id VARCHAR(128) PRIMARY KEY,
  stage VARCHAR(64) NOT NULL,
  reason_code VARCHAR(128) NOT NULL,
  blocked_at BIGINT NOT NULL,
  last_observed_at BIGINT NOT NULL,
  resolved_at BIGINT NULL,
  CONSTRAINT fk_learning_supply_incident_item FOREIGN KEY (build_item_id)
    REFERENCES learning_catalog_build_items(id)
);
