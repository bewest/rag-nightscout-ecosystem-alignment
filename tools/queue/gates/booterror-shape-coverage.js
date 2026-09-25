'use strict';
/*
 * booterror-shape-coverage.js  —  BF-63
 *
 * `lib/server/booterror.js` renders the page an operator sees when Nightscout
 * refuses to boot. Up to 15.0.8 its error-line map computed
 *
 *   message = JSON.stringify(pick(obj.err, Object.getOwnPropertyNames(obj.err)))
 *
 * for every non-string `err`. `Object.getOwnPropertyNames(obj.err)` is
 * evaluated as an ARGUMENT, before `pick()`'s own `obj == null` guard runs, so
 * a boot error with no `err` throws `TypeError: Cannot convert undefined or
 * null to object`, and the page that explains why the site will not start
 * crashes instead. `origin/dev` guards it (`obj.err == null` renders the
 * description only; e6a50e9a, merged with #8753).
 *
 * It matters because cut 4 adds the first callers that omit `err`: a missing
 * `CONNECT_COUNTRY_CODE` becomes a boot refusal whose one explanatory line is
 * exactly the shape that throws on a renderer without the guard (BF-61). The
 * fix is both halves - the renderer guard AND `err` at the call sites.
 *
 * WHAT IS MEASURED: the map callback itself, lifted out of the ref's
 * booterror.js (brace-matched from `ctx.bootErrors.map(function (obj) {`) and
 * run with that ref's `pick`. Nothing is retyped, so a guard added anywhere in
 * the callback is seen. If the callback cannot be found, the gate says so and
 * measures nothing.
 *
 * NON-VACUITY: three control shapes must render through the same callback -
 * the Mongo shape (`err` a string), the ENV shape (an array) and a real
 * `Error`. If none renders, the harness is broken and that is reported as
 * such, not as a defect. `--ref origin/master` (15.0.8, no guard) must FAIL
 * the two err-less arms; `--ref origin/dev` must pass them.
 *
 * READS ONLY.
 *
 *   --ref <ref>   which ref's booterror.js, pick.js and bootevent.js to measure
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
 * The map callback is taken FROM THE FILE: find its opening, brace-match to its
 * end, and compile that source with the ref's own `pick` in scope.
 */
const START = /ctx\.bootErrors\.map\(\s*function\s*\(\s*obj\s*\)\s*\{/;
const start = START.exec(rendererSource);
let callbackSource = null;
if (start) {
  let depth = 0;
  let i = start.index + start[0].length - 1;
  for (; i < rendererSource.length; i += 1) {
    if (rendererSource[i] === '{') depth += 1;
    else if (rendererSource[i] === '}') { depth -= 1; if (depth === 0) break; }
  }
  if (depth === 0) callbackSource = rendererSource.slice(start.index + start[0].length - 1, i + 1);
}
findings.push({
  ok: callbackSource !== null,
  text: `the error-line map callback was found in ${REF}:lib/server/booterror.js = ${callbackSource !== null}`
      + `${callbackSource !== null ? '' : ' - the renderer has changed shape and this gate measures nothing'}`,
});
if (callbackSource === null) report('booterror-shape-coverage (BF-63)', findings);

// eslint-disable-next-line no-eval
const pick = eval(`(function(){ ${pickSource.replace('module.exports = pick;', '')} return pick; })()`);
// eslint-disable-next-line no-new-func
const renderLine = new Function('pick', `return function (obj) ${callbackSource};`)(pick);

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
