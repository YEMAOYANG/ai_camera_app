-- Keep verification codes scoped to the operation that issued them.
-- Existing rows are short-lived login codes and are labelled accordingly.

ALTER TABLE sms_codes ADD COLUMN purpose varchar(32);

UPDATE sms_codes SET purpose = 'login' WHERE purpose IS NULL;

ALTER TABLE sms_codes ALTER COLUMN purpose SET NOT NULL;
ALTER TABLE sms_codes DROP CONSTRAINT sms_codes_pkey;
ALTER TABLE sms_codes ADD CONSTRAINT sms_codes_pkey PRIMARY KEY (phone, purpose);
ALTER TABLE sms_codes ADD CONSTRAINT chk_sms_codes_purpose
  CHECK (purpose IN ('login', 'phone_change'));
