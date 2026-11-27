# Britsmaid handover fixes — 3 November 2026

## Booking and statement integrity

An imported iCal event can say “Airbnb (Not available)” even after an administrator has entered the actual guest and amount. Previously the importer could replace the name and status. A confirmed booking changed to blocked was excluded from statements although its amount was retained.

Imports now preserve all saved business fields for manual bookings, admin-edited imports, and imports with an amount or commission. Different calendar observations are stored separately and surfaced through the existing sync notice, Settings → Booking checks, and the booking form. Saving after reviewing an observation acknowledges that observation; a later different observation needs review again. Untouched zero-value imported reservations can still receive genuine OTA amendments/cancellations. Missing events are not treated as permission to delete bookings.

Admin edits record the prior booking and the requested change in `booking_history`. The form sends the revision it loaded; a stale save returns an actionable conflict instead of replacing a newer save. Existing historical changes cannot be reconstructed from this new history. Never invent a lost guest name or commission: check the original OTA record or a suitable backup.

The confirmed live example was Divya Villa, 1–2 November 2026, saved amount ₹5,300 and Blocked status. Repair the existing booking after deploying the protection, preserving its ID and amount; do not create a second booking. Verify its statement, calendar and subsequent sync. Check the original guest name separately.

## Deductions

- Existing `other` expenses retain their owner-only meaning.
- New `pre_split` expenses require a title and explanatory note. They are deducted after OTA commission and before either revenue share is calculated.
- Example: ₹10,000 gross − ₹1,000 commission − ₹1,000 shared deduction = ₹8,000 to split. At 70/30, the owner share is ₹5,600 and Britsmaid share ₹2,400. A further ₹300 owner-only expense leaves ₹5,300 owner payout.
- Admin statement: **Add deduction before split**, or property → Bills & deductions → Add bill → Before split. Select the correct statement month.
- Both admin and assigned owner can expand **Other deductions · details** to see titles, notes, amounts and where each item is applied. The breakdown itself is not another deduction.
- Statement PDFs, new payout-receipt snapshots and new shared owner reports carry explanations. Existing issued snapshots are preserved, not rewritten.
- Duplicate taps are guarded; a retry of the same expense request returns the same record. Removed expenses are soft-deleted, preserving their history while excluding them from current calculations.
- Revenue remains assigned to the check-in month, as before; this release does not change monthly accounting policy.

## Calendar markers

Cleaning due uses a solid amber/yellow square. Completed cleaning remains a white square with black border. OTA/booking markers remain circles, with their existing colours. Mixed tasks still show cleaning due until all relevant tasks are complete.

## Team & logins

An admin may create an account using email, username, phone number, or a combination, with the password they choose. An email is optional. Usernames start with a letter and use 3–40 letters/numbers/dots/underscores/hyphens. Indian 10-digit phone numbers and +91 equivalents match. Include the country code for other countries.

Login identifiers must be unique. Ambiguous legacy shared contact numbers do not select an arbitrary account; those people can use their email until the admin assigns unique login details. Inactive accounts cannot sign in. Property assignment, role, identifier or password changes revoke previous sessions; the affected person signs in again. Owners see only assigned properties; cleaners and supervisors retain their existing duty restrictions. A username/phone login still needs a password; this is not SMS/OTP authentication.

The email uniqueness index becomes sparse to allow multiple accounts with no email; supplied emails remain unique. Separate unique indexes protect new normalised phone and username identifiers. Records and passwords are not reset. Older releases that require every account to have an email are not compatible with new phone-only accounts: use a compatible code rollback rather than blindly restoring an old schema assumption.

## Explicitly deferred

Guest-ID storage, its credentials, retention and activation are unchanged and inactive, following the user's decision. No guest IDs are put in ordinary R2 media. Zoho is not configured, so this release makes no changes to booking/invoice generation or their existing separation. Cleaning-photo deletion settings, legacy MongoDB photos, covers, damage records, existing invoices and hosting plans are unchanged. No paid service is enabled.

## Verification

Run the explicitly isolated local regression modules listed in `.github/workflows/quality.yml`; do not run legacy live-API suites. The handover module uses synthetic calendars and in-memory MongoDB only. Frontend checks include type checking, lint, API/capture/installation regressions and statement/receipt escaping and old-snapshot compatibility. GitHub's hosted-container job additionally exercises real isolated MongoDB indexes, phone-only accounts, role scoping and session revocation. Local browser tests use a synthetic preview; never use real properties for destructive or artificial financial tests.

Before live deployment verify encrypted backup health, preserve the current source revision, wait for CI, deploy the existing service without changing secrets or plan, and verify health and the affected screens. A code deploy does not automatically repair already-overwritten historical fields.
