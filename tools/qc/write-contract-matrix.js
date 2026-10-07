'use strict';
// WRITE-CONTRACT measurement: how each write path of a cgm-remote-monitor build
// stores, stamps, deletes and announces a record, per collection and write form.
//
//   WC_WORKTREE=<crm worktree> WC_MONGO=mongodb://127.0.0.1:27151 \
//     node tools/qc/write-contract-matrix.js [--out results.json] [--only treatments,food] \
//       [--paths v1,v3,ws,inproc] [--forms create,resend-hex] [--no-cross]
//   node tools/qc/write-contract-matrix.js --compare a.json b.json   cell-by-cell diff
//   node tools/qc/write-contract-matrix.js --table a.json            markdown tables, every field
//   node tools/qc/write-contract-matrix.js --compact a.json          one condensed table per collection
//   node tools/qc/write-contract-matrix.js --divergence a.json       which groups the paths disagree on
//
// Over the socket an ObjectId cannot be sent; the resend-oid form sends the
// Extended JSON {"$oid": ...} there and over HTTP, and an ObjectId in-process.
//
// Plan rule 4: the server is the build's own code, booted in this process from
// WC_WORKTREE exactly as lib/server/server.js boots it (bootevent, app, http
// server, websocket); every module is require()d by path from that worktree.
// HTTP and socket.io requests go over a real listener. Booting in-process is
// what lets a cell record the bus emissions (`data-update`, `storage-socket-*`)
// and the in-memory cache, which no client can observe directly.
//
// Every record a cell writes carries `wc: <cell id>`, so the cell finds all of
// its stored documents (twins included) without trusting any _id. Stored state
// is read from MongoDB, not from the API. Synthetic data only; the database is
// a fresh `wcm_<random>` and is dropped at the end. Never point WC_MONGO at a
// real site.
//
// Each cell also asserts liveness (GET /api/v1/status.json = 200) before and
// after its measured step; a cell whose liveness fails is reported INVALID, so
// a "nothing happened" cell cannot come from a dead server.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');

const argv = process.argv.slice(2);
const opt = (name, dflt) => { const i = argv.indexOf(name); return i === -1 ? dflt : argv[i + 1]; };
const flag = name => argv.includes(name);

if (flag('--compare')) {
  const [a, b] = argv.slice(argv.indexOf('--compare') + 1).map(f => JSON.parse(fs.readFileSync(f, 'utf8')));
  let n = 0;
  for (const k of Object.keys(Object.assign({}, a.cells, b.cells))) {
    const x = JSON.stringify(a.cells[k]); const y = JSON.stringify(b.cells[k]);
    if (x !== y) { n++; console.log(k + '\n  A ' + x + '\n  B ' + y); }
  }
  console.log('differing cells: ' + n + ' (A ' + a.head + ', B ' + b.head + ')');
  process.exit(n === 0 ? 0 : 1);
}

if (flag('--table')) {
  const r = JSON.parse(fs.readFileSync(argv[argv.indexOf('--table') + 1], 'utf8'));
  const cols = ['st', 'store', 'srv', 'hist', 'ev', 'wire', 'cache', 'v1read'];
  for (const coll of r.collections) {
    console.log('\n#### ' + coll + '\n');
    console.log('| path | form | ' + cols.join(' | ') + ' |');
    console.log('|---|---|' + cols.map(() => '---').join('|') + '|');
    for (const k of Object.keys(r.cells).filter(k => k.startsWith(coll + ' ') && !k.includes(' x '))) {
      const [, p, f] = k.split(' ');
      const c = r.cells[k];
      console.log('| ' + p + ' | ' + f + ' | ' + cols.map(x => String(c[x] === undefined ? '' : c[x]).replace(/\|/g, '\\|')).join(' | ') + ' |');
    }
  }
  const cross = Object.keys(r.cells).filter(k => k.includes(' x '));
  if (cross.length) {
    console.log('\n#### cross-path re-send (create through the first path, re-send the same body through the second)\n');
    console.log('| collection | first x then | second reply | stored |');
    console.log('|---|---|---|---|');
    cross.forEach(k => { const [coll, , a, , b] = k.split(' '); const c = r.cells[k]; console.log('| ' + coll + ' | ' + a + ' x ' + b + ' | ' + c.st + ' | ' + c.store + ' |'); });
  }
  process.exit(0);
}

