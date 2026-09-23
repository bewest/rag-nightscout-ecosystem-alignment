'use strict';
/*
 * timeago-future-reading.js  —  BF-41
 *
 * BF-41 claimed that a CGM reading stamped ahead of the server clock switches
 * off both stale-data alarm paths: `timeago.checkStatus` computes staleness
 * as `sbx.time - lastSGVEntry.mills`, which would be negative for a future
 * reading, so the status would never leave `'current'`.
 *
 * WHAT THIS GATE MEASURES. The arithmetic is right, but `lastSGVEntry` comes
 * from `lib/sandbox.js` `lastEntry`, which skips every entry later than
 * `sbx.time` (`notInTheFuture`, since 556091bf, 2015; in every tag from
 * 0.10.0, including 15.0.8). This gate loads readings into the data the
 * sandbox is built from and lets the shipping `lastEntry` choose the reading,
 * on both paths:
 *
 *   - server: `serverInit(env, ctx)` from `ctx.ddata`, then `checkStatus`
 *     and `checkNotifications` with `enableAlerts` on, recording what the
 *     plugin passes to `requestNotify` (the push alarm);
 *   - browser: `clientInit(ctx, now, { sgvs })`, then `checkStatus`.
 *
 * An earlier version of this gate replaced `sbx.lastSGVEntry` with a stub
 * that returned the future reading. That skipped the one step that prevents
 * the symptom, so it reproduced a state the shipping code does not reach.
 * Measurement and write-up:
 * docs/60-research/remedial/bf41-future-reading-2026-09-23.md.
 *
 * THIS GATE PASSES WHEN THE DEFECT DOES NOT REPRODUCE: a real reading that
 * has gone stale still raises the warn or urgent status and the push alarm
 * when a future-dated reading is also loaded. It fails if a future-dated
 * reading ever silences either path.
 *
 * NON-VACUITY. Three controls (2, 20 and 40 minutes old, no future reading)
 * must come out `current`, `warn` and `urgent` on both paths. Sharper
 * control, run by hand 2026-09-23: with `lastEntry`'s filter replaced by
 * `return true` in a scratch worktree (`--tree`), the future arms go to
 * `current` with no push alarm and this gate fails, while the controls stay
 * green. The record is in queue/gate-controls.yaml.
 *
 * NOT MEASURED HERE: an uploader whose clock runs ahead (the stale warning
 * arrives late by the size of the error once the wall clock passes the
 * readings' timestamps), and "only future readings loaded" (the no-reading
 * branch, which assumes current). Both are characterised in the write-up.
 *
 * READS ONLY. It requires shipping modules by path out of the official
 * checkout (or `--tree <path>`), builds sandboxes in memory, writes nothing,
 * opens no socket and needs no database.
 */

