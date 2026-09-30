# OpenMAIC learning integration

For grade 1–2 games and courseware, follow the root AGENTS low-reading rule and `../docs/learning/low-reading-interaction-rule.md`. Children must be able to follow narration and choose distinguishable pictures without reading question text, names or answer labels. Native hand-authored scenes are subject to the same rule as generated scenes.

Keep the existing classroom, teacher, discussion and student authentication boundaries. Put durable native source changes in the numbered patch series and update the lock manifest. Use the managed local stack for runtime checks; never replace an unidentified listener by port.

Student classrooms always show the original playback toolbar: directory, sound, playback speed, previous/next, play, whiteboard, fullscreen and chat stay directly accessible. Do not add toolbar collapse/expand controls, replace the toolbar with a header “更多” menu, or add a duplicate bottom navigation bar. Preserve the teacher/discussion area.

Native classroom action sizes use the shared `--mira-orbit-*` control tokens in `app/mira-student-orbit.css`. In `textbook-play.module.css`, use 36px for secondary actions, 48px for primary actions and icon-only replay, and 18px icons. Compact controls retain 48px touch targets. Keep illustrated answers and drag targets large; do not independently enlarge action buttons per scene.

Preserve automatic teacher narration for active questions and feedback. Announce completion only when an action completes the current activity; reopening saved results stays quiet and offers explicit replay.
