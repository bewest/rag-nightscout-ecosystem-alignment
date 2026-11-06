'use strict';
// Owned lab process only. Deliberately no public CLI/config field for selection.
const path = require('node:path');
const assert = require('node:assert/strict');
const req = name => require(path.join(process.env.SELECTED_OWNER_ARCHIVE, name));
const { CATALOGUE } = require('./contract');
async function main () {
  assert.ok(['selected', 'reference'].includes(process.env.SELECTED_OWNER_LAB_MODE));
  const config = req('lib/server/serve/preview-config').load(process.env);
  assert.equal(config.namespaces.authorization, 'preview_auth');
  const { Client } = req('node_modules/pg');
  const { catalogueDigest } = req('lib/subject-admin/owner-policy');
  const admin = new Client({ connectionString: process.env.SELECTED_OWNER_OPERATOR_PG });
  await admin.connect();
  try {
    for (const tenant of config.bindings.keys()) {
      const row = await admin.query('SELECT anonymous_roles FROM preview_auth.tenant_authorization_config WHERE tenant_id=$1', [tenant]);
      assert.deepEqual(row.rows.map(r => r.anonymous_roles), [['denied']], 'existing explicit denied-anonymous fixture required');
      const update = await admin.query("UPDATE preview_auth.tenant_authorization_roles SET permissions=$2 WHERE tenant_id=$1 AND name='viewer'", [tenant, CATALOGUE]);
      assert.equal(update.rowCount, 1);
      await admin.query('INSERT INTO preview_auth.tenant_owner_policy(tenant_id,catalogue_digest,ceiling) VALUES ($1,$2,$3)',
        [tenant, catalogueDigest(CATALOGUE), CATALOGUE]);
    }
  } finally { await admin.end(); }
  const runtime = await require('./bootstrap').boot(config, { selected: process.env.SELECTED_OWNER_LAB_MODE === 'selected' });
  const server = runtime.app.listen(0, '127.0.0.1', () => console.log('Listening for role api on 127.0.0.1:' + server.address().port));
  process.once('SIGTERM', () => server.close(() => runtime.close().then(() => process.exit(0), () => process.exit(1))));
}
if (require.main === module) main().catch(() => { console.error('selected subject lab setup refused'); process.exitCode = 1; });
module.exports = { main };
