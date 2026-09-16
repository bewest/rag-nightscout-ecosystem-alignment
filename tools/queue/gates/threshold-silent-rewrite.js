'use strict';
/*
 * threshold-silent-rewrite.js  —  BF-67
 *
 * `lib/settings.js` `verifyThresholds()` enforces
 * `bgLow < bgTargetBottom < bgTargetTop < bgHigh`. It does not REFUSE a
 * violation — it rewrites the offending value to its neighbour ±1 and calls
 * `console.warn` twice. Nothing in `lib/client/` or `views/` reports the
 * rewrite, so the person sees the corrected number as though they had chosen
 * it.
 *
 * THE REACHABLE CASE IS A UNIT MIX-UP, which is the commonest configuration
 * error there is. An operator who thinks in mmol/L and sets `BG_HIGH=14` is
 * asking for an urgent high at 14 mmol/L. With `UNITS` left at the mg/dL
 * default the mmol conversion at `settings.js:291` does not run, 14 is below
 * `bgTargetTop`, and it is stored as 181 mg/dL. They believe they have set a
 * high alarm and they have set a different one.
 *
 * WHAT THIS GATE ASSERTS: a threshold an operator set is not silently
 * rewritten. It FAILS TODAY, and that is the point — it is BF-67 expressed as
 * a measurement rather than a paragraph. The register filed BF-67 as read on
 * master and dev and NOT reproduced; this gate is the reproduction, and it
 * costs nothing (no database, no network, one `require`).
 *
 * THE GATE DOES NOT PRESCRIBE THE FIX, and neither does the register: whether
 * to refuse the input, to correct it and announce it, or to unit-check it is
 * a maintainer decision with a safety dimension. This register has already
 * shipped two prescribed fixes that were wrong when somebody ran them. The
 * gate goes green under any of the three, because all three stop the value
 * being changed behind the operator's back.
 *
 * NON-VACUITY. Three controls must come out the other way through the same
 * harness: the shipped defaults survive untouched; `UNITS=mmol` with
 * `BG_HIGH=14` converts to 252 and is NOT rewritten (so the gate is not just
 * flagging any small number); and an explicit, internally consistent mg/dL
 * set survives untouched (so it is not flagging any explicit setting). If the
 * harness could not tell those apart, the failing arm would mean nothing.
 *
 * READS ONLY. `--source <path>` points it at a copy, for ablation.
 */

