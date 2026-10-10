# Britsmaid property management app

Expo / React Native frontend, FastAPI backend and MongoDB.

- [Application review, role matrix, edge cases and feature backlog](docs/APP_REVIEW.md)
- [Guest ID storage setup and rollout](docs/GUEST_ID_DEPLOYMENT.md)
- [Existing product requirements](memory/PRD.md)

New guest ID intake uses manual admin review and a dedicated private S3/KMS store. Automated Indian ID verification is a documented next phase and requires provider onboarding. Never commit guest documents or production credentials.
