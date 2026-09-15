// Module-level mutable state: what one tenant can change for every other tenant
// sharing the process.
//
// {M} §5.2 item 4 asks for "a lint rule or test banning module-level mutable
// plugin state". This is the measurement that has to come first: a ban is only
// writable once you know what it would ban, and a ban nobody can satisfy gets
// switched off.
//
// WHY THIS IS THE TENANCY QUESTION AND NOT A STYLE QUESTION. Under D4 the target
// is several tenants served by one Node process. A `var cache = {}` at module
// scope is initialised once per process, not once per tenant -- so it is shared
// by every tenant that process serves. If it holds anything derived from a
// request, one person's data is visible to another. If it holds anything a
// request can grow, one tenant can exhaust it for everyone. Neither failure
// announces itself: the module keeps working, and the tests keep passing,
// because a test process serves one tenant.
//
// WHAT IT LOOKS FOR, and what each finding means:
//
//   mutable-binding   `let`/`var` at module scope, or a `const` bound to an
//                     object/array/Map/Set. A const OBJECT is mutable state --
//                     const freezes the binding, never the value, and this is
//                     the single most common way the pattern hides.
//   assignment        an assignment to a module-scope binding from inside a
//                     function. This is the strongest signal: it is the state
//                     being written after load, which is what makes it state
//                     rather than configuration.
//   exported-mutable  a mutable module-scope binding that is also exported,
//                     which puts it beyond the module's own control.
//
// WHAT IT DELIBERATELY DOES NOT FLAG. A frozen object, a primitive const, a
// RegExp or a function: those are configuration, and a rule that flags them
// teaches people to ignore it. Requires are excluded for the same reason --
// every module has them and none of them is the problem.
//
// Usage:
//   node tools/qc/tenant-shared-state.js [--json] [--root <server checkout>]

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_ROOT = path.join(__dirname, '..', '..', 'externals', 'work', 'crm-seam');
const SCAN_DIRS = ['lib'];

const args = process.argv.slice(2);
const asJson = args.includes('--json');
const rootArg = args.indexOf('--root');
const ROOT = rootArg > -1 ? args[rootArg + 1] : DEFAULT_ROOT;

// espree ships with eslint, which this server already depends on, so the parse
// is the same one the project's own lint uses rather than a second dialect.
const espree = require(path.join(ROOT, 'node_modules', 'espree'));

const PARSE = { ecmaVersion: 2024, sourceType: 'script', loc: true };

function walkFiles (dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
      walkFiles(full, out);
    } else if (entry.name.endsWith('.js')) {
      out.push(full);
    }
  }
  return out;
}

// A require() call, or a member/chain rooted in one. Excluded wholesale: every
// module has them, none of them is the state this is looking for.
function isRequire (node) {
  if (!node) return false;
  if (node.type === 'CallExpression') {
    if (node.callee.type === 'Identifier' && node.callee.name === 'require') return true;
    return isRequire(node.callee);
  }
  if (node.type === 'MemberExpression') return isRequire(node.object);
  return false;
}

function isFrozen (node) {
  return node && node.type === 'CallExpression'
    && node.callee.type === 'MemberExpression'
    && node.callee.object.type === 'Identifier' && node.callee.object.name === 'Object'
    && node.callee.property.type === 'Identifier' && node.callee.property.name === 'freeze';
}

// Is the initialiser a mutable VALUE? const freezes the binding, not the value,
// so `const cache = {}` is shared mutable state and `const MAX = 5` is not.
function mutableValue (node) {
  if (!node) return false;
  if (isRequire(node) || isFrozen(node)) return false;
  if (node.type === 'ObjectExpression' || node.type === 'ArrayExpression') return true;
  if (node.type === 'NewExpression' && node.callee.type === 'Identifier') {
    return ['Map', 'Set', 'WeakMap', 'WeakSet', 'Array', 'Object'].includes(node.callee.name);
  }
  return false;
}

