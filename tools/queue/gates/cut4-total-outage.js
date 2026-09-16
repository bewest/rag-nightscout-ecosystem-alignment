'use strict';
/*
 * cut4-total-outage.js  — RT-5 (cut 4, chore/mime-exposure-review)
 *
 * Cut 4 deletes two CGM ingestion paths. The summaries describe that as losing
 * ingestion. GT4 executed the shims and measured something worse.
 *
 * lib/server/mmconnect-connect-compat.js cannot infer a country from
 * MMCONNECT_SERVER, so an operator with MiniMed credentials and no
 * CONNECT_COUNTRY_CODE gets {migrated:false, error:...}. bootevent.js pushes
 * that to ctx.bootErrors; app.js then installs app.get('*', bootErrorView) and
 * returns, and server.js returns before websocket setup. The WHOLE SITE serves
 * the boot-error page. No API, no sockets, no charts.
 *
 * And an operator running BRIDGE_* and MMCONNECT_* together — which works today
 * as two independent boot stages — hits the same total outage, because cut 4
 * has one CONNECT_SOURCE and the second source has nowhere to go. That is a
 * capability removal, concurrent multi-source CGM ingestion, absent from every
 * summary of this cut.
 *
 * What this means for a person: their Nightscout goes dark. Not degraded — dark.
 * Someone managing diabetes loses the display they check, and loses it at
 * upgrade time, which is not when anyone is braced for it.
 *
 * This gate re-runs GT4's execution. It FAILS while any env shape a real
 * operator can hold today produces a bootError. It must be green before cut 4
 * ships, and the deprecation release in front of it is what makes it green.
 *
 * Reads only: the shims are extracted from the git object database into a
 * scratch directory. No worktree and no shipping file is touched.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { show, report } = require('./_gate');

const REF = 'origin/chore/mime-exposure-review';
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
  findings.push({ ok: false, text: `could not load cut 4's shims: ${e.message}` });
  report('cut4-total-outage (RT-5)', findings);
}

if (!bridge || !mmconnect) {
  findings.push({
    ok: false,
    text: `${REF} does not carry both migration shims; nothing was measured`,
  });
  report('cut4-total-outage (RT-5)', findings);
}

const applyBridge = bridge.applyBridgeToConnectCompatibility;
const applyMm = mmconnect.applyMmconnectToConnectCompatibility;

if (typeof applyBridge !== 'function' || typeof applyMm !== 'function') {
  findings.push({ ok: false, text: 'the shims do not export the expected functions; nothing measured' });
  report('cut4-total-outage (RT-5)', findings);
}

// The shims read env.extendedSettings.{bridge,mmconnect,connect}, NOT flat
// process-env names. An earlier version of this gate passed flat names, got
// {migrated:false} from every shape because no legacy settings were visible,
// and reported four outages. That is a vacuous gate wearing a failing result:
// every shape "failed" for a reason that had nothing to do with the property.
// It is recorded here because it is the exact error the gate exists to prevent.
//
// And the discriminator is `error`, not `migrated`. A bare {migrated:false}
// means "no legacy credentials to migrate", which is the correct answer for an
// operator who has none. Only an `error` becomes a bootError.
const SHAPES = [
  {
    name: 'MiniMed credentials, no CONNECT_COUNTRY_CODE (the common case: the '
        + 'country cannot be inferred from MMCONNECT_SERVER)',
    settings: { mmconnect: { userName: 'u', password: 'p', server: 'carelink.minimed.eu' } },
  },
  {
    name: 'MiniMed credentials WITH CONNECT_COUNTRY_CODE (the documented upgrade)',
    settings: { mmconnect: { userName: 'u', password: 'p' }, connect: { countryCode: 'us' } },
  },
  {
    name: 'Dexcom BRIDGE_* only (this path has a named deprecation escape hatch today)',
    settings: { bridge: { userName: 'u', password: 'p', server: 'US' } },
  },
  {
    name: 'BRIDGE_* and MMCONNECT_* together -- two independent boot stages that '
        + 'work today, and one CONNECT_SOURCE afterwards',
    settings: {
      bridge: { userName: 'u', password: 'p', server: 'US' },
      mmconnect: { userName: 'u', password: 'p' },
      connect: { countryCode: 'us' },
    },
  },
];

for (const shape of SHAPES) {
  // bootevent.js calls the bridge shim first, then the mmconnect shim, against
  // the SAME env object. Running them in isolation would miss the interaction,
  // which is the entire point of the fourth shape.
  const env = { extendedSettings: JSON.parse(JSON.stringify(shape.settings)) };
  const results = [];
  try {
    if (env.extendedSettings.bridge) results.push(applyBridge(env) || {});
    if (env.extendedSettings.mmconnect) results.push(applyMm(env) || {});
  } catch (e) {
    findings.push({ ok: false, text: `${shape.name} -> shim THREW: ${e.message}` });
    continue;
  }

  const errored = results.filter((r) => r && r.error);
  findings.push({
    ok: errored.length === 0,
    text: errored.length === 0
      ? `${shape.name} -> migrates cleanly (${results.map((r) => `migrated:${r.migrated}`).join(', ')})`
      : `${shape.name} -> bootError: "${errored.map((r) => r.error).join(' | ').slice(0, 220)}". `
        + 'bootevent pushes this to ctx.bootErrors, app.js serves the boot-error page '
        + 'for "*", and server.js skips websocket setup. The entire site goes dark.',
  });
}

// Control. A shape with NO legacy credentials must come back benign; if this
// ever reports an outage, the gate is mis-reading the shims rather than the
// shims being hostile, and the four results above mean nothing.
const cleanEnv = { extendedSettings: { connect: { source: 'dexcomshare' } } };
const control = [applyBridge(cleanEnv), applyMm(cleanEnv)];
findings.push({
  ok: control.every((r) => r && !r.error),
  text: 'CONTROL: an operator with no legacy credentials migrates without error '
      + `(${control.map((r) => `migrated:${r.migrated}`).join(', ')})`,
});

try { fs.rmSync(scratch, { recursive: true, force: true }); } catch (e) { /* scratch only */ }

report('cut4-total-outage (RT-5)', findings);
