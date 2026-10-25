'use strict';
/*
 * runtime-requires-declared.js — BF-176.
 *
 * Every package that server code loads must be declared under `dependencies`
 * in package.json. A production install (`npm ci --omit=dev`, the Dockerfile's
 * `npm prune --omit=dev --omit=optional`, Azure's `npm install --production`)
 * keeps only runtime dependencies and what they pull in. A package declared
 * only under devDependencies, or not at all, is there by luck: as a transitive
 * dependency of something else, or not at all. On v15.0.9 axios (a
 * devDependency, loaded by lib/server/bootevent.js for IMPORT_CONFIG) and
 * lodash (undeclared, loaded by lib/utils.js) are both supplied that way, and
 * cut 1 (#8828, 806ff2f0) removes the package that supplied axios. Cut 1 is
 * merged to dev at eb72a1d3 (2026-10-25, 16.0.0), where a production install
 * with IMPORT_CONFIG set exits at boot with "Cannot find module 'axios'".
 *
 * WHAT COUNTS AS SERVER CODE. The server starts as `node lib/server/server.js`
 * (Procfile, `npm start`, package.json `main`, the Dockerfile's CMD). The rule:
 *
 *   server.js, bin/*.js, and lib/**\/*.js except lib/client/**,
 *   lib/report/** and lib/report_plugins/**
 *
 * The three excluded directories are browser code: nothing outside them
 * requires them except bundle/*.source.js, which webpack builds into
 * node_modules/.cache (read on dev 04d435eb). Everything else under lib/ is
 * scanned even where only part of it is reached by the server (for example
 * lib/admin_plugins, which the bundle also loads), which errs strict.
 * bundle/ and webpack/ are build inputs and are not scanned.
 *
 * WHAT IS CHECKED. Each `require('<id>')` with a literal id. node: and builtin
 * modules and relative or absolute paths are skipped; a subpath resolves to its
 * package (lodash/escape -> lodash, @scope/pkg/x -> @scope/pkg). Each package
 * must be under dependencies: under devDependencies only, or absent, is BAD.
 *
 * THE ALLOWLIST, and why it is safe. lib/server/app.js loads webpack,
 * webpack-dev-middleware and webpack-hot-middleware only inside
 * `if (process.env.NODE_ENV === 'development') {` (the live-rebuild mode for
 * developers; guard at :334, requires at :343 and :353 on dev 04d435eb; on cut
 * 2 ee94b148 the guard is at :333 and webpack is required at :340). The two
 * middlewares are devDependencies everywhere; cut 2 (#8837) moves webpack to
 * devDependencies too, where dev still lists it under dependencies. Each is
 * allowed ONLY in that file and ONLY on a line inside a block opened by that
 * guard; a require of any of the three anywhere else is BAD, whichever list
 * declares it. The block is found by counting braces from the guard line,
 * which ignores braces inside strings and comments;
 * runtime-requires-declared-control.sh checks that a webpack-hot-middleware or
 * webpack require appended outside the block goes red.
 *
 *   RUNTIME_REQUIRES_REF=<ref>  node tools/queue/gates/runtime-requires-declared.js
 *   RUNTIME_REQUIRES_TREE=<dir> node tools/queue/gates/runtime-requires-declared.js
 *
 * The ref form reads with `git show` only. The tree form reads a directory
 * (for the guard control, which mutates a scratch copy, never a worktree).
 */

const fs = require('fs');
const path = require('path');
const { builtinModules } = require('module');
const { show, git, report } = require('./_gate');

const TREE = process.env.RUNTIME_REQUIRES_TREE || null;
const REF = process.env.RUNTIME_REQUIRES_REF || 'official/dev';
const label = TREE ? 'tree' : REF;

