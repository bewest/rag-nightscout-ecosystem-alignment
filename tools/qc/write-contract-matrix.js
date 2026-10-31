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
//
// Temporary Target cells (QC-MATRIX-TT). The build's own environment selects
// its write-validation mode: run once with WRITE_VALIDATION unset (off) and
// once with WRITE_VALIDATION=reject, then --compare the two. After the cells
// above, the treatments collection gets Temporary Target forms whose bodies
// carry eventType "Temporary Target" with targetBottom/targetTop/units/duration,
// the fields lib/server/write-validation.js checks:
//   tt-create-ok     a valid target (100-120 mg/dl, 60 min), every path
//   tt-create-order  targetBottom above targetTop (rule tt-order), every path
//   tt-create-units  labelled mmol with mg/dL numbers (tt-units-plausible), every path
//   tt-update-ok     a valid target, then targetTop 130 (v1 PUT, v3 PATCH,
//                    socket dbUpdate, in-process save)
//   tt-update-order  a valid target, then targetTop 80, below targetBottom
//   tt-put-ok / tt-put-order        the same through v3 PUT
//   tt-unset-ok / tt-unset-target   socket dbUpdateUnset of endmills (a domain
//                    field, so the update is validated) / of targetTop (tt-target)
// Each TT cell adds a `tt` field: the stored targets and units. The seed of an
// update form is always valid, so the seed is stored in either mode. A
// "-ok" cell should be the same off and reject, a "-order/-units/-target" cell
// should differ, and no earlier cell should change. --no-tt leaves them out;
// --tt-only runs only them. The ids and results of the earlier cells do not
// depend on these: they run first, in the same order as before.
//
// Forms added 2026-10-27 (QC-MATRIX-V2), for gaps the WC-STEP-PATCH slices
// found. They run last, after the Temporary Target cells, so every earlier cell
// keeps its order and its result; --forms selects them like any other form.
//   update-twin        a record stored straight to MongoDB under a 24-hex _id
//                      as a STRING (seed `mongo str`, as legacy-lower), then the
//                      path's update with that _id: v1 PUT, v3 PATCH, socket
//                      dbUpdate, in-process save. A save that stores the
//                      ObjectId form must remove the string twin it replaces.
//   idread-fail        socket dbAdd with a 24-hex _id while the read that
//                      chooses the stored _id form fails. The failure is
//                      injected in this process: storage-reads.findOne throws
//                      for a { _id: { $in: [...] } } read projected to { _id: 1 },
//                      armed only for the measured dbAdd. The cell's `inj`
//                      field says how many reads it failed, so a cell where the
//                      injection never fired cannot pass for one where it did.
//                      Socket only; n/a on the other paths.
//   harddelete-custom  a record stored straight to MongoDB under a custom
//                      non-hex string _id (seed `mongo str*`), then the path's
//                      hard delete (v1 DELETE, v3 permanent DELETE, socket
//                      dbRemove, in-process remove) by that _id.
//   harddelete-num     the same with a numeric _id (seed `mongo number`).
// The pin with these forms is results/write-contract-matrix/dev-db3b9e4e-v2.json
// (456 cells: the 360 of dev-db3b9e4e.json, byte-identical, and 96 new, 25 of
// them n/a). As before, `cache` is racy; it is more so on cells seeded straight
// to MongoDB, which the cache learns of only at its next reload. Compare with
// `cache` set aside before calling a difference there a finding.
//
// Forms added 2026-10-29 (QC-MATRIX-IDF), the re-send cells ID-FIRST-MATCH
// pins. They run last, after the QC-MATRIX-V2 cells, so every earlier cell
// keeps its order, its timestamps and its result; their ids all start "idf-"
// (and the settings cells start "settings "), so no earlier id is reused.
// Every seed carries a seed-only field `wck: 1` that the re-send leaves out,
// and the re-send carries `wcv: 2`; each new cell adds a `shape` field, one
// label per stored record of the cell:
//   merge        the re-send was written and the seed's `wck` is still there
//   replace      the re-send was written into the seeded record and `wck` is gone
//   not-written  the seeded record has none of the re-send's fields
//   new          a record the measured step created
// `shape` exists on the new cells only, so an earlier cell is unchanged.
//   idf-<field>-<variant>   seed with one client identity field, then re-send
//                      with the same value. <field> is identifier, syncIdentifier,
//                      id, uuid, NSCLIENT_ID, or uuidid (a UUID as the _id, as
//                      Loop sends overrides). <variant>: same (the same record),
//                      amt (the same time, another amount), time (the same
//                      amount, five minutes later). Every path, and across
//                      paths: "<coll> x <A> x <B> idf-<field>-<variant>" seeds
//                      through A and re-sends through B, as the cross cells do.
//   idf-softdel-<plain|identifier>  seed, the path's own soft delete, re-send
//   idf-harddel-<plain|identifier>  seed, the path's own hard delete, re-send
//   idf-v3del-<plain|identifier>    seed through the path, API v3 DELETE (soft),
//                      re-send through the path (v1 entries and devicestatus
//                      have no soft delete of their own)
//   idf-split-first / idf-split-second  two records stored straight to MongoDB
//                      with one identifier (the chart-drag split): A, then B two
//                      minutes later with another amount; re-send A or B
//   idf-split-written  A then B written through the path, then A re-sent
// Settings (API v3 only, its one write path) gets the earlier forms create,
// resend-identity, update, update-put, softdelete and harddelete plus the
// idf- forms above, as "settings v3 <form>"; no other path has settings.
// --uuid-off boots the build with UUID_HANDLING=false (recorded in the result
// as uuid_handling); run it with --idf-only, which runs only the new cells, and
// write a separate result file. --no-idf leaves the new cells out.
// --compare --keys-of-a a.json b.json compares only the cells a.json has, so
// a run with the new cells compares against an earlier pin.
// The pin with these forms is results/write-contract-matrix/dev-e1f7ac41-idfirst.json
// (1929 cells: the 456 of the earlier forms, the 360 of dev-db3b9e4e.json among
// them unchanged, and 1473 new); dev-e1f7ac41-idfirst-uuidoff.json holds the
// new cells on entries and treatments with UUID_HANDLING=false (504 cells, ids
// as in the default run). `cache` stays racy on the new cells too, chiefly on
// entries cells that cross API v3.
//
// Forms added 2026-10-30 (QC-MATRIX-IDFMT), the identifier-format cells
// ID-FIRST-MATCH slice 2 (`identifier-format`, ID-VALIDATE) pins. They run
// last, after the QC-MATRIX-IDF cells, so every earlier cell keeps its order,
// its timestamps and its result; their ids all start "idfmt-". Form
// "idfmt-<class>-<mode>" sends one value as `identifier` (class idundef sends
// it as `_id` instead, which UUID_HANDLING can move into `identifier`):
//   placeholders  undefined, null, invalid, nan ("NaN"), unknown, empty (""),
//                 blank ("   "), jsonnull (a JSON null): the union of the
//                 candidate lists (ID-PLACEHOLDER-LIST), so each list has cells
//   number        a non-string identifier (the cell's time, a number)
//   len256/len257 a string of exactly 256 / 257 characters
//   urlsafe, colon ("glooko:bolus:<sha256>", as nightscout-connect), slash,
//   nonascii      character classes; today's behaviour only
//   idundef       `_id: "undefined"` and no identifier
// The placeholder values are the same in every cell (that is their point):
// before each such cell, records carrying the cell's value (as `identifier`
// or `_id`) are deleted straight from MongoDB, so a cell starts from no record
// with that value. The other classes are new per cell. Modes:
//   time    seed with `wck: 1`, re-send five minutes later with `wcv: 2`
//           (as idf-*-time, so a match is not on the time key)
//   single  one write with `wcv: 2`, no seed
//   twoapp  two DIFFERENT apps sharing the value (placeholder classes and
//           idundef only): app A's record, then app B's (other app, device
//           and enteredBy, another amount, 2.5 minutes later); `shape` says
//           what B's write did: new,new (two records), merge or replace (B
//           landed in A's record), not-written (B was dropped)
// Every path; time and twoapp also across paths ("<coll> x <A> x <B> <form>"),
// as the idf cross cells. Settings gets the same-path cells on API v3. Each new
// cell has the idf fields (shape included) plus `ident`, one label per stored
// record in `store` order: kept (the sent value, same type), absent, or what is
// there instead (null, num, empty, uuid, str<length>[ trimmed]).
// --idfmt-only runs only these cells; --no-idfmt leaves them out (as do
// --idf-only and --tt-only).
// The pin with these forms is results/write-contract-matrix/dev-991b0654-idformat.json
// (2675 cells, the new ones only, from an --idfmt-only run).
//
// `wire` attribution (QC-MATRIX-WIRE-ATTRIBUTION, 2026-10-31). Before it, a
// cell's `wire` was every storage-socket frame received in its measured
// window, so a late frame from the previous cell, or the cell's own seed frame
// (a v3 seed or v3 delete before the measured step), could be counted. Now a
// cell counts only frames for its own records (by `wc`, or for a delete by the
// identifier of one of its records), and it settles before and after the
// measured step: it waits until every storage-socket emission on the bus has
// reached the subscriber and the socket has been quiet for 50 ms, bounded at
// 3 s. Cell ids and fields are unchanged. The result's `wire_settle` (outside
// `cells`) counts frames emitted, received and not attributed, and bound hits.
// Break-it: --wire-inject-foreign emits one frame for another cell's record at
// the start of every measured step; with attribution every cell is unchanged,
// without it every cell whose collection is subscribed gains a `create`.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');

