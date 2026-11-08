# Britsmaid cleaning-photo retention

User decision: 27 October 2026. This policy replaces both the two-newest-sets rule and the proposed 30-day archive. The seven-day photo-recovery extension no longer applies to photos expired by this new policy.

## What changes

Each before/after cleaning photo must be at least **45 full days (1,080 hours) from its own upload timestamp** before it is eligible. Upload age is measured in UTC; local timezone and daylight-saving changes cannot shorten it. A late after-photo gets its own full 45 days, regardless of when the cleaning began or was approved. There is no requirement to upload a third cleaning set.

Automatic deletion is **off by default for every property**. Earlier global opt-in settings cannot activate the new policy. New properties also start off. Turning a property's setting on permits permanent removal of its eligible photos during a later cleanup run; it does not shorten the 45-day minimum. Turning it off stops future cleanup for that property, including pending recovery-copy removals. It cannot bring back files already removed.

## Admin instructions

1. Sign in as an admin and open **Notices → Security, storage & backups → Cleaning photo retention**.
2. Review the named property, its On/Off status and eligible-photo count.
3. Enter a reason. Select **Turn on deletion for [property]**, review the permanent-deletion notice, then confirm. Leave it off unless the business is ready for expiry.
4. To pause, enter a reason and select **Turn off deletion for [property]**. Other properties' settings are unaffected.
5. To keep a particular cleaning's evidence for damage, a dispute or owner review, open its admin cleaning controls, enter a note and select **Keep photos for damage or review**. Release that hold explicitly when appropriate.

Only admins can change these settings or holds. Owners, cleaners and supervisors cannot enable deletion, remove a hold or run cleanup. Policy changes and photo-deletion intent/completion have audit records with an actor, time and note. A confirmation screen can be cancelled without enabling anything.

## What is preserved

- Cleaning dates, room/checklist details, notes, approvals, reassignment history and payout-review records remain in MongoDB. Expired photos show a retention placeholder instead of a broken image.
- Property covers, owner-report attachments, training material, invoice/expense attachments, damage/incident records and photos referenced by other cleaning histories are excluded.
- Photos on a hold, explicitly marked as protected/damage evidence, or in a cleaning with recorded damage are preserved. The app cannot identify unlabelled damage from an image: use a damage record/report reference or the cleaning photo hold.
- Active, reopened and unapproved cleaning tasks are preserved. Only photos in completed cleanings with a matching cleaning attachment binding can expire.
- Videos, unbound uploads, government-ID documents and other categories do not inherit this policy.
- Missing, invalid, timezone-ambiguous or future upload timestamps never authorize deletion.

## Storage and recovery behaviour

R2 stores the actual photos and separate encrypted recovery files. MongoDB stores business information and photo references. The worker removes only eligible R2 cleaning images and their encrypted photo-recovery copies; it does not delete cleaning records, properties, invoices, bookings or database files.

Some migrated photos still have MongoDB rollback copies retained from the earlier rollout. **These photos stay protected until their storage review is completed.** This release does not delete those database copies or claim they have already been retired. New R2-only uploads use the normal 45-day policy.

A verified recovery object must exist and authenticate successfully before original-file removal. The recovery copy is then removed under the same expiry policy, rather than keeping an additional seven-day copy. Failed deletion is retried; metadata records intent and expiration. A pending recovery deletion respects a property pause or cleaning hold. Daily database snapshots keep business records and references, not raw R2 photo bytes; seven database snapshots are retained separately.

Cleanup uses the shared business-write lease so reference changes and policy edits cannot race file removal. It processes up to 100 eligible photos per run. Missing backup configuration or verification stops deletion. Failures appear through the existing in-app issue reporting. There are no bucket-wide Cloudflare lifecycle rules that could delete property covers or bypass property controls.

The worker checks hourly while the backend is awake. Free Render can sleep, so removal may occur **after** the 45-day threshold, never before it. Pausing deletion or keeping photos on hold increases storage use and remains subject to the existing free-allowance budgets.

## Validation and rollout

Synthetic tests cover the exact 45-day boundary, mixed upload ages and timezone offsets, unknown dates, isolated property settings, default-off behaviour, invalid property IDs, non-admin access, covers/reports/damage/shared references, holds, rollback protection, failed storage requests, recovery-copy retries and switching a property off during verification. Existing application regression checks remain required.

Deploy frontend and backend together. Verify the live page lists every property as Off. Do not enable any live property or delete real photos as part of deployment verification. Physical-phone review and a full cloud restore drill remain separate handover checks.
