// probe.js — one probe set, run unchanged against cgm-remote-monitor and Nocturne.
//
// Usage: NPAR_SECRET=<plaintext secret> node probe.js <base url> <label>
// Prints one JSON line per request. Synthetic data only: every record it writes is made here.
//
// Derived from the route audit for cgm-remote-monitor #8858 (its probe.js, 325 requests per run):
// the v1, v2-auth and v3 request list is kept; what changed is listed in README.md ("Probe set").
//
// The full-access credential is the server's API secret, sent the Nightscout way: the SHA-1 hex
// of the plaintext in the `api-secret` header. For v3, the probe tries, in order, a JWT minted
// through /api/v2/authorization (cgm-remote-monitor's documented v3 credential) and the
// `api-secret` header (Nocturne's documented v3 credential), and uses the first one that
// /api/v3/status accepts; the result line `v3.credential` says which.
//
// Nothing secret is written out: paths are recorded with the secret, its hash, access tokens and
// JWTs replaced by <secret>, <secret-sha1>, <access-token> and <jwt>. Bodies are reduced to shapes
// (kind, keys, length) and to the named semantic values in `sem`; no record ids are written.
const crypto = require('crypto');
const base = process.argv[2], label = process.argv[3];
const SECRET = process.env.NPAR_SECRET;
if (!SECRET) { console.error('NPAR_SECRET must be set'); process.exit(2); }
const H = crypto.createHash('sha1').update(SECRET).digest('hex');
const TAG = 'npar-' + label;             // device / enteredBy tag, distinct per run label
const redactions = [[SECRET, '<secret>'], [H, '<secret-sha1>']];
const out = [];

function keysOf (o) { return Object.keys(o).sort(); }
function shape (b) {
  if (b === null) return {kind: 'null'};
  if (b === undefined) return {kind: 'empty'};
  if (Array.isArray(b)) {
    const objs = b.filter(x => x && typeof x === 'object' && !Array.isArray(x));   // field union over every item
    const s = {kind: 'array', len: b.length};
    if (objs.length) s.itemKeys = [...new Set(objs.flatMap(keysOf))].sort();
    else if (b.length) s.itemKind = typeof b[0];
    return s;
  }
  if (typeof b === 'object') {
    const s = {kind: 'object', keys: keysOf(b)};
    if ('result' in b) s.result = shape(b.result);
    return s;
  }
  return {kind: typeof b};
}
function redact (s) { for (const [a, b] of redactions) s = s.split(a).join(b); return s; }

async function live () {
  const st = await fetch(base + '/api/versions').then(r => r.status).catch(e => 'DOWN ' + e.message);
  if (st !== 200) throw new Error('server not live: ' + st);
}
// op: "METHOD /normalised/path" (ops.js), the operation the request exercises
// cred: the credential class the comparison joins on (README "How results are compared")
const credOf = {};
async function req (id, op, method, path, {auth, body, headers = {}, bearer, sem, cred} = {}) {
  const h = Object.assign({}, headers);
  if (auth === 'secret') h['api-secret'] = H;
  if (bearer) h.Authorization = 'Bearer ' + bearer;
  if (body !== undefined) h['Content-Type'] = 'application/json';
  await live();   // liveness inside the same run as every probe, negative ones included
  const rec = {label, id, op, method, path: redact(path), auth: auth || (bearer ? 'bearer' : 'none'),
    cred: cred || (auth === 'secret' ? 'full' : bearer ? (credOf[bearer] || 'other-bearer') : 'none')};
  let r, text, json;
  try {
    r = await fetch(base + path, {method, headers: h, body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)), redirect: 'manual'});
    text = await r.text();
    try { json = JSON.parse(text); } catch { json = undefined; }
  } catch (e) { rec.error = e.message; out.push(rec); return; }
  rec.status = r.status;
  rec.ctype = (r.headers.get('content-type') || '').split(';')[0] || null;
  rec.shape = json !== undefined ? shape(json) : (text.length ? {kind: 'text'} : {kind: 'empty'});
  // an error body's message, with long numbers and uuids masked (they change per run)
  const m = r.status >= 400 && json && typeof json === 'object' && (json.message || json.title || json.description);
  if (m) rec.msg = redact(String(m)).replace(/[0-9a-f]{8}-[0-9a-f-]{27}|[0-9a-f]{24}|\d{6,}/g, '<n>').slice(0, 120);
  if (sem) { try { rec.sem = sem(json, r); } catch (e) { rec.sem = {error: e.message}; } }
  out.push(rec);
  return json;
}
const DAY = 86400000;
const arr = j => Array.isArray(j) ? j : (j && Array.isArray(j.result) ? j.result : null);

