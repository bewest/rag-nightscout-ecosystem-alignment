const fs = require('fs'), path = require('path');
const ROOT = process.argv[2] || process.cwd();
const R = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

const settings = require(path.resolve(ROOT, 'lib/settings.js'))();
const s1 = new Set();
settings.eachSettingAsEnv(name => { s1.add(name); return undefined; });

const envSrc = R('lib/server/env.js'); const s2 = new Set();
for (const m of envSrc.matchAll(/readENV(?:Truthy|Raw)?\s*\(\s*'([A-Z0-9_]+)'/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/readEnvFile\s*\(\s*'([A-Z0-9_]+)'/g))            s2.add(m[1]);
for (const m of envSrc.matchAll(/(?:shadowEnv|process\.env)\s*\[\s*'([A-Z0-9_]+)'\s*\]/g)) s2.add(m[1]);
for (const m of envSrc.matchAll(/process\.env\.([A-Z][A-Z0-9_]+)/g))              s2.add(m[1]);

const s3 = new Set(fs.readdirSync(path.join(ROOT, 'lib/plugins'))
  .filter(f => f.endsWith('.js')).map(f => f.replace(/\.js$/, '').toUpperCase()));

const s4 = new Set();
for (const m of R('README.md').matchAll(/\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b/g)) s4.add(m[1]);

const union = new Set([...s1,...s2,...s4]);
console.log(JSON.stringify({ s1: s1.size, s2: s2.size, s3prefixes: s3.size,
                             s4: s4.size, union: union.size }));
fs.writeFileSync('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/union.txt', [...union].sort().join('\n'));
fs.writeFileSync('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/s1.txt', [...s1].sort().join('\n'));
fs.writeFileSync('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/s2.txt', [...s2].sort().join('\n'));
fs.writeFileSync('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/s4.txt', [...s4].sort().join('\n'));
