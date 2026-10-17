'use strict';
// What a Nightscout build does when a record is re-sent with the same
// `identifier` but a different `date`, `device` or `eventType`.
// Run through lab.sh; see README.md for the cases.
//
//   node probes.js <name> <build-dir> <port>   run every case, print one JSON object
//   node probes.js --drop <name> <build-dir>   drop that build's lab database
//   node probes.js --compare <a.json> <b.json>  one markdown table, a column per run
//
// Synthetic data only. Each case uses a fresh identifier, so a run can be repeated.

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

const drop = argv[0] === '--drop';
const [NAME, DIR0, PORT] = drop ? argv.slice(1) : argv;
const MODULES = path.join(path.resolve(DIR0), 'node_modules');
const { MongoClient } = require(path.join(MODULES, 'mongodb'));
const MONGO = 'mongodb://127.0.0.1:' + (process.env.V3I_MONGO_PORT || 27183);
const DB = 'v3imm_' + NAME;

if (drop) {
  MongoClient.connect(MONGO).then(async cli => { await cli.db(DB).dropDatabase(); await cli.close(); });
  return;
}

const STATE = process.env.V3I_STATE || path.join(process.env.TMPDIR || '/tmp', 'v3-identifier-immutable');
const HASH = crypto.createHash('sha1').update(fs.readFileSync(path.join(STATE, 'secret'), 'utf8').trim()).digest('hex');
const BASE = 'http://127.0.0.1:' + PORT;
const iso = t => new Date(t).toISOString();
const uuid = () => crypto.randomUUID();

async function req (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json' }, headers),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
  return { s: r.status, j, t };
}
// The reply, reduced to what a cell needs: status and the message or identifier.
const brief = r => {
  if (r.j && r.j.message) return r.s + ' "' + r.j.message + '"';
  if (r.j && r.j.identifier) return r.s + ' identifier';
  if (r.j && r.j.result && r.j.result.identifier) return r.s + ' identifier';
  return String(r.s);
};