(async () => {
  const now = Date.now();
  const iso = new Date(now).toISOString();
  const S = {auth: 'secret'};
  // ---------- API v1 surface, without and with the credential ----------
  for (const a of ['none', 'secret']) {
    const o = a === 'secret' ? {auth: 'secret'} : {};
    await req('v1.entries.get', 'GET /api/v1/entries', 'GET', '/api/v1/entries', o);
    await req('v1.entries.get.json', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=2', o);
    await req('v1.entries.current', 'GET /api/v1/entries/current', 'GET', '/api/v1/entries/current', o);
    await req('v1.entries.spec.type', 'GET /api/v1/entries/{}', 'GET', '/api/v1/entries/sgv?count=2', o);
    await req('v1.slice', 'GET /api/v1/slice/{}/{}/{}/{}', 'GET', '/api/v1/slice/entries/dateString/sgv/2026', o);
    await req('v1.echo', 'GET /api/v1/echo/{}/{}', 'GET', '/api/v1/echo/entries/sgv', o);
    await req('v1.times', 'GET /api/v1/times/{}', 'GET', '/api/v1/times/2026', o);
    await req('v1.times.echo', 'GET /api/v1/times/echo/{}/{}', 'GET', '/api/v1/times/echo/2026/T{13..14}', o);
    await req('v1.count', 'GET /api/v1/count/{}/where', 'GET', '/api/v1/count/entries/where', o);
    await req('v1.treatments.get', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments', o);
    await req('v1.profile.get', 'GET /api/v1/profile', 'GET', '/api/v1/profile', o);
    await req('v1.profile.current', 'GET /api/v1/profile/current', 'GET', '/api/v1/profile/current', o);
    await req('v1.profiles.get', 'GET /api/v1/profiles', 'GET', '/api/v1/profiles', o);
    await req('v1.status', 'GET /api/v1/status', 'GET', '/api/v1/status', o);
    await req('v1.status.json', 'GET /api/v1/status', 'GET', '/api/v1/status.json', o);
    await req('v1.devicestatus.get', 'GET /api/v1/devicestatus', 'GET', '/api/v1/devicestatus', o);
    await req('v1.activity.get', 'GET /api/v1/activity', 'GET', '/api/v1/activity', o);
    await req('v1.food.get', 'GET /api/v1/food', 'GET', '/api/v1/food', o);
    await req('v1.food.quickpicks', 'GET /api/v1/food/quickpicks', 'GET', '/api/v1/food/quickpicks', o);
    await req('v1.food.regular', 'GET /api/v1/food/regular', 'GET', '/api/v1/food/regular', o);
    await req('v1.adminnotifies', 'GET /api/v1/adminnotifies', 'GET', '/api/v1/adminnotifies', o);
    await req('v1.verifyauth', 'GET /api/v1/verifyauth', 'GET', '/api/v1/verifyauth', o);
    await req('v1.experiments.test', 'GET /api/v1/experiments/test', 'GET', '/api/v1/experiments/test', o);
    await req('v1.notifications.ack', 'GET /api/v1/notifications/ack', 'GET', '/api/v1/notifications/ack?level=0', o);
    await req('api.versions', 'GET /api/versions', 'GET', '/api/versions', o);
    // writes
    await req('v1.entries.preview', 'POST /api/v1/entries/preview', 'POST', '/api/v1/entries/preview', Object.assign({body: [{type: 'sgv', sgv: 120, date: now, dateString: iso, device: TAG}]}, o));
    const ent = await req('v1.entries.post', 'POST /api/v1/entries', 'POST', '/api/v1/entries', Object.assign({body: [{type: 'sgv', sgv: 121, date: now - 60000, dateString: new Date(now - 60000).toISOString(), device: TAG + '-' + a}]}, o));
    const entId = Array.isArray(ent) && ent[0] && ent[0]._id;
    await req('v1.entries.spec.id', 'GET /api/v1/entries/{}', 'GET', '/api/v1/entries/' + (entId || '000000000000000000000000'), o);
    await req('v1.entries.delete.spec', 'DELETE /api/v1/entries/{}', 'DELETE', '/api/v1/entries/' + (entId || '000000000000000000000000'), o);
    await req('v1.entries.delete', 'DELETE /api/v1/entries', 'DELETE', '/api/v1/entries?find[device]=' + TAG + '-none', o);
    const tr = await req('v1.treatments.post', 'POST /api/v1/treatments', 'POST', '/api/v1/treatments', Object.assign({body: {eventType: 'Note', notes: 'npar probe', created_at: iso, enteredBy: TAG + '-' + a}}, o));
    const t0 = Array.isArray(tr) && tr[0];
    await req('v1.treatments.put', 'PUT /api/v1/treatments', 'PUT', '/api/v1/treatments', Object.assign({body: t0 ? Object.assign({}, t0, {notes: 'npar probe 2'}) : {_id: '000000000000000000000000', eventType: 'Note', created_at: iso}}, o));
    await req('v1.treatments.delete.id', 'DELETE /api/v1/treatments/{}', 'DELETE', '/api/v1/treatments/' + ((t0 && t0._id) || '000000000000000000000000'), o);
    await req('v1.treatments.delete', 'DELETE /api/v1/treatments', 'DELETE', '/api/v1/treatments?find[enteredBy]=' + TAG + '-none', o);
    const ds = await req('v1.devicestatus.post', 'POST /api/v1/devicestatus', 'POST', '/api/v1/devicestatus', Object.assign({body: {device: TAG + '-' + a, created_at: iso, uploaderBattery: 50}}, o));
    await req('v1.devicestatus.delete.id', 'DELETE /api/v1/devicestatus/{}', 'DELETE', '/api/v1/devicestatus/' + ((Array.isArray(ds) && ds[0] && ds[0]._id) || '000000000000000000000000'), o);
    await req('v1.devicestatus.delete', 'DELETE /api/v1/devicestatus', 'DELETE', '/api/v1/devicestatus?find[device]=' + TAG + '-none', o);
    const pr = await req('v1.profile.post', 'POST /api/v1/profile', 'POST', '/api/v1/profile', Object.assign({body: {defaultProfile: 'Default', startDate: iso, store: {Default: {dia: 3, units: 'mg/dl', timezone: 'UTC', carbratio: [{time: '00:00', value: 10}], sens: [{time: '00:00', value: 50}], basal: [{time: '00:00', value: 1}], target_low: [{time: '00:00', value: 100}], target_high: [{time: '00:00', value: 120}]}}, created_at: iso}}, o));
    const p0 = Array.isArray(pr) && pr[0];
    await req('v1.profile.put', 'PUT /api/v1/profile', 'PUT', '/api/v1/profile', Object.assign({body: p0 ? Object.assign({}, p0, {defaultProfile: 'Default'}) : {_id: '000000000000000000000000'}}, o));
    await req('v1.profile.delete.id', 'DELETE /api/v1/profile/{}', 'DELETE', '/api/v1/profile/' + ((p0 && p0._id) || '000000000000000000000000'), o);
    await req('v1.profile.delete.prune', 'DELETE /api/v1/profile', 'DELETE', '/api/v1/profile?keep=100', o);
    const ac = await req('v1.activity.post', 'POST /api/v1/activity', 'POST', '/api/v1/activity', Object.assign({body: {created_at: iso, steps: 10, enteredBy: TAG}}, o));
    const a0 = Array.isArray(ac) && ac[0];
    await req('v1.activity.put', 'PUT /api/v1/activity', 'PUT', '/api/v1/activity', Object.assign({body: a0 ? Object.assign({}, a0, {steps: 11}) : {_id: '000000000000000000000000', steps: 1}}, o));
    await req('v1.activity.delete.id', 'DELETE /api/v1/activity/{}', 'DELETE', '/api/v1/activity/' + ((a0 && a0._id) || '000000000000000000000000'), o);
    const fd = await req('v1.food.post', 'POST /api/v1/food', 'POST', '/api/v1/food', Object.assign({body: {type: 'food', name: 'npar probe', carbs: 10, portion: 100, unit: 'g', category: 'probe'}}, o));
    const f0 = Array.isArray(fd) ? fd[0] : (fd && fd._id ? fd : null);
    await req('v1.food.put', 'PUT /api/v1/food', 'PUT', '/api/v1/food', Object.assign({body: f0 ? Object.assign({}, f0, {carbs: 11}) : {_id: '000000000000000000000000', carbs: 1}}, o));
    await req('v1.food.delete.id', 'DELETE /api/v1/food/{}', 'DELETE', '/api/v1/food/' + ((f0 && f0._id) || '000000000000000000000000'), o);
    await req('v1.alexa', 'POST /api/v1/alexa', 'POST', '/api/v1/alexa', Object.assign({body: {request: {type: 'SessionEndedRequest', locale: 'en-US'}}}, o));
    await req('v1.googlehome', 'POST /api/v1/googlehome', 'POST', '/api/v1/googlehome', Object.assign({body: {queryResult: {parameters: {}, intent: {displayName: 'Glucose'}}, originalDetectIntentRequest: {payload: {user: {locale: 'en-US'}}}}}, o));
    await req('v1.notifications.pushovercallback', 'POST /api/v1/notifications/pushovercallback', 'POST', '/api/v1/notifications/pushovercallback', Object.assign({body: {receipt: 'none'}}, o));
  }
  // ---------- API v1 variants, with the credential ----------
  await req('v1.entries.csv', 'GET /api/v1/entries', 'GET', '/api/v1/entries.csv?count=1', S);
  await req('v1.entries.tsv', 'GET /api/v1/entries', 'GET', '/api/v1/entries.tsv?count=1', S);
  await req('v1.entries.txt', 'GET /api/v1/entries', 'GET', '/api/v1/entries.txt?count=1', S);
  await req('v1.entries.badOperator', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?find[sgv][$where]=1', S);
  await req('v1.entries.spec.unknownid', 'GET /api/v1/entries/{}', 'GET', '/api/v1/entries/0123456789abcdef01234567', S);
  for (const ext of ['txt', 'html', 'js', 'png', 'svg']) await req('v1.status.' + ext, 'GET /api/v1/status', 'GET', '/api/v1/status.' + ext, S);
  await req('v1.treatments.post.bad', 'POST /api/v1/treatments', 'POST', '/api/v1/treatments', {auth: 'secret', body: 'x'});
  await req('v1.entries.post.scalar', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: 5});
  await req('v1.count.treatments', 'GET /api/v1/count/{}/where', 'GET', '/api/v1/count/treatments/where', S);
  await req('v1.echo.treatments', 'GET /api/v1/echo/{}', 'GET', '/api/v1/echo/treatments', S);
  await req('v1.slice.short', 'GET /api/v1/slice/{}/{}', 'GET', '/api/v1/slice/entries/dateString', S);
  await req('v1.times.none', 'GET /api/v1/times', 'GET', '/api/v1/times', S);
  // credential spellings
  await req('v1.entries.secret-query', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=1&secret=' + H, {cred: 'secret-query'});
  await req('v1.entries.secret-plain', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=1', {headers: {'api-secret': SECRET}, cred: 'plaintext-header'});
  await req('v1.entries.secret-upper', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=1', {headers: {'api-secret': H.toUpperCase()}, cred: 'uppercase-sha1-header'});

  // ---------- API v2 authorization: subject + access token + JWT ----------
  const subjName = TAG.replace(/[^a-z0-9]/g, '') + 'admin';
  const roName = TAG.replace(/[^a-z0-9]/g, '') + 'ro';
  await req('v2.subjects.post', 'POST /api/v2/authorization/subjects', 'POST', '/api/v2/authorization/subjects', {auth: 'secret', body: {name: subjName, roles: ['admin']}});
  await req('v2.subjects.post.ro', 'POST /api/v2/authorization/subjects', 'POST', '/api/v2/authorization/subjects', {auth: 'secret', body: {name: roName, roles: ['readable']}});
  const subjects = await req('v2.subjects.get', 'GET /api/v2/authorization/subjects', 'GET', '/api/v2/authorization/subjects', {auth: 'secret'});
  const find = n => Array.isArray(subjects) ? subjects.find(s => s.name === n) : null;
  const accessToken = (find(subjName) || {}).accessToken || '';
  const roTok = (find(roName) || {}).accessToken || '';
  for (const t of [accessToken, roTok]) if (t) redactions.push([t, '<access-token>']);
  if (accessToken) credOf[accessToken] = 'access-token';
  let jwt = '', roJwt = '';
  if (accessToken) {
    const j = await req('v2.request.token', 'GET /api/v2/authorization/request/{}', 'GET', '/api/v2/authorization/request/' + accessToken, {sem: j => ({hasToken: !!(j && j.token)})});
    jwt = (j && j.token) || '';
    if (roTok) { const j2 = await fetch(base + '/api/v2/authorization/request/' + roTok).then(r => r.json()).catch(() => null); roJwt = (j2 && j2.token) || ''; }
    for (const t of [jwt, roJwt]) if (t) redactions.push([t, '<jwt>']);
    if (jwt) credOf[jwt] = 'full'; if (roJwt) credOf[roJwt] = 'readonly';
    await req('v1.entries.token-query', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=1&token=' + accessToken, {cred: 'token-query'});
    if (jwt) {
      await req('v1.entries.bearer-jwt', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=1', {bearer: jwt});
      await req('v1.verifyauth.jwt', 'GET /api/v1/verifyauth', 'GET', '/api/v1/verifyauth', {bearer: jwt});
    }
  }
  out.push({label, id: 'v2.subject.accessToken', op: 'GET /api/v2/authorization/subjects', sem: {adminAccessTokenIssued: !!accessToken, readableAccessTokenIssued: !!roTok, jwtIssued: !!jwt}});

  // ---------- API v3 ----------
  await req('v3.version', 'GET /api/v3/version', 'GET', '/api/v3/version', {});
  await req('v3.status.none', 'GET /api/v3/status', 'GET', '/api/v3/status', {});
  const stSecret = await req('v3.status.secret', 'GET /api/v3/status', 'GET', '/api/v3/status', {auth: 'secret', cred: 'api-secret-header'});
  if (accessToken) await req('v3.status.accesstoken', 'GET /api/v3/status', 'GET', '/api/v3/status', {bearer: accessToken});
  const stJwt = jwt ? await req('v3.status.jwt', 'GET /api/v3/status', 'GET', '/api/v3/status', {bearer: jwt, cred: 'jwt'}) : null;
  const okStatus = j => j && j.status === 200 && j.result;
  const V = okStatus(stJwt) ? {bearer: jwt} : okStatus(stSecret) ? {auth: 'secret'} : {bearer: jwt};
  const RO = roJwt ? {bearer: roJwt} : null;
  out.push({label, id: 'v3.credential', op: 'GET /api/v3/status', sem: {v3FullCredential: okStatus(stJwt) ? 'jwt' : okStatus(stSecret) ? 'api-secret' : 'none-accepted', readOnlyCredential: RO ? 'jwt' : 'none-issued'}});
  await req('v3.lastModified', 'GET /api/v3/lastmodified', 'GET', '/api/v3/lastModified', Object.assign({sem: j => ({collections: j && j.result && j.result.collections ? keysOf(j.result.collections) : null})}, V));
  await req('v3.test', 'GET /api/v3/test', 'GET', '/api/v3/test', V);
  await req('v3.swagger-ui-dist', 'GET /api/v3/swagger-ui-dist', 'GET', '/api/v3/swagger-ui-dist', {});
  for (const col of ['devicestatus', 'entries', 'food', 'profile', 'settings', 'treatments']) {
    const P = '/api/v3/' + col;
    await req('v3.' + col + '.search.none', 'GET ' + P, 'GET', P, {});
    await req('v3.' + col + '.search', 'GET ' + P, 'GET', P + '?limit=2', V);
    if (RO) await req('v3.' + col + '.search.ro', 'GET ' + P, 'GET', P + '?limit=2', RO);
    const ident = TAG + '-' + col + '-' + now;
    const doc = {date: now, app: TAG, device: TAG, identifier: ident};
    if (col === 'treatments') doc.eventType = 'Note';
    if (col === 'entries') { doc.type = 'sgv'; doc.sgv = 100; }
    const idSem = j => ({identifierReturned: j && j.identifier !== undefined ? (j.identifier === ident ? 'client-identifier' : 'other') : 'absent', isDeduplication: j ? j.isDeduplication === true : null});
    const created = await req('v3.' + col + '.create', 'POST ' + P, 'POST', P, Object.assign({body: doc, sem: idSem}, V));
    await req('v3.' + col + '.create.again', 'POST ' + P, 'POST', P, Object.assign({body: doc, sem: idSem}, V));
    await req('v3.' + col + '.create._id', 'POST ' + P, 'POST', P, Object.assign({body: Object.assign({}, doc, {_id: '0123456789abcdef01234567', identifier: ident + 'x'})}, V));
    if (RO) await req('v3.' + col + '.create.ro', 'POST ' + P, 'POST', P, Object.assign({body: Object.assign({}, doc, {identifier: ident + 'ro'})}, RO));
    // per-record probes use the identifier the server answered with (what a client would hold);
    // reading by the identifier the client sent is its own probe
    await req('v3.' + col + '.read.client-identifier', 'GET ' + P + '/{}', 'GET', P + '/' + ident, V);
    const sid = (created && typeof created.identifier === 'string' && created.identifier) || ident;
    if (sid !== ident) redactions.push([sid, '<server-identifier>']);
    const readSem = j => { const d = j && (j.result || j); return d && typeof d === 'object' ? {identifierIsClient: d.identifier === ident, hasId: d._id !== undefined, idEqualsIdentifier: d._id !== undefined && d._id === d.identifier} : null; };
    await req('v3.' + col + '.read', 'GET ' + P + '/{}', 'GET', P + '/' + sid, Object.assign({sem: readSem}, V));
    if (RO) await req('v3.' + col + '.read.ro', 'GET ' + P + '/{}', 'GET', P + '/' + sid, RO);
    await req('v3.' + col + '.read.ims', 'GET ' + P + '/{}', 'GET', P + '/' + sid, Object.assign({headers: {'If-Modified-Since': new Date(now + 3600000).toUTCString()}}, V));
    await req('v3.' + col + '.read.missing', 'GET ' + P + '/{}', 'GET', P + '/' + TAG + '-nonexistent', V);
    await req('v3.' + col + '.read.csv', 'GET ' + P + '/{}', 'GET', P + '/' + sid + '.csv', V);
    await req('v3.' + col + '.read.xml', 'GET ' + P + '/{}', 'GET', P + '/' + sid, Object.assign({headers: {Accept: 'application/xml'}}, V));
    await req('v3.' + col + '.read.406', 'GET ' + P + '/{}', 'GET', P + '/' + sid, Object.assign({headers: {Accept: 'image/png'}}, V));
    await req('v3.' + col + '.update', 'PUT ' + P + '/{}', 'PUT', P + '/' + sid, Object.assign({body: Object.assign({}, doc, {notes: 'updated'})}, V));
    await req('v3.' + col + '.update.new', 'PUT ' + P + '/{}', 'PUT', P + '/' + sid + '-put', Object.assign({body: Object.assign({}, doc, {identifier: undefined})}, V));
    await req('v3.' + col + '.update.ius', 'PUT ' + P + '/{}', 'PUT', P + '/' + sid, Object.assign({body: Object.assign({}, doc, {notes: 'u2'}), headers: {'If-Unmodified-Since': new Date(now - 3600000).toUTCString()}}, V));
    await req('v3.' + col + '.patch', 'PATCH ' + P + '/{}', 'PATCH', P + '/' + sid, Object.assign({body: {notes: 'patched'}}, V));
    await req('v3.' + col + '.patch.missing', 'PATCH ' + P + '/{}', 'PATCH', P + '/' + TAG + '-nonexistent', Object.assign({body: {notes: 'patched'}}, V));
    await req('v3.' + col + '.patch.immutable', 'PATCH ' + P + '/{}', 'PATCH', P + '/' + sid, Object.assign({body: {date: now + 1}}, V));
    await req('v3.' + col + '.history.header', 'GET ' + P + '/history', 'GET', P + '/history', Object.assign({headers: {'Last-Modified': new Date(now - 3600000).toUTCString()}}, V));
    await req('v3.' + col + '.history.noheader', 'GET ' + P + '/history', 'GET', P + '/history', V);
    await req('v3.' + col + '.history.ts', 'GET ' + P + '/history/{}', 'GET', P + '/history/' + (now - 3600000) + '?limit=1000', V);   // all of this run's changes: a fixed set
    if (RO) await req('v3.' + col + '.history.ro', 'GET ' + P + '/history/{}', 'GET', P + '/history/' + (now - 3600000), RO);
    await req('v3.' + col + '.delete', 'DELETE ' + P + '/{}', 'DELETE', P + '/' + sid, V);
    await req('v3.' + col + '.read.deleted', 'GET ' + P + '/{}', 'GET', P + '/' + sid, V);
    await req('v3.' + col + '.delete.again', 'DELETE ' + P + '/{}', 'DELETE', P + '/' + sid, V);
    await req('v3.' + col + '.delete.permanent', 'DELETE ' + P + '/{}', 'DELETE', P + '/' + sid + '-put?permanent=true', V);
    await req('v3.' + col + '.delete.missing', 'DELETE ' + P + '/{}', 'DELETE', P + '/' + TAG + '-nonexistent', V);
  }
  await req('v3.search.skip.neg', 'GET /api/v3/entries', 'GET', '/api/v3/entries?skip=-1', V);
  await req('v3.search.sortboth', 'GET /api/v3/entries', 'GET', '/api/v3/entries?sort=date&sort$desc=date', V);
  await req('v3.search.badop', 'GET /api/v3/entries', 'GET', '/api/v3/entries?sgv$foo=1', V);
  await req('v3.search.filter', 'GET /api/v3/entries', 'GET', '/api/v3/entries?sgv$gte=50&fields=date,sgv', V);
  await req('v3.search.csv', 'GET /api/v3/entries', 'GET', '/api/v3/entries.csv?limit=1', V);
  await req('v3.search.csvaccept', 'GET /api/v3/entries', 'GET', '/api/v3/entries?limit=1', Object.assign({headers: {Accept: 'text/csv'}}, V));
  await req('v3.unknown.collection', 'GET /api/v3/{}', 'GET', '/api/v3/bogus', V);
  await req('v3.unknown.op', 'POST /api/v3/entries/history', 'POST', '/api/v3/entries/history', Object.assign({body: {}}, V));

  // ---------- semantics (README "Semantics probed") ----------
  // window: entries and treatments 1, 3, 5 and 10 days old; which ages a read with no date filter returns
  const ages = [1, 3, 5, 10];
  const agesOf = (j, f) => (arr(j) || []).filter(x => x.device === undefined || x.device === winDev || x.enteredBy === winDev).map(x => Math.round((now - (typeof x[f] === 'number' ? x[f] : Date.parse(x[f]))) / DAY)).sort((a, b) => a - b);
  const winDev = TAG + '-window';
  const beforeWindowSeed = Date.now() - 1000;
  await req('sem.window.seed.entries', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: ages.map(d => ({type: 'sgv', sgv: 100 + d, date: now - d * DAY, dateString: new Date(now - d * DAY).toISOString(), device: winDev}))});
  await req('sem.window.seed.treatments', 'POST /api/v1/treatments', 'POST', '/api/v1/treatments', {auth: 'secret', body: ages.map(d => ({eventType: 'Note', notes: 'age ' + d, created_at: new Date(now - d * DAY).toISOString(), enteredBy: winDev}))});
  // v3 history keyed on modification: the four old readings were written just now
  await req('sem.history.old-records-written-now', 'GET /api/v3/entries/history/{}', 'GET', '/api/v3/entries/history/' + beforeWindowSeed + '?limit=1000', Object.assign({sem: j => ({agesReturnedDays: agesOf(j, 'date')})}, V));
  await req('sem.window.entries', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=100&find[device]=' + winDev, {auth: 'secret', sem: j => ({agesReturnedDays: agesOf(j, 'date')})});
  await req('sem.window.entries.dated', 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?count=100&find[device]=' + winDev + '&find[date][$gte]=' + (now - 30 * DAY), {auth: 'secret', sem: j => ({agesReturnedDays: agesOf(j, 'date')})});
  await req('sem.window.treatments', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments.json?count=100&find[enteredBy]=' + winDev, {auth: 'secret', sem: j => ({agesReturnedDays: agesOf(j, 'created_at')})});
  // count: 15 recent entries
  const cDev = TAG + '-count';
  await req('sem.count.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: Array.from({length: 15}, (_, i) => ({type: 'sgv', sgv: 90 + i, date: now - (i + 1) * 300000, dateString: new Date(now - (i + 1) * 300000).toISOString(), device: cDev}))});
  const lenSem = j => ({len: (arr(j) || {length: null}).length});
  const countSem = (j, r) => ({len: (arr(j) || {length: null}).length, deprecation: r.headers.get('deprecation') === 'true'});
  const win = '&find[date][$gte]=' + (now - 2 * 3600000) + '&find[date][$lte]=' + now;
  for (const [n, q] of [['default', ''], ['0', '&count=0'], ['0-in-date-window', '&count=0' + win], ['3', '&count=3'], ['abc', '&count=abc'], ['neg', '&count=-3'],
    ['leading-number-then-query', '&count=5?npar'], ['leading-number-then-text', '&count=5abc'], ['decimal', '&count=3.5'], ['exponent', '&count=1e1'], ['empty', '&count=']]) {
    await req('sem.count.' + n, 'GET /api/v1/entries', 'GET', '/api/v1/entries.json?find[device]=' + cDev + q, {auth: 'secret', sem: countSem});
  }
  await req('sem.count.treatments.0', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments.json?count=0&find[enteredBy]=' + winDev, {auth: 'secret', sem: countSem});
  await req('sem.count.devicestatus.0', 'GET /api/v1/devicestatus', 'GET', '/api/v1/devicestatus.json?count=0', {auth: 'secret', sem: countSem});
  await req('sem.count.delete.0', 'DELETE /api/v1/entries', 'DELETE', '/api/v1/entries?count=0&find[device]=' + TAG + '-nothing', {auth: 'secret'});
  // v1 dedup: an isolated re-send, and readings from two devices at the same or a nearby time,
  // each in an hour no other probe writes to; counted by a date-range read
  const HOUR = 3600000;
  const dEnt = t => ({type: 'sgv', sgv: 133, date: t, dateString: new Date(t).toISOString(), device: TAG + '-dedup'});
  const inRange = (t0, t1) => '/api/v1/entries.json?count=10&find[date][$gte]=' + t0 + '&find[date][$lte]=' + t1;
  // times are placed on the 5-minute clock grid (slot start + 30 s), so each pair below either
  // shares a 5-minute slot or straddles a slot boundary on every run
  const SLOT = 300000;
  const slot = h => Math.floor((now - h * HOUR) / SLOT) * SLOT + 30000;
  let t = slot(30);
  await req('sem.dedup.entries.1', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [dEnt(t)], sem: lenSem});
  await req('sem.dedup.entries.2', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [dEnt(t)], sem: lenSem});
  await req('sem.dedup.entries.stored', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 1000), {auth: 'secret', sem: lenSem});
  t = slot(33);
  await req('sem.dedup.otherdevice.same-time.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t), {device: TAG + '-dev-a', sgv: 140}), Object.assign(dEnt(t), {device: TAG + '-dev-b', sgv: 141})], sem: lenSem});
  await req('sem.dedup.otherdevice.same-time', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 1000), {auth: 'secret', sem: lenSem});
  t = slot(36);
  await req('sem.dedup.otherdevice.60s-same-slot.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t), {device: TAG + '-dev-a', sgv: 150}), Object.assign(dEnt(t + 60000), {device: TAG + '-dev-b', sgv: 151})], sem: lenSem});
  await req('sem.dedup.otherdevice.60s-same-slot', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 61000), {auth: 'secret', sem: lenSem});
  // the same pair as two requests, as two uploaders would send them
  t = slot(37);
  await req('sem.dedup.otherdevice.60s-same-slot.separate.seed-a', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t), {device: TAG + '-dev-a', sgv: 152})], sem: lenSem});
  await req('sem.dedup.otherdevice.60s-same-slot.separate.seed-b', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t + 60000), {device: TAG + '-dev-b', sgv: 153})], sem: lenSem});
  await req('sem.dedup.otherdevice.60s-same-slot.separate', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 61000), {auth: 'secret', sem: lenSem});
  // 60 s apart across a slot boundary (slot start - 30 s, slot start + 30 s)
  t = slot(38) - 60000;
  await req('sem.dedup.otherdevice.60s-across-slots.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t), {device: TAG + '-dev-a', sgv: 154}), Object.assign(dEnt(t + 60000), {device: TAG + '-dev-b', sgv: 155})], sem: lenSem});
  await req('sem.dedup.otherdevice.60s-across-slots', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 61000), {auth: 'secret', sem: lenSem});
  t = slot(39);
  await req('sem.dedup.samedevice.60s-same-slot.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: [Object.assign(dEnt(t), {sgv: 160}), Object.assign(dEnt(t + 60000), {sgv: 161})], sem: lenSem});
  await req('sem.dedup.samedevice.60s-same-slot', 'GET /api/v1/entries', 'GET', inRange(t - 1000, t + 61000), {auth: 'secret', sem: lenSem});
  const dTr = {eventType: 'Note', notes: 'dedup', created_at: new Date(now - 42 * HOUR).toISOString(), enteredBy: TAG + '-dedup'};
  await req('sem.dedup.treatments.1', 'POST /api/v1/treatments', 'POST', '/api/v1/treatments', {auth: 'secret', body: dTr, sem: lenSem});
  await req('sem.dedup.treatments.2', 'POST /api/v1/treatments', 'POST', '/api/v1/treatments', {auth: 'secret', body: dTr, sem: lenSem});
  await req('sem.dedup.treatments.stored', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments.json?count=10&find[enteredBy]=' + TAG + '-dedup', {auth: 'secret', sem: lenSem});
  const dDs = {device: TAG + '-dedup', created_at: new Date(now - 45 * HOUR).toISOString(), uploaderBattery: 40};
  await req('sem.dedup.devicestatus.1', 'POST /api/v1/devicestatus', 'POST', '/api/v1/devicestatus', {auth: 'secret', body: dDs, sem: lenSem});
  await req('sem.dedup.devicestatus.2', 'POST /api/v1/devicestatus', 'POST', '/api/v1/devicestatus', {auth: 'secret', body: dDs, sem: lenSem});
  await req('sem.dedup.devicestatus.stored', 'GET /api/v1/devicestatus', 'GET', '/api/v1/devicestatus.json?count=10&find[device]=' + TAG + '-dedup&find[created_at][$gte]=' + new Date(now - 46 * HOUR).toISOString(), {auth: 'secret', sem: lenSem});
  // v3 identifier: client identifier kept or replaced; v1-created record read through v3
  const vid = TAG + '-ident-' + now;
  await req('sem.v3.identifier.create', 'POST /api/v3/treatments', 'POST', '/api/v3/treatments', Object.assign({body: {date: now - 120000, app: TAG, eventType: 'Note', identifier: vid}, sem: j => ({identifierReturned: j && j.identifier !== undefined ? (j.identifier === vid ? 'client-identifier' : 'other') : 'absent'})}, V));
  const rsAt = now - 50 * 3600000;
  const rsDoc = {date: rsAt, app: TAG, eventType: 'Note', notes: 'resend', identifier: vid + '-resend'};
  await req('sem.v3.resend.1', 'POST /api/v3/treatments', 'POST', '/api/v3/treatments', Object.assign({body: rsDoc}, V));
  await req('sem.v3.resend.2', 'POST /api/v3/treatments', 'POST', '/api/v3/treatments', Object.assign({body: rsDoc, sem: j => ({isDeduplication: j ? j.isDeduplication === true : null})}, V));
  await req('sem.v3.resend.stored', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments.json?count=10&find[created_at][$gte]=' + new Date(rsAt - 1000).toISOString() + '&find[created_at][$lte]=' + new Date(rsAt + 1000).toISOString(), {auth: 'secret', sem: lenSem});
  await req('sem.v3.identifier.search', 'GET /api/v3/treatments', 'GET', '/api/v3/treatments?identifier$eq=' + vid, Object.assign({sem: j => { const a = arr(j) || []; return {found: a.length, identifierIsClient: a.length ? a[0].identifier === vid : null, hasId: a.length ? a[0]._id !== undefined : null, idEqualsIdentifier: a.length ? a[0]._id === a[0].identifier : null}; }}, V));
  await req('sem.v3.identifier.v1read', 'GET /api/v1/treatments', 'GET', '/api/v1/treatments.json?count=1&find[created_at][$gte]=' + new Date(now - 180000).toISOString() + '&find[eventType]=Note', {auth: 'secret', sem: j => { const a = arr(j) || []; const d = a.find(x => x.identifier === vid) || a[0]; return d ? {identifierIsClient: d.identifier === vid, idEqualsIdentifier: d._id === d.identifier, idLooksObjectId: /^[0-9a-f]{24}$/.test(String(d._id))} : null; }});
  await req('sem.v3.identifier.fromv1', 'GET /api/v3/entries', 'GET', '/api/v3/entries?limit=1&device$eq=' + cDev, Object.assign({sem: j => { const a = arr(j) || []; return a.length ? {hasIdentifier: a[0].identifier !== undefined, hasId: a[0]._id !== undefined, idEqualsIdentifier: a[0]._id !== undefined && a[0]._id === a[0].identifier, idLooksObjectId: /^[0-9a-f]{24}$/.test(String(a[0]._id))} : {found: 0}; }}, V));
  // v3 limit: 1050 entries, one a minute from 3 hours ago back; default and bounds
  const lDev = TAG + '-limit';
  await req('sem.limit.seed', 'POST /api/v1/entries', 'POST', '/api/v1/entries', {auth: 'secret', body: Array.from({length: 1050}, (_, i) => ({type: 'sgv', sgv: 70 + (i % 50), date: now - 3 * 3600000 - i * 60000, dateString: new Date(now - 3 * 3600000 - i * 60000).toISOString(), device: lDev}))});
  for (const [n, q] of [['default', ''], ['1000', '&limit=1000'], ['1001', '&limit=1001'], ['100000', '&limit=100000'], ['0', '&limit=0'], ['abc', '&limit=abc'], ['neg', '&limit=-1']]) {
    await req('sem.limit.' + n, 'GET /api/v3/entries', 'GET', '/api/v3/entries?device$eq=' + lDev + q, Object.assign({sem: lenSem}, V));
  }
  // lastModified once the collections hold records
  await req('sem.lastModified.end', 'GET /api/v3/lastmodified', 'GET', '/api/v3/lastModified', Object.assign({sem: j => ({collections: j && j.result && j.result.collections ? keysOf(j.result.collections) : null})}, V));

  // cleanup: remove the probe subjects
  const subs = await fetch(base + '/api/v2/authorization/subjects', {headers: {'api-secret': H}}).then(r => r.json()).catch(() => []);
  for (const s of Array.isArray(subs) ? subs : []) if ((s.name === subjName || s.name === roName) && s._id) await fetch(base + '/api/v2/authorization/subjects/' + s._id, {method: 'DELETE', headers: {'api-secret': H}});
  for (const o of out) console.log(JSON.stringify(o));
})().catch(e => { for (const o of out) console.log(JSON.stringify(o)); console.error('PROBE FAILED', e.message); process.exit(1); });
