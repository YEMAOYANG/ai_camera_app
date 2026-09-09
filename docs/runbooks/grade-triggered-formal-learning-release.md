# Grade-triggered formal learning release runbook

## Scope and safety boundary

This runbook covers the single production allowlist entry `primary_1` and the
publication contract `mira.learning.formal-publication.v1`.

The verifier is read-only. It opens a MySQL read-only transaction and issues
only aggregate `SELECT` statements. It does not generate courses, contact the
Runtime or any Provider, publish a release, move a pointer, delete data, or
perform rollback. Its JSON output omits database identities, hashes, prompts,
credentials, family/child identifiers, and course or conversation content.

The following are hard stop conditions:

- the configured grade allowlist is anything other than exactly `primary_1`;
- migrations 056 through 061 or any required evidence table are absent;
- an active pointer does not match its exact history and release row;
- the pointer contract is not `mira.learning.formal-publication.v1`;
- fewer than 30 release items have matching course, package, Runtime, 057,
  058, and 059 evidence;
- the Grade-1 distribution is not 12 Chinese, 9 math, and 9 English courses;
- a session event stream has a sequence gap or exceeds the accepted event-lag
  threshold.

Do not override a failed check with a direct status edit.

## Prerequisites

1. Run from the deployed backend revision containing migrations 056–061.
2. Inject `DATABASE_URL` through the deployment secret manager. Never paste it
   into a ticket, command history, log, or verifier argument.
3. Set `LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=primary_1`.
4. Keep generation, automatic publication, and student-release gates in their
   reviewed state. Running this verifier never changes a gate.
5. Use a database account whose permissions are limited to the required
   `SELECT` operations whenever possible.

## Preflight

Run before enabling a release or starting a controlled Grade-1 publication:

```sh
cd backend
python3 scripts/verify_grade_release.py --phase preflight
```

Preflight passes without an active pointer when this is the first release. If
an active pointer already exists, that pointer and all 30 items must still be
exact; a broken current release is never ignored merely because a new release
is being prepared.

The default active-session event-lag ceiling is 300 seconds. A stricter reviewed
value may be supplied without changing data:

```sh
python3 scripts/verify_grade_release.py \
  --phase preflight \
  --max-event-lag-seconds 120
```

Exit codes are stable:

- `0`: every required check passed;
- `1`: the database was read successfully, but one or more release checks
  failed;
- `2`: configuration, input, schema access, or database availability prevented
  verification.

An exit code of `1` or `2` blocks release progression.

## Postflight

Run immediately after the formal publication transaction and before student
release is enabled:

```sh
cd backend
python3 scripts/verify_grade_release.py --phase postflight
```

Postflight requires all of the following as one coherent snapshot:

- the `primary_1` pointer, its selected history row, and its published release
  agree on revision, target fingerprint, contract, release, and activation;
- the history row was produced by formal publication and has a publication
  receipt;
- the release is `published/ready`, is not retired, and reports 30 ready items;
- exactly 30 published release items resolve to the same build items, released
  courses, published packages, ready Runtime classrooms, published 057
  receipts, terminal 058 audio receipts, and terminal 059 five-call Provider
  receipts;
- the subject-specific Qwen voice route is present with no fallback;
- every Runtime event stream has a contiguous persisted event count, and every
  active stream is within the reviewed lag ceiling.

The report exposes only aggregate fields such as pointer revision, item count,
session count, stream count, and maximum lag. Save the complete JSON and exit
code in the restricted release evidence location; do not enrich it with raw
database rows.

After student release begins, run postflight on the monitoring interval and
alert on any non-zero exit code. Zero bound sessions or event streams is valid
immediately after publication. Once streams exist, sequence consistency and
lag are fail-closed.

## Failure response

1. Keep or return the affected release gates to their reviewed off state.
2. Preserve the verifier JSON and service metrics; do not export raw prompts,
   classroom content, credentials, or child records.
3. Identify whether the failure is schema, pointer/history, release evidence,
   event consistency, or event lag.
4. Repair through the owning pipeline. Never insert receipts, update statuses,
   retire an old grade release, or move sessions manually to make verification
   pass.
5. Re-run preflight and postflight after the repair.

## Emergency grade-pointer rollback contract

Rollback is an explicitly reviewed emergency operation, not a command provided
by `verify_grade_release.py`. It requires a release manager and a database
reviewer. The previous release must first be proven to contain the same exact
30-item 057/058/059 evidence and must remain published, ready, and unretired.

The approved implementation is one grade-scoped database transaction with one
pointer CAS update:

1. lock the current `primary_1` pointer and confirm the expected current
   history identity;
2. lock its `previous_history_id` row and the previous release;
3. re-run the same 30-item evidence predicates used by postflight for that
   previous release inside the transaction;
4. update only `learning_curriculum_grade_release_pointers` to the exact tuple
   already stored on the reviewed previous history row, conditional on the
   still-current history identity;
5. commit, then run postflight and keep automatic publication disabled until
   the result is reviewed.

This is a contract for the reviewed operator implementation, not copy-paste
SQL. The transaction must not update or delete release history, releases,
release items, courses, packages, Runtime rows, receipts, learning sessions,
formal session bindings, events, reports, or mastery records. In particular,
do not clear the old history row's `superseded_at`; the pointer is the current
authority and historical rows remain immutable.

A rollback may move the pointer revision back to an earlier stored revision.
Keep automatic publication off afterward. Before a later forward publication,
review the monotonic revision/CAS path explicitly; do not repair the revision
chain by rewriting history.

## Prohibited operations

- running a global curriculum activation or retirement path;
- deleting or rewriting any release/history/session/event artifact;
- changing another grade pointer;
- manually fabricating 057, 058, or 059 receipts;
- reissuing Provider calls from a verifier or GET/status path;
- printing database URLs, tokens, prompt text, child content, or raw event
  payloads;
- describing a successful verifier run as proof that the entire product is
  production-ready. It proves only the checks listed in this runbook.
