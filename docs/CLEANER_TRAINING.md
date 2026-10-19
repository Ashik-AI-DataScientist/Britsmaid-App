# Cleaner training

Administrators open **Home → Cleaner training**. Cleaners open **My training** above their task list. Owners and supervisors have no training-management access.

1. Create a lesson with a clear title and short numbered instructions. Supporting HTTPS image/video links open in the phone browser. Never include guest IDs, passwords or private records in public links.
2. Optionally mark it for onboarding, set days allowed to finish and a refresher interval in days. Leave refresher empty for a one-off lesson.
3. Save the draft, review it and publish. Editing a draft does not change its published version until **Publish current draft** is pressed. Draft-change guidance makes this explicit.
4. Choose **Assign or reassign lesson**, select individual active cleaners or all active cleaners, and optionally enter a due date. Date-only deadlines use the end of that date in India; the API stores UTC and the screen displays device-local time.
5. Use **To do / History** to inspect cleaner names, pending/overdue status, lesson version and completion dates. A re-assignment creates a new record, preserving earlier completion evidence.
6. Cleaners read/watch the material, practise as instructed and press **I have read and completed this lesson**. The server checks that the assignment belongs to that active cleaner. Repeating completion preserves the original completion time.
7. New cleaner accounts receive published onboarding lessons. A running backend retries scheduling every minute and records scheduler errors in the existing admin issue panel. **Update refresher schedule** is a manual recovery action, not something cleaners must press. A new refresher becomes visible with its next due date after completion. Deactivated cleaners and archived lessons receive no new assignments.
8. Archiving retains assignments and completion history. Existing assignments can still be read and acknowledged; it stops new assignments and refreshers. For obsolete procedures, assign a newly published revision and tell the team which version to follow.

Lessons and their published versions are snapshotted into assignments. Editing/publishing/archiving a lesson does not rewrite past evidence. Recurrence is deduplicated by deterministic assignment keys with a unique index; only the latest completion per cleaner/lesson is considered when there is no unfinished assignment.

Training never blocks urgent cleaning tasks. Quiz authoring, pass marks and mandatory training gates are not implemented. They were optional in this request.

The local preview contains **SAMPLE — Room photo basics** as an unpublished draft. Its content is synthetic and is not approved operational training. Publishing it in a local test does not approve it for business use. Have your supervisor approve real lessons before publishing them in a persistent system.
