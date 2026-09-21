'use strict';
/*
 * bf72-regex-operand-bounded.js  —  BF-72
 *
 * API v1 accepts `$regex` on a field BY DESIGN -- the 14-project client census
 * found real clients sending it, and `treatments.notes` is promoted to a
 * regular expression by the walker as a documented search affordance. So the
 * defect is not the operator. The defect is that the caller's PATTERN reaches
 * `mongod` with no anchoring requirement, no length cap and no complexity
 * limit, and `mongod`'s `$regex` backtracks. Measured 2026-09-21 on
 * `dev` 59430336 against mongod 7.0.43, 20 000 seeded entries, one
 * unauthenticated GET each: 22 ms with no regex, 29 ms for a benign anchored
 * prefix, and 60-71 s for three patterns with nested quantifiers.
 *
 * WHY THIS GATE MEASURES THE BOUND AND NOT THE TIMING. Writing the timing
 * measurement into this repository means writing the patterns into this
 * repository, and this repository is PUBLIC while the defect is live on the
 * shipping release. That is the same constraint BF-70 carried. So the
 * reproduction stays outside version control (see the register's BF-72 detail
 * section) and what is gated here is the property whose absence IS the defect:
 * nothing between the query string and the driver constrains the operand of
 * `$regex`. A reader should know that this gate is the cheaper half of the
 * evidence and that the expensive half exists elsewhere -- BFQ-72 carries an
 * explicit `no-gate` saying so, rather than letting this one imply it covers
 * the finding.
 *
 * THIS GATE FAILS TODAY, BY DESIGN. It goes green when some bound on the
 * pattern exists on the v1 read path -- a length cap, a required literal
 * prefix, a rejection of nested quantifiers, or a linear-time engine. It
 * deliberately does NOT prescribe which: the register records that none of the
 * four has been measured and that choosing between them is a decision about
 * the search affordance's contract.
 *
 * NON-VACUITY. Two findings can each come out either way, and the first is the
 * control: `$regex` must be REACHABLE at all (present in the allowlist). If a
 * future change refused the operator outright, the control flips and this
 * gate's subject is gone -- which is a different world, not a silent pass.
 * The second finding is the bound. Proven to flip: with a length bound spliced
 * into an isolated copy of the allowlist module
 * (`tmp/bf72-vacuity-probe` in externals/cgm-remote-monitor-official), this
 * gate goes green and the control stays green. The first draft of the detector
 * did NOT flip under that same ablation -- see the comment at the detector.
 *
 * READS ONLY. `git show` into memory; no working tree, no database.
 */

const { show, git, report } = require('./_gate');

const REF = process.env.BF72_REF || 'origin/dev';
const CANDIDATES = [
  'lib/server/query-operator-allowlist.js',
  'lib/server/query.js',
];

const findings = [];
const sources = {};
for (const f of CANDIDATES) {
  const s = show(REF, f);
  if (s !== null) sources[f] = s;
}

if (Object.keys(sources).length === 0) {
  console.log('gate: bf72-regex-operand-bounded');
  console.log(`  BAD  none of ${CANDIDATES.join(', ')} readable at ${REF} -- nothing measured`);
  process.exit(1);
}

const all = Object.entries(sources).map(([f, s]) => `/* ${f} */\n${s}`).join('\n');

// CONTROL: the operator has to be reachable for the finding to exist.
const reachable = /\$regex/.test(all);
findings.push({
  ok: reachable,
  text: reachable
    ? `CONTROL: $regex is reachable on the v1 read path at ${git(['rev-parse', '--short', REF])} `
      + `(${Object.keys(sources).join(', ')})`
    : 'CONTROL: $regex is not reachable here -- the subject of this gate is absent, which is a '
      + 'change in the world and not a pass. Re-read BF-72 before touching this gate',
});

// THE DEFECT: nothing constrains the operand.
//
// DELIBERATELY NOT POSITIONAL. An earlier draft of this gate looked for a
// bound within 400 characters of a `$regex` occurrence and did not flip when a
// bound was spliced in, because the natural site for one -- inside
// assertFieldPredicate, where the operator is validated -- is well over a
// thousand characters from the accept-set literal. A gate that only recognises
// a fix written in one particular place is a gate that reads a real fix as
// absent. So the detector is line-scoped and name-based instead: a line that
// names a regular expression or pattern AND names a bound on it counts,
// wherever in the module it sits.
const SUBJECT = /(regex|pattern)/i;
const BOUND = /(max|limit|length|complex|quantifier|\bre2\b|timeout)/i;
const boundLine = all.split('\n').find((line) => {
  const code = line.replace(/\/\/.*$/, '');        // a comment is not a bound
  return SUBJECT.test(code) && BOUND.test(code);
});
const bounded = boundLine !== undefined;
findings.push({
  ok: bounded,
  text: bounded
    ? `a bound on the $regex operand is present on the v1 read path: ${boundLine.trim().slice(0, 90)}`
    : 'BF-72 PRESENT: no length, complexity or engine bound on the $regex operand anywhere on the '
      + 'v1 read path. Unauthenticated on the shipped AUTH_DEFAULT_ROLES=readable. This is an '
      + 'AVAILABILITY finding, not exposure -- the collections reached are already readable on '
      + 'that default. Timing evidence is deliberately held outside this repository; see the '
      + "register's BF-72 detail section and BFQ-72's no-gate",
});

report('bf72-regex-operand-bounded', findings);
