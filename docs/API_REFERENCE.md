# API Reference

The backend is a FastAPI application. Interactive OpenAPI docs are available at `/docs` when the backend is running.

## Auth

- `POST /auth/login`: returns JWT token and user payload.
- `GET /auth/me`: returns the current authenticated user.
- `POST /auth/change-password`: lets an authenticated user change their own password after providing the current password.

## Users

Super Admin only:

- `GET /users`
- `POST /users`
- `PATCH /users/{user_id}`: update name, role, active status, or reset password. The API prevents self-disable, self-demotion, and removal of the last active Super Admin.

## Sources

- `GET /sources`: list discovery connectors.
- `PATCH /sources/{source_id}`: update source connector, Super Admin only.

## Compacts

- `POST /compacts/upload`: upload a course compact PDF and start extraction. The backend accepts PDF files only, validates the PDF header, rejects empty uploads, and enforces `MAX_COMPACT_UPLOAD_MB`.

## Jobs

- `GET /jobs/{job_id}`: inspect extraction or resource generation progress.

## Courses

- `GET /courses`
- `GET /courses/{course_id}`: returns course detail even when the course is archived, so staff can inspect history and restore it.
- `PATCH /courses/{course_id}`: updates course metadata only; workflow status changes happen through topic confirmation, generation, export, archive, and restore endpoints.
- `POST /courses/{course_id}/archive`
- `POST /courses/{course_id}/restore`: restores the course to the workflow status it had before archive when that audit record is available.

Archived courses are read-only until restored. Mutation endpoints, resource generation, and new export generation return `409 Conflict` for archived courses.

## Topics

- `POST /courses/{course_id}/topics`
- `PATCH /courses/{course_id}/topics/{topic_id}`: marking a topic non-searchable removes generated candidates and approved resources attached to that topic.
- `DELETE /courses/{course_id}/topics/{topic_id}`: removes the topic and cleans up generated candidates and approved resources attached to that topic.
- `POST /courses/{course_id}/topics/confirm`

## Resource Candidates

- `POST /courses/{course_id}/generate-resources`: requires topics to be confirmed first with `POST /courses/{course_id}/topics/confirm` and at least one topic marked searchable.
- `PATCH /courses/{course_id}/candidates/{candidate_id}`: category must be one of the six RCAABUT resource categories.
- `POST /courses/{course_id}/candidates/{candidate_id}/review`: optional approval category override must be one of the six RCAABUT resource categories. Rejecting an approved candidate removes its linked approved resource.

## Approved Resources

- `POST /courses/{course_id}/manual-resources`: category must be one of the six RCAABUT resource categories, and the target topic must be searchable.
- `PATCH /courses/{course_id}/approved-resources/{resource_id}`: category must be one of the six RCAABUT resource categories.
- `DELETE /courses/{course_id}/approved-resources/{resource_id}`

## Exports

Export endpoints require at least one approved resource for the course.
They also require the course to be active, not archived. Stored exports can still be downloaded from report history.

- `POST /courses/{course_id}/exports/json`: stores and returns a repository-ready payload with course metadata, `generated_at`, the RCAABUT category list, and `resources_by_topics`. Each topic group includes module/week/topic fields, a `categories` map, and a flat `resources` list for compatibility. Resources are numbered within each category using `resource_number`.
- `GET /courses/{course_id}/exports/csv`: downloads the same approved resource set as CSV with `course_code`, `course_title`, `module_number`, `module_title`, `week`, `topic`, `category`, `resource_number`, `title`, `authors`, `year`, `url`, and `source`.
- `GET /courses/{course_id}/exports/html`: downloads a readable RCAABUT-style "Resources By Topics" HTML report grouped by topic, category, and numbered resources.

## Reports

- `GET /reports/activity`: returns the latest 100 audit/activity records.
- `GET /reports/exports`
- `GET /reports/exports/{export_id}/download`
- `GET /reports/evaluation`
