# Database Schema

The system uses PostgreSQL through SQLAlchemy models. During local smoke tests, SQLite is used only as a lightweight test database.

## `users`

Stores Super Admin and Library Staff accounts.

| Field | Purpose |
| --- | --- |
| `id` | Primary key |
| `full_name` | User display name |
| `email` | Login email |
| `password_hash` | PBKDF2 password hash |
| `role` | `super_admin` or `library_staff` |
| `is_active` | Enables/disables login |
| `created_at` | Creation timestamp |

## `source_databases`

Stores configurable discovery sources.

| Field | Purpose |
| --- | --- |
| `source_key` | Connector key such as `openalex` |
| `display_name` | Human-readable source name |
| `source_type` | Metadata/source class |
| `base_url` | Source API or site URL |
| `is_enabled` | Whether generation can use this source |
| `notes` | Staff-facing source notes |

## `courses`

Stores extracted course compact metadata.

| Field | Purpose |
| --- | --- |
| `course_code` | Course code |
| `course_title` | Course title |
| `college` | College name |
| `department` | Department |
| `programme` | Programme |
| `level` | Level, when present |
| `semester` | Alpha/Omega semester |
| `session` | Academic session |
| `lecturers_json` | Lecturer names |
| `description` | Course overview |
| `status` | Workflow state: `uploaded`, `extracted`, `topics_reviewed`, `resources_generated`, `exported`, or `archived` |

## `course_compacts`

Stores uploaded PDF metadata and extracted text.

| Field | Purpose |
| --- | --- |
| `original_filename` | Uploaded filename |
| `content_type` | MIME type |
| `file_size` | PDF size |
| `extracted_text` | Text extracted from PDF |
| `status` | Upload/extraction state |
| `error_message` | Failure detail |

## `topics`

Stores extracted and edited weekly topics.

| Field | Purpose |
| --- | --- |
| `course_id` | Parent course |
| `module_number` | Module number |
| `module_title` | Module title |
| `week_number` | Week number |
| `topic_title` | Searchable topic |
| `subtopics_json` | Subtopics |
| `outcomes_json` | Learning outcomes |
| `extraction_confidence` | Parser confidence score |
| `is_searchable` | Whether resource search should use topic |

## `candidate_resources`

Stores raw generated/retrieved resource candidates.

| Field | Purpose |
| --- | --- |
| `course_id` | Parent course |
| `topic_id` | Parent topic |
| `category` | RCAABUT category |
| `title` | Resource title |
| `authors_json` | Author names |
| `year` | Publication year |
| `abstract` | Abstract/description |
| `url` | Access/discovery URL |
| `source_system` | Connector or fallback source |
| `source_record_id` | External identifier |
| `relevance_score` | Ranking score |
| `match_reason` | Explanation |
| `status` | Pending/edited/approved/rejected |

## `approved_resources`

Stores repository-ready records after staff approval.

| Field | Purpose |
| --- | --- |
| `candidate_id` | Source candidate, if any |
| `category` | RCAABUT category |
| `title` | Approved title |
| `authors_json` | Approved authors |
| `year` | Approved year |
| `url` | Approved URL |
| `source_system` | Candidate/manual source |
| `note` | Staff note |
| `approved_by_id` | Approving user |

## `processing_jobs`

Tracks extraction and resource generation work.

| Field | Purpose |
| --- | --- |
| `job_type` | Extraction or resource generation |
| `status` | Queued/running/completed/failed |
| `progress` | Percent progress |
| `message` | Staff-facing job status |
| `error_message` | Failure detail |
| `finished_at` | Completion timestamp |

## `approval_logs`

Stores audit history for compact upload/extraction, resource generation, topic edits, approvals, source updates, exports, user changes, archive, and restore actions.

## `export_records`

Stores generated JSON, CSV, and HTML export history.
