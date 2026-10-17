"""Authenticated assistant integration, using isolated DB fixtures and scripted LLMs."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from test_event_integration import api, create
from app.assistant.pending import PendingAction
from app.assistant.tools import execute_tool, save_job_or_event
from app.assistant.confirm import confirm_action
from app.assistant.client import OllamaClient
from app.models.additional import SavedItem


def llm_save(eid, **extra):
    return {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'save-call', 'function': {
        'name': 'save_job_or_event', 'arguments': {'event_id': eid, 'student_id': 999, 'confirmed': True, **extra}}}]}


def pending(api):
    client, tokens, db = api
    eid = create(api)
    with patch.object(OllamaClient, 'complete', return_value=llm_save(eid)):
        response = client.post('/assistant/chat', headers=tokens[3], json={'message': 'Save this event', 'student_id': 4})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'pending_confirmation'
    assert not db.scalars(select(SavedItem)).all()
    return data


def test_jwt_and_roles(api):
    client, tokens, _ = api
    for path, body in [('/assistant/chat', {'message': 'hi'}), ('/assistant/confirm', {'pending_id': 'x', 'approve': True})]:
        assert client.post(path, json=body).status_code == 401
        assert client.post(path, headers={'Authorization': 'Bearer invalid'}, json=body).status_code == 401
        assert client.post(path, headers=tokens[1], json=body).status_code == 403


def test_history_and_authenticated_student_context(api):
    client, tokens, _ = api
    calls = []
    def complete(self, messages, tools):
        calls.append(messages.copy())
        return {'role': 'assistant', 'content': 'Actual scripted answer'}
    with patch.object(OllamaClient, 'complete', complete):
        first = client.post('/assistant/chat', headers=tokens[3], json={'message': 'hello'}).json()
        second = client.post('/assistant/chat', headers=tokens[3], json={'message': 'follow up', 'conversation': first['conversation']}).json()
    assert first['answer'] == 'Actual scripted answer'
    assert [m['content'] for m in second['conversation'] if m['role'] == 'user'] == ['hello', 'follow up']
    assert calls[1][1:-1] == first['conversation']
    read = {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'get_student_preferences', 'arguments': {'student_id': 4}}}]}
    with patch.object(OllamaClient, 'complete', side_effect=[read, {'role': 'assistant', 'content': 'done'}]), patch('app.assistant.loop.execute_tool', return_value='{}') as tool:
        client.post('/assistant/chat', headers=tokens[3], json={'message': 'my preferences', 'student_id': 4})
        assert tool.call_args.kwargs['arguments']['student_id'] == 3


def test_approval_and_replay(api):
    client, tokens, db = api
    data = pending(api)
    body = {'pending_id': data['pending_id'], 'approve': True}
    assert client.post('/assistant/confirm', headers=tokens[4], json=body).status_code == 409
    response = client.post('/assistant/confirm', headers=tokens[3], json=body)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'completed'
    assert response.json()['conversation'][:len(data['conversation'])] == data['conversation']
    assert client.post('/assistant/confirm', headers=tokens[3], json=body).status_code == 409
    rows = db.scalars(select(SavedItem)).all()
    assert len(rows) == 1 and rows[0].student_id == 3


def test_rejection(api):
    client, tokens, db = api
    data = pending(api)
    response = client.post('/assistant/confirm', headers=tokens[3], json={'pending_id': data['pending_id'], 'approve': False})
    assert response.json()['status'] == 'cancelled'
    assert not db.scalars(select(SavedItem)).all()
    assert client.post('/assistant/confirm', headers=tokens[3], json={'pending_id': data['pending_id'], 'approve': True}).status_code == 409


def test_expired_invalid_and_injected_confirmation(api):
    client, tokens, db = api
    data = pending(api)
    for body in [{'pending_id': 'invalid', 'approve': True}, {'pending_id': data['pending_id'], 'approve': True, 'event_id': 99}, {'approve': True}, {'pending_id': data['pending_id'], 'approve': 'true'}]:
        assert client.post('/assistant/confirm', headers=tokens[3], json=body).status_code in (409, 422)
    row = db.scalar(select(PendingAction))
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post('/assistant/confirm', headers=tokens[3], json={'pending_id': data['pending_id'], 'approve': True}).status_code == 409
    assert not db.scalars(select(SavedItem)).all()


def test_tools_cannot_bypass_confirmation(api):
    _, _, db = api
    eid = create(api)
    assert 'required' in execute_tool('save_job_or_event', {'student_id': 3, 'event_id': eid, 'confirmed': True})
    assert 'required' in save_job_or_event(3, event_id=eid, confirmed=True)
    assert not confirm_action('save_job_or_event', {'confirmed': True}, auto_approve=True)
    assert not db.scalars(select(SavedItem)).all()


def test_followup_does_not_execute_old_write(api):
    client, tokens, db = api
    data = pending(api)
    with patch.object(OllamaClient, 'complete', return_value={'role': 'assistant', 'content': 'It remains pending.'}):
        result = client.post('/assistant/chat', headers=tokens[3], json={'message': 'tell me more', 'conversation': data['conversation']})
    assert result.status_code == 200
    assert not db.scalars(select(SavedItem)).all()
    tool = next(m for m in data['conversation'] if m['role'] == 'tool')
    assert tool['tool_call_id'] == 'save-call'


def test_service_error_and_bad_arguments(api):
    client, tokens, db = api
    with patch.object(OllamaClient, 'complete', return_value={'error': True}):
        assert client.post('/assistant/chat', headers=tokens[3], json={'message': 'hello'}).status_code == 503
    eid = create(api)
    for extra in [{'job_id': 1}, {'event_id': -1}, {'event_id': '1'}, {'unexpected': True}]:
        with patch.object(OllamaClient, 'complete', return_value=llm_save(eid, **extra)):
            assert client.post('/assistant/chat', headers=tokens[3], json={'message': 'save'}).status_code == 422
    assert not db.scalars(select(PendingAction)).all()


def test_pending_survives_new_session(api):
    from sqlalchemy.orm import Session
    from app.assistant.pending import resolve_pending
    _, _, db = api
    data = pending(api)
    with Session(db.get_bind()) as another_session:
        result = resolve_pending(another_session, 3, data['pending_id'], True)
        assert result['status'] == 'completed'
    assert len(db.scalars(select(SavedItem)).all()) == 1


def test_concurrent_confirmation_claim_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.database import Base
    from app.models.core import User, Student, Company
    from app.models.additional import Event
    from app.assistant.pending import create_pending, resolve_pending
    from datetime import date, time

    engine = create_engine(f'sqlite:///{tmp_path / "approvals.db"}')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([User(id=1, email='host@example.com', role='company', password_hash='unused'),
                    User(id=3, email='student@example.com', role='student', password_hash='unused')])
        db.flush()
        db.add_all([Company(user_id=1, company_name='Host'), Student(user_id=3, full_name='Student')])
        db.flush()
        db.add(Event(id=1, company_id=1, event_name='Event', description='Fixture',
                     event_date=date.today(), event_time=time(12), location='Test'))
        db.commit()
        pending_id = create_pending(db, 3, {'event_id': 1}, [], 'Save?')['pending_id']
    barrier = Barrier(2)
    def approve():
        with Session(engine) as db:
            barrier.wait()
            try:
                return resolve_pending(db, 3, pending_id, True)['status']
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: approve(), range(2)))
    assert outcomes.count('completed') == 1 and outcomes.count(409) == 1
    with Session(engine) as db:
        assert len(db.scalars(select(SavedItem)).all()) == 1
    engine.dispose()
