# Overview

`codex-session-sync` helps users move an in-progress Codex conversation between devices with as little friction as possible.

## User Goal

The user should feel like they are doing something close to syncing code:

- choose the work they want
- choose how much fidelity they need
- choose where it should go
- restore it on another machine with as little manual cleanup as possible

## Export Flow

1. Choose a conversation or thread.
2. Choose one of three modes:
   - `快速发送`
   - `继续工作（推荐）`
   - `完整迁移`
3. Choose a destination:
   - GitHub
   - Local zip bundle
4. Export and show a clear result:
   - repo destination
   - local bundle path
   - next step for restore

## Import Flow

1. Choose a source:
   - GitHub
   - Local zip bundle
2. Choose the session to restore.
3. Let the importer decide the safest restore strategy:
   - summary reference
   - continuation context
   - raw local session merge
4. Tell the user exactly what happened.

## Merge Strategy

The skill avoids aggressive merges.

- If a raw session exists and the same session id already exists locally, it treats it as the same session and avoids duplicating it.
- If only lightweight artifacts exist, it restores context rather than forcing a native local-session merge.
- If title, first message, project, and time suggest a likely match, that match is reported as a hint rather than silently overwriting local state.

## Privacy Model

- Lightweight exports still preserve the conversation title and first user message.
- Sensitive-looking strings are redacted from previews.
- Raw session export is available, but it is intentionally not the default.

## Recommended Product Positioning

- `快速发送`: quick backup or lightweight sharing
- `继续工作（推荐）`: best cross-device continuation path
- `完整迁移`: closest to local session restoration
