'use strict';
/*
 * doc-links.js — DOC-LINKS
 *
 * Every path this programme's documents and tooling cite must resolve to a
 * file that exists.
 *
 * WHY THIS GATE EXISTS. On 2026-09-16 the September material was moved into
 * programme subdirectories (remedial / modernization / tenancy / platform) and
 * every reference was rewritten programmatically. The rewrite reported 280
 * links and 212 paths repaired and looked complete. It was not. Three classes
 * of reference survived it, and none of the existing checks saw any of them:
 *
 *   1. PIECEWISE CONSTRUCTION. Four gates built their target with
 *      `path.join(REPO_ROOT, 'docs', '30-design', 'nightscout-backfix-register.md')`.
 *      A full-path string replace cannot match a path that is never spelled as
 *      a string. Three of those four gates were ALREADY EXPECTED TO FAIL — they
 *      are docs-truth items — so the ENOENT was invisible inside a red that
 *      the summary line said was supposed to be red.
 *   2. A LINK THAT IS NOT A LINK. ``(`../../60-research/x.md` §3)`` is a
 *      backticked path inside parentheses, so `](...)` never matched it.
 *   3. A MARKDOWN LINK INSIDE A NON-MARKDOWN FILE — a `[E2](../60-research/…)`
 *      embedded in a Python edit script.
 *
 * That is the register's own read-or-run rule applied to a refactor: the
 * rewrite was a hypothesis about what a reference looks like, and it was wrong
 * in three ways. This gate is the reproduction.
 *
 * WHAT IT DOES NOT COVER, deliberately. The legacy tree — the Jan-Apr research
 * campaign in `docs/60-research/*.md`, `docs/backlogs/archive/`, `specs/` —
 * carries 109 dead links that predate this work and that the maintainer chose
 * to leave alone. Gating them would mean this gate is red forever for reasons
 * nobody intends to fix, which is how a gate stops being read. The scope below
 * is the groomed material plus the live tooling, and the legacy count is
 * printed rather than enforced, so that leaving it alone stays a decision
 * somebody can see rather than an omission.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { REPO_ROOT, report } = require('./_gate');

// ---------------------------------------------------------------------------
// Scope: the groomed programme material, plus every tool that reads it.
// ---------------------------------------------------------------------------
const SCOPE = [
  'docs/00-overview',
  'docs/30-design',
  'docs/40-migration',
  'docs/60-research/remedial',
  'docs/60-research/modernization',
  'docs/60-research/tenancy',
  'docs/60-research/programme',
  'docs/reports/nightscout-release-planning-2026-09',
  'queue',
  'releases',
  'reports',
  'tools/queue',
];
const SCOPE_FILES = ['README.md', 'Makefile'];

// Frozen records. Each one is evidence OF a past action, so editing it to keep
// its paths current would destroy the thing it is evidence of. Excluding them
// is the same judgement the rewrite made when it left them alone.
const FROZEN = [
  ['tools/qc/cgm-ingestion-evidence/harnesses/',
   'one-shot edit scripts and a manifest snapshot; they record what WAS done'],
];

// Paths that are deliberately not real.
const NOT_REAL = new Map([
  ['docs/60-research/something.md',
   'the worked example in queue/README.md and the manifest field reference'],
]);

// PLANNED: a path that names something not yet created, ON PURPOSE. These are
// not broken citations and must not be reported as such - the distinction is
// the whole point of the gate. Each is a DECLARED OUTPUT (a file some command
// or procedure produces when it is run) or a DELIVERABLE a queue item exists
// to produce. A gate that called these dead would be telling a reader that
// not-started work is a documentation defect.
//
// The rule for adding one: it must be named by an item in the queue, or by a
// Make target, that WOULD create it. If nothing would create it, it is dead.
// QUOTED: one document quoting a path AS IT WAS, where the quotation is the
// evidence. Keyed by `file::target` rather than by file, so the exemption
// covers exactly the one citation and every other path in that document stays
// enforced. Each entry names the correction the document itself carries -
// without that, this map is just a suppression, and the register's suppression
// audit is the reason this project distrusts those.
const QUOTED = new Map([
  // THIS FILE quotes the pre-move spellings in its own header, as the record of
  // what the 2026-09-16 rewrite missed. It could not see itself until it was
  // committed - `tracked()` reads `git ls-files`, so an untracked gate is
  // invisible to its own scan, and this gate ran green three times before the
  // commit made it visible and it immediately flagged its own documentation.
  // Worth knowing generally: a gate that scans tracked files cannot self-check
  // until it is tracked.
  ['tools/queue/gates/doc-links.js::docs/30-design/nightscout-backfix-register.md',
   'the header quotes the pre-move path.join segments that broke four gates'],
  ['tools/queue/gates/doc-links.js::docs/60-research/tenant-config-surface-2026-09-15.md',
   'the PLANNED and QUOTED entries name the pre-move spelling to explain the exemption'],
  ['docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md::docs/60-research/tenant-config-surface-2026-09-15.md',
   'E3 quotes the gate command as it ran during the audit. The document carries a '
   + 'dated "Path note, 2026-09-16" giving the current spelling. Rewriting the '
   + 'quotation would alter the record of what was measured.'],
]);

const PLANNED = new Map([
  ['docs/60-research/tenancy/tenant-config-surface-2026-09-15.md',
   'T30-RESEARCH\'s deliverable; its gate is `test -f`, so the item is not-started '
   + 'BY MEASUREMENT. NOTE for whoever takes T30-RESEARCH: a 122 KB '
   + 'docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md exists and may '
   + 'already BE this deliverable under another name. Not assumed here - deciding '
   + 'that is the item\'s work, not this gate\'s.'],
  ['docs/60-research/seam-tips-pre-R5.txt',
   'post-phase0-roadmap L477 tells an operator to CREATE this with git for-each-ref '
   + 'before the R5 rebase, as the rollback record. Absent until that rebase starts.'],
  ['reports/schema-census/impact-smoke.json',
   'the declared --out of `make schema-impact-smoke` (Makefile L761-763).'],
]);

// `externals/` is git-ignored by design (README, "Directory Structure"), so a
// reference into it is a reference to a checkout that may or may not be on
// this disk. Its presence is `make bootstrap`'s business, not this gate's.
const NOT_CHECKED_PREFIX = ['externals/'];

const TEXT_EXT = new Set(['.md', '.yaml', '.yml', '.js', '.py', '.json',
                          '.txt', '.sh', '.tsv', '.csv', '.mjs']);

const CITED_EXT = 'md|js|py|json|yaml|yml|tsv|csv|txt|sh|mjs';

// Only THIS repository's documentation and evidence surface. `tools/`,
// `workflows/`, `specs/` and friends are deliberately absent: a string like
// `workflows/main.yml` in these documents overwhelmingly names a file inside
// the SHIPPING checkout (cgm-remote-monitor's `.github/workflows/main.yml`),
// not a path here, and a gate that cannot tell those apart reports other
// repositories' files as this repository's dead links. That is a gate whose
// output a reader learns to skim, which is worse than no gate.
const ROOT_DIRS = 'docs|reports|releases|queue';

// The leading lookbehind is load-bearing. With `\\b` instead, this pattern
// matched the TAIL of a longer path: `tools/queue/gates/x.js` contains
// `queue/gates/x.js`, which does not exist at the repository root, and the
// first run of this gate reported 289 failures of which ~250 were that. A
// gate's own false positives are the fastest way to make it unreadable.
const ROOT_PATH = new RegExp(
  `(?<![A-Za-z0-9._/-])(?:${ROOT_DIRS})/[A-Za-z0-9._/-]+\\.(?:${CITED_EXT})\\b`, 'g');
const MD_LINK = /\]\(\s*<?([^)\s>]+?)>?\s*\)/g;

// A path that is never spelled as a string. This is failure class 1 from the
// header, and neither of the passes above can see it: `path.join(REPO_ROOT,
// 'docs', '30-design', 'x.md')` contains no substring that looks like a path.
// Four gates were broken this way by the 2026-09-16 move and three of them hid
// inside an expected red. Reconstructing the argument list is the only way to
// measure it.
const PATH_JOIN = /path\.join\(\s*REPO_ROOT\s*,\s*((?:'[^']*'\s*,\s*)*'[^']*')\s*\)/g;
const STRING_ARG = /'([^']*)'/g;

// ---------------------------------------------------------------------------

function tracked() {
  const out = execFileSync('git', ['-C', REPO_ROOT, 'ls-files'],
                           { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  return out.split('\n').filter(Boolean);
}

function inScope(f) {
  if (FROZEN.some(([prefix]) => f.startsWith(prefix))) return false;
  if (SCOPE_FILES.includes(f)) return true;
  return SCOPE.some((d) => f === d || f.startsWith(d + '/'));
}

function skipTarget(t) {
  if (!t) return true;
  if (t.includes('://') || t.startsWith('#') || t.startsWith('mailto:')
      || t.startsWith('tel:')) return true;
  // Regex literals, format strings and template placeholders read as paths.
  if (/[[\]{}$<>*+\\|]/.test(t)) return true;
  // An elided path in prose - "nightscout-multitenancy-execution-plan-...md",
  // or the same with a typographic ellipsis - is an abbreviation, not a
  // citation.
  if (t.includes('...') || t.includes('\u2026')) return true;
  // A reference into the git-ignored externals tree, in any spelling. The
  // prefix test below cannot see this one, because `../../externals/x` inside
  // `docs/60-research/tenancy/` normalises to `docs/externals/x`.
  if (/(^|\/)externals\//.test(t)) return true;
  return false;
}

// The first two path segments, which is the granularity at which the two
// repositories' `docs/` trees differ.
function topTwo(rel) {
  const parts = rel.split('/');
  return parts.length <= 2 ? rel : parts.slice(0, 2).join('/');
}

function exists(rel) {
  try {
    fs.statSync(path.join(REPO_ROOT, rel));
    return true;
  } catch (e) {
    return false;
  }
}

const files = tracked().filter(inScope);
const dead = [];
let refsChecked = 0;
let filesWithRefs = 0;
let foreign = 0;
let planned = 0;
let quoted = 0;
const perScope = new Map();

for (const f of files) {
  if (!TEXT_EXT.has(path.extname(f)) && f !== 'Makefile') continue;
  let src;
  try {
    src = fs.readFileSync(path.join(REPO_ROOT, f), 'utf8');
  } catch (e) {
    continue;
  }
  const dir = path.dirname(f);
  let n = 0;

  const check = (target, kind) => {
    if (skipTarget(target)) return;
    const bare = target.split('#')[0];
    if (!bare) return;
    const asRoot = path.normalize(bare);
    const asRel = path.normalize(path.join(dir, bare));
    if (NOT_REAL.has(asRoot) || NOT_REAL.has(asRel)) return;
    if (PLANNED.has(asRoot) || PLANNED.has(asRel)) { planned += 1; return; }
    if (QUOTED.has(`${f}::${asRoot}`) || QUOTED.has(`${f}::${asRel}`)) {
      quoted += 1;
      return;
    }
    if (NOT_CHECKED_PREFIX.some((p) => asRoot.startsWith(p) || asRel.startsWith(p))) return;
    // BOTH REPOSITORIES HAVE A `docs/`. `docs/meta/architecture-overview.md`,
    // `docs/INDEX.md` and `docs/proposals/api-query-normalization.md` are real
    // files -- in cgm-remote-monitor, which is what these documents are ABOUT.
    // `docs/runtime-upgrade.md` is real on cut 1's branch. Measured against
    // origin/dev, origin/master and chore/nightscout-modernization; the first
    // run of this gate called all four dead and it was wrong about all four.
    //
    // So a root-path reference is enforced only when its first two segments
    // name something that exists HERE. A reference into a subtree this
    // repository does not have is another repository's path, and this gate
    // has no standing to call it broken. The count is printed, not enforced.
    if ((kind === 'root-path' || kind === 'path.join') && !exists(topTwo(asRoot))) {
      foreign += 1;
      return;
    }
    n += 1;
    refsChecked += 1;
    if (exists(asRel) || exists(asRoot)) return;
    dead.push({ file: f, target: bare, kind });
  };

  // (A) markdown links — in EVERY scoped text file, not only .md, because a
  // markdown link embedded in a script is exactly what was missed once.
  let m;
  MD_LINK.lastIndex = 0;
  while ((m = MD_LINK.exec(src)) !== null) check(m[1], 'md-link');

  // (B) repo-root-absolute paths anywhere in the text, which catches the
  // backticked citation, the YAML evidence list and the Makefile alike.
  ROOT_PATH.lastIndex = 0;
  while ((m = ROOT_PATH.exec(src)) !== null) check(m[0], 'root-path');

  // (C) piecewise path.join(REPO_ROOT, 'a', 'b', 'c.md') in gate sources.
  if (path.extname(f) === '.js') {
    PATH_JOIN.lastIndex = 0;
    while ((m = PATH_JOIN.exec(src)) !== null) {
      const segs = [];
      STRING_ARG.lastIndex = 0;
      let a;
      while ((a = STRING_ARG.exec(m[1])) !== null) segs.push(a[1]);
      if (!segs.length) continue;
      // Only paths, not directory handles: a trailing segment with no
      // extension is a directory this gate has no expectation about.
      if (!path.extname(segs[segs.length - 1])) continue;
      check(segs.join('/'), 'path.join');
    }
  }

  if (n > 0) {
    filesWithRefs += 1;
    const bucket = SCOPE.find((d) => f.startsWith(d + '/')) || path.dirname(f);
    perScope.set(bucket, (perScope.get(bucket) || 0) + n);
  }
}

// ---------------------------------------------------------------------------
// Findings. The per-scope counts are printed on a PASS as well as a fail, so a
// reader can tell a gate that examined 900 references and liked them all from
// a gate whose scope silently stopped matching anything.
// ---------------------------------------------------------------------------
const findings = [];

findings.push({
  ok: files.length > 0,
  text: `scope resolves to ${files.length} tracked files across ${SCOPE.length} roots`,
});

for (const [bucket, n] of [...perScope].sort()) {
  findings.push({ ok: true, text: `${bucket}: ${n} references` });
}

findings.push({
  ok: refsChecked > 0,
  text: `${refsChecked} references checked in ${filesWithRefs} files`,
});

findings.push({
  ok: true,
  text: `${foreign} root-path references name a subtree this repository does not `
      + 'have (cgm-remote-monitor\'s own docs/); counted, not enforced',
});

for (const d of dead) {
  findings.push({ ok: false, text: `${d.file} -> ${d.target}  (${d.kind})` });
}

findings.push({
  ok: true,
  text: `${planned} references name a PLANNED output or deliverable, listed with a reason`,
});
for (const [target, why] of PLANNED) {
  findings.push({ ok: true, text: `planned: ${target} - ${why}` });
}

findings.push({
  ok: true,
  text: `${quoted} references are HISTORICAL QUOTATIONS, exempt per file+target with a reason`,
});
for (const [key, why] of QUOTED) {
  findings.push({ ok: true, text: `quoted: ${key.split('::')[1]} - ${why}` });
}

for (const [prefix, why] of FROZEN) {
  findings.push({ ok: true, text: `excluded (frozen record): ${prefix} - ${why}` });
}

report('doc-links (DOC-LINKS)', findings);
