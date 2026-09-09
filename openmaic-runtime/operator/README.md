# Operator recovery utilities

These utilities preserve the audit of specific saved-course repairs. They are
not part of application startup or a general course-generation workflow.

`repair_saved_english.py` requires the original local snapshot at
`output/course-library-supply-2026-09-09/recovery/english-original.json` under the
repository root. The root `output/` directory contains local acceptance records
and may contain account, session, or Provider data; it is intentionally excluded
from Git. A fresh clone does not include those snapshots, generated course media,
runtime databases, or credentials. References to `output/` in project documents
refer to the original local verification records.

Use this historical repair only when its matching original snapshot and audit
are available. Do not substitute another classroom or generate replacement
content to satisfy that input. See the runtime README and scripts for normal
bootstrap and startup.
