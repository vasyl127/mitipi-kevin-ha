---
name: jira
description: Look up and update Mitipi Jira issues (MA-* tickets) via Atlassian MCP at mitipi.atlassian.net. Use when fetching ticket details, acceptance criteria, linking branches/commits/PRs to Jira, transitioning issue status, or when the user mentions MA-123, Jira, or Atlassian. For creating new issues from a short description, use jira-create-issue skill.
---

# Jira (Mitipi)

Jira Cloud: **https://mitipi.atlassian.net**  
Project key: **`MA`** (e.g. `MA-735`)

Requires the **Atlassian Rovo MCP** server (see [Setup](#setup)).

## When to use Jira MCP

- Starting work on `feat/MA-735-…` — fetch ticket summary, description, acceptance criteria
- Writing commit messages or PR bodies — link ticket and mirror requirements
- Code review — verify change matches Jira acceptance criteria
- After merge — transition issue (e.g. In Review → Done) if team workflow expects it

## Workflow

### 1. Fetch ticket before coding

```
Get Jira issue MA-735 — summary, description, acceptance criteria, and current status.
```

Use MCP tools to read the issue. Summarize requirements before implementing.

### 2. Branch naming (Gitflow)

```text
feat/MA-735-short-kebab-description
```

See `.claude/skills/gitflow/`.

### 3. Commits (Conventional Commits)

```text
feat(MA-735): add play preset sound feature
```

Scope = ticket ID when available. See `.claude/skills/conventional-commits/`.

### 4. Pull request

- Title: `feat(MA-735): add play preset sound`
- Body: fill ticket link, branch, test scenarios, checklist
- See `.claude/skills/pull-request/`

### 5. Code review

Compare diff against Jira acceptance criteria. See `.claude/skills/code-review/`.

## Example prompts

```text
What are the acceptance criteria for MA-735?
Create a Jira story: user can preview preset sound on card tap
/jira-create-issue fix MQTT reconnect banner when app returns online
Summarize MA-734 and suggest a branch name and commit message.
```

## Setup

### Claude Code (this repo)

Project config is in [`.mcp.json`](../../.mcp.json) (OAuth — safe to commit, no secrets).

1. Open Claude Code in this repo.
2. Approve the `atlassian` MCP server when prompted (`claude mcp list` → pending approval).
3. Complete browser OAuth for **mitipi.atlassian.net** on first use.

**Verify:**

```bash
claude mcp list
claude mcp get atlassian
```

**API token (optional, local-only — no browser re-auth):** see [`.mcp.json.example`](../../.mcp.json.example).

Admin note: org admin may need to enable **Atlassian Rovo MCP** and API token auth in Atlassian AI settings.

### Cursor IDE

1. **Settings → MCP → Add server**
2. URL: `https://mcp.atlassian.com/v1/mcp/authv2`
3. Or install the [Atlassian plugin from Cursor Marketplace](https://cursor.com/marketplace/atlassian)
4. Authenticate with your Mitipi Atlassian account

Cursor and Claude Code use separate MCP configs — set up both if you use both tools.

## Permissions

MCP actions use **your** Jira permissions. You can only read/update issues you already have access to. Do not transition or comment on tickets without user confirmation for high-impact changes.

## Related skills

- **Create issue from description:** `.claude/skills/jira-create-issue/`
- Gitflow: `.claude/skills/gitflow/`
- Commits: `.claude/skills/conventional-commits/`
- PRs: `.claude/skills/pull-request/`
- Review: `.claude/skills/code-review/`
