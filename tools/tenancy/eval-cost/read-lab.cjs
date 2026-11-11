'use strict';

// Evaluator cost lane, candidate A: the in-process projection reads
// (lib/storage/projection-memory-read.js) against the SQL path they replace
// (postgres-projection-read.js: jsonb_to_recordset on actual PostgreSQL), with
// mingo (D8) as the MongoDB-semantics oracle.
//
// Three arms for every read the views make (findFiltered, findOne,
// findOneFilter, count, through the collection intent's legacy translation):
//   sql     the shipping path on PostgreSQL;
//   memory  the in-process path;
//   mingo   toMongo(ast) evaluated by mingo over the same documents
//           (membership, then sort/limit), as an oracle for both.
// A read is EQUAL when memory returns exactly the sql documents (typed _id,
// content, key order) in the same order; ORDER-ONLY when the same documents
// come back in another order (rows equal on every sort key: PostgreSQL leaves
// their order unspecified); otherwise DIFFERENT. End to end, every instant also
// compares the whole working set and the plugin output of a view read through
// each arm.
//
// Datasets: the views-equality synthetic scenarios and corpus sets
// (VIEWS_CORPUS_DIR, read in place, reported by position), the views-replay
// timelines, and a typed-twin/sort-tie set. Synthetic _id values are given
// here; every seventh document carries an ObjectId-kind _id.
//
//   CRM_ROOT=<crm tree> NS_TEST_POSTGRES_ADMIN_URI=<disposable *_test db> [VIEWS_CORPUS_DIR=<dir>] node read-lab.cjs
const path = require('node:path'), util = require('node:util'), crypto = require('node:crypto');
const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI) { process.stderr.write('CRM_ROOT and NS_TEST_POSTGRES_ADMIN_URI required\n'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
const mingo = require(path.join(__dirname, '../../seam/node_modules/mingo'));
const { Pool } = req('node_modules/pg');
const { ObjectId } = req('node_modules/mongodb');
const scope = req('lib/storage/tenant-scope');
const projectionRead = req('lib/storage/postgres-projection-read');
const evaluator = req('lib/data/tenant-projection-evaluator');
const viewsFactory = req('lib/data/views');
const environment = req('lib/server/tenant-app/environment');
const { toMongo } = req('lib/storage/filter');
const clock = req('tests/lib/views-replay/clock');
const { SCENARIOS, corpusNames, loadCorpus } = req('tests/lib/views-equality/fixtures');
const { TIMELINES } = req('tests/lib/views-replay/timelines');
console.log = () => {}; console.info = () => {}; console.warn = () => {};
const say = line => process.stdout.write(line + '\n');

const TENANT = '7e7e7e7e-0000-4000-8000-00000000eca1';
const MIN = 60000, HOUR = 60 * MIN;
const PLUGINS = ['bgnow', 'delta', 'direction', 'rawbg', 'timeago', 'upbat', 'ar2', 'simplealarms', 'errorcodes', 'iob', 'cob',
  'careportal', 'pump', 'openaps', 'xdripjs', 'loop', 'bwp', 'cage', 'sage', 'iage', 'bage', 'treatmentnotify', 'basal',
  'dbsize', 'devicestatus', 'profile', 'bolus', 'override'];

function withIds (records, tag) {
  const out = {};
  for (const [domain, docs] of Object.entries(records)) {
    out[domain] = (docs || []).map((doc, i) => {
      const hex = crypto.createHash('md5').update(tag + '/' + domain + '/' + i).digest('hex').slice(0, 24);
      return { ...doc, _id: i % 7 === 3 ? new ObjectId(hex) : domain + '-' + i };
    });
  }
  return out;
}

// Typed twins (an ObjectId _id and its same-spelling string) and rows equal
// on every sort key the loader uses.
function twinsAndTies (now) {
  const hex = n => n.toString(16).padStart(24, '0');
  const entries = [], treatments = [], devicestatus = [];
  for (let k = 0; k < 24; k++) {
    const at = now - k * 5 * MIN;
    entries.push({ _id: hex(k), type: 'sgv', sgv: 100 + k, date: at, dateString: new Date(at).toISOString(), direction: 'Flat' });
    entries.push({ _id: new ObjectId(hex(k)), type: 'sgv', sgv: 200 + k, date: at, dateString: new Date(at).toISOString(), direction: 'Flat' });
    if (k % 3 === 0) entries.push({ _id: 'mbg-' + k, type: 'mbg', mbg: 150, date: at, dateString: new Date(at).toISOString() });
  }
  for (let k = 0; k < 10; k++) {
    const at = new Date(now - k * 20 * MIN).toISOString();
    treatments.push({ _id: 'tie-a-' + k, created_at: at, eventType: 'Note', notes: 'a' });
    treatments.push({ _id: new ObjectId(hex(1000 + k)), created_at: at, eventType: 'Note', notes: 'b' });
    treatments.push({ _id: hex(1000 + k), created_at: at, eventType: 'Site Change' });
    devicestatus.push({ _id: 'ds-a-' + k, created_at: at, device: 'u1', uploader: { battery: 50 + k } });
    devicestatus.push({ _id: new ObjectId(hex(2000 + k)), created_at: at, device: 'u2', uploader: { battery: 70 - k } });
  }
  return { entries, treatments, devicestatus, profile: SCENARIOS.steady(now).profile.map((doc, i) => ({ ...doc, _id: 'profile-' + i })) };
}

const typed = doc => [doc && typeof doc._id === 'string' ? 's' : 'o', JSON.stringify(doc)];
const sameDocs = (a, b) => util.isDeepStrictEqual(a.map(typed), b.map(typed));
const sortedSame = (a, b) => util.isDeepStrictEqual(a.map(typed).map(JSON.stringify).sort(), b.map(typed).map(JSON.stringify).sort());

(async () => {
  // POOL=1 (default): the SQL arm's reads complete in the order they are made,
  // as the in-process reads do. The data loader keeps whichever copy of a
  // treatment two of its reads both return merges last, so with POOL>1 the
  // SQL arm's working set can differ in that copy's fields (read completion
  // order, not the answers).
  const pool = new Pool({ connectionString: process.env.NS_TEST_POSTGRES_ADMIN_URI, max: Number(process.env.POOL || 1) });
  const connection = { query: (text, values) => pool.query(text, values) };
  scope.setTenancyMode('multi'); clock.install();
  const totals = { reads: 0, equal: 0, orderOnly: 0, different: 0, refusedBoth: 0, refusedOne: 0,
    mingoMembership: 0, mingoMembershipDiffer: 0, mingoOrder: 0, mingoOrderDiffer: 0, instants: 0, workingSetEqual: 0, outputEqual: 0,
    totalEqual: 0, totalDifferent: 0, mongoMatchesToday: 0, mongoMatchesTotal: 0, mongoBoth: 0, mongoNeither: 0,
    totalPathsOutputEqual: 0, outputChangedWithoutTie: 0 };
  const tieReads = new Map(), mongoNeither = new Map(), changes = new Map();
  const mongoClient = process.env.MONGO_URI ? new (req('node_modules/mongodb').MongoClient)(process.env.MONGO_URI) : null;
  if (mongoClient) await mongoClient.connect();
  const mongoDb = mongoClient ? mongoClient.db('ec_read_lab') : null;
  const examples = [];
  const byMethod = {};
  async function instant (name, records, env, now) {
    const documents = Object.fromEntries(evaluator.domains.map(d => [d, records[d] || []]));
    // sql: today's SQL path (ties in PostgreSQL's unspecified order).
    // memory / sqlTotal: decision view-reads-total-order on each path, the
    // insertion ordinal being the document's position in its dataset (the
    // order MongoDB receives them in below).
    const sql = {}, memory = {}, sqlTotal = {};
    let tieReadsHere = 0;
    for (const d of evaluator.domains) {
      sql[d] = projectionRead({ tenant: TENANT, connection, logical: d, documents: documents[d], maxRows: 100000, maxBytes: 256 * 1024 * 1024, env });
      const prepared = projectionRead.prepare({ documents: documents[d], ordinals: documents[d].map((_, i) => i + 1), maxRows: 100000, maxBytes: 256 * 1024 * 1024, memory: true });
      memory[d] = projectionRead({ tenant: TENANT, connection, logical: d, prepared, memory: true, totalOrder: true, maxRows: 100000, maxBytes: 256 * 1024 * 1024, env });
      sqlTotal[d] = projectionRead({ tenant: TENANT, connection, logical: d, prepared, totalOrder: true, maxRows: 100000, maxBytes: 256 * 1024 * 1024, env });
      if (mongoDb) {
        await mongoDb.collection(d).deleteMany({});
        if (documents[d].length) await mongoDb.collection(d).insertMany(documents[d].map(doc => ({ ...doc })), { ordered: true });
      }
    }
    // The dual store: every call to both arms (and mingo), the sql answer used.
    const dual = d => Object.fromEntries(['findFiltered', 'findOne', 'findOneFilter', 'count'].map(method => [method, async (...args) => {
      let a, b, ea, eb;
      try { a = await sql[d][method](...args); } catch (e) { ea = e; }
      try { b = await memory[d][method](...args); } catch (e) { eb = e; }
      totals.reads++;
      const key = d + '.' + method;
      byMethod[key] = (byMethod[key] || 0) + 1;
      if (ea || eb) {
        if (ea && eb && ea.message === eb.message) totals.refusedBoth++;
        else { totals.refusedOne++; examples.push({ name, now, d, method, sql: ea && ea.message, memory: eb && eb.message }); }
        if (ea) throw ea;
        return a;
      }
      const c = await sqlTotal[d][method](...args);
      if (method === 'count' ? b === c : sameDocs(b, c)) totals.totalEqual++;
      else { totals.totalDifferent++; examples.push({ name, now, d, method, kind: 'sql-total-vs-memory' }); }
      if (method === 'count' ? a === b : sameDocs(a, b)) totals.equal++;
      else if (method !== 'count' && sortedSame(a, b)) {
        totals.orderOnly++; tieReadsHere++;
        const tie = d + ' ' + method + ' sort ' + JSON.stringify(args[1] && args[1].sort) + (args[1] && args[1].limit ? ' limit ' + args[1].limit : '');
        tieReads.set(tie, (tieReads.get(tie) || 0) + 1);
        if (mongoDb) {
          let cursor = mongoDb.collection(d).find(toMongo(args[0], { v1: !!(args[1] && args[1].v1) }) || {}).sort(args[1].sort);
          if (args[1].skip) cursor = cursor.skip(args[1].skip);
          if (args[1].limit) cursor = cursor.limit(args[1].limit);
          const key = doc => (typeof doc._id === 'string' ? 's' : 'o') + String(doc._id);
          const m = (await cursor.toArray()).map(key);
          const today = util.isDeepStrictEqual(m, a.map(key)), total = util.isDeepStrictEqual(m, b.map(key));
          totals[today && total ? 'mongoBoth' : today ? 'mongoMatchesToday' : total ? 'mongoMatchesTotal' : 'mongoNeither']++;
          if (!today && !total) mongoNeither.set(tie, (mongoNeither.get(tie) || 0) + 1);
        }
      } else { totals.different++; if (examples.length < 20) examples.push({ name, now, d, method, kind: 'different', n: [a.length, b.length] }); }
      if (method === 'findFiltered') {
        const [ast, opts = {}] = args;
        let filter;
        try { filter = toMongo(ast, { v1: !!opts.v1 }); } catch { filter = null; }
        if (filter) {
          const plain = documents[d].map(doc => JSON.parse(JSON.stringify({ ...doc, _id: typeof doc._id === 'string' ? doc._id : doc._id.toHexString() })));
          let cursor = new mingo.Query(filter).find(plain);
          const ids = docs => docs.map(doc => typeof doc._id === 'string' ? doc._id : doc._id.toHexString()).sort();
          const all = cursor.all();
          const sqlAll = opts.limit || opts.skip ? null : a;
          if (sqlAll) {
            totals.mingoMembership++;
            if (!util.isDeepStrictEqual(ids(all), ids(sqlAll))) { totals.mingoMembershipDiffer++; if (examples.length < 30) examples.push({ name, now, d, kind: 'mingo-membership', filter: JSON.stringify(filter).slice(0, 200), mingo: all.length, sql: sqlAll.length }); }
          }
          if (opts.sort) {
            cursor = new mingo.Query(filter).find(plain).sort(opts.sort);
            if (opts.skip) cursor = cursor.skip(opts.skip);
            if (opts.limit) cursor = cursor.limit(opts.limit);
            const ordered = cursor.all().map(doc => doc._id);
            totals.mingoOrder++;
            if (!util.isDeepStrictEqual(ordered, a.map(doc => typeof doc._id === 'string' ? doc._id : doc._id.toHexString()))) totals.mingoOrderDiffer++;
          }
        }
      }
      return a;
    }]));
    const stores = Object.fromEntries(evaluator.domains.map(d => [d, dual(d)]));
    const language = req('lib/language')(); language.set('en');
    const view = arm => viewsFactory(env, evaluator.createContext({ env, language, dbstats: async () => ({ dataSize: 1, indexSize: 1 }), storage: d => arm[d] }));
    const materialise = (v, viewName) => new Promise((resolve, reject) => v.materialise(viewName, { now, dbstats: { dataSize: 1, indexSize: 1 } }, (e, s) => e ? reject(e) : resolve(s)));
    clock.pin(now);
    await scope.withTenant(TENANT, async () => {
      for (const viewName of ['properties', 'alarms']) {
        const d = await materialise(view(stores), viewName); // every read through all three arms
        const m = await materialise(view(memory), viewName);
        totals.instants++;
        const data = x => Object.fromEntries(Object.keys(x.ddata).filter(k => typeof x.ddata[k] !== 'function').map(k => [k, x.ddata[k]]));
        if (util.isDeepStrictEqual(data(d), data(m))) totals.workingSetEqual++;
        else {
          // The first path where the two working sets differ (structure only, no values).
          const first = (x, y, at) => {
            if (util.isDeepStrictEqual(x, y)) return null;
            if (!x || !y || typeof x !== 'object' || typeof y !== 'object') return at + ' (' + typeof x + '/' + typeof y + ')';
            const kx = Object.keys(x), ky = Object.keys(y);
            if (!util.isDeepStrictEqual(kx, ky)) return at + ' keys ' + JSON.stringify(kx.filter(k => !ky.includes(k))) + '/' + JSON.stringify(ky.filter(k => !kx.includes(k))) + (kx.length === ky.length ? ' order' : '');
            for (const k of kx) { const r = first(x[k], y[k], at + '.' + k); if (r) return r; }
            return at + ' (prototype or undefined members)';
          };
          const at = first(data(d), data(m), '$');
          const k = 'working set ' + viewName + ' ' + at.replace(/\.\d+/g, '.[]') + (tieReadsHere ? '' : ' WITHOUT A TIE READ');
          changes.set(k, (changes.get(k) || 0) + 1);
        }
        const out = s => JSON.stringify((({ emitted, requested, properties }) => ({ emitted, requested, properties }))(viewsFactory(env, evaluator.createContext({ env, language, dbstats: async () => ({}), storage: x => memory[x] })).evaluateCycle(s)));
        const outObj = x => JSON.parse(out(x));
        if (out(d) === out(m)) totals.outputEqual++;
        else {
          const firstOut = (x, y, at) => {
            if (util.isDeepStrictEqual(x, y)) return null;
            if (!x || !y || typeof x !== 'object' || typeof y !== 'object') return at;
            for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) { const r = firstOut(x[k], y[k], at + '.' + (/^\d+$/.test(k) ? '[]' : k)); if (r) return r; }
            return at + ' (key order)';
          };
          const k = 'output ' + viewName + ' ' + name.split(' #')[0] + ' ' + firstOut(outObj(d), outObj(m), '$') + (tieReadsHere ? '' : ' WITHOUT A TIE READ');
          changes.set(k, (changes.get(k) || 0) + 1);
          if (!tieReadsHere) totals.outputChangedWithoutTie++;
        }
        const t = await new Promise((resolve, reject) => view(sqlTotal).materialise(viewName, { now, dbstats: { dataSize: 1, indexSize: 1 } }, (e, x) => e ? reject(e) : resolve(x)));
        if (out(t) === out(m) && util.isDeepStrictEqual(data(t), data(m))) totals.totalPathsOutputEqual++;
        else examples.push({ name, now, viewName, kind: 'sql-total-vs-memory working set or output' });
      }
    });
  }
  const envOf = extra => environment({ settings: { enable: PLUGINS, units: 'mg/dl' }, ...(extra || {}) });
  const started = process.hrtime.bigint();
  // 1. views-equality synthetic scenarios, at their instant and later ones
  const now0 = Date.UTC(2026, 10, 6, 12);
  for (const [name, make] of Object.entries(SCENARIOS)) {
    for (const offset of [0, 30000, 5 * MIN, HOUR]) await instant('scenario:' + name, withIds(make(now0), name), envOf(), now0 + offset);
  }
  await instant('twins-and-ties', twinsAndTies(now0), envOf(), now0);
  await instant('twins-and-ties', twinsAndTies(now0), envOf(), now0 + 7 * MIN);
  say('PART scenarios ' + JSON.stringify(totals));
  // 2. views-replay timelines, every 2 hours across each
  for (const [name, make] of Object.entries(TIMELINES)) {
    const t = make();
    const env = envOf(t.env && Object.keys(t.env).length ? t.env : undefined);
    const records = withIds(t.records, name);
    for (let at = t.start + 2 * HOUR; at <= t.end; at += 2 * HOUR) await instant('timeline:' + name, records, env, at);
  }
  say('PART timelines ' + JSON.stringify(totals));
  // 3. corpus sets, read in place, by position
  const dir = process.env.VIEWS_CORPUS_DIR;
  if (dir) {
    const names = corpusNames(dir);
    for (let i = 0; i < names.length; i++) {
      const records = withIds(loadCorpus(dir, names[i], now0), 'corpus' + i);
      for (const offset of [0, 10 * MIN, 2 * HOUR]) await instant('corpus #' + (i + 1), records, envOf(), now0 + offset);
    }
    say('PART corpus sets=' + names.length + ' ' + JSON.stringify(totals));
  }
  clock.uninstall();
  await pool.end();
  if (mongoClient) { await mongoDb.dropDatabase(); await mongoClient.close(); }
  say('READS_BY_METHOD ' + JSON.stringify(byMethod));
  for (const [k, n] of tieReads) say('TIE_READ ' + n + ' ' + k);
  for (const [k, n] of mongoNeither) say('MONGO_NEITHER ' + n + ' ' + k);
  for (const [k, n] of changes) say('CHANGE ' + n + ' ' + k);
  for (const e of examples.slice(0, 30)) say('EXAMPLE ' + JSON.stringify(e));
  // Pass: the two total-order paths agree everywhere; today's SQL and the
  // total order differ only in the order of tied rows, and every working-set
  // or output change happens at an instant with a tie read.
  const pass = totals.different === 0 && totals.refusedOne === 0 && totals.totalDifferent === 0 &&
    totals.totalPathsOutputEqual === totals.instants && totals.outputChangedWithoutTie === 0 && ![...changes.keys()].some(k => k.includes('WITHOUT'));
  say((pass ? 'PASS' : 'FAIL') + ' A_READ_DIFFERENTIAL ' + JSON.stringify(totals) + ' elapsed_s=' + (Number(process.hrtime.bigint() - started) / 1e9).toFixed(1) +
    ' load=' + require('node:os').loadavg().map(x => x.toFixed(2)).join(' '));
  process.exitCode = pass ? 0 : 1;
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exit(1); });
