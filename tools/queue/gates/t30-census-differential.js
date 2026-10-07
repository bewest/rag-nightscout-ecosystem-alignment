'use strict';
/*
 * t30-census-differential.js  —  T30-RESEARCH
 *
 * One property: **the configuration surface the tenant-owner specification
 * enumerates is the configuration surface the code reads.** Not "the report
 * exists", and not "the report's numbers were once printed by a script" — the
 * two sets, derived independently at run time, are compared name by name and
 * the gate fails on any name present in one and absent from the other.
 *
 * WHAT IT LIFTS. The census script printed in §G.3 of
 * docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md, verbatim
 * for its four sources, so that its output can be compared with the
 * transcript the document quotes:
 *   s1          lib/settings.js's own eachSettingAsEnv, executed
 *   s2          literal arguments to the readENV family inside lib/server/env.js
 *   s3prefixes  lib/plugins/*.js basenames (findExtendedSettings accepts any
 *               <PLUGIN>_* key, so the closed set is the prefix set)
 *   s4          README.md, any [A-Z][A-Z0-9]*(_[A-Z0-9]+)+ token
 *   union       s1 ∪ s2 ∪ s4
 *
 * WHAT IT ADDS — the places §B.2 says configuration enters that no G.3 source
 * can see, each enumerated by parsing the code rather than copied from the
 * document (which would make the comparison circular):
 *   direct      process.env.X and process.env['X'] anywhere in lib/ or bin/
 *               outside lib/server/env.js (§B.2 gaps 1, 2 and CI)
 *   generic     literal arguments to api3's setENVTruthy, plus the
 *               'PREFIX_' + collection.toUpperCase() call expanded over the
 *               collections api3 registers in `enabledCollections` (gap 3)
 *   injected    readers over an env object that defaults to process.env —
 *               readEnv(env,'X') / readEnv('X','Y') / readInt('X') /
 *               source.X / env[CONST] in any file that takes `|| process.env`
 *               or defines readEnv (gap 5: the hosted entrypoints)
 * and an AUDIT: every process.env[<expression>] site outside env.js must
 * belong to a reader whose callers this gate parses. A new generic reader is
 * a new invisible family, and it is reported rather than silently missed.
 *
 * THE REPORT SIDE is parsed from §B.4 (class lists T, TS, D, B, X, the
 * "ten the census could not see" table and the WEBHOOK line) and §B.6. The
 * document abbreviates; the gate expands:
 *   `PREFIX_*` (N)        every code-side name with that prefix, and the
 *                         expansion must have exactly N members — so the
 *                         document's hand-expanded group counts are checked
 *                         rather than trusted
 *   `X_1`…`X_8`           a numeric range
 *   `A_B_C` `_D`          a suffix fragment, attached to the previous name's
 *                         stem (the API3_AUTOPRUNE_ row)
 *
 * NON-VACUITY. Run it against a copy of the tree with one extra
 * readENV('...') planted in lib/server/env.js: it must go red naming exactly
 * that variable as code-only. Run it against an identical untampered copy: it
 * must go green, or the red above may be the copy's fault (an incomplete copy
 * is red for the wrong reason). Both commands are in the evidence note,
 * docs/60-research/tenancy/t30-census-gate-and-schema-cred-2026-10-07.md.
 *
 * MODES (one is required — there is no default tree, because the document
 * names the commit it measured and a moving default would quietly measure a
 * different one):
 *   --ref <ref>    read out of the cgm-remote-monitor object database
 *                  (externals/cgm-remote-monitor-official, which every crm-*
 *                  worktree shares). lib/settings.js and lib/constants.json are
 *                  materialised into a temporary directory to be executed.
 *   --root <dir>   read a working tree or a copy of one, e.g. a control copy.
 *   --spec <path>  the specification (default: the 2026-09-15 document).
 *
 * READS ONLY. Nothing is written to a checkout or a worktree.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { REPO_ROOT, CRM, show, git, report } = require('./_gate');

function argValue (flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const REF = argValue('--ref', null);
const ROOT = argValue('--root', null);
const SPEC = argValue('--spec', path.join(REPO_ROOT, 'docs', '30-design', 'tenancy',
  'tenant-owner-config-surface-2026-09-15.md'));
const NAME = 't30-census-differential';
const findings = [];

if (!!REF === !!ROOT) {
  console.log(`gate: ${NAME}\n  BAD  exactly one of --ref <ref> or --root <dir> is required; nothing was measured`);
  process.exit(1);
}
const where = REF ? `ref ${REF}` : `tree ${ROOT}`;

/* --- the tree, behind one interface for both modes ------------------------ */

