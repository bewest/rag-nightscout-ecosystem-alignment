'use strict';

// This script executes inside the serving container. Only the fields needed by
// the independent SQL reader leave it. DSNs, credentials and other role
// settings stay in the process.
const path = require('node:path');

function projection(root, role, environment) {
  const settings = require(path.join(root, 'lib/server/serve/deployment-settings'));
  const values = settings.withSecrets(environment);
  const config = settings.configuration(role, values);
  const sqlRoles = [...new Set(Object.entries(values)
    .filter(([name, url]) => name.endsWith('_PG') && typeof url === 'string' && /^postgres(?:ql)?:/.test(url))
    .map(([, url]) => decodeURIComponent(new URL(url).username)).filter(Boolean))];
  if (role === 'realtime') return { completedOutput: config.completedOutput, sqlRoles };
  if (role !== 'evaluator') throw new Error('M7_COMPLETION_ROLE');
  const { clock, checkpoint, entries } = config.postgres.namespaces;
  if (environment.NS_INPUT_TRANSPORT === 'writer-driven') {
    const { devicestatus, treatments } = config.postgres.namespaces;
    return { inputTransport: 'writer-driven', postgres: { namespaces: { clock, checkpoint, entries, devicestatus, treatments } },
      trustedWorker: { activity: config.trustedWorker.activity }, consumer: config.consumer, sqlRoles };
  }
  const { generation, slot, streamRole, recovery } = config.pgstream;
  const selection = settings.nativeSelection(settings.layout(values));
  return { postgres: { namespaces: { clock, checkpoint, entries } },
    pgstream: { generation, slot, recovery: Boolean(recovery) }, trustedWorker: {activity: config.trustedWorker.activity},
    consumer: config.consumer, contractDigest: selection.contractDigest, streamRole, sqlRoles };
}

console.log(JSON.stringify(projection(process.cwd(), process.argv[2], process.env)));
