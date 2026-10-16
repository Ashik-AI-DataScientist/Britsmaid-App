# Britsmaid edge-case and usability audit

Date: 16 October 2026 (India)

## Decision

**Not ready for real guest IDs, financial records or production deployment.** Role access tests are encouraging, but new tests reproduced security, booking, financial-validation and error-recovery defects. The original 62 regression tests still pass; passing those alone did not cover these additional failures.

This is an assessment and approval checkpoint. Only test files and audit artifacts were added/edited during this audit. Application workflows, the preview database, GitHub branches and deployment settings were not changed. No external notifications were sent.

## Executed checks and evidence

| Check | Result |
|---|---|
| Backend regression and edge cases | 129 cases: 101 passed, 28 failed |
| Frontend API failure handling | 9 cases: 5 passed, 4 failed |
| Total executed behavioral cases | **138: 106 passed, 32 failed** |
| TypeScript no-emit check | Passed |
| Read-only ESLint check | 22 errors, 4 warnings |
| GitHub read-only check | Draft PR #1 remains open; remote feature head a8208e4; no check runs at that head; workflows directory not found at that ref |

Failures are test cases, not a count of distinct bugs: several are variants of the same validation defect. They have deliberately not been hidden or marked as expected successes.

Evidence: `test_reports/edge-audit/backend.xml`, `frontend-api.json`, `lint.json`, `summary.json`.

Reproduction tests: `backend/tests/test_edge_audit_local.py`, `frontend/tests/edge-audit.cjs`, plus the existing `backend/tests/test_role_security_local.py`.

Backend tests use an isolated in-memory MongoDB adapter and mocked object storage. They do not call production, create bills/payments in the running preview, or upload actual IDs. Frontend tests execute the actual API module against controlled fake responses. Older test files default to a hosted Emergent endpoint and contain mutating tests; they were deliberately not run against that service.

## Reproduced defects

| ID | Priority | Trigger and actual result | Needed correction |
|---|---|---|---|
| A01 | High | A token issued before a password reset still gets HTTP 200 from `/auth/me` after the reset. | Revoke all old sessions using a session version/revocation cutoff; test both JWT and Google session paths. |
| A02 | High | General `/upload` accepts HTML labelled as a cleaning image. `stream_media` serves the stored content type on the API origin. | Validate actual image/video bytes, disallow active formats, constrain decoded size and add safe download/security headers. Same-origin HTML is a potential script-execution risk; no malicious script was executed in this audit. Private guest ID intake has separate image validation which passed its existing tests. |
| A03 | High | Two simultaneous booking requests pass the overlap check and both return 200 for the same property/dates. | Make reservation conflict handling atomic. The test deliberately synchronizes both reads before insertion. Verify the remedy on real MongoDB as well. |
| A04 | High | Expense requests accept negative amounts, invalid months and nonexistent property references. | Validate financial values, month syntax and active property existence on the server. |
| A05 | High | Invoices accept negative quantity/rate/tax/discount, invalid issue dates and invalid property IDs. Payouts accept impossible payment dates. | Validate references, dates and finite nonnegative amounts; show field-specific errors. Credit notes, if wanted, should be a separate explicit workflow. |
| A06 | High | A stay from 31 January to 2 February is counted as two occupied nights in January rather than one. | Clip occupancy to the requested month. Agree separately whether revenue/payout allocation follows arrival month or nightly accrual; do not silently change the accounting rule. |
| A07 | Medium | Changing a cancelled booking to confirmed does not create its cleaning task. | Reconcile cleaning when booking status/property/dates change, not just on initial creation. |
| A08 | Medium | Cancelling a booking leaves its linked pending cleaning in the cleaner's To do list. | Reconcile/cancel the associated task, preserving work already performed in history. |
| A09 | Medium | An ID past retention disappears from guest status, but still holds the active unique slot; uploading a replacement returns 409. | Retire/purge the expired slot before replacement while preserving the required audit record. |
| A10 | Medium | Invalid calendar/statement months return unhandled 500 responses instead of helpful validation errors. Eight variants failed. | Centralize date/month validation with clear 4xx JSON errors. |
| A11 | Medium | A simulated private storage outage returns plain-text 500 rather than a recoverable structured service error. | Translate storage failures, preserve context safely, give a support/error reference and retry guidance. |
| A12 | Medium | A repeated admin reopen request adds two history events and executes the reset twice. | Protect repeat taps/retries with request IDs and optimistic revisions. This is a repeat-action resilience requirement, not evidence of a financial duplicate charge. |
| A13 | Medium | Offline fetch errors show only technical text; HTML gateway errors are passed through; a 200 HTML response becomes `null`; requests have no timeout signal. Four frontend tests failed. | Normalize network/server/invalid-response errors, add bounded timeouts and show persistent recovery cards. |

