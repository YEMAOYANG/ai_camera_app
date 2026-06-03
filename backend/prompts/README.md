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
