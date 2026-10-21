# Britsmaid free hosted test

Deploy branch `deploy/render-free`, from the audited app at `3a837e0`.
This adds a Docker web export plus persistent FastAPI/MongoDB; it does not run
`scripts/local_preview.py`, wipe data, submit to stores or alter the PC preview.

## Accounts and configuration

Use the existing Render free account and the `Britsmaid-Free` Atlas FREE cluster
in Mumbai. A blueprint is provided in `render.yaml`; choose FREE compute,
Singapore, Docker, one worker, health `/healthz`, automatic deployment off.
The service's HTTPS origin serves both SPA and `/api`, so the browser needs no
separate backend URL or CORS allowance. TLS is provided by Render.

Set secret `MONGO_URL` to an Atlas SRV URI whose user has readWrite access only
to database `britsmaid_test`. Allow only Render's selected outbound IP ranges in
Atlas, not `0.0.0.0/0`. The owner must create the database credential and enter
it privately in Render. Never paste the URI/password in public GitHub or chat.

The blueprint generates a stable JWT secret and distinct initial passwords for
`admin@example.com`, `owner@example.com`, `cleaner@example.com` and
`supervisor@example.com`. Read them privately from Render's environment settings.
They are created only if absent; restarting or redeploying does not reset them.
Changing an existing account's environment password does not reset its database
password: use Team's password controls. Add real named users through Team; do
not share the admin login. Initial nonadmin accounts have no property assignment;
admin must create properties and assign the appropriate scope through Team.

## Persistent photos

Ordinary room/report images and videos use MongoDB GridFS in the same protected
Atlas database. They survive Render sleeping/redeploying and retain existing
authenticated file/task/property guards. They consume part of Atlas's 512 MB
database allowance. A conservative 128 MiB chunk allocation budget prevents
photos consuming the entire free database; this is not unlimited storage. The
single worker serializes writes; scaling requires revisiting that coordination.
Interrupted orphan chunks count against budget. Old/discarded uploads are not
automatically garbage collected; inspect storage before expanding or deleting.

Private guest identity uploads retain the separate S3/KMS requirement and fail
closed until configured. They are NEVER redirected into ordinary GridFS. Real
government IDs must not be uploaded to this free setup until the intended private
document service, permissions, retention and deletion are verified.

## Operation and limits

- Render Free sleeps after inactivity; first app requests can time out during
  the roughly one-minute wakeup. Wait and retry; check a timed-out write before
  submitting another. No artificial keepalive is configured.
- Background training/calendar/retention jobs pause while asleep and resume on
  startup. This is not reliable continuous production scheduling.
- Google sign-in is disabled for this host; email/password supports all four
  roles. Same-origin CORS, security headers and an in-memory sign-in throttle
  apply. Access logs are disabled so media token query strings are not logged.
- No demo data or publicly known password is seeded. No guest IDs or real records
  are committed. Real property/booking records entered by the owner remain in
  Atlas; verify backup/restore before depending on this as the sole copy.
- The free cluster currently has backups OFF unless the owner explicitly enables
  an available free backup option. Do not enable paid backup without approval.
- Store publication is unnecessary. Phone browser can use the HTTPS URL over
  mobile data. The old APK points to the PC: build a new APK with the hosted
  origin before claiming native PC-independent use.

## Validation

Run the three previous isolated test files plus `test_hosted_local.py`, then
frontend type/lint/controller checks and export. The new cases use MongoMock
GridFS/ASGI, not live Atlas. After deployment, verify all four role logins,
property assignments, actual photo round trip and persistence across restart,
cross-property/ID denial, guest-storage refusal and the HTTPS guest route.
No mocked result proves real database concurrency, backups or physical camera.

Local validation on 21 October 2026: 190 isolated backend tests passed (175
existing plus 15 hosted tests); 30 frontend regressions, TypeScript and lint
passed. Linux container build, live Atlas connection, restore and hosted-phone
smoke checks are separate checks and must not be assumed from those results.
