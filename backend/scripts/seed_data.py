"""Deterministic additive Pair 15 fixtures. Default execution is read-only."""
import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import random
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from sqlalchemy.orm import Session
import bcrypt
from app.database import engine
from app.models.core import User, Student, Company, Job
from app.models.additional import Resume, Application, Event

SEED = 15
CITIES = ('Sunnyvale', 'Cupertino', 'Palo Alto')
STAMP = datetime(2026, 10, 1, 9)
MARKER = 'Synthetic DATA 260 Pair 15 seed v1; not a real person or organization.'
RESUME = Path(__file__).with_name('seed_resume.txt')
MODELS = (User, Student, Company, Job, Resume, Application, Event)


def specifications():
    """Logical references make generated content independent of database IDs."""
    rng = random.Random(SEED)
    rows = []
    def add(key, model, values, refs=None):
        rows.append((key, model, values, refs or {}))
    first = ('Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley', 'Sam', 'Avery')
    last = ('Patel', 'Chen', 'Garcia', 'Nguyen', 'Williams', 'Kim', 'Singh', 'Lee')
    for role, count in [('student', 200), ('company', 50)]:
        for i in range(count):
            key = f'{role}-{i:03}'
            add('user-'+key, User, dict(email=f'p15-seed-v1-{key}@example.invalid', role=role,
                is_active=False, created_at=STAMP, updated_at=STAMP))
            if role == 'student':
                add(key, Student, dict(full_name=f'{rng.choice(first)} {rng.choice(last)}',
                    college_name='San Jose State University', career_objective=MARKER,
                    city=CITIES[i % 3], state='California', country='USA',
                    degree='BS', major=rng.choice(['Data Science', 'Computer Science', 'Business Analytics']),
                    graduation_year=2027+i % 3, date_of_birth=date(2002+i % 4, 1+i % 12, 1+i % 27),
                    cgpa=Decimal(rng.randrange(280, 401))/100,
                    skills_json=['SQL', rng.choice(['Python', 'Tableau', 'Excel'])]), {'user_id':'user-'+key})
                add('resume-'+key, Resume, dict(original_filename='Synthetic seed resume.txt',
                    stored_filename=f'p15-seed-v1-{key}.txt', file_path=str(RESUME), uploaded_at=STAMP),
                    {'student_id':key})
            else:
                add(key, Company, dict(company_name=f'P15 Seed {i+1:03} Analytics',
                    location=CITIES[i % 3], description=MARKER), {'user_id':'user-'+key})
    for i in range(300):
        category = ('internship','full_time','part_time','on_campus')[i % 4]
        add(f'job-{i:03}', Job, dict(title=f'P15 Seed {i+1:03} '+rng.choice(['Data Analyst','SQL Developer','Analytics Engineer']),
            description=MARKER+' Analyze datasets and communicate findings with the analytics team.',
            location=CITIES[i % 3], category=category, is_remote=i % 3 == 0,
            salary=Decimal(rng.randrange(2500, 9001)), posting_date=date(2026,10,1),
            deadline=date(2026,12,31), skills_json=['SQL','Python'], created_at=STAMP),
            {'company_id':f'company-{i % 50:03}'})
    pairs = rng.sample([(s,j) for s in range(200) for j in range(300)],1500)
    for i,(s,j) in enumerate(pairs):
        status = ('pending','reviewed','declined')[i % 3]
        applied = STAMP + timedelta(days=1+i % 10)
        add(f'application-{i:04}', Application, dict(status=status, applied_at=applied,
            reviewed_at=None if status == 'pending' else applied+timedelta(days=2)),
            {'student_id':f'student-{s:03}', 'job_id':f'job-{j:03}', 'resume_id':f'resume-student-{s:03}'})
    for i in range(100):
        add(f'event-{i:03}', Event, dict(event_name=f'P15 Seed {i+1:03} Analytics Career Workshop',
            description=MARKER, event_date=date(2026,11,1)+timedelta(days=i % 30),
            event_time=time(10+i % 7), location=CITIES[i % 3],
            eligibility='Undergraduate and graduate students interested in analytics', created_at=STAMP),
            {'company_id':f'company-{i % 50:03}'})
    return rows


