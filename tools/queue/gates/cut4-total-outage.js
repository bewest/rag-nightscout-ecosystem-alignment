'use strict';
/*
 * cut4-total-outage.js  — RT-5 / RT-1 (the legacy CGM bridge removal, BF-61)
 *
 * The removal of the legacy Dexcom (share2nightscout-bridge) and MiniMed
 * (mmconnect) bridges ships two migration shims. When a shim cannot migrate
 * leftover BRIDGE_* or MMCONNECT_* settings it returns an error; bootevent.js
 * pushes it to ctx.bootErrors, app.js serves the boot-error page for every
 * route, and server.js skips websocket setup. The whole site stops.
 *
 * DECIDED 2026-09-23 (maintainer): that hard stop is intended. These settings
 * are usually the site's primary data source, so a misconfigured one should
 * show a page that says what to fix. So this gate no longer fails because a
 * boot error exists. It fails unless, for every settings shape an operator can
 * hold today:
 *
 *   - a shape that stops the site names a fix, names no release number and
 *     exposes no credential; and
 *   - applying the fix the message names, as written, lets the site boot with
 *     a CGM source selected.
 *
 * "As written" matters. CONNECT_* settings are read only for plugins in
 * ENABLE (lib/server/env.js findExtendedSettings), so a message that says
 * "set CONNECT_COUNTRY_CODE" but not "add connect to ENABLE" names a fix that
 * does not boot. The 15.0.9-rc rehearsal measured exactly that on rh/cut4.
 * The fix is derived from the message text below, so a message that stops
 * naming a step makes the fixed shape stop too, and the gate goes red.
 *
 * Where a message offers two fixes ("To keep X ... To use Y instead ..."), the
 * gate applies the first. The branch's own tests/legacy-bridge-boot-errors.test.js
 * applies both, through the real lib/server/env.js and setupConnect.
 *
 * The ENABLE rule is modelled here (resolve() below) because a gate reads git
 * objects and cannot load env.js with its dependencies. The model is the
 * property under test; the branch test is the check that it matches env.js.
 *
 * QUEUE_GATE_REF selects the tree. The default is the local branch that
 * carries the removal with the decision-A fixes; a clone without it fails
 * with "nothing was measured", which is the safe direction.
 *
 * Reads only: the shims are extracted from the git object database into a
 * scratch directory. No worktree and no shipping file is touched.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { show, report } = require('./_gate');

const REF = process.env.QUEUE_GATE_REF || 'rh/cut1-retire-legacy';
const NAME = `cut4-total-outage (RT-5, ${REF})`;
const findings = [];

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-cut4-'));
function load(file) {
  const source = show(REF, `lib/server/${file}`);
  if (source === null) return null;
  const target = path.join(scratch, file);
  fs.writeFileSync(target, source);
  return require(target);
}

let bridge; let mmconnect;
try {
  bridge = load('bridge-connect-compat.js');
  mmconnect = load('mmconnect-connect-compat.js');
} catch (e) {
  findings.push({ ok: false, text: `could not load the shims: ${e.message}` });
  report(NAME, findings);
}

if (!bridge || !mmconnect) {
  findings.push({ ok: false, text: `${REF} does not carry both migration shims; nothing was measured` });
  report(NAME, findings);
}

const applyBridge = bridge.applyBridgeToConnectCompatibility;
const applyMm = mmconnect.applyMmconnectToConnectCompatibility;
if (typeof applyBridge !== 'function' || typeof applyMm !== 'function') {
  findings.push({ ok: false, text: 'the shims do not export the expected functions; nothing measured' });
  report(NAME, findings);
}

// PLUGIN_SOME_NAME=value is read as extendedSettings.plugin.someName, and only
// for plugins listed in ENABLE. That is the rule the ENABLE gap comes from.
function resolve(shape) {
  const extendedSettings = {};
  for (const plugin of shape.enable) {
    const prefix = `${plugin.toUpperCase()}_`;
    for (const [key, value] of Object.entries(shape.vars)) {
      if (!key.startsWith(prefix)) continue;
      const setting = key.slice(prefix.length).toLowerCase()
        .replace(/_([a-z])/g, (m, c) => c.toUpperCase());
      extendedSettings[plugin] = extendedSettings[plugin] || {};
      extendedSettings[plugin][setting] = value;
    }
  }
  return { extendedSettings };
}

// bootevent.js runs the bridge shim, then the mmconnect shim, on one env.
function bootErrors(shape) {
  const env = resolve(shape);
  const errors = [];
  for (const apply of [applyBridge, applyMm]) {
    const result = apply(env) || {};
    if (result.error) { errors.push(result.error); break; }
  }
  const source = env.extendedSettings.connect && env.extendedSettings.connect.source;
  return { errors, source };
}

// Apply the first fix the message names. Each step is taken only when the
// message says it.
function applyNamedFix(shape, message) {
  const first = message.split(/ To use /)[0];
  const fixed = { enable: shape.enable.slice(), vars: { ...shape.vars } };
  const steps = [];
  const drop = (prefix, plugin) => {
    Object.keys(fixed.vars).filter((k) => k.startsWith(prefix)).forEach((k) => delete fixed.vars[k]);
    fixed.enable = fixed.enable.filter((p) => p !== plugin);
  };
  if (/connect to ENABLE/.test(first) && !fixed.enable.includes('connect')) { fixed.enable.push('connect'); steps.push('add connect to ENABLE'); }
  if (/CONNECT_COUNTRY_CODE/.test(first)) { fixed.vars.CONNECT_COUNTRY_CODE = 'GB'; steps.push('set CONNECT_COUNTRY_CODE'); }
  if (/remove the MMCONNECT_\* settings and mmconnect from ENABLE/.test(first)) { drop('MMCONNECT_', 'mmconnect'); steps.push('remove MMCONNECT_* and mmconnect'); }
  if (/remove the BRIDGE_\* settings and bridge from ENABLE/.test(first)) { drop('BRIDGE_', 'bridge'); steps.push('remove BRIDGE_* and bridge'); }
  return { fixed, steps };
}

const MINIMED = { MMCONNECT_USER_NAME: 'gate-user', MMCONNECT_PASSWORD: 'gate-pass', MMCONNECT_SERVER: 'EU' };
const DEXCOM = { BRIDGE_USER_NAME: 'gate-user', BRIDGE_PASSWORD: 'gate-pass' };
const GLOOKO = { CONNECT_SOURCE: 'glooko', CONNECT_GLOOKO_EMAIL: 'gate@example.invalid', CONNECT_GLOOKO_PASSWORD: 'gate-pass' };

const SHAPES = [
  { name: 'MiniMed, no CONNECT_COUNTRY_CODE', enable: ['mmconnect'], vars: { ...MINIMED } },
  { name: 'MiniMed with CONNECT_COUNTRY_CODE but connect not in ENABLE', enable: ['mmconnect'], vars: { ...MINIMED, CONNECT_COUNTRY_CODE: 'GB' } },
  { name: 'MiniMed with country and connect in ENABLE', enable: ['mmconnect', 'connect'], vars: { ...MINIMED, CONNECT_COUNTRY_CODE: 'GB' } },
  { name: 'Dexcom BRIDGE_* only', enable: ['bridge'], vars: { ...DEXCOM } },
  { name: 'BRIDGE_* and MMCONNECT_* together (works on 15.0.9)', enable: ['bridge', 'mmconnect'], vars: { ...DEXCOM, ...MINIMED, CONNECT_COUNTRY_CODE: 'GB' } },
  { name: 'BRIDGE_* alongside another CONNECT_SOURCE', enable: ['bridge', 'connect'], vars: { ...DEXCOM, ...GLOOKO } },
];

for (const shape of SHAPES) {
  let outcome;
  try { outcome = bootErrors(shape); } catch (e) {
    findings.push({ ok: false, text: `${shape.name} -> shim THREW: ${e.message}` });
    continue;
  }
  if (outcome.errors.length === 0) {
    findings.push({ ok: !!outcome.source, text: `${shape.name} -> boots, CONNECT source ${outcome.source || 'NONE'}` });
    continue;
  }
  const message = outcome.errors[0];
  const clean = !/15\.0\.9/.test(message) && !message.includes('gate-');
  const { fixed, steps } = applyNamedFix(shape, message);
  const after = bootErrors(fixed);
  const ok = clean && steps.length > 0 && after.errors.length === 0 && !!after.source;
  findings.push({
    ok,
    text: `${shape.name} -> stops the site; named fix [${steps.join(', ') || 'NONE'}] `
      + (after.errors.length === 0
        ? `boots with CONNECT source ${after.source}`
        : `STILL STOPS: "${after.errors[0].slice(0, 160)}"`)
      + (clean ? '' : '; message names a release number or exposes a credential'),
  });
}

// BF-62: DEXCOM_BRIDGE_USE_LEGACY is reported as ignored rather than dropped.
findings.push({
  ok: typeof bridge.legacyBridgeRequested === 'function'
    && bridge.legacyBridgeRequested({ useLegacy: true }) === true
    && /ignored/.test(bridge.LEGACY_OVERRIDE_IGNORED || ''),
  text: 'BF-62: the bridge shim detects DEXCOM_BRIDGE_USE_LEGACY and carries a message saying it is ignored',
});

// Control. No legacy settings: nothing stops and nothing is selected. If this
// reports a stop, the gate is misreading the shims.
const control = bootErrors({ enable: ['careportal'], vars: {} });
findings.push({
  ok: control.errors.length === 0 && !control.source,
  text: `CONTROL: no legacy settings -> ${control.errors.length ? 'STOPS' : 'boots'}, no CONNECT source selected`,
});

try { fs.rmSync(scratch, { recursive: true, force: true }); } catch (e) { /* scratch only */ }

report(NAME, findings);
