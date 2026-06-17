# Prompt Registry

Prompts are stored by scenario and referenced by `prompt_id` plus `version`.
Backend business code should reference prompt IDs, not copy prompt text into
routes or UI code.

Required metadata header:

```text
# prompt_id: task.observation.summary
# version: v1
# scenario: task
# status: active
```

Current task prompts:

- `task.observation.summary:v1` summarizes camera task observations for parents.
- `task.reminder.voice:v1` generates short child-facing voice reminders from task context.

Camera care prompts are separate from task prompts:

- `reminder.*:v1` generates JSON-only camera care reminder text.
- `vision.*:v1` reserves structured scene and behavior summary prompts for future camera observation adapters.

Reminder prompts must return JSON with `text`, `tone`, `scenario`, and `safety`.
