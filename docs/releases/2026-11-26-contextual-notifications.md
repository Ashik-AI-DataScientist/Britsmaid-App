# Contextual notifications and guest invitation messages

## Notification design

New activity uses an action/property heading and a separate detail line. Booking events include stay dates; cleaning events include cleaning dates and distinguish scheduled, in progress, awaiting review, completed and cancelled states. Member events show member name, role and assigned properties. Expense, payout, invoice, owner report, calendar, guest-ID and training events receive appropriate summaries where their saved relationships provide context.

In-app cards display heading, details and occurrence time. Push payloads include the same context, occurrence time in IST and a safe internal destination. Updated workers open that record; older workers still receive contextual text in the compatible body. Existing workers can update when the admin visits Notifications without another permission prompt. No subscriptions are automatically enabled or disabled.

Summaries use allowlisted saved fields, not request bodies. Passwords, login tokens, invitation tokens, ID images, guest-ID names and private notes are excluded. Deleted records use a safe pre-delete snapshot. Response fields take precedence over a later concurrent edit. Failed writes produce no success event. Existing snapshot deduplication and per-admin read state remain. Password verification and unattached file uploads no longer generate misleading business-action events.

Existing notification records remain unchanged because their original detail snapshots were not captured. The new format applies to new events; this release does not invent historical dates or replay old push notifications.

## Guest share message

Get guest upload link prepares a selectable message with the lead guest name, property, stay dates, short instructions for individual/group submission and the full invitation URL. Share message & link passes this complete message to the platform share sheet. Open upload form uses the URL alone. The invitation state binds message and URL to the same captured booking so changing the selected stay cannot combine another booking's details with the link.

The previous retained-fragment fix remains in place. New messages keep the complete `#invite=...` URL; refreshing or forwarding it retains the invitation. No account, app installation or code entry is needed with a valid link. Creating a new link still revokes the previous link. Guest access remains names-only and IDs remain bound to their server-side booking/property. Admin-only review/removal and 90-day retention are unchanged.

## Verification

- 869 isolated backend tests passed, including contextual summaries, deleted records, failed actions, bounded/unusual text, credential redaction, legacy events, push payload/idempotency, concurrent-edit snapshots and the previous group upload/access tests.
- Frontend typecheck, zero-warning lint, edge suites and production web export passed. Actual screen-handler tests verify the message contents, exact URL preservation and raw-link opening. Worker tests cover contextual push, safe internal click destinations and legacy payloads.
- Built-web loopback preview at 360 x 800: cards and prepared guest message wrap without horizontal overflow or overlap. The guest form opens for the expected property/dates and retains its invitation on reload. Only synthetic data was used; no WhatsApp/email message or real push notification was sent during testing.
- No business-data migration, financial calculation change, credential reset or retention-policy change is included. Broader audit remediation remains deferred.

Deployment and live health outcome are recorded separately after the release gates pass.
