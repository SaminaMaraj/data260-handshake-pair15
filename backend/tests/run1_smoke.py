"""Live Run 1 integration checks. Adds test data and never deletes data."""
import secrets
import uuid
from week2_smoke import request


def account(role):
    credentials = {'email': f'run1-{uuid.uuid4().hex[:12]}@example.com', 'password': secrets.token_urlsafe(24)}
    user, _ = request('POST', '/users/register', 201, {**credentials, 'role': role})
    login, _ = request('POST', '/users/login', 200, credentials)
    return user['id'], login['access_token']


def main():
    sid, st = account('student')
    sid2, st2 = account('student')
    cid, ct = account('company')
    cid2, ct2 = account('company')
    student = {'full_name': 'Run 1 Student', 'college_name': 'Test College', 'date_of_birth': '2002-04-01',
               'graduation_year': 2027, 'cgpa': '3.75', 'skills_json': ['Python', 'SQL'], 'phone': '123'}
    company = {'company_name': 'Run 1 Company', 'location': 'Sunnyvale', 'description': 'Test profile'}
    for resource, uid, token, wrong, other_id, other_token, body in [
        ('students', sid, st, ct, sid2, st2, student), ('companies', cid, ct, st, cid2, ct2, company)]:
        path = f'/{resource}/{uid}'
        request('GET', path, 404, token=token)
        request('PUT', path, 404, body, token)
        request('POST', f'/{resource}', 401, {**body, 'user_id': uid})
        request('PUT', path, 401, body)
        request('PUT', path, 401, body, 'invalid')
        request('PUT', path, 403, body, wrong)
        request('POST', f'/{resource}', 403, {**body, 'user_id': other_id}, token)
        request('POST', f'/{resource}', 201, {**body, 'user_id': uid}, token)
        request('PUT', path, 403, body, other_token)
        updated = {**body, ('full_name' if resource == 'students' else 'company_name'): 'Updated Run 1 Name'}
        request('PUT', path, 200, updated, token)
        actual, _ = request('GET', path, 200, token=token)
        for key, value in updated.items(): assert actual[key] == value, key
        request('PUT', path, 422, {**body, ('full_name' if resource == 'students' else 'company_name'): ' '}, token)
        request('PUT', path, 422, {**body, ('full_name' if resource == 'students' else 'company_name'): 'x' * 256}, token)
    request('PUT', f'/students/{sid}', 422, {**student, 'graduation_year': 9999}, st)
    request('PUT', f'/students/{sid}', 422, {**student, 'cgpa': '123.456'}, st)
    request('PUT', f'/students/{sid}', 422, {**student, 'skills_json': 'bad'}, st)
    job = {'company_id': cid, 'title': 'Run 1 persisted job', 'posting_date': '2026-10-03',
           'deadline': '2026-12-01', 'location': 'Sunnyvale', 'description': 'Integration test',
           'category': 'internship', 'is_remote': True, 'salary': '1234.50', 'skills_json': ['SQL']}
    request('POST', '/jobs', 401, job)
    request('POST', '/jobs', 403, job, st)
    request('POST', '/jobs', 403, job, ct2)
    request('POST', '/jobs', 409, {**job, 'company_id': cid2}, ct2)
    request('POST', '/jobs', 422, {**job, 'category': 'invalid'}, ct)
    request('POST', '/jobs', 422, {**job, 'deadline': '2026-01-01'}, ct)
    request('POST', '/jobs', 422, {**job, 'salary': '-1'}, ct)
    created, _ = request('POST', '/jobs', 201, job, ct)
    actual, _ = request('GET', f'/jobs/{created["id"]}', 200, token=ct)
    for key, value in job.items(): assert actual[key] == value, key
    _, headers = request('OPTIONS', f'/students/{sid}', 200, headers={
        'Origin': 'http://localhost:5174', 'Access-Control-Request-Method': 'PUT',
        'Access-Control-Request-Headers': 'authorization,content-type'})
    assert headers['Access-Control-Allow-Origin'] == 'http://localhost:5174'
    print('Run 1 checks passed; all new test data retained.')


if __name__ == '__main__':
    main()
