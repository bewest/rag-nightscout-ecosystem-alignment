'use strict';
// URL-form identifiers (`scheme://a/b/c`) against a running cgm-remote-monitor:
// API v3 POST, then GET/PATCH/PUT/DELETE by identifier with the identifier
// fully percent-encoded, half-encoded and raw; v3 search by identifier; API v1
// find[identifier]= (encoded and raw), v1 re-send dedupe and v1 DELETE by id.
// Servers come from tools/lab/record-identity/lab.sh up (same secret, same mongo).
//
//   node url-identifier-probes.js <name> <build-dir> <port>        one JSON object
//   node url-identifier-probes.js --compare <a.json> <b.json>      one markdown table
//
// Synthetic data only; every case uses a fresh random identifier.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const argv = process.argv.slice(2);
if (argv[0] === '--compare') {
  const runs = argv.slice(1).map(f => JSON.parse(fs.readFileSync(f, 'utf8')));
  console.log('| case | ' + runs.map(r => r.version + ' `' + r.head.slice(0, 8) + '`').join(' | ') + ' |');
  console.log('|---|' + runs.map(() => '---').join('|') + '|');
  for (const k of Object.keys(runs[0].cells)) {
    console.log('| ' + k + ' | ' + runs.map(r => String(r.cells[k] || '—').replace(/\|/g, '\\|')).join(' | ') + ' |');
  }
  process.exit(0);
}

const [NAME, DIR0, PORT] = argv;
const MODULES = path.join(path.resolve(DIR0), 'node_modules');
const { MongoClient } = require(path.join(MODULES, 'mongodb'));
const MONGO = 'mongodb://127.0.0.1:' + (process.env.RID_MONGO_PORT || 27184);
const DB = 'ridlab_' + NAME;
const STATE = process.env.RID_STATE || path.join(process.env.TMPDIR || '/tmp', 'record-identity');
const HASH = crypto.createHash('sha1').update(fs.readFileSync(path.join(STATE, 'secret'), 'utf8').trim()).digest('hex');
const BASE = 'http://127.0.0.1:' + PORT;
const H = { 'api-secret': HASH };

async function req (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json' }, headers),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
  return { s: r.status, j, t };
}

