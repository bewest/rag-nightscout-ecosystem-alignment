#!/usr/bin/env node
'use strict';

/*
 * connector-pin-agreement-gate.js
 *
 * Fail when cgm-remote-monitor's branches disagree about how they depend on
 * nightscout-connect.
 *
 * The defect this guards against is not a bad pin. It is a SET of branches
 * that each pin something defensible while the set as a whole is incoherent:
 * four pin values, two spec shapes, three `overrides` states, and three
 * different code trees all reporting `nightscout-connect@0.0.13` to `npm ls`.
 * No single-branch check can see that, so this gate takes the whole set.
 *
 *   node tools/qc/connector-pin-agreement-gate.js \
 *        --repo <cgm-remote-monitor path> \
 *        --ref origin/master --ref origin/dev [--ref ...] \
 *        [--connect-repo <nightscout-connect path>]  enables R6
 *        [--package nightscout-connect]              default
 *        [--baseline <file>]                         accept a recorded skew
 *        [--json]
 *
 * Read-only: every fact comes from `git show <ref>:<file>`. The gate never
 * writes to, checks out, or fetches in either repository.
 *
 * Exit codes: 0 all rules pass, 1 at least one rule fails, 2 usage/environment.
 *
 * RULES (each fires independently; each has a break-it test in
 * docs/40-migration/connector-pin-consolidation-2026-09-15.md section F)
 *
 *   R1 SHAPE       every ref declares the dependency in the same shape
 *                  (npm-range | tag-tarball | commit-tarball | git-shorthand)
 *   R2 NAMEABLE    every pin carries a name a human can put in release notes.
 *                  A bare-commit tarball does not.
 *   R3 LOCK-AGREE  package.json spec == lockfile root spec == lockfile
 *                  `resolved` for that ref
 *   R4 VERSION-1-1 across the ref set, one reported `version` maps to exactly
 *                  one `resolved` URL and vice versa
 *   R5 OVERRIDES   `overrides[<package>]` is identical across refs (or absent
 *                  from all of them)
 *   R6 ORDERED     the pinned commits are totally ordered by ancestry, so the
 *                  set has a newest member that contains all the others.
 *                  SKIPPED, not passed, without --connect-repo.
 */

const { execFileSync } = require('child_process');
const fs = require('fs');

// ---------------------------------------------------------------- arguments

function parseArgs (argv) {
  const out = { repo: process.cwd(), refs: [], connectRepo: null,
                pkg: 'nightscout-connect', baseline: null, json: false,
                allowSkip: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--repo') out.repo = argv[++i];
    else if (a === '--ref') out.refs.push(argv[++i]);
    else if (a === '--connect-repo') out.connectRepo = argv[++i];
    else if (a === '--package') out.pkg = argv[++i];
    else if (a === '--baseline') out.baseline = argv[++i];
    else if (a === '--allow-skip') out.allowSkip = true;
    else if (a === '--json') out.json = true;
    else { console.error('unknown argument: ' + a); process.exit(2); }
  }
  if (out.refs.length < 2) {
    console.error('need at least two --ref values; the gate compares a SET');
    process.exit(2);
  }
  return out;
}

const args = parseArgs(process.argv);