const ALLOW = {
  webpack: 'lib/server/app.js',
  'webpack-dev-middleware': 'lib/server/app.js',
  'webpack-hot-middleware': 'lib/server/app.js',
};
const GUARD = /if\s*\(\s*process\.env\.NODE_ENV\s*===\s*['"]development['"]\s*\)\s*\{/;

function listFiles() {
  if (TREE) {
    const out = [];
    (function walk(rel) {
      for (const f of fs.readdirSync(path.join(TREE, rel))) {
        const r = rel ? rel + '/' + f : f;
        if (fs.statSync(path.join(TREE, r)).isDirectory()) walk(r);
        else out.push(r);
      }
    })('');
    return out;
  }
  return git(['ls-tree', '-r', '--name-only', REF]).split('\n');
}
function read(file) {
  if (TREE) {
    try { return fs.readFileSync(path.join(TREE, file), 'utf8'); } catch (e) { return null; }
  }
  return show(REF, file);
}
function isServerFile(f) {
  if (!/\.c?js$/.test(f)) return false;
  if (f === 'server.js') return true;
  if (/^bin\/[^/]+\.c?js$/.test(f)) return true;
  return f.startsWith('lib/') && !/^lib\/(client|report|report_plugins)\//.test(f);
}
function guardedLines(source) {
  // 1-based line numbers inside every block opened by the development guard.
  const lines = source.split('\n');
  const inside = new Set();
  const guards = [];
  for (let i = 0; i < lines.length; i++) {
    if (!GUARD.test(lines[i])) continue;
    guards.push(i + 1);
    let depth = 0;
    for (let j = i; j < lines.length; j++) {
      const line = j === i ? lines[j].slice(lines[j].search(GUARD)) : lines[j];
      for (const ch of line) {
        if (ch === '{') depth++;
        else if (ch === '}') depth--;
      }
      if (j > i) inside.add(j + 1);
      if (depth <= 0) break;
    }
  }
  return { inside, guards };
}

const findings = [];
const pkgText = read('package.json');
if (pkgText === null) {
  findings.push({ ok: false, text: `${label}: package.json not readable` });
  report('runtime-requires-declared', findings);
}
const pkg = JSON.parse(pkgText);
const deps = pkg.dependencies || {};
const devDeps = pkg.devDependencies || {};

const files = listFiles().filter(isServerFile);
const uses = new Map();
for (const file of files) {
  const source = read(file);
  if (source === null) continue;
  let guard = null;
  source.split('\n').forEach((text, index) => {
    for (const m of text.matchAll(/\brequire\(\s*['"]([^'"]+)['"]\s*\)/g)) {
      const id = m[1];
      if (id.startsWith('node:') || id.startsWith('.') || id.startsWith('/')) continue;
      const name = id.startsWith('@') ? id.split('/').slice(0, 2).join('/') : id.split('/')[0];
      if (builtinModules.includes(name)) continue;
      if (!uses.has(name)) uses.set(name, []);
      if (ALLOW[name] && guard === null) guard = guardedLines(source);
      uses.get(name).push({
        file, line: index + 1,
        guarded: guard ? guard.inside.has(index + 1) : false,
        guards: guard ? guard.guards : [],
      });
    }
  });
}

if (files.length === 0) {
  findings.push({ ok: false, text: `${label}: no server files found` });
}
for (const must of ['axios', 'lodash']) {
  // The packages this gate was written for. If either stops being loaded the
  // gate must be re-read, not silently pass on the rest.
  if (!uses.has(must)) findings.push({ ok: false, text: `${label}: server code no longer requires ${must}; re-read BF-176` });
}

for (const name of [...uses.keys()].sort()) {
  const where = uses.get(name);
  const at = where.map(u => `${u.file}:${u.line}`).join(', ');
  if (ALLOW[name]) {
    const stray = where.filter(u => u.file !== ALLOW[name] || !u.guarded);
    if (stray.length) {
      findings.push({ ok: false, text: `${label}: ${name} is allowed only inside the NODE_ENV === 'development' block of ${ALLOW[name]}, but is required outside it at ${stray.map(u => `${u.file}:${u.line}`).join(', ')}` });
    } else {
      const decl = deps[name] ? 'dependencies' : devDeps[name] ? 'devDependencies' : 'undeclared';
      findings.push({ ok: true, text: `${label}: ${name} (${decl}) allowlisted: required only inside the development guard at ${ALLOW[name]}:${where[0].guards.join(',')} (${at})` });
    }
    continue;
  }
  if (deps[name]) {
    findings.push({ ok: true, text: `${label}: ${name} in dependencies (${deps[name]})` });
  } else if (devDeps[name]) {
    findings.push({ ok: false, text: `${label}: ${name} is required by server code (${at}) but declared only in devDependencies (${devDeps[name]})` });
  } else {
    findings.push({ ok: false, text: `${label}: ${name} is required by server code (${at}) but not declared` });
  }
}

console.log(`  scanned ${files.length} server files at ${label}`);
report('runtime-requires-declared', findings);