const argv = process.argv.slice(2);
const opt = (name, dflt) => { const i = argv.indexOf(name); return i === -1 ? dflt : argv[i + 1]; };
const flag = name => argv.includes(name);

if (flag('--compare')) {
  const [a, b] = argv.slice(argv.indexOf('--compare') + 1).filter(f => !f.startsWith('--')).map(f => JSON.parse(fs.readFileSync(f, 'utf8')));
  let n = 0;
  for (const k of Object.keys(flag('--keys-of-a') ? a.cells : Object.assign({}, a.cells, b.cells))) {
    const x = JSON.stringify(a.cells[k]); const y = JSON.stringify(b.cells[k]);
    if (x !== y) { n++; console.log(k + '\n  A ' + x + '\n  B ' + y); }
  }
  console.log('differing cells: ' + n + (flag('--keys-of-a') ? ' of ' + Object.keys(a.cells).length + ' in A' : '') + ' (A ' + a.head + ', B ' + b.head + ')');
  process.exit(n === 0 ? 0 : 1);
}

if (flag('--table')) {
  const r = JSON.parse(fs.readFileSync(argv[argv.indexOf('--table') + 1], 'utf8'));
  const cols = ['st', 'store', 'tt', 'srv', 'hist', 'ev', 'wire', 'cache', 'v1read', 'inj'];
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
if (flag('--uuid-off')) process.env.UUID_HANDLING = 'false'; // QC-MATRIX-IDF run mode (see the header)
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
// QC-MATRIX-IDF forms: run after the QC-MATRIX-V2 cells (see the header).
const IDF_FIELDS = ['identifier', 'syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID', 'uuidid'];
const IDF_VARIANTS = ['same', 'amt', 'time'];
const IDF_FORMS = [].concat(
  ...IDF_FIELDS.map(fl => IDF_VARIANTS.map(v => 'idf-' + fl + '-' + v))
  , ['softdel', 'harddel', 'v3del'].map(d => ['idf-' + d + '-plain', 'idf-' + d + '-identifier']).flat()
  , ['idf-split-first', 'idf-split-second', 'idf-split-written']);
const FORMS = (opt('--forms', 'create,resend-hex,resend-upper,resend-oid,resend-identity,resend-near,legacy-lower,legacy-upper,update,update-put,softdelete,harddelete,update-twin,idread-fail,harddelete-custom,harddelete-num'
  + (flag('--no-idf') ? '' : ',' + IDF_FORMS.join(','))))
  .split(',');
// QC-MATRIX-V2 forms: run after the Temporary Target cells (see the header).
const V2_FORMS = ['update-twin', 'idread-fail', 'harddelete-custom', 'harddelete-num'];
const IDF_ONLY = flag('--idf-only');
// QC-MATRIX-IDFMT forms: run after the QC-MATRIX-IDF cells (see the header).
const IDFMT_ONLY = flag('--idfmt-only');
const EARLIER = !IDFMT_ONLY; // the cells before QC-MATRIX-IDFMT
const IDFMT_PH = ['undefined', 'null', 'invalid', 'nan', 'unknown', 'empty', 'blank', 'jsonnull'];
const IDFMT_CLASSES = IDFMT_PH.concat(['number', 'len256', 'len257', 'urlsafe', 'colon', 'slash', 'nonascii', 'idundef']);
const IDFMT_FORMS = [].concat(...IDFMT_CLASSES.map(k => ['time', 'single']
  .concat(IDFMT_PH.includes(k) || k === 'idundef' ? ['twoapp'] : []).map(m => 'idfmt-' + k + '-' + m)));
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
    // QC-MATRIX-IDF: API v3 only
    , settings: { device: 'wc-lab', settings: { units: 'mg/dl', alarmHigh: 180, alarmLow: 70 } }
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

  // ---- the idread-fail injection (see the header): the socket's _id-form read,
  // { _id: { $in: [...] } } projected to { _id: 1 }, fails while armed.
  const storageReads = R('lib/server/storage-reads');
  const realFindOne = storageReads.findOne;
  const inject = { armed: false, fired: 0 };
  storageReads.findOne = function (storage, query, projection) {
    if (inject.armed && query && query._id && Array.isArray(query._id.$in)
      && JSON.stringify(projection) === JSON.stringify({ _id: 1 })) {
      inject.fired++;
      return Promise.reject(new Error('wc-lab injected _id read failure'));
    }
    return realFindOne.apply(this, arguments);
  };

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
  let subscribed = [];
  const storage = await new Promise((resolve, reject) => {
    const s = io(BASE + '/storage', { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('subscribe', { accessToken: subj.accessToken }, a => {
      if (!(a && a.success)) return reject(new Error('storage subscribe refused ' + JSON.stringify(a)));
      subscribed = a.collections; resolve(s);
    }));
    s.on('connect_error', reject);
    setTimeout(() => reject(new Error('storage socket timeout')), 8000);
  });
  // Frame attribution and settling (QC-MATRIX-WIRE-ATTRIBUTION). A frame can
  // arrive after the write that caused it has replied, so the previous cell's
  // late frame, or this cell's seed frame, could land in the measured step.
  // Every frame is kept with what it carries (the record's `wc`, or the
  // identifier of a delete), and a cell's `wire` counts only frames for its
  // own records (wireOf). Settling: each storage-socket emission on the bus
  // (in this process, synchronous with the write) is counted against the
  // frames received; settle() waits until every emitted frame has arrived and
  // none has arrived for WIRE_QUIET ms, at most WIRE_SETTLE_MAX ms. A cell
  // settles after its seed (before its measured step) and after its measured
  // step (before `wire` is read). Bound hits are counted in the result's
  // `wire_settle`, outside `cells`, so they never change a cell.
  // --wire-inject-foreign (break-it control): at the start of each measured
  // step, emit one storage-socket-create for a record of another cell; a
  // harness without attribution then records it in `wire`.
  const WIRE_QUIET = 50;
  const WIRE_SETTLE_MAX = 3000;
  let frames = [];
  const wireStat = { emitted: 0, received: 0, timeouts: 0, rejected: 0, injected: 0 };
  let lastFrameAt = 0;
  ['storage-socket-create', 'storage-socket-update', 'storage-socket-delete'].forEach(n =>
    ctx.bus.on(n, e => { if (e && subscribed.includes(e.colName)) wireStat.emitted++; }));
  ['create', 'update', 'delete'].forEach(n => storage.on(n, e => {
    wireStat.received++; lastFrameAt = Date.now();
    frames.push({ n, wc: e && e.doc ? e.doc.wc : undefined, id: e && e.doc ? e.doc.identifier : e && e.identifier });
  }));
  async function settle () {
    const start = Date.now();
    for (;;) {
      const now = Date.now();
      if (wireStat.received >= wireStat.emitted && now - lastFrameAt >= WIRE_QUIET) return;
      if (now - start >= WIRE_SETTLE_MAX) { wireStat.timeouts++; return; }
      await sleep(10);
    }
  }
  // The measured step starts: settle what came before, then record afresh.
  async function wireStart (c) {
    await settle();
    frames = [];
    if (flag('--wire-inject-foreign') && subscribed.includes(c)) {
      wireStat.injected++;
      ctx.bus.emit('storage-socket-create', { colName: c, doc: { wc: 'wc-foreign', identifier: 'wc-foreign' } });
    }
  }
  // The frames of this cell's records: a create or update carries the record
  // (its `wc`); a delete carries only the identifier the request named, the
  // record's identifier or _id, so it is matched against the cell's records.
  async function wireOf (cellId, docs) {
    await settle();
    const ids = new Set();
    docs.forEach(d => {
      if (d.identifier !== undefined && d.identifier !== null) ids.add(String(d.identifier));
      ids.add(d._id instanceof ObjectId ? d._id.toHexString() : String(d._id));
    });
    const mine = frames.filter(f => f.wc !== undefined ? f.wc === cellId : f.id !== undefined && f.id !== null && ids.has(String(f.id)));
    wireStat.rejected += frames.length - mine.length;
    frames = [];
    return mine.length ? mine.map(f => f.n).join(',') : 'none';
  }
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
  const V3 = { entries: true, treatments: true, devicestatus: true, profile: true, food: true, settings: true };
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
    if (c === 'settings') return 'n/a'; // QC-MATRIX-IDF: no API v1 settings
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
    } else if (f === 'update-twin' || f === 'harddelete-custom' || f === 'harddelete-num') {
      // Seeded straight to MongoDB, as the legacy forms, so every path starts
      // from the same stored record; then the path's own update or hard delete.
      const fn = path_[f === 'update-twin' ? 'update' : 'harddelete'];
      if (!fn) { cells[key] = { st: 'n/a' }; return; }
      const id = f === 'update-twin' ? hex() : f === 'harddelete-custom' ? 'wc-custom-' + hex().slice(0, 10) : t;
      await col(c).insertOne(Object.assign(body(c, t, cellId, { _id: id }), c === 'entries' ? { sysTime: iso(t) } : {}));
      out.seed = 'mongo ' + idForm(id);
      const tg = await target();
      measured = () => fn(c, tg.doc, tg.ident);
    } else if (f === 'idread-fail') {
      if (p !== 'ws') { cells[key] = { st: 'n/a' }; return; }
      const h = hex();
      measured = async () => {
        inject.armed = true; inject.fired = 0;
        try { return await createVia(c, body(c, t, cellId, { _id: h })); } finally { inject.armed = false; }
      };
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

    await wireStart(c);
    const before = await docsOf(c, cellId);
    const cursor = await cursorOf(c);
    events = [];
    const st = await measured();
    if (st === null) { cells[key] = { st: 'n/a' }; return; }
    await sleep(250);
    const evs = events.slice(); events = [];
    const after = await docsOf(c, cellId);
    const wired = await wireOf(cellId, before.concat(after));
    out.st = st;
    out.store = storeDesc(after);
    out.srv = srvDesc(before, after);
    out.hist = await histOf(c, cellId, cursor);
    out.ev = evDesc(evs);
    out.wire = wired;
    out.cache = cacheOf(c, cellId);
    out.v1read = await v1readOf(c, cellId);
    if (f === 'idread-fail') out.inj = 'reads failed: ' + inject.fired;
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness after' }; return; }
    cells[key] = out;
  }

  const TT_ONLY = flag('--tt-only');
  if (EARLIER && !TT_ONLY && !IDF_ONLY) for (const c of COLLS) {
    for (const p of PATHS) {
      for (const f of FORMS) {
        if (f === 'update-put' && p !== 'v3') continue;
        if (V2_FORMS.includes(f) || IDF_FORMS.includes(f)) continue;
        await cell(c, p, f);
      }
    }
  }

  // ---- cross-path: create through A, re-send the same body (no _id) through B
  if (EARLIER && !flag('--no-cross') && !TT_ONLY && !IDF_ONLY) {
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

  // ---- Temporary Target cells (see the header). The body is a valid target;
  // `change` is what the measured step sends or applies.
  const TT_FORMS = [];
  if (EARLIER && COLLS.includes('treatments') && !flag('--no-tt') && !IDF_ONLY) {
    const c = 'treatments';
    const ttBody = (t, cell, extra) => Object.assign({ date: t, utcOffset: 0, app: 'wc-lab', wc: cell, wcv: 1
      , eventType: 'Temporary Target', reason: 'wc-lab', targetBottom: 100, targetTop: 120, units: 'mg/dl', duration: 60
      , created_at: iso(t), device: 'wc-lab', enteredBy: 'wc-lab' }, extra || {});
    const ttDesc = docs => docs.length ? docs.map(d => d.targetBottom + '-' + d.targetTop + ' ' + (d.units === undefined ? 'no-units' : d.units)).join(',') : 'none';
    const update = {
      v1: (d, ch) => req('PUT', '/api/v1/treatments/', Object.assign({}, d, ch, { wcv: 2 })).then(r => replyDesc(r))
      , v3: (d, ch, ident) => req('PATCH', '/api/v3/treatments/' + ident, Object.assign({}, ch, { wcv: 2 }), V).then(r => replyDesc(r))
      , ws: (d, ch) => emit('dbUpdate', { collection: c, _id: d._id, data: Object.assign({}, ch, { wcv: 2 }) }).then(a => sockDesc(a))
      , inproc: (d, ch) => cb(fn => ctx.treatments.save(Object.assign({}, d, ch, { _id: d._id, wcv: 2 }), fn)).then(r => inDesc(r))
    };
    const put = (d, ch, ident) => {
      const b = Object.assign({}, d, ch, { wcv: 2 }); delete b._id; delete b.srvModified; delete b.srvCreated; delete b.subject;
      return req('PUT', '/api/v3/treatments/' + ident, b, V).then(r => replyDesc(r));
    };
    const unset = (d, fields) => emit('dbUpdateUnset', { collection: c, _id: d._id, data: fields }).then(a => sockDesc(a));
    // form -> [paths, kind, argument]
    const TT = {
      'tt-create-ok': [PATHS, 'create', {}]
      , 'tt-create-order': [PATHS, 'create', { targetBottom: 150, targetTop: 120 }]
      , 'tt-create-units': [PATHS, 'create', { units: 'mmol' }]
      , 'tt-update-ok': [PATHS, 'update', { targetTop: 130 }]
      , 'tt-update-order': [PATHS, 'update', { targetTop: 80 }]
      , 'tt-put-ok': [['v3'], 'put', { targetTop: 130 }]
      , 'tt-put-order': [['v3'], 'put', { targetTop: 80 }]
      , 'tt-unset-ok': [['ws'], 'unset', { endmills: 1 }]
      , 'tt-unset-target': [['ws'], 'unset', { targetTop: 1 }]
    };
    TT_FORMS.push(...Object.keys(TT));
    for (const p of PATHS) {
      for (const f of TT_FORMS) {
        const [paths, kind, arg] = TT[f];
        if (!paths.includes(p)) continue;
        const key = c + ' ' + p + ' ' + f;
        const cellId = 'wc-tt' + seq + '-' + crypto.randomBytes(3).toString('hex');
        const t = nextT();
        const out = {};
        if (!(await alive())) { cells[key] = { st: 'INVALID liveness before' }; continue; }
        let measured;
        if (kind === 'create') {
          measured = () => P[p].create(c, ttBody(t, cellId, arg));
        } else {
          out.seed = await P[p].create(c, ttBody(t, cellId)); await sleep(80);
          const d = (await docsOf(c, cellId)).slice(-1)[0];
          if (!d) { cells[key] = { st: 'n/a (seed not stored: ' + out.seed + ')' }; continue; }
          const doc = Object.assign({}, d, { _id: d._id instanceof ObjectId ? d._id.toHexString() : d._id });
          const ident = d.identifier || doc._id;
          measured = kind === 'update' ? () => update[p](doc, arg, ident)
            : kind === 'put' ? () => put(doc, arg, ident) : () => unset(doc, arg);
        }
        await wireStart(c);
        const before = await docsOf(c, cellId);
        const cursor = await cursorOf(c);
        events = [];
        out.st = await measured();
        await sleep(250);
        const evs = events.slice(); events = [];
        const after = await docsOf(c, cellId);
        const wired = await wireOf(cellId, before.concat(after));
        out.store = storeDesc(after);
        out.tt = ttDesc(after);
        out.srv = srvDesc(before, after);
        out.hist = await histOf(c, cellId, cursor);
        out.ev = evDesc(evs);
        out.wire = wired;
        out.cache = cacheOf(c, cellId);
        out.v1read = await v1readOf(c, cellId);
        if (!(await alive())) { cells[key] = { st: 'INVALID liveness after' }; continue; }
        cells[key] = out;
      }
    }
  }

  // ---- QC-MATRIX-V2 forms (see the header), after every earlier cell
  if (EARLIER && !TT_ONLY && !IDF_ONLY) for (const c of COLLS) for (const p of PATHS) for (const f of FORMS) {
    if (V2_FORMS.includes(f)) await cell(c, p, f);
  }

  // ---- QC-MATRIX-IDF forms (see the header), after every earlier cell.
  // One client identity field and its value. Each value is new per cell, so no
  // cell can match another cell's record on it.
  const idfIdent = (field, t) => field === 'uuidid' ? { _id: crypto.randomUUID().toUpperCase() } // Loop override
    : { [field]: {
      identifier: crypto.randomUUID() // API v3 clients (AndroidAPS)
      , syncIdentifier: crypto.randomBytes(16).toString('hex') // Loop
      , id: crypto.randomUUID().toUpperCase() // Trio
      , uuid: crypto.randomUUID() // xDrip+
      , NSCLIENT_ID: String(t) // AndroidAPS NSClient (v1), a millisecond time as a string
    }[field] };
  // The re-send's other amount, per collection (variant amt, and record B of a split).
  function idfAmount (c, t) {
    if (c === 'entries') return { sgv: 100 + (t % 50) + 7 };
    if (c === 'treatments') return { carbs: 20 };
    if (c === 'devicestatus') return { uploaderBattery: 70 };
    if (c === 'profile') { const s = body(c, t).store; s.Default.dia = 4; return { store: s }; }
    if (c === 'food') return { carbs: 15 };
    if (c === 'activity') return { steps: 150 };
    return { settings: { units: 'mg/dl', alarmHigh: 200, alarmLow: 70 } };
  }
  // One label per stored record (see the header). `before` is the cell's records
  // just before the measured step.
  function shapeDesc (before, after) {
    if (!after.length) return 'none';
    return after.map(d => {
      const seeded = before.some(b => String(b._id) === String(d._id) && typeof b._id === typeof d._id);
      const sent = d.wcv === 2;
      if (d.wck === 1) return sent ? 'merge' : 'not-written';
      if (seeded) return sent ? 'replace' : 'other';
      return sent ? 'new' : 'other';
    }).join(',');
  }
  // The measured step and every observation an earlier cell records, plus shape.
  // `extra` (QC-MATRIX-IDFMT only) adds fields from the ordered records.
  async function idfMeasure (key, c, cellId, out, measured, extra) {
    await wireStart(c);
    const before = await docsOf(c, cellId);
    const cursor = await cursorOf(c);
    events = [];
    const st = await measured();
    if (st === null) { cells[key] = { st: 'n/a' }; return; }
    await sleep(250);
    const evs = events.slice(); events = [];
    // Seeded records first, in their order, then the records the step created:
    // an _id made by mongod (an upsert's insert) and one made by the driver in
    // the same second sort by each process's random bytes, so _id order is racy.
    const was = d => before.findIndex(b => String(b._id) === String(d._id) && typeof b._id === typeof d._id);
    const after = (await docsOf(c, cellId)).map((d, i) => [was(d), i, d])
      .sort((x, y) => (x[0] === -1 ? 1e9 : x[0]) - (y[0] === -1 ? 1e9 : y[0]) || x[1] - y[1]).map(x => x[2]);
    const wired = await wireOf(cellId, before.concat(after));
    out.st = st;
    out.store = storeDesc(after);
    out.shape = shapeDesc(before, after);
    out.srv = srvDesc(before, after);
    out.hist = await histOf(c, cellId, cursor);
    out.ev = evDesc(evs);
    out.wire = wired;
    out.cache = cacheOf(c, cellId);
    out.v1read = await v1readOf(c, cellId);
    if (extra) extra(out, after);
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness after' }; return; }
    cells[key] = out;
  }
  const idfTarget = async (c, cellId) => {
    const d = (await docsOf(c, cellId)).slice(-1)[0];
    if (!d) return null;
    const plain = Object.assign({}, d, { _id: d._id instanceof ObjectId ? d._id.toHexString() : d._id });
    return { doc: plain, ident: d.identifier || plain._id };
  };
  // Seed through path a, re-send through path b (a === b for a same-path cell).
  async function idfCell (c, a, b, f) {
    const key = a === b ? c + ' ' + a + ' ' + f : c + ' x ' + a + ' x ' + b + ' ' + f;
    const cellId = 'wc-idf' + seq + '-' + crypto.randomBytes(3).toString('hex');
    const t = nextT();
    const out = {};
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness before' }; return; }
    const m = /^idf-(.+)-(same|amt|time|plain|identifier|first|second|written)$/.exec(f);
    const kind = m[1]; const v = m[2];
    let measured;
    if (IDF_FIELDS.includes(kind)) {
      // one identity field, seeded with wck, re-sent with wcv 2
      const fixed = idfIdent(kind, t);
      const mk = extra => body(c, v === 'time' && extra.wcv ? t + 300000 : t, cellId
        , Object.assign({}, fixed, extra, v === 'amt' && extra.wcv ? idfAmount(c, t) : {}));
      out.seed = await P[a].create(c, mk({ wck: 1 })); await sleep(80);
      if (out.seed === null) { cells[key] = { st: 'n/a' }; return; }
      measured = () => P[b].create(c, mk({ wcv: 2 }));
    } else if (kind === 'softdel' || kind === 'harddel' || kind === 'v3del') {
      const fixed = v === 'identifier' ? idfIdent('identifier', t) : {};
      const mk = extra => body(c, t, cellId, Object.assign({}, fixed, extra));
      out.seed = await P[a].create(c, mk({ wck: 1 })); await sleep(80);
      if (out.seed === null) { cells[key] = { st: 'n/a' }; return; }
      const tg = await idfTarget(c, cellId);
      if (!tg) { cells[key] = { st: 'n/a (seed not stored: ' + out.seed + ')' }; return; }
      const del = kind === 'v3del' ? (V3[c] ? P.v3.softdelete : null) : P[a][kind === 'softdel' ? 'softdelete' : 'harddelete'];
      const dr = del ? await del(c, tg.doc, tg.ident) : null;
      if (dr === null) { cells[key] = { st: 'n/a' }; return; }
      out.del = dr; await sleep(80);
      measured = () => P[b].create(c, mk({ wcv: 2 }));
    } else if (kind === 'split') {
      // A at t, B two minutes later with another amount, one identifier
      const fixed = idfIdent('identifier', t);
      const tB = t + 120000;
      const mkA = extra => body(c, t, cellId, Object.assign({}, fixed, extra));
      const mkB = extra => body(c, tB, cellId, Object.assign({}, fixed, idfAmount(c, t), extra));
      if (v === 'written') {
        const ra = await P[a].create(c, mkA({ wck: 1 })); await sleep(80);
        if (ra === null) { cells[key] = { st: 'n/a' }; return; }
        const rb = await P[a].create(c, mkB({ wck: 1 })); await sleep(80);
        out.seed = ra + '; ' + rb;
      } else {
        if (P[a].create === undefined || (a === 'v3' && !V3[c])) { cells[key] = { st: 'n/a' }; return; }
        // server dates from the clock, as a write now would stamp them: the
        // record's own time can be in the future late in a run, and a future
        // srvModified would put every later history cursor past every write
        const stored = (tt, d) => { const now = Date.now(); return Object.assign(d, { _id: new ObjectId(), srvCreated: now, srvModified: now }
          , c === 'entries' ? { sysTime: iso(tt) } : {}); };
        await col(c).insertOne(stored(t, mkA({ wck: 1 })));
        await col(c).insertOne(stored(tB, mkB({ wck: 1 })));
        out.seed = 'mongo OID,OID';
      }
      measured = () => P[b].create(c, v === 'second' ? mkB({ wcv: 2 }) : mkA({ wcv: 2 }));
    }
    await idfMeasure(key, c, cellId, out, measured);
  }

  const IDF_COLLS = opt('--only', null) ? COLLS : COLLS.concat(['settings']);
  if (EARLIER && !TT_ONLY && !flag('--no-idf')) {
    for (const c of IDF_COLLS) {
      const paths = c === 'settings' ? PATHS.filter(p => p === 'v3') : PATHS;
      // settings: the earlier forms, through the generic cell
      if (c === 'settings') for (const f of ['create', 'resend-identity', 'update', 'update-put', 'softdelete', 'harddelete']) {
        if (paths.includes('v3') && FORMS.includes(f)) await cell(c, 'v3', f);
      }
      for (const p of paths) for (const f of FORMS) if (IDF_FORMS.includes(f)) await idfCell(c, p, p, f);
    }
    // across paths: the identity forms only
    if (!flag('--no-cross')) for (const c of IDF_COLLS) {
      if (c === 'settings') continue;
      for (const a of PATHS) for (const b of PATHS) {
        if (a === b) continue;
        if ((a === 'v3' || b === 'v3') && !V3[c]) continue;
        for (const f of FORMS) {
          if (!IDF_FORMS.includes(f) || !IDF_FIELDS.includes(f.split('-')[1]) || f.endsWith('-amt')) continue;
          await idfCell(c, a, b, f);
        }
      }
    }
  }

  // ---- QC-MATRIX-IDFMT forms (see the header), after every earlier cell.
  const IDFMT_FIXED = { undefined: 'undefined', null: 'null', invalid: 'invalid', nan: 'NaN', unknown: 'unknown'
    , empty: '', blank: '   ', jsonnull: null, idundef: 'undefined' };
  // The value a cell sends; the classes not in IDFMT_FIXED are new per cell.
  function idfmtValue (k, t) {
    if (Object.prototype.hasOwnProperty.call(IDFMT_FIXED, k)) return IDFMT_FIXED[k];
    const h = crypto.randomBytes(16).toString('hex');
    if (k === 'number') return t;
    if (k === 'len256' || k === 'len257') return ('wc-' + h + crypto.randomBytes(160).toString('hex')).slice(0, k === 'len256' ? 256 : 257);
    if (k === 'urlsafe') return 'wc_' + h + '.~-A';
    if (k === 'colon') return 'glooko:bolus:' + crypto.createHash('sha256').update(h).digest('hex');
    if (k === 'slash') return 'wc/' + h + '/dose';
    if (k === 'nonascii') return 'wc-\u00fc-\u65e5\u672c-' + h;
    throw new Error('idfmt class ' + k);
  }
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  function identDesc (docs, sent) {
    if (!docs.length) return 'none';
    return docs.map(d => {
      if (!Object.prototype.hasOwnProperty.call(d, 'identifier')) return 'absent';
      const v = d.identifier;
      if (v === sent) return 'kept';
      if (v === null) return 'null';
      if (typeof v === 'number') return 'num';
      if (typeof v !== 'string') return typeof v;
      if (v === '') return 'empty';
      if (UUID_RE.test(v)) return 'uuid';
      return 'str' + v.length + (typeof sent === 'string' && v === sent.trim() ? ' trimmed' : '');
    }).join(',');
  }
  async function idfmtCell (c, a, b, f) {
    const key = a === b ? c + ' ' + a + ' ' + f : c + ' x ' + a + ' x ' + b + ' ' + f;
    const cellId = 'wc-idfmt' + seq + '-' + crypto.randomBytes(3).toString('hex');
    const t = nextT();
    const out = {};
    if (!(await alive())) { cells[key] = { st: 'INVALID liveness before' }; return; }
    const m = /^idfmt-(.+)-(time|single|twoapp)$/.exec(f);
    const k = m[1]; const mode = m[2];
    const val = idfmtValue(k, t);
    // no record from an earlier cell carries the fixed value
    if (Object.prototype.hasOwnProperty.call(IDFMT_FIXED, k)) {
      await col(c).deleteMany(val === null ? { identifier: { $type: 'null' } } : { $or: [{ identifier: val }, { _id: val }] });
    }
    const fixed = k === 'idundef' ? { _id: val } : { identifier: val };
    const mk = (tt, extra) => body(c, tt, cellId, Object.assign({}, fixed, extra));
    let measured;
    if (mode === 'single') {
      if (!P[b].create || (b === 'v3' && !V3[c])) { cells[key] = { st: 'n/a' }; return; }
      measured = () => P[b].create(c, mk(t, { wcv: 2 }));
    } else {
      out.seed = await P[a].create(c, mk(t, { wck: 1 })); await sleep(80);
      if (out.seed === null) { cells[key] = { st: 'n/a' }; return; }
      measured = mode === 'time' ? () => P[b].create(c, mk(t + 300000, { wcv: 2 }))
        : () => P[b].create(c, mk(t + 150000, Object.assign({ app: 'wc-app-b', device: 'wc-app-b', enteredBy: 'wc-app-b' }
          , idfAmount(c, t), { wcv: 2 })));
    }
    await idfMeasure(key, c, cellId, out, measured, (o, after) => { o.ident = identDesc(after, val); });
  }

  if (!TT_ONLY && !IDF_ONLY && !flag('--no-idfmt')) {
    for (const c of IDF_COLLS) {
      const paths = c === 'settings' ? PATHS.filter(p => p === 'v3') : PATHS;
      for (const p of paths) for (const f of IDFMT_FORMS) await idfmtCell(c, p, p, f);
    }
    if (!flag('--no-cross')) for (const c of IDF_COLLS) {
      if (c === 'settings') continue;
      for (const a of PATHS) for (const b of PATHS) {
        if (a === b) continue;
        if ((a === 'v3' || b === 'v3') && !V3[c]) continue;
        for (const f of IDFMT_FORMS) if (!f.endsWith('-single')) await idfmtCell(c, a, b, f);
      }
    }
  }

  const result = {
    head, dirty_lib: dirty || '', node: process.version, mongod: serverVersion, db: DBNAME
    , write_validation: env.writeValidation === undefined ? '(not read by this build)' : env.writeValidation
    , date: new Date().toISOString(), collections: COLLS, paths: PATHS
    , forms: TT_ONLY ? TT_FORMS : IDF_ONLY ? FORMS.filter(f => IDF_FORMS.includes(f)) : IDFMT_ONLY ? IDFMT_FORMS
      : FORMS.filter(f => !V2_FORMS.includes(f) && !IDF_FORMS.includes(f)).concat(TT_FORMS, FORMS.filter(f => V2_FORMS.includes(f)), FORMS.filter(f => IDF_FORMS.includes(f))
        , flag('--no-idfmt') ? [] : IDFMT_FORMS)
    , idf_collections: IDF_COLLS, uuid_handling: env.uuidHandling
    , wire_settle: { quiet_ms: WIRE_QUIET, max_ms: WIRE_SETTLE_MAX, emitted: wireStat.emitted, received: wireStat.received
      , bound_hits: wireStat.timeouts, frames_not_attributed: wireStat.rejected, injected_foreign: wireStat.injected }
    , cells
  };
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  else console.log(JSON.stringify(result, null, 1));
  console.error('cells: ' + Object.keys(cells).length + ', invalid: ' + Object.values(cells).filter(x => /INVALID/.test(x.st)).length
    + '; wire frames emitted ' + wireStat.emitted + ', received ' + wireStat.received + ', not attributed ' + wireStat.rejected
    + ', settle bound hits ' + wireStat.timeouts + (wireStat.injected ? ', injected foreign ' + wireStat.injected : ''));

  sock.close();
  storage.close();
  await db.dropDatabase();
  await cli.close();
  ctx.bus.emit('teardown');
  server.close();
  setTimeout(() => process.exit(0), 500);
})().catch(e => { console.error(e); process.exit(1); });
