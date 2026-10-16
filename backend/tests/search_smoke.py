"""Live search regression checks; uses existing records without changing data."""
import ast
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import create_access_token
from app.database import SessionLocal
from app.models.core import User
from sqlalchemy import select
from week2_smoke import BASE, request


def main():
    source = ast.parse((Path(__file__).resolve().parents[1] / 'app/routers/core.py').read_text())
    paths = [d.args[0].value for node in source.body if isinstance(node, ast.FunctionDef)
             for d in node.decorator_list if isinstance(d, ast.Call)
             and isinstance(d.func, ast.Attribute) and d.func.attr == 'get']
    assert paths.index('/jobs/search') < paths.index('/jobs/{job_id}')
    with urlopen(BASE + '/openapi.json', timeout=10) as response:
        schema = json.load(response)
    search = schema['paths']['/jobs/search']['get']
    assert {p['name'] for p in search['parameters']} == {'q', 'location', 'category', 'is_remote'}
    assert search['security']
    for token in (None, 'invalid'):
        request('GET', '/jobs/search', 401, token=token)
    with SessionLocal() as db:
        users = [db.scalar(select(User).where(User.role == role, User.is_active.is_(True)))
                 for role in ('student', 'company')]
        assert all(users), 'Run existing smoke scripts first to create test accounts'
        tokens = [create_access_token(user) for user in users]
    for token in tokens:
        jobs, _ = request('GET', '/jobs', 200, token=token)
        assert jobs, 'Need existing jobs to verify search'
        filters = [{}, {'location': 'sUnNy'}, {'location': 'Cupertino'}, {'location': 'Palo Alto'},
                   {'location': 'no-such-city-search-regression'}, {'category': 'internship'},
                   {'is_remote': 'true'}, {'is_remote': 'false'},
                   {'location': 'Sunnyvale', 'category': 'internship', 'is_remote': 'true'},
                   {'location': '', 'category': ''}]
        for query in filters:
            result, _ = request('GET', '/jobs/search?' + urlencode(query), 200, token=token)
            expected = [job for job in jobs
                        if (not query.get('location') or query['location'].lower() in job['location'].lower())
                        and (not query.get('category') or job['category'] == query['category'])
                        and ('is_remote' not in query or job['is_remote'] == (query['is_remote'] == 'true'))]
            assert result == sorted(expected, key=lambda job: job['id'], reverse=True), query
        request('GET', '/jobs/search?is_remote=invalid', 422, token=token)
    print('Search smoke PASS: route order, OpenAPI security, both roles, filters, sorting and validation; no data changed.')


if __name__ == '__main__':
    main()
