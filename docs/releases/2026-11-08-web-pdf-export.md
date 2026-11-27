# Web PDF export uses the generated document

The owner Download statement PDF action and other web PDF actions previously passed generated HTML to Expo Print. Expo's web implementation calls `window.print()` on the current app page and ignores the HTML argument. The complete statement template therefore appeared in synthetic samples but was not the document printed by the live web app.

Web exports now open the generated HTML in an isolated, script-disabled preview with Print / Save PDF and Close preview controls. Printing targets the preview frame, including its statement layout and A4 landscape page rules. The app button stops loading when the preview is ready, rather than waiting on a browser print dialog. Closing restores focus; failed or slow loading reports an error. The refreshed current-statement data and native PDF generation/sharing paths are preserved.

Validation includes an export-path regression test verifying exact HTML delivery, frame printing instead of app printing, preview closing/focus and native sharing. The synthetic browser walkthrough verified that the approved complete statement template opens from the download action and closes correctly. Existing statement content/layout tests, type checks, lint and web export are also required. Live rollout and actual print-dialog checks are recorded separately in release evidence; do not equate a synthetic sample with a completed live export.

No business records, authorization rules, storage, environment or hosting configuration are changed.
