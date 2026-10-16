"""Seed tests use SQLite in memory only; never connect to the configured MySQL DB."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.seed_data import seed, specifications, CITIES, MODELS
from app.database import Base
from app.models.core import User, Student, Company, Job
from app.models.additional import Application, Resume, Event
from sqlalchemy import BigInteger, create_engine, event, select, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kwargs):
    return 'INTEGER'


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def snapshot(self):
        return {m.__tablename__: [tuple(getattr(row,c.name) for c in m.__table__.columns)
                for row in self.db.scalars(select(m).order_by(*m.__table__.primary_key.columns))]
                for m in MODELS}

    def test_dry_run_is_read_only_and_reproducible(self):
        statements = []
        @event.listens_for(self.engine, 'before_cursor_execute')
        def track(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        result = seed(self.db)
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT') for s in statements))
        self.assertEqual(specifications(), specifications())
        self.assertEqual(result['insert'], dict(users=250,students=200,companies=50,
                         jobs=300,resumes=200,applications=1500,events=100))
        self.assertTrue(all(not rows for rows in self.snapshot().values()))

    def test_counts_relationships_statuses_and_idempotency(self):
        old = User(email='preserve@example.invalid',role='student',password_hash='untouched')
        self.db.add(old)
        self.db.flush()
        profile = Student(user_id=old.id,full_name='Existing student')
        self.db.add(profile)
        self.db.commit()
        original = self.snapshot()
        seed(self.db, apply=True)
        self.db.commit()
        first = self.snapshot()
        expected = dict(users=251,students=201,companies=50,jobs=300,resumes=200,applications=1500,events=100)
        self.assertEqual({k:len(v) for k,v in first.items()},expected)
        for table, rows in original.items():
            for row in rows:
                self.assertIn(row, first[table])
        for profile in self.db.scalars(select(Student).where(Student.user_id != old.id)):
            self.assertEqual(self.db.get(User, profile.user_id).role,'student')
            self.assertIn(profile.city,CITIES)
        for company in self.db.scalars(select(Company)):
            self.assertEqual(self.db.get(User,company.user_id).role,'company')
        pairs = set()
        statuses = set()
        for app in self.db.scalars(select(Application)):
            self.assertEqual(self.db.get(Resume,app.resume_id).student_id,app.student_id)
            job = self.db.get(Job,app.job_id)
            self.assertIsNotNone(self.db.get(Company,job.company_id))
            self.assertLessEqual(job.posting_date,app.applied_at.date())
            self.assertLessEqual(app.applied_at.date(),job.deadline)
            self.assertEqual(app.reviewed_at is None,app.status=='pending')
            if app.reviewed_at:
                self.assertGreaterEqual(app.reviewed_at,app.applied_at)
            pairs.add((app.student_id,app.job_id)); statuses.add(app.status)
        self.assertEqual(len(pairs),1500)
        self.assertEqual(statuses,{'pending','reviewed','declined'})
        for event_row in self.db.scalars(select(Event)):
            self.assertIsNotNone(self.db.get(Company,event_row.company_id))
            self.assertIn(event_row.location,CITIES)
        result = seed(self.db,apply=True)
        self.db.commit()
        self.assertTrue(all(n==0 for n in result['insert'].values()))
        self.assertEqual(self.snapshot(),first)

    def test_reproducible_content_across_fresh_databases(self):
        seed(self.db, apply=True)
        self.db.commit()
        first = self.snapshot()
        self.db.close()
        self.engine.dispose()
        self.setUp()
        seed(self.db, apply=True)
        self.db.commit()
        second = self.snapshot()
        # Password salts intentionally remain random; all fixture data is seeded.
        password_index = list(User.__table__.columns.keys()).index('password_hash')
        for result in (first, second):
            result['users'] = [row[:password_index] + row[password_index+1:] for row in result['users']]
        self.assertEqual(first, second)

    def test_conflicts_abort_without_overwrite(self):
        self.db.add(User(email='p15-seed-v1-student-000@example.invalid',role='company',password_hash='preserve'))
        self.db.commit()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError,'differs'):
            seed(self.db,apply=True)
        self.assertEqual(self.snapshot(),before)

    def test_failure_rolls_back_all_inserts(self):
        @event.listens_for(self.engine,'before_cursor_execute')
        def fail(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith('INSERT INTO jobs'):
                raise RuntimeError('Injected failure')
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            with self.db.begin():
                seed(self.db,apply=True)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(User)),0)


if __name__ == '__main__':
    unittest.main()
