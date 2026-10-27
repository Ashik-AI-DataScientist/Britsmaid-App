# Britsmaid: free-service production preparation

Work branch: `production/free-services`, based on deployed `0c979a7`.

## User decisions and deferred work

- Use free allowances for additional services; do not upgrade Render or Atlas automatically.
- Domain: `britsmaid.in`; proposed app address: `app.britsmaid.in`.
- DNS is managed at Hostinger. **The user explicitly deferred DNS changes on 27 October 2026 because access is unavailable.** Resume this when access is available; do not change nameservers, the main website or email records. Keep the existing Render address working meanwhile.
- Replace the earlier proposed 90-day cleaning-photo policy with a count-based policy: preserve the two newest complete before/after sets for each property. The third complete upload makes the oldest completed set eligible. Keep cleaning records and all business information.
- Cloudflare R2 was activated by the user after reviewing its $0 starting cost and usage-based overage terms. A free allowance is not a provider-enforced spending cap.

## Cloud resources prepared

R2 Standard buckets, all checked with Public Access **Disabled**:

| Bucket | Purpose |
| --- | --- |
| `britsmaid-media` | Private ordinary photos/videos |
| `britsmaid-backups` | Encrypted database and photo recovery files |
| `britsmaid-staging-media` | Isolated synthetic staging files |

Live-media and backup credentials are separate Object Read & Write tokens, scoped to their individual buckets. The user creates and stores these credentials privately in Render. Do not put keys in source, GitHub issues, logs or this document. Staging must use a separately scoped credential, separate JWT secret and a database user restricted to `britsmaid_staging`; do not share the production token with staging.

## Implemented application changes

- Configurable R2 ordinary-media adapter. New uploads can use private object storage while existing GridFS references remain readable. Guest ID storage stays separate and unavailable until its dedicated private S3/KMS prerequisites are met.
- Idempotent uploads, checksums on cloud reads, atomic shared quota counters, per-object leases and conservative monthly operation limits. Storage failures do not silently fall back to another store.
- Copy/verify migration job, in batches of three files. It preserves each media ID, checks the copied bytes, switches its pointer conditionally and retains the legacy object for rollback. Physical retirement of old database copies requires a verified recovery copy and explicit review.
- Shared business-write leases coordinate API edits with cleanup and database exports. Background calendar reconciliation uses the same guard for its database write phase, without holding it while waiting for provider downloads. This does not constitute a measured unlimited-scale guarantee.
- Browser login uses Secure, HttpOnly, SameSite=Strict cookies. Unsafe cookie-authenticated requests require a matching Origin. Browser-readable legacy tokens are cleared; users must sign in again once. Native clients retain bearer tokens in platform secure storage. Hosted Google sign-in remains disabled.
- Optional administrator authenticator enrollment, verified activation and one-use hashed recovery codes. MFA secrets are encrypted and excluded from API user responses. Enabling MFA invalidates other sessions, while refreshing the enrolling admin's session. Each admin must enroll and privately save recovery codes; do not enable it on their behalf.
- Twelve-character minimum for newly created/reset passwords, UTF-8 byte validation for bcrypt, stronger generated reset passwords and session invalidation on account deactivation.
- Login throttles persist in MongoDB across restarts and instances. They currently use 20 attempts per IP per minute; shared networks and proxy configuration still need monitoring.
- Admin **Notices → Security, storage & backups** shows backup status, cleanup eligibility and MFA setup. Cleaning admin controls can place or release evidence holds with a note. Expired images display a retention message while cleaning history remains intact.

## Cleaning retention safeguards

Only before/after evidence bound to a cleaning task is eligible. At least three complete sets must exist for the same property, with usable newer evidence. Incomplete newer uploads do not displace old evidence. Active/reopened tasks, dispute holds, property covers, shared owner-report files and evidence referenced by other tasks are protected. Legacy records with unknown upload order are not guessed.

Cleanup is **disabled by default**. An admin reviews the eligible count and enables it with a note. Automatic checks occur hourly while the service is running. Manual cleanup has a separate explicit confirmation. Missing verified backup objects prevent deletion; interrupted deletion keeps metadata for retry. A shared lease prevents simultaneous reference edits. Each successful deletion records an audit entry. Cleaning dates, checklists, reviews, invoices, bookings, balances and other records are not deleted.

