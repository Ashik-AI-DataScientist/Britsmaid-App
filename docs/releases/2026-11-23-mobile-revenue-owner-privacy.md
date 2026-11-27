# Britsmaid mobile revenue and owner reporting release

## Behavior

Additional revenue uses a keyboard-aware scrolling form inside the existing sheet. The sheet title stays fixed and Save can be reached on short screens. Other sheets are unchanged.

Owner-facing booking details, insights, dashboard totals, statements, report links and receipts exclude add-ons whose effective owner allocation rounds to zero. Explicit owner amount overrides percentage. Pending and refunded private entries are also withheld. Owner payout and TDS retain their original calculation. Admin booking and settlement ledgers keep all entries. Stored records and issued snapshot data are not rewritten; owner-destination responses are projected when read. Previously downloaded files cannot be changed by this release.

The approved logo retains the original emblem image, with Britsmaid underneath. Header boxes remain 44 by 44; login dimensions are unchanged. Home-screen icons use versioned v2 paths and include the name. Original source hash and reproducible SVG composition are in frontend/brand-source. Maskable artwork fits inside the standard central safe circle.

## Validation

- 838 isolated backend tests passed, including retry-safe expense registration, 0/25/100 percent expense allocation, unchanged owner payout/TDS, private report links, immutable snapshots, fixed-zero overrides and rounding/status boundaries.
- Frontend typecheck, lint, all edge suites and production web export passed.
- Actual app with disposable in-memory data: 390 by 844 and 390 by 480 screens; revenue form scrolls to Save; zero-owner add-on saved successfully.
- A 200 INR expense allocated 25/75 registered once and deducted 50 INR from the owner and 150 INR from Britsmaid. Statement payout reconciled to 2,557.80 INR after TDS.
- Admin PDF preview excluded the private 1,234 INR add-on, retained rental revenue of 4,000 INR and the same owner payout, and showed the expense allocation correctly.
- Original artwork file and the image embedded in the master SVG match byte-for-byte; icon dimensions verified; maskable artwork maximum radius 190.9 pixels within the 204.8 pixel safe circle.

## Deployment and rollback

No data migration, credential change, or storage setting change is required. Deploy only after GitHub backend, frontend (web and Android) and hosted-container checks pass. Verify the live source SHA and backup health, header alignment and revenue-sheet scroll without creating financial records. The previous source is f9e8b31a5e4ede2fb715f8e64e200472229cff66. Render can redeploy that source if a regression occurs; all stored ledger records remain compatible.