## What passed

- Unauthenticated users cannot read protected records.
- Owners, cleaners and supervisors cannot create admin records through tested endpoints, including by bypassing the screen.
- Owners are restricted to their assigned property, including dashboard and financial statement access. An owner with no property sees an empty successful response.
- Supervisors see only eligible cleaners and cleaning tasks within their property scope.
- Changing a task's assignee immediately removes the previous cleaner's server access.
- Ordinary cleaning completion requires evidence and checklist completion; approval/rework permissions and stale-write checks pass their existing tests.
- Guest invitations expire, revoke and replace correctly in existing tests. Duplicate slots, rejected-ID reupload, bounded request sizes, invalid images, consent and guest counts are covered.
- Admin-only overrides require a nonblank note. Reassignment preserves historical evidence and starts a fresh round. Undo and role restrictions pass.
- Attempting to undo an old rejected ID after a newer active submission gives a conflict rather than replacing the newer ID.
- Tested frontend authorization failures trigger sign-out, while a wrong login password does not invoke global sign-out.

## Role journeys: source-based usability review

These observations are based on the actual screens and handlers, not an observed usability study with cleaners or owners.

### Cleaner

Recommended flow: **Today's tasks → Open task → Before photo → After photo → Check the room → Send for review.**

Currently the cleaner has to understand room-by-room before/after evidence and five checklist chips per room. A disabled submission button does not list every missing requirement, so a user can be stuck without knowing which checklist/photo is missing. Pending and awaiting-review sessions share To do; an overdue badge can hide the more useful Needs review state.

A photo upload can announce success and close the capture sheet before the asynchronous attachment to its cleaning room succeeds. If a later file in a batch fails, earlier uploads are not attached by that callback. This is a source-confirmed risk, not a camera/device test. Use one awaited save pipeline, progress per photo, keep unsuccessful items visible and preserve draft notes/photos for retry.

Proposed changes: task cards with property, date and one large Start/Continue button; a short guided room flow; a clear missing-items list; persistent Saved/Not saved status; a Need help action. Keep admin-only exceptions separate.

### Supervisor

Recommended flow: **Needs review → Inspect photos → Approve or Send back → Assign if needed.**

Currently review tasks and ordinary work are mixed. Assignment, photo evidence and review controls share a long detail screen. Team-loading errors have no dedicated error card in that assignment section, which can look like no eligible cleaners. Review notes are needed for rework but the button itself does not guide the user to the missing note before submission.

Proposed changes: a default Needs review queue, distinct Unassigned and In progress views, clear staff-loading/retry states, and a short rework form with a visible reason field and assignee.

### Owner

Recommended flow: **My properties → Payment summary / Stays / Property updates.**

The current owner home is separated from admin operations, which is helpful. However, it shows many financial measures at once and calls calculated earnings Your payout, which can be confused with money already paid. The villa Payouts, Stays and Updates sections do not consistently render query error states. Failed requests can therefore display No payouts / No stays / No reports / No cleanings instead of a retry card. The Earnings section has a retry card already.

Proposed changes: emphasize Expected earnings, Paid and Balance due separately; keep detailed breakdowns behind View details; show a visible Refresh button and Last updated time; distinguish genuine empty lists from failed requests. Owners should have read-only access to their property data and no guest-ID controls.

### Admin

The simplified stay list is an improvement over many invitation buttons on every card. Keep the common actions visible and place exceptions/history under Admin options. Notes must accompany overrides; permanent document deletion is not an undoable action. Do not expand Undo into unaudited erasure of financial or security history.

## Error cards, alerts and recovery

**Not complete today.** A shared ErrorState/Retry component and a render-crash reload screen exist, but they do not cover all queries, uploads or mutations. Toasts disappear after 3.2 seconds and are easy to miss. There is no configured automatic administrator failure/recovery notification system. Existing backend sync, storage-initialization and retention failures log locally; logging is not an alert.

