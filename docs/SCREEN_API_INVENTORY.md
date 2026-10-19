# Screen and API inventory — 19 October 2026

Static inspection inventory. This is not browser/device execution coverage.

## Screens

| Source | Request calls | Error-state handling in source |
|---|---|---|
| frontend/app/(admin)/_layout.tsx | 0 | Review/layout or delegated handling |
| frontend/app/(admin)/calendar.tsx | 4 | Present |
| frontend/app/(admin)/finance.tsx | 4 | Present |
| frontend/app/(admin)/index.tsx | 2 | Present |
| frontend/app/(admin)/properties.tsx | 1 | Present |
| frontend/app/+html.tsx | 0 | Review/layout or delegated handling |
| frontend/app/_layout.tsx | 0 | Present |
| frontend/app/booking/new.tsx | 5 | Present |
| frontend/app/cleaning/[id].tsx | 9 | Present |
| frontend/app/cleaning/index.tsx | 1 | Present |
| frontend/app/guest-check-in.tsx | 1 | Present |
| frontend/app/guests.tsx | 8 | Present |
| frontend/app/index.tsx | 0 | Review/layout or delegated handling |
| frontend/app/invoice/[id].tsx | 3 | Present |
| frontend/app/invoice/new.tsx | 3 | Present |
| frontend/app/issues.tsx | 1 | Present |
| frontend/app/login.tsx | 0 | Present |
| frontend/app/owner/[id].tsx | 6 | Present |
| frontend/app/owner/index.tsx | 1 | Present |
| frontend/app/property/[id].tsx | 7 | Present |
| frontend/app/property/edit.tsx | 4 | Present |
| frontend/app/report/[id].tsx | 2 | Present |
| frontend/app/report/new.tsx | 2 | Present |
| frontend/app/report/settlement.tsx | 1 | Present |
| frontend/app/staff.tsx | 5 | Present |
| frontend/app/training.tsx | 10 | Present |

## API route inventory

