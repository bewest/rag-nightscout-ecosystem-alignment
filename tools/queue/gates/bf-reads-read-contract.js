'use strict';
/*
 * bf-reads-read-contract.js — P0-E (bf/reads)
 *
 * WHY THIS EXISTS
 *
 * P0-E's only content gate used to be
 *
 *     git log --format=%H bf/reads | grep -q .
 *
 * which asserts that the branch has at least one commit. The E3 audit ran it
 * against origin/dev, origin/master and bf/alarms and it passed for all three:
 * it measured nothing about the six read-path fixes. Its behavioural gate was
 * `npm run test:unit`, filed `integration` and therefore OFF by default, so the
 * item reported 3/3 PASS while nothing had looked at the code.
 *
 * WHY NOT JUST RUN THE BRANCH'S OWN TESTS
 *
 * We do — P0-E now also declares the five test files the branch adds. But all
 * five need MongoDB (measured: with the mongo URL pointed at a dead port,
 * api.count-parameter goes 13 passing -> 0 passing / 1 failing), so they are
 * `integration` and skipped by default. This gate is the DATABASE-FREE half:
 * it drives the four pure modules the fixes live in, directly, so a default
 * `make queue-status` measures the branch instead of reporting UNMEASURED.
 *
 * THE CONTROL IS BUILT IN
 *
 *   node tools/queue/gates/bf-reads-read-contract.js --rev origin/dev
 *
 * runs the identical assertions against a rev materialised from the object
 * database into a throwaway directory. Against origin/dev every one of them
 * must FAIL. A run of this gate that passes at origin/dev is a vacuous gate,
 * and `tools/queue/gates/vacuity-controls.py` runs exactly that command as
 * P0-E's declared control.
 *
 * Rule 0: this never writes into a shipping checkout or a worktree. The
 * materialised tree goes to a mkdtemp directory and is removed on exit.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { REPO_ROOT, CRM, report } = require('./_gate');

const argv = process.argv.slice(2);
function opt (name, fallback) {
  const i = argv.indexOf(name);
  return i === -1 ? fallback : argv[i + 1];
}

const worktree = path.resolve(REPO_ROOT, opt('--worktree', 'externals/work/crm-bf-reads'));
const rev = opt('--rev', null);

const findings = [];
let root = worktree;
let scratch = null;

if (rev) {
  // Materialise `lib/` from the rev, and borrow the reference worktree's
  // node_modules so that `uuid` and friends resolve. Nothing is written into
  // any checkout.
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-control-'));
  const tar = execFileSync('git', ['-C', CRM, 'archive', rev, 'lib'],
                           { maxBuffer: 512 * 1024 * 1024 });
  const tarPath = path.join(scratch, 'lib.tar');
  fs.writeFileSync(tarPath, tar);
  execFileSync('tar', ['-xf', tarPath, '-C', scratch]);
  fs.symlinkSync(path.join(worktree, 'node_modules'), path.join(scratch, 'node_modules'));
  root = scratch;
  findings.push({ ok: true, text: `CONTROL MODE: assertions run against ${rev}, materialised to a temporary tree` });
}

function cleanup () {
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
process.on('exit', cleanup);

function load (relative) {
  // A module that is absent at this rev is a MEASUREMENT, not a crash: BF-13's
  // fix is a new file, so "it is not there" is exactly what the control should
  // report.
  try {
    return { mod: require(path.join(root, relative)) };
  } catch (error) {
    return { error: `${relative}: ${error.code === 'MODULE_NOT_FOUND' ? 'not present at this rev' : error.message}` };
  }
}

function check (label, fn) {
  try {
    const detail = fn();
    findings.push({ ok: true, text: `${label}${detail ? ' — ' + detail : ''}` });
  } catch (error) {
    findings.push({ ok: false, text: `${label} — ${error.message}` });
  }
}

function assert (condition, message) {
  if (!condition) throw new Error(message);
}

// ---------------------------------------------------------------- BF-13/BF-33
// `?count=` and `?limit=`. MongoDB defines `.limit(0)` as NO limit, so every
// spelling that `parseInt` quietly turns into 0 or some other number returned
// the whole collection instead of the requested slice.
const count = load('lib/server/count.js');
if (count.error) {
  findings.push({ ok: false, text: `BF-13: the ?count= validator module is unavailable — ${count.error}` });
} else {
  check('BF-13: parseCount refuses every spelling that parseInt would guess at', () => {
    const rejected = ['0', '0x10', '2.5', '-3', '1e2', 'abc', ' ', '00x1', '9007199254740993'];
    const wrong = rejected.filter((v) => count.mod.parseCount(v) !== null);
    assert(wrong.length === 0, `these were accepted: ${JSON.stringify(wrong)}`);
    return `${rejected.length} rejected`;
  });
  check('BF-13: parseCount accepts a whole number of documents', () => {
    assert(count.mod.parseCount('100') === 100, "parseCount('100') !== 100");
    assert(count.mod.parseCount(' 7 ') === 7, "parseCount(' 7 ') !== 7");
    assert(count.mod.parseCount(25) === 25, 'parseCount(25) !== 25');
    return "'100' -> 100";
  });
  check('BF-13: hasCount separates "no count given" from "a bad count given"', () => {
    assert(count.mod.hasCount(undefined) === false, 'undefined counted as supplied');
    assert(count.mod.hasCount('') === false, 'empty string counted as supplied');
    assert(count.mod.hasCount(null) === false, 'null counted as supplied');
    assert(count.mod.hasCount('0') === true, "'0' not counted as supplied — it must reach the 400");
    return 'absent/empty/null are not errors; "0" is';
  });
  check('BF-13: applyCount bounds the cursor only when a count was given', () => {
    let limited = null;
    const cursor = { limit (n) { limited = n; return `limited:${n}`; } };
    assert(count.mod.applyCount(cursor, {}) === cursor, 'an absent count still called .limit()');
    assert(limited === null, 'an absent count still called .limit()');
    assert(count.mod.applyCount(cursor, { count: '0' }) === cursor, '.limit(0) reached the driver — that is NO LIMIT');
    assert(limited === null, '.limit(0) reached the driver — that is NO LIMIT');
    assert(count.mod.applyCount(cursor, { count: '5' }) === 'limited:5', 'a good count did not bound the cursor');
    return 'count=0 never reaches .limit()';
  });
}

// ------------------------------------------------------------------- BF-15
// v3 `?fields=app.version` answered `{}` with HTTP 200: the projector deleted
// every key whose exact name was not requested, and `app` never is.
const projector = load('lib/api3/shared/fieldsProjector.js');
if (projector.error) {
  findings.push({ ok: false, text: `BF-15: fieldsProjector is unavailable — ${projector.error}` });
} else {
  check('BF-15: a dotted ?fields= keeps the nested value instead of emptying the document', () => {
    const doc = { srvModified: 1, app: { version: '15.0.9', secret: 'x' }, other: 2 };
    new projector.mod('srvModified,app.version').applyProjection(doc);
    assert(doc.app && doc.app.version === '15.0.9', `app.version was dropped: ${JSON.stringify(doc)}`);
    assert(!('secret' in (doc.app || {})), `an unrequested sibling survived: ${JSON.stringify(doc)}`);
    assert(!('other' in doc), `an unrequested key survived: ${JSON.stringify(doc)}`);
    return JSON.stringify(doc);
  });
  check('BF-15: naming a parent still keeps the whole subtree', () => {
    const doc = { app: { version: '1', build: '2' }, other: 3 };
    new projector.mod('app').applyProjection(doc);
    assert(doc.app && doc.app.version === '1' && doc.app.build === '2',
      `naming the parent pruned its children: ${JSON.stringify(doc)}`);
    return JSON.stringify(doc);
  });
}

// ------------------------------------------------------------------- BF-14
// v3 paging lost and repeated documents whenever the whole sort chain tied.
const input = load('lib/api3/generic/search/input.js');
if (input.error) {
  findings.push({ ok: false, text: `BF-14: the v3 search input parser is unavailable — ${input.error}` });
} else {
  check('BF-14: the v3 sort chain ends in _id, so the order is total', () => {
    for (const query of [{ sort: 'date' }, {}, { sort$desc: 'date' }]) {
      const sort = input.mod.parseSort({ query }, null);
      assert(sort && Object.prototype.hasOwnProperty.call(sort, '_id'),
        `no _id tiebreak for ${JSON.stringify(query)}: ${JSON.stringify(sort)}`);
      const keys = Object.keys(sort);
      assert(keys[keys.length - 1] === '_id', `_id is not last for ${JSON.stringify(query)}`);
      const directions = new Set(Object.values(sort));
      assert(directions.size === 1, `_id sorts against the chain for ${JSON.stringify(query)}: ${JSON.stringify(sort)}`);
    }
    return 'ascending, descending and default all carry _id last';
  });
}

// --------------------------------------------------------------- BF-01/BF-05
// count/:storage/where counted nothing, because it built its filter from the
// defaults instead of the collection's own query_for — and printed that filter,
// with its values, to stdout on every request.
const aggregate = load('lib/server/aggregate.js');
if (aggregate.error) {
  findings.push({ ok: false, text: `BF-01: the aggregate module is unavailable — ${aggregate.error}` });
} else {
  check('BF-01/BF-05: counting uses the collection\'s own query_for and prints nothing', () => {
    let queryForCalls = 0;
    let printed = 0;
    const api = function api () {
      return { aggregate: () => ({ toArray: async () => [{ count: 7 }] }) };
    };
    api.query_for = function queryFor () { queryForCalls += 1; return { fromQueryFor: true }; };

    const real = console.log;
    console.log = function capture () { printed += 1; };
    let result = null;
    let error = null;
    try {
      const run = aggregate.mod({ pipeline: [] }, api);
      run({}, (err, res) => { error = err; result = res; });
    } finally {
      console.log = real;
    }
    assert(queryForCalls === 1, `query_for was called ${queryForCalls} times; the count path still builds its own filter`);
    assert(printed === 0, `the count path printed ${printed} line(s) to stdout`);
    assert(error === null || error === undefined, `aggregate errored: ${error && error.message}`);
    void result;
    return 'query_for called once, zero lines printed';
  });
}

report('bf-reads-read-contract (P0-E)' + (rev ? ` @ ${rev}` : ''), findings);
