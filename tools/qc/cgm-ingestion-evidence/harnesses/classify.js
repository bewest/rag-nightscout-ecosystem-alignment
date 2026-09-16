// Enumerate Nightscout's environment-variable configuration surface from FOUR
// sources and take the union. Run from the root of a cgm-remote-monitor tree.
const fs = require('fs'), path = require('path');
const ROOT = process.argv[2] || process.cwd();
const R = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

// --- Source 1: the settings layer's own env spelling -------------------
const settings = require(path.resolve(ROOT, 'lib/settings.js'))();
const s1 = new Set();
settings.eachSettingAsEnv(function record (name) { s1.add(name); return undefined; });

// --- Source 2: literal arguments to the readENV family in env.js -------
const envSrc = R('lib/server/env.js');
const s2 = new Set();
for (const m of envSrc.matchAll(/readENV(?:Truthy|Raw)?\s*\(\s*'([A-Z0-9_]+)'/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/readEnvFile\s*\(\s*'([A-Z0-9_]+)'/g)) s2.add(m[1]);
// shadowEnv / process.env bracket reads inside env.js
for (const m of envSrc.matchAll(/(?:shadowEnv|process\.env)\s*\[\s*'([A-Z0-9_]+)'\s*\]/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/process\.env\.([A-Z][A-Z0-9_]+)/g)) s2.add(m[1]);

// --- Source 3: plugin prefixes that findExtendedSettings can match -----
// findExtendedSettings accepts ANY key <ENABLEDPLUGIN>_*, so the closed set is
// the PREFIX set, never the variable set.
const plugins = fs.readdirSync(path.join(ROOT, 'lib/plugins'))
  .filter(f => f.endsWith('.js'))
  .map(f => f.replace(/\.js$/, ''))
  .filter(n => !['index', 'pluginbase', 'ar2'].includes(n) === true || n === 'ar2');
const s3 = new Set(plugins.map(p => p.toUpperCase()));

// --- Source 4: README, to catch what sources 1-3 cannot see ------------
const s4 = new Set();
for (const m of R('README.md').matchAll(/\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b/g)) s4.add(m[1]);

const union = new Set([...s1, ...s2, ...s4]);
// Source 3 contributes prefixes; fold in README names matching a prefix.
const out = {
  s1: s1.size, s2: s2.size, s3prefixes: s3.size, s4: s4.size, union: union.size,
};
console.log(JSON.stringify(out, null, 1));
if (process.argv[3] === '--list') console.log([...union].sort().join('\n'));
if (process.argv[3] === '--s1') console.log([...s1].sort().join('\n'));
if (process.argv[3] === '--s2') console.log([...s2].sort().join('\n'));
if (process.argv[3] === '--s3') console.log([...s3].sort().join('\n'));
