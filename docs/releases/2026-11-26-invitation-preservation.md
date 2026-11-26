# Britsmaid invitation preservation

## Causes and changes

- Team list invitations previously called the random password-reset endpoint. Every new invite invalidated the password previously assigned/shared. Invitations now verify an administrator-entered current member password without changing the password hash, session version, phone number or access. The creation screen continues to share the password just assigned. Stored hashes are never decrypted or returned. Explicit password resets require a supplied password; stale clients cannot trigger an automatic random reset.
- Guest intake previously removed `#invite=...` from the address after reading it. Refreshing or forwarding that address lost the invitation. Keep the fragment so the same link opens on another phone or after a reload. Native admin builds receive a complete canonical HTTPS guest link from the server instead of falling back to a bare code. An incomplete link displays resend guidance, without asking guests to enter a code. Invitation tokens remain outside HTTP URL paths/queries and are sent to the API in the authorization header.
- Show property name and stay dates on intake. The booking/property mapping still comes exclusively from the server-side invitation record; guests cannot choose or change it.

## Privacy and operations

Guests can submit for their group and see submitted names/slots only. Existing backend controls prevent overwriting an occupied slot, reading documents or removing submissions. Admin review/removal remains required; removal/rejection releases the affected slot for a replacement. Creating a new booking invitation intentionally revokes the previous link, without removing documents already uploaded. Retention stays 90 days after checkout.

An invitation contains sensitive access details: administrators must send it only to the intended recipient. This release does not recover an earlier password already replaced by the old invite flow. Set the intended password explicitly in Edit member in that case. Refresh the app before using the new flow and send a newly generated complete guest link when an earlier copied link has no fragment.

## Validation

- 850 isolated backend regression tests passed, including current-password verification, login acceptance/rejection, repeated invites preserving credentials/sessions, missing-body reset denial, role restrictions, five concurrent group uploads, cross-booking/property isolation, names-only roster, denied guest/staff reads/deletes, administrator removal and replacement, and old-link revocation.
- Frontend typecheck, zero-warning lint, all edge suites and production web export passed. Added invitation tests cover direct creation sharing, current-password verification, wrong-password refusal, separate members, first open, reload/forward, effect replay and missing-link guidance.
- Built-web loopback browser verification with synthetic data: direct access without login, five guest slots with one submitted name, reload preserving the invitation, and opening the same retained address in another tab. No real customer ID or staff password was used.
- The broader security audit is retained separately and remains deferred. No dependency upgrade, data migration, retention change or production password reset is part of this release.

## Release checks

Verify the exact deployed source and backup health, then inspect the live member invitation and public guest form. Production business data and existing passwords must not be changed merely for verification. Record deployment outcome separately; the validation above is not a claim that deployment has already occurred.
