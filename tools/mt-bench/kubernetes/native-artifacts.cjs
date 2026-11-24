'use strict';
// Test-actor artifact custody only. No application imports, credentials or API token.
const fs = require('node:fs'), path = require('node:path');
const { once } = require('node:events');
const root = process.env.NS_NATIVE_OUTPUT || '/out';
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
let config;
const manifestFile = path.join(root, 'artifacts.json');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function checked(name, expected) {
  if (!config.files[name] || path.basename(name) !== name) throw Error('K8S_NATIVE_ARTIFACT_NAME');
  const target = path.join(root, name), stat = fs.lstatSync(target);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0 || stat.size > config.files[name] ||
      (expected && stat.size !== expected.bytes)) throw Error('K8S_NATIVE_ARTIFACT_BOUND');
  return target;
}
function sized(name) {
  return {bytes: fs.lstatSync(checked(name)).size};
}
async function main() {
  const mode = process.argv[2];
  if (mode === 'publish') {
    const [source, runId, podUid, destination] = process.argv.slice(3);
    if (!source || !destination) throw Error('K8S_WRITER_PUBLICATION_ARGUMENTS');
    const custody = read(path.join(source, 'native-load.json'));
    if (custody.kind !== 'm7-kubernetes-k6-job-v1' || custody.runId !== runId || custody.podUid !== podUid ||
        custody.artifactSource?.podUid !== podUid || custody.writerContinuity === 'UNMEASURED')
      throw Error('K8S_WRITER_PUBLICATION_CUSTODY');
    const result = await require('./native-publication.cjs').publish(source, runId, podUid, destination,
      read(path.join(source, 'native-artifacts.json')));
    process.stdout.write(JSON.stringify(result) + '\n');
    if (result.status !== 'complete') process.exitCode = 78;
    return;
  }
  config = read(process.env.NS_NATIVE_EXPORT_CONFIG || '/inputs/export.json');
  if (mode === 'hold') {
    const timer = setTimeout(() => process.exit(78), config.seconds * 1000);
    try {
      while (!fs.existsSync(path.join(root, 'exit-code'))) await delay(100);
      const exit = fs.readFileSync(path.join(root, 'exit-code'), 'utf8').trim();
      if (!/^[0-9]{1,3}$/.test(exit)) throw Error('K8S_NATIVE_ARTIFACT_EXIT');
      const files = {};
      for (const name of Object.keys(config.files)) {
        try { files[name] = sized(name); }
        catch (err) {
          if (!config.writerPublication || (err.code !== 'ENOENT' && err.message !== 'K8S_NATIVE_ARTIFACT_BOUND')) throw err;
        }
      }
      const manifest = {kind:'m7-native-artifacts-v1', runId:config.runId, exitCode:Number(exit), files};
      if (config.writerPublication) {
        await require('./native-publication.cjs').publish(root, config.runId, process.env.NS_PUBLICATION_POD_UID,
          process.env.NS_PUBLICATION_ROOT, manifest);
      }
      fs.writeFileSync(manifestFile + '.tmp', JSON.stringify(manifest), {mode:0o600, flag:'wx'});
      fs.renameSync(manifestFile + '.tmp', manifestFile);
      while (!fs.existsSync(path.join(root, 'exported'))) await delay(100);
    } finally { clearTimeout(timer); }
    return;
  }
  const raw = fs.readFileSync(manifestFile), manifest = JSON.parse(raw);
  if (mode === 'manifest') { process.stdout.write(raw); return; }
  if (mode === 'ack') {
    if (process.argv[3] !== manifest.runId) throw Error('K8S_NATIVE_ARTIFACT_ACK');
    fs.writeFileSync(path.join(root, 'exported'), 'complete\n', {mode:0o600, flag:'wx'});
    return;
  }
  if (mode !== 'read' && mode !== 'read-range') throw Error('K8S_NATIVE_ARTIFACT_MODE');
  const name = process.argv[3], expected = manifest.files[name];
  if (!expected) throw Error('K8S_NATIVE_ARTIFACT_NAME');
  const options = {highWaterMark:65536};
  if (mode === 'read-range') {
    const [offset, length] = process.argv.slice(4, 6).map(Number);
    if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(length) || offset < 0 || length < 1 ||
        !Number.isSafeInteger(config.rangeBytes) || length > config.rangeBytes || offset > expected.bytes - length)
      throw Error('K8S_NATIVE_ARTIFACT_BOUND');
    options.start = offset;
    options.end = offset + length - 1;
  }
  for await (const chunk of fs.createReadStream(checked(name, expected), options)) {
    if (!process.stdout.write(chunk)) await once(process.stdout, 'drain');
  }
}
main().catch(error => { console.error(/^K8S_[A-Z_]+$/.test(error.message) ? error.message : 'K8S_NATIVE_ARTIFACT_UNAVAILABLE'); process.exitCode = 78; });
