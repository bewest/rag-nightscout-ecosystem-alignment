'use strict';
// Tokenless init phase. Bounds precede every read, inflate, parse and write.
const fs = require('node:fs'), crypto = require('node:crypto'), zlib = require('node:zlib');
const MAX_RAW = 4 * 1024**2, MAX_GZIP = 600 * 1024, MAX_TENANTS = 10000;
const need = (ok, code) => { if (!ok) throw Error('K8S_NATIVE_INPUT_' + code); };
const hash = raw => crypto.createHash('sha256').update(raw).digest('hex');
function bounded(path, maximum) {
  const size = fs.statSync(path).size;
  need(Number.isSafeInteger(size) && size > 0 && size <= maximum, 'FILE_BOUND');
  const raw = fs.readFileSync(path);
  need(raw.length === size, 'FILE_CHANGED');
  return raw;
}
function restore(input, output, count) {
  need(Number.isSafeInteger(count) && count > 0 && count <= MAX_TENANTS, 'TENANT_BOUND');
  need(!fs.existsSync(input + '/tenants.json') && !fs.existsSync(output + '/tenants.json'), 'AMBIGUOUS_ROSTER');
  const meta = JSON.parse(bounded(input + '/tenants.digest.json', 4096));
  need(Object.keys(meta).sort().join(',') === 'bytes,codec,gzipBytes,gzipSha256,sha256,tenants' &&
       meta.codec === 'gzip-v1' && meta.tenants === count &&
       Number.isSafeInteger(meta.bytes) && meta.bytes > 0 && meta.bytes <= MAX_RAW &&
       Number.isSafeInteger(meta.gzipBytes) && meta.gzipBytes > 0 && meta.gzipBytes <= MAX_GZIP &&
       typeof meta.sha256 === 'string' && /^[0-9a-f]{64}$/.test(meta.sha256) &&
       typeof meta.gzipSha256 === 'string' && /^[0-9a-f]{64}$/.test(meta.gzipSha256), 'DIGEST_INVALID');
  const packed = bounded(input + '/tenants.json.gz', meta.gzipBytes);
  need(packed.length === meta.gzipBytes && hash(packed) === meta.gzipSha256, 'GZIP_CHANGED');
  const raw = zlib.gunzipSync(packed, {maxOutputLength: meta.bytes});
  need(raw.length === meta.bytes && hash(raw) === meta.sha256, 'ROSTER_CHANGED');
  const rows = JSON.parse(raw), ids = new Set();
  need(Array.isArray(rows) && rows.length === count && rows.every(row => {
    if (!row || typeof row.id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(row.id) ||
        ids.has(row.id) || typeof row.host !== 'string' || !row.host.endsWith('.test') ||
        typeof row.token !== 'string' || !row.token) return false;
    ids.add(row.id); return true;
  }), 'ROSTER_CONTRACT');
  fs.writeFileSync(output + '/tenants.json', raw, {mode: 0o400, flag: 'wx'});
}
try {
  need(process.argv.length === 5, 'ARGUMENTS');
  restore(process.argv[2], process.argv[3], Number(process.argv[4]));
} catch (error) {
  // Do not log input values, JSON parser excerpts or synthetic DATA tokens.
  console.error(/^K8S_NATIVE_INPUT_[A-Z_]+$/.test(error.message) ? error.message : 'K8S_NATIVE_INPUT_DECODE_REFUSED');
  process.exitCode = 78;
}
