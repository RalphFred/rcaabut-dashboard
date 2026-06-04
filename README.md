# RCAABUT Dashboard

A final-year project prototype for building a structured course resource repository workflow for Covenant University Library.

The system is an operational staff dashboard, not a direct writer into the live RCAABUT platform. It accepts Covenant University course compact PDFs, extracts course topics, lets Library Staff edit topics before search, generates top resource recommendations with an AI pipeline powered by Gemini, supports approval/manual additions, and exports RCAABUT-style JSON/CSV/HTML records.

## Stack

- Frontend: Next.js, TypeScript, Tailwind CSS
- Backend: FastAPI, SQLAlchemy
- Database: PostgreSQL
- Auth: email/password, JWT, role-based access
- AI pipeline: Gemini behind parser/ranker/normalizer service abstractions
- Metadata connectors: OpenAlex, Crossref, Open Library, plus software/tool suggestions
- Processing: lightweight background tasks plus `processing_jobs` records

## Roles

- `Super Admin`: manages users, resets staff passwords, and has full dashboard access.
- `Library Staff`: changes their own password, uploads compacts, edits extracted topics, generates resources, reviews/approves/rejects records, manually adds approved resources, and exports data.

Courses can be archived and restored from the dashboard. Archiving is soft and auditable; it does not delete extracted topics, recommendations, approvals, or exports. Restoring a course returns it to the workflow status it had before archive.
Course metadata edits do not change workflow status; review, generation, export, archive, and restore steps control status transitions.

Super Admin can also enable/disable source connectors from the dashboard. Default connectors are OpenAlex, Crossref, Open Library, and Software & Tools Suggestions.
Disabling a user blocks new logins and invalidates access by stale tokens because every protected API request checks that the user is still active.
Super Admin account updates are protected against self-disable, self-demotion, and removing the last active Super Admin.

Approved resources can be edited or removed before export. Re-approving the same candidate updates the existing approved record instead of creating duplicates, while rejecting an approved candidate removes its linked approved record.

The activity log traces the workflow from compact upload and extraction through resource generation, topic/resource review, exports, user changes, source changes, and archive actions.

## Workflow

1. Super Admin signs in with the seeded account.
2. Super Admin creates Library Staff accounts and can reset passwords when needed.
3. Library Staff uploads a course compact PDF.
4. Backend extracts PDF text and parses course metadata/topics.
5. Library Staff reviews and edits topics before resource generation.
6. Library Staff confirms the reviewed topics before resource generation; the API rejects generation attempts before confirmation or when no teaching topic is marked searchable.
7. The system skips non-teaching topics such as revision and examination weeks.
   If staff later marks a topic as non-searchable, generated candidates and approved resources for that topic are removed.
8. The connector layer searches open metadata sources and software/tool suggestions.
9. Gemini reranks and classifies the strongest candidates when configured.
10. Library Staff approves, rejects, edits, or manually adds resources.
11. Approved records are previewed and exported as RCAABUT-style JSON, CSV, or readable HTML, grouped by course topic, RCAABUT category, and resource number. Export requires at least one approved resource.
12. Stored export history can be downloaded again from the dashboard.

## RCAABUT Resource Categories

Resource creation and edit endpoints validate against this fixed category set:

- Books
- Journal Articles
- Newspaper Articles
- Industry Reports
- Workshops & Trainings
- Software & Tools

## Local Setup

### 1. Start PostgreSQL

```bash
docker compose up -d
```

PostgreSQL runs on host port `5434`.

### 2. Configure Backend

```bash
cd backend
cp .env.example .env
```

Set `GEMINI_API_KEY` in `backend/.env` when you want full AI extraction and AI reranking. Without it, the backend uses a basic fallback parser and ranks connector results deterministically. If external metadata APIs are unavailable too, it falls back to review placeholders so the demo still moves.

Course compact uploads must be valid PDF files. The default upload limit is `20 MB`; change `MAX_COMPACT_UPLOAD_MB` in `backend/.env` if your deployment needs a different limit.

### 3. Run Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.init_db
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

Seed login:

