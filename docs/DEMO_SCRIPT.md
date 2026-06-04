# Demo Script

Use this script for a project defense walkthrough or recorded demo. It follows the implementation flow in the current dashboard.

## 1. Start With The Problem

Explain that Covenant University Library staff need a faster way to turn course compact topics into organized RCAABUT-style learning resources. The system is not a live writer into the production RCAABUT platform; it is a review and export layer that prepares repository-ready records.

## 2. Sign In As Super Admin

- Open the dashboard.
- Sign in with the seeded Super Admin account.
- Point out the two supported roles: Super Admin and Library Staff.
- Show that Super Admin can create users, reset passwords, disable users, and manage discovery connectors.
- Mention that disabled users cannot log in and stale tokens are rejected on protected API routes.

## 3. Upload A Course Compact

- Use a valid course compact PDF.
- Show that the upload action creates a processing job.
- Explain that the backend extracts PDF text, parses metadata/topics with Gemini when configured, and falls back to deterministic parsing when Gemini is unavailable.
- Point out that uploads are validated as PDFs and stored as extracted database records rather than permanent local files.

## 4. Review Extracted Topics Before Search

- Open the extracted course workspace.
- Edit a topic title or subtopics.
- Add a missing topic.
- Mark a non-teaching item as not searchable if needed.
- Explain that revision/exam/non-teaching weeks are skipped from resource search.
- Confirm topics before generating resources.

## 5. Generate Top 5 Resources

- Click Generate Resources after topic confirmation.
- Show the job progress area.
- Explain that enabled connectors include OpenAlex, Crossref, Open Library, and Software & Tools Suggestions.
- Explain that Gemini reranks/classifies results when configured, while fallback generation keeps the prototype usable for demos.
- Show that each searchable topic gets up to the top 5 recommendations.

## 6. Review, Edit, Approve, And Reject

- Edit a candidate resource title/category/year/authors if needed.
- Approve at least one resource.
- Reject one pending resource.
- Add one manual approved resource.
- Point out that categories are restricted to RCAABUT categories:
  - Books
  - Journal Articles
  - Newspaper Articles
  - Industry Reports
  - Workshops & Trainings
  - Software & Tools

## 7. Export Repository-Ready Records

- Show the approved repository preview grouped by topic and category.
- Export JSON, CSV, and HTML.
- Explain that exports require at least one approved resource.
- Show export history and download a stored export.
- Mention that JSON/CSV are integration-oriented, while HTML is useful for human review and presentation evidence.

## 8. Show Audit And Evaluation Evidence

- Open the activity log and point out upload, extraction, generation, review, export, user, and source events.
- Open the evaluation metrics panel.
- Mention the repeatable evaluator script:

```bash
backend/.venv/bin/python backend/scripts/evaluate_compacts.py
```

Use the generated `evaluation-results/compact-evaluation.md` table as Chapter Four evidence.

## 9. Demonstrate Archive And Restore

- Archive a course.
- Show that the course remains visible.
- Point out that mutation/generation/export buttons are disabled while archived.
- Restore the course and show that it returns to its previous workflow status.

## 10. Close With Deployment Readiness

- Explain that the backend is FastAPI with PostgreSQL and the frontend is Next.js with Tailwind.
- Mention that deployment helper files are included for Render and Railway.
- Show health endpoints:
  - `/health`
  - `/health/ready`
