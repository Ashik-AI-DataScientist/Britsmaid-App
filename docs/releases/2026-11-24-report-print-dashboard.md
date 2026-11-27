# Britsmaid report printing and net dashboard totals

## Changes

Monthly statements use A4 portrait pagination instead of landscape. Print / Save PDF prints a dedicated report root in the top-level document, with app controls and the preview excluded and fixed-height app constraints cleared. The temporary report root and print styles are removed after printing, on preview close, or on print failure. No pop-up or external print service is needed. Native PDF sharing remains unchanged.

Owner allocation for statements containing add-ons reads rental and add-ons. The redundant individual-allocation note and rental/add-on bracket in the Britsmaid breakdown are removed. Additional revenue columns are service, status/notes, gross, tax/fee, then allocation. Allocation shows owner and Britsmaid amounts with percentages in brackets; a fixed amount uses its effective percentage of net revenue. The report section is omitted when there is no positive owner allocation. Existing owner-facing filtering and stored ledgers are preserved.

The admin dashboard adds Total Owner Payout and Total Britsmaid earnings for the displayed month. The totals sum the existing settlement results for active properties: owner payout after allocated expenses and TDS; Britsmaid net after its expenses. They are calculated earnings, not the remaining unpaid balance. Private zero-owner add-ons remain included in admin earnings. Loss balances are retained. Currency font sizing responds to narrow screens and long values.

## Verification

- The backend CI runner uses Asia/Kolkata, matching the production container, so India-date fixtures and process-date queries remain consistent across midnight.
- 842 isolated backend tests passed. Added dashboard cases cover expenses, owner TDS, private add-ons, negative balances, deleted properties and non-admin denial. Existing expense, booking, owner access and reporting tests pass.
- Frontend typecheck, lint, edge suites and production web export passed, including report wording, column ordering, effective allocation, zero-share omission, print isolation and afterprint/close/error cleanup.
- Chrome local PDF renderer: synthetic A4 and Letter reports are two pages and use full-height portrait flow. First-page body reaches 775.5/841.9 points (A4) and 676.9/792 points (Letter), compared with the supplied PDF content ending around halfway down the page.
- A seven-page stress report retained all 55 bookings and 35 add-ons, repeated headers and preserved complete notes. PDF extraction verified no text outside any page. All pages visually reviewed via rendered images.
- A dedicated fixture with restrictive full-height app styles generated identical report text and pagination to the standalone report; application chrome and preview toolbar were absent.
- Actual app with disposable records verified at 390 by 844 and 320 by 640. Six tiles fit without horizontal overflow. Maximum synthetic booking amounts produced large currency values that remained readable within the tiles.

## Release safety

No database migration or stored financial edits are required. Previously downloaded PDFs remain unchanged; generate a new PDF to use this layout. Promote only after GitHub backend, frontend (including Android) and hosted-container checks pass. Verify the exact live source SHA, backup health, new tiles and owner-safe report preview without creating live financial records. Previous source: a4f60113d54b5db0f0f25b215f0c0ad7cd57b56a. Render can redeploy that source for rollback without data conversion.
