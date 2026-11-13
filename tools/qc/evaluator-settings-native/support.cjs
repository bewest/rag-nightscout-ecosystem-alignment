'use strict';
const assert = require('node:assert/strict');
const ANCHORS = Object.freeze({
  core: 'debcc2c7a44fb812b342d0e524ff0611045094d1',
  deploy: '2e9afbb6906441e096e9e86e892cc44073d5b0ae',
  suppliedImage: 'sha256:e0cadd35872c43fa63602d6c8945952383df462aef69d72a5465378b0e20cd77',
  suppliedBindingPrefix: '56183'
});
const quote = value => { assert.match(value, /^[a-z][a-z0-9_]{0,62}$/); return '"' + value + '"'; };
const PHASES = Object.freeze(['actual-role-boot', 'fresh-owner-policy-A-B', 'RLS-refusal-restoration',
  'SELECT-refusal-restoration', 'write-grant-refusal-restoration', 'catalogue-refusal-restoration',
  'direct-check-bound-FIFO-context', 'exact-owned-backend-termination-recovery', 'queued-and-active-shutdown', 'owned-cleanup']);
async function waitFor (label, check, ms = 1500) {
  const end = performance.now() + ms;
  while (performance.now() < end) {
    const value = await check(); if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw Object.assign(new Error(label), { code: 'NATIVE_CONDITION_TIMEOUT', phase: label });
}
function exactBackend (row, role) {
  assert.equal(row.role, role); assert(Number.isSafeInteger(row.pid) && row.pid > 0);
  assert.equal(typeof row.birth, 'string'); assert(row.birth.length > 0);
  return [row.pid, row.birth, role];
}
const TERMINATE = `SELECT pg_terminate_backend(pid) AS terminated FROM pg_stat_activity
  WHERE pid=$1 AND backend_start=$2::timestamptz AND usename=$3 AND datname=current_database()`;
function observeClients (pg, role, scope, jobs) {
  const original = pg.Client.prototype.connect;
  const live = new Map(), starts = [], violations = []; let peakDirect = 0, peakTotal = 0;
  pg.Client.prototype.connect = function (...args) {
    if (this.user === role) {
      const pooled = this.connectionParameters.application_name === 'nightscout-display-settings';
      const job = jobs.getStore();
      if (!pooled && job) { starts.push(job.id); if (scope.currentTenant() !== job.tenant) violations.push(job.id); }
      const connected = () => {
        live.set(this, { pooled });
        peakDirect = Math.max(peakDirect, [...live.values()].filter(value => !value.pooled).length);
        peakTotal = Math.max(peakTotal, live.size);
      };
      this.once('connect', connected); this.once('end', () => live.delete(this));
    }
    return original.apply(this, args);
  };
  return { starts, violations, live, snapshot: () => ({ peakDirect, peakTotal, live: live.size }),
    restore () { pg.Client.prototype.connect = original; } };
}
function writeGrantRefusal (error) {
  return error instanceof Error && error.name === 'Error' && error.code === undefined &&
    error.message === 'unsafe settings scope' && error.cause === undefined && error.cleanupError === undefined;
}
async function expectRefusal (operation, expected) {
  assert.notEqual(expected, undefined, 'Every mutation requires an explicit refusal matcher');
  return assert.rejects(operation, expected);
}
// Only the reused fixture's admin instance is bounded; application reader SQL
// and its reviewed timeout/cadence are untouched. Install before open resumes.
function boundAdmin (client) {
  const original = client.query.bind(client); let configured;
  client.query = function (input, ...args) {
    if (!configured) configured = original({ text: "SET statement_timeout='3s'; SET lock_timeout='1500ms'; SET idle_in_transaction_session_timeout='10s'", query_timeout: 1500 });
    const query = typeof input === 'string' ? { text: input, query_timeout: 3000 } : { ...input, query_timeout: 3000 };
    return configured.then(() => original(query, ...args));
  };
}
module.exports = { ANCHORS, PHASES, quote, waitFor, exactBackend, TERMINATE, observeClients, boundAdmin, writeGrantRefusal, expectRefusal };
