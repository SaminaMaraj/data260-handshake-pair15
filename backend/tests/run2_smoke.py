"""Live API tests with unique accounts and test-only resume fixtures; retains data.
Uses the backend Python environment for direct MySQL fixtures. Override its
interpreter with RUN2_DB_PYTHON if needed; never prints credentials or tokens.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import uuid
from week2_smoke import request


def db_fixture(payload):
    configured = os.getenv('RUN2_DB_PYTHON')
    candidates = [configured] if configured else [sys.executable,
        '/Users/bhavana/Desktop/Anaconda3/anaconda3/bin/python']
    for candidate in candidates:
        if candidate and subprocess.run([candidate, '-c', 'import sqlalchemy, pymysql, dotenv'],
                                        capture_output=True, timeout=10).returncode == 0:
            result = subprocess.run([candidate, str(Path(__file__).with_name('run2_db_fixture.py'))],
                                    input=json.dumps(payload), text=True, capture_output=True, timeout=20)
            if result.returncode:
                raise AssertionError('Database fixture failed; check backend environment/database (details suppressed to protect credentials).')
            return json.loads(result.stdout)
    raise RuntimeError('Set RUN2_DB_PYTHON to your backend Python interpreter.')


def account(role):
    credentials = {'email': f'run2-{uuid.uuid4().hex}@example.com', 'password': secrets.token_urlsafe(24)}
    user, _ = request('POST', '/users/register', 201, {**credentials, 'role': role})
    login, _ = request('POST', '/users/login', 200, credentials)
    return user['id'], login['access_token']


def main():
    socket.setdefaulttimeout(15)
    sid, st = account('student')
    bid, bt = account('student')
    cid, ct = account('company')
    for uid, token in [(sid, st), (bid, bt)]:
        request('POST', '/students', 201, {'user_id': uid, 'full_name': 'Run 2 Test Student'}, token)
    request('POST', '/companies', 201, {'user_id': cid, 'company_name': 'Run 2 Test Company'}, ct)
    options, _ = request('GET', '/applications/resume-options', 200, token=st)
    assert options == []
    resumes = db_fixture({'action': 'resumes', 'student_ids': [sid, bid]})
    options, _ = request('GET', '/applications/resume-options', 200, token=st)
    assert [r['id'] for r in options] == [resumes[0]]
    assert set(options[0]) == {'id', 'original_filename'}
    job_data = {'company_id': cid, 'title': f'Run 2 SQL Intern {uuid.uuid4().hex[:8]}',
                'posting_date': '2026-10-04', 'deadline': '2027-12-01', 'location': 'Sunnyvale',
                'description': 'Run 2 integration fixture', 'category': 'internship',
                'salary': '2500.00', 'is_remote': True, 'skills_json': ['SQL', 'Python']}
    job, _ = request('POST', '/jobs', 201, job_data, ct)
    jid = job['id']
    for key, value in job_data.items(): assert job[key] == value, key
    jobs, _ = request('GET', '/jobs', 200, token=st)
    assert any(item['id'] == jid for item in jobs)
    detail, _ = request('GET', f'/jobs/{jid}', 200, token=st)
    assert detail == job
    request('GET', '/jobs/9223372036854775807', 404, token=st)
    body = {'job_id': jid, 'resume_id': resumes[0]}
    for token in (None, 'invalid'):
        request('POST', '/applications', 401, body, token)
        request('GET', '/applications', 401, token=token)
        request('GET', '/applications/resume-options', 401, token=token)
    request('POST', '/applications', 403, body, ct)
    request('GET', '/applications', 403, token=ct)
    request('GET', '/applications/resume-options', 403, token=ct)
    request('POST', '/applications', 422, {**body, 'student_id': bid}, st)
    request('POST', '/applications', 422, {**body, 'status': 'reviewed'}, st)
    request('POST', '/applications', 422, {'job_id': jid}, st)
    request('POST', '/applications', 404, {**body, 'job_id': 9223372036854775807}, st)
    request('POST', '/applications', 404, {**body, 'resume_id': 9223372036854775807}, st)
    request('POST', '/applications', 403, {**body, 'resume_id': resumes[1]}, st)
    empty, _ = request('GET', '/applications', 200, token=st)
    assert empty == []
    app, _ = request('POST', '/applications', 201, body, st)
    assert app['student_id'] == sid and app['job_id'] == jid and app['resume_id'] == resumes[0]
    assert app['status'] == 'pending' and app['applied_at'] and app['job_title'] == job_data['title']
    assert app['company_name'] == 'Run 2 Test Company'
    duplicate, _ = request('POST', '/applications', 409, body, st)
    assert duplicate['detail'] == 'You have already applied to this job.'
    own, _ = request('GET', '/applications', 200, token=st)
    assert own == [app]
    other, _ = request('GET', '/applications', 200, token=bt)
    assert other == []
    # Arbitrary query parameters cannot change the token-scoped owner.
    other, _ = request('GET', f'/applications?student_id={sid}', 200, token=bt)
    assert other == []
    assert db_fixture({'action': 'verify', 'application_id': app['id'], 'student_id': sid,
                       'job_id': jid, 'resume_id': resumes[0], 'title': job_data['title']})['persisted']
    print('PASS direct MySQL application/job persistence and foreign-key associations')
    _, headers = request('OPTIONS', '/applications', 200, headers={
        'Origin': 'http://localhost:5174', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type'})
    assert headers['Access-Control-Allow-Origin'] == 'http://localhost:5174'
    request('GET', '/health/db', 200)
    print('Run 2 smoke PASS. Unique test accounts, profiles, job, resumes and application retained.')


if __name__ == '__main__':
    main()
