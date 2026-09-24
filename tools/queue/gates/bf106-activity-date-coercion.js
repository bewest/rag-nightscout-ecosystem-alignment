'use strict';
/*
 * bf106-activity-date-coercion.js  — BF-106
 *
 * On 15.0.8 every v1 collection without its own `walker` inherited query.js's
 * default one, `{ date: parseInt, sgv: parseInt }`, so `find[date][$gte]=<ms>`
 * on /api/v1/activity compared a number with a number. The schema-driven
 * coercion (BF-03's fix, PR #8737) names a `collection` on each storage and,
 * when one is named, replaces that default with `{}`. `activity`'s schema entry
 * is empty, so its `date` and `sgv` filters now stay strings, and a string bound
 * never matches a numeric field: the filter answers 200 with no records.
 *
 * HOW IT MEASURES. For each ref, `git archive` the ref's lib/ into a scratch
 * directory, borrow node_modules by symlink, load the ref's own activity
 * storage module for its queryOpts, build the query a v1 request produces, and
 * look at the TYPE of the bound. Nothing is guessed from source text.
 *
 *   control  origin/master (15.0.8): the bound must be a number. If it is not,
 *            the harness is broken and the result for the ref means nothing.
 *   ref      origin/dev: the bound must be a number. A string is BF-106.
 *
 * Reads only. No worktree is written to; node_modules is never modified.
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { CRM, report } = require('./_gate');

const REF = process.argv.includes('--ref')
  ? process.argv[process.argv.indexOf('--ref') + 1] : 'origin/dev';
const CONTROL = 'origin/master';
const findings = [];

function boundTypes (ref) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-bf106-'));
  try {
    execFileSync('bash', ['-c',
      `git -C ${JSON.stringify(CRM)} archive ${ref} lib | tar -x -C ${JSON.stringify(dir)}`]);
    fs.symlinkSync(path.join(CRM, 'node_modules'), path.join(dir, 'node_modules'));
    const script = `
      const find_options = require('./lib/server/query');
      const storage = require('./lib/server/activity');
      const q = find_options({ find: { date: { $gte: '1000' }, sgv: { $gte: '100' } }, count: 10 },
                             Object.assign({}, storage.queryOpts));
      process.stdout.write(JSON.stringify({
        date: typeof (q.date && q.date.$gte), sgv: typeof (q.sgv && q.sgv.$gte) }));`;
    const out = execFileSync(process.execPath, ['-e', script],
                             { cwd: dir, encoding: 'utf8', env: Object.assign({}, process.env, { NODE_ENV: 'test' }) });
    return JSON.parse(out);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

let control;
try { control = boundTypes(CONTROL); } catch (e) {
  findings.push({ ok: false, text: `CONTROL ${CONTROL}: harness failed (${e.message.split('\n')[0]}). NOTHING WAS MEASURED.` });
  report('bf106-activity-date-coercion (BF-106)', findings);
}
findings.push({
  ok: control.date === 'number',
  text: `CONTROL ${CONTROL}: activity find[date][$gte] bound is a ${control.date}, sgv a ${control.sgv} `
      + '(15.0.8 inherits the default walker; if this is not a number the harness is broken)',
});

let got;
try { got = boundTypes(REF); } catch (e) {
  findings.push({ ok: false, text: `${REF}: harness failed (${e.message.split('\n')[0]}). NOT a clean result.` });
  report('bf106-activity-date-coercion (BF-106)', findings);
}
findings.push({
  ok: got.date === 'number',
  text: got.date === 'number'
    ? `${REF}: activity find[date][$gte] bound is a number, as on 15.0.8`
    : `BF-106 PRESENT at ${REF}: activity find[date][$gte] bound is a ${got.date} (sgv: ${got.sgv}), so a `
      + 'numeric-date filter on /api/v1/activity answers 200 with no records; 15.0.8 matched them',
});

report('bf106-activity-date-coercion (BF-106)', findings);
