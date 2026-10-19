# Britsmaid audit and handover — 19 October 2026

## Source and scope

Started from the clean PC checkout at `C:/Users/HP/Projects/Britsmaid/App`, fetched `feature/roles-cleaning-guest-verification` and verified `8e57274879de0c91b4cc7db645729dccf21f42dd`. The older main branch was not used. Changes are on `fix/camera-training-android-preview`, reviewed separately in [draft PR #2](https://github.com/Ashik-AI-DataScientist/Britsmaid-App/pull/2), targeting the existing feature branch. PR #1 and main were not merged or overwritten.

The existing Expo/React Native design and FastAPI/MongoDB application were extended. No real customer, enquiry, ID, calendar provider or production database was used. The research-based plan preceded implementation: [test plan and official sources](CAMERA_TRAINING_TEST_PLAN.md). [Screen/API inventory](SCREEN_API_INVENTORY.md) enumerates 26 route/layout sources and all decorated API routes; inventory is not a claim of end-to-end execution of every screen.

## Defects and verification

| What happened | Why | What changed | Evidence |
|---|---|---|---|
| Web Take photo opened library | Camera branch explicitly excluded web | User-gesture camera launch on web; separate library; native camera retained; browser capture hint and fallback explained | Installed SDK inspected; browser Take photo produced a single-file capture chooser; synthetic file attached to original Before room |
| Repeated taps could overlap pickers | Busy state began after selection | Synchronous shared picker lock before permissions/picker; explicit web cancellation reset ignores late picker results | Capture-controller regression tests |
| Attachment retries could follow a different room/route | Attachment callback used current mutable selection | Draft snapshots task, room, name, phase and revision; server validates destination, ownership and current task access | Wrong room/phase/revision and reassignment/lock tests |
| Upload success could be lost before attachment | Pending upload result existed only in component memory | Per-account draft metadata, Android result recovery, app-private native file copies, resume card, explicit discard, success only after attach | Serialization and upload-then-attach retry tests; physical recovery still untested |
| A lost upload acknowledgement could cause another media record | Uploads always generated a new media identity | Stable per-asset retry key bound to uploader; deterministic media ID, content digest and storage path; existing result returned on retry | Two POSTs return one ID and one sequential storage write in isolated test |
| A photo could be reused across phases | Deduplication applied only inside one phase array | Atomic media destination binding plus legacy-link check; same-destination acknowledgement retry does not bump revision | Cross-phase/concurrent mock tests and idempotent attachment tests |
| Cancelled work could still mark a property dirty | Readiness queried every non-completed status | Cancelled work excluded from readiness/dashboard; deletion cancels ongoing work and preserves its room evidence | Cancellation/readiness and deletion regression tests |
| OTA date/cancellation changes left outdated work | Import directly changed booking dates, ignoring status and task reconciliation | Imports use validated booking create/update path, reservation claims and cleaning reconciliation; explicit STATUS:CANCELLED supported; per-feed UID namespace; India timezone conversion | Mock feed create/repeat/date-change/cancel/timezone test; existing failure/recovery notice test |
| Changing a working task's property/date could leave old evidence under a different stay | Booking amendment reconciled only pending sessions | Reject property/checkout changes when work is in progress/reviewed/completed until admin reopens with a reason | Server guard inspected; existing booking/reopen tests |
| Property inputs allowed blank/duplicate room names and negative rates | Missing model constraints | Distinct nonempty trimmed room names, bounded property name and nonnegative finite base rate | Property validation and history-preservation tests |
| Reports/invoices accepted broken references or invalid recipient/date combinations | Some server validations were missing | Validate report media existence, invoice booking/property binding, nonblank recipient and due date order | Report reference, invoice validation/calculation/status tests |
| Some edit screens spun forever or opened blank after load failure | Unhandled/reduced GET failures | Persistent retry cards for property/booking/invoice/report/team loads; stale response guards; invoice prefill applied once | Type/lint/build checks and source review; actual outage interaction on each form not executed |
| Notes could not be saved before task submission | The screen sent notes only with final completion | Explicit Save notes action awaits the server; failed writes keep the text and show an error | Positive notes-save/incomplete-submit regression test; browser check recorded after rebuild |
| Late responses could cross a login change | Asynchronous file preparation and response handling used mutable global authentication | Capture-bound auth epochs stop a delayed upload before POST; stale responses/private blobs are rejected and cannot sign out the new account | Four request-level account-switch regressions |
| Previous user information could remain in request cache during role switching | Logout cleared without first cancelling active reads | Cancel reads and clear user cache before a subsequent login; drafts are scoped by account | Four-role browser sign-out/login smoke checks; cross-role API tests |
| Native release compile failed while exports had passed | Custom Metro config required an undeclared transitive cache module | Use Expo defaults; directly load Metro config in regression command | Initial native compiler log; corrected config-load/web/Android checks; APK result recorded below |

The compatibility pass preserves image/video report library selection and multiple-file batches. Batch revisions advance only after each acknowledged attachment; partial retries keep the successful items. A recovered cleaner draft can also be explicitly discarded from the task list if its original task is no longer accessible.

New training features and their operational instructions are in [Cleaner training](CLEANER_TRAINING.md). This includes publishable versions, immutable assignment snapshots, admin assignment/all-active assignment, onboarding, due dates, inactive-account filtering, idempotent completion, refresher scheduling and historical records. A scheduler issue is visible in the existing admin issue panel. Lessons do not block cleaning access.

## Automated results

- **175 isolated backend tests passed**, including the earlier 133 and 42 added/expanded cases. Latest local run uses Python 3.12, FastAPI HTTPX ASGI transport, MongoMock Motor and synthetic image/storage fixtures; pytest-xdist runs two workers. No external service is contacted. Known dependency warnings concern FastAPI on_event and multipart deprecation; they are not test failures.
- **30 frontend tests passed**: 13 request/error/auth cases, 13 capture queue/lock/recovery/media-mode cases, four preview network/config cases. These execute in Node with a mocked request environment or pure capture controller; they are not real camera tests. Metro configuration also loads successfully from the pinned dependencies.
- TypeScript and ESLint pass with zero errors/warnings on the final source. Frozen pnpm install is retained. Web and Android JavaScript exports and Android native prebuild are checked separately from native compilation.
- GitHub quality checks run the same isolated backend, type/lint/frontend tests and both JS exports. Current links/status are recorded with the APK result below; a local pass is not substituted for CI.
- During implementation an xdist collection error from a random parametrization ID and an unused test lint declaration were fixed and rerun. Failed intermediate native/CI runs remain visible in GitHub; they are not passing APKs.

Reproduce backend checks with:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_role_security_local.py backend/tests/test_edge_audit_local.py backend/tests/test_camera_training_local.py -q
```

Do not run the legacy broad live-service suites: `backend/tests/conftest.py` defaults those fixtures to a shared Emergent preview. Only the named isolated suites were used here.

Frontend:

```powershell
Set-Location frontend
pnpm install --frozen-lockfile --ignore-scripts
pnpm typecheck
pnpm lint:check
pnpm test:edges
pnpm exec expo export --platform web --output-dir dist
pnpm exec expo export --platform android --output-dir dist-android
```

## Completed practical checklist

P = passed in the specified environment; U = untested; B = blocked by missing external environment/device. No U/B item is a pass.

| Category | Cases and outcome | Environment |
|---|---|---|
| Role permissions | P: unauthenticated, cross-property owner/supervisor, other cleaner, finance/IDs restricted, malformed IDs, deactivated account, password-reset session invalidation | Isolated server tests |
| Role usability | P: admin → logout → cleaner → logout → owner → logout → supervisor; correct scoped landing screens and no stale admin dashboard | In-app browser, local synthetic backend |
| Guest | P: invitation expiry/revocation/replacement, consent/slot/name/expiry validation, pending/rejected/resubmit, manual review, admin view-before-approve, check-in/undo/override and audit; no ordinary media access to IDs | Isolated server tests, mocked private storage |
| Guest screen | P: invitation entry and invalid/expired invitation error with retry | Browser |
| Guest cloud identity | B: real S3 IAM/KMS/versioning/retention deletion and actual provider identity verification; automated provider is not configured | Needs staging credentials/provider |
| Guest relationships | Absent: accompanying-guest/minor relationship model. Individual numbered slots exist; no claim that these extra relationships are implemented | Source inspection |
| Capture navigation | P: assigned task → room → Before → Add photo → capture chooser → synthetic upload → original-room thumbnail; room/phase shown in sheet; incomplete submit disabled | Browser synthetic file; not physical camera |
| Capture platform | P: SDK/native config and controller checks. U: physical Android camera/no-camera, permission denial/permanent denial, settings, browser device-specific capture UI | Needs phone |
| Cancellation / rapid taps | P: empty cancellation draft never attaches; synchronous lock/repeated queue save. U: cancellation quirks on every supported mobile browser | Node tests / phone pending |
| Recovery | P: serialized destination/media recovery, original account binding, attach retry without new upload; app-copy/recovery hooks inspected. U: actual activity destruction/rotation/phone restart | Node tests / phone pending |
| Networks | P: offline/timeout/HTML/error responses and upload/attach failure paths; no write retry storm. U: physical Wi-Fi interruption, long background upload and server restart during upload | Mocked request/controller tests |
| Files | P: JPEG/PNG decoding/metadata stripping, corrupt/mislabelled/unsupported/oversized multipart, video container header, upload ownership, repeated key | Synthetic backend tests |
| Stale task edits | P: wrong cleaner, reassignment, locked/review/completed/cancelled task, stale revisions, wrong room and phase; concurrent mock attachment binding | Mock Mongo tests |
| Properties | P: create/edit validation, room rename preserving existing task evidence, property access. U: every large-data/property-deletion combination | Backend tests/source |
| Bookings | P: invalid dates/counts/amounts, back-to-back dates, overlap, simultaneous mock claims, cancellation/reactivation/reconciliation | Mock Mongo tests; real multi-worker/crash test B |
| Cleaning | P: assignment eligibility, checklist/photos required, review/return/approve, reasoned admin reopen/reassign and retained evidence | Backend tests; supervisor return-with-feedback browser test |
| Finance/reports | P: role scope, calculations, month clipping, payout dates, media links and report deletion invalidating its capability link, invoice status/reference/amounts | Backend tests; owner browser summary |
| Report-link lifecycle | Existing links remain valid until report deletion. Expiry/individual rotation/revocation is absent; treat links as sensitive | Source + deletion test |
| Calendar | P: mocked duplicate/changed/explicit-cancelled event, UID scope, India boundary, sync outage/recovery notice | Real parser + mocked HTTP provider |
| Calendar missing events | U/limited: disappearance alone is not treated as cancellation because feeds may be partial. Full authoritative-feed deletion reconciliation and upstream race/crash recovery need staging design | Not a live provider test |
| Training admin | P: create/edit/publish/archive, revisions and immutable historical snapshots, all-active/manual assignment, duplicate request | Backend tests; publish/assign browser flow |
| Training cleaner | P: own assignments only, completion timestamp unchanged on duplicate, inactive-account denial, no cleaning gate | Backend tests; completion/history browser flow |
| Training schedule | P: onboarding/new account, recurring duplicate runs, multiple completion records, inactive filtering and UTC deadlines | Mock Mongo tests; real Mongo unique-index/concurrency B |
| Responsive presentation | P: browser training/owner screens at 360×800 and 412×915, owner DOM no horizontal overflow, existing fonts/icons visible, wrapping photo/training labels | Desktop browser viewport only |
| Accessibility/device UX | U: physical keyboard, font scaling, screen reader, touch target comfort, landscape/OS rotation and all long-text screens | Needs phone; portrait configuration retained |
| Form errors | P: request error-contract tests and persistent card source/type/lint checks; U: simulated outage on each individual form through browser | Limited interaction coverage |
| Build | P: pinned dependency install, type/lint/tests, web/Android exports, native prebuild with exact package and host-only HTTP XML; native APK status below | Windows + GitHub Linux |
| Production operations | B: persistent DB/storage, backups/restore/rollback, live outbound integrations, uptime alerts when backend is offline | No production deployment authorized |

## Remaining practical limits

This is a phone-test preview, not a production-readiness certification. The test backend deliberately resets data and passwords on restart and cannot safely store real guest IDs. Real MongoDB transaction/crash recovery, orphan reservation reconciliation and actual S3 permissions/encryption/deletion need a persistent staging environment. General video validation checks container headers, not every frame or malware. An uploaded but discarded/unattached file may remain until storage lifecycle cleanup; configure that before production.

Browser capture is a supported file-input hint and can open a chooser instead of a camera. HTTPS is required for a live getUserMedia stream but does not change this code path into a live camera stream. Native Android pending-result recovery is attempted, but app data clearing/uninstall, OS loss before a result, a full disk, unavailable files and every phone restart cannot be promised recoverable. Uploaded media IDs can survive a retry; browser blob selections may not survive page reload. Keep the browser page open until saved.

No quiz engine or mandatory training gates were added. No automated Indian ID authenticity provider is enabled; **manual admin review** remains the implemented process. Report public links lack expiry/individual rotation; ordinary booking editing/deletion is not a complete immutable financial audit ledger. These limits must be considered before handling real operational/financial/identity data.

The in-app issue panel records sanitized server failures/recovery. It cannot alert if the PC/backend itself is offline, and no email/SMS/push alert destination was configured.

## APK, local PC and exact version

APK build/installation status and final commit evidence are appended after the native workflow finishes. See [Android preview instructions](ANDROID_PREVIEW.md) for private-PC start, random test accounts, permissions, source identification, installation/signing limits and the physical-device checklist.


### Verified current build evidence

- Signed standalone ARM64 APK **success**: https://github.com/Ashik-AI-DataScientist/Britsmaid-App/actions/runs/39286736988
- Exact APK source/configuration commit: **3d0f913704ccb71fa6a6c841a2b04cb2cf3e3550**. Subsequent commits update local launcher compatibility and handover evidence; mobile feature code is unchanged.
- Quality checks: https://github.com/Ashik-AI-DataScientist/Britsmaid-App/actions/runs/39286746555 (175 backend tests, 30 frontend tests, type/lint, web and Android exports). Individual backend/frontend check steps passed.
- APK SHA-256 independently matched the workflow checksum: `3b494b45b9d0e9e04d3b6bfd3d8659ff1c64400370dbf4c21343221c17a37dab`.
- Embedded `assets/app.config` and Hermes bundle independently inspected: package `com.emergent.britsmaidrevshare.ixdi3x`, source `3d0f913704ccb71fa6a6c841a2b04cb2cf3e3550`, backend **http://192.168.1.11:8766**, testOnly true. APK is 49,240,647 bytes; compressed artifact is about 30 MB.
- PC file: `C:/Users/HP/Projects/Britsmaid/App/.local-preview/android/Britsmaid-preview-arm64.apk`.
- Phone download while PC preview runs: **http://192.168.1.11:8766/preview.apk**. The route's HTTP status, MIME type, size and ZIP signature were checked through the PC's private interface; this does not prove a physical phone's firewall/network path.
- The first successful APK was built for a different Wi-Fi address (192.168.29.55). The PC changed networks before handover, so a new APK was compiled for 192.168.1.11. The old file is retained separately as `Britsmaid-preview-previous-network.apk`; it is not served by the active download route.
- GitHub artifact expires 22 October 2026; the downloaded PC copy is retained. No Play Store submission, production signing key, main merge, production DB or cloud deployment was made.
- APK installation/launch, physical camera/permissions and device-specific usability remain **untested** until the user installs it. Native compile success is not a physical camera test.

### Updated PC verification

The original checkout `C:/Users/HP/Projects/Britsmaid/App` is switched to the new working branch. Its broken dependency links from the earlier folder relocation were preserved under ignored `.local-preview/dependencies-before-relink` and replaced with a fresh pinned install. Expo resolution and direct Metro config loading now work there. Main remains `3e72b8dd6ab6c96f1a66b239b58f69c32774827b`; the original feature branch remains `8e57274879de0c91b4cc7db645729dccf21f42dd`.

One restarted private preview serves **8765 and 8766 from the same app/database**, so old PC bookmarks and the native app share test data. All four role logins and scoped workspaces were checked through real local HTTP, non-admin guest-ID access was denied, and a synthetic disk-backed upload retry produced one media ID and attached only to the chosen room. Incomplete completion was denied. Private-interface health returned successfully. These are still in-memory demo tests, not real MongoDB or a physical phone.

The new Start Android Test Preview launcher recognises the running server. The existing Start Britsmaid launcher now reuses it instead of stopping it and replacing the APK backend; its existing-preview self-test passed. Current test passwords are in `.local-preview/private-test-accounts.txt`, excluded from GitHub. They reset on restart. Keep this backend running when testing phone interruption recovery: restarting this demo also replaces task/user IDs, so a photo draft pointing to the previous demo database cannot restore that old task.
