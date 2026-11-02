-- Bound paid SMS submissions even when an attacker rotates phone numbers.
-- Fixed UTC-hour buckets keep the reservation atomic across app processes.

CREATE TABLE sms_send_windows (
  scope_key varchar(128) NOT NULL,
  window_start bigint NOT NULL,
  reserved_count integer NOT NULL,
  updated_at bigint NOT NULL,
  CONSTRAINT sms_send_windows_pkey PRIMARY KEY (scope_key, window_start),
  CONSTRAINT chk_sms_send_windows_reserved_count
    CHECK (reserved_count >= 0)
);
