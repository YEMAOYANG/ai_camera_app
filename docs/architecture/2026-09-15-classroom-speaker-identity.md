# Classroom learner identity and optional exploration discussion

## Problem

A published discussion originally selected the virtual peer `peer-lele` and asked 乐乐 to explain a misconception. The required-teaching authority correctly replaced unsnapshotted peer personas with the verified teacher, but retained the original discussion text. A real learner reply remained `role: user`; nevertheless the teacher credited that reply to 乐乐. Saved conversation replay was scoped correctly: the attribution error was already in the generated reply.

## Runtime change

Patch 0107 introduces `mira.classroom-speaker-identity.v1`. Only the authenticated required-teaching execution path enables it through the existing server-owned `requiredVisibleTeaching` flag. The director and both Native and Legacy teacher runtimes receive the same rule: `role: user` is the real learner, and virtual peers are separate classroom agents. Direct feedback addresses the real learner as 你. Names in a script, avatar, or previous mistaken teacher reply cannot supply the learner identity.

Model-facing history adds explicit real-learner / classroom-agent labels while preserving message roles and source words. The current-turn prompt marks the original discussion text as course context and identifies the latest real learner separately; a fresh conversation still has no learner answer. Default non-required paths keep their existing prompt/history output.

This policy is applied after saved canonical conversation reconstruction. It therefore governs new replies in existing conversations without rewriting old canonical requests, messages, replay caches, generated classroom content, narration, or publication fingerprints. Existing erroneous reply replay retains its original text; this patch does not manufacture corrected historical responses.

## Contract and verification

No student, gateway or backend API changes. No new identity field is taken from the browser. No paid Provider call or new classroom generation is required to install this change. Focused offline regression tests cover conflicting old prompts, incorrect old feedback, absent profiles, forged display metadata, virtual agent identity, fresh conversations, default-path compatibility, and actual teacher/director prompt wiring. Production build and managed runtime health verify deployment. These checks validate the execution contract; they do not claim a paid live-model response was re-evaluated.

## Optional discussion and exploration participation

Patch 0107 retains explicit participation in scripted discussions: a student can join or choose 跳过讨论, and timers cannot automatically join or skip. Selecting the next page consumes a pending discussion playback action; an active conversation first asks to end and continue. Error and interrupted states also offer continue and skip. This does not fabricate a learner answer or mark the Native teaching conversation completed. A scene-end receipt is saved only when its actual remaining playback actions are exhausted.

The frontend no longer redirects navigation to an unfinished discussion. Backend `openmaic_runtime_event_service.py` likewise removes the independent mandatory-teaching check for scene and classroom receipts. Existing signed event envelopes, binding validation, scene completion, exploration participation and authoritative independent questions still gate course completion.

Exploration observation now accepts a real trusted operation on a declared control/action with changed state and visible feedback. Publication examples such as 2/4 = 50% describe inspector samples, not the exact answer a learner must reproduce. A 3/5 = 60% result counts as participation. Native private frame-channel checks and backend objective/control/action validation remain. Participation alone submits no quiz answer and awards no mastery.

The existing `interaction_observed`, `action_completed` and `classroom_completed` contracts are unchanged. No new client identity authority, skip-answer event, paid model request, course regeneration or frozen courseware edit is introduced. Backend focused interaction/event-bridge tests and Native prompt wiring, discussion state and observer tests cover these contracts. Actual runtime checks are recorded separately after the production build and managed restart.

## Runtime discovery: scene navigation order

The first live browser check exposed a pre-existing `runtime_event_scene_gap` rejection when a newly launched runtime stream entered a later catalog page. The event client retained that valid page visit as a pending receipt, so subsequent operation events could not flush. Scene visits now accept any correctly bound, published page in the current course. A visit remains only a visit: later events still require entry into that scene, and course completion still requires every expected scene, its final playback action, exploration participation and authoritative independent answers. The event sequence and idempotency contracts are unchanged; no pending event or historical receipt is silently discarded.

## Deployed verification

Production build `SXq0uiYDpswqafWUuIQsl` succeeded, and the managed stack was restarted. The final backend navigation adjustment was loaded with a scoped managed backend restart. Native focused verification passed 50 combined tests plus 110 existing prompt/child/route regressions; the final backend interaction/event-bridge suite passed 28 tests.

A separate Chrome tab in the real student classroom showed 加入讨论 and 跳过讨论; clicking skip removed the invitation without a learner message. After the navigation fix, real numerator-plus clicks and a denominator-plus click produced 3/5 = 0.6 = 60%, and Next scene entered page 5. The updated tab is paused there for the learner. The original user's tab and its displayed conversation were not refreshed. Existing teaching conversation timestamps and message counts remained unchanged; no paid model turn was executed. Detailed evidence: `output/classroom-usability-0107-validation-20260915.json`.
