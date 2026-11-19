'use strict';

// Stream this actor into the verified waiting container. The mounted source
// owns issuance, per-state exclusion, durable completion and uncertain writes.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const read = (dir, file) => JSON.parse(fs.readFileSync(path.join(dir, file)));
const fail = code => { throw Object.assign(new Error(code), { code }); };

const known = new Set((
  'PRIMER_STATE_IN_USE PRIMER_STATE_LOCK_CHANGED PRIMER_OPTIONS_INVALID PRIMER_CONFIG_INVALID ' +
  'PRIMER_ORIGIN_INVALID PRIMER_CUSTODY_INVALID PRIMER_ENTRY_OUTCOME_UNCERTAIN ' +
  'PRIMER_CONNECTION_FAILED PRIMER_RESPONSE_INCOMPLETE PRIMER_RESPONSE_INVALID PRIMER_TENANT_WARM_TIMEOUT ' +
  'PRIMER_SUBJECT_TOKEN_MISSING PRIMER_OWNER_SUBJECT_MISSING PRIMER_OWNERSHIP_REFUSED ' +
  'PRIMER_OWNERSHIP_ALREADY_ASSIGNED PRIMER_MANAGEMENT_SESSION_REFUSED SOCKET_IPC_UNAVAILABLE ' +
  'SOCKET_IPC_CONFIG_REFUSED SOCKET_IPC_REQUEST_REFUSED SOCKET_IPC_RESPONSE_REFUSED EVALUATOR_SCOPE_UNSAFE ' +
  'K8S_PRIMER_SOURCE_CHANGED K8S_PRIMER_FIXTURE_CHANGED K8S_PRIMER_ROSTER_CHANGED K8S_PRIMER_DEADLINE ' +
  'K8S_PRIMER_OPTIONS_CHANGED K8S_PRIMER_OPTION_SOURCE_UNSUPPORTED ' +
  'PRIMER_POPULATION_OVER_CEILING POPULATION_CEILING_INVALID ' +
  'ENOENT EIO ENOSPC EACCES EROFS EEXIST'
).split(' '));

const responseErrors = new Set((
  'TENANT_WARMING TENANT_WARM_FAILED TENANT_UNAVAILABLE STORAGE_UNAVAILABLE AUTHORITY_UNAVAILABLE ' +
  'TENANT_ACTIVITY_UNAVAILABLE HUMAN_SESSION_UNAVAILABLE ACCESS_AUTHORITY_UNAVAILABLE ACCESS_AUTHORITY_INVALID ' +
  'TENANT_SNAPSHOT_UNAVAILABLE SUBJECT_ADMIN_STORE_UNAVAILABLE SUBJECT_ADMIN_STORE_UNSAFE AUTHENTICATION_REQUIRED ' +
  'UNAUTHORIZED FORBIDDEN UNCLASSIFIED'
).split(' '));

function diagnostic(error, source) {
  const code = [error?.code, error?.message].find(value => known.has(value) || /^PRIMER_DATA_API_REFUSED_[1-5][0-9]{2}$/.test(value || ''));
  const output = { error: code || 'PRIMER_UNCLASSIFIED' };
  if (code === 'SOCKET_IPC_UNAVAILABLE') {
    output.requestClass = 'internal-ownership';
    output.notReady = error.notReady === true;
  } else if (code && source) {
    // These classes and response tokens are selected by the verified source.
    const selected = source.diagnostic(error);
    if (selected.requestClass) output.requestClass = selected.requestClass;
    if (selected.connectionCause) output.connectionCause = selected.connectionCause;
    if (/^PRIMER_DATA_API_REFUSED_/.test(code) && responseErrors.has(selected.responseError)) output.responseError = selected.responseError;
  }
  if (!code) output.errorClass = error instanceof SyntaxError ? 'SyntaxError' : error instanceof TypeError ? 'TypeError' : 'Error';
  return output;
}

function verifyLegacy({ dir, contractFile, contractHash, proofHash, namespace, runId, concurrency, maxTenants, source }) {
  const contractBytes = fs.readFileSync(contractFile);
  const proofBytes = fs.readFileSync(path.join(dir, 'verified.json'));
  if (sha(contractBytes) !== contractHash || sha(proofBytes) !== proofHash) fail('K8S_PRIMER_FIXTURE_CHANGED');
  const contract = JSON.parse(contractBytes), proof = JSON.parse(proofBytes);
  // Image identity is the digest Kubernetes runs; only the fixture and the
  // admin credential boundary are checked here.
  if (proof.fixture?.namespace !== namespace || proof.fixture?.runId !== runId ||
      proof.credentialBoundary !== 'admin-private-api') fail('K8S_PRIMER_SOURCE_CHANGED');
  const declared = contract.primerOptions;
  if (declared === undefined) {
    if (maxTenants !== undefined || Number(concurrency) > 32) fail('K8S_PRIMER_OPTIONS_CHANGED');
  } else if (!declared || typeof declared !== 'object' || Array.isArray(declared) || !Object.keys(declared).length ||
             Object.entries(declared).some(([key,value]) => !['concurrency','maxTenants'].includes(key) ||
                                                            !Number.isSafeInteger(value) || value < 1) ||
             String(declared.concurrency ?? 1) !== concurrency ||
             (declared.maxTenants === undefined ? undefined : String(declared.maxTenants)) !== maxTenants) {
    fail('K8S_PRIMER_OPTIONS_CHANGED');
  }
  if (contract.primerOptionProtocol !== undefined &&
      (contract.primerOptionProtocol !== 'positive-safe-integer-v1' ||
       source.PRIMER_OPTION_PROTOCOL !== contract.primerOptionProtocol)) fail('K8S_PRIMER_OPTION_SOURCE_UNSUPPORTED');
  if (Number(concurrency) > 32 && contract.primerOptionProtocol === undefined) {
    fail('K8S_PRIMER_OPTION_SOURCE_UNSUPPORTED');
  }
}

