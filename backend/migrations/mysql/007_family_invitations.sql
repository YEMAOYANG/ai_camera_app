CREATE TABLE IF NOT EXISTS family_invitations (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(255) NOT NULL,
  role VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  created_by VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  expires_at BIGINT
);

CREATE INDEX idx_family_invitations_family
  ON family_invitations(family_id, status, created_at);

CREATE INDEX idx_family_invitations_phone
  ON family_invitations(phone, status);