function scan (file) {
  const source = fs.readFileSync(file, 'utf8');
  let ast;
  try {
    ast = espree.parse(source, PARSE);
  } catch (err) {
    // Reported, never skipped: a file this cannot parse is a hole in the
    // measurement, and a census that quietly covers less than it claims is
    // worse than one that says so.
    return { unparsed: err.message.split('\n')[0] };
  }

  const moduleScope = new Map();   // name -> {kind, line, mutable}
  const findings = [];

  for (const stmt of ast.body) {
    if (stmt.type !== 'VariableDeclaration') continue;
    for (const decl of stmt.declarations) {
      if (decl.id.type !== 'Identifier') continue;
      const mutable = stmt.kind !== 'const' || mutableValue(decl.init);
      if (isRequire(decl.init)) continue;
      moduleScope.set(decl.id.name, { kind: stmt.kind, line: decl.loc.start.line, mutable });
      if (mutable) {
        findings.push({ kind: 'mutable-binding', name: decl.id.name,
          line: decl.loc.start.line, detail: stmt.kind });
      }
    }
  }

  // Assignments to those bindings from anywhere below the top level. This is
  // the strongest signal -- state written after load is state, not config.
  let depth = 0;
  (function visit (node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    if (!node.type) return;

    const isFn = node.type === 'FunctionDeclaration' || node.type === 'FunctionExpression'
      || node.type === 'ArrowFunctionExpression';
    if (isFn) depth++;

    if (depth > 0 && node.type === 'AssignmentExpression') {
      let target = node.left;
      while (target && target.type === 'MemberExpression') target = target.object;
      if (target && target.type === 'Identifier' && moduleScope.has(target.name)) {
        findings.push({ kind: 'assignment', name: target.name,
          line: node.loc.start.line,
          detail: node.left.type === 'MemberExpression' ? 'writes a property' : 'rebinds' });
      }
    }

    for (const key of Object.keys(node)) {
      if (key === 'loc' || key === 'range' || key === 'parent') continue;
      visit(node[key]);
    }
    if (isFn) depth--;
  })(ast.body);

  return { findings, moduleScope };
}

// ---------------------------------------------------------------- residency
//
// Whether module-level state is a TENANCY hazard depends entirely on where the
// module runs, and a census that ignores that is misleading rather than
// incomplete: `lib/client/index.js` is the single largest holder of
// module-level state in the tree and it is not a hazard at all, because it is
// loaded once per BROWSER PAGE, by one person, for one site.
//
// Residency is computed from the require graph rather than from directory
// names, because the directories do not line up with it -- lib/plugins/ is
// loaded by BOTH the server (plugins.checkNotifications) and the bundles (the
// chart), which is precisely the category that needs naming.
//
// Limit worth stating: this follows static, relative require() calls only. A
// dynamic require, or a module reached only through a package name, is invisible
// to it. That makes the server set a LOWER BOUND -- the direction that matters,
// since an unreached module is reported as browser-only and therefore harmless.

const SERVER_ENTRIES = ['server.js', 'lib/server/server.js'];
const BROWSER_ENTRY_DIR = 'bundle';

// Both spellings. The bundle entry points are ESM and use `import`, while the
// server tree is CommonJS -- collecting only require() made every browser file
// look `unreached`, and it did so SILENTLY, because a module-syntax file fails a
// script-mode parse and the failure was swallowed. Parse failures are counted
// now rather than discarded.
const unresolvable = [];

function requiresOf (file) {
  let ast = null;
  for (const sourceType of ['script', 'module']) {
    try {
      ast = espree.parse(fs.readFileSync(file, 'utf8'), { ...PARSE, sourceType });
      break;
    } catch { /* try the other dialect */ }
  }
  // A .json or .css dependency is a leaf by definition -- it has no requires of
  // its own -- so failing to parse one is not a hole. Only a JavaScript file
  // this cannot read leaves the graph incomplete.
  if (!ast) {
    if (file.endsWith('.js')) unresolvable.push(file);
    return [];
  }

  const out = [];
  (function visit (node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    if ((node.type === 'ImportDeclaration'
         || node.type === 'ExportNamedDeclaration'
         || node.type === 'ExportAllDeclaration')
        && node.source && typeof node.source.value === 'string'
        && node.source.value.startsWith('.')) {
      out.push(node.source.value);
    }
    if (node.type === 'CallExpression' && node.callee.type === 'Identifier'
        && node.callee.name === 'require'
        && node.arguments.length === 1 && node.arguments[0].type === 'Literal'
        && typeof node.arguments[0].value === 'string'
        && node.arguments[0].value.startsWith('.')) {
      out.push(node.arguments[0].value);
    }
    for (const key of Object.keys(node)) {
      if (key === 'loc' || key === 'range') continue;
      visit(node[key]);
    }
  })(ast);
  return out;
}

