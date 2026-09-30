---
name: pull-request
description: Draft pull request descriptions for this Next.js/Stripe/Prisma web app with Conventional Commits alignment, a Stripe/Prisma/Auth0-aware checklist, test scenarios, and screenshot requirements. Auto-detects the change type (feat/fix/chore/…) from branch name and commits, generates a rich Summary + Impact overview, and omits the screenshots section for non-UI changes. Use when creating PRs, writing PR bodies, or reviewing changes to this repo.
---

# Pull Request

PR titles and bodies follow the same vocabulary as [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/). Use the template below unless the hosting tool supplies its own fields.

## PR title

Same format as commit subject:

```text
<type>(<scope>): <description>
```

Scope is the Jira ticket (`MA-828`) when one exists, otherwise the feature area. Examples: `feat(MA-828): choose-your-plan pricing page`, `fix(billing): handle out-of-order webhook events`.

## Auto-detecting the type of change

Don't ask the user - infer it. Check in this order, stop at the first match:

1. **Branch name** - `feat/MA-…`, `fix/…`, `hotfix/…`, `chore/…` map directly to `feat` / `fix` / `fix` / `chore`.
2. **Commits since the merge-base with the target branch** - `git log --pretty=%s <target>..HEAD`. If all commits share a single Conventional-Commits type, use it. If they're mixed, use the highest-impact type by this precedence: `feat` > `fix` > `perf` > `refactor` > `test` > `docs` > `chore` > `ci`.
3. **Diff shape** as a final tiebreaker:
   - Only `*.test.ts`, `tests/integration/`, or `e2e/*.spec.ts` → `test`
   - Only `*.md`, `docs/`, `.claude/` → `docs` or `chore`
   - Only `package.json`, `pnpm-lock.yaml`, `Dockerfile`, `docker-compose.yml`, `bitbucket-pipelines.yml` → `chore` or `ci`
   - `prisma/schema.prisma` + a new migration, with no accompanying `src/` behavior change → `chore` (schema catch-up); with behavior change → `feat` / `fix`
   - Public-API or user-visible changes (`src/app/`, `src/components/`, `src/server/`) → `feat` / `fix`

Detect **breaking changes** by scanning commit bodies for `BREAKING CHANGE:` footers or `!` in the subject (`feat!:`). If found, flag at the top of the PR body, regardless of type. A migration that is not backward-compatible until deploy (column drop, non-nullable add without a default) counts as breaking even without a `!`.

Render the inferred type as a single line, not a checklist:

```markdown
## Type of change

`feat` - new feature
```

## Summary structure

Open with **1–2 sentences** stating what changed and why, then a **bulleted list** with the specifics. Don't write paragraphs; reviewers scan.

Cover, as bullets:

- **What** changed - the user- or system-visible behavior.
- **Why** - the bug, Jira ticket, or constraint that prompted it.
- **How** - the approach, naming the central file or module (`src/domain/…`, `src/server/…`, `src/infra/stripe/…`).
- **Boundary** - what is intentionally _not_ in scope.

Draft from the commit subjects + bodies on the branch; synthesize, don't repeat the diff.

## Impact section

A short, bulleted list of consequences a reviewer / on-call should know. Use this section as your blast-radius statement. If a category doesn't apply, omit the bullet rather than writing "N/A".

- **Users:** new screens/copy, new errors, new empty/loading states, a11y changes.
- **Billing / Stripe:** new Products/Prices/coupons, webhook handling changes, `automatic_tax`/`currency_options`/idempotency changes. Remember: Stripe is the source of truth for billing, our DB is a projection.
- **Data / migrations:** `prisma/schema.prisma` changes, new migration files, anything needing `pnpm db:migrate`.
- **Auth / entitlements:** Auth0 role/permission changes, entitlement-resolver changes (the most expensive bug surface in the product).
- **i18n:** new or changed keys across `en`/`de`/`fr`/`it`.
- **Build / CI / Docker:** new dependency (needs `--renew-anon-volumes`), a new env var (needs `.env.example`), CSP header changes, `bitbucket-pipelines.yml` changes.
- **Rollback:** safe, or does it leave migrated DB state or a live Stripe object behind? (A live Stripe Price is never deleted or modified in place - only grandfathered via a new Price - so a pricing-only change is inherently one-directional.)

## PR body template

Copy and fill every section that applies. Sections marked _conditional_ should be **omitted entirely** when they don't apply - don't leave "N/A" placeholders behind.

Emoji on section headers is intentional - section anchors scan-jump in long PR bodies. Stay consistent with the headers below; don't sprinkle decorative emoji inside bullets.

**Punctuation:** use a hyphen `-` or colon `:` between a label and its description; do not use em-dashes (`—`) anywhere in the PR body.