const path = require('path');
const { CRM, git, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const SOURCE = argValue('--source', path.join(CRM, 'lib', 'settings.js'));
const OFFICIAL = SOURCE.startsWith(CRM);

const findings = [];
let head = 'not the official checkout';
if (OFFICIAL) {
  try { head = git(['rev-parse', '--short', 'HEAD']); } catch (e) { head = 'unknown'; }
}
findings.push({
  ok: true,
  text: OFFICIAL
    ? `shipping module ${path.relative(CRM, SOURCE)} at ${head}`
    : `NOT the shipping module — reading ${SOURCE} (an --source override)`,
});

/*
 * Drive the real settings layer the way the server does: build it, then hand
 * `eachSettingAsEnv` an accessor over an environment. `console.warn` is
 * captured rather than silenced, because WHAT THE OPERATOR IS TOLD is the
 * subject of this entry — the defect is not the rewrite, it is that the only
 * evidence of it is on stdout, where a self-hoster on a hosted platform may
 * never look.
 */
function applyEnv(env) {
  delete require.cache[require.resolve(SOURCE)];
  const settings = require(SOURCE)();
  const before = Object.assign({}, settings.thresholds);
  const warnings = [];
  const realWarn = console.warn;
  const realInfo = console.info;
  console.warn = (...a) => warnings.push(a.join(' '));
  console.info = () => {};
  try {
    settings.eachSettingAsEnv((name) => env[name]);
  } finally {
    console.warn = realWarn;
    console.info = realInfo;
  }
  return { before, after: settings.thresholds, warnings, units: settings.units };
}

function describe(result, keys) {
  return keys.map((k) => `${k}=${result.after[k]}`).join(' ');
}

const KEYS = ['bgLow', 'bgTargetBottom', 'bgTargetTop', 'bgHigh'];

/* --- controls ----------------------------------------------------------- */
const defaults = applyEnv({});
findings.push({
  ok: defaults.warnings.length === 0 && defaults.after.bgHigh === 260,
  text: `control: shipped defaults are not rewritten — ${describe(defaults, KEYS)}, `
      + `${defaults.warnings.length} console.warn lines`,
});

const mmol = applyEnv({ UNITS: 'mmol', BG_HIGH: '14', BG_TARGET_TOP: '10',
                        BG_TARGET_BOTTOM: '4.5', BG_LOW: '3.9' });
findings.push({
  ok: mmol.warnings.length === 0 && mmol.after.bgHigh === 252,
  text: `control: UNITS=mmol with BG_HIGH=14 converts and is NOT rewritten — `
      + `${describe(mmol, KEYS)}, ${mmol.warnings.length} console.warn lines`,
});

const consistent = applyEnv({ BG_HIGH: '200', BG_TARGET_TOP: '160',
                             BG_TARGET_BOTTOM: '80', BG_LOW: '65' });
findings.push({
  ok: consistent.warnings.length === 0 && consistent.after.bgHigh === 200,
  text: `control: an internally consistent mg/dL set survives — ${describe(consistent, KEYS)}, `
      + `${consistent.warnings.length} console.warn lines`,
});

// Control AND correction: the guard is one-sided. A BG_LOW far below the band
// is not rewritten at all, which refutes BF-67's own low-side sentence.
const farLow = applyEnv({ BG_LOW: '3.9' });
findings.push({
  ok: farLow.after.bgLow === 3.9 && farLow.warnings.length === 0,
  text: `control: BG_LOW=3.9 against the mg/dL defaults is stored as ${farLow.after.bgLow} `
      + `with ${farLow.warnings.length} warn lines — the guard is one-sided and does NOT `
      + "rewrite it, refuting BF-67's \"a BG_LOW of 3.9 becomes 79\"",
});

/* --- the arms ----------------------------------------------------------- */
/*
 * Two arms, top and bottom, because they are two different alarms.
 *
 * CORRECTION TO THE REGISTER, MEASURED HERE. BF-67's detail says "The same
 * applies at the bottom: a `BG_LOW` of `3.9` becomes `bgTargetBottom - 1 =
 * 79`." IT DOES NOT. The low check is `bgLow >= bgTargetBottom`, so a value
 * FAR BELOW the band passes through untouched — `BG_LOW=3.9` is stored as
 * 3.9, kept below as a control. The low-side rewrite is real but reachable
 * from the other direction: an operator who sets `BG_LOW=90` meaning "warn me
 * below 90 mg/dL", against the shipped `bgTargetBottom` of 80, silently gets
 * 79. That is the arm.
 *
 * The consequence of the refuted half is worse, not better, and belongs to a
 * different entry: a `BG_LOW` of 3.9 mg/dL is a low alarm that can never fire,
 * stored without a warning of any kind. Neither this gate nor the register
 * currently owns that; it is called out in the reconciliation document.
 */
const arms = [
  { label: 'BG_HIGH=14 with UNITS left at the mg/dL default (the mmol mix-up)',
    env: { BG_HIGH: '14' }, key: 'bgHigh', asked: 14 },
  { label: 'BG_LOW=90 with the shipped bgTargetBottom of 80 ("warn me below 90")',
    env: { BG_LOW: '90' }, key: 'bgLow', asked: 90 },
];

for (const arm of arms) {
  const result = applyEnv(arm.env);
  const stored = result.after[arm.key];
  const rewritten = stored !== arm.asked;
  findings.push({
    ok: !rewritten,
    text: `${arm.label}: the operator asked for ${arm.asked} and the deployment stored `
        + `${stored}. ${rewritten
            ? `The only evidence is ${result.warnings.length} console.warn line(s) on stdout `
              + '— grep over lib/client/ and views/ finds no surface that reports it'
            : 'the value the operator set is what is stored'}`,
  });
}

report('threshold-silent-rewrite (BF-67)', findings);