// One table per collection, a row per write form, a column per path; each cell
// condensed to: reply · stored documents · server dates · v3 history · emissions
// (and the v1 read count for deletes). The legend is in the WRITE-CONTRACT spec.
if (flag('--compact')) {
  const r = JSON.parse(fs.readFileSync(argv[argv.indexOf('--compact') + 1], 'utf8'));
  const reply = st => /^5\d\d|^err|^NO-ACK/.test(st) ? (/E11000/.test(st) ? 'dup-err' : String(st).slice(0, 3) === '500' ? '500' : 'err')
    : /^4\d\d/.test(st) ? String(st).slice(0, 3) : /^ack \{/.test(st) && !/success/.test(st) ? 'refused'
    : /\[0\]/.test(st) ? 'empty' : /no _id\]/.test(st) ? 'ok, no id' : /_id|identifier/.test(st) ? 'ok+id' : 'ok';
  const store = v => v === 'none' ? '0' : String(v).replace(/^n=/, '').replace(/ /, ' ');
  const hist = h => h === 'valid' ? 'h' : h === 'invalid' ? 'h:del' : h === 'absent' ? '–' : h === 'n/a' ? 'n/a' : h;
  const ev = (e, w) => {
    const parts = [];
    if (/du:update\[\d+,mills\]/.test(e)) parts.push('du');
    else if (/du:update\[\d+,no-mills\]/.test(e)) parts.push('du(no mills)');
    else if (/du:update\[0\]/.test(e)) parts.push('du(empty)');
    if (/du:remove/.test(e)) parts.push('du:rm');
    if (w && w !== 'none') parts.push('ws3:' + w);
    return parts.length ? parts.join('+') : '–';
  };
  for (const coll of r.collections) {
    console.log('\n**' + coll + '**\n');
    console.log('| form | ' + r.paths.join(' | ') + ' |');
    console.log('|---|' + r.paths.map(() => '---').join('|') + '|');
    for (const f of r.forms) {
      const row = r.paths.map(p => {
        const c = r.cells[coll + ' ' + p + ' ' + f];
        if (!c || /^n\/a/.test(c.st)) return 'n/a';
        if (/INVALID/.test(c.st)) return 'INVALID';
        let x = reply(c.st) + ' · ' + store(c.store) + ' · ' + c.srv + ' · ' + hist(c.hist) + ' · ' + ev(c.ev, c.wire);
        if (/delete/.test(f)) x += ' · v1:' + String(c.v1read).replace('n=', '');
        return x;
      });
      if (row.every(x => x === 'n/a')) continue;
      console.log('| ' + f + ' | ' + row.join(' | ') + ' |');
    }
  }
  process.exit(0);
}

