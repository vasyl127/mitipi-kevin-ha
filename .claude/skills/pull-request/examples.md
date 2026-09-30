# PR Examples

Each example shows the auto-detected type, the 1–2 sentence Summary + bullets, the Impact block, and conditional sections (Screenshots and the Stripe/Prisma/Auth checklists are included only when relevant).

---

## UI feature - pricing page

**Title:** `feat(MA-828): choose-your-plan pricing page`

**Summary:** Rebuilds the pricing page on the nordic prototype's design tokens with quarterly/yearly billing and a plan-card feature ladder, replacing the placeholder grid.

- What: new `PlanGrid` / `PlanCard` / `CompareMatrix` components, a currency provider, and the hardware bundle as three Stripe Prices.
- Why: MA-828 - ship the "choose your plan" experience described in `main_prompt.md` §7.1.
- How: `src/domain/pricing/catalog.ts` resolves prices from Stripe; components stay presentational and take a `PricingPrice` DTO.
- Boundary: not in scope - the checkout page itself (MA-829), promo-code UI.

**Impact:**

- Users: new pricing layout, quarterly/yearly toggle, currency switcher in the header.
- Billing / Stripe: three new one-off Prices for the hardware bundle via `pnpm stripe:bootstrap`.
- i18n: new `pricing.*` and `site.nav.*` keys added to all four locale files.
- Build / CI: no new env vars or dependencies.

**Type:** `feat` - new feature

**Ticket:** https://mitipi.atlassian.net/browse/MA-828

**Screenshots:**

| Breakpoint | Before                            | After                                       |
| ---------- | --------------------------------- | ------------------------------------------- |
| Desktop    | placeholder 3-column grid         | nordic-styled plan grid with feature ladder |
| Mobile     | stacked cards, no interval toggle | stacked cards with sticky interval toggle   |

**Test scenarios:**

1. Load `/en` → plan grid renders with both billing intervals selectable.
2. Switch Yearly ↔ Quarterly → prices and the "Yearly -30%" badge update together, `aria-pressed` reflects the active toggle.
3. Load with `STRIPE_SECRET_KEY` unset → pricing renders its honest unavailable state, never a `CHF 0.00` card.

### 🌐 Web / Next.js

- [x] `pnpm verify` passes
- [x] `pnpm test:e2e` (`purchase.spec.ts`) run
- [x] Responsive checked at mobile/tablet/desktop
- [x] Copy added through `src/i18n/messages/{en,de,fr,it}.json`

---

## UI + billing feature - checkout page

**Title:** `feat(MA-829): replace the confirmation modal with a /checkout page`

**Summary:** Moves purchase from a confirmation modal into a dedicated `/checkout` page using Stripe Elements (Address Element + Payment Element), because Stripe Tax needs a saved customer address before a subscription can be created.

- What: `/checkout` page, `CheckoutForm`/`CheckoutSummary` components, `createSubscriptionForUser()` use-case.
- Why: MA-829 - the modal didn't allow enough room for a real payment form, and `automatic_tax` requires an address on file first (see ADR-064).
- How: Elements mounts without a client secret (`mode: 'subscription'`); submit saves the address to the Stripe Customer, then creates the Subscription and confirms against the returned client secret.
- Boundary: not in scope - promo-code entry on this page (backend still accepts `promotionCode`), a custom Payment Element replacement (explicitly disallowed - CLAUDE.md).

**Impact:**

- Users: new full-page checkout instead of a modal; card entry unchanged (still Stripe-hosted iframes, no PCI scope added).
- Billing / Stripe: `automatic_tax: { enabled: true }` on every new Subscription; customer address saved via `tax.validate_location: 'immediately'` before creation.
- Data / migrations: none - no new columns, Stripe remains the source of truth.
- Build / CI: no new dependency beyond `@stripe/react-stripe-js` (already present).
- Rollback: safe - reverting restores the modal; no subscriptions are left in a half-created state because creation only happens after address validation succeeds.

**Type:** `feat` - new feature

**Ticket:** https://mitipi.atlassian.net/browse/MA-829

**Screenshots:**

| Breakpoint | Before                               | After                                        |
| ---------- | ------------------------------------ | -------------------------------------------- |
| Desktop    | `ConfirmModal` over the pricing page | full `/checkout` page, summary + Stripe form |
| Mobile     | modal, cramped card fields           | stacked summary/form, same fields as desktop |

**Test scenarios:**

1. Click "Start free trial" on a plan card → lands on `/checkout?plan=…&interval=…` with the Payment Element visible.
2. Submit a valid CH address + test card → redirected to `/welcome?subscription_id=…`.
3. Submit an address Stripe Tax rejects → inline error, no subscription created.
4. App paywall handoff (`?plan=max&interval=quarter&src=app`) → still redirects straight to `/checkout`, no second plan picker.

### 💳 Stripe / Billing

- [x] `automatic_tax`/address-ordering behavior verified against `docs.stripe.com/tax/subscriptions` (see comment in `CheckoutForm.tsx`)
- [x] No amount or plan resolved from the client - server maps `planCode` + `interval` to `stripe_price_id`
- [x] Webhook handling unchanged - `customer.subscription.created/.updated` already covers direct-Subscription creation

---

## Bug fix - entitlements

**Title:** `fix(entitlements): stop downgrading a user mid-dunning`

**Summary:** A payment-failed webhook arriving after a slightly newer `active` event was overwriting the subscription back to `past_due`, incorrectly cutting off access; the resolver now checks event ordering before applying state.

- What: `stripe_events`-backed ordering check added before `entitlements` is recomputed.
- Why: two webhook retries arrived out of order during a flaky delivery window, and the older `past_due` event was applied last.
- How: `src/server/webhooks/project-subscription.ts` now compares `event.created` against the row's `last_applied` timestamp and drops older events (matching the existing out-of-order protection pattern for subscription-updated events).
- Boundary: no change to the entitlement resolver's business rules themselves.

**Impact:**

- Users: no more spurious access loss during transient webhook redelivery.
- Billing / Stripe: no API calls added; purely a local ordering guard.
- Data / migrations: none.
- Rollback: safe - reverts to the previous (buggy) behavior, no migrated state.

**Type:** `fix` - bug fix

**Test scenarios:**

1. Replay `subscription.updated` (active) then an older `payment_failed` event → entitlement stays `active`.
2. Normal in-order dunning sequence (`past_due` → `active` on recovery) → unaffected.
3. Concurrency test: two webhook deliveries racing for the same subscription → exactly one final state, matching the newer `event.created`.

<!-- Screenshots section omitted: no UI change -->

---

## Docs / ADR only

**Title:** `docs(MA-828): record the design and bundle ADRs, refresh the technical docs`

**Summary:** Records the ADRs behind the pricing-page rework (design-token source, hardware-bundle pricing model) and brings `TECHNICAL.md` in line with what shipped.

- What: two new entries in `docs/decisions.md`, updated module and API-surface tables in `TECHNICAL.md`.
- Why: CLAUDE.md requires an ADR for every non-obvious self-made decision, and `TECHNICAL.md` to stay current at the end of a stage.
- How: no code changes; documentation only.
- Boundary: not in scope - any implementation change.

**Impact:**

- Build / CI: none - docs and `.claude/` files only.

**Type:** `docs` - documentation only

<!-- Screenshots section omitted: no UI change -->

**Test scenarios:**

1. `pnpm verify` still passes (no code touched).
