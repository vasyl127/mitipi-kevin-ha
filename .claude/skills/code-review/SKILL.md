---
name: code-review
description: Review code written by someone else — an incoming branch, a Bitbucket pull request, a contractor's delivery, or a whole repository being taken over. Treats the repo's own rules and documents as claims to verify rather than as ground truth, and requires file/line evidence for every finding. Use when reviewing work you did not write, auditing an unfamiliar codebase, or preparing review comments for another engineer.
argument-hint: '<branch, PR URL, commit range, or nothing to review the current branch>'
---

# External code review

For reviewing someone else's work. The sibling skill `.claude/skills/code-review/` is the
project's own checklist of invariants — read it, use its domain knowledge, but do not treat it as
the definition of correct. This skill exists because the person who wrote the code usually also
wrote the rules it is measured against, and because an agent reviewing at scale fails in two
specific ways: it invents findings that sound plausible, and it repeats the codebase's own
description of itself back as if it were an observation.

## The two rules that matter

**Every finding names a file and a line you actually opened.** Not a pattern you expect to be
there, not a summary from a search hit, not another agent's report. If a subagent or a grep
suggests a problem, open the file and confirm it before it reaches the output. Findings that
survive this step are worth more than ten that do not.

**The repository's documents are claims under review, not the specification.** `CLAUDE.md`,
`README.md`, `AGENTS.md`, ADRs and skill files describe what someone intended at the time they
wrote it. Check each load-bearing claim against the code, and report the drift as a finding of its
own. In this repository, at the time of writing, `CLAUDE.md` claimed stage T1 while `TECHNICAL.md`
claimed T9, and `CLAUDE.md` forbade a `/checkout` page that ADR-064 had deliberately introduced —
a reviewer trusting it would have filed a violation that was not one.

## Workflow

### 1. Establish the scope, precisely

```bash
git log --oneline -20
git branch -a
git log --format='%an <%ae>' | sort | uniq -c | sort -rn   # who wrote this
git diff --stat main...<branch>
git diff main...<branch>
```

For a branch that is not checked out, read files at that ref rather than switching branches:
`git show <ref>:<path>`. Paths containing `[locale]` need quoting.

This repository is on **Bitbucket**, so `gh` does not work and the GitHub PR-review tooling does
not apply. Pull request context comes from the branch itself, from `Merged in …` commit subjects,
or from the Jira ticket in the branch name (`.claude/skills/jira/`). Review output is a document
or chat unless the user asks for something else.

### 2. Read the project's own rules — then verify them

Read `CLAUDE.md`, `.claude/skills/code-review/SKILL.md`, `TECHNICAL.md` and recent ADRs. Extract
the load-bearing claims: which layers may import what, which invariants are stated absolutely,
which limits are declared. Then check a sample of each against the code. A rule that the codebase
does not follow is either a stale rule or a real violation, and which one it is changes the
finding entirely — so determine it rather than assuming.

### 3. Gather evidence in parallel, then verify it yourself

Structure, security, and tests/CI are independent questions; investigate them concurrently. Ask
for file paths, line numbers and counts, not for opinions. Then re-open the load-bearing hits
yourself. In the review this skill was written from, a reported enumeration oracle dissolved on
reading: the endpoint only revealed the caller's own account state, which the caller already knew.
That check is the difference between a review someone trusts and one they stop reading.

### 4. Verify vendor behaviour against documentation

Any finding that turns on how Stripe, Auth0, Prisma or next-intl behaves gets checked against the
vendor's published documentation, and the finding carries the link. Never assert vendor behaviour
from memory — it is the single most common way an agent review is confidently wrong, and it is the
kind of wrong that costs the reader an afternoon.

### 5. Run what you can

```bash
pnpm lint && pnpm typecheck && pnpm test    # unit needs no database
pnpm test:integration                       # needs postgres running
```

