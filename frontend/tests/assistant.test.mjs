import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { build } from 'rolldown';

let AssistantChat, directory;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const user = { id: 3, role: 'student', access_token: 'test-jwt' };
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const text = node => typeof node === 'string' ? node : Array.isArray(node) ? node.map(text).join('') : node ? text(node.children) : '';
const buttons = root => root.root.findAllByType('button');
const findButton = (root, label) => buttons(root).find(node => node.children.some(child => child === label));
async function render(props = {}) {
  let root;
  await act(async () => { root = create(React.createElement(AssistantChat, { user, ...props })); });
  return root;
}
async function send(root, message) {
  await act(async () => root.root.findByType('textarea').props.onChange({ target: { value: message } }));
  await act(async () => root.root.findByType('form').props.onSubmit({ preventDefault() {} }));
}
before(async () => {
  directory = await mkdtemp(resolve('tests/.assistant-runtime-'));
  await build({ input: 'src/components/AssistantChat.jsx', external: ['react', 'react/jsx-runtime'], transform: { jsx: 'react-jsx' },
    plugins: [{ name: 'ignore-styles', resolveId(id) { if (id.endsWith('.css')) return '\0empty-style'; }, load(id) { if (id === '\0empty-style') return 'export {};'; } }],
    output: { file: `${directory}/component.mjs`, format: 'esm' } });
  AssistantChat = (await import(pathToFileURL(`${directory}/component.mjs`))).default;
});
after(async () => { await rm(directory, { recursive: true, force: true }); });

test('JWT, actual answer, canonical tool history, and clear', async () => {
  const requests = [];
  const history = [{ role: 'user', content: 'hello' }, { role: 'assistant', content: '', tool_calls: [{ id: 'read', function: { name: 'search_jobs', arguments: {} } }] }, { role: 'tool', tool_call_id: 'read', content: '[]' }, { role: 'assistant', content: 'Actual backend answer' }];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options, body: JSON.parse(options.body) });
    return response({ answer: 'Actual backend answer', conversation: history, status: 'completed' });
  };
  const root = await render();
  await send(root, 'hello');
  assert.match(text(root.toJSON()), /Actual backend answer/);
  assert.equal(requests[0].headers.Authorization, 'Bearer test-jwt');
  assert.deepEqual(requests[0].body, { message: 'hello', conversation: [] });
  await send(root, 'follow up');
  assert.deepEqual(requests[1].body.conversation, history);
  assert.equal(requests[1].body.message, 'follow up');
  await act(async () => findButton(root, 'Clear Conversation').props.onClick());
  assert.doesNotMatch(text(root.toJSON()), /Actual backend answer/);
  await send(root, 'new chat');
  assert.deepEqual(requests[2].body.conversation, []);
  await act(async () => root.unmount());
});

for (const approve of [true, false]) {
  test(`explicit ${approve ? 'Yes' : 'No'} sends only token and decision`, async () => {
    const requests = [];
    globalThis.fetch = async (url, options) => {
      const body = JSON.parse(options.body); requests.push({ url, options, body });
      return response(url.endsWith('/chat')
        ? { answer: 'Save event 10?', status: 'pending_confirmation', pending_id: 'opaque-id', conversation: [{ role: 'assistant', content: 'Save event 10?' }] }
        : { answer: approve ? 'Saved by backend' : 'Cancelled by backend', status: approve ? 'completed' : 'cancelled', conversation: [{ role: 'assistant', content: 'decision' }] });
    };
    const root = await render();
    await send(root, 'save this');
    assert.equal(requests.length, 1);
    assert.equal(root.root.findByType('textarea').props.disabled, true);
    await act(async () => findButton(root, approve ? 'Yes' : 'No').props.onClick());
    assert.deepEqual(requests[1].body, { pending_id: 'opaque-id', approve });
    assert.equal(requests[1].options.headers.Authorization, 'Bearer test-jwt');
    assert.match(text(root.toJSON()), approve ? /Saved by backend/ : /Cancelled by backend/);
    assert.equal(findButton(root, 'Yes'), undefined);
    await act(async () => root.unmount());
  });
}

test('loading locks duplicate requests and connection failure preserves draft', async () => {
  let reject, count = 0;
  globalThis.fetch = () => { count++; return new Promise((_, no) => { reject = no; }); };
  const root = await render();
  await act(async () => root.root.findByType('textarea').props.onChange({ target: { value: 'hello' } }));
  let request;
  await act(async () => { request = root.root.findByType('form').props.onSubmit({ preventDefault() {} }); });
  assert.match(text(root.toJSON()), /Waiting for the assistant/);
  await act(async () => root.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.equal(count, 1);
  assert.equal(findButton(root, 'Clear Conversation').props.disabled, true);
  await act(async () => { reject(new Error('offline')); await request; });
  assert.match(text(root.toJSON()), /Could not connect/);
  assert.equal(root.root.findByType('textarea').props.value, 'hello');
  await act(async () => root.unmount());
});

test('confirmation locks repeat clicks and invalid confirmation can recover', async () => {
  let resolveDecision, count = 0;
  globalThis.fetch = async url => {
    count++;
    if (url.endsWith('/chat')) return response({ answer: 'Approve?', status: 'pending_confirmation', pending_id: 'p', conversation: [] });
    return new Promise(resolve => { resolveDecision = resolve; });
  };
  const root = await render();
  await send(root, 'save');
  const yes = findButton(root, 'Yes').props.onClick;
  let request;
  await act(async () => { request = yes(); });
  assert.equal(findButton(root, 'Yes').props.disabled, true);
  assert.equal(findButton(root, 'No').props.disabled, true);
  await act(async () => yes());
  assert.equal(count, 2);
  await act(async () => { resolveDecision(response({ detail: 'Expired approval' }, 409)); await request; });
  assert.match(text(root.toJSON()), /Expired approval/);
  assert.equal(findButton(root, 'Yes'), undefined);
  assert.equal(root.root.findByType('textarea').props.disabled, false);
  await act(async () => root.unmount());
});

test('backend errors and expired JWT are visible and propagated', async () => {
  let unauthorized = false;
  globalThis.fetch = async () => response({ detail: 'Session expired' }, 401);
  const root = await render({ onUnauthorized: () => { unauthorized = true; } });
  await send(root, 'hello');
  assert.equal(unauthorized, true);
  assert.match(text(root.toJSON()), /Session expired/);
  await act(async () => root.unmount());
});
