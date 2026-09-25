'use strict';
// Probes for how a Nightscout build treats a record's own _id, in the shapes
// real clients send. Run through lab.sh; see README.md for what each cell means.
//
//   node probes.js <name> <build-dir> <port>   run every probe, print one JSON object
//                                              (OID_PROBES=P-ID-10,P-ID-11 runs only those; P-ID-0 always runs)
//   node probes.js --drop <name> <build-dir>   drop that build's lab database
//   node probes.js --compare <out-dir>         tabulate <out-dir>/*.json cell by cell
//
// Every cell is a short string. The shared vocabulary:
//   OID / string    the BSON type of a stored _id
//   n=<k>           how many stored documents carry that hex, in either form
//   notes=<v>       which copy took the write (each seed has a distinct marker)
// Seeds that stand for data older releases left behind are written straight to
// mongo; everything else goes through the build's own HTTP or websocket API.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const argv = process.argv.slice(2);

if (argv[0] === '--compare') {
  const dir = argv[1];
  const runs = fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort()
    .map(f => ({ name: path.basename(f, '.json'), out: JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) }));
  const cells = [];
  runs.forEach(r => Object.keys(r.out.cells).forEach(k => { if (!cells.includes(k)) cells.push(k); }));
  console.log('| cell | ' + runs.map(r => r.name + ' `' + r.out.head + '`').join(' | ') + ' | differs |');
  console.log('|---|' + runs.map(() => '---').join('|') + '|---|');
  for (const k of cells) {
    const vs = runs.map(r => r.out.cells[k] === undefined ? '—' : String(r.out.cells[k]));
    console.log('| ' + k + ' | ' + vs.map(v => v.replace(/\|/g, '\\|')).join(' | ') + ' | ' + (new Set(vs).size > 1 ? 'yes' : '') + ' |');
  }
  process.exit(0);
}

const drop = argv[0] === '--drop';
const [NAME, DIR0, PORT] = drop ? argv.slice(1) : argv;
const DIR = path.resolve(DIR0);
const MODULES = path.join(DIR, 'node_modules');
const { MongoClient, ObjectId } = require(path.join(MODULES, 'mongodb'));
const MONGO = 'mongodb://127.0.0.1:' + (process.env.OID_MONGO_PORT || 27181);
const DB = 'oidlab_' + NAME;

if (drop) {
  MongoClient.connect(MONGO).then(async cli => { await cli.db(DB).dropDatabase(); await cli.close(); });
  return;
}

const io = require(path.join(MODULES, 'socket.io-client'));
const STATE = process.env.OID_STATE || path.join(process.env.TMPDIR || '/tmp', 'object-id-lab');
const HASH = crypto.createHash('sha1').update(fs.readFileSync(path.join(STATE, 'secret'), 'utf8').trim()).digest('hex');
const BASE = 'http://127.0.0.1:' + PORT;
const H = { 'api-secret': HASH, 'content-type': 'application/json' };

const hex = () => crypto.randomBytes(12).toString('hex');
const form = v => v instanceof ObjectId ? 'OID' : typeof v;
const idq = h => ({ _id: { $in: [h, new ObjectId(h)] } });
const iso = t => new Date(t).toISOString();

