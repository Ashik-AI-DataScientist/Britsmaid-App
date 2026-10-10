# Guest ID and cleaning rollout

## Configuration

Backend environment:

```
GUEST_ID_BUCKET=<dedicated-private-S3-bucket>
GUEST_ID_KMS_KEY=<customer-managed-KMS-key-ARN>
GUEST_ID_RETENTION_DAYS=<approved-integer-between-1-and-365>
AWS_DEFAULT_REGION=<bucket-region>
```

Use the hosting platform's IAM role rather than committing AWS keys. The guest ID feature intentionally returns 503 until the bucket, KMS key and retention period are configured. Retention is an operational policy decision; the application does not choose a legally required period. The storage calls use [Boto3 SSE-KMS parameters](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html).

Frontend environment:

```
EXPO_PUBLIC_BACKEND_URL=https://<api-host>
EXPO_PUBLIC_GUEST_WEB_URL=https://<guest-web-host>
```

Deploy the guest web route at `/guest-check-in` and configure SPA route fallback. Invitations put the capability in a URL fragment; the guest page removes the fragment and keeps the token only in memory. A reload requires reopening the invitation, or manually entering the invitation code. Do not install analytics that collect invitation fragments or document images. Backend tokens are stored hashed and expire after 48 hours. Reissuing/revoking/checking in invalidates invitations. No automated message is sent; the admin chooses where to share the invitation.

## Storage prerequisites

Use a dedicated bucket with all four S3 Block Public Access settings enabled and enforce TLS. Grant the backend role only the guest prefix's PutObject, GetObject, DeleteObject, GetObjectVersion and DeleteObjectVersion, bucket GetBucketPublicAccessBlock, and the required KMS encrypt/decrypt/data-key permissions. Keep the bucket and KMS key inaccessible to guest/owner/staff clients. The code does not expose presigned URLs. It re-encodes JPEG/PNG to strip metadata, rejects other formats and oversized requests, and streams images through an admin-only API with no-store headers.

Uploads save the bucket and object version returned by S3; deletion removes that exact version. Add an appropriate bucket lifecycle policy for abandoned objects and noncurrent versions as defence in depth, and document backup retention separately. The application purges expired records hourly in the running backend and exposes an admin purge action. Deletion failures retain storage references for retry. Run the backend continuously or schedule the purge endpoint in your existing deployment scheduler; do not rely on a Mongo TTL index, which would remove the record before deleting the stored object.

## Rollout checklist

1. In staging, create the bucket/key and choose the retention policy.
2. Start the backend to create guest-token and active guest-slot indexes.
3. Assign properties to existing cleaners and new supervisors using Team & logins. Assign cleaning sessions to eligible cleaners. Existing unassigned tasks are visible to their property's supervisors and admins.
4. Verify admin/owner/cleaner/supervisor accounts using separate sessions and two different properties.
5. Open Guest IDs from the admin home ID-card button, select a future/current booking and create an invitation. Guest uploads one ID per guest number; national IDs may have no expiry. Passport and driving licence require expiry through checkout.
6. Admin opens each private image and compares the name/document/person, approves or rejects with a reason. Guest sees rejection feedback and can retry. Check-in is allowed only on/after arrival and after every guest slot is verified.
7. Verify no document works through ordinary `/files`, public reports, owner credentials or staff credentials. Confirm actual S3 encryption, IAM denials, version deletion and expired-object purging.
8. Check cleaner before/after photos, checklist submission, supervisor rework/approval and property readiness. Test on Android/iOS devices and a browser with poor connectivity.

## Verification commands

Install the application's backend dependencies and `backend/requirements-test.txt` in an isolated environment, then run:

```
python -m pytest backend/tests/test_role_security_local.py -q
```

The suite uses the repository's configured two pytest-xdist workers and never calls the remote preview. Frontend validation after the existing Yarn dependency install:

```
yarn tsc --noEmit
yarn expo export --platform web
```

The existing remote suites expect the old direct cleaner-completion flow and unrestricted property discovery for cleaners. Update them for assigned properties, required checklists and awaiting-review semantics before running in staging.

