# Britsmaid application review and changes

Reviewed repository: `Ashik-AI-DataScientist/Britsmaid-App`, default branch `main`.

## Findings addressed in this change

| Finding | Implementation |
| --- | --- |
| `/files/{id}` allowed any authenticated account to retrieve another property's media | Owners need a link from their property's cleaning or report; cleaners need a link from their assigned cleaning; supervisors need their assigned property; admins can access all general media |
| Cleaner task detail and mutation routes did not enforce task assignment | Shared server-side task guard checks property access and cleaner assignment for reads, photos, notes, checklists and completion |
| Cleaners could read complete bookings and owner/property contact and financial details | Booking/calendar endpoints require admin or owner; operational property output contains only room/location/status data |
| No supervisor role | Admin assigns properties to supervisors; supervisors can assign eligible cleaners and approve or return cleaning for rework in those properties |
| Missing task quality checks | Fixed room checklist, real uploaded photo checks, duplicate photo prevention, review queue, rejection feedback and locked submitted/completed tasks |
| A concurrent task edit could overwrite a completion or change | Revision checks return 409 and require refresh rather than applying stale updates |
| Booking creation accepted nonexistent properties and invalid amounts/guest counts | Validate live property existence, positive guest count and finite nonnegative amounts |
| No guest document intake or review | Expiring/revocable booking invitation, consent, one active ID per guest slot, bounded JPEG/PNG uploads, validity checks, manual admin review and verification-gated check-in |
| Guest documents would be unsafe in ordinary report/media uploads | Separate private S3 store with required customer KMS key; IDs never become ordinary media or report attachments |
| No guest document lifecycle or accountability | Audited upload/view/review/delete/check-in, no-store responses, hourly expiry purge with retries, manual removal and explicit retention policy |

## Role access

| Role | Property scope | Cleaning | Guest documents | Financial records |
| --- | --- | --- | --- | --- |
| Admin | All | Create/assign/edit/review | Invite/view/review/delete/audit/check-in | All |
| Owner | Assigned properties | Read records and photos | No access | Existing property-scoped reports, stays and payouts |
| Supervisor | Assigned properties | Assign eligible cleaners, document work, review/rework | No access | No access |
| Cleaner | Assigned properties and personally assigned tasks | Photos, checklist, notes, submit for review | No access | No access |
| Invited guest | Invitation's booking only | No access | Submit ID and see the group's review status; cannot retrieve stored images | No access |

Admins must explicitly assign properties to existing cleaners after rollout. A cleaner with no property assignments sees no tasks. Existing completed cleaning stays completed; new completion requests go through supervisor review. Owners remain read-only. The guest invitation is a booking capability, not a permanent guest account.

## Edge cases verified locally

The isolated suite exercises unauthorized role routes; cross-property owners and cleaners; same-property wrong cleaner; deactivated accounts; media linking and photo ownership; duplicate photos; invalid room/checklist; missing photos/checklists; zero rooms; stale task revision; completed/review locks; supervisor rejection feedback; invalid assignee; malformed and oversized images/multipart requests; absent consent/name; invalid guest slot; expired ID; non-expiring national ID; expired/replaced/revoked invitation; cancellation/future check-in; duplicate active slot; two distinct guests with identical names; rejection reason and retry; opening an image before approval; review conflicts; all-guests check-in gate; expiry purge; exact-version S3 deletion; failed deletion preserving retry metadata; public storage configuration refusal and KMS upload options.

These tests use an in-memory MongoDB adapter and mocked S3. TypeScript and the Expo web export are checked separately. Real MongoDB concurrency, AWS IAM/KMS/bucket policies, a deployed browser session and physical Android/iOS devices still need staging verification. The existing suites target a shared remote preview and contain hard-coded demo credentials; they were not run against that live service.

## Further features to prioritise

| Priority | Feature | Repository evidence / need |
| --- | --- | --- |
| P1 | Automatic Indian ID verification through a contracted provider | Manual document review does not establish government authenticity; see provider plan below |
| P1 | Booking reservation lock/transaction and cancellation reconciliation | `check_overlap` currently reads before insertion; simultaneous admin bookings can race. `update_booking` updates only pending task date, so cancelled/changed-property bookings can leave obsolete cleaning work |
| P1 | Offline task drafts and retryable media queue | CaptureSheet uploads immediately; weak connectivity can interrupt a cleaner's work. Show sync state and preserve local photos/checklist until server acknowledgement |
| P1 | Structured incident and maintenance tracking | Damage/missing items currently use free-form cleaning notes. Add severity, affected room, evidence, assigned repair worker and resolution; owners see their property's incidents |
| P1 | Staff onboarding/session hardening | Existing password reset does not revoke all JWTs; add password-change session versioning, first-login password change and login rate limits. Startup currently reapplies seeded account credentials/roles; production should use explicit one-time provisioning |
| P1 | iCal import reconciliation and outbound availability | Existing import adds/updates but does not fully handle upstream cancellations or feed-to-feed conflicts; export availability and show sync failures to admins |
| P2 | Expiring/revocable owner-report sharing | Existing public reports use persistent capability links; add expiry, rotation/revocation and access auditing |
| P2 | Push reminders, priority and due time for turnovers | Cleaning currently has date/status only. Add urgent same-day turnaround, assignment notifications and escalation |
| P2 | Supplies/linen stock and expense receipts | Checklists can identify stockouts; connect to inventory and admin purchasing, add receipt evidence for property expenses |
| P2 | Scalable queues and guest lifecycle | Replace capped result lists with pagination/filtering and an arrivals-only admin queue; add identity-specific masking/redaction, minors policy and optional persistent guest account |
| P2 | Owner maintenance requests and approvals | Owners need an auditable request/quote approval flow for their own properties |

These are follow-up items, not claims that they have been implemented in this pull request.

## Indian identity provider recommendation

Start vendor evaluation with **HyperVerge**, using its DigiLocker flow for government-issued Indian documents and a separate passport flow for visitors. HyperVerge publishes India-specific document/validation APIs and describes DigiLocker retrieval for Aadhaar, PAN and driving licences:

- [HyperVerge official integrations marketplace](https://hyperverge.co/in/integrations-marketplace/)
- [HyperVerge India API documentation](https://docs.internal.hyperverge.co/modules-and-apis/india/apis/)
- [HyperVerge maintained Indian validation API repository](https://github.com/hyperverge/validation-india-rest-api)
- [Official DigiLocker partner onboarding](https://api.digitallocker.gov.in/)

This recommendation is based on documented coverage, not a pricing or hospitality eligibility assessment. Ask the provider to confirm the guest check-in use case, accepted IDs, data residency, retention/deletion, commercial terms and sandbox access before contracting. DigiLocker directly is another route, but requires requester/partner registration.

Next integration: server creates a provider transaction bound to booking + guest slot; guest completes a consent flow; server authenticates provider responses/webhooks, checks transaction binding, prevents replay, verifies issuer/document validity and records provider/method/transaction outcome. An OCR result alone must not set `verified`. Keep manual review available for failed/unsupported cases and preserve audit history. Do not store full Aadhaar numbers in ordinary booking fields or put provider credentials in Expo public environment variables.

No external verification API is enabled by this change; vendor credentials and onboarding are needed.
