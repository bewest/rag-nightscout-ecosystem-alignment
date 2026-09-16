'use strict';
/*
 * connector-pin-exposure.js  —  BF-42, BF-43, BF-65
 *
 * Every cgm-remote-monitor ref pins `nightscout-connect` as a tarball URL.
 * WHICH tarball decides two things an operator cannot see from their own
 * deployment, and this gate measures both.
 *
 * 1. THE v0.0.13 TAG LEAKS CREDENTIALS (BF-42, §1 — `origin/master` pins it,
 *    so it is what every current operator runs; BF-65, §1b — cuts 1, 2 and 3
 *    pin it too, and the adopted train ships those first as the "low-risk"
 *    releases). In that tree `index.js:54` is
 *    `console.log("INPUT PARAMS", spec, validated.config)`, printing the
 *    source's validated credential object — Dexcom's sharePassword,
 *    MiniMed's carelinkPassword, LibreLinkUp's linkUpPassword, Glooko's
 *    password — at every boot, for every source, before any network call,
 *    with no setting that disables it.
 *
 *    REDACTION DOES NOT IMPROVE MONOTONICALLY WITH RELEASE ORDER, which is
 *    why this is measured per-ref rather than assumed from a version number.
 *    `dev`'s pin `234d47c8` DELETES the leaking call sites; master's does not.
 *    A widely-repeated statement that "dev makes debug logging opt-in, which
 *    narrows when the leaks happen but does not stop them" is inverted.
 *
 * 2. THE axios OVERRIDE VIOLATES THE CONNECTOR'S OWN CONSTRAINT (BF-43).
 *    `origin/master` sets `overrides['nightscout-connect'].axios = "1.16.0"`
 *    while the connector declares `dependencies.axios = "^1.18.1"`.
 *    `overrides` exists precisely to suppress the ERESOLVE that would
 *    otherwise reject this, so nothing reports it — and master's lockfile
 *    confirms the override takes effect.
 *
 * NO RUNTIME FAILURE IS CLAIMED for arm 2. No axios API was identified that
 * the connector uses and 1.16.0 lacks. The defect asserted is the silent
 * constraint violation, and the gate asserts exactly that and no more.
 *
 * NON-VACUITY. The control is built in and is not optional: `origin/dev`
 * passes arm 1 (it pins a redacted tree) while master and cuts 1-3 fail, and
 * every ref except master passes arm 2. A gate that reported every ref the
 * same way would be measuring the command, not the pins. If EVERY ref comes
 * out the same, the gate says so and fails as unmeasured.
 *
 * READS ONLY, out of two object databases. No network: the pinned revision is
 * resolved against the local `externals/nightscout-connect` clone, and if a
 * revision is not present locally the gate says UNRESOLVED rather than
 * guessing.
 *
 *   --refs a,b,c   which cgm-remote-monitor refs to measure
 */

const path = require('path');
const { REPO_ROOT, CRM, show, report } = require('./_gate');

const CONNECT = path.join(REPO_ROOT, 'externals', 'nightscout-connect');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const REFS = argValue('--refs', 'origin/master,origin/dev').split(',').map((s) => s.trim());
const LEAKING_TAG = 'refs/tags/v0.0.13.tar.gz';

/*
 * A minimum-version comparison for the one range shape in play (`^X.Y.Z`),
 * written out rather than pulled from `semver`. `semver` resolves here only
 * from a node_modules directory OUTSIDE this repository, and a gate whose
 * verdict depends on a package that may or may not be installed is not a
 * measurement. If the range is not a plain caret the gate reports UNCHECKED.
 */
function caretMinimum(range) {
  const m = /^\^(\d+)\.(\d+)\.(\d+)$/.exec((range || '').trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function parseExact(version) {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec((version || '').trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function satisfiesCaret(version, range) {
  const min = caretMinimum(range);
  const v = parseExact(version);
  if (!min || !v) return null;
  if (v[0] !== min[0]) return false;                       // caret pins the major
  if (v[1] !== min[1]) return v[1] > min[1];
  return v[2] >= min[2];
}

function pinnedRevision(url) {
  if (!url) return null;
  const tag = /refs\/tags\/(v[\d.]+)\.tar\.gz/.exec(url);
  if (tag) return tag[1];
  const sha = /archive\/([0-9a-f]{7,40})\.tar\.gz/.exec(url);
  return sha ? sha[1] : null;
}

const findings = [];
const verdicts = [];

for (const ref of REFS) {
  const raw = show(ref, 'package.json');
  if (raw === null) {
    findings.push({ ok: false, text: `${ref}: package.json does not exist at this ref` });
    continue;
  }
  let pkg;
  try { pkg = JSON.parse(raw); } catch (e) {
    findings.push({ ok: false, text: `${ref}: package.json does not parse: ${e.message}` });
    continue;
  }

  const pin = (pkg.dependencies || {})['nightscout-connect'];
  const leaking = typeof pin === 'string' && pin.includes(LEAKING_TAG);
  verdicts.push(leaking);
  findings.push({
    ok: !leaking,
    text: `BF-42/BF-65 ${ref}: nightscout-connect pinned at ${pinnedRevision(pin) || pin}`
        + (leaking
          ? ' — the v0.0.13 TAG, the tree with 112 live console.* sites, 101 of them passing '
            + 'a non-literal argument, and no debug guard anywhere'
          : ' — not the v0.0.13 tag'),
  });

  const override = ((pkg.overrides || {})['nightscout-connect'] || {}).axios;
  if (override === undefined) {
    findings.push({
      ok: true,
      text: `BF-43 ${ref}: no axios override for nightscout-connect; nothing to violate`,
    });
    continue;
  }
  const rev = pinnedRevision(pin);
  const connectRaw = rev
    ? show(rev, 'package.json', CONNECT)
    : null;
  if (connectRaw === null) {
    findings.push({
      ok: false,
      text: `BF-43 ${ref}: axios override ${override} is set, but the pinned revision `
          + `${rev || '(unparsed)'} is not present in externals/nightscout-connect, so the `
          + 'constraint it overrides is UNRESOLVED. Not a pass',
    });
    continue;
  }
  const declared = (JSON.parse(connectRaw).dependencies || {}).axios;
  const ok = satisfiesCaret(override, declared);
  findings.push({
    ok: ok !== false,
    text: `BF-43 ${ref}: overrides['nightscout-connect'].axios = ${override}; the connector at `
        + `${rev} declares axios ${declared}. ` + (ok === null
          ? 'UNCHECKED — not a plain caret range, this gate does not guess'
          : ok
            ? 'the override satisfies the declared range'
            : 'the override VIOLATES the declared range, and `overrides` is exactly what '
              + 'suppresses the ERESOLVE that would otherwise report it'),
  });
}

/*
 * The vacuity check proper: if every ref measured came out the same way on
 * arm 1, this run has not distinguished anything and must not be read as a
 * result either way.
 */
if (verdicts.length > 1 && verdicts.every((v) => v === verdicts[0])) {
  findings.push({
    ok: false,
    text: `all ${verdicts.length} refs returned the same pin verdict (${verdicts[0]}); this run `
        + 'distinguished nothing. Include origin/dev, whose pin is redacted, as a control',
  });
}

report(`connector-pin-exposure (BF-42, BF-43, BF-65) over ${REFS.length} ref(s)`, findings);
