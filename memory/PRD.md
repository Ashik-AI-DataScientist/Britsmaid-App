# Britsmaid — Property Management App (PRD)

## Original problem
Property management company Britsmaid hosts villas on OTAs with owners on revenue share (varied ratios; for some clients Britsmaid pays 50% of electricity, for others owner pays all). Needs: invoices (guest stays & client services), manage all properties, owner reports with photos/videos + money split details, OTA reports, bookings from OTAs, calendar with availability & villa status, cleaning staff before/after photos of every room & common area after checkout. Client-facing reports must be interactive.

## User choices
JWT email/password (Admin & Cleaning Staff roles) · iCal import per OTA · Emergent Object Storage for media · INR · PDF invoices via share sheet · interactive client reports.

## Architecture
- Backend: FastAPI + MongoDB (server.py), bcrypt+PyJWT, icalendar, Emergent object storage. Collections: users, properties, bookings, cleaning, media, expenses, invoices, owner_reports, counters.
- Frontend: Expo Router SDK 57. (admin) tabs Home/Calendar/Villas/Finance (NativeTabs on iOS 26+). Screens: login, property/[id], property/edit, booking/new, invoice/new, invoice/[id], report/settlement, report/new, report/[id], cleaning/index, cleaning/[id], staff.

## Implemented (2026-06)
- Role-based auth; seeded admin + cleaner; team management
- Villas with owner share %, electricity mode, rooms list, iCal feeds + sync
- Bookings (manual + iCal), overlap guard, auto cleaning task at checkout
- Calendar month grid with OTA dots, cleaning markers, per-day bookings & available villas
- Cleaning sessions: per-room before/after photos, completion blocked until all documented, admin assignment
- Bills (electricity/other) feeding settlement math
- Interactive owner statement (split segments, 6-month trend, OTA expand), PDF share
- Owner reports with photos/videos + public interactive HTML link
- OTA-wise reports; invoices (guest/client, GST, discount, numbering, paid status, PDF)

## Iteration 2 (2026-06)
- Villa owner role: admin creates owner logins in Team & logins and assigns villas; owner portal shows only their villas' earnings (interactive statement + PDF), stays, reports and cleaning records (read-only)
- Server-side scoping: owners only see their own villas; cleaners can't see finances; owners can't see admin endpoints

## Iteration 3 (2026-06)
- Owner/staff invite: after creating a login (or via paper-plane icon → new temp password), share login details via WhatsApp, email or share sheet
- Automatic hourly OTA iCal sync (background task, status shown in Calendar, manual "sync all")
- Payout confirmations: admin marks month paid (amount, date, method, reference) → receipt BM-PAY-YYYY-NNNN; owners see Paid/Pending + Payouts tab with PDF receipts
- Emergent-managed Google sign-in (only for emails pre-created by admin; role from existing account)

## Backlog
- P1: Export bookings back to OTAs (iCal out feed)
- P1: WhatsApp/email send of invoices & reports
- P2: Expense categories & receipts upload, multi-currency, staff checklists per room