// For each collection and write form: do the paths leave the same stored state
// (documents, _id forms, server dates, v3 history, v1 read), give the same kind
// of reply, and make the same emissions? A path that has no such operation
// (n/a) is left out of the comparison.
if (flag('--divergence')) {
  const r = JSON.parse(fs.readFileSync(argv[argv.indexOf('--divergence') + 1], 'utf8'));
  // What the caller learns, whatever the protocol: accepted and told the record's
  // id; accepted without an id; refused (4xx, or an ack naming a problem); failed
  // (5xx, a storage error to the callback); or an empty answer.
  const replyClass = st => {
    if (/^5\d\d|^err|^NO-ACK/.test(st)) return 'failed';
    if (/^4\d\d/.test(st) || (/^ack \{/.test(st) && !/success/.test(st))) return 'refused';
    if (/\[0\]/.test(st)) return 'empty';
    if (/_id|identifier/.test(st) && !/no _id\]/.test(st)) return 'ok+id';
    return 'ok';
  };
  const ok = c => c && c.st && !/^n\/a/.test(c.st) && !/INVALID/.test(c.st);
  const counts = { state: 0, reply: 0, emission: 0, groups: 0 };
  console.log('| collection | form | paths | stored state | reply | emission |');
  console.log('|---|---|---|---|---|---|');
  for (const coll of r.collections) for (const f of r.forms) {
    const ps = r.paths.map(p => [p, r.cells[coll + ' ' + p + ' ' + f]]).filter(([, c]) => ok(c));
    if (ps.length < 2) continue;
    counts.groups++;
    const st = new Set(ps.map(([, c]) => [c.store, c.srv, c.hist, c.v1read].join(' ')));
    const rp = new Set(ps.map(([, c]) => replyClass(c.st)));
    const ev = new Set(ps.map(([, c]) => c.ev + ' ' + c.wire));
    if (st.size > 1) counts.state++;
    if (rp.size > 1) counts.reply++;
    if (ev.size > 1) counts.emission++;
    const mark = n => n > 1 ? 'differ (' + n + ')' : 'same';
    console.log('| ' + coll + ' | ' + f + ' | ' + ps.map(([p]) => p).join(',') + ' | ' + mark(st.size) + ' | ' + mark(rp.size) + ' | ' + mark(ev.size) + ' |');
  }
  console.log('\ngroups compared: ' + counts.groups + '; stored state differs in ' + counts.state + ', reply kind in ' + counts.reply + ', emissions in ' + counts.emission);
  process.exit(0);
}

const WT = path.resolve(process.env.WC_WORKTREE || '');
if (!fs.existsSync(path.join(WT, 'lib/server/bootevent.js'))) {
  console.error('WC_WORKTREE must be a cgm-remote-monitor worktree with npm ci done'); process.exit(2);
}
const MONGO = process.env.WC_MONGO || 'mongodb://127.0.0.1:27151';
const DBNAME = 'wcm_' + crypto.randomBytes(4).toString('hex');
const SECRET = crypto.randomBytes(18).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');

process.env.MONGODB_URI = MONGO + '/' + DBNAME;
process.env.API_SECRET = SECRET;
process.env.AUTH_DEFAULT_ROLES = 'denied';
process.env.ENABLE = 'careportal api';
process.env.INSECURE_USE_HTTP = 'true';
process.env.DISPLAY_UNITS = 'mg/dl';
const OUT = opt('--out', null) ? path.resolve(opt('--out', null)) : null; // before the chdir below
process.chdir(WT);

const R = p => require(path.join(WT, p));
const { MongoClient, ObjectId } = R('node_modules/mongodb');
const io = R('node_modules/socket.io-client');
const { execFileSync } = require('child_process');
const head = execFileSync('git', ['-C', WT, 'rev-parse', 'HEAD']).toString().trim();
const dirty = execFileSync('git', ['-C', WT, 'status', '--porcelain', '--', 'lib']).toString().trim();

const COLLS = (opt('--only', 'entries,treatments,devicestatus,profile,food,activity')).split(',');
const PATHS = (opt('--paths', 'v1,v3,ws,inproc')).split(',');
const FORMS = (opt('--forms', 'create,resend-hex,resend-upper,resend-oid,resend-identity,resend-near,legacy-lower,legacy-upper,update,update-put,softdelete,harddelete')).split(',');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex = () => crypto.randomBytes(12).toString('hex');
const iso = t => new Date(t).toISOString();

