'use strict';
/*
 * bf09-dedup-zero.js — BF-09 measured through the live socket path.
 *
 * What socket `dbAdd` dedup does with falsy values (0, '', false, null), and
 * whether treating a zero as a real value would change what is stored and
 * what the basal chart draws. No fix is proposed here; this is the evidence
 * for the maintainer's decision.
 *
 *   CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:<port>/<db containing "test"> \
 *     node tools/remedial/bf3/bf09-dedup-zero.js <cgm-remote-monitor tree>
 *
 * Arms, each a separate child process with its own require cache:
 *   shipped    the tree as it is (lib/server/websocket.js truthiness keys)
 *   zero-real  a scratch copy of the tree's lib/ in which each numeric key
 *              test `if (data.data.X)` becomes `if (data.data.X || data.data.X === 0)`
 *              for insulin, carbs, percent, absolute and duration — the
 *              smallest change that makes 0 a key and leaves '', false,
 *              null and absent as they are.
 *
 * For every case the harness records what each arm STORED, then renders the
 * temp-basal line from the stored records through the tree's own
 * ddata.processTreatments -> profilefunctions.updateTreatments ->
 * getBasalRenderTimes/getTempBasal, i.e. the path lib/client/renderer.js
 * takes. The reference ("sent") is the same render over every record that
 * was sent, with no dedup. Rendered with the shipped sampler (1-minute step
 * plus every temp's start and end, 846bb690) and, for context, with a bare
 * 1-minute step, the sampler bec641ca replaced.
 *
 * Writes to the database named in CUSTOMCONNSTR_mongo, and deletes every
 * treatment in it between cases. The database name must contain "test".
 * Prints a table and a JSON line. Exit 0 unless the harness itself fails.
 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync, spawnSync } = require('child_process');

const HERE = __filename;
const MIN = 60 * 1000;
const SEC = 1000;

/* ------------------------------------------------------------------ cases */
// Offsets in ms from T0. Every case stays inside the ±2 s dedup window unless
// it says otherwise. AAPS NSClient v1 (plugins/sync/.../TemporaryBasalExtension.kt)
// sends a temp basal with eventType 'Temp Basal', duration in whole minutes,
// durationInMilliseconds, and EITHER absolute OR percent (rate - 100), and no
// NSCLIENT_ID.
function tb (at, fields) { return Object.assign({ at, eventType: 'Temp Basal', enteredBy: 'bf09-harness' }, fields); }
const CASES = [
  { id: 'Z1', about: 'zero temp re-sent 1 s later (same content)', sends: [tb(0, { absolute: 0, duration: 30 }), tb(1 * SEC, { absolute: 0, duration: 30 })] },
  { id: 'Z2', about: '1.2 U/h temp, then a zero temp 1 s later, same duration', sends: [tb(0, { absolute: 1.2, duration: 30 }), tb(1 * SEC, { absolute: 0, duration: 30 })] },
  { id: 'Z3', about: 'zero temp, then a 1.2 U/h temp 1 s later, same duration', sends: [tb(0, { absolute: 0, duration: 30 }), tb(1 * SEC, { absolute: 1.2, duration: 30 })] },
  { id: 'Z4', about: 'zero temp, then a zero temp of a different duration 1 s later', sends: [tb(0, { absolute: 0, duration: 30 }), tb(1 * SEC, { absolute: 0, duration: 60 })] },
  { id: 'Z5', about: 'zero temp, then a cancel (duration 0, no rate) 1 s later', sends: [tb(0, { absolute: 0, duration: 30 }), tb(1 * SEC, { duration: 0 })] },
  { id: 'Z6', about: 'sub-minute zero temp (duration 0, durationInMilliseconds 40000), then a 1.2 U/h temp 1.5 s later', sends: [tb(0, { absolute: 0, duration: 0, durationInMilliseconds: 40000 }), tb(1500, { absolute: 1.2, duration: 30 })] },
  { id: 'X1', about: 'zero temp, then a Temporary Target of the same duration 1 s later', sends: [tb(0, { absolute: 0, duration: 30 }), { at: 1 * SEC, eventType: 'Temporary Target', enteredBy: 'bf09-harness', duration: 30, targetTop: 140, targetBottom: 140, units: 'mg/dl' }] },
  { id: 'X2', about: 'Temporary Target, then a zero temp of the same duration 1 s later', sends: [{ at: 0, eventType: 'Temporary Target', enteredBy: 'bf09-harness', duration: 30, targetTop: 140, targetBottom: 140, units: 'mg/dl' }, tb(1 * SEC, { absolute: 0, duration: 30 })] },
  { id: 'P1', about: 'control: AAPS percent-mode zero temp (percent -100) then 1.2 U/h 1 s later', sends: [tb(0, { percent: -100, duration: 30 }), tb(1 * SEC, { absolute: 1.2, duration: 30 })] },
  { id: 'N1', about: 'control: two zero temps 1 s apart with different NSCLIENT_IDs', sends: [tb(0, { absolute: 0, duration: 30, NSCLIENT_ID: 'bf09-a' }), tb(1 * SEC, { absolute: 0, duration: 30, NSCLIENT_ID: 'bf09-b' })] },
  { id: 'W1', about: 'control: 1.2 U/h, then zero temp 3 s later (outside the window)', sends: [tb(0, { absolute: 1.2, duration: 30 }), tb(3 * SEC, { absolute: 0, duration: 30 })] },
  { id: 'F1', about: "falsy non-numbers: absolute '' then absolute 1.2, 1 s apart", sends: [tb(0, { absolute: '', duration: 30 }), tb(1 * SEC, { absolute: 1.2, duration: 30 })] },
  { id: 'F2', about: 'falsy non-numbers: absolute false then absolute 1.2, 1 s apart', sends: [tb(0, { absolute: false, duration: 30 }), tb(1 * SEC, { absolute: 1.2, duration: 30 })] },
  { id: 'F3', about: 'falsy non-numbers: absolute null then absolute 1.2, 1 s apart', sends: [tb(0, { absolute: null, duration: 30 }), tb(1 * SEC, { absolute: 1.2, duration: 30 })] },
  { id: 'B1', about: 'insulin 0 bolus, then a 1 U bolus 1 s later (zero never occurs in the corpus)', sends: [{ at: 0, eventType: 'Correction Bolus', enteredBy: 'bf09-harness', insulin: 0 }, { at: 1 * SEC, eventType: 'Correction Bolus', enteredBy: 'bf09-harness', insulin: 1 }] },
  { id: 'C1', about: 'carbs 0 entry, then a 20 g entry 1 s later (zero never occurs in the corpus)', sends: [{ at: 0, eventType: 'Carb Correction', enteredBy: 'bf09-harness', carbs: 0 }, { at: 1 * SEC, eventType: 'Carb Correction', enteredBy: 'bf09-harness', carbs: 20 }] },
  { id: 'B2', about: '1 U bolus, then an insulin 0 bolus 1 s later', sends: [{ at: 0, eventType: 'Correction Bolus', enteredBy: 'bf09-harness', insulin: 1 }, { at: 1 * SEC, eventType: 'Correction Bolus', enteredBy: 'bf09-harness', insulin: 0 }] },
  { id: 'C2', about: '20 g entry, then a carbs 0 entry 1 s later', sends: [{ at: 0, eventType: 'Carb Correction', enteredBy: 'bf09-harness', carbs: 20 }, { at: 1 * SEC, eventType: 'Carb Correction', enteredBy: 'bf09-harness', carbs: 0 }] },
  { id: 'P2', about: 'percent-mode 150% temp (percent 50), then a 100% temp (percent 0) 1 s later, same duration', sends: [tb(0, { percent: 50, duration: 30 }), tb(1 * SEC, { percent: 0, duration: 30 })] }
];

