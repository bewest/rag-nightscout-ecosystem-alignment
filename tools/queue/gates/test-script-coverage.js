'use strict';
/*
 * test-script-coverage.js  — DOC-TESTSCRIPTS
 *
 * `npm run test:unit` and `npm run test:integration` are brace lists, not
 * globs. GT1 expanded them on origin/dev: 44 files and 89 files out of 159
 * `tests/*.test.js`, leaving 52 matched by NEITHER.
 *
 * This is not tidiness. Four of those 52 are the evidence for the current
 * backfix batch — boluscalc.quickpick (BF-35, high severity, the bolus
 * calculator resolving the wrong quick-pick record so the carbs reaching an
 * insulin calculation come from a record the user did not choose),
 * receiveddata.merge (BF-36), browser-utils.queryparms (BF-37) and dataloader.
 * An agent told "run test:unit" never executes BF-35's test, so a clean
 * 361-passing run on bf/food is not evidence that BF-35's fix works.
 *
 * CI is not blind to this: main.yml runs `test-ci`, which is ./tests/*.test.js,
 * all 159. The gap is in the LOCAL scripts, which is where humans and agents
 * look. So the risk is not that a defect ships — it is that someone reads a
 * green local run as evidence it will not.
 *
 * FAILS while any tests/*.test.js matches neither brace list.
 */

const { execFileSync } = require('child_process');
const { CRM, show, git, report } = require('./_gate');

const REF = 'origin/dev';
const findings = [];

const scripts = JSON.parse(show(REF, 'package.json')).scripts || {};

function braceLists(command) {
  // Pull the ./tests/{...}*.test.js arguments out of a mocha invocation and let
  // bash expand them, which is what npm will do. Reimplementing brace expansion
  // here would mean measuring my own parser rather than the shell's.
  const patterns = [...command.matchAll(/\.\/tests\/\{[^}]*\}[\w.*-]*/g)].map((m) => m[0]);
  if (patterns.length === 0) return [];
  const expanded = execFileSync('bash', ['-c', `echo ${patterns.join(' ')}`],
                                { encoding: 'utf8' }).trim();
  return expanded.split(/\s+/).filter(Boolean);
}

const allTests = git(['ls-tree', '-r', '--name-only', REF, 'tests/'])
  .split('\n')
  .filter((f) => /^tests\/[^/]+\.test\.js$/.test(f));

findings.push({ ok: allTests.length > 0, text: `${REF} has ${allTests.length} tests/*.test.js files` });

const unit = new Set(braceLists(scripts['test:unit'] || '').map((p) => p.replace(/^\.\//, '')));
const integration = new Set(braceLists(scripts['test:integration'] || '').map((p) => p.replace(/^\.\//, '')));

// The brace lists expand to PATTERNS (many end in `*`), so match by regex.
function matches(set, file) {
  for (const pattern of set) {
    const re = new RegExp('^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$');
    if (re.test(file)) return true;
  }
  return false;
}

const uncovered = allTests.filter((f) => !matches(unit, f) && !matches(integration, f));

findings.push({
  ok: true,
  text: `test:unit brace list expands to ${unit.size} pattern(s); `
      + `test:integration to ${integration.size}`,
});

// Name the four that are this batch's evidence explicitly, so a reader sees the
// consequence and not just a count.
const EVIDENCE_FOR_THIS_BATCH = [
  'tests/boluscalc.quickpick.test.js',
  'tests/receiveddata.merge.test.js',
  'tests/browser-utils.queryparms.test.js',
  'tests/dataloader.test.js',
];
for (const file of EVIDENCE_FOR_THIS_BATCH) {
  if (!allTests.includes(file)) continue;   // not yet on dev; it is on a bf/* branch
  findings.push({
    ok: !uncovered.includes(file),
    text: `${file} is reachable from a local test script`,
  });
}

findings.push({
  ok: uncovered.length === 0,
  text: uncovered.length === 0
    ? 'every tests/*.test.js is reachable from test:unit or test:integration'
    : `${uncovered.length} test file(s) match NEITHER local script, so a green local run `
      + `does not mean what a reader takes it to mean: ${uncovered.slice(0, 6).join(', ')}`
      + (uncovered.length > 6 ? `, +${uncovered.length - 6} more` : ''),
});

report('test-script-coverage (DOC-TESTSCRIPTS)', findings);