async function req (method, p, body, extra) {
  const r = await fetch(BASE + p, { method, headers: Object.assign({}, H, extra || {}), body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
  return { s: r.status, j, t: t.slice(0, 120) };
}
const len = r => Array.isArray(r.j) ? 'n=' + r.j.length : r.t;

function sock () {
  return new Promise((resolve, reject) => {
    const s = io(BASE, { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('authorize', { client: 'web', secret: HASH, history: 0 }, () => resolve(s)));
    s.on('connect_error', reject);
    setTimeout(() => reject(new Error('socket timeout')), 8000);
  });
}
const emit = (s, ev, d) => new Promise(resolve => {
  const t = setTimeout(() => resolve('NO-ACK'), 5000);
  s.emit(ev, d, a => { clearTimeout(t); resolve(a); });
});
const ack = a => JSON.stringify(a).slice(0, 40);
const WANT = process.env.OID_PROBES ? process.env.OID_PROBES.split(',') : null;
const want = p => !WANT || WANT.includes(p);

(async () => {
  const cli = await MongoClient.connect(MONGO);
  const db = cli.db(DB);
  const now = Date.now();
  const cells = {};
  const put = (probe, cell, v) => { cells[probe + ' ' + cell] = Array.isArray(v) ? v.join(' / ') : String(v); };
  const stored = async (coll, h, field) => (await db.collection(coll).find(idq(h)).toArray())
    .map(d => form(d._id) + (field ? ':' + d[field] : '')).join(',') || 'none';
  const count = async (coll, h) => 'n=' + await db.collection(coll).countDocuments(idq(h));

  put('P-ID-0', 'liveness before', (await req('GET', '/api/v1/status.json')).s);

  // P-ID-1 Loop: re-POST of a dose with the ObjectId it cached from an earlier reply,
  // onto a record stored as a string (<=15.0.6); ObjectId-stored control.
  // xDrip4iOS: the LibreLinkUp Sensor Start carries a deterministic hex _id and is retried.
  if (want('P-ID-1')) {
    const c = db.collection('treatments');
    const hs = hex(); const ca = iso(now - 90 * 60000);
    await c.insertOne({ _id: hs, eventType: 'Temp Basal', rate: 0.5, absolute: 0.5, duration: 30, created_at: ca, enteredBy: 'loop://lab' });
    const r = await req('POST', '/api/v1/treatments', [{ _id: hs, eventType: 'Temp Basal', rate: 0.8, absolute: 0.8, duration: 30, created_at: ca, enteredBy: 'loop://lab' }]);
    put('P-ID-1', 'loop cached id onto string record', [r.s, await stored('treatments', hs, 'rate')]);
    const ho = hex(); const ca2 = iso(now - 85 * 60000);
    await c.insertOne({ _id: new ObjectId(ho), eventType: 'Temp Basal', rate: 0.5, absolute: 0.5, duration: 30, created_at: ca2, enteredBy: 'loop://lab' });
    const r2 = await req('POST', '/api/v1/treatments', [{ _id: ho, eventType: 'Temp Basal', rate: 0.9, absolute: 0.9, duration: 30, created_at: ca2, enteredBy: 'loop://lab' }]);
    put('P-ID-1', 'loop cached id onto OID record (control)', [r2.s, await stored('treatments', ho, 'rate')]);
    const ts = now - 3 * 86400000; const sid = '6c6c75000000' + ts.toString(16).padStart(12, '0');
    const ss = { _id: sid, eventType: 'Sensor Start', created_at: iso(ts), enteredBy: 'lab-xdripswift' };
    const s1 = await req('POST', '/api/v1/treatments', ss); const s2 = await req('POST', '/api/v1/treatments', ss);
    put('P-ID-1', 'xdripswift sensor start retried', [s1.s, s2.s, await stored('treatments', sid)]);
  }

  // P-ID-2 API v3 identifier addressing of v1 records (AAPS 4.x; it treats 404 as done).
  let V;
  {
    await req('POST', '/api/v2/authorization/subjects', { name: 'oidlab-admin', roles: ['admin'] });
    const subj = ((await req('GET', '/api/v2/authorization/subjects')).j || []).find(x => x.name === 'oidlab-admin');
    const jwt = (await req('GET', '/api/v2/authorization/request/' + subj.accessToken)).j.token;
    V = { authorization: 'Bearer ' + jwt };
  }
  if (want('P-ID-2')) {
    const c = db.collection('treatments'); const t = now - 10 * 60000;
    const hs = hex(); const hs2 = hex(); const ho = hex();
    await c.insertOne({ _id: hs, eventType: 'Note', notes: 'legacy', created_at: iso(t), date: t, utcOffset: 0 });
    await c.insertOne({ _id: hs2, eventType: 'Note', notes: 'legacy2', created_at: iso(t + 1000), date: t + 1000, utcOffset: 0 });
    await c.insertOne({ _id: new ObjectId(ho), eventType: 'Note', notes: 'oid', created_at: iso(t + 2000), date: t + 2000, utcOffset: 0 });
    put('P-ID-2', 'GET string record', (await req('GET', '/api/v3/treatments/' + hs, undefined, V)).s);
    put('P-ID-2', 'GET OID record (control)', (await req('GET', '/api/v3/treatments/' + ho, undefined, V)).s);
    const p = await req('PATCH', '/api/v3/treatments/' + hs, { notes: 'v3-patch' }, V);
    put('P-ID-2', 'PATCH string record', [p.s, await stored('treatments', hs, 'notes')]);
    const d = await req('DELETE', '/api/v3/treatments/' + hs2, undefined, V);
    put('P-ID-2', 'DELETE string record', [d.s, await stored('treatments', hs2, 'isValid')]);
    const uu = crypto.randomUUID().toUpperCase();
    await c.insertOne({ _id: uu, eventType: 'Temporary Override', created_at: iso(t + 3000), date: t + 3000, utcOffset: 0 });
    const pu = await req('PATCH', '/api/v3/treatments/' + uu, { notes: 'v3-uuid' }, V);
    put('P-ID-2', 'PATCH UUID-string record', [pu.s, 'docs at that time n=' + await c.countDocuments({ date: t + 3000 })]);
  }

  // P-ID-3 entries: re-send with no _id, with a different hex, onto a string record; upper-case GET.
  if (want('P-ID-3')) {
    const T1 = now - 60 * 60000; const T2 = now - 55 * 60000; const T3 = now - 50 * 60000;
    const e = (t, extra) => Object.assign({ type: 'sgv', sgv: 111, date: t, dateString: iso(t), device: 'lab' }, extra || {});
    let r = await req('POST', '/api/v1/entries', [e(T1)]);
    const firstId = r.j && r.j[0] && r.j[0]._id;
    put('P-ID-3', 'POST without _id', [r.s, firstId ? 'reply has _id' : 'reply no _id']);
    r = await req('POST', '/api/v1/entries', [e(T1, { sgv: 112 })]);
    put('P-ID-3', 're-send without _id', [r.s, !r.j || !r.j[0] || r.j[0]._id === undefined || r.j[0]._id === null ? 'reply no _id' : (r.j[0]._id === firstId ? 'reply = stored' : 'reply other')]);
    const h1 = hex(); const h2 = hex();
    await req('POST', '/api/v1/entries', [e(T2, { _id: h1 })]);
    r = await req('POST', '/api/v1/entries', [e(T2, { _id: h2, sgv: 113 })]);
    const got = r.j && r.j[0] ? (r.j[0]._id === h2 ? 'reply = sent' : r.j[0]._id === h1 ? 'reply = stored' : 'reply other') : 'no reply body';
    const st = (await db.collection('entries').find({ date: T2 }).toArray()).map(x => (String(x._id) === h1 ? 'stored' : String(x._id) === h2 ? 'sent' : '?') + ':sgv' + x.sgv).join(',');
    put('P-ID-3', 're-send with a different hex _id', [r.s, got, st]);
    const hs = hex();
    await db.collection('entries').insertOne({ _id: hs, type: 'sgv', sgv: 120, date: T3, dateString: iso(T3), sysTime: iso(T3), utcOffset: 0, device: 'legacy' });
    r = await req('POST', '/api/v1/entries', [e(T3, { _id: hs, sgv: 121 })]);
    put('P-ID-3', 're-send onto a string record', [r.s, await stored('entries', hs, 'sgv')]);
    put('P-ID-3', 'GET /entries/<UPPER>', len(await req('GET', '/api/v1/entries/' + String(firstId).toUpperCase() + '.json')));
    put('P-ID-3', 'GET /entries/<lower> (control)', len(await req('GET', '/api/v1/entries/' + String(firstId) + '.json')));
  }

  // P-ID-4 websocket (web UI editor, AAPS 3.x NSClient).
  if (want('P-ID-4')) {
    const s = await sock(); const c = db.collection('treatments');
    const hs = hex();
    await c.insertOne({ _id: hs, eventType: 'Note', notes: 'orig', created_at: iso(now - 40 * 60000) });
    let a = await emit(s, 'dbUpdate', { collection: 'treatments', _id: hs, data: { notes: 'ws-edit' } });
    put('P-ID-4', 'dbUpdate string record', [ack(a), await stored('treatments', hs, 'notes')]);
    a = await emit(s, 'dbRemove', { collection: 'treatments', _id: hs });
    put('P-ID-4', 'dbRemove string record', [ack(a), await count('treatments', hs)]);
    const hn = hex();
    a = await emit(s, 'dbAdd', { collection: 'treatments', data: { _id: hn, eventType: 'Note', notes: 'add', created_at: iso(now - 30 * 60000) } });
    put('P-ID-4', 'dbAdd with hex _id', [Array.isArray(a) && a[0] ? (String(a[0]._id) === hn ? 'ack = sent' : 'ack other') : ack(a), await stored('treatments', hn)]);
    await emit(s, 'dbUpdate', { collection: 'treatments', _id: hn, data: { notes: 'add-edit' } });
    put('P-ID-4', 'dbUpdate after dbAdd', await stored('treatments', hn, 'notes'));
    a = await emit(s, 'dbAdd', { collection: 'treatments', data: { eventType: 'Note', notes: 'aaps', created_at: iso(now - 20 * 60000) } });
    const aid = Array.isArray(a) && a[0] && String(a[0]._id);
    await emit(s, 'dbUpdate', { collection: 'treatments', _id: aid, data: { notes: 'aaps-edit' } });
    put('P-ID-4', 'AAPS 3.x add then update (control)', await stored('treatments', aid, 'notes'));
    const hf = hex();
    await emit(s, 'dbAdd', { collection: 'food', data: { _id: hf, type: 'food', name: 'lab', carbs: 10 } });
    put('P-ID-4', 'dbAdd food with hex _id', await stored('food', hf));
    s.close();
  }

  // P-ID-5 connector 0.1.0's profile guard (find[_id] must return the copy before it PUTs),
  // P-ID-6 restore from an export (POST the same record twice).
  if (want('P-ID-5') || want('P-ID-6')) {
    const hp = hex(); const sd = iso(now - 86400000);
    const sched = v => [{ time: '00:00', value: v }];
    const prof = { _id: hp, defaultProfile: 'Default', startDate: sd, created_at: sd, mills: now - 86400000, units: 'mg/dl', store: { Default: { dia: 5, carbratio: sched(10), sens: sched(50), basal: sched(1), target_low: sched(100), target_high: sched(110), timezone: 'UTC', units: 'mg/dl' } } };
    let r = await req('POST', '/api/v1/profile', prof);
    put('P-ID-5', 'profile copied with its _id', [r.s, await stored('profile', hp)]);
    const found = len(await req('GET', '/api/v1/profiles.json?find[_id]=' + hp + '&count=10'));
    put('P-ID-5', 'connector guard find[_id]', found);
    if (found === 'n=1') {
      const p2 = JSON.parse(JSON.stringify(prof)); p2.store.Default.dia = 6;
      r = await req('PUT', '/api/v1/profile.json', p2);
      put('P-ID-5', 'connector update PUT', [r.s, await count('profile', hp)]);
    } else put('P-ID-5', 'connector update PUT', 'skipped (connector logs NOT_REPLACED)');
    r = await req('POST', '/api/v1/profile', prof);
    put('P-ID-6', 'profile re-POST', [r.s, await stored('profile', hp)]);
    const docs = { devicestatus: { device: 'lab', created_at: iso(now), uploaderBattery: 50 }, food: { type: 'food', name: 'lab', carbs: 12 }, activity: { created_at: iso(now), steps: 10 } };
    for (const coll of Object.keys(docs)) {
      const h = hex(); const d = Object.assign({ _id: h }, docs[coll]);
      const r1 = await req('POST', '/api/v1/' + coll + '/', [d]); const f1 = await stored(coll, h);
      const r2 = await req('POST', '/api/v1/' + coll + '/', [d]); const f2 = await stored(coll, h);
      // food's GET ignores find[_id] on every build; count in mongo, not the reply.
      const g = coll === 'food' ? 'find n/a' : 'find ' + len(await req('GET', '/api/v1/' + coll + '.json?find[_id]=' + h + '&count=5'));
      const dl = await req('DELETE', '/api/v1/' + coll + '/' + h);
      put('P-ID-6', coll + ' POST, re-POST, find, DELETE', [r1.s + ':' + f1, r2.s + ':' + f2, g, 'DELETE ' + dl.s + ' ' + await count(coll, h)]);
    }
  }

  // P-ID-7 a twin: the string record and the ObjectId copy a PUT on <=15.0.8 left beside it.
  // Delete by the hex through each path a user or tool would take.
  if (want('P-ID-7')) {
    const c = db.collection('treatments');
    const twin = async (notes) => {
      const h = hex(); const ca = iso(now - 5 * 60000 - Math.floor(Math.random() * 60000));
      await c.insertMany([{ _id: h, eventType: 'Note', notes: 'old', created_at: ca }, { _id: new ObjectId(h), eventType: 'Note', notes, created_at: ca }]);
      return h;
    };
    let h = await twin('edited');
    put('P-ID-7', 'find[_id] on a twin', len(await req('GET', '/api/v1/treatments.json?find[_id]=' + h + '&count=10')));
    let r = await req('DELETE', '/api/v1/treatments/' + h);
    put('P-ID-7', 'v1 DELETE /treatments/<hex> (careportal, oref0 dedupe)', [r.s, await count('treatments', h)]);
    h = await twin('edited');
    const s = await sock();
    const a = await emit(s, 'dbRemove', { collection: 'treatments', _id: h });
    s.close();
    put('P-ID-7', 'websocket dbRemove (web UI Remove)', [ack(a), await count('treatments', h)]);
    h = await twin('edited');
    r = await req('DELETE', '/api/v3/treatments/' + h + '?permanent=true', undefined, V);
    put('P-ID-7', 'v3 permanent DELETE', [r.s, await count('treatments', h)]);
  }

  // P-ID-10 API v3 writes when a v1 record and the v3 copy an earlier v3 PUT added both exist:
  // {_id: X} (v1, no identifier) and {_id: ObjectId, identifier: X} (v3). v3 reads sort identifier:-1.
  if (want('P-ID-10')) {
    const c = db.collection('treatments');
    for (const kind of ['hex', 'non-hex']) {
      const seed = async () => {
        const X = kind === 'hex' ? hex() : 'oidlab-' + crypto.randomUUID();
        const t = now - 2 * 60000 - Math.floor(Math.random() * 60000);
        await c.insertMany([
          { _id: X, eventType: 'Note', notes: 'v1-original', created_at: iso(t), date: t, utcOffset: 0, app: 'oidlab' },
          { _id: new ObjectId(), identifier: X, eventType: 'Note', notes: 'v3-copy', created_at: iso(t), date: t, utcOffset: 0, app: 'oidlab' }
        ]);
        seed.t = t;
        return X;
      };
      const pair = async X => (await c.find({ $or: [{ _id: X }, { identifier: X }] }).sort({ notes: 1 }).toArray())
        .map(d => d.notes + (d.isValid === false ? '(invalid)' : '')).join(',');
      let X = await seed();
      const doc = g => g.j && (g.j.result || g.j);
      let g = await req('GET', '/api/v3/treatments/' + X, undefined, V);
      put('P-ID-10', kind + ' GET returns', [g.s, doc(g) && doc(g).notes ? doc(g).notes : g.t]);
      const d = await req('DELETE', '/api/v3/treatments/' + X, undefined, V);
      g = await req('GET', '/api/v3/treatments/' + X, undefined, V);
      put('P-ID-10', kind + ' DELETE, then GET', [d.s, await pair(X), 'GET ' + g.s + (doc(g) && doc(g).notes ? ' ' + doc(g).notes : '')]);
      X = await seed();
      const p = await req('PUT', '/api/v3/treatments/' + X, { eventType: 'Note', notes: 'v3-put', created_at: iso(seed.t), date: seed.t, utcOffset: 0, app: 'oidlab' }, V);
      put('P-ID-10', kind + ' PUT', [p.s, await pair(X), 'identifier=X n=' + await c.countDocuments({ identifier: X })]);
    }
  }

  // P-ID-11 find[_id][$in] (xDrip4iOS-style list operations) against a string record.
  // The control is a list of two ObjectId-stored records, which every build finds and deletes.
  if (want('P-ID-11')) {
    const c = db.collection('treatments');
    const o1 = hex(); const o2 = hex();
    await c.insertMany([{ _id: new ObjectId(o1), eventType: 'Note', notes: 'o1', created_at: iso(now - 72 * 60000) }, { _id: new ObjectId(o2), eventType: 'Note', notes: 'o2', created_at: iso(now - 73 * 60000) }]);
    const g0 = len(await req('GET', '/api/v1/treatments.json?find[_id][$in][]=' + o1 + '&find[_id][$in][]=' + o2 + '&count=10'));
    const r0 = await req('DELETE', '/api/v1/treatments/?find[_id][$in][]=' + o1 + '&find[_id][$in][]=' + o2);
    put('P-ID-11', 'GET, DELETE find[_id][$in] [OID, OID] (control)', [g0, r0.s, await count('treatments', o1), await count('treatments', o2)]);
    const hs = hex(); const ho = hex();
    await c.insertMany([{ _id: hs, eventType: 'Note', notes: 's', created_at: iso(now - 70 * 60000) }, { _id: new ObjectId(ho), eventType: 'Note', notes: 'o', created_at: iso(now - 71 * 60000) }]);
    put('P-ID-11', 'GET find[_id][$in] [string, OID]', len(await req('GET', '/api/v1/treatments.json?find[_id][$in][]=' + hs + '&find[_id][$in][]=' + ho + '&count=10')));
    const r = await req('DELETE', '/api/v1/treatments/?find[_id][$in][]=' + hs + '&find[_id][$in][]=' + ho);
    put('P-ID-11', 'DELETE find[_id][$in] [string, OID]', [r.s, 'string ' + await count('treatments', hs), 'OID ' + await count('treatments', ho)]);
  }

  // P-ID-12 auth subjects created with a hex _id (admin page, backup restore of subjects).
  // Since #8754 create keeps only the subject's owned fields, so the first two cells no longer
  // store the sent _id on dev; the legacy cells seed the subject straight to mongo, as 15.0.8's
  // create stored it (the string), and delete it by that hex through the API.
  if (want('P-ID-12')) {
    const subjects = db.collection('auth_subjects');
    const hs = hex(); const ho = hex();
    await subjects.insertMany([{ _id: hs, name: 'oidlab-legacy-string', roles: ['readable'], created_at: iso(now) }, { _id: new ObjectId(ho), name: 'oidlab-legacy-oid', roles: ['readable'], created_at: iso(now) }]);
    const ds = await req('DELETE', '/api/v2/authorization/subjects/' + hs);
    put('P-ID-12', 'legacy string subject DELETE by its hex', [ds.s, await count('auth_subjects', hs)]);
    const dob = await req('DELETE', '/api/v2/authorization/subjects/' + ho);
    put('P-ID-12', 'legacy OID subject DELETE by its hex (control)', [dob.s, await count('auth_subjects', ho)]);
    const h = hex();
    const r = await req('POST', '/api/v2/authorization/subjects', { _id: h, name: 'oidlab-hex', roles: ['readable'] });
    put('P-ID-12', 'subject POST with hex _id', [r.s, await stored('auth_subjects', h)]);
    const d = await req('DELETE', '/api/v2/authorization/subjects/' + h);
    put('P-ID-12', 'subject DELETE by that hex', [d.s, await count('auth_subjects', h)]);
  }

  put('P-ID-0', 'liveness after', (await req('GET', '/api/v1/status.json')).s);
  const head = require('child_process').execFileSync('git', ['-C', DIR, 'rev-parse', '--short', 'HEAD']).toString().trim();
  console.log(JSON.stringify({ build: NAME, head, measured: new Date().toISOString(), cells }, null, 1));
  await cli.close(); process.exit(0);
})().catch(e => { console.error('ERR', e && e.stack); process.exit(1); });
