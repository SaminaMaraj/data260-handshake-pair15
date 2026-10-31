# MongoDB Schema (Lab 2, Pair 15)

Database `handshake_p15`. Code: `backend/services/common/mongo.py` (collection
names, conversions, indexes) and `backend/services/common/repo.py` (every
business write). Migration: `backend/scripts/migrate_to_mongo.py`.

## Design decisions

| Decision | Why |
|---|---|
| **Integer ids kept** (`_id` is the Lab 1 id; new ids from `counters`, atomic `$inc`) | The React frontend, the assistant's `JOB_IDS` line and `rank_jobs` validation all use integer ids, so nothing above the database changed. |
| Students, companies and preferences use the **user id as `_id`** | One-to-one with the user, the same as Lab 1's primary keys. |
| **Dates are `"YYYY-MM-DD"` strings, times `"HH:MM:SS"`** | Range filters ("deadline before", "events next month") and sorting become plain string comparisons, with no timezone shifts. |
| **Money is `Decimal128`** with 2 places | Exact, like MySQL `NUMERIC(12,2)`. `85000` reads back as `85000.00`. |
| **Denormalized `jobs.company_name`** and **`applications.company_id`** | Job search by company name and a company's applicant list are single indexed queries with no join. `PUT /companies/{id}` updates the copy on that company's jobs. |
| **Eligibility as an object** `{description, majors, colleges}` | Lab 1 stored a JSON string inside a TEXT column; Mongo can query the fields directly. |
| **Files in GridFS** (`resume_files`, `profile_pictures`) | No shared disk volume between pods, so any replica can serve any file. |

## Collections

| Collection | Key fields | Indexes |
|---|---|---|
| `users` | `_id`, `email`, `password_hash` (bcrypt), `role`, `is_active`, `created_at` | `email` unique |
| `students` | `_id`=user id, profile fields, `cgpa` (Decimal128), `skills_json` [str] | `full_name`, `major`, `college_name` |
| `companies` | `_id`=user id, `company_name`, `location`, `description`, `contact_phone` | `company_name` |
| `jobs` | `_id`, `company_id`, `company_name`*, `title`, `posting_date`, `deadline`, `location`, `salary`, `category`, `is_remote`, `skills_json` | `(company_id, _id desc)`, `category`, `location`, `deadline`, `title`, `company_name` |
| `applications` | `_id`, `job_id`, `student_id`, `resume_id`, `company_id`*, `status`, `applied_at`, `reviewed_at`, `trace_id` | **`(job_id, student_id)` unique**, `(student_id, applied_at)`, `(company_id, applied_at)` |
| `resumes` | `_id`, `student_id`, `original_filename`, `stored_filename`, `gridfs_id` | `student_id` |
| `events` | `_id`, `company_id`, `event_name`, `description`, `event_date`, `event_time`, `location`, `eligibility` {…} | `(event_date, event_time)`, `company_id` |
| `event_registrations` | `_id`, `event_id`, `student_id`, `registered_at`, `trace_id` | **`(event_id, student_id)` unique**, `student_id` |
| `saved_items` | `_id`, `student_id`, `job_id` or `event_id`, `saved_at` | **unique `(student_id, job_id)` and `(student_id, event_id)`** (partial) |
| `student_preferences` | `_id`=student id, job preferences, event preferences, `updated_at` | — |
| `sessions` | `_id`=session id (in the JWT as `sid`), `user_id`, `role`, `created_at`, `expires_at` | **TTL on `expires_at`**, `user_id` |
| `activity_logs` | `user_id`, `action`, `at`, `trace_id`, `details` | `(user_id, at)`, `trace_id` |
| `pending_actions` | `_id`=pending id, `student_id`, `tool_name`, `arguments`, `conversation`, `expires_at` | **TTL on `expires_at`** (15 min) |
| `processed_events` | `_id`=Kafka `event_id`, `processed_at` | `processed_at` (consumer idempotency) |
| `assistant_rules`, `student_memory`, `conversations` | assistant memory layers (Part 3 memory) | `(student_id, date)`, `(student_id, updated_at)` |
| `counters` | `_id`=collection name, `seq` | — |

\* denormalized copy

## Security

- **Passwords:** bcrypt hashes, copied unchanged by the migration, so every
  Lab 1 account still signs in. Hashes are never returned by any route.
- **Sessions with expiry:** login creates a `sessions` document and puts its
  id (`sid`) in the JWT. Every request checks that the session exists, belongs
  to the token's user and has not expired. `POST /users/logout` deletes it,
  which revokes the token at once. A TTL index removes expired sessions, and
  the expiry is also checked on read, because MongoDB's TTL sweep runs only
  about once a minute.
- **Duplicates are impossible, not just unlikely:** unique indexes on
  `(job_id, student_id)`, `(event_id, student_id)` and the saved-item pairs
  mean that a replayed Kafka message or a double-clicked button cannot create
  a second row.

## Evidence

| Test | What it proves |
|---|---|
| `tests/test_mongo_parity.py` | 136 API calls give identical status and body on Lab 1 SQL and Lab 2 Mongo |
| `tests/test_tool_parity.py` | 20 assistant tool calls return identical results on the same seed data |
| `tests/test_mongo_security.py` | bcrypt, session revoke and expiry, forged-token rejection, TTL and unique indexes |
| `scripts/migrate_to_mongo.py` output | SQL row counts equal Mongo document counts for every table |