def identity(model, values):
    fields = {User:('email',), Student:('user_id',), Company:('user_id',),
              Job:('company_id','title'), Resume:('student_id','stored_filename'),
              Application:('student_id','job_id'), Event:('company_id','event_name')}[model]
    return tuple(values[f] for f in fields)


def plan(db):
    """SELECT only: detect existing seed rows and refuse conflicts, never overwrite."""
    indexes = {}
    totals = {}
    for model in MODELS:
        objects = db.scalars(select(model)).all()
        totals[model.__tablename__] = len(objects)
        index = {}
        for obj in objects:
            key = identity(model, obj.__dict__)
            index.setdefault(key, []).append(obj)
        indexes[model] = index
    resolved, missing = {}, []
    for key, model, values, refs in specifications():
        reference_values = {field:resolved[target] for field,target in refs.items()}
        fields = {**values, **reference_values}
        matches = indexes[model].get(identity(model, fields), [])
        if len(matches) > 1:
            raise ValueError(f'Ambiguous existing seed identity: {key}; no changes applied')
        existing = matches[0] if matches else None
        if existing is not None:
            # Existing statuses/profile edits are preserved by refusing a conflicting run.
            if any(getattr(existing, field) != value for field,value in fields.items()):
                raise ValueError(f'Existing seed row differs: {key}; no changes applied')
            resolved[key] = existing.user_id if model in (Student, Company) else existing.id
        else:
            resolved[key] = key  # Symbolic ID cannot collide with a database integer ID.
            missing.append((key, model, values, refs))
    return totals, resolved, missing


def seed(db, apply=False):
    if not RESUME.is_file():
        raise ValueError('Seed resume fixture is missing')
    totals, resolved, missing = plan(db)
    counts = Counter(model.__tablename__ for _,model,_,_ in missing)
    report = {'seed':SEED, 'mode':'apply' if apply else 'dry-run', 'existing':totals,
              'insert':{m.__tablename__:counts[m.__tablename__] for m in MODELS},
              'projected':{name:count+counts[name] for name,count in totals.items()}}
    if apply:
        # Accounts are disabled and have a random, undisclosed bcrypt password.
        password_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode('ascii') if counts['users'] else None
        for key, model, values, refs in missing:
            fields = {**values, **{field:resolved[target] for field,target in refs.items()}}
            if model is User:
                fields['password_hash'] = password_hash
            obj = model(**fields)
            db.add(obj)
            db.flush()
            resolved[key] = obj.user_id if model in (Student, Company) else obj.id
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true', help='Read-only plan (default)')
    group.add_argument('--apply', action='store_true', help='Insert missing fixtures in one transaction')
    args = parser.parse_args()
    try:
        with engine.connect() as connection:
            locked = False
            try:
                if args.apply:
                    if connection.dialect.name != 'mysql':
                        raise ValueError('Live apply supports the configured MySQL database only')
                    locked = connection.execute(text("SELECT GET_LOCK('p15_seed_v1', 0)")).scalar() == 1
                    connection.commit()
                    if not locked:
                        raise ValueError('Another seed operation is running')
                with Session(bind=connection) as db:
                    with db.begin():
                        report = seed(db, apply=args.apply)
                print(json.dumps(report, indent=2))
            finally:
                if locked:
                    connection.execute(text("SELECT RELEASE_LOCK('p15_seed_v1')"))
                    connection.commit()
    except ValueError as error:
        parser.exit(1, str(error)+'\n')
    except Exception:
        parser.exit(1, 'Seed failed; transaction rolled back. Database details suppressed to protect credentials.\n')


if __name__ == '__main__':
    main()
