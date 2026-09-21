'use strict';
/*
 * bf71-date-window-presence-check.js  —  BF-71
 *
 * `enforceDateFilter()` applies its default date window only when
 * `!dateValue && !query.dateString`. The second test is a bare PRESENCE check
 * on a different field, so ANY `dateString` key drops the window -- `$ne`,
 * `$exists`, `$gte`, `$regex` alike. The operator is irrelevant, which is why
 * no operator allowlist can reach this and why `bf/operators` did not.
 *
 * THIS GATE FAILS TODAY, BY DESIGN. It goes green when the guard tests
 * `dateString` the way it tests the configured date field -- for a date
 * CONSTRAINT rather than for a key's existence.
 *
 * WHAT THIS GATE DELIBERATELY DOES NOT ASSERT. BF-71 is NOT a privilege
 * boundary, and the register says so at its own severity. Reproduced
 * 2026-09-21 with the control in the same run: the allowlisted, documented
 * `find[date][$gte]=0` reaches the identical record set on the identical
 * authorisation, and every form is 401 under AUTH_DEFAULT_ROLES=denied. So a
 * reader must not take this gate's red as "an unauthenticated hole is open".
 * It measures a correctness defect: two spellings of one intent, one of which
 * silently removes the bound. The reason that matters is BF-72, where the size
 * of the scan a single anonymous request can cause is the whole finding.
 *
 * NON-VACUITY. The gate reads the shipping source out of the object database
 * and asserts THREE things that can each come out either way: the guard is
 * present at all (if the function were gone this would fail loudly rather than
 * pass by absence), the configured-date-field test is a value test, and the
 * `dateString` test is a presence test. The middle finding is the control: it
 * is the shape the third one is supposed to have, measured in the same file by
 * the same method, so "the matcher cannot see anything" is distinguishable
 * from "the defect is present".
 *
 * READS ONLY. `git show` into memory; no working tree is touched, no database
 * is needed. Compare tools/queue/gates/timeago-future-reading.js.
 */

const { show, git, report } = require('./_gate');

const REF = process.env.BF71_REF || 'origin/dev';
const FILE = 'lib/server/query.js';

const src = show(REF, FILE);
const findings = [];

if (src === null) {
  console.log(`gate: bf71-date-window-presence-check`);
  console.log(`  BAD  cannot read ${FILE} at ${REF} -- nothing measured`);
  process.exit(1);
}

const fn = (src.match(/function enforceDateFilter[\s\S]*?\n}/) || [null])[0];

findings.push({
  ok: fn !== null,
  text: fn
    ? `enforceDateFilter() found in ${FILE} at ${git(['rev-parse', '--short', REF])}`
    : `enforceDateFilter() NOT found in ${FILE} -- the gate has no subject and must not pass`,
});

if (fn) {
  const guard = (fn.match(/if \(\s*!dateValue[^)]*\)/) || [null])[0];

  // CONTROL. The configured date field is consulted by VALUE -- `dateValue` is
  // `query[opts.dateField]` and the guard tests that value. This finding is the
  // shape the next one should have; it exists so a red on the next one cannot
  // be blamed on the matcher.
  findings.push({
    ok: guard !== null && /!dateValue/.test(guard),
    text: guard
      ? `CONTROL: the configured date field is tested through its value (${guard.replace(/\s+/g, ' ')})`
      : 'CONTROL: no `!dateValue` guard found -- matcher cannot see the guard at all',
  });

  // THE DEFECT. `query.dateString` is tested for existence, not for a bound.
  const presenceCheck = guard !== null && /!query\.dateString/.test(guard);
  findings.push({
    ok: !presenceCheck,
    text: presenceCheck
      ? 'BF-71 PRESENT: `!query.dateString` is a presence check, so any dateString key drops the '
        + 'default window (measured: $ne, $exists, $gte, $regex each do). NOT a privilege boundary '
        + '-- see the register before reading this as an open hole'
      : 'the dateString arm no longer drops the window on the mere presence of the key',
  });
}

report('bf71-date-window-presence-check', findings);
