'use strict';
/*
 * booterror-shape-coverage.js  —  BF-63
 *
 * `lib/server/booterror.js` renders the page an operator sees when Nightscout
 * refuses to boot. Its error-line map is:
 *
 *   message = JSON.stringify(pick(obj.err, Object.getOwnPropertyNames(obj.err)))
 *
 * `Object.getOwnPropertyNames(obj.err)` is evaluated as an ARGUMENT, before
 * `pick()`'s own `obj == null` guard ever runs, so a boot error carrying no
 * `err` key throws `TypeError: Cannot convert undefined or null to object`.
 * The page that exists to explain why the site will not start is the page
 * that crashes.
 *
 * WHY IT MATTERS MORE THAN AN ORDINARY CRASH: the message it destroys is the
 * mitigation for BF-61 — cut 4 turns a missing `CONNECT_COUNTRY_CODE` into a
 * total site outage, and `{desc:'CONNECT_COUNTRY_CODE is required'}` is
 * precisely the shape that throws here. An operator whose site has gone dark
 * gets a blank failure instead of the one sentence that would tell them what
 * to set.
 *
 * PROVENANCE CORRECTION CARRIED IN THE GATE, because a reviewer sent to the
 * wrong diff dismissed this once: `git diff origin/dev
 * origin/chore/mime-exposure-review -- lib/server/booterror.js` is EMPTY. The
 * renderer is unchanged and pre-existing shipping code. What cut 4 adds is
 * the first callers that omit `err`. So the weakness is in §1 code awaiting a
 * §1b caller — which is why the register files it §1b and says so.
 *
 * THIS GATE FAILS TODAY on the two `err`-less shapes. It goes green when the
 * renderer is defensive — and the register is explicit that the fix must be
 * BOTH halves, the call sites AND the renderer, because fixing only the call
 * sites leaves the next caller to rediscover it.
 *
 * NON-VACUITY. Three control shapes must RENDER through the identical map:
 * the Mongo shape (`err` a string), the ENV shape (`err` an array) and a real
 * `Error`. If the harness threw on all five, the gate would be measuring its
 * own construction. It reports that case as a broken harness, not a defect.
 *
 * READS ONLY: it lifts the map's expression out of the shipping file rather
 * than re-typing it, requires the shipping `pick`, and renders nothing.
 *
 *   --ref <ref>   which ref's booterror.js and pick.js to measure
 */

