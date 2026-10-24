# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## License — do not alter the terms

- `LICENSE` is **Apache-2.0**; `NOTICE` carries attribution only. Preserve both verbatim; do not change the license terms. See the README [Scope](README.md#scope) for what this software includes.

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

When creating or editing any `.trug.json` file, use edge relations and node types from the TRUGS Language (TRL) vocabulary. See [TRUGS-LLC/TRUGS](https://github.com/TRUGS-LLC/TRUGS) for the specification.

## Navigation

- Start with `folder.trug.json` for machine-readable structure
- `README.md` for the human quickstart
- This repository is part of the public TRUGS-LLC collection; see CHANGELOG.md for release notes.
