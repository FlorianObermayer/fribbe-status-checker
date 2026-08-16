---
name: update-deps
description: "Use when: refreshing Python dependencies with uv, updating uv.lock, regenerating app/licenses.json, and validating the project after dependency changes."
---

# Update project dependencies

Use this workflow when the project needs a dependency refresh, a lockfile update, or a post-upgrade validation pass.

## Goal

Keep the repository's Python dependency set current while preserving the project's expected behavior and generated metadata.

## Required workflow

Use the VS Code task named `Update deps` in [.vscode/tasks.json](../../../.vscode/tasks.json).

## Expected files to change

- `uv.lock`
- `app/licenses.json`

## Notes

- This repository uses uv-managed dependency groups and vendor metadata generation via the script in `scripts/generate_licenses.py`.
- The project checks `app/licenses.json` as generated output, so it should be committed when dependency versions change.
- The validation command should be treated as the proof step before claiming the update is complete.

## Success criteria

- `uv.lock` reflects the upgraded dependency graph.
- `app/licenses.json` is regenerated and current.
- `uv run test` passes without regressions.
