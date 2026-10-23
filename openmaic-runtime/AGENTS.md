# OpenMAIC learning integration

For grade 1–2 games and courseware, follow the root AGENTS low-reading rule and `../docs/learning/low-reading-interaction-rule.md`. Children must be able to follow narration and choose distinguishable pictures without reading question text, names or answer labels. Native hand-authored scenes are subject to the same rule as generated scenes.

For textbook authoring and review across the four subjects, read `../backend/content/textbook_interaction_policy.v1.json`. New workbench requests explicitly freeze and inject this policy; follow its scoped precedence over generic skill quotas. Judge mechanisms by the child's decisions, real domain-state changes, computed consequences, revision and learning evidence, not by input modes or `widgetType` counts. Preserve explicitly approved plans and all textbook, teacher, audio and publication contracts. Older formal skill bodies and context hashes are historical contracts: do not rewrite them or running-job prompts to claim an upgrade. Authorized course repairs must preserve the original and record a revision or follow-up with actual play review.

Keep the existing classroom, teacher, discussion and student authentication boundaries. Put durable native source changes in the numbered patch series and update the lock manifest. Use the managed local stack for runtime checks; never replace an unidentified listener by port.

Student classrooms always show the original playback toolbar: directory, sound, playback speed, previous/next, play, whiteboard, fullscreen and chat stay directly accessible. Do not add toolbar collapse/expand controls, replace the toolbar with a header “更多” menu, or add a duplicate bottom navigation bar. Preserve the teacher/discussion area.

Native classroom action sizes use the shared `--mira-orbit-*` control tokens in `app/mira-student-orbit.css`. Desktop playback controls use 30px targets with 16px icons; activity secondary actions and replay use 36px, primary actions use 40px, and activity icons use 18px. Touch controls retain at least 48px targets. Keep illustrated answers and drag targets large; do not independently enlarge action buttons per scene. Generated iframe polish is limited to declared utility controls and known toolbar action IDs; preserve authored visibility and learning-object geometry.

Preserve automatic teacher narration for active questions and feedback. Announce completion only when an action completes the current activity; reopening saved results stays quiet and offers explicit replay.
