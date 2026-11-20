'use strict';
// Init-container gate: exit 0 once every named Job in this namespace is Complete.
// `<job>:ready` is released as soon as the Job has a Ready Pod, or is Complete.
// The primer completes only after the operator has
// exported tenant observations. Waiting for its completion would deadlock export.
// Exits 2 as soon as one is Failed and 3 at the deadline. Uses only the Pod's projected
// ServiceAccount token (namespace-scoped `get jobs`). It never writes to the cluster.
//   node -e "$(cat wait-for-jobs.js)" <job> [<job>...]
// Environment: NS_WAIT_DEADLINE_SECONDS (default 1800), NS_WAIT_API (test override).
const fs = require('node:fs');
const names = process.argv.slice(1);
const dir = process.env.NS_WAIT_DIR || '/var/run/secrets/kubernetes.io/serviceaccount';
const api = new URL(process.env.NS_WAIT_API || 'https://kubernetes.default.svc');
const transport = require(api.protocol === 'http:' ? 'node:http' : 'node:https');
const read = f => fs.readFileSync(dir + '/' + f, 'utf8').trim();
const deadline = Date.now() + 1000 * Number(process.env.NS_WAIT_DEADLINE_SECONDS || 1800);
if (names.length === 0) { console.error('WAIT_NO_JOBS'); process.exit(64); }
function job(name) {
  return new Promise((resolve, reject) => {
    const request = transport.request({
      hostname: api.hostname, port: api.port || undefined, protocol: api.protocol, timeout: 5000,
      path: '/apis/batch/v1/namespaces/' + read('namespace') + '/jobs/' + name,
      headers: { authorization: 'Bearer ' + read('token') },
      ...(api.protocol === 'https:' ? { ca: fs.readFileSync(dir + '/ca.crt') } : {}),
    }, response => {
      let body = '';
      response.on('data', chunk => { body += chunk; });
      response.on('end', () => response.statusCode === 200 ? resolve(JSON.parse(body)) : reject(new Error('HTTP_' + response.statusCode)));
    });
    request.on('timeout', () => request.destroy(new Error('TIMEOUT')));
    request.on('error', reject);
    request.end();
  });
}
const state = value => ((value.status || {}).conditions || []).filter(c => c.status === 'True').map(c => c.type).concat((value.status || {}).ready > 0 ? ['Ready'] : []);
(async () => {
  const pending = new Set(names);
  while (pending.size > 0) {
    for (const spec of [...pending]) {
      const [name, until] = spec.split(':');
      try {
        const found = state(await job(name));
        if (found.includes('Failed')) { console.error('WAIT_JOB_FAILED ' + name); process.exit(2); }
        if (found.includes('Complete') || (until === 'ready' && found.includes('Ready'))) pending.delete(spec);
      } catch (error) { /* the API or the Job is not reachable yet; keep waiting to the deadline */ }
    }
    if (pending.size === 0) break;
    if (Date.now() > deadline) { console.error('WAIT_DEADLINE ' + [...pending].join(',')); process.exit(3); }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
})();
