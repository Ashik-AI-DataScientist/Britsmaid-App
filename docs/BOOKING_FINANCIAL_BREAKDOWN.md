# Britsmaid booking financial breakdown

New bookings expose optional financial details. Existing bookings retain their original amount and commission calculation until an admin chooses Add detailed amounts. No migration rewrites stored bookings, past owner reports or payment receipts.

## Calculation order

1. The entry explicitly selects whether the entered amount includes GST. Inclusive GST = gross × rate / (100 + rate). Exclusive GST = entered subtotal × rate / 100; guest total includes this GST.
2. Platform fee and platform tax each choose a percentage base: guest total or amount excluding GST. They are independent deductions, not successive percentages of a shrinking balance.
3. Each percentage and amount has a separate field. Percentage edits return the line to automatic calculation. Amount edits set a manual override. Overrides survive gross changes and are visibly flagged for review. The server recalculates automatic values and validates manual amounts; browser-derived totals are not trusted.
4. Other booking expenses require a title and reduce revenue before the owner/Britsmaid split.
5. Monthly net revenue is split using the property's owner percentage. Existing before-split property expenses retain their meaning.
6. Owner and Britsmaid allocated expenses reduce each share exactly once. The expense must allocate 100% and its two amounts must equal the total. An expense cannot be both allocated and before-split.
7. Owner TDS is 2% of the positive owner balance AFTER all owner expenses. Negative/zero balances incur zero TDS. Final owner payout subtracts that TDS. TDS does not become Britsmaid income.

The new TDS calculation applies to a monthly statement once it contains a detailed booking or an explicitly allocated expense. Entirely untouched legacy months keep their old calculation. This avoids silently changing historical balances. TDS is rounded once at monthly level rather than independently per booking; monthly expenses cannot be accurately assigned to a single booking without a separate allocation rule.

Saved payment receipts and previously generated owner reports remain snapshots. Regenerate a report after amending financial entries to reflect the updated statement. Existing paid amounts remain recorded; the app's balance shows any resulting difference.

## Access and attachments

Admins edit financial data. Owners may expand their own bookings and expenses read-only. Cleaners and supervisors do not gain finance access. Expense evidence uses existing private media storage and camera/library capture. Attachments only load after View attachments. Server authorization checks property assignments. An intentionally shared owner-report link includes only the attachments recorded in that report's snapshot.

Expense evidence and report-snapshot evidence are protected from cleaning-photo retention. Existing MongoDB photos and guest-ID storage are unchanged.

## Release validation

Run the explicit isolated test modules in .github/workflows/quality.yml, frontend typecheck/lint/test:edges and web/Android exports. Synthetic tests cover GST-inclusive/exclusive calculations, independent fee bases, manual overrides, balanced allocations, rounding, TDS after expenses, negative balances, idempotent expense retries, stale revisions and cross-property attachment restrictions. No live booking or expense is required for verification.
