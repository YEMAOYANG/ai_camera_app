-- Preserve the first, pre-provider 403 rejection while allowing exactly one
-- same-request redispatch after the frozen runtime authentication fix. This
-- does not create a new recovery row or a fourth generation attempt.
ALTER TABLE learning_openmaic_deterministic_recoveries
  ADD COLUMN dispatch_count INTEGER NOT NULL DEFAULT 1
    AFTER status,
  ADD COLUMN first_dispatch_error_code VARCHAR(128)
    AFTER dispatch_count,
  ADD COLUMN first_dispatch_error_message_safe VARCHAR(512)
    AFTER first_dispatch_error_code,
  ADD COLUMN first_dispatch_rejected_at BIGINT
    AFTER first_dispatch_error_message_safe,
  ADD CONSTRAINT chk_openmaic_recovery_dispatch_count
    CHECK (
      (
        dispatch_count = 1
        AND first_dispatch_error_code IS NULL
        AND first_dispatch_error_message_safe IS NULL
        AND first_dispatch_rejected_at IS NULL
      )
      OR
      (
        dispatch_count = 2
        AND first_dispatch_error_code = 'openmaic_recovery_upstream_rejected'
        AND first_dispatch_error_message_safe IS NOT NULL
        AND first_dispatch_rejected_at IS NOT NULL
      )
    );