function walk (dir, rel, out) {
  let entries;
  try { entries = fs.readdirSync(path.join(dir, rel), { withFileTypes: true }); } catch (e) { return out; }
  for (const e of entries) {
    if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const r = path.posix.join(rel, e.name);
    if (e.isDirectory()) walk(dir, r, out); else out.push(r);
  }
  return out;
}

const tree = REF
  ? {
      list () {
        try { return git(['ls-tree', '-r', '--name-only', REF, '--', 'lib', 'bin']).split('\n').filter(Boolean); } catch (e) { return []; }
      },
      read (f) { return show(REF, f); },
    }
  : {
      list () { return walk(path.resolve(ROOT), 'lib', []).concat(walk(path.resolve(ROOT), 'bin', [])); },
      read (f) { try { return fs.readFileSync(path.join(path.resolve(ROOT), f), 'utf8'); } catch (e) { return null; } },
    };

const ENVJS = tree.read('lib/server/env.js');
const README = tree.read('README.md');
const SPECTEXT = (() => { try { return fs.readFileSync(SPEC, 'utf8'); } catch (e) { return null; } })();
if (ENVJS === null || README === null || SPECTEXT === null) {
  report(NAME, [{ ok: false,
    text: `could not read lib/server/env.js, README.md (at ${where}) and the specification ${SPEC}; `
        + 'this gate measured nothing' }]);
}

/* --- s1: execute the settings layer ---------------------------------------- */

function settingsNames () {
  let dir = ROOT ? path.resolve(ROOT) : null;
  let tmp = null;
  if (REF) {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 't30-census-'));
    fs.mkdirSync(path.join(tmp, 'lib'));
    for (const f of ['lib/settings.js', 'lib/constants.json']) {
      const body = show(REF, f);
      if (body === null) throw new Error(`${f} does not exist at ${REF}`);
      fs.writeFileSync(path.join(tmp, f), body);
    }
    dir = tmp;
  }
  const file = path.join(dir, 'lib', 'settings.js');
  const names = new Set();
  const info = console.info; console.info = () => {};
  try {
    delete require.cache[require.resolve(file)];
    const settings = require(file)();
    settings.eachSettingAsEnv((n) => { names.add(n); return undefined; });
  } finally {
    console.info = info;
    if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
  }
  return names;
}

let s1;
try { s1 = settingsNames(); } catch (e) {
  report(NAME, [{ ok: false, text: `could not execute lib/settings.js at ${where}: ${e.message}` }]);
}

/* --- s2, s3, s4: §G.3's regexes, unchanged --------------------------------- */

