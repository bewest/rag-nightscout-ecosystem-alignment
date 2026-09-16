'use strict';
/*
 * config-surface-census.js  —  BF-46, BF-48, BF-49, BF-50, BF-51
 *
 * One property, five places it is false: **a configuration name an operator
 * can set is visible in the configuration surface, and a name the surface
 * advertises does something.**
 *
 * `lib/server/env.js` is the surface. Every configuration census this
 * programme has run — and every operator reading `README.md` — goes through
 * it. A variable read straight from `process.env` somewhere else is invisible
 * to both, and under multi-tenancy it is worse than invisible: it cannot be
 * per-tenant at all, because it never passes through anything that has a
 * tenant.
 *
 * ARMS, selected with `--arm <name>` (default: all):
 *
 *   api3      BF-46. `lib/api3/index.js` setENVTruthy reads process.env
 *             directly for API3_SECURITY_ENABLE, API3_DEDUP_FALLBACK_ENABLED,
 *             API3_CREATED_AT_FALLBACK_ENABLED, API3_MAX_LIMIT and
 *             API3_AUTOPRUNE_<COLLECTION> for six collections. The autoprune
 *             family IRREVERSIBLY DELETES a person's stored glucose history
 *             and the delete is not awaited, so a failure is not even
 *             observed. Not one of them appears in README.md or env.js.
 *   webhook   BF-48. lib/plugins/webhook.js reads WEBHOOK_PROTOCOL, _HOST,
 *             _PORT, _PATH from process.env.
 *   hsts      BF-49. The env name settings.js's OWN nameFromKey produces for
 *             its security keys is not a name env.js reads — measured by
 *             running settings.js, not by guessing the spelling.
 *   readme    BF-50. README.md documents MONGODB_COLLECTION; nothing reads it.
 *   azure     BF-51. azuredeploy.json declares a WEBSITE_NODE_DEFAULT_VERSION
 *             parameter and references it nowhere.
 *
 * THIS GATE FAILS TODAY. Every arm is a recorded register entry; the gate is
 * those entries as a measurement, and it goes green when the surface tells
 * the truth.
 *
 * NON-VACUITY — the part that matters, because four of five arms are greps
 * and a grep is this programme's characteristic vacuity trap. Every arm
 * carries a CONTROL that must come out the OTHER way through the identical
 * lookup:
 *   api3/webhook/readme  MONGO_CONNECTION and DISPLAY_UNITS are found in both
 *                        README.md and env.js, and ENTRIES_COLLECTION is found
 *                        in env.js — so "not found" means absent, not that the
 *                        lookup is broken.
 *   hsts                 customTitle's generated name IS read by env.js.
 *   azure                mongoConnection IS referenced by parameters(); so a
 *                        zero for the Node knob is a fact about that knob.
 * A red arm whose control is also red is reported as a BROKEN LOOKUP, not as
 * a defect. That distinction is the whole reason the controls are here:
 * cut4-total-outage's first draft reported four outages that were four
 * misreads, and it was caught only because an earlier pass said two shapes
 * should be clean.
 *
 * READS ONLY — `git show` out of the object database, plus one `require` of
 * the shipping settings module. `--ref <ref>` measures a different ref.
 */