/* ------------------------------------------------------------- child arm */
async function childArm (tree) {
  process.chdir(tree);
  const req = (p) => require(path.join(tree, p));
  const crypto = require('crypto');
  process.env.API_SECRET = process.env.API_SECRET || 'bf09 harness long pass phrase';
  const secret = process.env.API_SECRET; // lib/server/env removes it from process.env
  const language = req('lib/language')();
  const env = req('lib/server/env')();
  env.settings.authDefaultRoles = 'readable';
  env.settings.enable = ['careportal', 'api'];
  const http = require('http');
  const io = require(path.join(tree, 'node_modules/socket.io-client'));

  const ctx = await new Promise((resolve) => req('lib/server/bootevent')(env, language).boot(resolve));
  const dbName = ctx.store.db.databaseName;
  if (!/test/i.test(dbName)) { throw new Error('refusing: database name "' + dbName + '" does not contain "test"'); }
  ctx.ddata = req('lib/data/ddata')();
  const server = http.createServer(require(path.join(tree, 'node_modules/express'))());
  req('lib/server/websocket')(env, ctx, server);
  await new Promise((r) => server.listen(0, r));
  const port = server.address().port;
  const col = ctx.store.collection(env.treatments_collection);

  const socket = io('http://localhost:' + port, { transports: ['websocket'], reconnection: false });
  await new Promise((resolve, reject) => {
    socket.on('connect', () => socket.emit('authorize', {
      client: 'bf09', secret: crypto.createHash('sha1').update(secret).digest('hex')
    }, (auth) => auth && auth.write_treatment ? resolve() : reject(new Error('not authorized to write treatments: ' + JSON.stringify(auth)))));
    socket.on('connect_error', reject);
  });

  const T0 = Math.floor((Date.now() - 60 * MIN) / 1000) * 1000;
  const out = {};
  for (const c of CASES) {
    await col.deleteMany({});
    const replies = [];
    for (const s of c.sends) {
      const doc = Object.assign({}, s, { created_at: new Date(T0 + s.at).toISOString() });
      delete doc.at;
      const reply = await new Promise((r) => socket.emit('dbAdd', { collection: 'treatments', data: doc }, r));
      replies.push(reply && reply[0] ? { _id: String(reply[0]._id) } : null);
    }
    const stored = (await col.find({}).sort({ created_at: 1 }).toArray()).map((d) => {
      const o = Object.assign({}, d); o._id = String(o._id); delete o.srvModified; return o;
    });
    out[c.id] = { T0, replies, stored };
  }
  socket.disconnect();
  server.close();
  await col.deleteMany({});
  process.stdout.write('BF09-ARM ' + JSON.stringify({ dbName, cases: out }) + '\n');
  process.exit(0);
}

