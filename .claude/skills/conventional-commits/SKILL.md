---
name: conventional-commits
description: Write git commit messages following Conventional Commits v1.0.0 (https://www.conventionalcommits.org/en/v1.0.0/). Use when creating commits, amending messages, reviewing staged changes, or when the user asks for a commit message.
---

# Conventional Commits

All commit messages must follow [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).

## Format

```text
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

- **Description:** imperative mood, lowercase, no trailing period, ≤72 characters
- **Scope:** ticket ID (`MA-735`) or feature area (`presets`, `onboarding`, `ble`, `mqtt`, `serverless`)
- **Body:** explain _why_ and impact — not a file list
- **Breaking change:** append `!` after type/scope, or add footer `BREAKING CHANGE: <description>`

## Types

| Type       | When to use                         |
| ---------- | ----------------------------------- |
| `feat`     | New user-facing capability          |
| `fix`      | Bug fix                             |
| `refactor` | Code change without behavior change |
| `perf`     | Performance improvement             |
| `test`     | Tests only                          |
| `docs`     | Documentation only                  |
| `style`    | Formatting, no logic change         |
| `chore`    | Build, CI, deps, version bumps      |
| `ci`       | CI/CD pipeline changes              |
| `revert`   | Reverts a prior commit              |

Use the **smallest accurate type**. Do not use `feat` for internal-only refactors.

## Workflow

1. Run `git diff --staged` (or `git diff` if nothing staged) to understand the change.
2. Pick one primary type. Split unrelated changes into separate commits when possible.
3. Write subject line first; add body only when context helps reviewers.
4. Reference ticket in scope when known: `feat(MA-735): add play preset sound feature`.

## Examples (this repo)

```text
feat(MA-735): add play preset sound feature

fix(onboarding): redirect existing users to home screen

feat(presets): auto-apply presets after environment switch

fix(presets): correct slider behaviour on small screens

chore: bump ios build number

refactor(ble): extract wifi config into dedicated saga

perf(home): memoize preset list rows

test(presets): cover tombstone cleanup on env change

feat(serverless)!: rename preset activity payload fields

BREAKING CHANGE: clients must send `presetId` instead of `activityPresetId`.
```

## Avoid

- Vague subjects: `fix bug`, `update code`, `wip`, `changes`
- Past tense: `fixed`, `added`, `updated`
- Multiple unrelated changes in one commit
- Committing secrets (`.env`, `env.dev.json`, keystores)

## Multi-commit guidance

When a PR spans layers, prefer focused commits:

```text
feat(presets): add play preset sound UI
test(presets): add saga coverage for play action
chore(ios): bump build number
```

## Related skills

- Branch naming (Gitflow): `.claude/skills/gitflow/`
- PR template: `.claude/skills/pull-request/`
- Code review checklist: `.claude/skills/code-review/`