// A synthetic URL-form identifier: scheme://kind/<12 digits>/<seconds>.
const urlId = scheme => scheme + '://g7/' + String(crypto.randomInt(1e11, 1e12)) + '/' + crypto.randomInt(1000, 900000);
const full = s => encodeURIComponent(s); // ':' -> %3A, '/' -> %2F
const half = s => s.replace(/\//g, '%2F'); // '/' encoded, ':' raw
const n = r => Array.isArray(r.j) ? 'found ' + r.j.length : (r.j && Array.isArray(r.j.result) ? 'found ' + r.j.result.length : String(r.s));

(async () => {
  const cli = await MongoClient.connect(MONGO);
  const db = cli.db(DB);
  const cells = {};
  const put = (k, v) => { cells[k] = v; };

  await req('POST', '/api/v2/authorization/subjects', { name: 'ridlab-admin', roles: ['admin'] }, H);
  const subj = ((await req('GET', '/api/v2/authorization/subjects', undefined, H)).j || []).find(x => x.name === 'ridlab-admin');
  const jwt = (await req('GET', '/api/v2/authorization/request/' + subj.accessToken)).j.token;
  const V = { authorization: 'Bearer ' + jwt };

  let slot = 0;
  const t0 = Date.now() - 2 * 86400e3 + crypto.randomInt(0, 86400) * 1000;
  const T = () => t0 + (slot++) * 60000;
  const body = (col, t, X, extra) => Object.assign(col === 'treatments'
    ? { identifier: X, date: t, utcOffset: 0, app: 'ridlab', device: 'ridlab-dev', eventType: 'Carb Correction', carbs: 10 }
    : { identifier: X, date: t, utcOffset: 0, app: 'ridlab', device: 'ridlab-dev', type: 'sgv', sgv: 120 }, extra);
  const field = col => col === 'treatments' ? 'carbs' : 'sgv';
  const got = (r, X) => r.s + (r.j && r.j.result && r.j.result.identifier !== undefined ? (r.j.result.identifier === X ? ' identifier=X' : ' identifier≠X') : '');

  for (const col of ['entries', 'treatments']) {
    const F = field(col);
    // create, then read by each spelling
    {
      const t = T(), X = urlId('cgm');
      const c = await req('POST', '/api/v3/' + col, body(col, t, X), V);
      const d = await db.collection(col).find({ identifier: X }).toArray();
      put('v3 ' + col + ' POST identifier scheme://a/b/c', c.s + ' | stored n=' + d.length + (d[0] ? (d[0].identifier === X ? ' identifier=X' : ' identifier≠X') : ''));
      put('v3 ' + col + ' GET /' + col + '/<encodeURIComponent: %3A %2F>', got(await req('GET', '/api/v3/' + col + '/' + full(X), undefined, V), X));
      put('v3 ' + col + ' GET /' + col + '/<%2F only, ":" raw>', got(await req('GET', '/api/v3/' + col + '/' + half(X), undefined, V), X));
      put('v3 ' + col + ' GET /' + col + '/<raw>', got(await req('GET', '/api/v3/' + col + '/' + X, undefined, V), X));
      const s1 = await req('GET', '/api/v3/' + col + '?identifier$eq=' + full(X) + '&fields=identifier', undefined, V);
      const s2 = await req('GET', '/api/v3/' + col + '?identifier=' + full(X) + '&fields=identifier', undefined, V);
      put('v3 ' + col + ' search ?identifier$eq=<encoded>, ?identifier=<encoded>', n(s1) + ', ' + n(s2));
      const g1 = await req('GET', '/api/v1/' + col + '.json?find[identifier]=' + full(X), undefined, H);
      const g2 = await req('GET', '/api/v1/' + col + '.json?find[identifier]=' + X, undefined, H);
      put('v1 ' + col + ' GET find[identifier]=<encoded>, find[identifier]=<raw in query>', n(g1) + ', ' + n(g2));
      // control: one more path segment must not find the record on any route
      const Y = X + '/1';
      const c1 = await req('GET', '/api/v3/' + col + '/' + full(Y), undefined, V);
      const c2 = await req('GET', '/api/v3/' + col + '?identifier$eq=' + full(Y) + '&fields=identifier', undefined, V);
      const c3 = await req('GET', '/api/v1/' + col + '.json?find[identifier]=' + full(Y), undefined, H);
      put('control: ' + col + ' the same identifier plus "/1": v3 GET <encoded>, v3 search, v1 find[identifier]', got(c1, X) + ', ' + n(c2) + ', ' + n(c3));
    }
    // PATCH, PUT, DELETE by the fully encoded identifier
    {
      const t = T(), X = urlId('cgm');
      await req('POST', '/api/v3/' + col, body(col, t, X), V);
      const p = await req('PATCH', '/api/v3/' + col + '/' + full(X), { [F]: 77 }, V);
      const d1 = await db.collection(col).find({ identifier: X }).toArray();
      const u = await req('PUT', '/api/v3/' + col + '/' + full(X), body(col, t, X, { [F]: 88 }), V);
      const d2 = await db.collection(col).find({ identifier: X }).toArray();
      const r = await req('PATCH', '/api/v3/' + col + '/' + X, { [F]: 99 }, V);
      const del = await req('DELETE', '/api/v3/' + col + '/' + full(X), undefined, V);
      const d3 = await db.collection(col).find({ identifier: X }).toArray();
      put('v3 ' + col + ' PATCH <encoded>, then PUT <encoded>, then PATCH <raw>, then DELETE <encoded>',
        'PATCH ' + p.s + ' ' + F + '=' + (d1[0] && d1[0][F]) + ' | PUT ' + u.s + ' ' + F + '=' + (d2[0] && d2[0][F]) +
        ' | raw PATCH ' + r.s + ' | DELETE ' + del.s + ' stored n=' + d3.length + (d3[0] && d3[0].isValid === false ? ' isValid:false' : '') + ' ' + F + '=' + (d3[0] && d3[0][F]));
    }
    // PUT-as-create (upsert) by an encoded identifier that does not exist yet
    {
      const t = T(), X = urlId('cgm');
      const u = await req('PUT', '/api/v3/' + col + '/' + full(X), body(col, t, X), V);
      const d = await db.collection(col).find({ identifier: X }).toArray();
      put('v3 ' + col + ' PUT <encoded> for a new identifier', u.s + ' | stored n=' + d.length + (d[0] && d[0].identifier === X ? ' identifier=X' : ''));
    }
  }

  // API v1: write with a URL-form identifier, re-send, delete by it
  {
    const t = new Date(T()).toISOString(), X = urlId('loop');
    const tr = extra => Object.assign({ eventType: 'Carb Correction', carbs: 10, created_at: t, enteredBy: 'ridlab', identifier: X }, extra);
    const r1 = await req('POST', '/api/v1/treatments', [tr()], H);
    const r2 = await req('POST', '/api/v1/treatments', [tr({ carbs: 12 })], H);
    const d = await db.collection('treatments').find({ identifier: X }).toArray();
    put('v1 treatments POST identifier scheme://a/b/c, then re-send with carbs changed', r1.s + ' -> ' + r2.s + ' | stored n=' + d.length + (d[0] ? ' carbs=' + d[0].carbs : ''));
    const del = await req('DELETE', '/api/v1/treatments/' + full(X), undefined, H);
    const left = await db.collection('treatments').find({ identifier: X }).toArray();
    put('v1 treatments DELETE /treatments/<encoded scheme://a/b/c>', del.s + ' ' + JSON.stringify(del.j) + ', left n=' + left.length);
  }
  {
    const t = T(), X = urlId('cgm');
    const e = { type: 'sgv', sgv: 111, date: t, dateString: new Date(t).toISOString(), device: 'ridlab', identifier: X };
    const r = await req('POST', '/api/v1/entries', [e], H);
    const d = await db.collection('entries').find({ identifier: X }).toArray();
    const g = await req('GET', '/api/v3/entries/' + full(X), undefined, V);
    put('v1 entries POST identifier scheme://a/b/c; v3 GET <encoded>', r.s + ' | stored n=' + d.length + ' | v3 GET ' + got(g, X));
  }

  const head = fs.existsSync(path.join(DIR0, '.lab-ref')) ? fs.readFileSync(path.join(DIR0, '.lab-ref'), 'utf8').trim() : '';
  const ver = (await req('GET', '/api/v3/version')).j.result;
  console.log(JSON.stringify({ name: NAME, head, version: ver.version, apiVersion: ver.apiVersion, cells }, null, 2));
  await cli.close();
})().catch(e => { console.error(e); process.exit(1); });
