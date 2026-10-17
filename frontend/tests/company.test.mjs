import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import React from 'react';
import { act, create } from 'react-test-renderer';
import { build } from 'rolldown';

let components, directory;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const user = { id: 8, role: 'company', email: 'company@example.test', access_token: 'company-test-token' };
const job = { id: 12, company_id: 8, title: 'Data Intern', posting_date: '2026-01-01', deadline: '2099-12-31', location: 'Sunnyvale', category: 'internship', description: 'Analyze data', salary: null, is_remote: true, skills_json: ['SQL'] };
const application = { id: 20, job_id: 12, job_title: job.title, student_id: 9, student_name: 'Test Student', resume_id: 4, applied_at: '2026-10-01', status: 'pending' };
const event = { id: 7, company_id: 8, company_name: 'Test Company', event_name: 'Meet our team', description: 'Career event', event_date: '2099-12-01', event_time: '12:00:00', location: 'Sunnyvale', eligibility: '', eligible_majors: ['Data Science'], eligible_colleges: [] };
const profile = { user_id: 8, company_name: 'Test Company', location: 'Sunnyvale', description: 'Our team', contact_phone: '', profile_picture_url: '' };
const text = node => typeof node === 'string' ? node : Array.isArray(node) ? node.map(text).join('') : node ? text(node.children) : '';
const button = (root, label) => root.root.findAllByType('button').find(node => text(node.toJSON ? node.toJSON() : { children: node.children }) === label);
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
let requests;
function mock(handler) {
  requests = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = new URL(url).pathname, query = new URL(url).searchParams;
    const request = { path, query, ...options, body: options.body ? JSON.parse(options.body) : undefined };
    requests.push(request);
    if (handler) { const result = handler(request); if (result) return result; }
    if (path === '/companies/me/jobs') return response([job]);
    if (path === '/companies/me/applications') return response([application]);
    if (path === '/companies/8') return response(profile);
    if (path === '/users/me') return response({ email: user.email });
    if (path === '/events') return response([event]);
    if (path === '/events/7') return response(event);
    if (path === '/events/7/registrations') return response([]);
    throw new Error(`Unexpected request: ${path}`);
  };
}
async function render(name, props = {}) {
  let root;
  await act(async () => { root = create(React.createElement(components[name], { user, onBack() {}, ...props })); });
  return root;
}
async function click(root, label) { await act(async () => button(root, label).props.onClick()); }
before(async () => {
  directory = await mkdtemp(resolve('tests/.company-runtime-'));
  await build({ input: ['CompanyDashboard', 'JobPostPage', 'ProfilePage', 'ApplicantsPage', 'EventsPage'].map(name => `src/components/${name}.jsx`),
    external: ['react', 'react/jsx-runtime'], transform: { jsx: 'react-jsx' },
    plugins: [{ name: 'ignore-styles', resolveId(id) { if (id.endsWith('.css')) return '\0empty-style'; }, load(id) { if (id === '\0empty-style') return 'export {};'; } }],
    output: { dir: directory, entryFileNames: '[name].mjs', format: 'esm' } });
  components = Object.fromEntries(await Promise.all(['CompanyDashboard', 'JobPostPage', 'ProfilePage', 'ApplicantsPage', 'EventsPage'].map(async name => [name, (await import(pathToFileURL(`${directory}/${name}.mjs`))).default])));
});
after(async () => { await rm(directory, { recursive: true, force: true }); });

test('company dashboard uses authenticated scoped data and existing navigation', async () => {
  mock(); let page;
  const root = await render('CompanyDashboard', { onNavigate: value => { page = value; } });
  assert.match(text(root.toJSON()), /Welcome back, Test Company/);
  assert.match(text(root.toJSON()), /Test Student/);
  assert.deepEqual(root.root.findAllByType('strong').map(node => node.children), [['1'], ['1'], ['1']]);
  assert(requests.every(request => request.headers.Authorization === 'Bearer company-test-token'));
  const request = requests.find(request => request.path === '/events');
  assert.equal(request.query.get('mine'), 'true'); assert.equal(request.query.get('upcoming'), 'true');
  await click(root, '+ Post a Job'); assert.equal(page, 'post-job');
  await click(root, 'Review Applicants'); assert.equal(page, 'applicants');
  await act(async () => root.unmount());
});

