# Saved classroom recovery

`run-saved-stage.sh inspect <manifest>` checks the saved repaired snapshot in a real browser without calling the content model. `complete` requires the matching successful preflight and preserves the source job, fixed assessments, review ledger, provider responses and durable dispatch claims.

Ordinary production retains three review attempts. When the user explicitly approves exactly one additional independent review after all three attempts failed or required revision, the local operator manifest may reference `reviewGrantPath`. The grant binds its approval reference, session, stage, complete review identity, exact repaired snapshot and prior ledger hash, with `maxAdditionalReviews: 1`.

The grant is not an Agent tool or a public API. It is reserved once per session before review work and cannot be replayed by renaming the grant, changing the snapshot or restarting the process. The new response has a separate artifact prefix and request identity; the three previous attempts remain intact. Only a validated pass becomes the canonical cache used by audio and publication. Any rejection or ambiguous result stops the course. Existing explicit provider 429 rejection handling remains one bounded retry; connection interruptions and model-result failures are not retried.

After quality passes, only required speech/recognition work and the existing publication gates run. No new Agent session or web search is created. The one-time grant does not increase course production scope or enable the curriculum worker.