/* ------------------------------------------------------- variant builder */
function buildZeroRealTree (tree) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bf09-zero-real-'));
  for (const p of ['lib', 'translations', 'package.json', 'static', 'views', 'bundle']) {
    if (fs.existsSync(path.join(tree, p))) fs.cpSync(path.join(tree, p), path.join(dir, p), { recursive: true });
  }
  fs.symlinkSync(path.join(tree, 'node_modules'), path.join(dir, 'node_modules'));
  const ws = path.join(dir, 'lib/server/websocket.js');
  let src = fs.readFileSync(ws, 'utf8');
  let n = 0;
  for (const f of ['insulin', 'carbs', 'percent', 'absolute', 'duration']) {
    const from = `if (data.data.${f}) {`;
    const count = src.split(from).length - 1;
    if (count !== 1) throw new Error(`expected exactly one "${from}" in websocket.js, found ${count}: the shipped code has moved, re-derive the variant`);
    src = src.replace(from, `if (data.data.${f} || data.data.${f} === 0) {`);
    n += 1;
  }
  fs.writeFileSync(ws, src);
  return { dir, replaced: n };
}

function runArm (tree) {
  const r = spawnSync(process.execPath, [HERE, '--child', tree], { encoding: 'utf8', env: process.env, maxBuffer: 64 * 1024 * 1024, timeout: 120000 });
  const line = (r.stdout || '').split('\n').find((l) => l.startsWith('BF09-ARM '));
  if (!line) throw new Error('arm failed for ' + tree + ':\n' + (r.stderr || '').slice(-4000) + (r.stdout || '').slice(-2000));
  return JSON.parse(line.slice('BF09-ARM '.length));
}

/* --------------------------------------------------------------- render */
function renderer (tree) {
  const req = (p) => require(path.join(tree, p));
  const cwd = process.cwd(); process.chdir(tree);
  const ctx = { language: req('lib/language')(), settings: req('lib/settings')(), levels: req('lib/levels'), moment: require(path.join(tree, 'node_modules/moment-timezone')) };
  process.chdir(cwd);
  const PROFILE = [{ defaultProfile: 'Default', startDate: '2000-01-01T00:00:00.000Z', mills: 0, units: 'mg/dl',
    store: { Default: { dia: 3, timezone: 'UTC', units: 'mg/dl', basal: [{ time: '00:00', value: 1.0 }], carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }] } } }];

  // Each render is evaluated to completion, over a 1-second grid, before the
  // next profile is built. lib/profilefunctions.js keeps `prevBasalTreatment`
  // at MODULE scope (shared by every profile instance in the process) and
  // tempBasalTreatment() returns it whenever the time falls inside it, so two
  // interleaved renders read each other's temp basals. profile.clear() resets
  // it; updateTreatments() does not.
  return function render (docs, from, to) {
    const ddata = req('lib/data/ddata')();
    ddata.treatments = docs.map((d) => Object.assign({}, d, { mills: Date.parse(d.created_at) }));
    ddata.processTreatments(true);
    const profile = req('lib/profilefunctions')(null, ctx);
    profile.clear();
    profile.loadData(JSON.parse(JSON.stringify(PROFILE)));
    profile.updateTreatments([], ddata.tempbasalTreatments, []);
    const exact = (t) => profile.getTempBasal(t).tempbasal;
    // the renderer draws a step from each sample time to the next
    function stepSeries (samples) {
      const vals = samples.map((x) => [x, exact(x)]);
      const out = []; let i = 0; let v = vals[0][1];
      for (let t = from; t < to; t += SEC) { while (i < vals.length && vals[i][0] <= t) { v = vals[i][1]; i += 1; } out.push(v); }
      return out;
    }
    const exactArr = []; for (let t = from; t < to; t += SEC) exactArr.push(exact(t));
    const shipped = stepSeries(profile.getBasalRenderTimes(from, to, MIN));
    const bareTimes = []; for (let t = from; t <= to; t += MIN) bareTimes.push(t);
    const bare = stepSeries(bareTimes);
    profile.clear();
    return { exact: exactArr, shipped, bare };
  };
}

