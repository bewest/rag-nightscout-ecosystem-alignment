'use strict';

const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');

// The pinned application supplies the same fixture seed used by its primer.
// The private controller forwards only the selected, already-issued DATA
// credentials (and each tenant's DATA JWT). No management credential enters the load Pod.
function install(demo, meta, credentials, directory) {
  if (!Number.isSafeInteger(meta.fixtureTenants) || meta.fixtureTenants < 1 ||
      !Array.isArray(credentials) || credentials.length !== meta.tenants ||
      meta.tenants < 1 || meta.tenants > meta.fixtureTenants) throw Error('ROSTER_COUNT');
  const aliases = new Map(demo.tenantIds(meta.fixtureTenants).map((id, i) => [id, demo.tenantAlias(i)]));
  const rows = credentials.map(pair => {
    const looping = meta.driverShape === 'looping-v1' || meta.driverShape === 'looping-v2';
    if (!Array.isArray(pair) || (looping ? pair.length !== 4 : pair.length < 2 || pair.length > 3)) throw Error('ROSTER_DATA');
    const [id, token, jwt, loopKind] = pair;
    const host = aliases.get(id);
    if (!host || typeof token !== 'string' || !token) throw Error('ROSTER_DATA');
    aliases.delete(id);
    const row = {id, host, token};
    if (jwt !== undefined && !(looping && jwt === null)) row.jwt = jwt;
    if (looping) {
      if (![null, 'loop', 'aaps', 'trio'].includes(loopKind)) throw Error('ROSTER_DATA');
      row.loopKind = loopKind;
    }
    return row;
  });
  const raw = JSON.stringify(rows);
  const digest = crypto.createHash('sha256').update(raw).digest('hex');
  if (digest !== meta.sha256) throw Error('ROSTER_CHANGED');
  const staging = path.join(directory, 'incoming');
  fs.writeFileSync(staging, raw, {flag: 'wx', mode: 0o400});
  fs.linkSync(staging, path.join(directory, 'tenants.json'));
  fs.unlinkSync(staging);
  return digest;
}

if (require.main === module) {
  try {
    if (!process.argv[2] || process.argv[2] !== process.env.NS_ROSTER_POD_UID) throw Error('POD_CHANGED');
    const demo = require('/opt/app/deploy/multitenant/demo-tenants');
    const meta = JSON.parse(fs.readFileSync('/inputs/fixture-data.json'));
    console.log(install(demo, meta, JSON.parse(fs.readFileSync(0)), '/roster'));
  } catch {
    console.error('K8S_NATIVE_LOAD_ROSTER_REFUSED');
    process.exitCode = 78;
  }
}

module.exports = {install};
