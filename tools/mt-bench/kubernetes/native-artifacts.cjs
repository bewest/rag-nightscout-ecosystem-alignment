'use strict';
// Test-actor artifact custody only. No application imports, credentials or API token.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { once } = require('node:events');
const root = process.env.NS_NATIVE_OUTPUT || '/out';
const config = JSON.parse(fs.readFileSync(process.env.NS_NATIVE_EXPORT_CONFIG || '/inputs/export.json'));
const manifestFile = path.join(root, 'artifacts.json');
const digest = raw => crypto.createHash('sha256').update(raw).digest('hex');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function checked(name, expected) {
  if (!config.files[name] || path.basename(name) !== name) throw Error('K8S_NATIVE_ARTIFACT_NAME');
  const target = path.join(root, name), stat = fs.lstatSync(target);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > config.files[name] ||
      (expected && stat.size !== expected.bytes)) throw Error('K8S_NATIVE_ARTIFACT_BOUND');
  return target;
}
async function hashFile(name) {
  const hash = crypto.createHash('sha256'); let bytes = 0;
  for await (const chunk of fs.createReadStream(checked(name), {highWaterMark: 65536})) {
    bytes += chunk.length;
    if (bytes > config.files[name]) throw Error('K8S_NATIVE_ARTIFACT_BOUND');
    hash.update(chunk);
  }
  return {bytes, sha256: hash.digest('hex')};
}
async function main() {
  const mode = process.argv[2];
  if (mode === 'hold') {
    const timer = setTimeout(() => process.exit(78), config.seconds * 1000);
    try {
      while (!fs.existsSync(path.join(root, 'exit-code'))) await delay(100);
      const exit = fs.readFileSync(path.join(root, 'exit-code'), 'utf8').trim();
      if (!/^[0-9]{1,3}$/.test(exit)) throw Error('K8S_NATIVE_ARTIFACT_EXIT');
      const files = {};
      for (const name of Object.keys(config.files)) files[name] = await hashFile(name);
      const manifest = {kind:'m7-native-artifacts-v1', runId:config.runId,
        sourceSha256:config.sourceSha256, driverWrapperSha256:config.driverWrapperSha256,
        exitCode:Number(exit), files};
      fs.writeFileSync(manifestFile + '.tmp', JSON.stringify(manifest), {mode:0o600, flag:'wx'});
      fs.renameSync(manifestFile + '.tmp', manifestFile);
      while (!fs.existsSync(path.join(root, 'exported'))) await delay(100);
    } finally { clearTimeout(timer); }
    return;
  }
  const raw = fs.readFileSync(manifestFile), manifest = JSON.parse(raw);
  if (mode === 'manifest') { process.stdout.write(raw); return; }
  if (mode === 'ack') {
    if (process.argv[3] !== digest(raw)) throw Error('K8S_NATIVE_ARTIFACT_ACK');
    fs.writeFileSync(path.join(root, 'exported'), 'complete\n', {mode:0o600, flag:'wx'});
    return;
  }
  if (mode !== 'read') throw Error('K8S_NATIVE_ARTIFACT_MODE');
  const name = process.argv[3], expected = manifest.files[name];
  if (!expected) throw Error('K8S_NATIVE_ARTIFACT_NAME');
  const actual = await hashFile(name);
  if (actual.bytes !== expected.bytes || actual.sha256 !== expected.sha256) throw Error('K8S_NATIVE_ARTIFACT_CHANGED');
  // Bounded chunks and backpressure; the whole CSV never enters Node memory.
  const hash = crypto.createHash('sha256'); let bytes = 0;
  for await (const chunk of fs.createReadStream(checked(name, expected), {highWaterMark:65536})) {
    bytes += chunk.length;
    if (bytes > expected.bytes) throw Error('K8S_NATIVE_ARTIFACT_CHANGED');
    hash.update(chunk);
    if (!process.stdout.write(chunk)) await once(process.stdout, 'drain');
  }
  if (bytes !== expected.bytes || hash.digest('hex') !== expected.sha256) throw Error('K8S_NATIVE_ARTIFACT_CHANGED');
}
main().catch(error => { console.error(/^K8S_[A-Z_]+$/.test(error.message) ? error.message : 'K8S_NATIVE_ARTIFACT_UNAVAILABLE'); process.exitCode = 78; });
