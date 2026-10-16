"""Test-only MySQL fixture setup/verification; never deletes existing data."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import SessionLocal
from app.models.additional import Application, Resume
from app.models.core import Job


def main():
    data = json.load(sys.stdin)
    with SessionLocal() as db:
        if data['action'] == 'resumes':
            path = Path(__file__).parent / 'fixtures' / 'run2_resume.txt'
            assert path.is_file()
            ids = []
            for student_id in data['student_ids']:
                resume = Resume(student_id=student_id, original_filename='Run 2 test resume.txt',
                                stored_filename=f'run2-test-{student_id}.txt', file_path=str(path.resolve()))
                db.add(resume)
                db.flush()
                ids.append(resume.id)
            db.commit()
            print(json.dumps(ids))
        elif data['action'] == 'verify':
            app = db.get(Application, data['application_id'])
            assert app is not None and app.student_id == data['student_id']
            assert app.job_id == data['job_id'] and app.resume_id == data['resume_id']
            assert app.status == 'pending'
            assert db.get(Job, app.job_id).title == data['title']
            print(json.dumps({'persisted': True}))


if __name__ == '__main__':
    main()
