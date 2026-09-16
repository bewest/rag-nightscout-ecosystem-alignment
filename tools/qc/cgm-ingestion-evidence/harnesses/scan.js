// Count live console.* call sites in lib/ + index.js, and how many pass a
// non-literal argument. Comments and string literals stripped first.
const fs = require('fs'), path = require('path');
function walk(d, out) {
  for (const e of fs.readdirSync(d, {withFileTypes:true})) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith('.js')) out.push(p);
  }
  return out;
}
// strip // and /* */ comments, respecting string/template literals
function strip(src) {
  let out = '', i = 0, n = src.length;
  while (i < n) {
    const c = src[i], d = src[i+1];
    if (c === '/' && d === '/') { while (i < n && src[i] !== '\n') i++; continue; }
    if (c === '/' && d === '*') { i += 2; while (i < n && !(src[i] === '*' && src[i+1] === '/')) i++; i += 2; continue; }
    if (c === '"' || c === "'" || c === '`') {
      const q = c; out += c; i++;
      while (i < n) { if (src[i] === '\\') { out += 'XX'; i += 2; continue; }
        if (src[i] === q) break; out += (src[i] === '\n' ? '\n' : 'X'); i++; }
      out += q; i++; continue;
    }
    out += c; i++;
  }
  return out;
}
const root = process.argv[2];
const files = [];
if (fs.existsSync(path.join(root,'index.js'))) files.push(path.join(root,'index.js'));
if (fs.existsSync(path.join(root,'lib'))) walk(path.join(root,'lib'), files);
let live = 0, dyn = 0; const per = {};
for (const f of files) {
  const s = strip(fs.readFileSync(f,'utf8'));
  let l = 0, dd = 0;
  const re = /console\.(log|error|warn|info|debug)\s*\(/g; let m;
  while ((m = re.exec(s))) {
    l++;
    // read the balanced argument list
    let i = re.lastIndex, depth = 1, args = '';
    while (i < s.length && depth > 0) {
      if (s[i] === '(') depth++;
      else if (s[i] === ')') { depth--; if (!depth) break; }
      args += s[i]; i++;
    }
    // non-literal = anything that is not purely quoted strings / numbers joined by commas
    const cleaned = args.replace(/"[^"]*"|'[^']*'|`[^`]*`/g, 'S').replace(/\s+/g,'');
    if (!/^(S|[0-9.]+)(,(S|[0-9.]+))*,?$/.test(cleaned) && cleaned.length) dd++;
  }
  if (l) { per[path.relative(root,f)] = l + '/' + dd; live += l; dyn += dd; }
}
console.log(root.split('/').pop(), 'TOTAL', live + '/' + dyn);
for (const k of Object.keys(per).sort()) console.log('   ', k, per[k]);
