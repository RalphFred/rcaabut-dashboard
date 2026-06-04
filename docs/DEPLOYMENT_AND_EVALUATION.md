# Deployment and Evaluation Guide

## Local Verification

Run backend smoke test:

```bash
cd backend
source .venv/bin/activate
python -m app.db.init_db
python scripts/smoke_test.py
```

The smoke test uses a temporary SQLite database and resets it by default for repeatable results. Set `SMOKE_RESET=0` only when you want to preserve the previous smoke-test database for debugging.

Run frontend production build:

```bash
cd frontend
pnpm build
```

Generate multi-compact evaluation evidence:

```bash
cd backend
source .venv/bin/activate
python scripts/evaluate_compacts.py
```

The evaluator writes:

- `evaluation-results/compact-evaluation.json`: machine-readable metrics.
- `evaluation-results/compact-evaluation.md`: report table suitable for Chapter Four discussion.

Use `EVALUATION_PDFS` with path-separated PDF paths when evaluating a different set of course compacts.

## Render Deployment

The repository includes `render.yaml` with:

- backend FastAPI service
- frontend Next.js service
- managed PostgreSQL database
- backend pre-deploy command that initializes database tables and seed data
- backend readiness health check at `/health/ready`
- frontend build command that enables Corepack before using the pinned pnpm version

Important environment variables:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `FRONTEND_ORIGINS`
- `SEED_SUPER_ADMIN_EMAIL`
- `SEED_SUPER_ADMIN_PASSWORD`
- `SEED_DEMO_DATA`
- `NEXT_PUBLIC_API_BASE_URL`

The backend accepts both `postgresql://` and hosted-provider `postgres://` database URLs. It normalizes `postgres://` internally for SQLAlchemy.

The database initializer is idempotent. It creates missing tables and seeds the Super Admin account plus default source connectors without duplicating existing records.

Set `SEED_DEMO_DATA=true` only when you want a presentation-ready database with a demo course, topics, candidate resources, approved resources, and activity-log evidence. Keep it `false` for a clean production database.

## Railway Deployment

Use two services:

- backend service from `backend/`
- frontend service from `frontend/`

Add a PostgreSQL plugin/database and set the backend `DATABASE_URL`.

Recommended Railway settings:

- Backend root directory: `/backend`
- Backend config file path: `/backend/railway.toml`
- Frontend root directory: `/frontend`
- Frontend config file path: `/frontend/railway.toml`

The service config files define Railpack builds, start commands, health checks, and the backend pre-deploy database initializer. If entering commands manually in Railway, use:

```bash
python -m app.db.init_db
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Frontend manual build/start commands:

```bash
corepack enable && pnpm build
pnpm start --hostname 0.0.0.0 --port $PORT
```

## Evaluation Metrics

The evaluation dashboard is backed by `GET /reports/evaluation`.

Suggested Chapter Four evidence:

- Upload screenshots for at least three compact formats:
  - clean week-word format
  - portal table format
  - modern module/week format
- Topic extraction counts from the dashboard.
- Average job time from the evaluation panel.
- Average extraction confidence from the evaluation panel.
- Candidates per searchable topic.
- Approval rate after Library Staff review.
- Source breakdown to show metadata coverage.
- Category breakdown to show RCAABUT compatibility.
- Activity log screenshot to prove auditability.
- Export history screenshot to prove output generation.
- `evaluation-results/compact-evaluation.md` table to support claims about extraction coverage and candidate-generation consistency across multiple compact formats.

## Usability Evidence

For staff usability evaluation, pair dashboard screenshots with a simple questionnaire covering:

- ease of PDF upload
- clarity of extracted topic review
- usefulness of top 5 recommendations
- ease of editing/approving records
- usefulness of JSON/CSV export
- overall time saved compared to manual search and entry
