# Android phone preview — no Play Store publication

## Testing arrangement

This preview uses a standalone ARM64 APK with embedded JavaScript and the existing package ID `com.emergent.britsmaidrevshare.ixdi3x`. It calls the PC at **http://192.168.29.55:8766**. Only that private host gets an HTTP exception; other non-HTTPS hosts and localhost are rejected by build configuration. It contains no password or government document.

The PC must remain awake and the phone must use the same private Wi-Fi. Guest/public Wi-Fi may isolate devices. Do not disable Windows Firewall, forward a router port or expose this synthetic server through an internet tunnel. The app uses HTTP for this explicitly scoped local test; use dummy data only. A hosted staging version requires HTTPS and persistent protected storage instead.

**The APK endpoint is fixed at build time.** If the PC's Wi-Fi address changes, use a newly configured APK (or use the web preview's current LAN URL). The existing automatic web launcher does not change an already installed APK's endpoint.

## Start and accounts

From the updated PC checkout `C:/Users/HP/Projects/Britsmaid/App`:

1. Double-click **Start Android Test Preview.cmd**, keep its window open and keep the PC awake. It starts the synthetic backend on port 8766 and also serves old PC bookmarks on 8765 from the same app/database. If the port is occupied, close the earlier test preview; the script does not terminate unrelated programs.
2. Open `.local-preview/private-test-accounts.txt` locally. It contains admin@example.com, cleaner@example.com, supervisor@example.com, owner@example.com and relief@example.com with a newly generated random test password. Do not upload that file to GitHub. Passwords and database records reset on each restart.
3. Confirm the backend is reachable from the phone by opening http://192.168.29.55:8766/login in its browser. If the browser cannot connect, the APK cannot connect either. Check same Wi-Fi, PC sleep, current IP and the existing local-network firewall allowance. No firewall policy was changed by this work.
4. On the phone, open **http://192.168.29.55:8766/preview.apk** to download the verified APK from the PC, then open it to install. Alternatively transfer the local `.local-preview/android/Britsmaid-preview-arm64.apk` file. Log in with a synthetic account. The login screen identifies its source commit. Installing a preview does not publish it on Google Play.

This is the actual app code with an **in-memory** Mongo-compatible test database and local dummy file storage. It is not persistent staging or production. Guest ID files here are not protected by production S3/KMS encryption. Google sign-in and external calendar/provider calls are disabled in this launcher.

If setting up another PC, install `backend/requirements-runtime.txt` plus `backend/requirements-test.txt` in `.venv`, install frontend dependencies with `pnpm install --frozen-lockfile --ignore-scripts`, and export the web preview:

```powershell
Set-Location frontend
$env:EXPO_PUBLIC_BACKEND_URL=''
pnpm exec expo export --platform web --output-dir ../.local-preview/web
```

## Build and installation

The branch contains an **Android test APK** GitHub workflow. It generates Expo's Android project, compiles `assembleRelease` for ARM64 and signs with an ephemeral test key. It uploads only the APK, exact source metadata and SHA-256 checksum. It does not use production signing credentials or submit to any store. Artifacts expire after three days, so keep the downloaded copy locally.

The first native compile exposed an undeclared `metro-cache` dependency in the old Metro configuration. The custom cache import was removed; `test:edges` now first loads the actual Metro config. A passing web/Android export had not proved a native compile would pass.

After a successful run, open its **Artifacts → britsmaid-android-preview-<commit>**, download/extract the ZIP and transfer `app-release.apk` to the phone. Android may ask to allow installation from that specific browser/file manager. Enable that source only for installation and turn the allowance off afterward. No Play Store account is needed.

This is a **test signing identity**. A later preview built with another ephemeral key may require uninstalling the earlier preview before installation. Uninstalling removes its local drafts/session. Never use this key or preview as the store release. A future production build needs the intended long-lived signing setup. ARM64 support and the generated minimum Android version must match the phone; installation on an old 32-bit phone is not verified.

## Expo/EAS alternative

No signed-in Expo/EAS account or local Java/Android SDK was present on this PC. The GitHub runner route avoids requiring a new account for this preview. EAS internal-distribution profiles remain available in `frontend/eas.json`:

- `preview`: HTTPS staging, internal distribution, APK.
- `preview-lan`: explicit private-LAN testing, internal distribution, APK.

For EAS, connect your Expo account locally using `pnpm dlx eas-cli login`, link the intended existing/new EAS project, and configure its project ID without committing tokens. From a clean committed checkout, run `scripts/Prepare-AndroidPreview.ps1 -BackendUrl <reachable-origin>` in the same terminal, then the displayed EAS build command. That helper stamps source provenance; `.easignore` includes it but excludes secrets and generated native projects. An EAS project-link change should be reviewed/committed before stamping again. Review any account quota or paid-build prompt yourself; no paid EAS service was enabled here.

Official references: [Expo APK](https://docs.expo.dev/build-reference/apk/), [internal distribution](https://docs.expo.dev/build/internal-distribution/), [native production builds](https://docs.expo.dev/guides/local-app-production/), [GitHub runner billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions). Emergent's repository metadata contains a job ID, but no connected managed-build/signing capability was available; no Emergent job was republished.

## Phone checklist

- Cleaner: open a pending assigned task, choose Living Room → Before → Take photo. Allow camera permission for that action. Save and verify its thumbnail before taking After. Repeat in a second room; confirm phases and rooms stay separate.
- Cancel the camera; check there is no new attachment. Rapidly tap capture; only one picker should open. Try library separately.
- Deny camera once, then permanently deny. Check explanations, Settings and the library fallback. Settings wording depends on the phone.
- Turn Wi-Fi off after selecting a photo. Confirm a clear error, pending work and retry. Restore Wi-Fi and retry; success must appear only after attachment.
- Background/return, rotate, and test Android developer option **Don't keep activities**. Return to the original task through the pending-photo card. Disable that developer option afterward.
- Close/reopen the app with a pending draft. Native copies are kept in app-private documents; Android result recovery is attempted on the original task. OS cleanup, app data clearing, uninstall, device restart during capture and lack of disk space are not guaranteed recoverable. A browser's temporary selection may not survive reload; keep its page open.
- Switch accounts and confirm no other person's training/tasks/photos appear. Try a completed/review-locked/reassigned task and check that the server refuses edits.
- Training: publish/assign the labelled sample as admin, acknowledge as cleaner, inspect History, run scheduler and check the next refresher.
- Supervisor: return a submitted task with feedback or approve it. Admin: reopen/reassign a completed task with a reason and inspect retained history.
- Try small/large font settings, a long room name, keyboard, back navigation and poor connectivity. Browser-sized checks do not replace these physical-device tests.

## Useful errors

Record the screen/action, time, account **role**, displayed error/reference, network state, phone model/Android version and preview source commit. Use a screenshot with names/phone numbers/IDs blurred. Never share passwords, JWTs, invitation fragments/codes, raw guest documents, full database exports or unsanitized request logs. The in-app issue panel can report recoverable server errors; it cannot notify when the entire PC is offline.
