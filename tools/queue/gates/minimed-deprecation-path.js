'use strict';
/*
 * minimed-deprecation-path.js  — RT-4
 *
 * Cut 4 deletes lib/plugins/mmconnect.js. The adopted train puts a deprecation
 * release in front of it. A deprecation release is only meaningful if the
 * release BEFORE the removal tells an operator, by name, what to set.
 *
 * GT4 measured the asymmetry. Dexcom has a path: bridge-connect-compat.js is on
 * master AND dev and bootevent.js prints DEPRECATION WARNING lines that name
 * DEXCOM_BRIDGE_USE_LEGACY. MiniMed has none: its only warning is the generic
 * "PLEASE CONSIDER nightscout-connect instead." naming no setting at all, and
 * mmconnect-connect-compat.js is BORN in the same branch that deletes the
 * plugin.
 *
 * This matters to a person, not just to a release manager: an operator whose
 * MiniMed data stops arriving is a person whose glucose readings stop arriving.
 *
 * FAILS while dev carries no named MiniMed migration setting. It is expected to
 * fail today; that failure IS the deprecation-release work item.
 */

const { show, report } = require('./_gate');

// QUEUE_GATE_REF lets a branch be checked before it merges; the queue runs dev.
const REF = process.env.QUEUE_GATE_REF || 'origin/dev';
const findings = [];
const boot = show(REF, 'lib/server/bootevent.js');

if (boot === null) {
  findings.push({ ok: false, text: 'origin/dev has no lib/server/bootevent.js' });
  report('minimed-deprecation-path (RT-4)', findings);
}

// Positive control. If the Dexcom path ever stops being detectable, this gate
// has broken rather than the MiniMed path having improved, and we want to know
// which. A gate whose negative result cannot be distinguished from its own
// breakage is not a measurement.
const dexcomNamed = /DEXCOM_BRIDGE_USE_LEGACY/.test(boot);
findings.push({
  ok: dexcomNamed,
  text: 'CONTROL: the Dexcom path names DEXCOM_BRIDGE_USE_LEGACY on dev '
      + '(if this goes BAD the gate itself is broken, not MiniMed)',
});

const mmLines = boot.split('\n')
  .map((line, i) => ({ line, n: i + 1 }))
  .filter((x) => /DEPRECATION WARNING/.test(x.line));

// A warning line may log mmconnect.DEPRECATION_WARNING instead of a literal;
// then the text it logs is the constant in lib/plugins/mmconnect.js.
const plugin = show(REF, 'lib/plugins/mmconnect.js') || '';
const constant = (plugin.match(/var DEPRECATION_WARNING = ([\s\S]*?);\n/) || [])[1] || '';
const logged = (x) => (/mmconnect\.DEPRECATION_WARNING/.test(x.line) ? constant : x.line);

// A named setting is an ALL_CAPS token an operator can put in their env.
const mmNamed = mmLines.filter((x) => /MMCONNECT|CONNECT_COUNTRY_CODE|CONNECT_SOURCE/.test(logged(x)));

findings.push({
  ok: mmNamed.length > 0,
  text: `dev's MiniMed deprecation warnings name a setting an operator can act on `
      + `(${mmNamed.length} of ${mmLines.length} DEPRECATION WARNING lines name one)`,
});

const shim = show(REF, 'lib/server/mmconnect-connect-compat.js');
findings.push({
  ok: shim !== null,
  text: 'dev ships lib/server/mmconnect-connect-compat.js, so the migration can be '
      + 'exercised before the removal release',
});

report('minimed-deprecation-path (RT-4)', findings);