| Method | Path | Handler |
|---|---|---|
| POST | /auth/login | backend/server.py:241 login |
| POST | /auth/session | backend/server.py:255 google_session |
| GET | /auth/me | backend/server.py:274 me |
| GET | /users | backend/server.py:279 list_users |
| POST | /users | backend/server.py:284 create_user |
| PUT | /users/{uid} | backend/server.py:299 update_user |
| POST | /users/{uid}/reset-password | backend/server.py:338 reset_password |
| DELETE | /users/{uid} | backend/server.py:350 deactivate_user |
| POST | /upload | backend/server.py:358 upload |
| GET | /files/{media_id} | backend/server.py:393 get_file |
| GET | /properties | backend/server.py:467 list_properties |
| POST | /properties | backend/server.py:496 create_property |
| GET | /properties/{pid} | backend/server.py:504 get_property |
| PUT | /properties/{pid} | backend/server.py:515 update_property |
| DELETE | /properties/{pid} | backend/server.py:521 delete_property |
| GET | /bookings | backend/server.py:569 list_bookings |
| POST | /bookings | backend/server.py:582 create_booking |
| GET | /bookings/{bid} | backend/server.py:603 get_booking |
| PUT | /bookings/{bid} | backend/server.py:614 update_booking |
| DELETE | /bookings/{bid} | backend/server.py:649 delete_booking |
| POST | /properties/{pid}/ical-sync | backend/server.py:724 ical_sync |
| GET | /sync/status | backend/server.py:768 sync_status |
| POST | /sync/run | backend/server.py:778 sync_run |
| GET | /calendar | backend/server.py:783 calendar |
| PUT | /cleaning/{cid}/rooms/{idx}/checklist | backend/server.py:846 set_checklist |
| POST | /cleaning/{cid}/admin-action | backend/server.py:868 cleaning_admin_action |
| GET | /cleaning-team | backend/server.py:903 cleaning_team |
| POST | /cleaning/{cid}/review | backend/server.py:914 review_cleaning |
| GET | /cleaning | backend/server.py:947 list_cleaning |
| POST | /cleaning | backend/server.py:965 create_cleaning |
| GET | /cleaning/{cid} | backend/server.py:982 get_cleaning |
| POST | /cleaning/{cid}/rooms/{idx}/media | backend/server.py:988 add_room_media |
| DELETE | /cleaning/{cid}/rooms/{idx}/media/{phase}/{media_id} | backend/server.py:1019 remove_room_media |
| PUT | /cleaning/{cid} | backend/server.py:1031 update_cleaning |
| GET | /expenses | backend/server.py:1066 list_expenses |
| POST | /expenses | backend/server.py:1072 create_expense |
| DELETE | /expenses/{eid} | backend/server.py:1081 delete_expense |
| GET | /reports/settlement | backend/server.py:1144 settlement |
| POST | /payouts | backend/server.py:1173 create_payout |
| GET | /payouts | backend/server.py:1191 list_payouts |
| DELETE | /payouts/{pid} | backend/server.py:1198 delete_payout |
| GET | /reports/ota | backend/server.py:1204 ota_report |
| POST | /owner-reports | backend/server.py:1241 create_owner_report |
| GET | /owner-reports | backend/server.py:1254 list_owner_reports |
| GET | /owner-reports/{rid} | backend/server.py:1261 get_owner_report |
| DELETE | /owner-reports/{rid} | backend/server.py:1270 delete_owner_report |
| GET | /public/reports/{token}/media/{media_id} | backend/server.py:1276 public_media |
| GET | /public/reports/{token} | backend/server.py:1288 public_report |
| GET | /invoices | backend/server.py:1376 list_invoices |
| POST | /invoices | backend/server.py:1382 create_invoice |
| GET | /invoices/{iid} | backend/server.py:1395 get_invoice |
| PUT | /invoices/{iid}/status | backend/server.py:1407 set_invoice_status |
| DELETE | /invoices/{iid} | backend/server.py:1413 delete_invoice |
| GET | /dashboard | backend/server.py:1419 dashboard |
| GET | /owner/dashboard | backend/server.py:1444 owner_dashboard |
| GET | /meta | backend/server.py:1472 meta |
| GET | /guest-bookings | backend/guest_ids.py:139 guest_bookings |
| POST | /bookings/{bid}/guest-link | backend/guest_ids.py:160 invite |
| POST | /bookings/{bid}/guest-admin-action | backend/guest_ids.py:171 admin_action |
| DELETE | /bookings/{bid}/guest-link | backend/guest_ids.py:220 revoke |
| GET | /guest/check-in | backend/guest_ids.py:226 guest_status |
| POST | /guest/documents | backend/guest_ids.py:235 submit |
| GET | /guest-ids | backend/guest_ids.py:282 queue |
| GET | /guest-id-audit | backend/guest_ids.py:294 audit_log |
| GET | /guest-ids/{did}/image | backend/guest_ids.py:308 image |
| POST | /guest-ids/{did}/review | backend/guest_ids.py:315 review |
| DELETE | /guest-ids/{did} | backend/guest_ids.py:331 remove |
| POST | /guest-ids/purge-expired | backend/guest_ids.py:342 purge |
| POST | /bookings/{bid}/check-in | backend/guest_ids.py:349 check_in |
| GET | /training/lessons | backend/training.py:104 lessons |
| POST | /training/lessons | backend/training.py:108 create |
| PUT | /training/lessons/{lid} | backend/training.py:115 edit |
| POST | /training/lessons/{lid}/publish | backend/training.py:122 publish |
| POST | /training/lessons/{lid}/archive | backend/training.py:137 archive |
| POST | /training/lessons/{lid}/assign | backend/training.py:144 assign |
| GET | /training/assignments | backend/training.py:161 assignments |
| POST | /training/assignments/{aid}/complete | backend/training.py:169 complete |
| POST | /training/schedule | backend/training.py:180 schedule |
| GET | /system/issues | backend/operations.py:36 issues |
