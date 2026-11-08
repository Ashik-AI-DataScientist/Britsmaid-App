# Uniform owner statements and property calendar

Prepared 8 November 2026. Local review only, deployment requires the user's confirmation.

## Changes

- Admin and owner statement PDF exports use the same branded, fully expanded renderer. The statement shows the complete payout calculation, itemized expenses, OTA totals and a booking ledger with gross payment, GST, platform fee, other taxes, other booking expenses, net revenue, owner allocation and Britsmaid allocation. Rate bases and booking expense notes accompany each row.
- PDF statements show pending payment or recorded payment amount, paid date, method, reference/UTR, receipt number and payment notes. A difference between the recorded payment and current statement is labelled. The screen also explains that difference. Payout entry preserves paise instead of rounding the default amount to whole rupees.
- Statement data is refreshed successfully before a PDF is generated. A refresh error is reported instead of exporting stale data.
- Owner property pages have a Calendar tab reusing the admin calendar component and its OTA and cleaning markers. It is fixed to the selected property. Owners can open booking financial details and cleaning records, with admin booking creation and synchronization controls omitted. Server property scoping and write authorization remain enforced.
- All booking screens use the detailed amount component. Existing records are displayed with their saved payment and commission and a notice when tax details were not recorded. Editing an older booking opens the full amount editor with the existing commission retained. Viewing a record does not create missing tax details or rewrite it.
- Current settlements apply the configured 2% owner TDS to the positive owner balance after applicable expenses for every property, including months containing only older bookings. The old gate based on entry format was removed.
- Property split editing remains available in Edit property. Tests verify 0%, fractional and 100% owner shares and correct current statement recalculation after updates. Saved issued reports and payment receipts retain their snapshots. Current statements can therefore differ from earlier payment receipts, which is explicitly disclosed.
- Older shared electricity expenses now use the same per-record exact allocation for calculation and presentation. A residual paisa belongs to the opposite share, so owner and Britsmaid deductions equal the total bill.
- The six-month graph and statement interactive breakdowns were retained.

## Validation

- 617 isolated backend tests passed using in-memory MongoDB mocks and synthetic file/storage services, including 26 new uniform reporting, split, calendar authorization and paisa cases.
- Frontend edge suite passed, including 600 existing report/receipt scenarios and 56 new PDF cases for older, newer, mixed and empty booking sets, payment state, allocation boundaries, escaping and input immutability.
- TypeScript and zero-warning lint checks passed.
- Final web export and Android export passed.
- Pending and paid sample PDFs were generated and visually inspected after pagination fixes. A 55-booking stress PDF with long names/notes was also generated. Content and text bounds checks passed for all three PDFs.
- Existing framework deprecation warnings remain in backend tests (FastAPI startup/shutdown event hooks and multipart import). No failed tests.

## Limits and release status

Both browser-control tools failed during startup with `failed to write kernel assets: The system cannot find the path specified`. Interactive browser, physical Android and physical iPhone walkthroughs have not been completed for this release. Compilation, isolated access/calculation tests and rendered PDF checks are complete, but do not substitute for those device checks.

No live bookings, expenses, property splits, payouts or other production data were changed. No production database migration was run. No deployment branch was pushed and Render was not deployed. The separate sample PDFs contain fictional test data and are for layout review only.

PDF statements use A4 landscape to accommodate the expanded financial columns. The browser print dialog can offer Save as PDF on web. A standalone native build uses Expo's PDF/share workflow. Some print layout features, such as margin footers, depend on the device printing engine and require the pending phone checks.

## OTA clarity revision

The Revenue by OTA section now shows gross guest payments, combined taxes and commission, and revenue available to split. When recorded, other booking expenses appear separately so they are not mislabelled as taxes. The channel total is explicitly identified as being before property expenses and owner TDS, and zero deductions display without a minus sign. The same presentation is used in admin/owner statements, PDF exports and shared owner reports.

Validation for this revision: 148 targeted backend/report tests passed, including three new OTA cases for zero, one-paisa and positive booking expenses. The frontend edge suite and 659 report/PDF scenarios passed. Revised paid/pending PDF samples and the long-report sample passed content/bounds checks and visual inspection of the updated table. TypeScript, lint and the local web build were checked. Retired booking editor prompts and the old OTA Commission/Net label pair were checked for absence from current application source. This revision is a descendant of the previously reviewed local release, retaining those changes.

Interactive browser and physical phone checks remain outstanding because the browser-control tools cannot start. Deployment still requires the user's confirmation.
