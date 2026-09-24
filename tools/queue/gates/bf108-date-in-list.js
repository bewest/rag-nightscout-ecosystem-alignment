'use strict';
/*
 * bf108-date-in-list.js  — BF-108
 *
 * xdripswift deletes readings in bulk with
 *   DELETE /api/v1/entries.json?find[type]=sgv&find[date][$in][]=<ms>&…
 * (NightscoutSyncManager.swift, chunks of 50). `enforceDateFilter` in
 * lib/server/query.js walks every operator under the date field and, for a
 * value that `isNaN`, calls `.replace` on it as a string. A list of two or more
 * timestamps is an array, which `isNaN`, and an array has no `.replace`, so the
 * query builder throws and the request answers 500 with nothing deleted. A
 * one-element list coerces to a number and passes, which is why single deletes
 * work.
 *
 * HOW IT MEASURES. `git archive` the ref's lib/ into a scratch directory,
 * borrow node_modules by symlink, and build the entries query with the ref's
 * own query.js and the options entries.js passes.
 *
 *   control  the same filter with a ONE-element list must build. If it does
 *            not, the harness is broken and the result means nothing.
 *   ref      a two-element list must build. A throw is BF-108.
 *
 * Reads only. Default ref origin/dev; pass --ref to measure another.
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { CRM, report } = require('./_gate');

const REF = process.argv.includes('--ref')
  ? process.argv[process.argv.indexOf('--ref') + 1] : 'origin/dev';
const findings = [];

function build (ref, values) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-bf108-'));
  try {
    execFileSync('bash', ['-c',
      `git -C ${JSON.stringify(CRM)} archive ${ref} lib | tar -x -C ${JSON.stringify(dir)}`]);
    fs.symlinkSync(path.join(CRM, 'node_modules'), path.join(dir, 'node_modules'));
    const script = `
      const find_options = require('./lib/server/query');
      try {
        find_options({ find: { type: 'sgv', date: { $in: ${JSON.stringify(values)} } } },
                     { collection: 'entries', useEpoch: true });
        process.stdout.write('built');
      } catch (e) { process.stdout.write('threw: ' + e.message); }`;
    return execFileSync(process.execPath, ['-e', script],
                        { cwd: dir, encoding: 'utf8', env: Object.assign({}, process.env, { NODE_ENV: 'test' }) });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

let one, two;
try {
  one = build(REF, ['1758600000000']);
  two = build(REF, ['1758600000000', '1758600300000']);
} catch (e) {
  findings.push({ ok: false, text: `${REF}: harness failed (${e.message.split('\n')[0]}). NOTHING WAS MEASURED.` });
  report('bf108-date-in-list (BF-108)', findings);
}
findings.push({ ok: one === 'built',
  text: `CONTROL ${REF}: find[date][$in] with one timestamp -> ${one} (must build, or the harness is broken)` });
findings.push({ ok: two === 'built',
  text: two === 'built'
    ? `${REF}: find[date][$in] with two timestamps builds`
    : `BF-108 PRESENT at ${REF}: find[date][$in] with two timestamps -> ${two}; the request answers 500 and a bulk delete removes nothing` });
report('bf108-date-in-list (BF-108)', findings);
