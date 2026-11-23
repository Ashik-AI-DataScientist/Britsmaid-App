# Britsmaid calendar reconciliation

iCal feeds describe availability and may supply generic labels rather than guest names. Protected bookings retain their entered business fields. Sync updates only its observation/review metadata for those records.

A matching-date, matching-channel reservation label of Reserved, BOOKED or OTA Guest does not replace an entered name or create a review notice by itself. Whitespace and letter case do not create name differences.

A confirmed Direct booking with the identical date range is consistent with an external OTA reporting those dates blocked. This narrow case does not change its confirmed status or Direct channel. A different date range, cancellation, actual external reservation or missing OTA still requires review. Same-channel status differences and meaningful named-guest differences also remain reviewable. Existing explicit review acknowledgements continue to apply only to the exact observation reviewed.

The comparison does not change booking amounts, commissions, financial breakdowns, guest counts, notes, revisions, payments or history. There is no bulk migration. Existing notices are recalculated by the next ordinary sync, and service notices recover after a successful sync.

Validation: the explicit isolated backend suite contains 817 cases. New regressions cover exact placeholders, meaningful names, real dates/status/channels, repeat sync, Direct availability bounds and unchanged records/settlements. The hosted-container smoke, frontend and backend CI gates must pass before deployment.