```markdown
## 📝 Summary

<!-- 1–2 sentence intro, then bullets covering what / why / how / boundary -->
<!-- - What: …
- Why: …
- How: …
- Boundary: … -->

## 💥 Impact

- 👤 Users: …
- 💳 Billing / Stripe: …
- 💾 Data / migrations: …
- 🔐 Auth / entitlements: …
- 🌍 i18n: …
- 🛠️ Build / CI / Docker: …
- ↩️ Rollback: …

## 🏷️ Type of change

`<inferred-type>` - <short label>
<!-- Breaking change? Add: ⚠️ BREAKING - <describe> -->

## 🎫 Ticket / link

<!-- e.g. https://mitipi.atlassian.net/browse/MA-828 -->

## 🌿 Branch

<!-- Source branch and target, e.g. feat/MA-828-pricing-choose-your-plan → dev -->

<!-- conditional: include only if change is UI / visual / copy -->

## 📸 Screenshots

| Breakpoint | Before              | After |
| ---------- | ------------------- | ----- |
| Desktop    | <!-- screenshot --> |       |
| Mobile     | <!-- screenshot --> |       |

<!-- Add a locale row instead of / in addition to breakpoints if the change is copy-driven and a locale (de/fr/it) has notably different text length -->

## 🧪 Test scenarios

1. **Happy path:** …
2. **Regression:** …
3. **Edge case:** …

## ✅ Checklist

### 🌐 Web / Next.js

- [ ] `pnpm verify` passes (lint + typecheck + unit + integration) - needs postgres running
- [ ] `pnpm test:e2e` run if a user-facing flow changed (needs the app running + `AUTH0_SECRET`)
- [ ] Responsive checked at mobile/tablet/desktop breakpoints (if UI)
- [ ] Keyboard focus trap, `Esc`-to-close, and WCAG AA contrast verified (if modal/dialog)
- [ ] `prefers-reduced-motion` respected (if animation)
- [ ] All new copy added through `src/i18n/messages/{en,de,fr,it}.json` with ICU pluralization - no bare JSX text
- [ ] Currency/number/date formatting goes through `Intl.*` - no hand-built strings

<!-- conditional: include only if src/infra/stripe/, src/server/billing/, src/server/checkout/, or webhooks are touched -->

### 💳 Stripe / Billing

- [ ] API behavior (`automatic_tax`, `currency_options`, `pause_collection`, `trial_settings`, webhook payload shape) verified against official Stripe docs, with the doc link in a code comment - not recalled from memory
- [ ] No amount or `plan_id` trusted from the client; price resolved server-side from `stripe_price_id`
- [ ] Webhook handler keeps `runtime = 'nodejs'`, raw-body signature verification, `stripe_events` idempotency, and out-of-order protection
- [ ] `Idempotency-Key` present on every mutating Stripe request this change adds
- [ ] No live Stripe Price deleted or modified in place - grandfathered via a new Price if pricing changed
- [ ] `pnpm stripe:bootstrap` / `pnpm reconcile:stripe` re-run locally if Products/Prices/coupons changed

<!-- conditional: include only if roles, permissions, or src/domain/entitlements are touched -->

### 🔐 Auth / entitlements

- [ ] Role checks happen server-side (`requirePermission()` in `/api/admin/*` and the `/admin` layout) - not just a hidden button
- [ ] Entitlement resolver unit-tested for the new source/status combination
- [ ] Every admin action carries a reason and writes to `audit_log`

<!-- conditional: include only if prisma/schema.prisma or a migration changed -->

### 🗄️ Database / Prisma

- [ ] Migration created via `pnpm db:migrate:dev` - never `db push`, never `migrate reset`
- [ ] No amounts or prices stored in our DB - only `stripe_price_id`, plan ordering, and marketing copy
- [ ] Concurrency case tested if this touches a race (redemptions, referral qualifications, JIT provisioning)

<!-- conditional: include only if a dependency, env var, or Docker/CI config changed -->

### 🐳 Docker / env / CI

- [ ] `.env.example` updated if a new env var was added
- [ ] `docker compose up -d --build --force-recreate --renew-anon-volumes web cron` run after adding a dependency
- [ ] `TECHNICAL.md` updated to match what actually shipped
- [ ] A non-obvious decision recorded as an ADR in `docs/decisions.md`

## ⚠️ Risk & rollout notes

<!-- Optional: feature flags, migrations, manual steps, rollback -->

## 🔗 Related commits

<!-- Optional: list key commits if squash-merge is disabled -->
```

## When to include the Screenshots section

**Include** when the change affects:

- Layout, spacing, typography, colors, icons, Tailwind tokens
- Pricing page, plan cards, checkout, modals, the admin dashboard
- Animations, loading states, empty states, error states
- Locale-specific copy where text length materially changes layout (German in particular)

**Omit the section entirely** for:

- Pure `src/domain/` or `src/server/` logic changes with no rendering impact
- Webhook / cron / reconciliation-only changes
- Test-only or doc-only changes
- Dependency / lockfile / CI-config bumps without UI consequence
- Tooling, CLAUDE rules, skill content

## Review tips

- Call out if reviewers need a **Docker rebuild** (`--build --force-recreate --renew-anon-volumes`) vs a plain `pnpm dev` hot reload.
- Mention that e2e mints its own Auth0 session cookie (ADR-052) - reviewers don't need a real Auth0 tenant to click through authenticated flows locally.
- Flag **webhook, schema, or migration** touches prominently in Summary - these need `pnpm db:migrate` before the app boots.
- Split large PRs by layer (`domain` / `infra` / `server` / `app`) when review would exceed ~400 lines of meaningful change.

## Examples

See [examples.md](examples.md) for filled PR bodies.

## Related skills

- Commit message format: `.claude/skills/conventional-commits/`
- Jira workflow: `.claude/skills/jira/`