function compare (render, sentDocs, storedDocs, from, to) {
  const ref = render(sentDocs, from, to);
  const got = render(storedDocs, from, to);
  let exactDiff = 0; let shippedDiff = 0; let bareVsRef = 0; let uRef = 0; let uGot = 0;
  for (let i = 0; i < ref.exact.length; i++) {
    const r = ref.exact[i];
    if (got.exact[i] !== r) exactDiff += 1;
    if (got.shipped[i] !== r) shippedDiff += 1;
    if (ref.bare[i] !== r) bareVsRef += 1;
    uRef += r / 3600; uGot += got.exact[i] / 3600;
  }
  return { exactDiffSecs: exactDiff, shippedRenderDiffSecs: shippedDiff, bareMinuteRenderOfSentDiffSecs: bareVsRef, unitsSent: +uRef.toFixed(3), unitsStored: +uGot.toFixed(3) };
}

/* ----------------------------------------------------------------- main */
async function main () {
  if (process.argv[2] === '--child') return childArm(path.resolve(process.argv[3]));
  const tree = path.resolve(process.argv[2] || '.');
  if (!process.env.CUSTOMCONNSTR_mongo || !/test/i.test(process.env.CUSTOMCONNSTR_mongo.split('/').pop())) {
    throw new Error('set CUSTOMCONNSTR_mongo to a database whose name contains "test"');
  }
  process.env.NODE_ENV = 'test';
  let head = 'unknown'; try { head = execFileSync('git', ['-C', tree, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim(); } catch (e) { /* not a checkout */ }

  const variant = buildZeroRealTree(tree);
  const arms = { shipped: runArm(tree), 'zero-real': runArm(variant.dir) };
  fs.rmSync(variant.dir, { recursive: true, force: true });

  const render = renderer(tree);
  const rows = [];
  for (const c of CASES) {
    const row = { id: c.id, about: c.about };
    for (const arm of Object.keys(arms)) {
      const r = arms[arm].cases[c.id];
      const T0 = r.T0;
      const sent = c.sends.map((s) => { const d = Object.assign({}, s, { created_at: new Date(T0 + s.at).toISOString() }); delete d.at; return d; });
      const from = T0 - 5 * MIN; const to = T0 + 70 * MIN;
      const kept = r.stored.map((d) => {
        const idx = sent.findIndex((s) => Object.keys(s).every((k) => k === 'created_at' || JSON.stringify(s[k]) === JSON.stringify(d[k])));
        return idx;
      });
      row[arm] = Object.assign({ stored: r.stored.length, keptSends: kept, storedCreatedAtOffsetsMs: r.stored.map((d) => Date.parse(d.created_at) - T0) }, compare(render, sent, r.stored, from, to));
    }
    rows.push(row);
  }

  const pad = (s, n) => String(s).padEnd(n);
  console.log(`tree ${tree} @ ${head}; zero-real variant replaced ${variant.replaced} key tests; db ${arms.shipped.dbName}`);
  console.log(pad('case', 5) + pad('arm', 10) + pad('stored', 7) + pad('kept', 8) + pad('at(ms)', 12) + pad('exactΔs', 9) + pad('drawnΔs', 9) + pad('U sent', 8) + pad('U stored', 9) + 'about');
  for (const r of rows) {
    for (const arm of Object.keys(arms)) {
      const a = r[arm];
      console.log(pad(r.id, 5) + pad(arm, 10) + pad(a.stored + '/' + CASES.find((c) => c.id === r.id).sends.length, 7) + pad(JSON.stringify(a.keptSends), 8) + pad(JSON.stringify(a.storedCreatedAtOffsetsMs), 12) + pad(a.exactDiffSecs, 9) + pad(a.shippedRenderDiffSecs, 9) + pad(a.unitsSent, 8) + pad(a.unitsStored, 9) + (arm === 'shipped' ? r.about : ''));
    }
  }
  console.log('bare 1-minute sampler (pre-bec641ca shape) vs exact, over every SENT record: ' + rows.map((r) => r.id + '=' + r.shipped.bareMinuteRenderOfSentDiffSecs + 's').join(' '));
  console.log('BF09-RESULT ' + JSON.stringify({ tree, head, rows }));
}

main().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
