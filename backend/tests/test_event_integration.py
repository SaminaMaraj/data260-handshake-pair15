"""Merged event API regression tests; all writes use isolated in-memory SQLite."""
import os
import sys
import warnings
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'isolated-event-test-key-not-for-production')

from app.auth import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.core import Company, Student, User
from app.models.additional import Event, EventRegistration


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kwargs):
    return 'INTEGER'


@pytest.fixture
def api():
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        users = [User(id=i, email=f'user{i}@example.com', role=role,
                      password_hash='unused', is_active=True)
                 for i, role in [(1, 'company'), (2, 'company'), (3, 'student'),
                                 (4, 'student'), (5, 'student')]]
        db.add_all(users)
        db.flush()
        db.add_all([Company(user_id=1, company_name='Host'),
                    Company(user_id=2, company_name='Other Host'),
                    Student(user_id=3, full_name='Eligible', major='Data Science', college_name='SJSU'),
                    Student(user_id=4, full_name='Ineligible', major='History', college_name='SJSU')])
        db.commit()
        tokens = {u.id: {'Authorization': 'Bearer ' + create_access_token(u)} for u in users}
        def override_db():
            yield db
        app.dependency_overrides[get_db] = override_db
        try:
            with TestClient(app) as client:
                yield client, tokens, db
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def payload(**changes):
    return dict(event_name='Career Day', description='Meet engineers',
                event_date=(date.today() + timedelta(days=10)).isoformat(),
                event_time='12:00:00', location='San Jose', eligibility='Students welcome',
                eligible_majors=['Data Science'], eligible_colleges=['SJSU'], **changes)


def create(api):
    client, tokens, _ = api
    response = client.post('/events', json=payload(), headers=tokens[1])
    assert response.status_code == 201, response.text
    assert response.json()['company_id'] == 1
    return response.json()['id']


