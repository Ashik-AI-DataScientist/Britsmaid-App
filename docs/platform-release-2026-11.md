# Britsmaid platform improvements

Existing records are preserved. There is no bulk migration, property relabelling, payment rewriting or business-data deletion in this release. Older clients preserve the added category and cancellation reason when those fields are omitted.

## Included

- Business writes wait briefly for competing saves. Database snapshot capture remains serialized; encryption, cloud upload and verification no longer hold the business-write lease. No uncertain write is automatically replayed.
- Confirmed stays determine occupancy. Calendar blocks show Unavailable in both property cards and owner stay lists; checkout-day stays move to recent/completed stays. Cancellation keeps the booking/history and recorded amounts, releases nights, cancels unfinished cleaning and revokes upload links. It does not cancel an OTA reservation; protected local changes are not silently resurrected by iCal.
- Per-booking additional revenue has independent percentage or rupee allocation, taxes/collection fees, service date, received/pending/refunded state and correction history. Only received entries enter earnings; original rental deductions are unchanged. Statements, reports, dashboard and insight totals include received add-ons. Saved payout snapshots remain fixed.
- Revenue insights use line charts with daily/monthly and custom ranges. Rental revenue follows check-in date; add-ons follow service date. Net excludes property expenses and owner TDS. Daily ranges are bounded to 93 days and monthly ranges to two years.
- Property categories are Villa, Apartment and Resort. Legacy categories remain unclassified until an admin chooses one. This does not introduce resort room-level inventory.
- Admin activity inbox, optional browser push, daily pending-cleaning reminders and issue alerts. Calendar imports generate activity. Push permission is device-specific; iPhone requires the home-screen web app. Push delivery is independently retried and cannot roll back a successful booking save. Notification titles omit guest ID contents.
- Shared guest upload links accept JPEG, PNG, WebP, HEIC/HEIF and up-to-four-page PDFs, maximum 8 MB per file. Files are validated and converted to sanitized JPEG, then authenticated-encrypted in a dedicated namespace in the existing private R2 backup bucket. Guest documents do not use ordinary media endpoints. Public roster exposes only names and guest slots; admin can view, review and download documents against the booking.
- Guest cleanup waits briefly for competing jobs and retries after 60 seconds when the write lease is busy, without raising a false storage failure. Guest documents expire 90 days after checkout; the hourly retention worker deletes eligible objects and clears sensitive document metadata. Changing checkout recalculates retention for documents using this policy. Existing legacy storage is still supported. A 512 MB guest-document allowance stays inside the existing shared cloud-storage cap. Keep the recovery key safe; changing it requires a deliberate migration.
- Cleaner checklist and supervisor review reject stale revisions. A multi-photo upload advances its acknowledged revision after each attachment.

## Validation and release

Run the explicit isolated backend list in .github/workflows/quality.yml; never run legacy external-service tests. Frontend gates are typecheck, lint:check, test:edges, web export and Android export. Synthetic browser walkthroughs cover desktop and phone charts, custom controls, category display and statement rendering. No production booking/payment/ID is created for testing.

Rollback uses the previous Render deploy (f3bae85b50cc1f4e0df5522d1bd67c2418515fe9). New records remain stored, but the prior UI cannot display new revenue or encrypted guest documents. Do not alter those records from the old UI. Verify the new health source SHA, backup health, admin role and a privately signed-in owner after deploying.

## ELIVAAS comparison

The developer-published eliHOMES listing describes owner booking/earnings visibility, housekeeping/maintenance status, issue reporting, performance insights and alerts. Source: https://play.google.com/store/apps/details?id=com.elivaas.owner (reviewed 23 November 2026). These public claims do not reveal its private implementation or prove accounting accuracy. Britsmaid already supplies scoped owner bookings, detailed statements/payouts and cleaning evidence; this release adds charts and admin alerts. Remaining differences include owner-created maintenance tickets and owner notifications, intentionally outside this admin-only first phase. An iCal feed is an availability import rather than a full OTA reservation/payment integration; replacing it would require official channel APIs and a separate integration project. No unsupported claim is made about ELIVAAS using a particular channel API.