async function commission({ app, dir, configDirectory = dir, contractFile, env, args }) {
  const split = args[0] === '--verified-serving';
  const [namespace, runId, cutoff, count, concurrency, maxTenants] = split ?
    args.slice(1) : [...args.slice(0, 2), ...args.slice(4)];
  const [contractHash, proofHash] = args.slice(2, 4);
  const stop = Number(cutoff), expectedCount = Number(count);
  const remaining = stop - Date.now();
  if (!Number.isSafeInteger(stop) || remaining <= 0 || remaining > 2147483647) fail('K8S_PRIMER_DEADLINE');
  if (!(split ? args.length === 7 : [7,8].includes(args.length)) || !/^[1-9][0-9]*$/.test(count) || !Number.isSafeInteger(expectedCount) ||
      env.NS_FIXTURE_NAMESPACE !== namespace || env.NS_FIXTURE_RUN_ID !== runId ||
      fs.existsSync(path.join(dir, '.exported'))) fail('K8S_PRIMER_FIXTURE_CHANGED');
  const source = require(path.join(app, 'deploy/multitenant/prime.js'));
  if (!split) verifyLegacy({ dir, contractFile, contractHash, proofHash, namespace, runId, concurrency, maxTenants, source });
  const options = source.parsePrimeOptions(['--concurrency', concurrency, ...(maxTenants === undefined ? [] : ['--max-tenants', maxTenants])]);
  const config = source.load(path.join(configDirectory, 'config.json'));
  if (config.apiOrigin !== 'http://api:1337' || config.adminOrigin !== 'http://admin:1342') fail('PRIMER_ORIGIN_INVALID');
  const saved = read(dir, 'provisioned.json');
  let seed = config.seed;
  if (split) {
    const demo = require(path.join(app, 'deploy/multitenant/demo-tenants.js'));
    seed = demo.tenantIds(expectedCount).map((id, index) => ({ id, hosts: [demo.tenantAlias(index)] }));
  }
  const expected = new Map(seed.map(row => [row.id, row.hosts?.[0]]));
  if (expected.size !== expectedCount || seed.length !== expectedCount || !Array.isArray(saved) ||
      saved.length !== expectedCount || new Set(saved.map(row => row.id)).size !== expectedCount ||
      saved.some(row => !row.hosts?.[0] || expected.get(row.id) !== row.hosts[0])) fail('K8S_PRIMER_ROSTER_CHANGED');
  const signal = new AbortController();
  const cancel = () => signal.abort();
  process.once('SIGTERM', cancel);
  process.once('SIGINT', cancel);
  // Let the original source drain admitted tenants. If the hard cutoff fires,
  // its lock and ambiguous-write journal remain evidence for the owner.
  const left = stop - Date.now();
  if (left <= 0) fail('K8S_PRIMER_DEADLINE');
  const soft = setTimeout(cancel, Math.max(0, left - Math.min(5000, Math.floor(left / 4))));
  const hard = setTimeout(() => {
    fs.writeSync(1, JSON.stringify({ error: 'K8S_PRIMER_DEADLINE' }) + '\n');
    process.exit(124);
  }, left);
  try {
    const result = await source.prime(config, dir, { ...options, signal: signal.signal });
    if (Date.now() >= stop) fail('K8S_PRIMER_DEADLINE');
    if (result.state === 'synthetic-data-primed') {
      const roster = read(dir, 'tenants.json'), roots = new Map(saved.map(row => [row.id, row.rootSecret]));
      if (roster.version !== 1 || result.tenants !== expectedCount || roster.tenants?.length !== expectedCount ||
          new Set(roster.tenants.map(row => row.id)).size !== expectedCount ||
          roster.tenants.some(row => !expected.has(row.id) || row.host !== expected.get(row.id) ||
            typeof row.dataToken !== 'string' || !row.dataToken || row.dataToken === row.managementToken ||
            row.dataToken === roots.get(row.id))) fail('K8S_PRIMER_ROSTER_CHANGED');
    }
    return result;
  } catch (error) {
    return diagnostic(error, source);
  } finally {
    clearTimeout(hard); clearTimeout(soft);
    process.removeListener('SIGTERM', cancel); process.removeListener('SIGINT', cancel);
  }
}

async function main() {
  const result = await commission({ app: process.cwd(), dir: process.argv[2] === '--verified-serving' ? '/run/ns-client' : '/run/ns-primer',
    configDirectory: '/run/ns-primer', contractFile: '/run/ns-overlay/source-contract.json', env: process.env, args: process.argv.slice(2) })
    .catch(error => diagnostic(error));
  process.stdout.write(JSON.stringify(result) + '\n');
  process.exitCode = result.error ? 1 : result.state === 'synthetic-data-primed' ? 0 : 2;
}

if (require.main === module || process.argv[1] === '-') main();
module.exports = { commission, diagnostic };
