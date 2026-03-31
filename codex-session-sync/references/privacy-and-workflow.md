# Privacy And Workflow

## Recommendation

Use a private GitHub repository dedicated to Codex continuity notes.

Prefer this rollout:

1. Sync Markdown summaries by default.
2. Add raw `jsonl` mirroring only for sessions where exact replay matters.
3. Keep code changes in the real project repository, not in the session-sync repo.

## What Summary Sync Preserves Well

- The task goal
- The recent user requests
- The assistant's final answers
- The working directory and session timestamp
- Enough context to continue on another machine

## What Raw Mirroring Adds

- Full local event stream
- Intermediate commentary
- Tool call traces
- More exact forensic history

## What Raw Mirroring Risks

- Sensitive prompts
- Local file paths
- Search queries
- Broader context than you intended to publish

## Suggested Team Pattern

- Put code in the project repository.
- Put session continuity notes in a separate private repository.
- When a task becomes important, ask Codex to sync the current session summary before switching devices.