def test_routes_and_openapi():
    def api_routes(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            elif hasattr(route, 'original_router'):
                # Newer FastAPI versions retain included routers lazily.
                yield from api_routes(route.original_router.routes)
    routes = list(api_routes(app.routes))
    counts = Counter((m, r.path) for r in routes for m in r.methods)
    assert all(count == 1 for count in counts.values())
    for method, path in [('POST', '/events'), ('GET', '/events'), ('GET', '/events/{event_id}')]:
        route = next(r for r in routes if r.path == path and method in r.methods)
        assert route.endpoint.__module__ == 'app.routers.part_a'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        app.openapi_schema = None
        schema = app.openapi()
    assert not caught, [str(w.message) for w in caught]
    operations = [op['operationId'] for methods in schema['paths'].values()
                  for op in methods.values() if isinstance(op, dict) and 'operationId' in op]
    assert len(operations) == len(set(operations))
    assert 'post' in schema['paths']['/assistant/chat']
    assert len(schema['paths']) == 44


def test_authentication_and_cors(api):
    client, _, _ = api
    for method, path, body in [('GET', '/events', None), ('GET', '/events/search', None),
                              ('GET', '/events/1', None), ('POST', '/events', payload()),
                              ('PUT', '/events/1', payload()),
                              ('GET', '/events/1/registrations', None),
                              ('POST', '/events/1/registrations', {'confirm_eligibility': True}),
                              ('POST', '/event-registrations', {'event_id': 1, 'student_id': 3}),
                              ('GET', '/event-registrations/student/3', None),
                              ('GET', '/event-registrations/1', None)]:
        assert client.request(method, path, json=body).status_code == 401
    assert client.get('/events', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        response = client.options('/events', headers={'Origin': origin,
            'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'})
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == origin
        assert response.headers['access-control-allow-credentials'] == 'true'


def test_creation_update_detail_and_filters(api):
    client, tokens, db = api
    eid = create(api)
    assert client.post('/events', json=payload(), headers=tokens[3]).status_code == 403
    assert client.post('/events', json={**payload(), 'company_id': 2}, headers=tokens[1]).status_code == 422
    assert client.post('/events', json={**payload(), 'event_date': '2000-01-01'}, headers=tokens[1]).status_code == 422
    assert client.put(f'/events/{eid}', json=payload(), headers=tokens[2]).status_code == 403
    assert client.put(f'/events/{eid}', json=payload(), headers=tokens[3]).status_code == 403
    assert client.put(f'/events/{eid}', json={**payload(), 'location': 'Cupertino'}, headers=tokens[1]).status_code == 200
    detail = client.get(f'/events/{eid}', headers=tokens[3]).json()
    assert detail['eligible'] and not detail['registered'] and detail['location'] == 'Cupertino'
    assert not client.get(f'/events/{eid}', headers=tokens[4]).json()['eligible']
    assert client.get('/events?mine=true', headers=tokens[2]).json() == []
    assert client.get('/events?mine=true', headers=tokens[3]).status_code == 403
    assert client.get('/events?registered=true', headers=tokens[1]).status_code == 403
    assert len(client.get('/events?q=Career', headers=tokens[3]).json()) == 1
    assert client.get('/events?q=absent', headers=tokens[3]).json() == []
    row = db.get(Event, eid)
    row.event_date = date.today() - timedelta(days=1)
    db.commit()
    assert client.get('/events', headers=tokens[3]).json() == []
    assert len(client.get('/events?upcoming=false', headers=tokens[3]).json()) == 1
    assert not client.get(f'/events/{eid}', headers=tokens[3]).json()['eligible']


def test_search_and_legacy_eligibility_storage(api):
    client, tokens, db = api
    eid = create(api)
    for query in ('q=engineers', 'location=San', 'q=Students', f'from_date={date.today().isoformat()}'):
        response = client.get('/events/search?' + query, headers=tokens[3])
        assert response.status_code == 200, response.text
        assert [e['id'] for e in response.json()] == [eid]
        assert 'created_at' in response.json()[0]
    assert client.get('/events/search?location=absent', headers=tokens[3]).json() == []
    row = db.get(Event, eid)
    row.eligibility = 'All students welcome'
    db.commit()
    detail = client.get(f'/events/{eid}', headers=tokens[4]).json()
    assert detail['eligibility'] == 'All students welcome'
    assert detail['eligible_majors'] == [] and detail['eligible']
    row.eligibility = None
    db.commit()
    assert client.get(f'/events/{eid}', headers=tokens[4]).json()['eligibility'] == ''


@pytest.mark.parametrize('legacy', [False, True])
def test_registration_and_history_authorization(api, legacy):
    client, tokens, db = api
    eid = create(api)
    path = '/event-registrations' if legacy else f'/events/{eid}/registrations'
    def body(sid):
        return {'event_id': eid, 'student_id': sid} if legacy else {'confirm_eligibility': True}
    assert client.post(path, json=body(1), headers=tokens[1]).status_code == 403
    assert client.post(path, json=body(4), headers=tokens[4]).status_code == 403
    assert client.post(path, json=body(5), headers=tokens[5]).status_code in (403, 404)
    if legacy:
        assert client.post(path, json=body(4), headers=tokens[3]).status_code == 403
    else:
        assert client.post(path, json={'confirm_eligibility': False}, headers=tokens[3]).status_code == 422
    response = client.post(path, json=body(3), headers=tokens[3])
    assert response.status_code == 201, response.text
    assert client.post(path, json=body(3), headers=tokens[3]).status_code == 409
    other_path = f'/events/{eid}/registrations' if legacy else '/event-registrations'
    other_body = {'confirm_eligibility': True} if legacy else {'event_id': eid, 'student_id': 3}
    assert client.post(other_path, json=other_body, headers=tokens[3]).status_code == 409
    assert client.get(f'/events/{eid}', headers=tokens[3]).json()['registered']
    assert len(client.get('/events?registered=true', headers=tokens[3]).json()) == 1
    assert not client.get(f'/events/{eid}', headers=tokens[4]).json()['registered']
    for uid in (2, 3):
        assert client.get(f'/events/{eid}/registrations', headers=tokens[uid]).status_code == 403
    attendees = client.get(f'/events/{eid}/registrations', headers=tokens[1]).json()
    assert attendees[0]['student']['user_id'] == 3
    history = client.get('/event-registrations/student/3', headers=tokens[3]).json()
    assert len(history) == 1 and history[0]['event_id'] == eid
    for uid in (1, 4):
        assert client.get('/event-registrations/student/3', headers=tokens[uid]).status_code == 403
    rid = history[0]['id']
    for uid in (1, 3):
        assert client.get(f'/event-registrations/{rid}', headers=tokens[uid]).status_code == 200
    for uid in (2, 4):
        assert client.get(f'/event-registrations/{rid}', headers=tokens[uid]).status_code == 403
    assert len(db.scalars(select(EventRegistration)).all()) == 1


@pytest.mark.parametrize('legacy', [False, True])
def test_closed_event_cannot_be_registered(api, legacy):
    client, tokens, db = api
    eid = create(api)
    row = db.get(Event, eid)
    row.event_date = date.today() - timedelta(days=1)
    db.commit()
    path = '/event-registrations' if legacy else f'/events/{eid}/registrations'
    body = {'event_id': eid, 'student_id': 3} if legacy else {'confirm_eligibility': True}
    assert client.post(path, json=body, headers=tokens[3]).status_code == 403
    assert not db.scalars(select(EventRegistration)).all()


def test_both_preference_routes_remain_reachable(api):
    client, tokens, _ = api
    body = {'preferred_city': 'San Jose', 'preferred_category': 'internship',
            'minimum_salary': '1000.00', 'preferred_skills_json': ['SQL'], 'remote_only': True}
    response = client.put('/students/me/preferences', headers=tokens[3], json=body)
    assert response.status_code == 200, response.text
    assert client.get('/students/me/preferences', headers=tokens[3]).json() == body
    response = client.get('/students/3/preferences', headers=tokens[3])
    assert response.status_code == 200
    assert response.json()['preferred_city'] == 'San Jose'
    assert client.put('/students/3/preferences', headers=tokens[3], json=body).status_code == 200


def test_existing_part_a_workflows_in_isolation(api, tmp_path, monkeypatch):
    """Run the existing broad HTTP smoke suite without touching the real DB/uploads."""
    import importlib.util
    from app.routers import part_a

    spec = importlib.util.spec_from_file_location(
        'part_a_smoke', Path(__file__).with_name('run3_part_a_smoke.py'))
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    smoke.client.close()
    monkeypatch.setattr(smoke, 'client', api[0])
    monkeypatch.setattr(part_a, 'UPLOADS', tmp_path)
    smoke.main()
    assert smoke.checks > 70


def test_assistant_confirmation_gate_preserves_saved_items(api, monkeypatch):
    from app.assistant import tools
    from app.assistant.confirm import confirm_action
    from app.models.additional import SavedItem

    _, _, db = api
    eid = create(api)
    # A separate session on the isolated test engine keeps tool-owned closing safe.
    monkeypatch.setattr(tools, 'SessionLocal', lambda: Session(db.get_bind()))
    for value in (False, None, 'true', 1):
        assert not confirm_action('save_job_or_event', {'confirmed': value})
        result = tools.save_job_or_event(3, event_id=eid, confirmed=value)
        assert 'Confirmation required' in result
        assert not db.scalars(select(SavedItem)).all()
    assert confirm_action('save_job_or_event', {'confirmed': True})
    assert 'Saved successfully' in tools.save_job_or_event(3, event_id=eid, confirmed=True)
    assert 'already saved' in tools.save_job_or_event(3, event_id=eid, confirmed=True)
    rows = db.scalars(select(SavedItem)).all()
    assert len(rows) == 1 and rows[0].student_id == 3 and rows[0].event_id == eid
