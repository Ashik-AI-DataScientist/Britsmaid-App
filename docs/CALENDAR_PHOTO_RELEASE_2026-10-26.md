# Britsmaid calendar, photo and cleaning update — 26 October 2026

## Calendar links for each villa

Admin: Villas → select villa → Edit property → Send this villa’s availability to an OTA.
Choose the destination, create the iCal link, copy it and paste it into that OTA’s Import calendar setting for the matching villa. Repeat for each destination and property. No OTA account is connected automatically by deploying this release.

Feeds share confirmed bookings and manually blocked nights. Checkout is exclusive: a stay ending on 10 November does not block the night of 10 November. Cancelled or removed bookings disappear from the feed. UIDs stay stable as dates change. The feed includes the last year and the next three years; longer horizons require a separate change. Failed or revoked links return an error, rather than an empty feed implying that every night is available.

Guest names, contact details, invoice amounts, cleaning evidence and ID documents are not exported. A long random read-only link is required. Only admins can create, retrieve or disable links. Disabling a link invalidates the old address; creating another one requires updating the subscribed OTAs. Possession of the link permits reading this villa’s availability, so share it only with intended calendar services.

Destination-specific links omit that destination’s own imported bookings. Incoming events carrying Britsmaid export UIDs are ignored to reduce loops. External OTAs may transform calendar events, so complete a controlled cross-platform booking/cancellation test before relying on a circular calendar configuration. iCal is availability exchange, not a full channel manager or a guarantee against double bookings.

## Sync timing

Britsmaid checks imported OTA feeds every 10 minutes while its service is running. The scheduler checks whether work is due at least every 30 seconds; after waking/restarting, overdue imports run again. The UI displays this accurately.

Exported availability is read from current saved bookings when an OTA requests it. Britsmaid cannot push an iCal feed into an OTA or determine that OTA’s polling frequency. Airbnb documents automatic refresh every three hours. Manual sync imports into Britsmaid; it does not force an OTA to pull the export. Render Free can sleep after inactivity, so the existing free setup cannot guarantee an uninterrupted ten-minute schedule. No paid hosting change is included.

Sources: https://www.airbnb.ca/help/article/99 and https://render.com/docs/free

## Photo formats and sizes

The former 20-megapixel error was a limit on width × height, not file size in megabytes. Ordinary photo uploads now accept JPEG/JPG, PNG, WebP, AVIF, HEIC/HEIF, BMP, TIFF and GIF. The first frame of animated or multipage files is used. Decoded images must be at most 50 megapixels; the existing 100 MB upload-byte limit remains. Unsupported or corrupt files are rejected before storage.

Photos are oriented correctly, scaled to at most 2400 × 2400 while preserving aspect ratio, flattened on white where transparent, and saved as compressed JPEG without source EXIF metadata. This keeps large phone/PC photos usable without consuming full-resolution storage. Photo processing is serialized within the hosted worker to limit peak memory. Uploaded video behaviour is unchanged. Guest ID validation and separate encrypted storage requirements are unchanged.

## Cleaning indicators and freshness

Completed cleaning uses a purple circular dot and a “Cleaning complete” calendar legend. Pending/review work uses a yellow circular dot; Direct bookings retain their green booking marker. If several tasks exist on a day, unfinished work takes precedence. Cancelled tasks do not create a cleaning-due indicator.

Completing, approving, reopening or reassigning cleaning invalidates the task list, admin dashboard, property list, property detail, owner dashboard and calendar caches. These property/calendar views also refresh every 30 seconds while active, so changes from another device become visible. A different outstanding cleaning task still correctly keeps “Needs cleaning” active; approval of one task does not dismiss other work.

## Owner access verification

Separate owner accounts can be assigned separate property IDs in Team & logins. API tests verify that each sees only its assigned property and cannot request another owner’s property, bookings, cleaning or calendar using a guessed ID. Existing cover-photo, report, financial and guest-ID role tests remain in the regression suite. Calendar exports are admin-managed and do not grant a signed-in app role to the recipient. An admin still sees every property.

## Zoho Invoice feasibility — investigated, not connected

The requested one-way flow is feasible: save an app invoice, then create the matching customer/invoice in the existing Zoho Invoice organisation using the supported API. Existing app invoice generation can remain available. The integration should run on the backend using OAuth with offline refresh access, not expose credentials to phone clients, and store the returned Zoho customer/invoice IDs.

Recommended implementation: save an outbox job together with the app invoice; resolve the customer mapping; create the Zoho invoice; save its ID, number and sync state; retry temporary failures with backoff; show Pending, Synced or Needs attention to admins. A stable app-invoice reference plus reconciliation before retrying an uncertain create response is required to prevent duplicates. Editing/voiding and payments need explicit mapping if those should also sync. Sending invoice emails automatically is a separate decision and should remain off unless requested.

Required setup: Zoho organisation ID and actual data centre, one-time consent to a registered OAuth application, securely stored client credentials/refresh token, customer matching rules, tax/item mappings, numbering rules and the desired Zoho invoice status (draft versus issued). Confirm how app discounts, taxes, deposits and already-paid invoices map to Zoho. Review existing invoice fields before implementing these mappings. Do not paste OAuth secrets into chat or commit them to GitHub. No existing Zoho invoice has been created, modified, emailed or deleted by this release.

Official references:
- https://www.zoho.com/invoice/api/v3/oauth/
- https://www.zoho.com/invoice/api/v3/invoices/

## Validation

Local automated regression checks include iCal privacy, property scoping, stable UIDs, exclusive checkout, cancellation/blocking, destination filtering, revocation, deleted properties, self-import prevention and ten-minute scheduling. Image checks include all eight format families, a 24-megapixel JPEG under 1 MB, orientation, transparency and metadata removal. Existing role, booking, cleaning, guest-ID, upload and hosted-storage regressions are included. Frontend checks cover mixed/cancelled task aggregation and invalidation of every affected view, plus existing request, capture and installation regressions.

Physical PC/phone selection, external OTA refresh timing and actual Zoho synchronisation are separate acceptance checks. Automated tests use synthetic records, images and mocked storage; they do not change live bookings or cleaning history.

Local result: 225 backend tests passed. TypeScript, lint, frontend request/capture/config/installation/cleaning-status checks and web export passed. A running localhost HTTP preview also passed sign-in, 24 MP image upload, cover save/read, 2400 × 1600 conversion, public availability-only feed output and 10-minute sync status. Visual browser verification was blocked because both browser and Computer Use tools failed to initialise; no physical-device or live-deployment success is claimed by this local result.
