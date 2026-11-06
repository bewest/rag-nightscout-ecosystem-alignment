'use strict';
// Separate synthetic lab bootstrap, derived from preview-api at frozen 8713395.
// Never loaded by a shipping entry point. No production configuration selects this.
const path = require('node:path');
const sourceRequire = name => require(path.join(process.env.SELECTED_OWNER_ARCHIVE, name));
const { CATALOGUE, SUBJECT, readiness } = require('./contract');

const express = sourceRequire('node_modules/express');
const scope = sourceRequire('lib/server/serve/../../storage/tenant-scope');
const connect = sourceRequire('lib/server/serve/../../storage/postgres-connection');
const { createSecrets } = sourceRequire('lib/server/serve/../../secrets/component');
const { createPostgresSecrets } = sourceRequire('lib/server/serve/../../secrets/postgres');
const createLegacyAuthority = sourceRequire('lib/server/serve/../../secrets/legacy-postgres');
const createAuthority = sourceRequire('lib/server/serve/../../tenant-authorization/postgres');
const createAccessAuthority = sourceRequire('lib/server/serve/../../tenant-authorization/access-postgres');
const { createVerifier, createAuthentication } = sourceRequire('lib/server/serve/../../tenant-authorization/access-token');
const createDataAccess = sourceRequire('lib/server/serve/../tenant-app/data-access');
const createExchange = sourceRequire('lib/server/serve/../tenant-app/exchange');
const { createTenantApp } = sourceRequire('lib/server/serve/../tenant-app');
const postgresDomains = sourceRequire('lib/server/serve/postgres-domains');
const previewDomains = sourceRequire('lib/server/serve/preview-domains');
const { PreviewConfigError } = sourceRequire('lib/server/serve/preview-config');


async function boot (config, { selected }) {
  if (typeof selected !== 'boolean' || config.accessTokens) throw new Error('Explicit legacy subject-only lab selection required');
  const resources = [];
  let closed = false;
  async function close () {
    if (closed) return;
    closed = true;
    const results = await Promise.allSettled(resources.reverse().map(resource =>
      resource.end ? resource.end() : resource.close()));
    if (results.some(result => result.status === 'rejected')) throw new Error('preview storage shutdown failed');
  }
  try {
    await postgresDomains.readiness(config);
    scope.setTenancyMode('multi');
    const legacy = await createLegacyAuthority({
      connectionString: config.connectionString, namespace: config.namespaces.legacy
    });
    resources.push(legacy);
    const authority = await createAuthority({
      connectionString: config.connectionString, namespace: config.namespaces.authorization,
      ...(selected ? { ownerPolicy: { catalogue: CATALOGUE } } : {})
    });
    resources.push(authority);
    let accessTokens;
    if (config.accessTokens) {
      const access = await createAccessAuthority({ connectionString: config.connectionString,
        namespace: config.namespaces.access, authorityNamespace: config.namespaces.authorization });
      resources.push(access);
      accessTokens = { authenticate: createAuthentication({ verifyToken: createVerifier(config.accessTokens), snapshot: access.snapshot }) };
    }
    const persistence = await createPostgresSecrets({
      connectionString: config.connectionString, namespace: config.namespaces.secrets
    });
    resources.push(persistence);
    const connection = await connect({
      connectionString: config.connectionString, max: 4, connectionTimeoutMillis: 5000,
      statement_timeout: 5000, application_name: 'nightscout-preview-data'
    });
    resources.push(connection);
    await postgresDomains.assertServing(config, connection);
    // This capability is created only inside this process, for its configured
    // tenant/key bindings. A client principal or consumer never selects it.
    const secrets = createSecrets({
      ...persistence, maxTokenLifetimeSeconds: 28800,
      legacyAuthorityFor: tenant => legacy.read(tenant),
      providerFor: async tenant => {
        const provider = config.providers.get(tenant);
        if (!provider) throw new Error('unconfigured preview tenant');
        return provider;
      },
      authorize: async (identity, action) => {
        const binding = config.bindings.get(identity.tenant);
        if (!binding || identity.principal !== binding.principal || identity.consumer !== binding.consumer) return false;
        if (action.operation === 'decrypt') {
          const current = await legacy.read(identity.tenant);
          return !!current && current.reference.tenant === identity.tenant && current.reference.id === action.id;
        }
        return ['sign', 'verify'].includes(action.operation);
      }
    });
    for (const tenant of config.bindings.keys()) {
      const metadata = await legacy.read(tenant);
      if (!metadata || !metadata.reference || !await persistence.store.get(tenant, metadata.reference.id)) {
        throw new Error('incomplete preview root preparation');
      }
      // This fixture explicitly provisions one subject; readiness uses that subject.
      // Selected authority intentionally refuses root and anonymous principals.
      await readiness(authority, tenant, SUBJECT);
    }
    const verifierContext = tenant => config.bindings.get(tenant);
    const exchange = createExchange({ secrets, authority, verifierContext });
    const dataConnection = config.writeClock
      ? sourceRequire('lib/server/serve/../../storage/postgres-write-clock')(connection, config.namespaces.clock) : connection;
    const domains = await previewDomains({ config, connection: dataConnection, exchange });
    const unavailable = async () => { throw new Error('preview management is unavailable'); };
    const app = express();
    app.disable('x-powered-by');
    // No owner/operator listener or management route is enabled by this role.
    app.use(['/api/v1/tenant', '/api/v1/operator'], (req, res) => res.status(404).json({ error: 'NOT_FOUND' }));
    app.use(createTenantApp({
      resolver: config.resolver, dataRouter: domains.data,
      legacyRouter: domains.legacyRouter, rootRouter: domains.rootRouter,
      dataAccess: createDataAccess({ secrets, authority, verifierContext, accessTokens,
        collections: domains.v3Names, legacyCollections: domains.legacyNames, safeRoutes: domains.safeRoutes,
        derivedReads: config.legacyEnabled }),
      exchange,
      verifyCredential: async () => null, authorizeRequest: async () => false,
      tenantSettings: { read: unavailable, replace: unavailable, rollback: unavailable },
      subjectPolicy: { read: unavailable, replace: unavailable }
    }));
    return { app, close };
  } catch {
    await close();
    throw new PreviewConfigError('preview readiness or storage initialization refused; check operator preparation and credential privileges');
  }
}

module.exports = { boot };
