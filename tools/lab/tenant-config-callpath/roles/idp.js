'use strict';
// Identity provider stub (D17: pluggable, behind Nightscout's own token
// exchange). Checks a synthetic password and returns a signed assertion
// naming the human. It knows nothing about tenants.
const { matrix, serve } = require('../lib/net');
const c = require('../lib/crypto');
const { loadRun, key } = require('../lib/store');

const run = loadRun(process.argv[2]);
const mx = matrix(run.design, run.breaks);
const priv = key(run.runDir, 'idp.key'); // the IdP's own signing key
const users = JSON.parse(key(run.runDir, 'users.json')); // synthetic owners

serve('idp', 'idp', mx, [
  ['GET', /^\/pubkey$/, async () => [200, { pem: key(run.runDir, 'idp.pub').toString() }]],
  ['POST', /^\/login$/, async (req, m, b) => {
    const u = users[b.user];
    if (!u || u.password !== b.password) return [401, { error: 'bad-login' }];
    const t = c.now();
    return [200, { assertion: c.signEd({ iss: 'lab-idp', aud: 'nightscout-lab', sub: b.user, auth_time: t, iat: t, exp: t + 600 }, priv) }];
  }]
]);
