# OpenMAIC learning integration

For all new courseware, including grade 1–2 low-reading games, follow `../docs/learning/courseware-standard.md`. Children must be able to follow narration and choose distinguishable pictures without reading question text, names or answer labels. Native hand-authored scenes are subject to the same rule as generated scenes.

The older interaction policy files and the frozen workbench contracts belong to lessons that are already published. Older formal skill bodies and context hashes are historical contracts: do not rewrite them or running-job prompts to claim an upgrade. Repair a published lesson by publishing a new version, with actual play review.

Keep the existing classroom, teacher, discussion and student authentication boundaries. Put durable native source changes in the numbered patch series and update the lock manifest. Use the managed local stack for runtime checks; never replace an unidentified listener by port.

Student classrooms always show the original playback toolbar: directory, sound, playback speed, previous/next, play, whiteboard, fullscreen and chat stay directly accessible. Do not add toolbar collapse/expand controls, replace the toolbar with a header “更多” menu, or add a duplicate bottom navigation bar. Preserve the teacher/discussion area.

Native classroom utility buttons use the single `lib/ui/classroom-controls.ts` presentation contract, shared by RootLayout and isolated iframe tools. Components expose semantic `data-mira-control` roles; CSS Modules and `app/mira-student-orbit.css` own layout and theme tokens, without overriding button dimensions or appearance. Desktop playback controls use 30px targets with 16px icons; activity secondary actions and replay use 36px, primary actions use 40px, and activity icons use 18px. Any coarse pointer retains at least 48px targets. Keep illustrated answers and drag targets large; do not independently enlarge action buttons per scene. Generated iframe polish is limited to declared utility controls and known toolbar action IDs; preserve authored visibility and learning-object geometry.

Preserve automatic teacher narration for active questions and feedback. Announce completion only when an action completes the current activity; reopening saved results stays quiet and offers explicit replay.
