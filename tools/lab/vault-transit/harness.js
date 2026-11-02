'use strict';

const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');

async function main () {
  const address = process.env.VAULT_ADDR;
  const root = process.env.VAULT_TOKEN;
  if (!address || !root) throw new Error('VAULT_ADDR and a disposable lab VAULT_TOKEN are required');
  const url = new URL(address);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.username || url.password) {
    throw new Error('This destructive synthetic lab requires a loopback Vault address without userinfo');
  }
  const mount = 'ns-lab-' + randomUUID();
  const policies = [];
  const tokens = [];
  const checks = [];
  let mounted = false;

  async function api (path, body, token = root, expected = [200, 204], method) {
    const response = await fetch(address + '/v1/' + path, {
      method: method || (body === undefined ? 'GET' : 'POST')
      , headers: { 'X-Vault-Token': token, 'Content-Type': 'application/json' }
      , body: body === undefined ? undefined : JSON.stringify(body)
      , signal: AbortSignal.timeout(10000)
    });
    assert.ok(expected.includes(response.status), path + ': unexpected HTTP ' + response.status);
    return response.status === 204 ? {} : response.json();
  }

  async function check (name, fn) {
    await fn();
    checks.push({ name, passed: true });
  }

  try {
    const health = await api('sys/health');
    await api('sys/mounts/' + mount, { type: 'transit' });
    mounted = true;
    for (const tenant of ['tenant-a', 'tenant-b']) {
      await api(mount + '/keys/' + tenant, { type: 'aes256-gcm96', exportable: false });
    }

    async function consumer (name, tenants) {
      const policyName = mount + '-' + name;
      const policy = tenants.map(tenant =>
        ['encrypt', 'decrypt', 'hmac', 'verify'].map(operation =>
          `path "${mount}/${operation}/${tenant}" { capabilities = ["update"] }`).join('\n')).join('\n');
      await api('sys/policies/acl/' + policyName, { policy });
      policies.push(policyName);
      const result = await api('auth/token/create', {
        policies: [policyName], no_default_policy: true, ttl: '5m', renewable: false
      });
      tokens.push(result.auth.client_token);
      return result.auth.client_token;
    }

    const a = await consumer('a', ['tenant-a']);
    const b = await consumer('b', ['tenant-b']);
    const broad = await consumer('control', ['tenant-a', 'tenant-b']);
    const plaintext = Buffer.from('synthetic-connector-secret').toString('base64');
    let ciphertext, hmac;

    await check('scoped encrypt/decrypt round trip', async function () {
      ciphertext = (await api(mount + '/encrypt/tenant-a', { plaintext }, a)).data.ciphertext;
      assert.equal((await api(mount + '/decrypt/tenant-a', { ciphertext }, a)).data.plaintext, plaintext);
      assert.notEqual(ciphertext, plaintext);
    });
    await check('other-tenant key paths refused by provider policy', async function () {
      await api(mount + '/decrypt/tenant-a', { ciphertext }, b, [403]);
      await api(mount + '/encrypt/tenant-b', { plaintext }, a, [403]);
      await api(mount + '/hmac/tenant-b', { input: plaintext }, a, [403]);
    });
    await check('wrong tenant key cannot decrypt copied ciphertext', async function () {
      await api(mount + '/decrypt/tenant-b', { ciphertext }, b, [400]);
    });
    await check('non-exportable key material stays inside Transit', async function () {
      await api(mount + '/export/encryption-key/tenant-a', undefined, root, [400]);
      await api(mount + '/export/hmac-key/tenant-a', undefined, root, [400]);
      await api(mount + '/keys/tenant-a', undefined, a, [403]);
    });
    await check('HS256-compatible HMAC and verification without exporting key', async function () {
      const input = Buffer.from('synthetic.header.payload').toString('base64');
      hmac = (await api(mount + '/hmac/tenant-a', { input, algorithm: 'sha2-256' }, a)).data.hmac;
      assert.match(hmac, /^vault:v\d+:[A-Za-z0-9+/]+=*$/);
      assert.equal(Buffer.from(hmac.split(':')[2], 'base64').length, 32);
      const verified = await api(mount + '/verify/tenant-a', { input, hmac, hash_algorithm: 'sha2-256' }, a);
      assert.equal(verified.data.valid, true);
      const otherTenant = await api(mount + '/verify/tenant-b', { input, hmac, hash_algorithm: 'sha2-256' }, b);
      assert.equal(otherTenant.data.valid, false);
      const changed = await api(mount + '/verify/tenant-a', {
        input: Buffer.from('changed').toString('base64'), hmac, hash_algorithm: 'sha2-256'
      }, a);
      assert.equal(changed.data.valid, false);
    });
    await check('consumer cannot change key configuration or rotate', async function () {
      await api(mount + '/keys/tenant-a/config', { exportable: true }, a, [403]);
      await api(mount + '/keys/tenant-a/rotate', {}, a, [403]);
    });
    await check('rotation and ciphertext rewrap preserve stored plaintext', async function () {
      await api(mount + '/keys/tenant-a/rotate', {});
      const rewrapped = (await api(mount + '/rewrap/tenant-a', { ciphertext })).data.ciphertext;
      assert.match(rewrapped, /^vault:v2:/);
      assert.equal((await api(mount + '/decrypt/tenant-a', { ciphertext: rewrapped }, a)).data.plaintext, plaintext);
      assert.equal((await api(mount + '/decrypt/tenant-a', { ciphertext }, a)).data.plaintext, plaintext);
    });
    await check('red control: broad consumer policy permits other-tenant decrypt', async function () {
      assert.equal((await api(mount + '/decrypt/tenant-a', { ciphertext }, broad)).data.plaintext, plaintext);
    });
    await check('revoked consumer credential fails closed', async function () {
      await api('auth/token/revoke', { token: a });
      await api(mount + '/encrypt/tenant-a', { plaintext }, a, [403]);
    });
    return {
      experiment: 'MT-SECRETS-CONTRACT / Vault Transit feasibility'
      , vaultVersion: health.version
      , checks
      , limits: [
        'Disposable development server; no production persistence, TLS, unseal/recovery or HA acceptance'
        , 'Provider ACL proof, not integrated Nightscout membership, JWT policy, ciphertext store or audit proof'
        , 'Broad service credentials still reach all permitted tenants; Transit does not infer caller tenant'
        , 'HMAC feasibility is not a complete legacy JWT encoding/key-version/rotation integration'
      ]
    };
  } finally {
    for (const token of tokens) {
      await api('auth/token/revoke', { token });
    }
    for (const policy of policies) {
      await api('sys/policies/acl/' + policy, undefined, root, [204], 'DELETE');
    }
    if (mounted) await api('sys/mounts/' + mount, undefined, root, [204], 'DELETE');
  }
}

main().then(result => console.log(JSON.stringify(result, null, 2))).catch(error => {
  console.error(error.name + ': ' + error.message);
  process.exitCode = 1;
});
