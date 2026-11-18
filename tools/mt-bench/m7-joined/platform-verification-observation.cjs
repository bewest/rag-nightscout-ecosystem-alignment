'use strict';

// Run inside the owned admin container. The selected core classifies the
// diagnostic. Keep the remaining private inspection response inside the process.
const path = require('node:path');

function observation(snapshot, read) {
  const operation = snapshot?.operation;
  if (snapshot?.version !== 1 || operation?.status !== 'FAILED' ||
      operation.code !== 'PLATFORM_VERIFICATION_FAILED') {
    return { status: 'UNMEASURED', reason: 'NO_FAILED_OPERATION' };
  }
  const diagnostic = read({ verificationDiagnostic: operation.diagnostic });
  return diagnostic ? { status: 'OBSERVED', ...diagnostic }
    : { status: 'UNMEASURED', reason: 'NO_CLASSIFIED_DIAGNOSTIC' };
}

async function main() {
  const { read } = require(path.resolve('lib/server/serve/platform-verification-diagnostic'));
  const response = await fetch('http://admin:1342/v1/platform-verification', {
    method: 'GET', redirect: 'error', signal: AbortSignal.timeout(2500)
  });
  if (!response.ok) return { status: 'UNMEASURED', reason: 'ADMIN_READ_REFUSED' };
  return observation(await response.json(), read);
}

main().then(value => console.log(JSON.stringify(value)), () => { process.exitCode = 1; });