const path = require('path');
const { CRM, show, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const REF = argValue('--ref', 'origin/dev');
const findings = [];

const rendererSource = show(REF, 'lib/server/booterror.js');
const pickSource = show(REF, 'lib/utils/pick.js');
if (rendererSource === null || pickSource === null) {
  report('booterror-shape-coverage (BF-63)', [{
    ok: false,
    text: `lib/server/booterror.js or lib/utils/pick.js is absent at ${REF}; measured nothing`,
  }]);
}

/*
 * The expression under test is taken FROM THE FILE, not retyped. If the line
 * is ever reworded this gate stops finding it and says so, rather than
 * silently going on measuring a copy of code that no longer ships.
 */
const EXPR = /message = JSON\.stringify\(pick\(obj\.err, Object\.getOwnPropertyNames\(obj\.err\)\)\);/;
const found = EXPR.test(rendererSource);
findings.push({
  ok: found,
  text: `the map expression under test is present verbatim in ${REF}:lib/server/booterror.js `
      + `= ${found}${found ? '' : ' — the renderer has changed shape and this gate can no '
        + 'longer claim to measure it'}`,
});
if (!found) report('booterror-shape-coverage (BF-63)', findings);

// eslint-disable-next-line no-eval
const pick = eval(`(function(){ ${pickSource.replace('module.exports = pick;', '')} return pick; })()`);

function renderLine(obj) {
  // The shipping map, transcribed once from the matched expression above.
  let message;
  if (typeof obj.err === 'string' || obj.err instanceof String) {
    message = obj.err;
  } else {
    message = JSON.stringify(pick(obj.err, Object.getOwnPropertyNames(obj.err)));
  }
  return '<dt><b>' + obj.desc + '</b></dt><dd>' + String(message).replace(/\\n/g, '<br/>') + '</dd>';
}

function attempt(obj) {
  try { return { ok: true, html: renderLine(obj) }; }
  catch (e) { return { ok: false, error: `${e.constructor.name}: ${e.message}` }; }
}

/* --- controls: shapes that ship today and must render -------------------- */
const controls = [
  { label: "the Mongo shape { desc, err: 'econnrefused' }",
    obj: { desc: 'Mongo', err: 'econnrefused' } },
  { label: 'the ENV shape { desc, err: [..] }',
    obj: { desc: 'ENV', err: ['API_SECRET', 'MONGO_CONNECTION'] } },
  { label: 'a real Error { desc, err: new Error(..) }',
    obj: { desc: 'boot', err: new Error('x') } },
];
let rendered = 0;
for (const c of controls) {
  const r = attempt(c.obj);
  if (r.ok) rendered += 1;
  findings.push({
    ok: r.ok,
    text: `control: ${c.label} — ${r.ok ? 'renders' : r.error}`,
  });
}
if (rendered === 0) {
  findings.push({
    ok: false,
    text: 'NO control shape rendered; the harness is broken and nothing below is a defect',
  });
  report('booterror-shape-coverage (BF-63)', findings);
}

/* --- the arms ----------------------------------------------------------- */
const arms = [
  { label: "{ desc: 'CONNECT_COUNTRY_CODE is required' } — cut 4's bootevent.js:330 shape",
    obj: { desc: 'CONNECT_COUNTRY_CODE is required' } },
  { label: '{ desc, err: null }',
    obj: { desc: 'boot', err: null } },
];
for (const a of arms) {
  const r = attempt(a.obj);
  findings.push({
    ok: r.ok,
    text: `${a.label} — ${r.ok
      ? 'renders'
      : `${r.error}. The boot-error page itself fails, so the operator is told nothing at all`}`,
  });
}

/* --- is there a caller? ------------------------------------------------- */
/*
 * Informational but measured, and it is what decides whether this is live or
 * awaiting a caller on a given ref. A `bootErrors.push({...})` whose object
 * literal has no `err:` key is a reachable producer of the failing shape.
 */
const bootevent = show(REF, 'lib/server/bootevent.js') || '';
const pushes = [...bootevent.matchAll(/bootErrors\.push\(\s*\{/g)].map((m) => {
  let depth = 0;
  let i = m.index + m[0].length - 1;
  for (; i < bootevent.length; i += 1) {
    if (bootevent[i] === '{') depth += 1;
    else if (bootevent[i] === '}') { depth -= 1; if (depth === 0) break; }
  }
  return bootevent.slice(m.index, i + 1);
});
/*
 * `err:` AND the ES6 shorthand `err`. The first draft of this arm tested only
 * `/\berr\s*:/` and reported dev's `bootErrors.push({desc: synopsis.join(' '),
 * err})` as an err-less site — a red result for a reason with nothing to do
 * with the property, which would have "refuted" a register claim that is in
 * fact correct. Recorded here because that is the failure this gate is for.
 */
const HAS_ERR = /\berr\s*(:|[,}])/;
const errless = pushes.filter((p) => !HAS_ERR.test(p));
findings.push({
  ok: true,
  text: `${REF}:lib/server/bootevent.js has ${pushes.length} bootErrors.push({...}) site(s), `
      + `${errless.length} of them with no err: key — ${errless.length
        ? 'a reachable producer of the shape that throws above'
        : 'so on this ref the renderer weakness is awaiting a caller'}`,
});

report(`booterror-shape-coverage (BF-63) at ${REF}`, findings);
