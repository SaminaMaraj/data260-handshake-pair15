import assert from 'node:assert/strict';
import { filterJobs, emptyFilters } from '../src/components/jobFilters.js';
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
