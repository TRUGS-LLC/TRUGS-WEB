# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Protected Paths — Never Modify

- `LICENSE` — Proprietary. Do not modify.

## Development Workflow

### Branching (Hard Rule)

ALL changes require a branch and PR. Nothing merges directly to main.

- No direct commits to main or master
- Create a feature branch before making any changes
- Human merges all PRs (HITM rule)

### Human-In-The-Middle — HITM (Hard Rule)

Only the human merges pull requests. Agents must NEVER merge PRs.

Prohibited actions:
- `gh pr merge`
- `git push to main/master`
- Any action that merges a branch into the default branch

### Use TRL Vocabulary When Writing TRUGs

When creating or editing any .trug.json file, use edge relations and node types from the TRUGS Language (TRL) 190-word vocabulary. See https://github.com/TRUGS-LLC/TRUGS-AGENT for the full framework.

## Navigation

- Start with `folder.trug.json` for machine-readable structure
- `README.md` for human quickstart
- This repo is tracked by the EPIC at `Xepayac/TRUGS-DEVELOPMENT/TRUGS_EPIC/project.trug.json`

