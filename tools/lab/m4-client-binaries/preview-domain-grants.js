'use strict';

// The archived application's reviewed catalogue selects its grant contract.
// No live-schema guess or newest-checkout helper is substituted for that source.
module.exports = function domainGrants ({ load, catalogue, logical, namespace, role }) {
  const identifier = /^[a-z][a-z0-9_]{0,62}$/;
  if (typeof load !== 'function' || [logical, namespace, role].some(value => typeof value !== 'string' || !identifier.test(value))) {
    throw new TypeError('Explicit selected source and fixture grant identifiers required');
  }
  const files = load('lib/migrations/catalogue').validateCatalogue(catalogue);
  const conversions = files.filter(file => file.operation?.kind === 'tenant-insertion-v1');
  if (!conversions.length) return Object.freeze([
    `GRANT SELECT, INSERT, UPDATE, DELETE ON ${namespace}.${logical} TO ${role}`,
    `GRANT USAGE ON ALL SEQUENCES IN SCHEMA ${namespace} TO ${role}`
  ]);
  if (conversions.length !== 1 || conversions[0].operation.domain !== logical) throw new Error('Fixture counter catalogue domain mismatch');
  const selected = load('lib/tenant-lifecycle/tenant-insertion-sql').build({ namespace, domain: logical });
  return Object.freeze([
    `GRANT SELECT, UPDATE, DELETE ON ${namespace}.${logical} TO ${role}`,
    ...selected.servingGrants(role), selected.verifyGrants(role)
  ]);
};
