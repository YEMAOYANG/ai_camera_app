CREATE TABLE IF NOT EXISTS family_default_devices (
  family_id VARCHAR(255) PRIMARY KEY,
  device_id VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CONSTRAINT fk_family_default_devices_family
    FOREIGN KEY (family_id) REFERENCES families(id),
  CONSTRAINT fk_family_default_devices_device
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

CREATE INDEX idx_family_default_devices_device
  ON family_default_devices(device_id);