The two-set rule applies to live cleaning photos. An encrypted recovery copy can remain for seven further days, then expires through the backup cleanup job. This short recovery window is separate from ordinary app access; it is not indefinite retention. Active photos on hold are not expired. Other file categories do not inherit this cleaning rule.

## Backup design and limits

The backend exports BSON-compatible JSON lines in gzip form, then encrypts them with a chunked authenticated format. Each file derives a separate key; blocks authenticate their order, and a final authenticated block detects truncation. The backup encryption secret is separate from object-storage credentials and must be saved privately outside Render. Losing it makes recovery impossible.

Exports omit ephemeral sessions, quota ledgers and raw GridFS collections. Business writes are briefly serialized during database export. Ordinary media is backed up separately by immutable media ID. Cloud read-back, decryption and checksum checks must succeed before a run is labelled verified. A successful checksum/decryption check is not by itself a full disaster-recovery drill.

The backend schedules daily backups at approximately **02:00 IST**, catches up after an overdue run, and supports an admin queue action. It keeps seven verified database snapshots. Stored expired cleaning-media recovery copies are removed after seven days. Failed jobs appear in the in-app issue panel. Free Render can sleep: a reliable fixed-time schedule additionally needs an external wake/health job or always-on hosting. A failed-backup/outage alert outside the app requires a notification destination and an external monitor; do not describe these as active until configured and tested.

Before handover: restore the encrypted export and representative photos into an isolated database/bucket, verify counts, relationships, invoices and images, and document who owns recovery. Never run a trial restore over the live database.

## Conservative free-allowance safeguards

- Live media: 3 GiB app budget by default.
- Backup bucket: 4 GiB app budget.
- Proposed staging media budget: 512 MiB, set explicitly in its own environment.
- These budgets leave headroom within R2's 10 GB-month Standard allowance, but other account activity, temporary objects, console operations and provider billing can still consume allowance.
- Live adapter: 20,000 write and 1,000,000 read operations per calendar month, with SDK automatic retries disabled. Backup store separately bounds operations. These deliberately undershoot provider allowances and can stop uploads/reads before a provider limit is reached.
- Capacity accounting is conservative after a crash; an uncertain upload can overcount allocated space rather than grant extra space. Review/reconcile before changing limits. Do not simply remove guards.
- `FREE_TIER_GUARD=true` clamps live-media capacity. Later paid expansion requires an explicit budget review and configuration change; adding replicas also needs actual capacity, failover and job testing.
- No Redis, paid identity provider, paid monitoring service or new paid Render compute is required by this code change. R2 is still a usage-billed service; app safeguards are not a contractual zero-cost guarantee.

## Environment configuration

Existing `MONGO_URL`, `DB_NAME`, passwords, `JWT_SECRET` and `SEED_DEMO_DATA=false` remain unchanged.

```text
MEDIA_PROVIDER=r2
MEDIA_BUCKET=britsmaid-media
MEDIA_ENDPOINT=https://<cloudflare-account-id>.r2.cloudflarestorage.com
MEDIA_ACCESS_KEY_ID=<private media token access key>
MEDIA_SECRET_ACCESS_KEY=<private media token secret>
MEDIA_BUDGET_BYTES=3221225472
FREE_TIER_GUARD=true
BACKUP_BUCKET=britsmaid-backups
BACKUP_ACCESS_KEY_ID=<private backup token access key>
BACKUP_SECRET_ACCESS_KEY=<private backup token secret>
BACKUP_ENCRYPTION_KEY=<unique generated secret of at least 32 characters>
PUBLIC_APP_URL=https://britsmaid-test.onrender.com
```

Do not change `PUBLIC_APP_URL` to `https://app.britsmaid.in` before DNS/HTTPS is verified. Changing the canonical origin affects cookie-based POST requests. Deploy frontend and backend together. Keep the old URL usable while transferring installation and OTA links. Staging must use its own `APP_ENV=staging`, `DB_NAME=britsmaid_staging`, URL, bucket and credentials; the hosted validator refuses a staging environment pointed at an obviously non-staging database name.