// ---- synthetic bodies, one per collection; the same body on every path
// (v3 needs date, utcOffset and app; v1 and the socket keep them as fields).
function body (coll, t, cell, extra) {
  const base = { date: t, utcOffset: 0, app: 'wc-lab', wc: cell, wcv: 1 };
  const b = {
    entries: { type: 'sgv', sgv: 100 + (t % 50), dateString: iso(t), device: 'wc-lab' }
    , treatments: { eventType: 'Carb Correction', carbs: 12, created_at: iso(t), device: 'wc-lab', enteredBy: 'wc-lab' }
    , devicestatus: { device: 'wc-lab', created_at: iso(t), uploaderBattery: 77 }
    , profile: { defaultProfile: 'Default', startDate: iso(t), created_at: iso(t), units: 'mg/dl'
      , store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }]
        , basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }]
        , target_high: [{ time: '00:00', value: 120 }], timezone: 'UTC', units: 'mg/dl' } } }
    , food: { type: 'food', category: 'wc', subcategory: 'lab', name: 'wc food', carbs: 10, created_at: iso(t) }
    , activity: { created_at: iso(t), steps: 100 }
  }[coll];
  return Object.assign(base, b, extra || {});
}

(async () => {
  const cli = await MongoClient.connect(MONGO);
  const db = cli.db(DBNAME);
  const serverVersion = (await db.admin().serverInfo()).version;

  // ---- boot the build as lib/server/server.js does
  const env = R('lib/server/env')();
  const language = R('lib/language')();
  const ctx = await new Promise(resolve => R('lib/server/bootevent')(env, language).boot(resolve));
  if (ctx.bootErrors && ctx.bootErrors.length) { console.error('boot errors', ctx.bootErrors); process.exit(2); }
  const app = R('lib/server/app')(env, ctx);
  const server = http.createServer(app);
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  R('lib/server/websocket')(env, ctx, server);
  const BASE = 'http://127.0.0.1:' + server.address().port;

  // ---- bus taps
  let events = [];
  ['data-update', 'storage-socket-create', 'storage-socket-update', 'storage-socket-delete'].forEach(n =>
    ctx.bus.on(n, e => events.push({ n, e })));

  const H = { 'api-secret': HASH, 'content-type': 'application/json' };
  async function req (method, p, b, extra) {
    const r = await fetch(BASE + p, { method, headers: Object.assign({}, H, extra || {}), body: b === undefined ? undefined : JSON.stringify(b) });
    const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
    return { s: r.status, j, t: t.slice(0, 160) };
  }
  const alive = async () => (await req('GET', '/api/v1/status.json')).s === 200;

  await req('POST', '/api/v2/authorization/subjects', { name: 'wc-admin', roles: ['admin'] });
  const subj = ((await req('GET', '/api/v2/authorization/subjects')).j || []).find(x => x.name === 'wc-admin');
  const jwt = (await req('GET', '/api/v2/authorization/request/' + subj.accessToken)).j.token;
  const V = { authorization: 'Bearer ' + jwt };

  const sock = await new Promise((resolve, reject) => {
    const s = io(BASE, { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('authorize', { client: 'web', secret: HASH, history: 0 }, () => resolve(s)));
    s.on('connect_error', reject);
    setTimeout(() => reject(new Error('socket timeout')), 8000);
  });
  // A real API v3 storage-socket client (the /storage namespace AndroidAPS
  // NSClientV3 listens on in websocket mode), subscribed to every collection:
  // what it receives is what such a client learns of each write.
  let wire = [];
  const storage = await new Promise((resolve, reject) => {
    const s = io(BASE + '/storage', { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('subscribe', { accessToken: subj.accessToken }, a =>
      a && a.success ? resolve(s) : reject(new Error('storage subscribe refused ' + JSON.stringify(a)))));
    s.on('connect_error', reject);
    setTimeout(() => reject(new Error('storage socket timeout')), 8000);
  });
  ['create', 'update', 'delete'].forEach(n => storage.on(n, () => wire.push(n)));
  const emit = (ev, d) => new Promise(resolve => {
    const t = setTimeout(() => resolve('NO-ACK'), 5000);
    sock.emit(ev, d, a => { clearTimeout(t); resolve(a); });
  });
  // The database name is random per run; keep it out of the cells so two runs compare.
  const anon = m => String(m).replace(/wcm_[0-9a-f]+/g, 'wcm_*').slice(0, 60);
  const cb = fn => new Promise(resolve => { try { fn((err, res) => resolve({ err: err ? anon(err.message || err) : null, res })); } catch (e) { resolve({ err: 'THROW ' + anon(e.message) }); } });

  // ---- the paths. Each returns a short reply descriptor.
  const ARRAY_POST = { entries: true, treatments: true, devicestatus: true };
  const V1_PUT = { treatments: true, profile: true, food: true, activity: true };
  const V3 = { entries: true, treatments: true, devicestatus: true, profile: true, food: true };
  const IN_SAVE = { treatments: true, profile: true, food: true, activity: true };

  function replyDesc (r, sentId) {
    const arr = Array.isArray(r.j) ? r.j : (r.j && Array.isArray(r.j.result) ? r.j.result : null);
    if (arr) {
      const ids = arr.map(d => d && d._id !== undefined ? String(d._id) : '-');
      const rel = ids.map(i => i === '-' ? 'no _id' : (sentId !== undefined && i === String(sentId) ? '_id=sent' : '_id'));
      return r.s + ' [' + arr.length + (arr.length ? ' ' + Array.from(new Set(rel)).join(',') : '') + ']';
    }
    if (r.j && typeof r.j === 'object') return r.s + ' {' + Object.keys(r.j).filter(k => k !== 'status').join(',') + '}';
    return r.s + (r.t ? ' ' + r.t.slice(0, 40) : '');
  }
  function sockDesc (a, sentId) {
    if (a === 'NO-ACK') return 'NO-ACK';
    if (Array.isArray(a)) {
      const rel = a.map(d => d && d._id !== undefined ? (sentId !== undefined && String(d._id) === String(sentId) ? '_id=sent' : '_id') : 'no _id');
      return 'ack [' + a.length + (a.length ? ' ' + Array.from(new Set(rel)).join(',') : '') + ']';
    }
    return 'ack ' + JSON.stringify(a).slice(0, 40);
  }
  function inDesc (r, sentId) {
    if (r.err) return 'err ' + r.err;
    const arr = Array.isArray(r.res) ? r.res : (r.res ? [r.res] : []);
    const rel = arr.map(d => d && d._id !== undefined ? (sentId !== undefined && String(d._id) === String(sentId) ? '_id=sent' : '_id') : 'no _id');
    return 'cb [' + arr.length + (arr.length ? ' ' + Array.from(new Set(rel)).join(',') : '') + ']';
  }

  const P = {
    v1: {
      create: async (c, b) => { const r = await req('POST', '/api/v1/' + c + '/', ARRAY_POST[c] ? [b] : b); return replyDesc(r, b._id); }
      , update: async (c, d) => V1_PUT[c] ? replyDesc(await req('PUT', '/api/v1/' + c + '/', Object.assign({}, d, { wcv: 2 }))) : null
      , softdelete: async (c, d) => V1_PUT[c] ? replyDesc(await req('PUT', '/api/v1/' + c + '/', Object.assign({}, d, { isValid: false }))) : null
      , harddelete: async (c, d) => replyDesc(await req('DELETE', '/api/v1/' + c + '/' + d._id))
    }
    , v3: {
      create: async (c, b) => V3[c] ? replyDesc(await req('POST', '/api/v3/' + c, b, V)) : null
      , update: async (c, d, ident) => V3[c] ? replyDesc(await req('PATCH', '/api/v3/' + c + '/' + ident, { wcv: 2 }, V)) : null
      , 'update-put': async (c, d, ident) => {
        if (!V3[c]) return null;
        const b = Object.assign({}, d, { wcv: 2 }); delete b._id; delete b.srvModified; delete b.srvCreated; delete b.subject;
        return replyDesc(await req('PUT', '/api/v3/' + c + '/' + ident, b, V));
      }
      , softdelete: async (c, d, ident) => V3[c] ? replyDesc(await req('DELETE', '/api/v3/' + c + '/' + ident, undefined, V)) : null
      , harddelete: async (c, d, ident) => V3[c] ? replyDesc(await req('DELETE', '/api/v3/' + c + '/' + ident + '?permanent=true', undefined, V)) : null
    }
    , ws: {
      create: async (c, b) => sockDesc(await emit('dbAdd', { collection: c, data: b }), b._id)
      , update: async (c, d) => sockDesc(await emit('dbUpdate', { collection: c, _id: d._id, data: { wcv: 2 } }))
      , softdelete: async (c, d) => sockDesc(await emit('dbUpdate', { collection: c, _id: d._id, data: { isValid: false } }))
      , harddelete: async (c, d) => sockDesc(await emit('dbRemove', { collection: c, _id: d._id }))
    }
    , inproc: {
      // the id as sent is taken before the call: create() writes the stored _id into the body
      create: async (c, b) => { const sent = b._id; return inDesc(await cb(fn => ctx[c].create(ARRAY_POST[c] || c === 'activity' || c === 'food' ? [b] : b, fn)), sent); }
      , update: async (c, d) => IN_SAVE[c] ? inDesc(await cb(fn => ctx[c].save(Object.assign({}, d, { _id: d._id, wcv: 2 }), fn))) : null
      , softdelete: async (c, d) => IN_SAVE[c] ? inDesc(await cb(fn => ctx[c].save(Object.assign({}, d, { isValid: false }), fn))) : null
      , harddelete: async (c, d) => inDesc(await cb(fn => (c === 'profile' || c === 'food' || c === 'activity')
        ? ctx[c].remove(d._id, fn) : ctx[c].remove({ find: { _id: d._id } }, fn)))
    }
  };

  // ---- observation
  const col = c => db.collection(env[c + '_collection'] || c);
  const idForm = id => id instanceof ObjectId ? 'OID' : (typeof id === 'string' ? (/^[0-9a-f]{24}$/.test(id) ? 'str' : /^[0-9A-Fa-f]{24}$/.test(id) ? 'STR' : 'str*') : typeof id);
  const docsOf = async (c, cell) => col(c).find({ wc: cell }).sort({ _id: 1 }).toArray();
  async function cursorOf (c) {
    const d = await col(c).find({ srvModified: { $type: 'number' } }).sort({ srvModified: -1 }).limit(1).toArray();
    // An empty collection: a cursor a day back (history refuses a cursor at or
    // below its minimum timestamp, and every write here is stamped near now).
    return d.length ? d[0].srvModified : Date.now() - 86400000;
  }
  async function histOf (c, cell, cursor) {
    if (!V3[c]) return 'n/a';
    const r = await req('GET', '/api/v3/' + c + '/history/' + cursor + '?limit=1000', undefined, V);
    if (r.s !== 200 || !r.j || !Array.isArray(r.j.result)) return 'ERR ' + r.s;
    const hit = r.j.result.filter(d => d.wc === cell);
    if (!hit.length) return 'absent';
    return hit.map(d => d.isValid === false ? 'invalid' : 'valid').join(',');
  }
  function evDesc (evs) {
    if (!evs.length) return 'none';
    return evs.map(({ n, e }) => {
      if (n !== 'data-update') return n.replace('storage-socket-', 'ss:');
      const ch = Array.isArray(e.changes) ? e.changes : (e.changes === undefined ? null : [e.changes]);
      if (e.op === 'remove') return 'du:remove(' + (ch === null ? 'reload' : typeof ch[0] === 'string' ? 'id' : 'obj') + ')';
      const mills = ch && ch.length && ch.every(d => d && typeof d === 'object' && Number.isFinite(d.mills));
      return 'du:' + e.op + '[' + (ch ? ch.length : 0) + (ch && ch.length ? (mills ? ',mills' : ',no-mills') : '') + ']';
    }).join(' ');
  }
  function cacheOf (c, cell) {
    if (!ctx.cache || !Array.isArray(ctx.cache[c])) return 'n/a';
    const held = ctx.cache[c].filter(d => d.wc === cell);
    if (!held.length) return 'absent';
    return 'held' + (held.length > 1 ? '×' + held.length : '') + (held.every(d => Number.isFinite(d.mills)) ? '' : ' no-mills')
      + (held.some(d => d.isValid === false) ? ' invalid' : '');
  }
  async function v1readOf (c, cell) {
    const r = await req('GET', '/api/v1/' + c + '.json?find[wc]=' + encodeURIComponent(cell) + '&count=50');
    const arr = Array.isArray(r.j) ? r.j : null;
    if (!arr) return 'ERR ' + r.s;
    const n = arr.filter(d => d.wc === cell).length;
    return 'n=' + n;
  }
  function storeDesc (docs) {
    if (!docs.length) return 'none';
    return 'n=' + docs.length + ' ' + docs.map(d => idForm(d._id) + (d.wcv === 2 ? ':v2' : '') + (d.isValid === false ? ':inv' : '')).join(',');
  }
  function srvDesc (before, after) {
    if (!after.length) return '-';
    return after.map(d => {
      const prev = before.find(b => String(b._id) === String(d._id) && typeof b._id === typeof d._id);
      const c = typeof d.srvCreated === 'number' ? (prev ? (prev.srvCreated === d.srvCreated ? 'C=' : (prev.srvCreated === undefined ? 'C+' : 'C~')) : 'C') : 'noC';
      const m = typeof d.srvModified === 'number' ? (prev ? (prev.srvModified === d.srvModified ? 'M=' : 'M+') : 'M') : 'noM';
      return c + m;
    }).join(',');
  }

  const cells = {};
  let seq = 0;
  const t0 = Date.now() - 6 * 3600000;
  const nextT = () => t0 + (++seq) * 61000;

  async function cell (c, p, f) {
    const key = c + ' ' + p + ' ' + f;
    const cellId = 'wc-' + seq + '-' + crypto.randomBytes(3).toString('hex');
    const t = nextT();
    const out = {};
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness before' }; return; }
    const path_ = P[p];
    const createVia = path_.create;
    let measured;
    // the seed and the stored record a later step addresses
    const seedOnce = async (extra) => {
      const r = await createVia(c, body(c, t, cellId, extra));
      await sleep(80);
      return r;
    };
    const target = async () => {
      const d = (await docsOf(c, cellId)).slice(-1)[0];
      if (!d) return null;
      const plain = Object.assign({}, d, { _id: d._id instanceof ObjectId ? d._id.toHexString() : d._id });
      return { doc: plain, ident: d.identifier || plain._id };
    };

    let seedReply = null;
    if (f === 'create') {
      measured = () => createVia(c, body(c, t, cellId));
    } else if (f === 'resend-hex' || f === 'resend-upper' || f === 'resend-oid') {
      const h = hex();
      const id = f === 'resend-hex' ? h : f === 'resend-upper' ? h.toUpperCase()
        : (p === 'inproc' ? () => new ObjectId(h) : { $oid: h });
      const mk = () => body(c, t, cellId, { _id: typeof id === 'function' ? id() : id });
      if (createVia === undefined) { cells[key] = { st: 'n/a' }; return; }
      seedReply = await createVia(c, mk()); await sleep(80);
      measured = () => createVia(c, mk());
    } else if (f === 'legacy-lower' || f === 'legacy-upper') {
      // A record a release before 15.0.9 left behind: the client's 24-hex _id
      // stored as the string, no srvCreated/srvModified, no identifier. Written
      // straight to MongoDB; the path then re-sends it with that id in lower or
      // upper case.
      const h = hex();
      await col(c).insertOne(Object.assign(body(c, t, cellId, { _id: h }), c === 'entries' ? { sysTime: iso(t) } : {}));
      out.seed = 'mongo str';
      measured = () => createVia(c, body(c, t, cellId, { _id: f === 'legacy-lower' ? h : h.toUpperCase() }));
    } else if (f === 'resend-identity') {
      seedReply = await seedOnce();
      measured = () => createVia(c, body(c, t, cellId));
    } else if (f === 'resend-near') {
      // The same record one second later (a clock or rounding difference between
      // a first send and a retry): the socket's similar-treatment window is +-2 s.
      seedReply = await seedOnce();
      measured = () => createVia(c, body(c, t + 1000, cellId));
    } else {
      const fn = path_[f];
      if (!fn) { cells[key] = { st: 'n/a' }; return; }
      seedReply = await seedOnce();
      const tg = await target();
      if (!tg) { cells[key] = { st: 'n/a (seed not stored: ' + seedReply + ')' }; return; }
      measured = () => fn(c, tg.doc, tg.ident);
    }
    if (seedReply !== null) out.seed = seedReply;

    const before = await docsOf(c, cellId);
    const cursor = await cursorOf(c);
    events = []; wire = [];
    const st = await measured();
    if (st === null) { cells[key] = { st: 'n/a' }; return; }
    await sleep(250);
    const evs = events.slice(); events = [];
    const wired = wire.slice(); wire = [];
    const after = await docsOf(c, cellId);
    out.st = st;
    out.store = storeDesc(after);
    out.srv = srvDesc(before, after);
    out.hist = await histOf(c, cellId, cursor);
    out.ev = evDesc(evs);
    out.wire = wired.length ? wired.join(',') : 'none';
    out.cache = cacheOf(c, cellId);
    out.v1read = await v1readOf(c, cellId);
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness after' }; return; }
    cells[key] = out;
  }

  for (const c of COLLS) {
    for (const p of PATHS) {
      for (const f of FORMS) {
        if (f === 'update-put' && p !== 'v3') continue;
        await cell(c, p, f);
      }
    }
  }

  // ---- cross-path: create through A, re-send the same body (no _id) through B
  if (!flag('--no-cross')) {
    for (const c of COLLS) {
      for (const a of PATHS) for (const b of PATHS) {
        if (a === b) continue;
        if ((a === 'v3' || b === 'v3') && !V3[c]) continue;
        const cellId = 'wc-x' + (++seq) + '-' + crypto.randomBytes(3).toString('hex');
        const t = nextT();
        if (!(await alive())) { cells[c + ' x ' + a + ' x ' + b] = { st: 'INVALID' }; continue; }
        await P[a].create(c, body(c, t, cellId)); await sleep(80);
        const st = await P[b].create(c, body(c, t, cellId)); await sleep(150);
        const after = await docsOf(c, cellId);
        const ok = await alive();
        cells[c + ' x ' + a + ' x ' + b] = ok ? { st, store: storeDesc(after) } : { st: 'INVALID liveness after' };
      }
    }
  }

  const result = {
    head, dirty_lib: dirty || '', node: process.version, mongod: serverVersion, db: DBNAME
    , date: new Date().toISOString(), collections: COLLS, paths: PATHS, forms: FORMS, cells
  };
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  else console.log(JSON.stringify(result, null, 1));
  console.error('cells: ' + Object.keys(cells).length + ', invalid: ' + Object.values(cells).filter(x => /INVALID/.test(x.st)).length);

  sock.close();
  storage.close();
  await db.dropDatabase();
  await cli.close();
  ctx.bus.emit('teardown');
  server.close();
  setTimeout(() => process.exit(0), 500);
})().catch(e => { console.error(e); process.exit(1); });
