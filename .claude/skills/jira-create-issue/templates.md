# Jira issue description templates

Use Markdown. Replace `{placeholders}` with content inferred from the short description.

---

## Story template

```markdown
## Context

{1–2 sentences: why this work exists, link to feature area if obvious}

## User story

As a **{persona}**, I want **{goal}**, so that **{benefit}**.

## Acceptance criteria

- [ ] {criterion 1 — observable, testable}
- [ ] {criterion 2}
- [ ] {criterion 3}
- [ ] Works on **iOS** (physical device or simulator — note which was tested)
- [ ] Works on **Android** (physical device or emulator — note which was tested)

## Test scenarios

1. **Happy path:** {steps}
2. **Regression:** {what must not break}
3. **Edge case:** {offline, permissions, empty state, etc. if relevant}

## Out of scope

- {explicitly excluded items, or "None" if clear}

## Technical notes

- {Redux/Saga, BLE, MQTT, serverless touchpoints — omit section if N/A}

## Definition of done

- [ ] Code merged to `staging`
- [ ] Unit tests added/updated where logic changed
- [ ] PR includes screenshots or screen recording (iOS + Android) if UI changed
```

---

## Task template

```markdown
## Objective

{What needs to be done and why — 1–3 sentences}

## Scope

- {bullet list of concrete deliverables}

## Done when

- [ ] {verifiable outcome 1}
- [ ] {verifiable outcome 2}
- [ ] `npm run lint` and `npm test` pass (if app code changed)
- [ ] {integration/serverless tests if backend changed}

## Verification

1. {How a reviewer confirms this is complete}

## Dependencies / risks

- {blockers, env changes, native rebuild, deploy notes — or "None"}

## Out of scope

- {or "None"}
```

---

## Bug template

```markdown
## Summary

{One-line description of the defect}

## Environment

- **App version:** {if known, else "latest staging"}
- **Platform:** iOS / Android / both
- **Device/OS:** {if reported}

## Steps to reproduce

1. {step}
2. {step}
3. {step}

## Expected behaviour

{what should happen}

## Actual behaviour

{what happens instead}

## Acceptance criteria (fix)

- [ ] Bug no longer reproducible on iOS
- [ ] Bug no longer reproducible on Android
- [ ] Regression test added if applicable
- [ ] No new crashes or layout regressions

## Notes

- {logs, screenshots, related MA tickets — or "None"}
```

---

## Summary title guidelines

| Good                                       | Bad          |
| ------------------------------------------ | ------------ |
| Add preset preview sound on card tap       | Preset sound |
| Fix onboarding redirect for existing users | Bug fix      |
| Bump ffmpeg-kit 16kb aar for Android       | Update deps  |

Use imperative mood, no period at end.