- Email: `admin@rcaabut.local`
- Password: `ChangeMe123!`

Change these in `.env` before deployment.

### Optional Demo Data

For a presentation-ready dashboard without uploading a PDF first, set this in `backend/.env` before running `python -m app.db.init_db`:

```bash
SEED_DEMO_DATA=true
```

This seeds one artificial intelligence demo course with extracted topics, top 5 candidate resources per topic, approved resources, and an activity-log entry. Leave it as `false` for a clean production database.

### 4. Run Frontend

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

The dashboard runs at `http://localhost:3000`.

## Smoke Test

After backend dependencies are installed, you can run a full backend workflow check without starting the servers:

```bash
cd backend
source .venv/bin/activate
python scripts/smoke_test.py
```

The script logs in with the seeded Super Admin, uploads a sample course compact, extracts topics, generates candidates, approves one resource, exports JSON/CSV/HTML, and checks activity/export reports. Set `SMOKE_PDF=/path/to/course-compact.pdf` to test another compact.
By default, the smoke test resets its temporary SQLite database before each run. Set `SMOKE_RESET=0` only when you intentionally want to inspect data from previous smoke runs.

## Compact Evaluation Report

To generate repeatable Chapter Four evidence across the available sample course compacts:

```bash
cd backend
source .venv/bin/activate
python scripts/evaluate_compacts.py
```

The evaluator uploads each compact, extracts topics, generates top 5 resource candidates, approves one resource, exports JSON/CSV, and writes `evaluation-results/compact-evaluation.json` plus `evaluation-results/compact-evaluation.md`. Set `EVALUATION_PDFS` to path-separated PDF paths to evaluate a custom set.

## Evaluation Evidence

The dashboard includes a prototype evaluation panel backed by `GET /reports/evaluation`. It reports:

- speed: average completed processing-job time
- extraction quality proxy: average extraction confidence
- resource coverage: average candidates per searchable topic
- review outcome: approval rate
- metadata coverage: source and category breakdowns

These metrics are designed to support Chapter Four evaluation screenshots and discussion. For usability evidence, pair the dashboard activity log with staff feedback/questionnaire results.

## Project Documentation

- [System Design](docs/SYSTEM_DESIGN.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [API Reference](docs/API_REFERENCE.md)
- [Deployment and Evaluation Guide](docs/DEPLOYMENT_AND_EVALUATION.md)
- [Defense Demo Script](docs/DEMO_SCRIPT.md)
- [Project Completion Audit](docs/PROJECT_COMPLETION_AUDIT.md)

## Deployment Notes

For Render or Railway:

- Deploy PostgreSQL as a managed database.
- Set backend env vars from `backend/.env.example`.
- Set `DATABASE_URL` to the managed PostgreSQL connection string.
- Set `JWT_SECRET_KEY` to a strong random value.
- Set `GEMINI_API_KEY` for production-like AI behavior.
- Set `FRONTEND_ORIGINS` to the deployed frontend URL.
- Set frontend `NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL.
- Optionally set `SEED_DEMO_DATA=true` for a presentation database; keep it `false` for a clean live database.
- Run `python -m app.db.init_db` before starting the backend. The included Render, Railway, and Procfile commands already do this.

The app does not depend on persistent local file storage. Uploaded PDFs are processed through temporary files, while extracted text, topics, resources, approvals, and exports are stored in PostgreSQL.

Deployment helper files included:

- `render.yaml` for a two-service Render deployment plus managed PostgreSQL.
- `backend/railway.toml` and `frontend/railway.toml` for Railway service-level config.
- `backend/Procfile` for Python web service startup with database initialization.
- `frontend/Procfile` for Next.js web service startup.
- `backend/runtime.txt` to pin a stable Python runtime.

For Railway, create two services from the same repository:

- Backend service: root directory `backend`, config file `/backend/railway.toml`, attach PostgreSQL, and set backend environment variables.
- Frontend service: root directory `frontend`, config file `/frontend/railway.toml`, and set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL.

Backend health endpoints:

- `/health`: process-level health.
- `/health/ready`: database readiness check for deployment platforms.
