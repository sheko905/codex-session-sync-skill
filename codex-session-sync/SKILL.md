---
name: codex-session-sync
description: Sync Codex local desktop session history into a Git repository with resumable Markdown summaries and optional raw JSONL mirrors. Use when Codex needs to preserve, migrate, back up, or continue work across devices by exporting sessions from ~/.codex/sessions and committing them into a private GitHub-backed repo.
---

# Codex Session Sync

Use this skill to turn local Codex desktop sessions into portable artifacts that can be resumed on another machine.

Offer three user-facing sync modes:

- `快速发送`
- `继续工作（推荐）`
- `完整迁移`

Use this skill as a guided workflow inside Codex. Do not make the user run multiple commands manually unless they explicitly want to.

## Workflow

### Export

1. Let the user choose a conversation or thread.
2. Let the user choose an export mode.
3. Let the user choose an export destination.
4. If the destination is GitHub, gather the repository info and upload there.
5. If the destination is local file export, create a zip bundle and return the file path.

### Import

1. Let the user choose an import source.
2. If the source is GitHub, gather the repository info and list importable sessions.
3. If the source is a local file, ask for the bundle path.
4. Restore the session into local Codex storage according to what the bundle contains.

## Interaction Pattern

When this skill is used, guide the user in small steps:

1. Run `scripts/list_codex_sessions.py` to gather candidates.
2. Present a short selection UI.
3. Ask for export mode with `scripts/list_sync_modes.py`.
4. Ask for export destination with `scripts/list_export_destinations.py`, or import source with `scripts/list_import_sources.py`.
5. After the user chooses, run the matching export or import script.

When a native selector is available, prefer:

```bash
python3 skills/codex-session-sync/scripts/list_codex_sessions.py --selector-json
```

Treat each item as:

- `label`: session title for the visible row title
- `description`: time, project, and a safe preview
- `value`: session id
- `group`: project name

For the sync mode picker, prefer:

```bash
python3 skills/codex-session-sync/scripts/list_sync_modes.py --selector-json
```

For export destination choices, prefer:

```bash
python3 skills/codex-session-sync/scripts/list_export_destinations.py --selector-json
```

For import source choices, prefer:

```bash
python3 skills/codex-session-sync/scripts/list_import_sources.py --selector-json
```

Do not dump raw paths or long command syntax up front. Lead with plain language such as:

- "I found 3 recent projects. Which one do you want to continue on this device?"
- "你想怎么带走这段对话：快速发送、继续工作，还是完整迁移？"
- "你想上传到 GitHub，还是先导出成本地文件？"
- "你想从 GitHub 恢复，还是从本地导出包恢复？"

When the user wants the imported session to appear locally again, explain the distinction:

- Summary plus context bundle restores high-quality continuation material.
- Raw session import is required for the closest thing to native local session merging.

## Safety Rules

- Prefer a private repository.
- Warn that raw session files may contain prompts, file paths, tool traces, and other sensitive context.
- Avoid syncing auth files, token files, or anything outside `~/.codex/sessions`.
- Default to `继续工作（推荐）`.

## Commands

Only sync sessions from one project:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --project "AI 小工具"
```

Export the latest session into a repo:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo
```

Export the latest session as a local bundle:

```bash
python3 skills/codex-session-sync/scripts/export_local_bundle.py \
  --out-dir /absolute/path/to/exports \
  --mode continuation
```

Export summary only:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --mode summary
```

Export the recommended continuation package:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --mode continuation
```

Export the latest two sessions and push:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --latest 2 \
  --push
```

Also mirror the raw session file:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --mode archive
```

Import a local bundle:

```bash
python3 skills/codex-session-sync/scripts/import_local_bundle.py \
  --bundle /absolute/path/to/codex-session-export-xxxxxx.zip
```

Target one known session file:

```bash
python3 skills/codex-session-sync/scripts/sync_codex_sessions.py \
  --repo /absolute/path/to/private-repo \
  --session ~/.codex/sessions/2026/03/31/rollout-...jsonl
```

## Output Layout

Write exported material into:

- `sessions/YYYY/MM/DD/<session-id>/artifact.json`
- `sessions/YYYY/MM/DD/<session-id>/summary.md`
- `sessions/YYYY/MM/DD/<session-id>/context.json`
- `sessions/YYYY/MM/DD/<session-id>/raw.jsonl` when `--copy-raw` is used
- `latest.md` as a convenience copy of the newest summary

## Bundled Scripts

- `scripts/list_codex_sessions.py`
  Use to gather recent sessions in a user-friendly list before asking the user what to sync. Use `--selector-json` when a native picker is available.
- `scripts/list_sync_modes.py`
  Use to present the three human-readable sync modes. Use `--selector-json` when a native picker is available.
- `scripts/list_export_destinations.py`
  Use to present the two export destinations: GitHub or local bundle.
- `scripts/list_import_sources.py`
  Use to present the two import sources: GitHub or local bundle.
- `scripts/sync_codex_sessions.py`
  Use to export the chosen session or project into a Git repo. Default output should favor continuation quality with summary plus `context.json`.
- `scripts/import_codex_sessions.py`
  Use to restore synced artifacts on another machine. Merge raw sessions into local Codex storage when available, and always restore `context.json` plus `summary.md` for continuation.
- `scripts/export_local_bundle.py`
  Use to create a local zip bundle when the user chooses file export instead of GitHub.
- `scripts/import_local_bundle.py`
  Use to restore a local zip bundle back into local Codex storage.
- `scripts/build_codex_session_browser.py`
  Optional fallback. Use only when the user explicitly wants a standalone visual page.

## Resume Pattern

On another machine, prefer the restored `context.json` plus `summary.md` and continue from them. A good prompt is:

```text
Use the restored Codex continuation bundle at <context-dir>/context.json and <context-dir>/summary.md as continuation context. Reconstruct the task state, list open decisions, then continue implementation in the current workspace.
```

## References

- Read [privacy-and-workflow.md](references/privacy-and-workflow.md) when you need guidance on choosing summary-only vs raw mirroring.
