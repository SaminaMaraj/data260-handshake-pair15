"""Migrate the Lab 1 SQL database into MongoDB (Lab 2 Part 3, S5).

Two sources:
  --sql-url URL    an existing Lab 1 database, e.g. the Pair 15 MySQL:
                   mysql+pymysql://user:pass@127.0.0.1:3307/handshake_pair15
  --from-seed      run the Lab 1 seed generator (random_state = 15) into a
                   temporary SQLite file first, then migrate that. Gives the
                   same Pair 15 dataset anywhere (Docker, EKS) without MySQL.

What it does
  * copies every table into its collection, keeping the integer ids
    (students/companies/preferences use the user id as _id)
  * keeps bcrypt password hashes unchanged, so every account still logs in
  * converts dates to "YYYY-MM-DD", times to "HH:MM:SS", money to Decimal128
  * turns Lab 1's eligibility JSON-in-TEXT into {description, majors, colleges}
  * adds denormalized fields: jobs.company_name, applications.company_id
  * copies uploaded resume PDFs into GridFS when the file still exists
  * moves each id counter past the largest imported id
  * creates all indexes, then prints SQL vs Mongo counts and verifies them

Idempotent: re-running replaces documents by _id instead of duplicating.
Use --drop to start from an empty Mongo database.

Examples, from backend/:
    python scripts/migrate_to_mongo.py --from-seed --drop
    python scripts/migrate_to_mongo.py --sql-url "$LAB1_DATABASE_URL" --drop
Environment: MONGO_URL (default mongodb://127.0.0.1:27017), MONGO_DB (handshake_p15)
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TABLES = [  # (SQL model name, collection, id column used as _id)
    ("User", "users", "id"),
    ("Student", "students", "user_id"),
    ("Company", "companies", "user_id"),
    ("Job", "jobs", "id"),
    ("Resume", "resumes", "id"),
    ("Application", "applications", "id"),
    ("Event", "events", "id"),
    ("EventRegistration", "event_registrations", "id"),
    ("StudentPreference", "student_preferences", "student_id"),
    ("SavedItem", "saved_items", "id"),
]
COUNTED = {"users", "jobs", "resumes", "applications", "events",
           "event_registrations", "saved_items"}


def run_seed_into_sqlite() -> str:
    """Lab 1 seed generator -> temporary SQLite file; returns its URL."""
    path = Path(tempfile.mkdtemp(prefix="p15_seed_")) / "lab1_seed.db"
    url = f"sqlite:///{path}"
    os.environ.setdefault("DATABASE_URL", url)
    from sqlalchemy import BigInteger, create_engine
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker

    @compiles(BigInteger, "sqlite")
    def _bigint(element, compiler, **kw):  # SQLite autoincrement needs INTEGER
        return "INTEGER"

    from app.database import Base
    import app.models  # noqa: F401  register tables
    import seed_generator

    engine = create_engine(url)
    Base.metadata.create_all(engine)
    # Bind the generator to this file explicitly, whatever DATABASE_URL says.
    seed_generator.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed_generator.make_seed_data()
    return url


def row_to_doc(model_name: str, row, id_column: str) -> dict:
    from services.common.mongo import to_mongo
    from services.common.repo import event_rules

    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    doc = {"_id": data.pop(id_column), **data}
    if model_name == "Event":
        doc["eligibility"] = event_rules({"eligibility": doc.get("eligibility")})
    if model_name == "Resume":
        doc["gridfs_id"] = None
    return to_mongo(doc)


def migrate(sql_url: str, drop: bool) -> int:
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    import gridfs
    import app.models as models
    from services.common import mongo

    engine = create_engine(sql_url)
    db = mongo.database()
    if drop:
        mongo.client().drop_database(db.name)
        print(f"Dropped MongoDB database {db.name}")

    sql_counts, max_ids = {}, {}
    with Session(engine) as session:
        for model_name, collection, id_column in TABLES:
            model = getattr(models, model_name)
            rows = session.scalars(select(model)).all()
            sql_counts[collection] = len(rows)
            docs = [row_to_doc(model_name, r, id_column) for r in rows]
            for doc in docs:
                db[collection].replace_one({"_id": doc["_id"]}, doc, upsert=True)
            if docs and collection in COUNTED:
                max_ids[collection] = max(d["_id"] for d in docs)
            print(f"  {collection:22} {len(docs):6} documents")

    # Denormalized copies the Lab 2 routes rely on.
    company_names = {c["_id"]: c["company_name"] for c in db.companies.find({}, {"company_name": 1})}
    job_company = {}
    for job in db.jobs.find({}, {"company_id": 1}):
        job_company[job["_id"]] = job["company_id"]
        db.jobs.update_one({"_id": job["_id"]},
                           {"$set": {"company_name": company_names.get(job["company_id"])}})
    for app_doc in db.applications.find({}, {"job_id": 1}):
        db.applications.update_one({"_id": app_doc["_id"]},
                                   {"$set": {"company_id": job_company.get(app_doc["job_id"])}})

    # Resume files: copy the PDF into GridFS when it is still on disk.
    bucket, copied = gridfs.GridFSBucket(db, bucket_name=mongo.RESUME_BUCKET), 0
    for resume in db.resumes.find({"gridfs_id": None}):
        path = Path(resume.get("file_path") or "")
        if path.suffix == ".pdf" and path.is_file():
            file_id = bucket.upload_from_stream(resume["stored_filename"], path.read_bytes(),
                                                metadata={"student_id": resume["student_id"]})
            db.resumes.update_one({"_id": resume["_id"]}, {"$set": {"gridfs_id": file_id}})
            copied += 1
    print(f"  resume PDFs copied to GridFS: {copied} (others are metadata-only seed rows)")

    for collection, top in max_ids.items():
        mongo.set_counter_at_least(db, collection, top)
    mongo.ensure_indexes(db)

    print("\nVerification (SQL rows vs Mongo documents):")
    ok = True
    for _, collection, _ in TABLES:
        n = db[collection].count_documents({})
        flag = "ok" if n == sql_counts[collection] else "MISMATCH"
        ok &= n == sql_counts[collection]
        print(f"  {collection:22} sql={sql_counts[collection]:6}  mongo={n:6}  {flag}")
    users = db.users.find_one({}, {"password_hash": 1})
    hashes_ok = users is None or users["password_hash"].startswith("$2")
    print(f"  bcrypt hashes preserved: {hashes_ok}")
    print(f"  indexes on applications: {sorted(db.applications.index_information())}")
    return 0 if ok and hashes_ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql-url", help="SQLAlchemy URL of the Lab 1 database")
    source.add_argument("--from-seed", action="store_true",
                        help="generate the Pair 15 seed data (SEED=15) and migrate it")
    parser.add_argument("--drop", action="store_true", help="empty the Mongo database first")
    args = parser.parse_args()

    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    sql_url = run_seed_into_sqlite() if args.from_seed else args.sql_url
    from services.common import mongo
    print(f"Migrating {sql_url.split('@')[-1]} -> MongoDB {mongo.database().name}")
    sys.exit(migrate(sql_url, args.drop))


if __name__ == "__main__":
    main()
