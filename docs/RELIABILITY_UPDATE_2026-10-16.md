# Reliability and role-flow update — 16 October 2026

Implemented locally after approval of the edge audit. This supersedes the earlier audit's failure status for the tested cases; that report remains as a historical baseline.

## Changes

- Cleaner: one room at a time, missing-evidence guidance, and awaited photo upload/attachment with a persistent retry state. Successful file transfer is no longer announced as a successfully attached cleaning photo until the attachment request succeeds.
- Supervisor/admin: Review, Unassigned, To do and Done queues. Cleaner-list failures have retry cards. Sending work back requires feedback.
- Owner: expected earnings, paid and balance due are labelled separately; visible refresh/last-updated controls; failed Payouts/Stays/Updates requests no longer pretend to be empty lists.
- Admin: Service notices with sanitized incident references, open/recovered states and a dashboard indicator. Notices include request/storage failures, calendar-sync failures and background ID cleanup failures. No external messages or external notification account were configured. The panel cannot alert when the entire PC/backend is unreachable.
- Shared requests: timeouts, clear connection/server/invalid-response errors, one bounded read retry, no automatic write retries and persistent dismissible error messages.
- Security: password resets/password changes invalidate old JWTs and stored Google sessions. General photo uploads validate/re-encode JPEG/PNG; MP4/MOV types require their container signature. Existing unsafe active content cannot be served inline. This is format validation, not malware scanning.
- Data integrity: shared date/month validation, nonnegative finite money fields, valid invoice/property references and payout dates, per-night atomic claims for new manual bookings, booking/cleaning cancellation/reactivation reconciliation, expired-ID replacement and deduplication of an unchanged repeated admin cleaning action.
- Statements: occupied nights are clipped to the month. Revenue remains allocated to arrival month, preserving the existing accounting rule.
- Structure: shared validation, reservation-claim and incident-tracking modules; a minimal pinned runtime dependency list; pnpm lockfile; read-only lint/type checks and isolated backend/frontend tests in GitHub Actions. The older broad dependency list remains available for compatibility.
- Production startup no longer silently re-enables/resets existing bootstrap accounts, and sample property seeding now requires explicit SEED_DEMO_DATA=true. The local preview still deliberately seeds fictional data.

## Validation

133 isolated backend tests and 9 frontend request tests passed (142 total). TypeScript and ESLint passed with zero errors/warnings. The pnpm frozen lockfile was verified offline. The Expo web preview build is refreshed separately. The source tests mock MongoDB/object storage; the live demo uses an in-memory database and dummy files.

A storage-deletion test now asserts a recoverable 503 response plus preservation of the original record, rather than expecting an uncaught server exception. This reflects the new error contract and does not weaken its data-preservation assertion.

## Local testing

Open Start Britsmaid, or refresh the already-running preview. Use admin@example.com, owner@example.com, cleaner@example.com or supervisor@example.com with Preview@2026. A second cleaner is relief@example.com. Keep the PC awake; phone and PC need the same Wi-Fi. Network changes restart the demo and reset its sample records.

Open Admin > Notices to see actual recorded incidents and request recovery. This is not an external uptime monitor or a guarantee that every subsystem is healthy. Opening a notice does not erase its history.

## Release limits

The app remains a local testing demo, not a production deployment. Real MongoDB concurrency/crash recovery and reservation-claim reconciliation, live S3/KMS/IAM, backups, production restore/rollback, physical phones/cameras, accessibility and visual end-to-end checks still require staging validation. In particular, reservation claims protect normal simultaneous creation but are not a substitute for a full transactional booking integration across all external calendar feeds. Stale claims after an interrupted database operation require reconciliation before production use.

General video validation checks the MP4/MOV container signature; it does not decode all video frames. Production media processing/scanning and storage lifecycle policy remain deployment work. Guest document storage in this demo is not encrypted; use fictional IDs only.

GitHub Actions is configured in the feature branch. A local pass does not prove a clean remote CI run; branch protection and merge/deployment remain separate actions. No main-branch merge or production deployment is part of this update.
