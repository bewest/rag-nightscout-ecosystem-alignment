# Vault Transit feasibility lab

Implements the first bounded check for `MT-SECRETS-CONTRACT`, under the
[multitenant roadmap](../../../docs/30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md).
Synthetic payloads and disposable loopback Vault only. The harness creates
an isolated random mount, policies and consumer tokens, and removes only those
resources on completion. It does not inspect existing secrets.

Run a disposable Vault development container with a randomly generated root
token and a loopback-only published port. Pass its address and token through
`VAULT_ADDR` and `VAULT_TOKEN` (never commit them), then:

```sh
node tools/lab/vault-transit/harness.js
```

Nonzero exit means failure. Successful output contains check names and the
Vault version, never tokens, key material, ciphertext or revealed values.
Do not treat development-mode storage, its root bootstrap token or HTTP as a
production configuration.

The lab checks real Transit encryption/HMAC, non-exportability, scoped ACL
refusals, wrong-key failure, rotation/rewrap and token revocation. A deliberately
broader consumer demonstrates that the cross-tenant check detects an overbroad
policy. The application still needs an authenticated tenant/consumer boundary,
ciphertext/reference store, JWT encoding/version policy, audit and operational
acceptance. Generic Transit decrypt is not an owner reveal API.
