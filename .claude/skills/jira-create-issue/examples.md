# Jira create issue — examples

## Example 1: Story from short description

**Input:**

```text
/jira-create-issue user can preview preset sound by tapping the card in my simulations
```

**Inferred type:** Story (user-facing)

**Draft summary:** `Add preset preview sound on card tap`

**Draft description:** (Story template — user story, AC with iOS/Android, test scenarios)

**Preview shown → user confirms → created `MA-742`**

**Output:**

```text
URL: https://mitipi.atlassian.net/browse/MA-742
Branch: feat/MA-742-preset-preview-sound
Commit: feat(MA-742): add preset preview sound on card tap
```

---

## Example 2: Task from short description

**Input:**

```text
Create Jira task: upgrade react-native-svg patch for Android 16kb alignment
```

**Inferred type:** Task (technical / deps)

**Draft summary:** `Upgrade react-native-svg patch for Android 16kb alignment`

**Draft description:** (Task template — objective, done when includes `npm run android:check-16kb`)

---

## Example 3: Bug

**Input:**

```text
Jira bug: app crashes when returning from background during BLE onboarding on Android 14
```

**Inferred type:** Bug

**Draft summary:** `Fix crash returning from background during BLE onboarding on Android 14`

**Draft description:** (Bug template — repro steps, expected/actual, AC for both platforms)

---

## Example 4: Duplicate check

Before creating, search:

```text
searchJiraIssuesUsingJql(
  jql='project = MA AND summary ~ "preset preview" AND status != Done'
)
```

If `MA-700` already covers the work, tell the user and link instead of creating a duplicate.

---

## Example 5: With Epic parent

**Input:**

```text
Create story under MA-650: add language selector on sound onboarding step
```

**Additional field:** `parent: "MA-650"` (if project uses Epic link field, use `additional_fields` per `getJiraIssueTypeMetaWithFields`)