function git (repo, ...a) {
  return execFileSync('git', ['-C', repo, ...a],
                      { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
}
function gitShow (repo, ref, file) {
  try { return git(repo, 'show', ref + ':' + file); } catch (e) { return null; }
}
function isAncestor (repo, a, b) {
  try { git(repo, 'merge-base', '--is-ancestor', a, b); return true; }
  catch (e) { return false; }
}

// ------------------------------------------------------------ spec grammar

const GH_TAG = /^https:\/\/github\.com\/([^/]+)\/([^/]+)\/archive\/refs\/tags\/(.+)\.tar\.gz$/;
const GH_SHA = /^https:\/\/github\.com\/([^/]+)\/([^/]+)\/archive\/([0-9a-f]{7,40})\.tar\.gz$/;
const GH_SHORT = /^(github:|git\+|git:)/;

function classify (spec) {
  if (spec === null || spec === undefined) return { shape: 'absent', name: null, commitish: null };
  let m = GH_TAG.exec(spec);
  if (m) return { shape: 'tag-tarball', name: m[3], commitish: m[3] };
  m = GH_SHA.exec(spec);
  if (m) return { shape: 'commit-tarball', name: null, commitish: m[3] };
  if (GH_SHORT.test(spec)) {
    const hash = spec.indexOf('#');
    const c = hash >= 0 ? spec.slice(hash + 1) : null;
    return { shape: 'git-shorthand', name: c, commitish: c };
  }
  if (/^https?:/.test(spec) || /^file:/.test(spec)) return { shape: 'other-url', name: null, commitish: null };
  return { shape: 'npm-range', name: spec, commitish: null };
}

// ------------------------------------------------------------- observation

function observe (ref) {
  const pjText = gitShow(args.repo, ref, 'package.json');
  if (pjText === null) { console.error('cannot read package.json at ' + ref); process.exit(2); }
  const pj = JSON.parse(pjText);
  const spec = (pj.dependencies || {})[args.pkg]
            || (pj.devDependencies || {})[args.pkg] || null;
  const override = (pj.overrides || {})[args.pkg];

  const lkText = gitShow(args.repo, ref, 'package-lock.json');
  let lockRootSpec = null, lockResolved = null, lockVersion = null, lockIntegrity = null, lockSeen = false;
  if (lkText !== null) {
    lockSeen = true;
    const lk = JSON.parse(lkText);
    const root = (lk.packages || {})[''];
    if (root) lockRootSpec = (root.dependencies || {})[args.pkg]
                          || (root.devDependencies || {})[args.pkg] || null;
    const entry = (lk.packages || {})['node_modules/' + args.pkg]
               || (lk.dependencies || {})[args.pkg] || null;
    if (entry) {
      lockResolved = entry.resolved || null;
      lockVersion = entry.version || null;
      lockIntegrity = entry.integrity || null;
    }
  }
  return { ref, spec, ...classify(spec), override: override === undefined ? null : override,
           lockSeen, lockRootSpec, lockResolved, lockVersion, lockIntegrity };
}

const obs = args.refs.map(observe);

// ------------------------------------------------------------------- rules

const results = [];
function rule (id, title, ok, detail, skipped) {
  results.push({ id, title, status: skipped ? 'SKIP' : (ok ? 'PASS' : 'FAIL'), detail });
}
const uniq = a => [...new Set(a)];
const J = v => JSON.stringify(v);

// R1 SHAPE
{
  const shapes = uniq(obs.map(o => o.shape));
  rule('R1', 'all refs declare ' + args.pkg + ' in the same shape', shapes.length === 1,
       shapes.length === 1 ? 'all ' + shapes[0]
         : obs.map(o => '  ' + o.ref + ' : ' + o.shape).join('\n'));
}

// R2 NAMEABLE
{
  const bad = obs.filter(o => o.shape === 'commit-tarball'
                           || (o.shape === 'git-shorthand' && /^[0-9a-f]{7,40}$/.test(o.commitish || ''))
                           || o.shape === 'absent' || o.shape === 'other-url');
  rule('R2', 'every pin names a version a release note can cite', bad.length === 0,
       bad.length === 0 ? 'all pins nameable'
         : bad.map(o => '  ' + o.ref + ' : ' + o.shape + ' -> '
                        + (o.commitish || '(none)') + ' has no version name').join('\n'));
}

// R3 LOCK-AGREE
{
  const bad = [];
  for (const o of obs) {
    if (!o.lockSeen) { bad.push('  ' + o.ref + ' : no package-lock.json'); continue; }
    if (o.lockRootSpec !== o.spec) { bad.push('  ' + o.ref + ' : package.json ' + J(o.spec) + ' != lock root ' + J(o.lockRootSpec)); continue; }
    // `resolved` echoes the spec only for URL specs; for an npm range npm
    // writes the registry tarball instead, which is not a disagreement.
    const urlSpec = o.shape === 'tag-tarball' || o.shape === 'commit-tarball' || o.shape === 'other-url';
    if (urlSpec && o.lockResolved !== o.spec) bad.push('  ' + o.ref + ' : spec ' + J(o.spec) + ' != lock resolved ' + J(o.lockResolved));
  }
  rule('R3', 'each ref\'s lockfile agrees with its own package.json', bad.length === 0,
       bad.length === 0 ? 'lock and manifest agree on every ref' : bad.join('\n'));
}

// R4 VERSION-1-1
{
  const byVersion = new Map();
  for (const o of obs) {
    if (!o.lockVersion) continue;
    if (!byVersion.has(o.lockVersion)) byVersion.set(o.lockVersion, new Map());
    byVersion.get(o.lockVersion).set(o.lockResolved, (byVersion.get(o.lockVersion).get(o.lockResolved) || []).concat(o.ref));
  }
  const bad = [];
  for (const [v, m] of byVersion) {
    if (m.size > 1) {
      bad.push('  version ' + J(v) + ' is reported by ' + m.size + ' different trees:');
      for (const [r, refs] of m) bad.push('    ' + r + '   <- ' + refs.join(', '));
    }
  }
  rule('R4', 'one reported version maps to exactly one tree', bad.length === 0,
       bad.length === 0 ? 'version strings are one-to-one with resolved trees' : bad.join('\n'));
}

// R5 OVERRIDES
{
  const vals = uniq(obs.map(o => J(o.override)));
  rule('R5', 'overrides[' + args.pkg + '] is identical across refs', vals.length === 1,
       vals.length === 1 ? 'all ' + vals[0]
         : obs.map(o => '  ' + o.ref + ' : ' + J(o.override)).join('\n'));
}

// R6 ORDERED
{
  if (!args.connectRepo) {
    rule('R6', 'pinned commits are totally ordered by ancestry', false,
         'SKIPPED: --connect-repo not supplied. A skipped rule is not a passed\n'
         + 'rule; pass --allow-skip to accept that deliberately.', true);
  } else {
    const pinned = [];
    for (const o of obs) {
      if (!o.commitish) continue;
      let sha;
      try { sha = git(args.connectRepo, 'rev-parse', o.commitish + '^{commit}').trim(); }
      catch (e) { pinned.push({ ref: o.ref, commitish: o.commitish, sha: null }); continue; }
      pinned.push({ ref: o.ref, commitish: o.commitish, sha });
    }
    const unresolved = pinned.filter(p => !p.sha);
    const bad = unresolved.map(p => '  ' + p.ref + ' : ' + p.commitish + ' not found in the connector repository');
    const ok = pinned.filter(p => p.sha);
    for (let i = 0; i < ok.length; i++) {
      for (let j = i + 1; j < ok.length; j++) {
        const a = ok[i], b = ok[j];
        if (a.sha === b.sha) continue;
        if (!isAncestor(args.connectRepo, a.sha, b.sha) && !isAncestor(args.connectRepo, b.sha, a.sha)) {
          bad.push('  INCOMPARABLE: ' + a.ref + ' (' + a.commitish + ') and '
                   + b.ref + ' (' + b.commitish + ') -- neither contains the other');
        }
      }
    }
    rule('R6', 'pinned commits are totally ordered by ancestry', bad.length === 0,
         bad.length === 0 ? 'every pin is an ancestor-or-equal of the newest' : bad.join('\n'));
  }
}

// ------------------------------------------------------------------ verdict

const failed = results.filter(r => r.status === 'FAIL');
const skipped = results.filter(r => r.status === 'SKIP');

if (args.json) {
  console.log(JSON.stringify({ package: args.pkg, refs: obs, rules: results,
                               verdict: failed.length ? 'FAIL' : 'PASS' }, null, 2));
} else {
  console.log('connector pin agreement gate -- package ' + args.pkg);
  console.log('repo ' + args.repo);
  console.log('');
  const w = Math.max(...obs.map(o => o.ref.length));
  for (const o of obs) {
    console.log('  ' + o.ref.padEnd(w) + '  ' + o.shape.padEnd(15)
                + '  name=' + String(o.name).padEnd(10)
                + '  lockVersion=' + String(o.lockVersion));
  }
  console.log('');
  for (const r of results) {
    console.log('[' + r.status + '] ' + r.id + ' ' + r.title);
    if (r.status !== 'PASS') console.log(r.detail.split('\n').map(l => '     ' + l).join('\n'));
  }
  console.log('');
  console.log('VERDICT: ' + (failed.length ? 'FAIL (' + failed.length + ' rule(s))'
              : (skipped.length && !args.allowSkip ? 'INCOMPLETE (' + skipped.length + ' rule(s) did not run)' : 'PASS'))
              + (skipped.length && args.allowSkip ? ' (' + skipped.length + ' skipped, allowed)' : ''));
}
// A rule that did not run has not passed. Exiting 0 on a skip is how a gate
// goes vacuous, so a skip fails unless the caller opts into it explicitly.
process.exit(failed.length ? 1 : ((skipped.length && !args.allowSkip) ? 3 : 0));
