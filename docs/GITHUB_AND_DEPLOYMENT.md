# GitHub branches and deployment

The current review branch is `feature/roles-cleaning-guest-verification` in the company-owned `Ashik-AI-DataScientist/Britsmaid-App` repository. Draft pull request #1 compares it with `main`.

## What is saved

Git stores application source, required image/font assets, dependency lockfiles, tests, setup notes and local launcher scripts. The same repository holds the backend and Expo frontend. A branch is a sequence of saved commits, not a second application server.

Generated dependencies (`node_modules` and `.venv`), `.env` files, credentials, signing keys, private guest files and `.local-preview` output are excluded. Install dependencies and regenerate builds when setting up another PC. Never commit real IDs or database backups.

## What each action does

- Edit files: changes exist on that PC until saved in a commit.
- Commit: creates a local, named snapshot on the current branch.
- Push: uploads those commits to that branch on GitHub.
- Pull request: shows the difference and discussion before bringing the branch into `main`. A draft is not a production-readiness approval.
- Merge: brings the approved changes into `main`; it does not itself guarantee that any running service has updated.
- Deployment: a hosting service builds/runs a selected version. Its configuration determines whether a push or merge triggers this automatically.

## Current automation

The repository's `App quality checks` workflow runs backend tests and frontend type, lint, edge-case and web-export checks on pushes to `main` and the review branch, and on pull requests. This workflow does not contain a hosting deployment or Google Play release step. External hosting services may have their own repository integrations; inspect those separately before merging.

## A practical release flow

1. Save and push changes to the review branch.
2. Check tests and review the pull request.
3. Test the chosen version in a staging deployment and on actual Android devices.
4. Merge approved changes into `main`.
5. Deploy the approved commit, or confirm the host's configured `main` deployment succeeds.
6. Verify production behaviour and keep the previous deployable version available for rollback. Database migrations require their own backup and rollback plan; reverting code does not restore database contents.

A host can instead deploy a feature branch for a separate preview. Keep that preview distinct from production data and services.

## Emergent

As checked on 18 October 2026, Emergent documents repository imports at new-job creation rather than a mid-job GitHub pull/merge. A GitHub push or merge should therefore not be assumed to update an existing Emergent workspace or live app. Ensure the Emergent job contains the approved code; use Publish or Re-publish for the hosted version. See https://help.emergent.sh/faqs and https://emergent.sh/docs/put-your-app-live .

For Android app changes, re-publish the approved code, generate a new native build and submit it to Google Play. Backend-only changes can be deployed without replacing the installed Android binary when the API remains compatible. Emergent's current managed pipeline is documented at https://help.emergent.sh/publishing-to-the-stores .

## Local preview

On the original PC, use `Start App.cmd` or `scripts/Start-Britsmaid.ps1` from the current app folder. The launcher needs the local Python environment and generated `.local-preview/web` files. Those are intentionally not uploaded. The preview runs at http://127.0.0.1:8765/ and uses sample records that reset on restart; it is not the production backend.

The real production application still needs its deployment configuration, persistent database, protected file storage, secrets and production-readiness checks. Having source in GitHub does not mean these services are deployed.