(async () => {
  const cli = await MongoClient.connect(MONGO);
  const db = cli.db(DB);
  const now = Date.now();
  const cells = {};
  const put = (k, v) => { cells[k] = v; };

  // Times are shown relative to the run's start in seconds (t-1800 = 30 min before).
  const rel = (f, v) => (f === 'date' && typeof v === 'number') ? 't' + Math.round((v - now) / 1000)
    : (f === 'created_at' && typeof v === 'string') ? 't' + Math.round((Date.parse(v) - now) / 1000) : v;
  // Stored copies carrying the identifier, with the fields the case varies.
  const stored = async (coll, X, fields) => {
    const docs = await db.collection(coll).find({ identifier: X }).toArray();
    return 'stored n=' + docs.length + (docs.length ? ' [' + docs.map(d => fields.map(f => f + '=' + rel(f, d[f])).join(' ')).join('; ') + ']' : '');
  };

  await req('POST', '/api/v2/authorization/subjects', { name: 'v3imm-admin', roles: ['admin'] }, { 'api-secret': HASH });
  const subj = ((await req('GET', '/api/v2/authorization/subjects', undefined, { 'api-secret': HASH })).j || []).find(x => x.name === 'v3imm-admin');
  const jwt = (await req('GET', '/api/v2/authorization/request/' + subj.accessToken)).j.token;
  const V = { authorization: 'Bearer ' + jwt };

  // One record shape per collection. t is ms, device is the uploader string.
  const shapes = {
    treatments: (X, t, device, eventType) => ({ identifier: X, date: t, utcOffset: 0, app: 'v3imm-lab', device, eventType: eventType || 'Carb Correction', carbs: 20 }),
    entries: (X, t, device) => ({ identifier: X, date: t, utcOffset: 0, app: 'v3imm-lab', device, type: 'sgv', sgv: 120, direction: 'Flat' }),
    devicestatus: (X, t, device) => ({ identifier: X, date: t, utcOffset: 0, app: 'v3imm-lab', device, loop: { timestamp: iso(t) } })
  };
  const fields = { treatments: ['date', 'device', 'eventType'], entries: ['date', 'device'], devicestatus: ['date', 'device'] };

  const t1 = now - 30 * 60000;
  const phone = 'loop://lab-phone', watch = 'loop://lab-watch';

  for (const col of Object.keys(shapes)) {
    const mk = shapes[col], F = fields[col];
    const pair = async (key, first, second) => {
      const r1 = await req('POST', '/api/v3/' + col, first, V);
      const r2 = await req('POST', '/api/v3/' + col, second, V);
      put(col + ' ' + key, brief(r1) + ' -> ' + brief(r2) + ' | ' + await stored(col, first.identifier, F));
    };
    let X;
    X = uuid(); await pair('e. identical re-send (control)', mk(X, t1, phone), mk(X, t1, phone));
    X = uuid(); await pair('a. same id, date +60 s, same device', mk(X, t1, phone), mk(X, t1 + 60000, phone));
    X = uuid(); await pair('b. same id, other device, date +1.5 s', mk(X, t1, phone), mk(X, t1 + 1500, watch));
    X = uuid(); await pair('b2. same id, other device, same date', mk(X, t1, phone), mk(X, t1, watch));
    if (col === 'treatments') {
      X = uuid(); await pair('c. same id, other eventType', mk(X, t1, phone, 'Carb Correction'), mk(X, t1, phone, 'Meal Bolus'));
    }
    X = uuid();
    const r1 = await req('POST', '/api/v3/' + col, mk(X, t1, phone), V);
    const body = mk(X, t1 + 60000, phone); delete body.identifier;
    const r2 = await req('PUT', '/api/v3/' + col + '/' + X, body, V);
    put(col + ' d. PUT by id, date +60 s', brief(r1) + ' -> ' + brief(r2) + ' | ' + await stored(col, X, F));
  }

  // Contrast: v1 with the same identifier and a changed time.
  {
    const X = uuid();
    const tr = t => [{ identifier: X, eventType: 'Carb Correction', carbs: 20, created_at: iso(t), enteredBy: 'loop://lab-phone' }];
    const r1 = await req('POST', '/api/v1/treatments', tr(t1), { 'api-secret': HASH });
    const r2 = await req('POST', '/api/v1/treatments', tr(t1 + 60000), { 'api-secret': HASH });
    put('v1 treatments: same identifier, created_at +60 s', r1.s + ' -> ' + r2.s + ' | ' + await stored('treatments', X, ['created_at']));
  }
  {
    const X = uuid();
    const en = t => [{ identifier: X, type: 'sgv', sgv: 120, date: t, dateString: iso(t), device: 'loop://lab-phone' }];
    const r1 = await req('POST', '/api/v1/entries', en(t1), { 'api-secret': HASH });
    const r2 = await req('POST', '/api/v1/entries', en(t1 + 60000), { 'api-secret': HASH });
    put('v1 entries: same identifier, date +60 s', r1.s + ' -> ' + r2.s + ' | ' + await stored('entries', X, ['date']));
  }

  // f. A record first written through v1 (no device, app or date stored), then
  // re-sent through v3 with the same identifier. dev's isSameAsStored accepts a
  // first device/app and a date equal to created_at; 15.0.8 compares as stored.
  for (const [key, dt] of [['f. v1 record, then v3 same id + device, same time', 0], ['f2. v1 record, then v3 same id + device, time +60 s', 60000]]) {
    const X = uuid();
    const r1 = await req('POST', '/api/v1/treatments', [{ identifier: X, eventType: 'Carb Correction', carbs: 20, created_at: iso(t1), enteredBy: 'loop://lab-phone' }], { 'api-secret': HASH });
    const r2 = await req('POST', '/api/v3/treatments', shapes.treatments(X, t1 + dt, phone), V);
    put('treatments ' + key, r1.s + ' -> ' + brief(r2) + ' | ' + await stored('treatments', X, ['date', 'created_at', 'device']));
  }

  const head = fs.existsSync(path.join(DIR0, '.lab-ref')) ? fs.readFileSync(path.join(DIR0, '.lab-ref'), 'utf8').trim() : '';
  const ver = (await req('GET', '/api/v3/version')).j.result;
  console.log(JSON.stringify({ name: NAME, head, version: ver.version, apiVersion: ver.apiVersion, storage: ver.storage, cells }, null, 2));
  await cli.close();
})().catch(e => { console.error(e); process.exit(1); });
