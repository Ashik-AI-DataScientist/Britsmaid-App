# Britsmaid app domain

The intended public app address is `https://app.britsmaid.in`. Hostinger manages DNS; the existing Render service continues to run the application. MongoDB, private R2 media, backups, user accounts and business records stay in their existing services.

## Configuration

- Render service: `srv-dbca9l8473hc73fk2r10`, deployment branch `deploy/render-free`.
- Render custom domain: `app.britsmaid.in`.
- Hostinger DNS: CNAME name `app`, target `britsmaid-test.onrender.com`, TTL300 seconds.
- Keep the existing root A record, `www` CNAME, Zoho MX/SPF/DKIM/verification records and nameservers unchanged.
- Wait for Render domain verification and a valid HTTPS certificate before switching the application origin.
- Render `PUBLIC_APP_URL`: `https://app.britsmaid.in`.
- Render `LEGACY_APP_ORIGIN`: `https://britsmaid-test.onrender.com`.
- Do not change secrets, database name, media credentials, paid plans or photo retention for this cutover.

## Compatibility

The frontend uses same-origin APIs and relative installation assets. The configured legacy hostname redirects website GET/HEAD requests to the branded origin with their path and query retained. Redirects use307/no-store so a configuration rollback is not trapped behind a permanent browser cache. Browser fragment inheritance preserves guest-invitation fragments; guest-ID storage remains inactive.

API and health URLs on the old Render hostname remain available. Existing OTA iCal links and bearer-token clients keep their addresses and credentials; do not disable the Render subdomain. Cookie-authenticated write requests must come from the new exact origin, retaining the existing CSRF protection. Never solve a hostname issue by enabling wildcard CORS or weakening cookies.

Users sign in again at the branded address because browser cookies are scoped to the hostname. Existing home-screen shortcuts may still use the old origin; add the app to the home screen from the branded domain and then remove the older shortcut. Removing a shortcut does not delete an account. Existing test/pilot hosting limitations are unchanged by branding.

## Verification and rollback

Verify the DNS record and Render certificate, `/healthz`, `/healthz/backup`, installation page, manifest/icons and static assets. Check an actual admin sign-in privately, role-scoped reads, a reversible write on the existing synthetic test property, calendar links, PDFs and a private photo. Do not create artificial business records on real villas.

If the new domain is unavailable, restore `PUBLIC_APP_URL` to the old Render origin, remove `LEGACY_APP_ORIGIN`, and redeploy the same code. Old web access then works without copying or restoring the database. Do not delete DNS records or data as a first response. Keep CNAME ownership and domain renewal active for continued certificate renewal.