A finding backed by a failing command is worth more than any amount of reading. If nothing can be
run, say so in the report rather than implying the code was exercised.

## What to look for beyond the project's checklist

The sibling skill covers this project's invariants — money in minor units, webhook idempotency,
entitlement purity, rate limits, PII. These are the patterns that checklist does not name and that
external reviews repeatedly find:

- **A safety decision inherited by an endpoint it was not reasoned for.** A shared helper's
  trade-off — fail open on error, cache aggressively, swallow an exception — is usually argued for
  one class of caller in a comment, and then a later feature puts a different class behind it.
  Read the comment justifying the behaviour and ask whether every current caller fits it.
- **Test-only or internal APIs on a production path.** Imports from a `/testing` subpath, deep
  imports past a package's `exports` map, or behaviour documented by quoting `node_modules`. Often
  well-argued and genuinely the only option, and still worth a pinned version, a round-trip test,
  and an upgrade note.
- **New code that skips the bar the project set for itself.** A new route handler, domain helper
  or migration arriving without the test the project's own rules require. Check what the diff adds
  against what it tests, not against what it changes.
- **Claims in comments and ADRs that the code no longer supports.** Comments age worse than code
  and are trusted more.
- **Limits declared but not enforced.** File-length, function-length or coverage limits written
  down with no linter or CI step behind them, and a list of files already over. Either enforce or
  amend — both are fine, and having neither is what actually costs time.
- **Validation or normalisation duplicated across layers.** Especially where the same project has
  already centralised the equivalent logic elsewhere; that asymmetry is the tell.
- **Uniqueness assumptions the schema does not make.** Code treating an email, a code or an
  external id as unique when no unique index says so.

## Bugs, and decisions that are not bugs

Some findings are a product or ops decision wearing a bug's clothes — an unverified email that
still gets a session, two identities for one human, an offline-capable feature that fails closed.
Do not file those as defects and do not silently pick a side. State the behaviour, state what it
costs, name who has to decide, and ask for an ADR. Reviews lose credibility faster by asserting a
product decision than by missing a bug.

## Calibration

- Raise a finding only at roughly **80% confidence or better**. Below that, either dig until you
  are above it or leave it out. A short list that is entirely correct is more useful than a long
  one that has to be argued down.
- **Consolidate repetition.** One finding with a count and two examples, never eight near-identical
  entries.
- **Do not review unchanged code** in a branch review unless the issue is severe and security
  relevant.
- **Do not fill severity buckets.** If nothing is critical, nothing is critical.
- **Say what is good, specifically.** Not as politeness — an external reviewer who names the
  strong parts is demonstrably reading, and the author knows which parts to protect during a
  refactor. Name the file or the test.

## Severity

| Level      | Meaning                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------ |
| **High**   | Security, money, auth, or data-integrity impact; or a stated invariant broken in practice  |
| **Medium** | Real defect, missing test on a risky path, or a decision that must be made before shipping |
| **Low**    | Drift, duplication, limits exceeded, hardening gap with small blast radius                 |

Skip style and preference entirely unless the user asked for an exhaustive pass.

## Output

A markdown document — a findings table first, then one section per finding, then what is good,
then a suggested order of work. Each finding section carries:

1. The file and line range, as a code reference.
2. What the code does, quoted if short.
3. Why it matters, in terms of consequence rather than rule violation.
4. What would fix it, including the option of amending the rule instead of the code.
5. A documentation link for any vendor-behaviour claim.

State the review's own limits in the header: what was read, what was executed, what was not
verified. A reader needs to know whether a finding was observed or inferred.

Close with a verdict — merge, do not merge, merge after specific items — and say which findings
gate it.

## Related

- `.claude/skills/code-review/` — this project's invariants and lenses; the domain half of the job
- `.claude/skills/jira/` — ticket context for a `MA-*` branch
- `.claude/skills/conventional-commits/` — commit and title conventions
- `.claude/skills/pull-request/` — PR description conventions
