# Camera, training and Android audit — 19 October 2026

## Source and boundaries

Clean PC checkout: C:/Users/HP/Projects/Britsmaid/App; fetched remote branch
feature/roles-cleaning-guest-verification at 8e57274879de0c91b4cc7db645729dccf21f42dd.
Isolated working branch: fix/camera-training-android-preview, based on that exact commit.
No production data, live shared-service tests, real documents, customer messages or store submission.

## Research before implementation

- [Expo ImagePicker](https://docs.expo.dev/versions/v57.0.0/sdk/imagepicker/): native camera and library are separate operations; web launch must occur directly in a user gesture. Android pending results need recovery after activity destruction. Permission requests are action-specific. Installed SDK source is also inspected; the latest online SDK differs from the app's SDK 57.
- [Android activity results](https://developer.android.com/training/basics/intents/result): camera activities can outlive the original process; persist the destination separately from the returned image.
- [Android permissions](https://developer.android.com/training/permissions/requesting): request in context; handle denial and settings without blocking unrelated features.
- [React Native AppState](https://reactnative.dev/docs/appstate): an external camera activity can background the app. Backgrounding is not proof of cancellation.
- [HTML capture](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/capture): capture is a browser/device hint, not a guaranteed camera UI; library remains an explicit fallback.
- [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): live browser camera streams require a secure context. This does not fix code that calls the library; file-input capture differs from a live stream.
- [Expo APK](https://docs.expo.dev/build-reference/apk/) and [internal distribution](https://docs.expo.dev/build/internal-distribution/): internal APK profile installs without Play; EAS project/account and signing are separate prerequisites.

## Planned checks

| Area | Cases | Environment / evidence needed |
|---|---|---|
| Capture | Native camera vs library; web gesture/capture hint; denied/permanently denied; cancel/no camera | SDK source, isolated controller tests, physical Android and mobile browser |
| Recovery | Activity destruction, background, rotation, app termination, unsaved exit, restored destination and same account | Persistent draft/controller tests; phone Don't keep activities test |
| Upload | Double taps, offline/slow/timeout, corrupt/mislabelled/oversized files, expired login, upload-then-attach failure, lost acknowledgement, retries | Isolated API/controller tests; actual device network interruption |
| Destination | Multiple rooms/phases, route changes, reassignment, locked/completed/cancelled work, stale revision | API regression tests plus phone workflow |
| Training | Admin CRUD/publish/archive/revision; own assignments only; onboarding; recurring and duplicate scheduler; inactive staff; due date zones; completion retry/history | Mock Mongo integration; real Mongo index/race validation separately |
| Roles | Admin/owner/supervisor/cleaner/guest; URL/record tampering; private IDs/finance; expired/deactivated session; logout cache isolation | Existing isolated security suite + new regression cases |
| Business | Properties/rooms; booking amendments/cancel/conflicts; cleaning reviews/override history; ID invitation/review/retention; reports/calendars | Existing suite + targeted additions; cloud/calendar mocks explicitly labelled |
| Usability | Small/large screens, font scale, touch targets, long labels, keyboard, empty/error/offline/back states | Source review, web checks if tooling allows; physical device checklist |
| Build | TypeScript/lint, web + Android JS exports, native config, APK signing/build/install | Local tooling inventory; EAS/Android toolchain availability |

Results and unresolved limitations are recorded in AUDIT_HANDOVER_2026-10-19.md. Planned tests are not passes. Real Mongo, AWS and device behaviour cannot be inferred from mocked checks.
