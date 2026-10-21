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
passed. GitHub Actions run `39592363145` also passed backend/frontend checks,
web/Android exports and the Linux Docker image build.

## Live test deployment — 21 October 2026

Open https://britsmaid-test.onrender.com/ in a phone or PC browser. This host
runs independently of the PC, over Wi-Fi or mobile data. The original local
preview and its PC-address APK remain separate; that APK needs a new hosted
build before it can use this service.

### Branded home-screen web app

Share https://britsmaid-test.onrender.com/install.html for Android/iPhone
installation instructions, or use **Add to Home Screen** below the login form.
The approved existing Britsmaid logo is packaged as PNG icons, including a
180px Apple touch icon and Android 192px/512px/maskable icons. The manifest's
stable identity, scope and launch address are `/`; installed icons open the
normal role-aware app, not a sample account or the instruction page.

Chrome can show the native installation prompt when the browser offers it.
Otherwise use its menu. Safari uses Share > Add to Home Screen; enable Open
as Web App if offered. In-app WhatsApp/email browsers should open the link in
Chrome/Safari first. Existing old shortcuts may need to be removed and added
again to pick up the icon/name. Save pending work before clearing any app data.

This is online-only: no service worker or offline/private-data cache is added.
The free host can still sleep; store publication, push notifications and native
APK/iOS releases are separate work. A home-screen install does not grant access.
Installed web and normal browser sessions can require separate sign-in.

For web releases run `pnpm export:web` in `frontend`. Expo's `single` output
ignores `app/+html.tsx`, so `scripts/prepare-web-install.cjs` adds metadata to
the exported index. `scripts/verify-web-install.cjs` checks the actual manifest,
icon dimensions, Apple metadata and install page. CI and the Docker build run
these steps; a bare Expo export alone does not complete the branding pipeline.
The ordinary export bundles the official artwork; `scripts/build_web_icons.py`
reproduces the icon sizes without redrawing the logo. Physical Android/iPhone
installation and launch acceptance must be recorded separately from the
controller, source/export and desktop browser checks.

Render service `britsmaid-test` uses Free Docker compute in Singapore and
branch `deploy/render-free`. Verified application source is `460dde5`.
Atlas uses the Mumbai `Britsmaid-Free` FREE cluster and `britsmaid_test`.
The approved Atlas allowlist contains only `74.220.52.0/24` and
`74.220.60.0/24`, both shared Render Singapore outbound ranges. They are
not exclusive to this service; database authentication is still required.

Verified against the live service:

- `/healthz` reports `ok`, `persistent-test` and the expected source commit.
- All four initial roles sign in. Admin sees Team and the full dashboard;
  owner sees its property portal; cleaner sees tasks/training; supervisor
  sees cleaning review, unassigned, to-do and done tabs.
- Owner and cleaner navigation to `/staff` returns to their role portal.
  A request to `/api/auth/me` without authorization is rejected.
- A synthetic property and owner report can be written and loaded again.
- A public sample React icon can be uploaded, attached to the report and
  displayed. The report and image still load after a Render service restart;
  authenticated media responses use `private, no-store`.
- Existing sign-in survives the restart. No credentials were reset.

Two clearly labelled test records remain for inspection: property
`TEST — Deployment check` and report `TEST — Hosted image persistence`.
They contain no real guest/property data. No property access was assigned to
the initial nonadmin accounts. Use admin's Team screen to assign real properties.

Initial login emails and the privately saved Render environment password keys:

| Role | Email | Password key |
| --- | --- | --- |
| Admin | admin@example.com | ADMIN_PASSWORD |
| Owner | owner@example.com | OWNER_PASSWORD |
| Cleaner | cleaner@example.com | CLEANER_PASSWORD |
| Supervisor | supervisor@example.com | SUPERVISOR_PASSWORD |

Use the generated password as saved, without URI encoding. URI encoding is
only for special characters in the separate Atlas connection password.
No password or connection string belongs in this document or GitHub.

Physical phone/camera testing, live cross-property data scenarios, external
calendar/provider integrations, private guest ID storage, backup/restore and
native hosted APK/iOS testing remain separate checks. The verified browser
smoke checks do not establish production readiness or replace those checks.

## Villa photos and camera choices

An admin can open Villas → a villa → Edit property → Add/Change cover photo. Choose Take photo or Choose from library, then Save changes (or Add property for a new villa). A preview appears before saving. Remove cover photo clears the cover when the property is saved; it does not delete historical files. Existing URL covers still display, but entering a URL is no longer required.

Uploaded covers use the same persistent private ordinary-media store as cleaning photos. Only the media ID is saved with the property; login tokens are not saved in property fields. Admins can manage covers, and assigned users can read them; unrelated accounts cannot. Owner dashboards include the saved cover.

Cleaning and report attachment sheets already have Take photo and Choose from library. Villa covers now use this sheet with one image at a time. The guest ID form also provides a camera and gallery choice, with cancellation recovery and visible submission errors. Guest documents continue to use the private guest-document endpoint, never ordinary media storage; this free deployment still refuses guest ID uploads until its separate encrypted private storage is configured.

A web app requests the rear camera through the browser photo picker. Phone/browser permissions and support determine whether it opens the camera directly or offers a chooser. Verify this on physical Android and iPhone devices; a desktop file chooser is not proof of a working phone camera. JPEG/PNG photos are supported; unsupported or oversized images produce an error rather than being attached.
