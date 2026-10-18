'use strict';
// What a Nightscout build does with a client-sent `_id` and `identifier` on
// each path: v1 POST/PUT/GET/DELETE, API v3, and the socket's dbAdd, dbUpdate
// and dbRemove, for entries, treatments, devicestatus, profile and food.
// Run through lab.sh; see README.md for the cases.
//
//   node probes.js <name> <build-dir> <port>   run every case, print one JSON object
//   node probes.js --drop <name> <build-dir>   drop that build's lab database
//   node probes.js --compare <a.json> <b.json>  one markdown table, a column per run
//
// Synthetic data only. Each case uses fresh ids and times, so a run can be repeated.

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
const { MongoClient, ObjectId } = require(path.join(MODULES, 'mongodb'));
const MONGO = 'mongodb://127.0.0.1:' + (process.env.RID_MONGO_PORT || 27184);
const DB = 'ridlab_' + NAME;

if (drop) {
  MongoClient.connect(MONGO).then(async cli => { await cli.db(DB).dropDatabase(); await cli.close(); });
  return;
}

const STATE = process.env.RID_STATE || path.join(process.env.TMPDIR || '/tmp', 'record-identity');
const HASH = crypto.createHash('sha1').update(fs.readFileSync(path.join(STATE, 'secret'), 'utf8').trim()).digest('hex');
const BASE = 'http://127.0.0.1:' + PORT;
const H = { 'api-secret': HASH };
const iso = t => new Date(t).toISOString();
const uuid = () => crypto.randomUUID();
const oid = () => new ObjectId().toHexString();

async function req (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json' }, headers),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
  return { s: r.status, j, t };
}

