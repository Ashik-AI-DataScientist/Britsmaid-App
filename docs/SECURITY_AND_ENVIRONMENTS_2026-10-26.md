# Britsmaid: local security hardening and environment plan

Prepared 26 October 2026 for Britsmaid Property Management Kerala Private Limited.

## Decision: separate testing from customer use

Maintain one codebase with separate local, staging and production environments. Do not experiment against real customer records. A Git branch separates code; it does not separate databases, uploaded files, passwords, calendar integrations or external effects.

The existing Render URL already holds real pilot data. Treat that service as a live pilot, preserve its records and address, and later upgrade it in place if this is the address staff should continue using. It does not become production-ready simply by changing its name or paying for compute. Add a separate staging service and database before routine cloud feature testing. Until then, use isolated local tests; do not reset the pilot to make it a test fixture.

This follows the environment separation described by [Google](https://firebase.google.com/docs/projects/dev-workflows/overview-environments) and [AWS](https://docs.aws.amazon.com/wellarchitected/2023-04-10/framework/sec_securely_operate_multi_accounts.html). [Render environments](https://render.com/docs/projects) can organise services, but names alone do not isolate secrets or data. These principles apply to this small app without needing Kubernetes or a large microservice architecture.

| Resource | Local / staging | Production |
| --- | --- | --- |
| Service and URL | Dedicated preview / staging URL | Existing pilot URL can be retained |
| Database | Synthetic records; own database user | Real records; own least-privilege user |
| Files | Synthetic photos; separate store | Private customer media; separate store |
| Secrets | Unique test JWT secret and passwords | Unique production secrets |
| Guest IDs | Artificial samples only | Approved private encrypted storage and retention |
| OTA / Zoho / messages | Disabled or sandbox; no real side effects | Explicitly configured live integrations |
| Releases | Feature branch → pull request → tests → staging | Same tested commit, manual approval and rollback plan |

Prefer separate Atlas projects/clusters when practical; at minimum use separate databases with users restricted to their own database. Never give a staging user read access to the live database. Never reuse production credentials in GitHub Actions or developer test fixtures. A second free Render service shares the workspace's 750 monthly free instance hours; it is not a second unlimited allowance. See [Render Free limits](https://render.com/docs/free).

## Implemented locally in this phase

No cloud setting, account, plan, live database or deployment was changed. Work is on `security/free-hardening`, based on live commit `87ce8cb`.

1. **Private media links:** the frontend no longer puts a reusable login token into photo/video URLs. An authenticated request obtains a five-minute ticket restricted to one media ID. Tickets cannot authenticate API requests or open another file. Every read rechecks the active account, password/session version and current property/task access. Header-authenticated file reads remain supported; old `?token=<login JWT>` file access is intentionally rejected. Private thumbnails and viewer images disable persistent disk caching through the image component.
2. **Server logout:** online sign-out records a hash of the access token as revoked, invalidating that token and its media tickets. Each new login has a unique token. Revocation records have a TTL index. Offline sign-out clears the local account/cache but cannot guarantee server revocation until communication succeeds; an unexpired stolen access token remains a risk in that case.
3. **Calendar fetching:** HTTPS only, no embedded credentials/custom ports/fragments, all DNS answers checked for public addresses, connection pinned to a validated IP while checking the original TLS hostname, and every redirect revalidated. Feed input and decompression are bounded to 2 MiB. Properties accept at most 32 feeds. Failures return safe messages without copying provider URLs or secret-bearing exception details. Existing HTTP-only feeds must be replaced with provider HTTPS export links. This follows [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
4. **Request limits:** ordinary API bodies are limited to 1 MiB; the ordinary upload endpoint allows the existing 100 MiB file allowance plus multipart overhead. Limits cover declared and chunked requests. Oversized requests return 413 with a clear message. Existing guest ID upload limits remain separate. The single-worker server admits one ordinary upload at a time before multipart parsing; additional uploads receive 429 and a retry instruction. Stalled uploads time out after 110 seconds and release the admission slot.
5. **Hosted browser protections:** content security policy restricts scripts to this app and exact hashes of the bundled installation controller, prevents framing/plugins, and limits network connections to the app origin. Inline styles remain permitted for React Native Web. HTTPS receives HSTS. All hosted API responses are no-store. Camera/microphone remain available to this app; geolocation is disabled. These headers also cover early hosted login errors. Existing stricter media sandbox headers remain intact.
6. **Regression coverage:** security tests added to the explicit GitHub quality workflow. Security pull requests also select the hosted-container build job. No GitHub workflow run or Docker build was claimed as completed locally.

## Local verification

- 259 isolated backend tests passed: the previous 227 tests plus 32 security cases. MongoDB, object storage and provider feeds are mocked. No real guest IDs or customer records were used.
- TypeScript checking and ESLint passed.
- Frontend edge suite passed: 15 API cases, 13 capture/upload cases, four native-config cases, installation-controller checks and cleaning-state checks.
- Production web export passed, including branded home-screen assets and installation metadata verification.
- Browser smoke checks passed with synthetic records: sign-in, dashboard/icons, private villa cover display, installation help and sign-out. The displayed private cover used a file ticket and contained no login-token query parameter. No security-policy console errors were observed on the working preview.
- The Windows preview needed extended-length paths because its generated font path exceeded 260 characters; the corrected test launcher is local-only. This was a local filesystem issue, not a production font change.
- Existing FastAPI lifecycle and multipart import deprecation warnings remain. They did not fail tests.

This is a regression/hardening phase, not proof that every possible vulnerability is absent. Physical Android/iPhone testing, live staging verification, a measured capacity test, dependency vulnerability scanning, independent penetration testing and a backup restore drill were not completed in this phase.

## Remaining work before calling this a production service

Some work is free engineering or account configuration, rather than a paid upgrade:

- Add admin MFA and enrollment/recovery. Enable MFA on GitHub, Render and Atlas accounts yourself; do not share recovery codes. App MFA is not implemented by this phase.
- Move web authentication from JavaScript-readable storage to a carefully tested HttpOnly-cookie/session design, with CSRF protection and native-client compatibility. CSP reduces exposure but does not eliminate the risk of a malicious script stealing a stored token. Access tokens currently last seven days.
- Replace per-process login throttling with a persistent/shared limit, with trusted-proxy handling. Existing hosted protection is 20 attempts per IP per minute, resets on restart and may combine users behind a shared IP. It is not comprehensive bot protection.
- Add secret/dependency scans and repository release protections, based on the GitHub plan's supported controls. Review old exposed image URLs/log retention; this update does not erase historical logs or automatically revoke every existing login. Coordinate any global session/secret rotation with staff.
- Keep a single application worker for now. The GridFS media quota lock, upload admission and background scheduling are process-local. Multiple workers/replicas require atomic shared quota/admission handling, distributed scheduler locks and idempotent jobs first.
- Add an external health alert destination. The existing in-app issue panel cannot notify someone while the whole app is unavailable. Configure a monitor independently from the app; an external monitoring account may be free.
- Define who can download guest documents, retention/deletion, audit review, incident response and restore ownership. Guest ID S3/KMS storage is not configured; it remains unavailable rather than falling back to ordinary photo storage. Production IDs require storage configuration and a separate privacy/security review.

## Paid upgrades / accounts to decide on

| Item | What is needed | When |
| --- | --- | --- |
| Always-on backend | Upgrade the existing Render service compute plan, not merely the workspace subscription. Current entry paid compute is listed at US$7/month; verify at checkout, with taxes/FX/usage extra. | Before relying on uninterrupted customer service and scheduled calendar polling |
| Database backups | Payment method and an approved backup/restore arrangement. Atlas documents optional M0 daily backups at US$0.10/day, capped at US$3/month, retaining four snapshots; this is a gradually rolled-out private preview and may be absent from this account. Otherwise choose an available paid tier or secure externally scheduled encrypted dumps. | Before depending on real operational records |
| Guest ID storage | AWS account, private S3 bucket, KMS key, least-privilege access and retention configuration. Storage, requests, KMS and transfer can be charged. | Before uploading real guest IDs |
| Media growth | Current ordinary-media quota is 128 MiB within the free database. Move ordinary photos/videos to private object storage, or expand storage after measurement. Keep ID documents separate. | Before quota is approached; do not simply remove the quota |
| Larger compute/database | Select from measured response times, memory, connections, storage and concurrent usage. Five users do not establish a tested maximum. | When load tests or monitoring justify it |
| Independent security review | Optional specialist account/service or security reviewer, using a defined scope and synthetic staging data. | Recommended before broader customer access and sensitive-document operations |

Sources: [Render pricing](https://render.com/pricing), [Render free-service limitations](https://render.com/docs/free), [Atlas M0 backup preview and pricing](https://www.mongodb.com/docs/atlas/backup/cloud-backup/free-cluster-backup/), [S3 pricing](https://aws.amazon.com/s3/pricing/). Prices checked 26 October 2026; no billing feature has been enabled. Existing Render and Atlas accounts can be retained; a new account is not required merely to pay for service capacity. An AWS account would be needed for the existing S3/KMS guest-ID design. MFA itself need not be a paid service.

## Review and release sequence

1. Review this local branch and the remaining risks. Agree on staging/data separation and backup ownership; do not reset or copy live identities into staging.
2. Create isolated staging resources/secrets only after approval. Run GitHub CI and a container build. Deploy the exact tested commit to staging. Test all four roles, phone camera/library uploads, video playback, private reports, availability/cleaning states and ID fail-closed behavior. Confirm CSP on the actual hosted origin.
3. Before a production release, obtain a recoverable backup and verify restoration into an isolated environment. Record the previous commit and database changes. This phase adds a revocation collection/index rather than altering existing business records.
4. Deploy frontend and backend together. Open tabs running an older bundle must reload because login-token media URLs are intentionally unsupported. Do not deploy only one half of the file-ticket change. Roll back both halves together if needed, then repeat role/media/calendar smoke checks.
5. Keep production deployments manually approved. Track failed requests, latency, memory, storage, login failures and sync health. Add capacity only after the single-worker constraints have been addressed.
