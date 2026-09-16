'use strict';
/*
 * timeago-future-reading.js  —  BF-41
 *
 * A CGM reading stamped ahead of the server clock silently switches off the
 * browser stale-data alarm. `timeago.checkStatus` computes staleness as
 * `sbx.time - lastSGVEntry.mills`, which is NEGATIVE for a future reading, so
 * `isStale(mins)` is false at every threshold and the status never leaves
 * `'current'`. `lib/client/index.js` only raises the alarm on `'warn'` or
 * `'urgent'`, so both alarm paths go quiet.
 *
 * WHY THIS GATE EXISTS RATHER THAN A NOTE. The register filed BF-41 as
 * DERIVED FROM SOURCE and said so: "the arithmetic is not in doubt, but no
 * end-to-end run was made... that run is the fix for this entry's provenance,
 * and it is cheap". Measured across this programme, every register claim that
 * had to be retracted was derived from reading; not one that began with a
 * reproduction has been. This is that run, at the level the defect lives:
 * the shipping plugin, executed.
 *
 * THIS GATE FAILS TODAY, BY DESIGN. It is the residual, expressed as a
 * measurement, exactly like RT-D3's drag-clamp gate and P0-C's console.log
 * gate. It goes green when a reading ahead of the clock stops being treated
 * as fresh.
 *
 * NON-VACUITY. Three controls run through the same harness and must come out
 * the other way: a fresh reading is `'current'`, a 20-minute-old reading is
 * `'warn'`, a 40-minute-old reading is `'urgent'`. If the harness could not
 * tell those apart, the future arm's `'current'` would mean nothing. Ablation
 * recorded in docs/60-research/remedial/e4-queue-register-reconciliation-2026-09-15.md
 * §6: with a one-line future guard patched into an isolated copy of
 * timeago.js, this gate goes green and the three controls stay green.
 *
 * READS ONLY. It requires the shipping plugin by path out of the official
 * checkout and calls one pure-ish function; it writes nothing, opens no
 * socket and needs no database. `--source <path>` points it at a copy, which
 * is how the ablation above is run without touching a worktree (rule 5).
 */

const path = require('path');
const { CRM, git, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const SOURCE = argValue('--source', path.join(CRM, 'lib', 'plugins', 'timeago.js'));

const findings = [];

// Name the ref the shipping source came from, so a green result can never be
// read as a statement about a commit nobody measured.
const OFFICIAL = SOURCE.startsWith(CRM);
let head = 'not the official checkout';
if (OFFICIAL) {
  try { head = git(['rev-parse', '--short', 'HEAD']); } catch (e) { head = 'unknown'; }
}

let timeago;
try {
  // ctx is minimal on purpose: checkStatus touches only settings, time and
  // lastSGVEntry. translate and levels are needed by init(), not by the
  // function under test.
  timeago = require(SOURCE)({
    language: { translate: (s) => s },
    levels: { URGENT: 2, WARN: 1, INFO: 0 },
  });
} catch (e) {
  report('timeago-future-reading (BF-41)', [{
    ok: false, text: `could not load ${SOURCE}: ${e.message}`,
  }]);
}

const NOW = Date.UTC(2026, 8, 15, 12, 0, 0);
const MIN = 60 * 1000;

function status(offsetMinutes) {
  return timeago.checkStatus({
    // 'server' is the branch that never claims hibernation, so the arms differ
    // only in the entry's timestamp. On 'client' a >20s gap between calls
    // returns 'current' for an unrelated reason and every arm would agree —
    // which is a vacuity trap, not a result.
    runtimeEnvironment: 'server',
    time: NOW,
    settings: {
      alarmTimeagoWarn: true,
      alarmTimeagoWarnMins: 15,
      alarmTimeagoUrgent: true,
      alarmTimeagoUrgentMins: 30,
    },
    lastSGVEntry: () => ({ mills: NOW - offsetMinutes * MIN }),
  });
}

findings.push({
  ok: true,
  text: OFFICIAL
    ? `shipping plugin ${path.relative(CRM, SOURCE)} at ${head}`
    : `NOT the shipping plugin — reading ${SOURCE} (an --source override; a result here `
      + 'is about that copy and about nothing that ships)',
});

/* --- controls: the harness must distinguish the branches ----------------- */
const controls = [
  { minutes: 2, expect: 'current', label: 'a 2-minute-old reading is current' },
  { minutes: 20, expect: 'warn', label: 'a 20-minute-old reading raises the warn alarm' },
  { minutes: 40, expect: 'urgent', label: 'a 40-minute-old reading raises the urgent alarm' },
];
for (const c of controls) {
  const got = status(c.minutes);
  findings.push({
    ok: got === c.expect,
    text: `control: ${c.label} — checkStatus returned '${got}', expected '${c.expect}'`,
  });
}

/* --- the arm ------------------------------------------------------------ */
/*
 * Two future offsets, because the two are different failures. A reading five
 * minutes ahead is an ordinary clock skew; a reading two hours ahead is what
 * BF-44's MiniMed time-derivation divergence produces (UTC+2 files readings
 * exactly two hours forward). Both silence the alarm identically today, and
 * the second is the one with a named shipping cause.
 */
for (const ahead of [5, 120]) {
  const got = status(-ahead);
  const ok = got !== 'current';
  findings.push({
    ok,
    text: `a reading ${ahead} minutes AHEAD of the server clock: checkStatus returned `
        + `'${got}' — ` + (ok
          ? 'a future reading is no longer treated as fresh'
          : 'both stale-data alarm paths are silent. The browser alarm (on by default, '
          + 'lib/settings.js:27-30) never fires because the status never leaves current; '
          + 'the push alarm (opt-in) returns early at timeago.js:26 on mills >= sbx.time'),
  });
}

report('timeago-future-reading (BF-41)', findings);