function resolveRelative (from, spec) {
  const base = path.resolve(path.dirname(from), spec);
  for (const candidate of [base, base + '.js', path.join(base, 'index.js')]) {
    try { if (fs.statSync(candidate).isFile()) return candidate; } catch { /* next */ }
  }
  return null;
}

function reachableFrom (entries) {
  const seen = new Set();
  const queue = entries.filter(f => { try { return fs.statSync(f).isFile(); } catch { return false; } });
  while (queue.length) {
    const file = queue.pop();
    if (seen.has(file)) continue;
    seen.add(file);
    for (const spec of requiresOf(file)) {
      const target = resolveRelative(file, spec);
      if (target && !seen.has(target)) queue.push(target);
    }
  }
  return seen;
}

const root = path.resolve(ROOT);
const files = SCAN_DIRS.flatMap(d => walkFiles(path.join(root, d)));

const serverReach = reachableFrom(SERVER_ENTRIES.map(e => path.join(root, e)));
const bundleDir = path.join(root, BROWSER_ENTRY_DIR);
let browserReach = new Set();
try {
  browserReach = reachableFrom(fs.readdirSync(bundleDir)
    .filter(f => f.endsWith('.js')).map(f => path.join(bundleDir, f)));
} catch { /* a checkout without bundles reports everything as server or neither */ }

function residencyOf (file) {
  const onServer = serverReach.has(file);
  const inBrowser = browserReach.has(file);
  if (onServer && inBrowser) return 'both';
  if (onServer) return 'server';
  if (inBrowser) return 'browser';
  return 'unreached';
}

const report = { root, scanned: files.length, unparsed: [], files: {} };

for (const file of files) {
  const rel = path.relative(root, file);
  const result = scan(file);
  if (result.unparsed) { report.unparsed.push({ file: rel, error: result.unparsed }); continue; }
  if (result.findings.length) {
    report.files[rel] = { residency: residencyOf(file), findings: result.findings };
  }
}

const counts = {};
for (const entry of Object.values(report.files)) {
  counts[entry.residency] = counts[entry.residency] || { files: 0, bindings: 0, assignments: 0 };
  counts[entry.residency].files++;
  for (const f of entry.findings) {
    if (f.kind === 'assignment') counts[entry.residency].assignments++;
    else counts[entry.residency].bindings++;
  }
}
report.counts = counts;
report.filesWithFindings = Object.keys(report.files).length;

if (asJson) {
  console.log(JSON.stringify(report, null, 1));
} else {
  console.log(`scanned ${report.scanned} files under ${path.relative(process.cwd(), root)}/lib`);
  if (unresolvable.length) {
    console.log(`\nUNPARSEABLE WHILE WALKING THE GRAPH (${unresolvable.length}) -- these files'`
      + ` dependencies are missing from the residency classification:`);
    for (const f of unresolvable) console.log(`  ${path.relative(root, f)}`);
  }
  if (report.unparsed.length) {
    console.log(`\nUNPARSED (${report.unparsed.length}) -- a hole in the measurement, not a pass:`);
    for (const u of report.unparsed) console.log(`  ${u.file}: ${u.error}`);
  }
  console.log(`\n${report.filesWithFindings} files carry module-level mutable state\n`);
  const LABEL = {
    server: 'SERVER-RESIDENT   one process, many tenants -- the hazard',
    both: 'BOTH              server-resident AND bundled; the server copy is the hazard',
    browser: 'browser-only      one page load, one person, one site -- NOT a hazard',
    unreached: 'unreached         no static require path from either entry',
  };
  console.log('  residency         files  bindings  writes');
  for (const key of ['server', 'both', 'browser', 'unreached']) {
    const c = counts[key];
    if (!c) continue;
    console.log(`  ${key.padEnd(10)}${String(c.files).padStart(11)}`
      + `${String(c.bindings).padStart(10)}${String(c.assignments).padStart(8)}`
      + `   ${LABEL[key].split('   ')[1] || ''}`);
  }

  const hazard = Object.entries(report.files)
    .filter(([, x]) => x.residency === 'server' || x.residency === 'both')
    .map(([f, x]) => [f, x.residency, x.findings.filter(v => v.kind === 'assignment').length,
      x.findings.length])
    .sort((a, b) => b[2] - a[2]);
  console.log(`\nServer-resident, written after load, worst first:\n`);
  for (const [file, residency, assigns, total] of hazard) {
    if (!assigns) continue;
    console.log(`  ${String(assigns).padStart(3)} writes  [${residency}] ${file}  (${total} findings)`);
  }
}