const path = require('path');
const { CRM, show, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const REF = argValue('--ref', 'origin/dev');
const ONLY = argValue('--arm', null);
const findings = [];

function wanted(arm) { return !ONLY || ONLY === arm; }

// --readme / --envjs replace one side of the comparison with a local file.
// They exist for the non-vacuity ablation — doctor a copy of README.md so the
// names ARE documented and confirm the arm goes green — and for nothing else.
// A gate that can only ever be red has not been shown to measure anything.
const fs = require('fs');
const readmeOverride = argValue('--readme', null);
const envjsOverride = argValue('--envjs', null);
const README = readmeOverride ? fs.readFileSync(readmeOverride, 'utf8') : show(REF, 'README.md');
const ENVJS = envjsOverride ? fs.readFileSync(envjsOverride, 'utf8') : show(REF, 'lib/server/env.js');

if (README === null || ENVJS === null) {
  report('config-surface-census', [{
    ok: false,
    text: `could not read README.md and lib/server/env.js at ${REF}; this gate measured nothing`,
  }]);
}

const inReadme = (name) => README.includes(name);
const inEnv = (name) => ENVJS.includes(name);

/* --- the shared control, run once and named ----------------------------- */
const controlOk = inReadme('MONGO_CONNECTION') && inEnv('MONGO_CONNECTION')
               && inReadme('DISPLAY_UNITS') && inEnv('DISPLAY_UNITS')
               && inEnv('ENTRIES_COLLECTION');
findings.push({
  ok: controlOk,
  text: `control for every name lookup at ${REF}: MONGO_CONNECTION and DISPLAY_UNITS are `
      + `present in BOTH README.md and lib/server/env.js, ENTRIES_COLLECTION in env.js. `
      + (controlOk ? 'A "not found" below is therefore absence, not a broken lookup.'
                   : 'THE LOOKUP IS BROKEN — treat every red arm below as unmeasured.'),
});

function censusArm(label, names, opts) {
  const missing = names.filter((n) => !inReadme(n) || (opts.alsoEnv && !inEnv(n)));
  findings.push({
    ok: missing.length === 0,
    text: `${label}: ${names.length} name(s) checked, ${missing.length} absent from `
        + `${opts.alsoEnv ? 'README.md and/or lib/server/env.js' : 'README.md'}`
        + (missing.length ? ` — ${missing.join(', ')}` : ''),
  });
}

/* --- api3 (BF-46) ------------------------------------------------------- */
if (wanted('api3')) {
  const COLLECTIONS = ['DEVICESTATUS', 'ENTRIES', 'FOOD', 'PROFILE', 'SETTINGS', 'TREATMENTS'];
  const names = ['API3_SECURITY_ENABLE', 'API3_DEDUP_FALLBACK_ENABLED',
                 'API3_CREATED_AT_FALLBACK_ENABLED', 'API3_MAX_LIMIT']
    .concat(COLLECTIONS.map((c) => `API3_AUTOPRUNE_${c}`));

  // Confirm the call sites are really there before reporting on their names,
  // so a renamed helper reads as "this gate can no longer see it" rather than
  // as a silently passing arm.
  const api3 = show(REF, 'lib/api3/index.js') || '';
  const collection = show(REF, 'lib/api3/generic/collection.js') || '';
  const sitesPresent = api3.includes('setENVTruthy') && api3.includes('process.env[varName]')
                    && collection.includes("'API3_AUTOPRUNE_'");
  findings.push({
    ok: sitesPresent,
    text: `api3 call sites at ${REF}: setENVTruthy reading process.env directly = `
        + `${api3.includes('process.env[varName]')}, API3_AUTOPRUNE_ prefix in `
        + `generic/collection.js = ${collection.includes("'API3_AUTOPRUNE_'")}`,
  });
  censusArm('BF-46 api3 variables documented and in the env surface', names, { alsoEnv: true });

  // The deletion is the reason this arm is high, so it is measured, not
  // asserted: deleteManyOr is called without await and without a promise.
  const pruneBlock = collection.slice(collection.indexOf('function autoPrune'),
                                      collection.indexOf('function autoPrune') + 1400);
  const unawaited = /self\.storage\.deleteManyOr\(/.test(pruneBlock)
                 && !/await\s+self\.storage\.deleteManyOr/.test(pruneBlock);
  findings.push({
    ok: !unawaited,
    text: `BF-46 deletion path at ${REF}: API3_AUTOPRUNE_<COLLECTION> computes deleteBefore and `
        + `calls storage.deleteManyOr ${unawaited ? 'WITHOUT awaiting the result — an '
          + 'irreversible delete of stored glucose history whose failure is not observed'
          : 'with the result awaited'}`,
  });
}

/* --- webhook (BF-48) ---------------------------------------------------- */
if (wanted('webhook')) {
  const plugin = show(REF, 'lib/plugins/webhook.js') || '';
  const reads = /process\.env\.WEBHOOK_/.test(plugin);
  findings.push({
    ok: reads,
    text: `webhook call site at ${REF}: lib/plugins/webhook.js reads process.env.WEBHOOK_* = `
        + `${reads} (if false this arm is measuring nothing, not passing)`,
  });
  censusArm('BF-48 webhook variables documented and in the env surface',
            ['WEBHOOK_PROTOCOL', 'WEBHOOK_HOST', 'WEBHOOK_PORT', 'WEBHOOK_PATH'],
            { alsoEnv: true });
}

/* --- hsts (BF-49) ------------------------------------------------------- */
/*
 * Measured by EXECUTING the shipping settings module and recording the env
 * names it asks its accessor for. Grepping for a spelling would beg the
 * question — the defect IS that two spellings exist, so a gate that hardcodes
 * one of them cannot detect a third.
 */
if (wanted('hsts')) {
  const SETTINGS = path.join(CRM, 'lib', 'settings.js');
  let asked = [];
  try {
    delete require.cache[require.resolve(SETTINGS)];
    const settings = require(SETTINGS)();
    const info = console.info; console.info = () => {};
    try {
      settings.eachSettingAsEnv((name) => { asked.push(name); return undefined; });
    } finally { console.info = info; }
  } catch (e) {
    asked = null;
    findings.push({ ok: false, text: `could not execute lib/settings.js: ${e.message}` });
  }
  if (asked) {
    const security = asked.filter((n) => /^(SECURE_|INSECURE_)/.test(n));
    const found = security.filter((n) => inEnv(n));
    const orphans = security.filter((n) => !inEnv(n));
    // The control is inside the same family, run through the identical
    // lookup: if SOME security names generated by nameFromKey are found in
    // env.js and others are not, the comparison works and the misses are real.
    // A control outside the family would be weaker, and an all-or-nothing
    // result would mean the lookup, not the spelling.
    findings.push({
      ok: found.length > 0,
      text: `hsts control: of ${security.length} security env names settings.js generates, `
          + `${found.length} ARE read by env.js (${found.join(', ') || 'none'}) — so a miss `
          + 'below is a spelling divergence, not a broken comparison',
    });
    findings.push({
      ok: orphans.length === 0,
      text: `BF-49: ${orphans.length} of the ${security.length} security env name(s) `
          + "settings.js's own nameFromKey asks for are read by no line of lib/server/env.js"
          + (orphans.length ? ` — ${orphans.join(', ')}. env.js reads the no-underscore `
            + 'spelling SECURE_HSTS_HEADER_INCLUDESUBDOMAINS, which nameFromKey never '
            + 'produces, so a settings-dictionary reader sets a header that never moves'
            : ''),
    });
  }
}

/* --- readme (BF-50) ----------------------------------------------------- */
if (wanted('readme')) {
  const reads = ['lib/server/env.js', 'lib/settings.js', 'lib/storage/mongo-storage.js',
                 'bin/dedupe-entries.js', 'bin/prepare-secrets.js']
    .map((f) => show(REF, f) || '').join('\n');
  const documented = inReadme('MONGODB_COLLECTION');
  const read = reads.includes('MONGODB_COLLECTION');
  findings.push({
    ok: !(documented && !read),
    text: `BF-50: README.md documents MONGODB_COLLECTION = ${documented}; any of the five `
        + `configuration/storage modules reads it = ${read}. Control: the same files DO `
        + `contain ENTRIES_COLLECTION = ${reads.includes('ENTRIES_COLLECTION')}`,
  });
}

/* --- azure (BF-51) ------------------------------------------------------ */
if (wanted('azure')) {
  const template = show(REF, 'azuredeploy.json');
  if (template === null) {
    findings.push({ ok: false, text: `azuredeploy.json does not exist at ${REF}` });
  } else {
    const count = (s) => (template.match(new RegExp(`parameters\\('${s}'\\)`, 'g')) || []).length;
    const declared = template.includes('"WEBSITE_NODE_DEFAULT_VERSION"');
    const used = count('WEBSITE_NODE_DEFAULT_VERSION');
    const control = count('mongoConnection');
    findings.push({
      ok: control > 0,
      text: `azure control at ${REF}: parameters('mongoConnection') occurs ${control} time(s) — `
          + 'a zero below is a fact about the parameter, not about the regex',
    });
    findings.push({
      ok: !(declared && used === 0),
      text: `BF-51: WEBSITE_NODE_DEFAULT_VERSION declared as a parameter = ${declared}, `
          + `referenced via parameters(...) ${used} time(s). The appSettings value is the `
          + 'literal string, so the field that appears to control an Azure deployment\'s '
          + 'Node version controls nothing',
    });
  }
}

report(`config-surface-census (${ONLY || 'all arms'}) at ${REF}`, findings);
