# Pair 15 additive seed data

The generator is `backend/scripts/seed_data.py`. It uses the existing SQLAlchemy
models and database configuration, with `SEED = 15` and cities Sunnyvale,
Cupertino, and Palo Alto. Run commands from the repository root using the existing
backend Python environment. Existing `.env` configuration is required; never
paste credentials into commands or commit them.

## Review before population

```sh
python backend/scripts/seed_data.py --dry-run
```

Omitting flags also performs a dry run. This only reads data and reports current,
missing, and projected counts. It does not insert and roll back a trial seed.
The reviewed plan adds a full, separately identifiable synthetic cohort:

| Table | Full cohort |
| --- | ---: |
| users | 250 |
| students | 200 |
| companies | 50 |
| jobs | 300 |
| resumes | 200 |
| applications | 1500 |
| events | 100 |

Existing records are additional to these counts. The cohort does not depend on
which smoke fixtures exist. It intentionally exceeds the assignment minimums
when combined with existing records. Event registrations, preferences, and saved
items are not generated.

## Populate only after explicit approval

```sh
python backend/scripts/seed_data.py --apply
```

**This command has not been executed against MySQL.** It acquires a MySQL advisory
lock to prevent concurrent runs of this generator, checks all identities, inserts
missing fixtures, and commits once. Any insertion error rolls back the transaction.
It never creates/drops tables, deletes records, or updates existing records.
Other applications should not modify seed fixtures during population.

Stable email addresses (`p15-seed-v1-…@example.invalid`), scoped job/event names,
resume filenames, and student/job application pairs identify fixtures on reruns.
A repeat run inserts zero records. Conflicting edits or ambiguous seed identities
abort the run rather than overwriting records. Do not change the namespace or
seed constant to rerun the same cohort.

Profile/job/application content and dates are deterministic. Auto-increment IDs
depend on existing database state. Bcrypt salts and the undisclosed random
password are intentionally not reproducible. Seed accounts are inactive; use
normal registered accounts to exercise login. There are no embedded credentials.

Each seeded student has a synthetic resume row referring to the bundled
`backend/scripts/seed_resume.txt` fixture, not a real personal document. Each
application uses its student's resume and a unique student/job pair. There are
500 pending, 500 reviewed, and 500 declined applications. Pending applications
have no review timestamp; other review timestamps follow application timestamps.
Dates are fixed in October–December 2026 for reproducibility, not shifted on reruns.

## Tests and verification

```sh
python -m unittest discover -s backend/tests -p test_seed_data.py -v
python backend/tests/search_smoke.py
```

Seed tests use only a disposable in-memory SQLite database with foreign keys
enabled and a SQLite-specific BIGINT primary-key compilation. They verify counts,
relationships, application statuses, preservation, idempotency, reproducibility,
read-only dry runs, conflicts, and transaction rollback. They do not verify MySQL
insertion behavior; that remains pending approved population. The search smoke
test reads the live API and database but creates no records.

After approved population, rerun `--dry-run`: insertion counts should all be zero
and database totals should meet the minimums. Do not run `schema.sql` as part of
seeding. The existing schema uses unprefixed table names; `p15` identifies seed
records without renaming tables or altering relationships.