test('job editing preserves PUT payload, ownership boundary and deadline validation', async () => {
  mock(request => request.path === '/jobs/12' ? response(job) : undefined);
  const root = await render('JobPostPage', { existingJob: job });
  await act(async () => root.root.findByProps({ id: 'deadline' }).props.onChange({ target: { value: '2025-01-01' } }));
  await act(async () => root.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.match(text(root.toJSON()), /Deadline must be on or after/); assert.equal(requests.length, 0);
  await act(async () => root.root.findByProps({ id: 'deadline' }).props.onChange({ target: { value: job.deadline } }));
  await act(async () => root.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  assert.equal(requests[0].method, 'PUT'); assert.equal(requests[0].path, '/jobs/12');
  assert.deepEqual(requests[0].body.skills_json, ['SQL']); assert.equal(requests[0].body.company_id, undefined);
  assert.match(text(root.toJSON()), /Job updated successfully/);
  await act(async () => root.unmount());
});

test('company profile saves supported fields and account email through existing endpoints', async () => {
  mock(); const root = await render('ProfilePage');
  await act(async () => root.root.findByProps({ id: 'company_name' }).props.onChange({ target: { value: 'Updated Company' } }));
  await act(async () => root.root.findByProps({ id: 'profile-email' }).props.onChange({ target: { value: 'updated@example.test' } }));
  await act(async () => root.root.findAllByType('form')[0].props.onSubmit({ preventDefault() {} }));
  const writes = requests.filter(request => request.method === 'PUT');
  assert.equal(writes[0].path, '/companies/8'); assert.equal(writes[0].body.company_name, 'Updated Company');
  assert.deepEqual(Object.keys(writes[0].body), ['company_name', 'location', 'description', 'contact_phone', 'profile_picture_url']);
  assert.deepEqual(writes[1].body, { email: 'updated@example.test' });
  assert.match(text(root.toJSON()), /Profile updated successfully/);
  await act(async () => root.unmount());
});

test('applicant filters and status changes retain authenticated request contracts', async () => {
  mock(request => request.path === '/applications/20/status' ? response({ ...application, status: 'reviewed' }) : undefined);
  const root = await render('ApplicantsPage', { initialJobId: 12 });
  assert.equal(requests.find(request => request.path === '/companies/me/applications').query.get('job_id'), '12');
  await act(async () => root.root.findAllByType('select')[2].props.onChange({ target: { value: 'reviewed' } }));
  const write = requests.find(request => request.method === 'PATCH');
  assert.equal(write.path, '/applications/20/status'); assert.deepEqual(write.body, { status: 'reviewed' });
  assert.equal(write.headers.Authorization, 'Bearer company-test-token');
  await act(async () => root.unmount());
});

test('event owner can view attendees and edit without changing eligibility payload', async () => {
  mock(); const root = await render('EventsPage', { initialEventId: 7 });
  await click(root, 'View Registered Students');
  assert(requests.some(request => request.path === '/events/7/registrations'));
  await click(root, 'Edit Event');
  await act(async () => root.root.findByType('form').props.onSubmit({ preventDefault() {} }));
  const write = requests.find(request => request.method === 'PUT');
  assert.equal(write.path, '/events/7'); assert.deepEqual(write.body.eligible_majors, ['Data Science']);
  assert.deepEqual(write.body.eligible_colleges, []); assert.equal(write.body.event_name, event.event_name);
  await act(async () => root.unmount());
  mock(request => request.path === '/events/7' ? response({ ...event, company_id: 99 }) : undefined);
  const other = await render('EventsPage', { initialEventId: 7 });
  assert.equal(button(other, 'Edit Event'), undefined); assert.equal(button(other, 'View Registered Students'), undefined);
  await act(async () => other.unmount());
});

test('failed and empty dashboard data never fabricate counts or applicants', async () => {
  mock(request => request.path === '/companies/me/applications' ? response({ detail: 'Unavailable' }, 503) : request.path === '/companies/me/jobs' ? response([]) : undefined);
  const root = await render('CompanyDashboard', { onNavigate() {} });
  assert.match(text(root.toJSON()), /Could not load applications/);
  assert.match(text(root.toJSON()), /Make your first connection/);
  assert.doesNotMatch(text(root.toJSON()), /Test Student/);
  assert.deepEqual(root.root.findAllByType('strong').map(node => node.children), [['0'], ['1']]);
  await act(async () => root.unmount());
});