const path = require('path');
const { CRM, git, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const TREE = path.resolve(argValue('--tree', CRM));
const OFFICIAL = TREE === path.resolve(CRM);
const NAME = 'timeago-future-reading (BF-41)';

let head = 'unknown';
try { head = git(['rev-parse', '--short', 'HEAD'], TREE); } catch (e) { /* reported below */ }

const findings = [];

let sandbox, timeagoInit, ddataInit, levels;
try {
  sandbox = require(path.join(TREE, 'lib', 'sandbox.js'));
  timeagoInit = require(path.join(TREE, 'lib', 'plugins', 'timeago.js'));
  ddataInit = require(path.join(TREE, 'lib', 'data', 'ddata.js'));
  levels = require(path.join(TREE, 'lib', 'levels.js'));
} catch (e) {
  report(NAME, [{ ok: false, text: `could not load the sandbox or timeago plugin from ${TREE}: ${e.message}` }]);
}

findings.push({
  ok: true,
  text: OFFICIAL
    ? `shipping lib/sandbox.js and lib/plugins/timeago.js at ${head}`
    : `NOT the official checkout: reading ${TREE} at ${head} (a --tree override; a result here `
      + 'is about that tree and about nothing that ships)',
});

const MIN = 60 * 1000;
const language = { translate: (s) => s };
const settings = {
  alarmTimeagoWarn: true,
  alarmTimeagoWarnMins: 15,
  alarmTimeagoUrgent: true,
  alarmTimeagoUrgentMins: 30,
};

function levelName(level) {
  if (level === levels.URGENT) return 'URGENT';
  if (level === levels.WARN) return 'WARN';
  return String(level);
}

// offsets: minutes relative to the clock; negative = past, positive = future.
function measure(offsets) {
  const timeago = timeagoInit({ language, levels });
  const now = Date.now();
  const sgvs = offsets.map((o) => ({ mills: now + o * MIN, mgdl: 120, type: 'sgv' }));

  // Server path, as the server's plugin tick builds it.
  const requested = [];
  const ctx = {
    language,
    levels,
    ddata: ddataInit(),
    notifications: {
      requestNotify: (n) => requested.push(n),
      requestSnooze: () => {},
      requestClear: () => {},
    },
  };
  ctx.ddata.sgvs = sgvs;
  const env = { settings, extendedSettings: { timeago: { enableAlerts: true } } };
  const ssbx = sandbox().serverInit(env, ctx).withExtendedSettings(timeago);
  const used = ssbx.lastSGVEntry();
  const server = timeago.checkStatus(ssbx);
  timeago.checkNotifications(ssbx);
  const push = requested.filter((n) => n.group === 'Time Ago').map((n) => levelName(n.level));

  // Browser path, as lib/client/index.js builds it (clientInit, wall clock).
  // runtimeEnvironment is set to 'server' after init so the client's
  // hibernation heuristic (a >20 s gap between calls returns 'current' for an
  // unrelated reason) cannot make every arm agree. That would be a vacuity
  // trap, not a result.
  const csbx = sandbox().clientInit({ settings, language, levels, pluginBase: null }, now, { sgvs });
  csbx.runtimeEnvironment = 'server';
  const browser = timeago.checkStatus(csbx);

  return {
    usedOffset: used ? Math.round((used.mills - now) / MIN) : null,
    server,
    push: push.length ? push.join('+') : 'none',
    browser,
  };
}

function describe(offsets) {
  return offsets.map((o) => (o > 0 ? `+${o}` : String(o))).join(', ') + ' min';
}

/* --- controls: the harness must distinguish the branches ----------------- */
const controls = [
  { offsets: [-2], status: 'current', push: 'none', label: 'a 2-minute-old reading is current' },
  { offsets: [-20], status: 'warn', push: 'WARN', label: 'a 20-minute-old reading raises warn' },
  { offsets: [-40], status: 'urgent', push: 'URGENT', label: 'a 40-minute-old reading raises urgent' },
];
for (const c of controls) {
  const got = measure(c.offsets);
  const ok = got.server === c.status && got.browser === c.status && got.push === c.push;
  findings.push({
    ok,
    text: `control: ${c.label} — server '${got.server}', push ${got.push}, browser '${got.browser}'; `
        + `expected '${c.status}', ${c.push}, '${c.status}'`,
  });
}

/* --- the arms: a stale real reading plus one dated ahead of the clock ---- */
/*
 * Two future offsets. Five minutes ahead is ordinary clock skew; two hours
 * ahead is what BF-44's MiniMed time-derivation divergence produces (UTC+2
 * files readings exactly two hours forward). The register's claim is that
 * either silences the alarm for the stale real reading loaded before it.
 */
const arms = [
  { offsets: [-40, 5], status: 'urgent', push: 'URGENT' },
  { offsets: [-40, 120], status: 'urgent', push: 'URGENT' },
  { offsets: [-20, 3], status: 'warn', push: 'WARN' },
  { offsets: [-20, 120], status: 'warn', push: 'WARN' },
];
for (const a of arms) {
  const got = measure(a.offsets);
  const real = a.offsets[0];
  const ok = got.usedOffset === real && got.server === a.status
          && got.browser === a.status && got.push === a.push;
  findings.push({
    ok,
    text: `readings at ${describe(a.offsets)}: lastSGVEntry used ${got.usedOffset} min, server `
        + `'${got.server}', push ${got.push}, browser '${got.browser}' — ` + (ok
          ? 'the future-dated reading is skipped and the stale real reading still alarms'
          : `BF-41's symptom: expected the ${real} min reading to be used and '${a.status}' / ${a.push}`),
  });
}

report(NAME, findings);
