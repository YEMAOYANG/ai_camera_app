"use client";

import { OTPInput, REGEXP_ONLY_DIGITS } from "input-otp";
import type { Ref } from "react";

type PinInputProps = {
  id: string;
  value: string;
  onChange(value: string): void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  ref?: Ref<HTMLInputElement>;
};

export function PinInput({ id, value, onChange, disabled, invalid, describedBy, ref }: PinInputProps) {
  return <OTPInput ref={ref} id={id} value={value} onChange={onChange} maxLength={4}
    type="password" pattern={REGEXP_ONLY_DIGITS} inputMode="numeric" autoComplete="current-password"
    disabled={disabled} aria-invalid={invalid} aria-describedby={describedBy}
    containerClassName="mira-pin" data-invalid={invalid || undefined}
    render={({ slots, isFocused }) => <div className="mira-pin-slots" data-invalid={invalid || undefined} data-disabled={disabled || undefined} aria-hidden="true">
      {slots.map((slot, index) => <div key={index} className="mira-pin-slot" data-active={isFocused && slot.isActive || undefined} data-filled={Boolean(slot.char) || undefined}>
        {slot.char ? <span className="mira-pin-dot" /> : slot.hasFakeCaret ? <span className="mira-pin-caret" /> : <span className="mira-pin-placeholder" />}
      </div>)}
    </div>} />;
}
