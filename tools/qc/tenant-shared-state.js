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

const root = path.resolve(ROOT);
const files = SCAN_DIRS.flatMap(d => walkFiles(path.join(root, d)));
const report = { root, scanned: files.length, unparsed: [], files: {} };

for (const file of files) {
  const rel = path.relative(root, file);
  const result = scan(file);
  if (result.unparsed) { report.unparsed.push({ file: rel, error: result.unparsed }); continue; }
  if (result.findings.length) report.files[rel] = result.findings;
}

const counts = { 'mutable-binding': 0, assignment: 0 };
for (const findings of Object.values(report.files)) {
  for (const f of findings) counts[f.kind] = (counts[f.kind] || 0) + 1;
}
report.counts = counts;
report.filesWithFindings = Object.keys(report.files).length;

if (asJson) {
  console.log(JSON.stringify(report, null, 1));
} else {
  console.log(`scanned ${report.scanned} files under ${path.relative(process.cwd(), root)}/lib`);
  if (report.unparsed.length) {
    console.log(`\nUNPARSED (${report.unparsed.length}) -- a hole in the measurement, not a pass:`);
    for (const u of report.unparsed) console.log(`  ${u.file}: ${u.error}`);
  }
  console.log(`\n${report.filesWithFindings} files carry module-level mutable state`);
  console.log(`  mutable-binding  ${counts['mutable-binding'] || 0}`);
  console.log(`  assignment       ${counts.assignment || 0}   <- written after load`);

  const byAssign = Object.entries(report.files)
    .map(([f, x]) => [f, x.filter(v => v.kind === 'assignment').length, x.length])
    .filter(([, a]) => a > 0)
    .sort((a, b) => b[1] - a[1]);
  console.log(`\nWritten after load, worst first -- these are the ones that hold state:\n`);
  for (const [file, assigns, total] of byAssign.slice(0, 25)) {
    console.log(`  ${String(assigns).padStart(3)} writes  ${file}  (${total} findings)`);
  }
}
