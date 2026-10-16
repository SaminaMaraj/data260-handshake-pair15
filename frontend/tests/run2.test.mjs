import assert from 'node:assert/strict';
import { filterJobs, emptyFilters, jobSearchPath, companyJobs } from '../src/components/jobFilters.js';
import { apiRequest } from '../src/api.js';
const jobs = [
  { id: 1, title: 'SQL Intern', location: 'Sunnyvale', category: 'internship', is_remote: true },
  { id: 2, title: 'SQL Analyst', location: 'Cupertino', category: 'full_time', is_remote: false },
];
assert.deepEqual(filterJobs(jobs, { ...emptyFilters, title: ' sQl ', location: 'SUNNY', category: 'internship', remote: 'remote' }).map(j => j.id), [1]);
assert.deepEqual(filterJobs(jobs, { ...emptyFilters, title: 'missing' }), []);
assert.deepEqual(filterJobs(jobs, { ...emptyFilters, remote: 'onsite' }).map(j => j.id), [2]);
assert.equal(filterJobs(jobs, emptyFilters).length, 2);
assert.deepEqual(filterJobs([], emptyFilters), []);
console.log('PASS filters: combined, case-insensitive, zero results, onsite/remote, clear, empty list');
let reset = false;
globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => { throw new Error('non-JSON'); } });
await assert.rejects(apiRequest('/applications', { onUnauthorized: () => { reset = true; } }), /Request failed/);
assert.equal(reset, true);
globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ detail: 'Student account required' }) });
await assert.rejects(apiRequest('/applications'), /Student account required/);
globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: 'You have already applied to this job.' }) });
await assert.rejects(apiRequest('/applications'), /already applied/);
globalThis.fetch = async () => { throw new Error('offline'); };
await assert.rejects(apiRequest('/jobs'), /Could not connect/);
console.log('PASS API helper: 401 reset, non-JSON error, 403, duplicate error, network error');

assert.equal(jobSearchPath(emptyFilters), '/jobs/search');
assert.equal(jobSearchPath({ ...emptyFilters, location: ' Palo Alto & Sunnyvale ', category: 'internship', remote: 'onsite' }),
  '/jobs/search?location=Palo+Alto+%26+Sunnyvale&category=internship&is_remote=false');
assert.equal(jobSearchPath({ ...emptyFilters, title: 'SQL', remote: 'remote' }), '/jobs/search?q=SQL&is_remote=true');
assert.deepEqual(companyJobs([{id:1,company_id:2},{id:3,company_id:1},{id:2,company_id:2}],2).map(j=>j.id),[2,1]);
assert.deepEqual(companyJobs(jobs,999),[]);
console.log('PASS server search query encoding, onsite=false, title/company search query, company ownership and sorting');

let captured;
globalThis.fetch = async (url, options) => { captured = { url, options }; return { ok: true, status: 201, json: async () => ({ id: 1 }) }; };
await apiRequest('/users/login', { method: 'POST', body: { email: 'test@example.com' } });
assert.equal(captured.options.headers['Content-Type'], 'application/json');
assert.equal(captured.options.body, '{"email":"test@example.com"}');
const upload = new FormData(); upload.append('file', new Blob(['test'], {type: 'application/pdf'}), 'test.pdf');
await apiRequest('/resumes', { method: 'POST', token: 'test-token', body: upload });
assert.equal(captured.options.body, upload);
assert.equal(captured.options.headers['Content-Type'], undefined);
assert.equal(captured.options.headers.Authorization, 'Bearer test-token');
console.log('PASS JSON requests and multipart uploads preserve payload and authorization');