(async () => {
  const cli = await MongoClient.connect(MONGO);
  const db = cli.db(DB);
  const cells = {};
  const put = (k, v) => { cells[k] = v; };

  // Each case gets its own minute, well inside the v1 default 4-day window.
  let slot = 0;
  // Start 1 to 2 days back (whole seconds), so every case stays inside v1's
  // default 4-day read window and a repeated run does not reuse a time.
  const t0 = Date.now() - 2 * 86400e3 + Math.floor(Math.random() * 86400) * 1000;
  const T = () => t0 + (slot++) * 60000;

  // How a stored _id is held, and whether it is the one a client sent.
  const idKind = (v, sent) => {
    const kind = (v && v._bsontype === 'ObjectId') ? 'oid' : typeof v;
    if (sent === undefined) return kind;
    return kind + (String(v).toLowerCase() === String(sent).toLowerCase() ? '=sent' : '≠sent');
  };
  const storedDocs = (coll, filter) => db.collection(coll).find(filter).toArray();
  const desc = (docs, sent, extra) => 'n=' + docs.length + (docs.length ? ' [' + docs.map(d =>
    '_id:' + idKind(d._id, sent) + (d.identifier !== undefined ? ' identifier' + (extra && extra.X !== undefined ? (d.identifier === extra.X ? '=X' : '≠X') : '') : '')
    + (d.isValid === false ? ' isValid:false' : '')
    + (extra && extra.fields ? ' ' + extra.fields.map(f => f + '=' + JSON.stringify(d[f])).join(' ') : '')).join('; ') + ']' : '');
  // A v1 reply item's _id against what was sent and what is stored.
  const replyId = (item, sent, storedId) => {
    if (!item || typeof item !== 'object') return 'no item';
    if (item._id === undefined) return 'no _id';
    const r = String(item._id);
    const tags = [];
    if (sent !== undefined && r.toLowerCase() === String(sent).toLowerCase()) tags.push('sent');
    if (storedId !== undefined && r === String(storedId)) tags.push('stored');
    return '_id=' + (tags.length ? tags.join('=') : 'other');
  };
  const first = r => Array.isArray(r.j) ? r.j[0] : r.j;
  // The error a 4xx/5xx carries: the reply's message, plus the MongoDB cause when the body names one.
  const cause = t => /E11000/.test(t) ? ' (E11000 duplicate key)' : /immutable field/.test(t) ? ' (immutable field _id)' : '';
  const msg = r => (r.s >= 400 ? ' "' + String((r.j && (r.j.message || r.j.description)) || r.t || '').slice(0, 70).replace(/\s+/g, ' ') + '"' + cause(r.t || '') : '');
  const st = r => r.s + msg(r);

  // ------------------------------------------------------------ entries v1
  const entry = (t, extra) => Object.assign({ type: 'sgv', sgv: 111, date: t, dateString: iso(t), device: 'ridlab' }, extra);
  const E = '/api/v1/entries';
  {
    const t = T(), A = oid();
    const r = await req('POST', E, [entry(t, { _id: A })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: new 24-hex _id', st(r) + ' | stored ' + desc(d, A) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid();
    await req('POST', E, [entry(t, { _id: A })], H);
    const r = await req('POST', E, [entry(t, { _id: A, sgv: 112 })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: same _id, same time (re-send)', st(r) + ' | stored ' + desc(d, A, { fields: ['sgv'] }));
  }
  {
    const t = T(), t2 = T(), A = oid();
    await req('POST', E, [entry(t, { _id: A })], H);
    const r = await req('POST', E, [entry(t2, { _id: A })], H);
    const d = await storedDocs('entries', { date: { $in: [t, t2] } });
    put('entries v1 POST: same _id, different time', st(r) + ' | stored ' + desc(d, A, { fields: ['date'] }).replace(String(t2), 't2').replace(String(t), 't1'));
  }
  {
    const t = T(), A = oid(), B = oid();
    await req('POST', E, [entry(t, { _id: A })], H);
    const r = await req('POST', E, [entry(t, { _id: B, sgv: 113 })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: different _id, same time', st(r) + ' | stored ' + desc(d, A, { fields: ['sgv'] }) + ' | reply ' + replyId(first(r), B, d[0] && d[0]._id));
  }
  {
    const t = T();
    const r1 = await req('POST', E, [entry(t)], H);
    const r = await req('POST', E, [entry(t, { sgv: 114 })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: no _id, same time twice', st(r1) + ' -> ' + st(r) + ' | stored ' + desc(d, undefined, { fields: ['sgv'] }) + ' | 1st reply ' + replyId(first(r1), undefined, d[0] && d[0]._id) + ', 2nd reply ' + replyId(first(r), undefined, d[0] && d[0]._id));
  }
  {
    const t = T(), U = uuid();
    const r = await req('POST', E, [entry(t, { _id: U })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: UUID _id', st(r) + ' | stored ' + desc(d, U, { X: U }) + ' | reply ' + replyId(first(r), U, d[0] && d[0]._id));
  }
  {
    const t = T(), S = 'ridlab-' + crypto.randomBytes(4).toString('hex');
    const r = await req('POST', E, [entry(t, { _id: S })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: non-UUID, non-hex string _id', st(r) + ' | stored ' + desc(d, S, { X: S }));
  }
  {
    const t = T(), t2 = T(), X = uuid();
    await req('POST', E, [entry(t, { identifier: X })], H);
    const r = await req('POST', E, [entry(t2, { identifier: X })], H);
    const d = await storedDocs('entries', { identifier: X });
    put('entries v1 POST: same identifier, different time', st(r) + ' | stored ' + desc(d, undefined, { X }));
  }
  {
    const t = T(), X = uuid(), Y = uuid();
    await req('POST', E, [entry(t, { identifier: X })], H);
    const r = await req('POST', E, [entry(t, { identifier: Y, sgv: 115 })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: identifier Y at the time of a stored entry with identifier X', st(r) + ' | stored n=' + d.length + ' [' + d.map(z => 'identifier=' + (z.identifier === X ? 'X' : z.identifier === Y ? 'Y' : '?') + ' sgv=' + z.sgv).join('; ') + ']');
  }
  {
    const t = T(), A = oid(), X = uuid();
    const r = await req('POST', E, [entry(t, { _id: A, identifier: X })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 POST: identifier X + new 24-hex _id', st(r) + ' | stored ' + desc(d, A, { X }) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const ta = T(), tb = T(), tc = T(), tx = T(), A = oid();
    await req('POST', E, [entry(tx, { _id: A })], H);
    const r = await req('POST', E, [entry(ta), entry(tb, { _id: A }), entry(tc)], H);
    const d = await storedDocs('entries', { date: { $in: [ta, tb, tc] } });
    put('entries v1 POST batch [new, same _id at another time, new]', st(r) + ' | of the batch stored ' + d.length + ' [' + [ta, tb, tc].map((x, i) => 'item' + (i + 1) + ':' + (d.some(z => z.date === x) ? 'yes' : 'no')).join(' ') + ']');
  }
  {
    const t = T(), A = oid(), X = uuid();
    await req('POST', E, [entry(t, { _id: A, identifier: X })], H);
    const g1 = await req('GET', '/api/v1/entries/' + A + '.json', undefined, H);
    const g2 = await req('GET', '/api/v1/entries.json?find[_id]=' + A, undefined, H);
    const g3 = await req('GET', '/api/v1/entries.json?find[identifier]=' + X, undefined, H);
    const n = r => Array.isArray(r.j) ? r.j.length : r.s;
    put('entries v1 GET: /entries/<hex>, find[_id]=<hex>, find[identifier]=X', 'found ' + n(g1) + ', ' + n(g2) + ', ' + n(g3));
  }
  {
    const t = T(), A = oid();
    await req('POST', E, [entry(t, { _id: A })], H);
    const del = await req('DELETE', '/api/v1/entries/' + A, undefined, H);
    const after = await storedDocs('entries', { date: t });
    const r = await req('POST', E, [entry(t, { _id: A })], H);
    const d = await storedDocs('entries', { date: t });
    put('entries v1 DELETE /entries/<hex>, then re-send same _id', 'delete ' + del.s + ' ' + JSON.stringify(del.j) + ', left n=' + after.length + ' | re-send ' + st(r) + ' | stored ' + desc(d, A));
  }

  // --------------------------------------------------------- treatments v1
  const tr = (t, extra) => Object.assign({ eventType: 'Carb Correction', carbs: 10, created_at: iso(t), enteredBy: 'ridlab' }, extra);
  const TR = '/api/v1/treatments';
  const trAt = t => storedDocs('treatments', { created_at: iso(t) });
  {
    const t = T(), A = oid();
    const r = await req('POST', TR, [tr(t, { _id: A })], H);
    const d = await trAt(t);
    put('treatments v1 POST: new 24-hex _id', st(r) + ' | stored ' + desc(d, A) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid();
    await req('POST', TR, [tr(t, { _id: A })], H);
    const r = await req('POST', TR, [tr(t, { _id: A, carbs: 11 })], H);
    const d = await trAt(t);
    put('treatments v1 POST: same _id, carbs changed', st(r) + ' | stored ' + desc(d, A, { fields: ['carbs'] }));
  }
  {
    const t = T(), t2 = T(), A = oid();
    await req('POST', TR, [tr(t, { _id: A })], H);
    const r = await req('POST', TR, [tr(t2, { _id: A })], H);
    const d = await storedDocs('treatments', { _id: new ObjectId(A) });
    put('treatments v1 POST: same _id, different time', st(r) + ' | stored ' + desc(d, A) + (d[0] ? ' created_at=' + (d[0].created_at === iso(t2) ? 't2' : 't1') : ''));
  }
  {
    const t = T(), A = oid(), X = uuid();
    const r = await req('POST', TR, [tr(t, { _id: A, identifier: X })], H);
    const d = await trAt(t);
    put('treatments v1 POST: identifier X + new 24-hex _id', st(r) + ' | stored ' + desc(d, A, { X }) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid(), B = oid(), X = uuid();
    await req('POST', TR, [tr(t, { _id: A, identifier: X })], H);
    const r = await req('POST', TR, [tr(t, { _id: B, identifier: X, carbs: 12 })], H);
    const d = await storedDocs('treatments', { identifier: X });
    put('treatments v1 POST: same identifier, other _id', st(r) + ' | stored ' + desc(d, B, { X, fields: ['carbs'] }) + ' | reply ' + replyId(first(r), B, d[0] && d[0]._id));
  }
  {
    const t = T(), t2 = T(), A = oid(), X = uuid(), Y = uuid();
    await req('POST', TR, [tr(t, { _id: A, identifier: X })], H);
    const s1 = await storedDocs('treatments', { identifier: X });
    const r = await req('POST', TR, [tr(t2, { _id: s1[0] && s1[0]._id.toHexString(), identifier: Y })], H);
    const d = await storedDocs('treatments', { identifier: { $in: [X, Y] } });
    put('treatments v1 POST: stored record\'s _id with a new identifier Y', st(r) + ' | stored n=' + d.length + ' [' + d.map(z => 'identifier=' + (z.identifier === X ? 'X' : z.identifier === Y ? 'Y' : '?')).sort().join('; ') + ']');
  }
  {
    const t = T(), U = uuid();
    const r = await req('POST', TR, [tr(t, { _id: U })], H);
    const d = await trAt(t);
    put('treatments v1 POST: UUID _id', st(r) + ' | stored ' + desc(d, U, { X: U }) + ' | reply ' + replyId(first(r), U, d[0] && d[0]._id));
  }
  {
    const t = T(), S = 'ridlab-' + crypto.randomBytes(4).toString('hex');
    const r = await req('POST', TR, [tr(t, { _id: S })], H);
    const d = await trAt(t);
    put('treatments v1 POST: non-UUID, non-hex string _id', st(r) + ' | stored ' + desc(d, S, { X: S }));
  }
  {
    const t = T();
    const r1 = await req('POST', TR, [tr(t)], H);
    const r = await req('POST', TR, [tr(t)], H);
    const d = await trAt(t);
    put('treatments v1 POST: no ids, identical body twice', st(r) + ' | stored ' + desc(d) + ' | 1st reply ' + replyId(first(r1), undefined, d[0] && d[0]._id) + ', 2nd reply ' + replyId(first(r), undefined, d[0] && d[0]._id));
  }
  {
    const t = T();
    await req('POST', TR, [tr(t)], H);
    const r = await req('POST', TR, [tr(t, { carbs: 25 })], H);
    const d = await trAt(t);
    put('treatments v1 POST: no ids, same time + eventType, other carbs', st(r) + ' | stored ' + desc(d, undefined, { fields: ['carbs'] }));
  }
  {
    const t = T(), X = uuid();
    const r1 = await req('POST', TR, tr(t, { identifier: X }), H);
    const r = await req('POST', TR, tr(t, { identifier: X, carbs: 13 }), H);
    const d = await storedDocs('treatments', { identifier: X });
    put('treatments v1 POST (single object): same identifier twice', st(r) + ' | stored ' + desc(d, undefined, { X, fields: ['carbs'] }) + ' | 1st reply ' + replyId(first(r1), undefined, d[0] && d[0]._id) + ', 2nd reply ' + replyId(first(r), undefined, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid();
    await req('POST', TR, [tr(t, { _id: A })], H);
    const r = await req('PUT', TR, tr(t, { _id: A, carbs: 14 }), H);
    const d = await trAt(t);
    put('treatments v1 PUT: by 24-hex _id', st(r) + ' | stored ' + desc(d, A, { fields: ['carbs'] }) + ' | reply ' + replyId(r.j, A, d[0] && d[0]._id));
  }
  {
    const t = T(), X = uuid();
    await req('POST', TR, [tr(t, { identifier: X })], H);
    const r = await req('PUT', TR, tr(t, { identifier: X, carbs: 15 }), H);
    const d = await storedDocs('treatments', { identifier: X });
    put('treatments v1 PUT: by identifier, no _id', st(r) + ' | stored ' + desc(d, undefined, { X, fields: ['carbs'] }) + ' | reply ' + replyId(r.j, undefined, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid(), X = uuid(), U1 = uuid(), U2 = uuid().toUpperCase();
    await req('POST', TR, [tr(t, { _id: A, identifier: X })], H);
    await req('POST', TR, [tr(T(), { _id: U1 })], H);
    await req('POST', TR, [tr(T(), { _id: U2 })], H);
    const n = r => Array.isArray(r.j) ? r.j.length : r.s;
    const g1 = await req('GET', TR + '.json?find[_id]=' + A, undefined, H);
    const g2 = await req('GET', TR + '.json?find[identifier]=' + X, undefined, H);
    const g3 = await req('GET', TR + '.json?find[_id]=' + U1, undefined, H);
    const g4 = await req('GET', TR + '.json?find[_id]=' + U2, undefined, H);
    const g5 = await req('GET', TR + '.json?find[_id]=' + U1.toUpperCase(), undefined, H);
    const g6 = await req('GET', TR + '.json?find[_id]=' + U2.toLowerCase(), undefined, H);
    put('treatments v1 GET: find[_id]=<hex sent beside identifier>, find[identifier]=X, find[_id]=<lower-case UUID sent as _id>, <upper-case UUID sent as _id>, the first asked upper-case, the second asked lower-case', 'found ' + [g1, g2, g3, g4, g5, g6].map(n).join(', '));
  }
  {
    const t = T(), X = uuid();
    await req('POST', TR, [tr(t, { identifier: X })], H);
    const del = await req('DELETE', TR + '/' + X, undefined, H);
    const left = await storedDocs('treatments', { identifier: X });
    const r = await req('POST', TR, [tr(t, { identifier: X })], H);
    const d = await storedDocs('treatments', { identifier: X });
    put('treatments v1 DELETE /treatments/<uuid identifier>, then re-send', 'delete ' + del.s + ' ' + JSON.stringify(del.j) + ', left n=' + left.length + ' | re-send ' + st(r) + ' | stored ' + desc(d, undefined, { X }));
  }
  {
    const t = T(), S = 'ridlab:' + crypto.randomBytes(4).toString('hex');
    await req('POST', TR, [tr(t, { identifier: S })], H);
    const del = await req('DELETE', TR + '/' + encodeURIComponent(S), undefined, H);
    const left = await storedDocs('treatments', { identifier: S });
    const g = await req('GET', TR + '.json?find[identifier]=' + encodeURIComponent(S), undefined, H);
    put('treatments v1 DELETE /treatments/<non-UUID identifier>; GET find[identifier]', 'delete ' + del.s + ' ' + JSON.stringify(del.j) + ', left n=' + left.length + ' | GET found ' + (Array.isArray(g.j) ? g.j.length : g.s));
  }
  {
    const t = T(), A = oid();
    await req('POST', TR, [tr(t, { _id: A })], H);
    const del = await req('DELETE', TR + '/' + A, undefined, H);
    const r = await req('POST', TR, [tr(t, { _id: A })], H);
    const d = await trAt(t);
    put('treatments v1 DELETE /treatments/<hex>, then re-send same _id', 'delete ' + del.s + ' ' + JSON.stringify(del.j) + ' | re-send ' + st(r) + ' | stored ' + desc(d, A));
  }

  // ------------------------------------------------------- devicestatus v1
  const ds = (t, extra) => Object.assign({ device: 'ridlab', created_at: iso(t), uploaderBattery: 50 }, extra);
  const DS = '/api/v1/devicestatus';
  const dsAt = t => storedDocs('devicestatus', { created_at: iso(t) });
  {
    const t = T(), A = oid();
    const r = await req('POST', DS, [ds(t, { _id: A })], H);
    const d = await dsAt(t);
    put('devicestatus v1 POST: new 24-hex _id', st(r) + ' | stored ' + desc(d, A) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const t = T(), A = oid();
    await req('POST', DS, [ds(t, { _id: A })], H);
    const r = await req('POST', DS, [ds(t, { _id: A })], H);
    const d = await dsAt(t);
    put('devicestatus v1 POST: same _id re-sent', st(r) + ' | stored ' + desc(d, A) + ' | reply ' + replyId(first(r), A, d[0] && d[0]._id));
  }
  {
    const ta = T(), tb = T(), tc = T(), A = oid();
    await req('POST', DS, [ds(tb, { _id: A })], H);
    const r = await req('POST', DS, [ds(ta), ds(tb, { _id: A }), ds(tc)], H);
    const d = await storedDocs('devicestatus', { created_at: { $in: [iso(ta), iso(tb), iso(tc)] } });
    const has = x => d.filter(z => z.created_at === iso(x)).length;
    put('devicestatus v1 POST batch [new, re-sent _id, new]', st(r) + ' | stored per item [' + [ta, tb, tc].map((x, i) => 'item' + (i + 1) + ':' + has(x)).join(' ') + ']');
  }
  {
    const t = T();
    await req('POST', DS, [ds(t)], H);
    const r = await req('POST', DS, [ds(t)], H);
    const d = await dsAt(t);
    put('devicestatus v1 POST: no _id, identical body twice', st(r) + ' | stored ' + desc(d));
  }
  {
    const t = T(), X = uuid();
    await req('POST', DS, [ds(t, { identifier: X })], H);
    const r = await req('POST', DS, [ds(t, { identifier: X })], H);
    const d = await storedDocs('devicestatus', { identifier: X });
    put('devicestatus v1 POST: same identifier twice', st(r) + ' | stored ' + desc(d, undefined, { X }));
  }
  {
    const t = T(), U = uuid();
    const r = await req('POST', DS, [ds(t, { _id: U })], H);
    const d = await dsAt(t);
    put('devicestatus v1 POST: UUID _id', st(r) + ' | stored ' + desc(d, U, { X: U }));
  }
  {
    const t = T(), A = oid();
    await req('POST', DS, [ds(t, { _id: A })], H);
    const g = await req('GET', DS + '.json?find[_id]=' + A, undefined, H);
    const del = await req('DELETE', DS + '/' + A, undefined, H);
    const left = await dsAt(t);
    put('devicestatus v1 GET find[_id]=<hex>, then DELETE /devicestatus/<hex>', 'GET found ' + (Array.isArray(g.j) ? g.j.length : g.s) + ' | delete ' + del.s + ' ' + JSON.stringify(del.j) + ', left n=' + left.length);
  }

  // ------------------------------------------------------- profile v1
  const pf = (extra) => Object.assign({ defaultProfile: 'Default', startDate: iso(T()), units: 'mg/dl', store: { Default: { dia: 3, timezone: 'UTC', units: 'mg/dl', carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }], basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }] } } }, extra);
  {
    const A = oid(), body = pf({ _id: A });
    const r = await req('POST', '/api/v1/profile', body, H);
    const d = await storedDocs('profile', { startDate: body.startDate });
    const p = await req('PUT', '/api/v1/profile', Object.assign({}, body, { defaultProfile: 'Edited' }), H);
    const d2 = await storedDocs('profile', { startDate: body.startDate });
    put('profile v1 POST new 24-hex _id, then PUT same _id', 'POST ' + st(r) + ' stored ' + desc(d, A) + ' | PUT ' + st(p) + ' stored ' + desc(d2, A, { fields: ['defaultProfile'] }));
  }
  {
    const A = oid(), body = pf({ _id: A });
    await req('POST', '/api/v1/profile', body, H);
    const r = await req('POST', '/api/v1/profile', body, H);
    const d = await storedDocs('profile', { startDate: body.startDate });
    put('profile v1 POST: same _id re-sent', st(r) + ' | stored ' + desc(d, A));
  }
  {
    const r = await req('POST', '/api/v1/profile', pf({ _id: uuid() }), H);
    put('profile v1 POST: UUID _id', st(r));
  }

  // ------------------------------------------------------- food v1
  const fd = (extra) => Object.assign({ type: 'food', name: 'ridlab-' + crypto.randomBytes(3).toString('hex'), carbs: 10, portion: 1, unit: 'g' }, extra);
  {
    const A = oid(), body = fd({ _id: A });
    const r = await req('POST', '/api/v1/food', body, H);
    const d = await storedDocs('food', { name: body.name });
    const p = await req('PUT', '/api/v1/food', Object.assign({}, body, { carbs: 11 }), H);
    const d2 = await storedDocs('food', { name: body.name });
    put('food v1 POST new 24-hex _id, then PUT same _id', 'POST ' + st(r) + ' stored ' + desc(d, A) + ' | PUT ' + st(p) + ' stored ' + desc(d2, A, { fields: ['carbs'] }));
  }
  {
    const r = await req('POST', '/api/v1/food', fd({ _id: uuid() }), H);
    put('food v1 POST: UUID _id', st(r));
  }

  // ------------------------------------------------------------ API v3
  await req('POST', '/api/v2/authorization/subjects', { name: 'ridlab-admin', roles: ['admin'] }, H);
  const subj = ((await req('GET', '/api/v2/authorization/subjects', undefined, H)).j || []).find(x => x.name === 'ridlab-admin');
  const jwt = (await req('GET', '/api/v2/authorization/request/' + subj.accessToken)).j.token;
  const V = { authorization: 'Bearer ' + jwt };
  const v3tr = (t, extra) => Object.assign({ date: t, utcOffset: 0, app: 'ridlab', device: 'ridlab-dev', eventType: 'Carb Correction', carbs: 10 }, extra);
  const v3brief = r => r.s + (r.j && r.j.message ? ' "' + r.j.message + '"' : '') + (r.j && r.j.identifier ? ' identifier' : '') + (r.j && r.j._id ? ' _id' : '') + (r.j && r.j.isDeduplication ? ' isDeduplication' : '');
  const uuidMod = require(path.join(MODULES, 'uuid'));
  const NS = [...Buffer.from('NightscoutRocks!', 'ascii')];
  {
    const t = T();
    const r = await req('POST', '/api/v3/treatments', v3tr(t), V);
    const d = await storedDocs('treatments', { date: t });
    const expect = uuidMod.v5('ridlab-dev_' + t + '_Carb Correction', NS);
    put('v3 treatments POST: no identifier', v3brief(r) + ' | stored ' + desc(d) + ' | identifier ' + (d[0] && d[0].identifier === expect ? '= uuid.v5(device_date_eventType)' : 'other: ' + (d[0] && d[0].identifier)) + ' | reply keys ' + Object.keys(r.j || {}).join(','));
  }
  {
    const t = T(), A = oid(), X = uuid();
    const r = await req('POST', '/api/v3/treatments', v3tr(t, { identifier: X, _id: A }), V);
    const d = await storedDocs('treatments', { date: t });
    put('v3 treatments POST: identifier + 24-hex _id in body', v3brief(r) + ' | stored ' + desc(d, A, { X }));
  }
  {
    const t = T(), A = oid();
    const r = await req('POST', '/api/v3/treatments', v3tr(t, { _id: A }), V);
    const d = await storedDocs('treatments', { date: t });
    put('v3 treatments POST: 24-hex _id in body, no identifier', v3brief(r) + ' | stored ' + desc(d, A));
  }
  {
    const t = T(), A = oid();
    await req('POST', TR, [tr(t, { _id: A })], H);
    const g = await req('GET', '/api/v3/treatments/' + A, undefined, V);
    const r = await req('POST', '/api/v3/treatments', v3tr(t, { identifier: A }), V);
    const d = await storedDocs('treatments', { created_at: iso(t) });
    put('v3 GET /treatments/<hex _id of a v1 record>; then v3 POST identifier=<that hex>', 'GET ' + g.s + (g.j && g.j.result ? ' identifier=' + (g.j.result.identifier === A ? 'hex' : g.j.result.identifier) + (g.j.result._id ? ' _id present' : ' no _id') : '') + ' | POST ' + v3brief(r) + ' | stored ' + desc(d, A, { X: A }));
  }
  for (const col of ['treatments', 'entries', 'devicestatus']) {
    const mk = (t, X) => col === 'treatments' ? v3tr(t, { identifier: X })
      : col === 'entries' ? { identifier: X, date: t, utcOffset: 0, app: 'ridlab', device: 'ridlab-dev', type: 'sgv', sgv: 120 }
        : { identifier: X, date: t, utcOffset: 0, app: 'ridlab', device: 'ridlab-dev', uploaderBattery: 40 };
    {
      const t = T(), X = uuid();
      await req('POST', '/api/v3/' + col, mk(t, X), V);
      const del = await req('DELETE', '/api/v3/' + col + '/' + X, undefined, V);
      const g = await req('GET', '/api/v3/' + col + '/' + X, undefined, V);
      const p = await req('PUT', '/api/v3/' + col + '/' + X, mk(t, X), V);
      const r = await req('POST', '/api/v3/' + col, mk(t, X), V);
      const d = await storedDocs(col, { identifier: X });
      put('v3 ' + col + ' soft DELETE, then GET, PUT, POST same identifier', 'delete ' + del.s + ' | GET ' + g.s + ' | PUT ' + v3brief(p) + ' | POST ' + v3brief(r) + ' | stored ' + desc(d, undefined, { X }));
    }
    {
      const t = T(), X = uuid();
      await req('POST', '/api/v3/' + col, mk(t, X), V);
      const del = await req('DELETE', '/api/v3/' + col + '/' + X + '?permanent=true', undefined, V);
      const r = await req('POST', '/api/v3/' + col, mk(t, X), V);
      const d = await storedDocs(col, { identifier: X });
      put('v3 ' + col + ' permanent DELETE, then POST same identifier', 'delete ' + del.s + ' | POST ' + v3brief(r) + ' | stored ' + desc(d, undefined, { X }));
    }
  }
  {
    const t = T(), X = uuid();
    await req('POST', '/api/v3/treatments', v3tr(t, { identifier: X }), V);
    await req('DELETE', '/api/v3/treatments/' + X, undefined, V);
    const r = await req('POST', '/api/v3/treatments', v3tr(t + 60000, { identifier: X, device: 'ridlab-other' }), V);
    const d = await storedDocs('treatments', { identifier: X });
    put('v3 treatments soft DELETE, then POST same identifier with date +60 s and another device', v3brief(r) + ' | stored ' + desc(d, undefined, { X }) + (d[0] ? ' date=' + (d[0].date === t + 60000 ? 't+60s' : d[0].date === t ? 't' : d[0].date) + ' device=' + d[0].device : ''));
  }
  {
    const t = T(), X = uuid();
    await req('POST', '/api/v3/treatments', v3tr(t, { identifier: X }), V);
    await req('DELETE', '/api/v3/treatments/' + X, undefined, V);
    const r = await req('POST', TR, [tr(t, { identifier: X, eventType: 'Carb Correction' })], H);
    const d = await storedDocs('treatments', { identifier: X });
    const g = await req('GET', TR + '.json?find[identifier]=' + X, undefined, H);
    put('v3 soft DELETE treatment, then v1 POST same identifier', st(r) + ' | stored ' + desc(d, undefined, { X }) + ' | v1 GET found ' + (Array.isArray(g.j) ? g.j.length : g.s));
  }

  // ------------------------------------------------------------ socket
  const { io } = require(path.join(MODULES, 'socket.io-client'));
  const sock = io(BASE, { transports: ['websocket'], reconnection: false });
  await new Promise((res, rej) => { sock.on('connect', res); sock.on('connect_error', rej); setTimeout(() => rej(new Error('socket connect timeout')), 10000); });
  const emit = (ev, payload) => new Promise(res => { const to = setTimeout(() => res({ timeout: true }), 8000); sock.emit(ev, payload, r => { clearTimeout(to); res(r); }); });
  const auth = await emit('authorize', { client: 'ridlab', secret: HASH, history: 1 });
  const sBrief = r => Array.isArray(r) ? (r.length ? '[' + r.length + ' item' + (r.length > 1 ? 's' : '') + ']' : '[]') : JSON.stringify(r);
  put('socket authorize', auth && auth.write ? 'write' : JSON.stringify(auth).slice(0, 80));
  {
    const t = T(), A = oid();
    const r = await emit('dbAdd', { collection: 'treatments', data: tr(t, { _id: A }) });
    const d = await trAt(t);
    const u = await emit('dbUpdate', { collection: 'treatments', _id: A, data: { carbs: 33 } });
    const d2 = await trAt(t);
    const rm = await emit('dbRemove', { collection: 'treatments', _id: A });
    const d3 = await trAt(t);
    put('socket treatments dbAdd 24-hex _id; dbUpdate and dbRemove by it', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d, A) + ' | dbUpdate ' + JSON.stringify(u) + ' carbs=' + (d2[0] && d2[0].carbs) + ' | dbRemove ' + JSON.stringify(rm) + ' left n=' + d3.length);
  }
  {
    const t = T(), U = uuid();
    const r = await emit('dbAdd', { collection: 'treatments', data: tr(t, { _id: U }) });
    const d = await trAt(t);
    put('socket treatments dbAdd UUID _id', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d, U, { X: U }));
  }
  {
    const t = T(), t2 = T(), X = uuid();
    await emit('dbAdd', { collection: 'treatments', data: tr(t, { identifier: X }) });
    const r = await emit('dbAdd', { collection: 'treatments', data: tr(t2, { identifier: X }) });
    const d = await storedDocs('treatments', { identifier: X });
    put('socket treatments dbAdd same identifier, time +60 s', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d, undefined, { X }));
  }
  {
    const t = T();
    await emit('dbAdd', { collection: 'entries', data: entry(t) });
    const r = await emit('dbAdd', { collection: 'entries', data: entry(t) });
    const d = await storedDocs('entries', { date: t });
    put('socket entries dbAdd identical body twice', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d));
  }
  {
    const t = T(), A = oid();
    await emit('dbAdd', { collection: 'entries', data: entry(t, { _id: A }) });
    const r = await emit('dbAdd', { collection: 'entries', data: entry(t, { _id: A }) });
    const d = await storedDocs('entries', { date: t });
    put('socket entries dbAdd same 24-hex _id twice', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d, A));
  }
  {
    const t = T();
    await emit('dbAdd', { collection: 'devicestatus', data: ds(t) });
    const r = await emit('dbAdd', { collection: 'devicestatus', data: ds(t, { uploaderBattery: 49 }) });
    const d = await dsAt(t);
    put('socket devicestatus dbAdd same created_at twice', 'dbAdd ' + sBrief(r) + ' stored ' + desc(d, undefined, { fields: ['uploaderBattery'] }));
  }
  sock.close();

  const head = fs.existsSync(path.join(DIR0, '.lab-ref')) ? fs.readFileSync(path.join(DIR0, '.lab-ref'), 'utf8').trim() : '';
  const ver = (await req('GET', '/api/v3/version')).j.result;
  console.log(JSON.stringify({ name: NAME, head, version: ver.version, apiVersion: ver.apiVersion, storage: ver.storage, cells }, null, 2));
  await cli.close();
})().catch(e => { console.error(e); process.exit(1); });
