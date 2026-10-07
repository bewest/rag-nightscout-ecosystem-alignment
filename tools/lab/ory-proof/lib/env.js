'use strict';
// Lab endpoints and the runtime secrets file. Nothing secret is committed; .secrets.env is generated.
const fs = require('fs');
const path = require('path');

function secrets () {
  const p = path.join(__dirname, '..', '.secrets.env');
  const out = {};
  for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
    const m = /^([A-Z_]+)=(.*)$/.exec(line.trim());
    if (m) out[m[1]] = m[2];
  }
  return out;
}

const LAB_PORT = parseInt(process.env.LAB_PORT || '44480', 10);
module.exports = {
  LAB_PORT,
  ORIGIN: (host) => `http://${host}:${LAB_PORT}`,
  AUTH_HOST: 'auth.apex.test',
  HYDRA_HOST: 'hydra.apex.test',
  CONTROL_HOST: 'lab.control',
  tenantHost: (slug) => `${slug}.user-content.apex.test`,
  // D10: host -> slug is a configured rule with exactly one capture group
  TENANT_HOST_RULE: process.env.TENANT_HOST_RULE || '^([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\\.user-content\\.apex\\.test(?::\\d+)?$',
  KRATOS_PUBLIC: process.env.KRATOS_PUBLIC || 'http://127.0.0.1:44433',
  KRATOS_ADMIN: process.env.KRATOS_ADMIN || 'http://127.0.0.1:44434',
  HYDRA_PUBLIC: process.env.HYDRA_PUBLIC || 'http://127.0.0.1:44444',
  HYDRA_ADMIN: process.env.HYDRA_ADMIN || 'http://127.0.0.1:44445',
  MAILPIT: process.env.MAILPIT || 'http://127.0.0.1:44825',
  pgUrl: (db) => `postgres://lab:${secrets().PG_PASSWORD}@127.0.0.1:54353/${db}`,
  secrets
};
