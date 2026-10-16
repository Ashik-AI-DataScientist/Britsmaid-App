# Local app preview

Open http://127.0.0.1:8765 on this computer while the preview server is running.

| Role | Email | Password |
| --- | --- | --- |
| Admin | admin@example.com | Preview@2026 |
| Property owner | owner@example.com | Preview@2026 |
| Cleaner | cleaner@example.com | Preview@2026 |
| Supervisor | supervisor@example.com | Preview@2026 |

Sign out to switch roles. Sample villas, bookings, invoices, owner reports, cleaning photos and a pending fictional guest ID are provided. Supervisors have a cleaning ready for approval/rework. Admins can open Guest IDs with the ID-card icon on the dashboard.

This runs the actual local frontend/backend from the feature branch, with an in-memory MongoDB-compatible demo adapter and local file storage. It does not connect to production or create paid cloud resources. Database edits reset when the server restarts. Test uploads stay under `.local-preview/media`; never upload real IDs or private documents. The demo storage does not provide production S3/KMS encryption. Google sign-in and external integrations are disabled; use the test logins.

To restart after closing the preview or rebooting, open PowerShell in the repository directory and run:

```powershell
& '.\.venv\Scripts\python.exe' scripts/local_preview.py
```

Keep that terminal running. Press Ctrl+C to stop it.

## Phone on the same Wi-Fi

The current phone build uses `http://192.168.1.11:8765`. Start the preview with:

```powershell
& '.\.venv\Scripts\python.exe' scripts/local_preview.py --lan-ip 192.168.1.11
```

This binds only to localhost and the specified private Wi-Fi address. The phone must use the same Wi-Fi, and the computer must remain running. Windows may require an administrator to allow inbound TCP 8765, restricted to the Wi-Fi interface and local subnet; no router port forwarding is needed. The automatic firewall change was not completed. Do not turn off Windows Firewall.

This preview build uses the address opened in the browser for API requests. If the Wi-Fi IP changes, restart the launcher with the new address and use that new phone URL. Uploaded demo files are not production-encrypted, so use dummy data only.

To rebuild after frontend edits:

```powershell
Set-Location frontend
$env:EXPO_PUBLIC_BACKEND_URL = ''
$env:EXPO_PUBLIC_GUEST_WEB_URL = ''
& '.\node_modules\.bin\expo.cmd' export --platform web --output-dir '../.local-preview/web' --clear
```

Refresh the browser after rebuilding. The launcher and ignored `.local-preview` assets are for local testing, not deployment.

## Simple admin workflows

- Guest check-in: open a stay, get the guest upload link, review IDs and press Check in. If a requirement is unmet, Check in opens a short reason form. Saving records an admin exception without claiming that missing IDs were verified.
- Under Admin options, undo check-in or undo an ID decision with a reason. Guest links stay revoked after undoing check-in; create a fresh link if needed.
- Cleaning: open a task, choose Admin: reopen, reassign or complete, pick the action, enter a reason and save. Completed tasks can be reopened and assigned to Demo Relief Cleaner. Reopening clears the current evidence for a fresh round and keeps previous photos/checklists in admin history.
- Admin exceptions do not grant other roles access to guest IDs. Deleted/expired documents cannot be restored by an override.
- Extra demo cleaner: relief@example.com, password Preview@2026. Use Cleaning > Completed to find a sample completed task for reassignment.

## Automatic Desktop shortcut

Double-click **Start Britsmaid** on the Desktop. Keep its window open. It detects the active private Wi-Fi/Ethernet address, starts the local demo, opens the PC preview and displays the URL to type on any phone/tablet using the same Wi-Fi. The window checks for address changes every five seconds and restarts the demo on the new address. A network change resets the in-memory sample data. No frontend rebuild is needed.

Only one launcher runs at a time. Ctrl+C stops its preview. If a different app owns port 8765, the launcher stops with a message rather than terminating that app. Some public or guest Wi-Fi networks prevent devices communicating with each other; the shortcut cannot change that network policy.

Launcher source: `scripts/Start-Britsmaid.ps1`. To inspect the detected address without starting/stopping anything, run it with `-CheckOnly`.
