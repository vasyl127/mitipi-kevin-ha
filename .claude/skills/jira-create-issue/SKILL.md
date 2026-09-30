---
name: jira-create-issue
description: Create a Jira Story or Task in project MA from a short natural-language description using Atlassian MCP. Expands summary, acceptance criteria, and mobile test scenarios, shows a preview, then creates the issue. Use when the user asks to create a Jira ticket, story, task, or backlog item from a brief description.
argument-hint: '<short description of the work>'
---

# Create Jira Story / Task

Turn a **short description** into a well-formed Jira issue in **project `MA`** on **mitipi.atlassian.net**.

Requires **Atlassian Rovo MCP** (see `.claude/skills/jira/SKILL.md` → Setup).

## Usage

```
/jira-create-issue preset preview plays sound when user taps card
```

Or: _"Create a Jira story: add offline banner when MQTT disconnects"_

## Workflow

Copy this checklist and track progress:

```
- [ ] 1. Parse user input (description, optional type, optional assignee)
- [ ] 2. Resolve cloudId for mitipi.atlassian.net
- [ ] 3. Confirm issue type (Story / Task / Bug)
- [ ] 4. Draft summary + full description
- [ ] 5. Show preview — wait for user approval
- [ ] 6. createJiraIssue via MCP
- [ ] 7. Return issue key, URL, suggested branch + commit
```

### Step 1 — Parse input

Extract from the user's message:

- **Short description** (required)
- **Issue type** (optional): `Story`, `Task`, or `Bug` — infer if omitted (see below)
- **Assignee** (optional): use `atlassianUserInfo` or `lookupJiraAccountId`
- **Parent Epic** (optional): issue key for subtasks or epic-linked stories

### Step 2 — Resolve cloudId

Call **`getAccessibleAtlassianResources`** and pick the resource for **`mitipi.atlassian.net`**.

If multiple sites match, ask the user. Cache `cloudId` for the rest of the workflow.

Optionally call **`getJiraProjectIssueTypesMetadata`** with `projectKey: "MA"` to confirm `Story`, `Task`, and `Bug` exist.

If **`getJiraIssueTypeMetaWithFields`** shows required custom fields, include them in `additional_fields` or ask the user.

### Step 3 — Choose issue type

| Type      | Use when                                                                             |
| --------- | ------------------------------------------------------------------------------------ |
| **Story** | User-facing feature, UX change, new app behaviour visible to end users               |
| **Task**  | Technical work, refactor, CI, serverless, deps, docs, tooling — no direct user story |
| **Bug**   | User says bug, fix, regression, crash, broken behaviour                              |

Default to **Story** for ambiguous mobile UI/flow work; **Task** for backend-only or infra.

### Step 4 — Draft the issue

**Summary** (title):

- Imperative, concise, ≤80 characters
- No trailing period
- Example: `Add preset preview sound on card tap`

**Description** — use the matching template from [templates.md](templates.md):

- **Story** → user story + acceptance criteria + iOS/Android test notes
- **Task** → objective + done criteria + verification steps
- **Bug** → steps to reproduce, expected vs actual, acceptance criteria for fix

Tailor for **MitipiApp** (React Native, iOS + Android, BLE/MQTT when relevant).

### Step 5 — Preview (required)

Show the user before creating:

```markdown
## Jira issue preview

**Project:** MA
**Type:** Story
**Summary:** Add preset preview sound on card tap

**Description:**
[full markdown body]

**Create this issue?** Reply yes to confirm, or tell me what to change.
```

Do **not** call `createJiraIssue` until the user confirms (unless they explicitly said "create without preview").

### Step 6 — Create via MCP

```text
createJiraIssue(
  cloudId="<from step 2>",
  projectKey="MA",
  issueTypeName="Story",        // or Task / Bug
  summary="<title>",
  description="<markdown body>",
  assignee_account_id="<optional>",
  parent="<optional epic key>",
  additional_fields={}          // only if required by project
)
```

On success, fetch the issue key from the response (e.g. `MA-742`).

### Step 7 — Post-create output

```markdown
## Created: MA-742

**URL:** https://mitipi.atlassian.net/browse/MA-742

**Suggested branch:** `feat/MA-742-preset-preview-sound`
**Suggested commit:** `feat(MA-742): add preset preview sound on card tap`

Next: checkout branch and implement, or ask me to draft a PR when done.
```

## MCP tools reference

| Step            | Tool                               |
| --------------- | ---------------------------------- |
| Site ID         | `getAccessibleAtlassianResources`  |
| Issue types     | `getJiraProjectIssueTypesMetadata` |
| Required fields | `getJiraIssueTypeMetaWithFields`   |
| Create          | `createJiraIssue`                  |
| Current user    | `atlassianUserInfo`                |
| Assign someone  | `lookupJiraAccountId`              |

Requires **`write:jira-work`** permission (OAuth or API token with write scope).

## Rules

- Always use project **`MA`** unless the user specifies another project key.
- Always show **preview** before create unless user opts out.
- Do not create duplicate tickets — if the description matches an open issue, search first with `searchJiraIssuesUsingJql` (e.g. `project = MA AND text ~ "preset preview" AND status != Done`).
- Description in **Markdown** (Atlassian MCP accepts markdown).
- Include **iOS and Android** in acceptance criteria when the work touches the mobile app.

## Examples

See [examples.md](examples.md).

## Related skills

- Jira read/update: `.claude/skills/jira/`
- Branch naming: `.claude/skills/gitflow/`
- Commits: `.claude/skills/conventional-commits/`
