"""Run against the live local API. Creates fresh test data; never deletes data."""
import json
import secrets
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:9150"


def request(method, path, expected, body=None, token=None, headers=None):
    headers = dict(headers or {})
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                  headers=headers, method=method)
    try:
        response = urlopen(req)
    except HTTPError as error:
        response = error
    data = response.read()
    assert response.status == expected, f'{method} {path}: expected {expected}, got {response.status}'
    print(f'PASS {method} {path}: {expected}')
    return json.loads(data) if data and "application/json" in response.headers.get("Content-Type", "") else None, response.headers


def main():
    request('GET', '/', 200)
    health, _ = request('GET', '/health/db', 200)
    assert health['database'] == 'handshake_pair15'
    accounts = {}
    for role in ('student', 'company'):
        credentials = {'email': f'week2-{role}-{uuid.uuid4().hex[:12]}@example.com',
                       'password': secrets.token_urlsafe(24)}
        user, _ = request('POST', '/users/register', 201, {**credentials, 'role': role})
        assert 'password_hash' not in user
        request('POST', '/users/register', 409, {**credentials, 'role': role})
        login, _ = request('POST', '/users/login', 200, credentials)
        assert login['role'] == role and login['id'] == user['id']
        token = login['access_token']
        accounts[role] = (user['id'], token)
        request('POST', '/users/login', 401, {**credentials, 'password': 'incorrect'})
        request('GET', '/students/me/dashboard' if role == 'student' else '/companies/me/dashboard', 200, token=token)
        other = 'company' if role == 'student' else 'student'
        other_path = '/companies/me/dashboard' if other == 'company' else '/students/me/dashboard'
        request('GET', other_path, 403, token=token)
        request('GET', '/users/me', 401, token=token[:-5] + 'xxxxx')
    for path in ('/users/me', '/students/me/dashboard', '/companies/me/dashboard', '/students', '/companies', '/jobs'):
        _, headers = request('GET', path, 401)
        assert headers['WWW-Authenticate'] == 'Bearer'
        request('GET', path, 401, token='invalid')
    sid, student_token = accounts['student']
    cid, company_token = accounts['company']
    student = {'user_id': sid, 'full_name': 'Week 2 Test Student'}
    company = {'user_id': cid, 'company_name': 'Week 2 Test Company'}
    request('POST', '/students', 403, student, company_token)
    request('POST', '/companies', 403, company, student_token)
    request('POST', '/students', 403, {**student, 'user_id': cid}, student_token)
    request('POST', '/companies', 403, {**company, 'user_id': sid}, company_token)
    request('POST', '/students', 201, student, student_token)
    request('POST', '/companies', 201, company, company_token)
    request('POST', '/students', 409, student, student_token)
    request('POST', '/companies', 409, company, company_token)
    job = {'company_id': cid, 'title': 'Week 2 authorization test', 'posting_date': '2026-10-03',
           'deadline': '2026-12-01', 'location': 'Sunnyvale', 'description': 'Test data', 'category': 'internship'}
    request('POST', '/jobs', 403, job, student_token)
    request('POST', '/jobs', 403, {**job, 'company_id': sid}, company_token)
    result, _ = request('POST', '/jobs', 201, job, company_token)
    for token in (student_token, company_token):
        for path in ('/students', '/companies', '/jobs', f'/students/{sid}', f'/companies/{cid}', f'/jobs/{result["id"]}'):
            request('GET', path, 200, token=token)
    _, headers = request('OPTIONS', '/users/me', 200, headers={
        'Origin': 'http://localhost:5174', 'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization'})
    assert headers['Access-Control-Allow-Origin'] == 'http://localhost:5174'
    print('All live API checks passed. Fresh test records were retained; no existing data was removed.')


if __name__ == '__main__':
    main()