const s2 = new Set();
for (const m of ENVJS.matchAll(/readENV(?:Truthy|Raw)?\s*\(\s*['"]([A-Z0-9_]+)['"]/g)) s2.add(m[1]);
for (const m of ENVJS.matchAll(/readEnvFile\s*\(\s*['"]([A-Z0-9_]+)['"]/g)) s2.add(m[1]);
for (const m of ENVJS.matchAll(/(?:shadowEnv|process\.env)\s*\[\s*['"]([A-Z0-9_]+)['"]\s*\]/g)) s2.add(m[1]);
for (const m of ENVJS.matchAll(/process\.env\.([A-Z][A-Z0-9_]+)/g)) s2.add(m[1]);

const files = tree.list();
const s3 = new Set(files.filter((f) => /^lib\/plugins\/[^/]+\.js$/.test(f))
  .map((f) => path.posix.basename(f, '.js').toUpperCase()));

const s4 = new Set();
for (const m of README.matchAll(/\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b/g)) s4.add(m[1]);

const union = new Set([...s1, ...s2, ...s4]);

/* --- what §B.2 says the four sources cannot see ---------------------------- */

const jsFiles = files.filter((f) => f.endsWith('.js') && f !== 'lib/server/env.js');
const direct = new Map(); // name -> first site
const generic = new Map();
const injected = new Map();
const unexplained = [];
const add = (map, name, site) => { if (!map.has(name)) map.set(name, site); };

// Readers whose CALLERS this gate parses. A dynamic process.env[...] read
// anywhere else is a reader the gate cannot see through.
const KNOWN_DYNAMIC = [
  { file: 'lib/api3/index.js', why: 'setENVTruthy — callers parsed as `generic`' },
  { file: 'bin/feed.js', why: 'readEnv(name, fallback) — callers parsed as `injected`' },
];

for (const f of jsFiles) {
  const src = tree.read(f);
  if (src === null) continue;
  const lineOf = (i) => src.slice(0, i).split('\n').length;

  for (const m of src.matchAll(/process\.env\.([A-Z][A-Z0-9_]+)/g)) add(direct, m[1], `${f}:${lineOf(m.index)}`);
  for (const m of src.matchAll(/process\.env\s*\[\s*['"]([A-Z0-9_]+)['"]\s*\]/g)) add(direct, m[1], `${f}:${lineOf(m.index)}`);

  for (const m of src.matchAll(/process\.env\s*\[(?!\s*['"][A-Z0-9_]+['"]\s*\])/g)) {
    if (!KNOWN_DYNAMIC.some((k) => k.file === f)) unexplained.push(`${f}:${lineOf(m.index)}`);
  }

  // generic: api3's setENVTruthy, literal and prefix-plus-collection forms
  for (const m of src.matchAll(/setENVTruthy\s*\(\s*['"]([A-Z][A-Z0-9_]*[A-Z0-9])['"]\s*[,)]/g)) {
    add(generic, m[1], `${f}:${lineOf(m.index)}`);
  }
  for (const m of src.matchAll(/setENVTruthy\s*\(\s*['"]([A-Z][A-Z0-9_]*_)['"]\s*\+\s*\w+\.toUpperCase\(\)/g)) {
    const api3 = tree.read('lib/api3/index.js') || '';
    const reg = api3.match(/enabledCollections['"]\s*,\s*\[([^\]]*)\]/);
    const cols = reg ? [...reg[1].matchAll(/['"]([a-z]+)['"]/g)].map((c) => c[1].toUpperCase()) : [];
    if (cols.length === 0) unexplained.push(`${f}:${lineOf(m.index)} (prefix ${m[1]} with no enabledCollections to expand over)`);
    for (const c of cols) add(generic, m[1] + c, `${f}:${lineOf(m.index)} × enabledCollections`);
  }

  // injected: an env object that defaults to process.env, or a local readEnv
  if (/\|\|\s*process\.env\b/.test(src) || /function\s+readEnv\s*\(/.test(src)) {
    const consts = new Map([...src.matchAll(/const\s+([A-Z_]+)\s*=\s*['"]([A-Z][A-Z0-9_]+)['"]/g)].map((m) => [m[1], m[2]]));
    for (const m of src.matchAll(/\breadEnv\s*\(\s*(?:\w+\s*,\s*)?['"]([A-Z][A-Z0-9_]+)['"](?:\s*,\s*['"]([A-Z][A-Z0-9_]+)['"])?/g)) {
      add(injected, m[1], `${f}:${lineOf(m.index)}`);
      if (m[2]) add(injected, m[2], `${f}:${lineOf(m.index)} (fallback)`);
    }
    for (const m of src.matchAll(/\breadInt\s*\(\s*['"]([A-Z][A-Z0-9_]+)['"]/g)) add(injected, m[1], `${f}:${lineOf(m.index)}`);
    for (const m of src.matchAll(/\b(?:source|env)\.([A-Z][A-Z0-9_]+)\b/g)) add(injected, m[1], `${f}:${lineOf(m.index)}`);
    for (const m of src.matchAll(/\b(?:source|env)\[\s*([A-Z][A-Z0-9_]*)\s*\]/g)) {
      if (consts.has(m[1])) add(injected, consts.get(m[1]), `${f}:${lineOf(m.index)} via ${m[1]}`);
      else unexplained.push(`${f}:${lineOf(m.index)} (env[${m[1]}] with no constant to resolve)`);
    }
  }
}

const code = new Set([...union, ...direct.keys(), ...generic.keys(), ...injected.keys()]);

/* --- the report side -------------------------------------------------------- */

function sectionOf (startRe, endRe) {
  const start = SPECTEXT.search(startRe);
  if (start < 0) return null;
  const rest = SPECTEXT.slice(start);
  const end = rest.slice(1).search(endRe);
  return end < 0 ? null : rest.slice(0, end + 1);
}

const b4 = sectionOf(/^#### T — per-tenant/m, /^### B\.5/m);
const b6 = sectionOf(/^### B\.6/m, /^\*\*Done, §B:\*\*/m);
// §B.2 gap 5 classifies the hosted entrypoints' twelve names (all D) in its own
// table rather than in §B.4's D list; the reconciliation counts them in 277.
const gap5 = sectionOf(/^5\. \*\*Twelve variables belonging to the hosted entrypoints/m, /^\s*All twelve are \*\*D\*\*/m);
if (!b4 || !b6 || !gap5) {
  report(NAME, [{ ok: false, text: `could not find §B.4's class lists, §B.2 gap 5's table and §B.6 in ${SPEC}; `
    + 'the report side was not enumerated' }]);
}

const groupProblems = [];
function parseNames (text, label) {
  const out = new Set();
  let stem = null;
  // Ranges first, so their endpoints are not also read as single names.
  const ranged = text.replace(/`([A-Z][A-Z0-9_]*?)(\d+)`\s*…\s*`\1(\d+)`/g, (all, p, a, b) => {
    for (let i = Number(a); i <= Number(b); i += 1) out.add(p + i);
    return ' ';
  });
  for (const m of ranged.matchAll(/`([^`]+)`(\s*\((\d+)\))?/g)) {
    const tok = m[1];
    if (/^[A-Z][A-Z0-9_]*[A-Z0-9]$/.test(tok)) {
      out.add(tok);
      stem = tok.replace(/_[A-Z0-9]+$/, '');
    } else if (/^_[A-Z0-9_]+$/.test(tok) && stem) {
      out.add(stem + tok);
    } else if (/^[A-Z][A-Z0-9_]*_\*$/.test(tok)) {
      const prefix = tok.slice(0, -1);
      const members = [...code].filter((n) => n.startsWith(prefix));
      members.forEach((n) => out.add(n));
      const stated = m[3] ? Number(m[3]) : null;
      if (stated === null || stated !== members.length) {
        groupProblems.push(`${label} ${tok} stated (${stated === null ? 'no count' : stated}), `
          + `expands to ${members.length} code-side name(s)`);
      }
    }
  }
  return out;
}

// Per class, so the headings' totals can be compared with what the lists hold.
const classes = {};
const classRe = /^#### (T|TS|D|B|X) — [^\n]*?\((\d+)\)\s*$/gm;
const heads = [...b4.matchAll(classRe)];
for (let i = 0; i < heads.length; i += 1) {
  const body = b4.slice(heads[i].index, i + 1 < heads.length ? heads[i + 1].index : undefined);
  // The class body ends where the next level-4 heading begins (the "ten" table).
  const own = body.split(/^#### The ten/m)[0];
  // `(+ \`AWS_...\` ..., read directly)` under D is classified but, per the
  // reconciliation, outside the heading's count. Parsed, kept apart.
  const paren = [...own.matchAll(/\(\+ ([^)]*)\)/g)].map((m) => m[1]).join(' ');
  classes[heads[i][1]] = { stated: Number(heads[i][2]),
    names: parseNames(own.replace(/\(\+ [^)]*\)/g, ' '), heads[i][1]),
    extra: parseNames(paren, heads[i][1] + '(+)') };
}
const tenText = (b4.split(/^#### The ten/m)[1]) || '';
const ten = parseNames(tenText, 'ten');
const b6names = parseNames(b6, 'B.6');

const gap5names = parseNames(gap5, 'gap5');
const reportSet = new Set([...Object.values(classes).flatMap((c) => [...c.names, ...c.extra]),
  ...ten, ...b6names, ...gap5names]);

/* --- the document's own numbers, read from the document --------------------- */

const transcript = (SPECTEXT.match(/^`(\{"s1":\d+,"s2":\d+,"s3prefixes":\d+,"s4":\d+,"union":\d+\})`\.?\s*$/m) || [])[1];
const statedTotal = Number((SPECTEXT.match(/= \*\*(\d+)\*\*, of which \d+ are class \*\*X\*\*/) || [])[1]);

/* --- findings ------------------------------------------------------------- */

const measured = { s1: s1.size, s2: s2.size, s3prefixes: s3.size, s4: s4.size, union: union.size };
findings.push({
  ok: s1.size > 0 && s2.size > 0 && s3.size > 0 && s4.size > 0,
  text: `§G.3 sources at ${where}: ${JSON.stringify(measured)} (every source non-empty, so a `
      + 'difference below is a difference, not an empty read)',
});
findings.push({
  ok: transcript === JSON.stringify(measured),
  text: `§G.3 transcript the document quotes: ${transcript || '(not found)'} — `
      + (transcript === JSON.stringify(measured) ? 'reproduced' : `NOT reproduced at ${where}`),
});
findings.push({
  ok: direct.size > 0 && generic.size > 0 && injected.size > 0,
  text: `§B.2 entry points parsed from code: direct ${direct.size}, generic ${generic.size}, `
      + `injected ${injected.size}; code-side surface ${code.size} (union ${union.size} + `
      + `${code.size - union.size} the union cannot see: `
      + `${[...code].filter((n) => !union.has(n)).sort().join(' ')})`,
});
findings.push({
  ok: unexplained.length === 0,
  text: `dynamic process.env[...] / env[...] reads outside env.js not explained by a parsed reader: `
      + (unexplained.length ? unexplained.join(', ') : 'none')
      + ` (known readers: ${KNOWN_DYNAMIC.map((k) => `${k.file} ${k.why}`).join('; ')})`,
});

const classSummary = Object.entries(classes)
  .map(([k, c]) => `${k} ${c.names.size}/${c.stated}${c.extra.size ? ` (+${c.extra.size})` : ''}`).join(', ');
const classesOk = ['T', 'TS', 'D', 'B', 'X'].every((k) => classes[k]);
findings.push({
  ok: classesOk && Object.values(classes).every((c) => c.names.size > 0) && ten.size > 0 && gap5names.size > 0,
  text: `report side parsed from §B.4, §B.2 gap 5 and §B.6: classes (parsed/heading) ${classSummary}; `
      + `ten-table ${ten.size}; gap 5 ${gap5names.size}; B.6 ${b6names.size}; distinct ${reportSet.size}`,
});
findings.push({
  ok: classesOk && Object.values(classes).every((c) => c.names.size === c.stated),
  text: 'every class heading\'s count equals the names its list holds (the document says its group '
      + 'counts are hand-expansions; this is where they stop being trusted)',
});
findings.push({
  ok: groupProblems.length === 0,
  text: `abbreviated groups whose stated count matches their expansion against the code: `
      + (groupProblems.length ? `MISMATCH — ${groupProblems.join('; ')}` : 'all'),
});

// A name in two classes would be counted twice by the headings and once here.
const seen = new Map();
for (const [k, c] of Object.entries(classes)) for (const n of [...c.names, ...c.extra]) seen.set(n, (seen.get(n) || []).concat(k));
const twice = [...seen].filter(([, ks]) => ks.length > 1).map(([n, ks]) => `${n} (${ks.join('+')})`);
findings.push({
  ok: twice.length === 0,
  text: `names classified in more than one class: ${twice.length ? twice.join(', ') : 'none'}`,
});

const reportOnly = [...reportSet].filter((n) => !code.has(n)).sort();
const codeOnly = [...code].filter((n) => !reportSet.has(n)).sort();
const site = (n) => direct.get(n) || generic.get(n) || injected.get(n)
  || (s2.has(n) ? 'lib/server/env.js' : s1.has(n) ? 'lib/settings.js' : 'README.md');
findings.push({
  ok: reportOnly.length === 0,
  text: `names the report classifies that the code does not read or document: ${reportOnly.length}`
      + (reportOnly.length ? ` — ${reportOnly.join(' ')}` : ''),
});
findings.push({
  ok: codeOnly.length === 0,
  text: `names the code reads or documents that the report does not classify: ${codeOnly.length}`
      + (codeOnly.length ? ` — ${codeOnly.map((n) => `${n} (${site(n)})`).join(' ')}` : ''),
});
findings.push({
  ok: statedTotal === reportSet.size && statedTotal === code.size,
  text: `stated surface total ${statedTotal || '(not found)'} vs report ${reportSet.size} vs code ${code.size}`,
});

report(`${NAME} at ${where}`, findings);
