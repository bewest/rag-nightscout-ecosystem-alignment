'use strict';
/*
 * boot-requires-runtime-deps.js — BF-176.
 *
 * Every package that lib/server/bootevent.js loads must be declared under
 * `dependencies` in package.json at the ref under test. A production install
 * (`npm ci --omit=dev`, or the Dockerfile's `npm prune --omit=dev`) keeps only
 * runtime dependencies and what they pull in; a package that is declared only
 * under devDependencies is present there by luck, as a transitive dependency
 * of something else, or not at all.
 *
 * On v15.0.9 and dev 04d435eb axios is a devDependency that arrives hoisted
 * from minimed-connect-to-nightscout; cut 1 (#8828, 806ff2f0) removes that
 * package and the server then exits at augmentSettings when IMPORT_CONFIG is
 * set. This gate measures the declaration, which is the cause, not the
 * transitive luck.
 *
 *   BOOT_DEPS_REF=<ref> node tools/queue/gates/boot-requires-runtime-deps.js
 *
 * Reads with `git show` only.
 */

const { builtinModules } = require('module');
const { show, report } = require('./_gate');

const ref = process.env.BOOT_DEPS_REF || 'official/dev';
const findings = [];

const pkgText = show(ref, 'package.json');
const boot = show(ref, 'lib/server/bootevent.js');
if (pkgText === null || boot === null) {
  findings.push({ ok: false, text: `${ref}: package.json or lib/server/bootevent.js not readable` });
  report('boot-requires-runtime-deps', findings);
}

const pkg = JSON.parse(pkgText);
const deps = pkg.dependencies || {};
const devDeps = pkg.devDependencies || {};

const names = new Set();
for (const m of boot.matchAll(/require\(\s*['"]([^'"]+)['"]\s*\)/g)) {
  const id = m[1].replace(/^node:/, '');
  if (id.startsWith('.') || builtinModules.includes(id.split('/')[0])) continue;
  names.add(id.startsWith('@') ? id.split('/').slice(0, 2).join('/') : id.split('/')[0]);
}

if (!names.has('axios')) {
  // The property this gate exists for is about axios; if bootevent.js stops
  // loading it, the gate must be re-read, not silently pass on the rest.
  findings.push({ ok: false, text: `${ref}: lib/server/bootevent.js no longer requires axios; re-read BF-176` });
}

for (const name of [...names].sort()) {
  if (deps[name]) {
    findings.push({ ok: true, text: `${ref}: ${name} is in dependencies (${deps[name]})` });
  } else if (devDeps[name]) {
    findings.push({ ok: false, text: `${ref}: ${name} is loaded by bootevent.js but declared only in devDependencies (${devDeps[name]})` });
  } else {
    findings.push({ ok: false, text: `${ref}: ${name} is loaded by bootevent.js but not declared` });
  }
}

report('boot-requires-runtime-deps', findings);
