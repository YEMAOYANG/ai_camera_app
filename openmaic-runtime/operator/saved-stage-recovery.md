# Saved classroom recovery

`run-saved-stage.sh inspect <manifest>` checks the saved repaired snapshot in a real browser without calling the content model. `complete` requires the matching successful preflight and preserves the source job, fixed assessments, review ledger, provider responses and durable dispatch claims.

Ordinary production retains three review attempts. When the user explicitly approves exactly one additional independent review after all three attempts failed or required revision, the local operator manifest may reference `reviewGrantPath`. The grant binds its approval reference, session, stage, complete review identity, exact repaired snapshot and prior ledger hash, with `maxAdditionalReviews: 1`.

The grant is not an Agent tool or a public API. It is reserved once per session before review work and cannot be replayed by renaming the grant, changing the snapshot or restarting the process. The new response has a separate artifact prefix and request identity; the three previous attempts remain intact. Only a validated pass becomes the canonical cache used by audio and publication. Any rejection or ambiguous result stops the course. Existing explicit provider 429 rejection handling remains one bounded retry; connection interruptions and model-result failures are not retried.

After quality passes, only required speech/recognition work and the existing publication gates run. No new Agent session or web search is created. The one-time grant does not increase course production scope or enable the curriculum worker.

Patch `0257` adds `prepare-missing-locked-quiz` / `run-missing-locked-quiz` to `scripts/repair-textbook-rejected-scene.ts` for a terminal, owned textbook job whose frozen quiz page was never saved. Prepare reads the exact current document/candidate hashes and constructs the page from the original locked assessment. Only its missing image keys may receive first bindings to verified, stage-owned PNG bytes; deterministic local artwork is recorded in the repair evidence. Existing bindings, questions, answers and page order stay frozen.

Review the sealed prepare plan before run. Run uses the existing owner-bound transaction and saves the original document, candidate and PNG bytes in an append-only repair directory. Retry the same plan after an interrupted run so its intent can reconcile a database rollback or missing receipt. The resulting candidate still needs whole-course play, audio, review, publication and student-entry acceptance.
