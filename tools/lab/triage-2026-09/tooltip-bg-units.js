'use strict';
/*
 * Triage probe (cgm-remote-monitor issue #5940): does the chart's treatment
 * tooltip show a careportal BG in the units it was entered in?
 *
 * Usage: node tools/lab/triage-2026-09/tooltip-bg-units.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the tree's own lib/client/renderer.js drawTreatment() in a jsdom
 * document (the tree's tests/fixtures/secure-jsdom.js and dom-globals.js, the
 * harness tests/stored-output-sinks.test.js uses for this tooltip), dispatches
 * a mouseover on the drawn treatment and reads the "BG:" value from the
 * tooltip. d3 comes from the tree: tests/fixtures/d3.js when present (d3 7,
 * dev), otherwise require('d3') (d3 5, 15.0.8). The careportal stores a BG as
 * { glucose, units: <display units> } (lib/client/careportal.js gatherData).
 *
 * Arms (display units differ from the profile's units; a Meal Bolus with 10 g
 * carbs and a BG, which drawTreatment draws as a bubble):
 *   mmol-on-mgdl-profile  display mmol, profile mg/dl, { glucose: 5, units: 'mmol' }
 *                         want 5
 *   mgdl-on-mmol-profile  display mg/dl, profile mmol, { glucose: 90, units: 'mg/dl' }
 *                         want 90
 *   mgdl-record-mmol-all  display mmol, profile mmol, a record stored in mg/dL
 *                         { glucose: 90, units: 'mg/dl' }: want 5 (the tooltip
 *                         keys on the profile's units, not the record's)
 * Controls, which must behave on every tree:
 *   same-units-mmol       display mmol, profile mmol, { glucose: 5, units: 'mmol' }: 5
 *   same-units-mgdl       display mg/dl, profile mg/dl, { glucose: 90, units: 'mg/dl' }: 90
 *   converted             display mmol, profile mg/dl, { glucose: 90, units: 'mg/dl' }: 5
 *                         (a mg/dL record shown in mmol is converted, as it should be)
 *   bg-check-dot          display mmol, profile mg/dl, a BG Check with no carbs or
 *                         insulin, { glucose: 5, units: 'mmol' }: 5. This record is
 *                         drawn by addTreatmentCircles, whose tooltip prints the
 *                         stored value; the report says BG Check entries look right.
 *
 * Exit status: 0 when every arm shows the value as entered, 1 when any arm
 * shows it in the wrong units (the defect), 2 when a control misbehaves,
 * 3 on a harness error (tree missing, jsdom or d3 failed to load).
 * No network: secure-jsdom blocks resource loads, fetch and XHR.
 */
const path = require('path');
const fs = require('fs');
const root = path.resolve(process.argv[2] || '.');
process.on('uncaughtException', (e) => { console.error('harness error:', e); process.exit(3); });
const r = (p) => require(path.join(root, p));

const { createSecureDOM } = r('tests/fixtures/secure-jsdom');
const domGlobals = r('tests/fixtures/dom-globals');
const d3Fixture = path.join(root, 'tests/fixtures/d3.js');
const d3 = fs.existsSync(d3Fixture) ? require(d3Fixture) : require(path.join(root, 'node_modules/d3'));