Proposed behavior after approval:

1. Keep the user's entered work visible and display a persistent, plain-language card: what failed, whether anything was saved, and the next action.
2. Give Retry / Return home / Contact admin actions appropriate to the failure. Do not blindly retry non-idempotent writes.
3. Return consistent API error codes and a request/incident reference; sanitize logs so ID images, invitation tokens, authorization headers and personal details are excluded.
4. Add independent uptime/readiness monitoring and backend/frontend error reporting. Alert the designated admin on confirmed outages, failed retention cleanup and repeated upload/sync failures; send a recovery notice when service is healthy again. Deduplicate alerts.
5. Configure recipient/channel only after approval. No notification destination or external service was created during testing.
6. Prepare a recovery runbook: identify incident, verify DB/storage, restart/rollback if appropriate, verify data integrity and confirm recovery. A notification alone cannot bring a dead PC or backend online.

## Code structure and GitHub workflow

- Backend: most routes, models, settlement logic, storage helpers and startup work are in a roughly 1,465-line `server.py`. Guest IDs are already separated. Split future work into auth/users, properties/bookings, cleaning, finance and guest-ID routers with service functions and shared validation/error types. Use explicit settings and an intentional demo-vs-production startup policy; current startup seeds sample data when properties are empty and re-applies configured accounts.
- Frontend: reusable UI, auth, API and query-client modules are a useful base. Many data models still use `any`. Move repeated queries/mutations into typed hooks, centralize error presentation and validate response shapes. Use one awaited upload-and-attach workflow.
- Lint: 22 errors and 4 warnings remain after excluding issues introduced by the audit harness itself. Three errors are in application screens (booking initialization and guest invitation effect ordering/state); 19 errors concern a vendored command-guard file. Configure an appropriate vendor exclusion rather than blindly rewriting third-party code. TypeScript passing is not equivalent to lint/runtime correctness.
- Version control: local branch is `feature/roles-cleaning-guest-verification` but local HEAD is still base commit `3e72b8d` with staged, unstaged and untracked changes. The remote draft PR head is `a8208e4`; recent simplification/preview/override work has not been committed into that remote head. Do not assume the current preview can be restored from GitHub alone.
- No `.github/workflows` directory was found on the reviewed feature ref and there are zero check runs for its head. Branch-protection settings were not verified; do not infer protection from an open PR.
- Recommended next workflow: preserve the current working tree, carefully reconcile it with the remote feature branch, commit focused changes, add isolated CI tests/type/lint/build checks, review a PR, then merge. Protect main and tag deployments. Use one declared package manager/lockfile; `package.json` declares Yarn while the installed local preview dependencies use pnpm.
- Keep demo state, ID uploads, logs, secrets and build output out of Git. Separate generated reports from source/test code. Legacy remote-targeting tests need an explicit opt-in guard before they can be part of CI.

## Limits and remaining verification

No finite test pass covers every possible edge case. This audit covers the 138 named behavioral cases and source review above. Full screen rendering/interaction, small-screen layout, screen readers, physical Android/iPhone cameras, denied permissions on devices, real offline reconnection, Wi-Fi transitions and QR/link sharing were not exercised in this audit. Browser automation had previously been blocked by its URL policy; this report does not claim fresh browser verification.

Production MongoDB concurrency/index behavior, live S3/KMS/IAM policies, retention lifecycle, recovery from backups, deployment rollback, performance/load, provider ID authentication and real email/push delivery still require a separate staging environment. The local demo intentionally has in-memory records and unencrypted dummy files and cannot stand in for those checks.

## Proposed approval batches

1. **Reliability/security first:** A01-A13, structured errors, persistent retry states, safe upload/attach, financial/month validation, booking/cleaning reconciliation and concurrency protection. Preserve existing approved role boundaries and admin-note requirements.
2. **Simple role journeys:** cleaner guided room steps, supervisor review queue, owner payment clarity and consistent empty/error states. Validate with a small number of actual intended users.
3. **Professional release workflow:** reconcile/push current source, CI/PR checks, typed module boundaries, independent monitoring and recovery runbook, then staging/device/security verification.

Awaiting approval before changing the app or configuring external notifications/deployment.
