function restorePrimerConfig(input, directory, limit) {
  const fs = require('node:fs');
  const digest = require('node:crypto').createHash;
  const gzip = require('node:zlib');
  if (fs.existsSync(input+'/config.json')) throw Error('K8S_PRIMER_STORAGE_AMBIGUOUS_CONFIG');
  const meta = JSON.parse(fs.readFileSync(input+'/config.digest.json'));
  if (Object.keys(meta).sort().join(',') !== 'bytes,sha256' ||
      !Number.isSafeInteger(meta.bytes) || meta.bytes < 1 || meta.bytes >= limit ||
      typeof meta.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(meta.sha256)) throw Error('K8S_PRIMER_STORAGE_DIGEST_INVALID');
  const raw = gzip.gunzipSync(fs.readFileSync(input+'/config.json.gz'), {maxOutputLength:meta.bytes});
  if (raw.length !== meta.bytes || digest('sha256').update(raw).digest('hex') !== meta.sha256)
    throw Error('K8S_PRIMER_STORAGE_CONFIG_CHANGED');
  fs.writeFileSync(directory+'/config.json', raw, {mode:0o400,flag:'wx'});
}
