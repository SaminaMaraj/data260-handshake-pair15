"""Prepare the CSV data the JMeter plan reads (jmeter/data/).

    python jmeter/make_data.py                  # CSVs from MongoDB (seeded data)
    python jmeter/make_data.py --tokens         # + log every student in -> tokens.csv

  students.csv      email,password,student_id,resume_id  (the 200 seeded students)
  tokens.csv        token,student_id,resume_id           (fresh JWTs; valid 30 min)
  open_jobs.csv     job_id of jobs whose deadline has not passed (applications)
  search_terms.csv  term,city,category                   (job / event search)
  event_terms.csv   event_term
  prompts.csv       prompt                               (assistant)

Tokens expire after 30 minutes (server session TTL), so run_all.sh refreshes
them before every test. Needs MONGO_URL/MONGO_DB (defaults: localhost,
handshake_p15) and, for --tokens, the gateway (--base).
"""
import argparse
import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DATA = Path(__file__).with_name("data")
SEED_PASSWORD = "Pair15SeedPassword!"   # the Lab 1 seed generator's shared test password

SEARCH = [  # term, city, category: all return results in the Pair 15 seed
    ("analyst", "Sunnyvale", "internship"), ("engineer", "Cupertino", "full_time"),
    ("research", "Palo Alto", "on_campus"), ("product", "Sunnyvale", "part_time"),
    ("data", "Cupertino", "internship"), ("software", "Palo Alto", "full_time"),
    ("intern", "Sunnyvale", "internship"), ("assistant", "Cupertino", "on_campus"),
]
EVENT_TERMS = ["Career", "Resume", "Information", "Networking", "Workshop"]
PROMPTS = [  # no commas or quotes: they go into a CSV and a JSON body
    "Find an internship in my city.",
    "Find a remote data science internship.",
    "Find an event for computer science students next month.",
    "Find full-time jobs in Cupertino.",
    "Show part-time jobs in Palo Alto.",
    "Find a job at Nonexistent Labs.",
    "What resume review events are coming up?",
    "Find analyst jobs that need SQL.",
]


def write(name, header, rows):
    DATA.mkdir(exist_ok=True)
    with open(DATA / name, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {name:18} {len(rows):5} rows")


def from_mongo():
    from services.common.mongo import database
    db = database()
    resumes = {r["student_id"]: r["_id"] for r in db.resumes.find({}, {"student_id": 1}).sort("_id", 1)}
    students = []
    for user in db.users.find({"role": "student", "email": {"$regex": r"^p15\.student\."}},
                              {"email": 1}).sort("_id", 1):
        if user["_id"] in resumes:
            students.append((user["email"], SEED_PASSWORD, user["_id"], resumes[user["_id"]]))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    jobs = [(j["_id"],) for j in db.jobs.find({"deadline": {"$gte": tomorrow}}, {"_id": 1}).sort("_id", 1)]
    if not students or not jobs:
        sys.exit("No seeded students or open jobs in MongoDB: run the seed first.")
    write("students.csv", ["email", "password", "student_id", "resume_id"], students)
    write("open_jobs.csv", ["job_id"], jobs)
    write("search_terms.csv", ["term", "city", "category"],
          [(t, quote(c), cat) for t, c, cat in SEARCH])     # "Palo Alto" -> "Palo%20Alto"
    write("event_terms.csv", ["event_term"], [(t,) for t in EVENT_TERMS])
    write("prompts.csv", ["prompt"], [(p,) for p in PROMPTS])
    return students


def make_tokens(base, students, limit):
    def login(row):
        email, password, student_id, resume_id = row
        req = urllib.request.Request(f"{base}/users/login", method="POST",
                                     data=json.dumps({"email": email, "password": password}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read())["access_token"], student_id, resume_id
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(login, students[:limit]))
    write("tokens.csv", ["token", "student_id", "resume_id"], rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokens", action="store_true", help="also log students in (tokens.csv)")
    parser.add_argument("--base", default=os.getenv("JMETER_BASE", "http://localhost:9150"))
    parser.add_argument("--token-count", type=int, default=200)
    args = parser.parse_args()
    print(f"Writing JMeter data to {DATA}")
    students = from_mongo()
    if args.tokens:
        make_tokens(args.base.rstrip("/"), students, args.token_count)


if __name__ == "__main__":
    main()