## Verification status and rollout

Local regression suites use synthetic data, fake object storage and mocked MongoDB. The forty-account concurrent read test checks role isolation; it is not a benchmark of Render's 512 MB hardware. Physical phone testing, actual provider integration, restored cloud backups, monitoring delivery and staging isolation must be verified before claiming the full rollout complete.

Recommended order: finish private credentials → run local checks and browser review → publish a reviewable branch/PR → create isolated staging → verify R2 upload/read, backup and restore → deploy together → verify all four roles → copy and verify legacy media → review the cleanup preview → enable the approved policy. Keep live business records intact throughout. Do not delete legacy files merely because a copy request returned success.

Sources: [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [Render free limits](https://render.com/docs/free), [Render custom domains](https://render.com/docs/custom-domains), [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule). Provider allowances and account requirements must be rechecked before activation.


## Local staging and external monitoring preparation

`compose.staging.yml` provides a local Docker staging app and an isolated MongoDB volume. The database has no host port, the app binds only to 127.0.0.1:8783, and its MongoDB URL is fixed to the internal staging service. A local `.env.staging.local` with generated passwords is ignored by Git and Docker's build context. Docker is not installed on the current PC, so the container staging configuration has not been run here. It is not a production credential file. Start with `docker compose -f compose.staging.yml up --build`; stop with `docker compose -f compose.staging.yml down` (without deleting the data volume). GitHub Actions run 40447347467 subsequently built this Docker image, started the isolated Compose stack and passed its four-role staging smoke test. It remains untested with Docker on this PC.

The hourly `.github/workflows/service-health.yml` checks app/database health and the age of the last verified backup. Its :35 UTC schedule includes 02:05 IST, helping wake the free backend near backup time. It is disabled until repository variable `ENABLE_FREE_MONITOR=true` is set and `BRITSMAID_APP_ORIGIN` is configured. **Scheduled workflows only run from the repository's default branch.** Deploying this feature branch alone does not activate the monitor. Review remaining free Actions minutes and set billing/spending controls before enabling it. Confirm GitHub Actions failure notifications reach the responsible administrator; until then external alerts are not active. GitHub schedules and free hosting do not provide an exact-time or availability guarantee.

Latest local verification before final container checks: 296 backend cases passed, including a forty-account concurrent role-isolation check and recovery of a synthetic invoice into an empty `_restore` database. Wrong keys and existing/live database targets are rejected. Frontend type checking, lint and production web export passed; API edge cases, capture recovery, native config, installation and cleaning-state tests passed. Browser smoke testing verified HttpOnly-cookie login and a synthetic cleanup preview reducing from two eligible files to zero. Live storage and restore checks remain separate from these synthetic tests.

## Confirmed rollout on 27 October 2026

- GitHub Actions run 40447347467: backend, frontend and hosted-container jobs all succeeded for c9f46ce. The container smoke test used an isolated synthetic database and verified four roles and a real image upload/download.
- The deployment branch was advanced without force-pushing to c9f46ce67c9088a7dfd1e3dfdba7707364d5e750. Render deploy dep-dbg26p4ipgvc73e9i5t0 succeeded on the existing Free service.
- The public /healthz returned status ok and that exact source commit. /healthz/backup returned status ok after startup, meaning a database-and-media backup run passed encrypted read-back verification. This is not a full cloud disaster-recovery restore drill.
- The user entered both separate R2 credential sets and the backup encryption key directly into Render, retaining the encryption key privately. No credentials are included here.
- The final browser cleanup regression, explicitly approved by the user, removed only two generated synthetic local photos and reduced eligibility to zero. Local cleanup was switched off afterward. Live cleanup has not been enabled and no live cleaning photos have been removed.
- Browser token hardening intentionally requires one new sign-in. Authenticated live upload, migration preview and admin-panel checks await that sign-in. Legacy media remains available through its existing storage references; migration has not been queued.
- Hostinger DNS remains deferred. External monitoring remains unactivated. Administrators must enroll their own authenticator. Actual isolated cloud restore and physical-phone checks remain handover requirements.