function tooltipBG (display, profileUnits, treatment, circle) {
  delete global.window; delete global.document;
  const env = createSecureDOM('<!DOCTYPE html><html><body></body></html>');
  const state = domGlobals.installDomGlobals(env);
  const priorD3 = global.d3; global.d3 = d3;
  try {
    const tooltip = d3.select(env.document.body).append('div').append('div').attr('id', 'tooltip');
    const svg = d3.select(env.document.body).append('svg');
    const client = {
      careportal: { resolveEventName: (v) => v },
      chart: { basals: svg.append('g'), drag: svg.append('g'), focus: svg.append('g'), prevChartWidth: 900, xScale: () => 0, yScale: () => 0 },
      ddata: { profile: { getUnits: () => profileUnits } },
      editMode: false, focusRangeMS: 1, formatTime: () => '12:00',
      sbx: { scaleEntry: () => 100 },
      settings: { units: display },
      tooltip, translate: (v) => v,
      utils: { scaleMgdl: (v) => v, toRoundedStr: (v) => String(v) }
    };
    delete require.cache[require.resolve(path.join(root, 'lib/client/renderer'))];
    if (circle) {
      const bgCheck = Object.assign({ eventType: 'BG Check', glucoseType: 'Finger', mills: Date.now() }, treatment);
      client.ddata.treatments = [bgCheck]; client.ddata.tempTargetTreatments = [];
      r('lib/client/renderer')(client, d3).addTreatmentCircles(new Date());
      const dot = svg.select('.treatment-dot').node();
      if (!dot) throw new Error('addTreatmentCircles drew no .treatment-dot');
      dot.dispatchEvent(new env.window.MouseEvent('mouseover', { bubbles: true, clientX: 10, clientY: 10 }));
      const mc = /BG:\s*([-0-9.]+)/.exec(tooltip.text());
      if (!mc) throw new Error('no BG line in tooltip: ' + tooltip.text());
      return Number(mc[1]);
    }
    r('lib/client/renderer')(client, d3).drawTreatment(Object.assign({ eventType: 'Meal Bolus', carbs: 10, glucoseType: 'Finger', mills: Date.now() }, treatment),
      { scale: 2, showLabels: false, treatments: 1 }, 10, {});
    const node = client.chart.focus.select('.draggable-treatment').node();
    if (!node) throw new Error('drawTreatment drew no .draggable-treatment');
    node.dispatchEvent(new env.window.MouseEvent('mouseover', { bubbles: true, clientX: 10, clientY: 10 }));
    const m = /BG:\s*([-0-9.]+)/.exec(tooltip.text());
    if (!m) throw new Error('no BG line in tooltip: ' + tooltip.text());
    return Number(m[1]);
  } finally {
    if (priorD3 === undefined) delete global.d3; else global.d3 = priorD3;
    domGlobals.restoreDomGlobals(state);
  }
}

console.log('tree', root, '| d3', d3.version);
const controls = [
  ['same-units-mmol', 'mmol', 'mmol', { glucose: 5, units: 'mmol' }, 5],
  ['same-units-mgdl', 'mg/dl', 'mg/dl', { glucose: 90, units: 'mg/dl' }, 90],
  ['converted      ', 'mmol', 'mg/dl', { glucose: 90, units: 'mg/dl' }, 5],
  ['bg-check-dot   ', 'mmol', 'mg/dl', { glucose: 5, units: 'mmol' }, 5, true]
];
let broken = false;
for (const [label, disp, prof, t, want, circle] of controls) {
  const got = tooltipBG(disp, prof, t, circle);
  console.log(`control ${label} display ${disp} profile ${prof} stored ${t.glucose} ${t.units}: tooltip BG ${got} (want ${want})${got === want ? '' : '  MISBEHAVES'}`);
  if (got !== want) broken = true;
}
if (broken) { console.log('a control misbehaved; the arms measure nothing'); process.exit(2); }
let bad = 0;
for (const [label, disp, prof, t, want] of [
  ['mmol-on-mgdl-profile', 'mmol', 'mg/dl', { glucose: 5, units: 'mmol' }, 5],
  ['mgdl-on-mmol-profile', 'mg/dl', 'mmol', { glucose: 90, units: 'mg/dl' }, 90],
  ['mgdl-record-mmol-all', 'mmol', 'mmol', { glucose: 90, units: 'mg/dl' }, 5]
]) {
  const got = tooltipBG(disp, prof, t);
  console.log(`arm     ${label} display ${disp} profile ${prof} stored ${t.glucose} ${t.units}: tooltip BG ${got} (want ${want})`);
  if (got !== want) bad++;
}
console.log(bad ? 'RESULT: DEFECT - the tooltip shows a BG in the wrong units' : 'RESULT: tooltip shows the BG as entered');
process.exit(bad ? 1 : 0);
