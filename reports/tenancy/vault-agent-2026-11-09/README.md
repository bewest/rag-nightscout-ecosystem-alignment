# Vault Agent sidecar: tokenFile in core and the Compose overlay (2026-11-09)

*Dated measurement record (contributor-facing). Never edited after capture. Queue items
`MT-VAULT-TOKEN-FILE` and `DEPLOY-VAULT-AGENT`, milestone M6c. Decision of record:
`releases/cgm-remote-monitor-16.0.0/decisions.md` anchor `vault-agent-sidecar`.*

## Anchors (read from `git log` / `docker image inspect` at the time of writing)

| tree | commit |
|---|---|
| cgm-remote-monitor base | `ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364` (`official/workspace/multitenant-20261102`) |
| cgm-remote-monitor branch `codex/vault-token-file-20261109` head | `0c5479584a39f68edb6b1eb2e1228129eb9722ac` (one commit on the base); worktree `externals/work/crm-vault-token-file-20261109`, local, unpushed |
| nightscout-deploy before | `75f0f61e61c04461b7285f9ea95419768734ee4f` |
| nightscout-deploy after | `cda38265d45a03763c6b826122f7badb7e1df86a` (on top of a peer's `b3b29dfe`, see traps) |
| alignment `main` at start / at writing | `9029fb6dd82b277fb92419bdc1ef9bbed7a21749` / `922fd5f8ea4ff3ac3a71eb21192a7fdf279dda41` |
| Vault image | `hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2` (image id `8794a735d581`, reports `Vault v2.2.1`); same digest as the imported `compose.yaml` |
| application image for the run | `nightscout-multitenant-vault-agent:local`, id `b6f56d13f7db`, label revision `0c5479584a39…` |

## A. Core: `tokenFile` alternative (MT-VAULT-TOKEN-FILE)

Brief mismatch, measured: at `ed2ced00` the only application `getToken` call site is
`lib/server/serve/preview-config.js:131`. `lib/human-session/access-config.js`,
`lib/server/serve/owner-credential-config.js` and `lib/secrets/vault-access-signing.js` named
in the brief do not exist at `ed2ced00` (`git cat-file -e` fails); they were added by
`eadf41f8 Bind human sessions to asymmetric access authority`, which is on
`codex/next-batch-integration-20261107`, `codex/owner-oidc-combined-20261107` and
`codex/shared-oidc-sessions-20261107`, not on the base. The change was made at the one real site;
the three later sites need the same `tokenEnv | tokenFile` treatment when their branch joins
(follow-up, below).

Change (`lib/server/serve/preview-config.js`): `tenant.vault` accepts exactly one of `tokenEnv`
(unchanged behaviour) or `tokenFile`; both or neither refuse at load; `tokenFile` must be a
normalized absolute path (relative, empty, trailing slash, `..`, non-string refuse). The sink is
read with `fs.promises.readFile` on every provider call, trimmed, must be non-empty, ≤ 4096 bytes,
no whitespace; any failure throws `SECRETS_PROVIDER_UNAVAILABLE` (the Transit client already maps
a throwing `getToken` to the same code). Several tenants may share one `tokenFile`; `tokenEnv`
uniqueness is unchanged. Load-time check is shape only: the sink is not required to exist at
load, so a sidecar that starts a moment later does not refuse the api (coordinator may tighten).
`lib/secrets/vault-transit.js` untouched. Test registered in `tests/tiers.json` (unit tier).

| check | command | result (from output) |
|---|---|---|
| new unit test | `node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js … tests/preview-vault-token-file.test.js` | `5 passing (53ms)` |
| ablation 1: cache the sink at load | same | `3 passing, 2 failing` (test 4 "rewritten token" and test 5 at load: readFileSync on the absent sink) |
| ablation 2: fall back to `source.TF_VAULT_0` when the sink is unreadable | same | `4 passing, 1 failing` — `AssertionError: Missing expected rejection` at test 5 |
| restored | same | `5 passing` |
| related unit files (`realtime-bootstrap`, `owner-preview`, `operation-cohort`, `secrets`) | mocha, 4 files | `44 passing` |
| `npm run test:tiers` | | `# 585 test files, 8 tiers: ok` |
| `npx eslint` on the two files | | 0 errors, 8 warnings (`security/detect-non-literal-fs-filename`, same class as pre-existing lines 79/81) |
| `npm run test:affected -- --since ed2ced00` (3 changed files, 35 implicated, 28 run) first run | host MongoDB 3.6 on 27017 | unit `191 passing`; harness `27 passing`; integration `4 passing, 69 pending, 17 failing`, every failure `MongoIncompatibleServerError … wire version 6` in boot-path tests (`start-paths`, `headless-test-server`, production safety check); unrelated to the change |
| same, second run | `mongo:7.0.43` container on 127.0.0.1:27417, `CUSTOMCONNSTR_mongo` repointed | unit `191 passing`; harness `27 passing`; integration `24 passing, 69 pending`, 0 failing, `exit=0` |

## B. Deploy: Vault Agent overlay (DEPLOY-VAULT-AGENT)

Files in nightscout-deploy: `bindings/compose/vault-agent/{compose.vault-agent.yaml, agent.hcl,
vault-agent-bootstrap.js, vault-agent.sh, README.md}`, `providers/secrets/vault-agent/README.md`,
a wave-3 "Vault service login" row and a status row in `docs/roadmap.md`. The imported tree
`bindings/compose/multitenant` is unchanged: `tools/compose-identity-check.sh <core>` → `ok`
twice, tree `8be3d761cbe592428357d6cee29612affafe4122`; `npm test` → `0 targets checked, 0 failing`.

Mechanism: the override adds `vault-agent` (same digest, `vault agent -config=…`, runs as the
runtime uid 1000 so it reads 0600 state files and writes a 0600 sink), a one-shot
`vault-agent-bootstrap` step (application image, private network) and one read-only mount
`…/vault-agent/sink:/run/ns-vault:ro` on `api`, `realtime`, `evaluator`, `tenant-admin`; `api`
depends on the Agent being healthy (sink non-empty). The step reads the root token and layout the
imported bootstrap left in `/state/bootstrap/`, enables AppRole, writes one policy that is the
union of the imported per-tenant policies read back from Vault plus `auth/token/renew-self`
(update) and `auth/token/lookup-self` (read), creates the role (`token_no_default_policy`,
`secret_id_num_uses=0`, `secret_id_ttl=24h`, TTLs from env), writes `role_id` and `secret_id`
(0600) to `/state/vault-agent/creds/`, and rewrites `/state/api/config.json` so each tenant's
`vault` block carries `tokenFile: /run/ns-vault/token` instead of `tokenEnv` (dropping
`NS_VAULT_0/1` from `env.json` unless `NS_VAULT_AGENT_KEEP_ENV_TOKENS=1`). `agent.hcl` uses
`remove_secret_id_file_after_reading = true`; the Agent keeps the value in memory for
re-authentication after `token_max_ttl`, and a restarted Agent needs `vault-agent.sh … secret-id`.

### Measured run

Project `nightscout-multitenant-vault-agent`, port 18090, private state in the session scratch
directory (removed afterwards), `NS_VAULT_AGENT_TOKEN_TTL=2m`, `NS_VAULT_AGENT_TOKEN_MAX_TTL=24h`,
`NS_VAULT_AGENT_KEEP_ENV_TOKENS=1`. Probe: `GET /api/v2/authorization/request/<synthetic legacy
token>` through nginx with the tenant `Host`, which the api serves only after Transit calls on
that tenant's keys; status codes only were recorded. The run script and the log live in the
session scratch directory; excerpts below are verbatim apart from redaction.

```
== 2026-11-09T20:03:32Z UP (TTL 2m, max 24h, env tokens kept as control)
{"state":"synthetic-demo-provisioned","sourceCommit":"0c5479584a39f68edb6b1eb2e1228129eb9722ac"}
{"state":"vault-agent-provisioned","role":"nsdemo_vault_agent","policy":"nsdemo_vault_agent","tokenTtl":"2m","tokenMaxTtl":"24h","credentials":"/state/vault-agent/creds/{role_id,secret_id}","sink":"/run/ns-vault/token","envTokensKept":true}
== 2026-11-09T20:03:51Z T0: sink sha c66bb9c2791d3964; creds dir: role_id
tenant A status 200 … tenant B status 200
(sink token) lookup-self ok: creation_ttl 120, renewable true, type service; renew-self ok: lease_duration 120
== 2026-11-09T20:06:22Z T0+150s (> 2m TTL): sink sha c66bb9c2791d3964
tenant A status 200 … tenant B status 200
agent log: 20:03:41 authentication successful / token written / renewed auth token; 20:05:08 renewed auth token
== 2026-11-09T20:06:22Z CONTROL: stop the Agent, wait past TTL
   env.json NS_VAULT_* keys present: NS_VAULT_0,NS_VAULT_1
== 2026-11-09T20:08:52Z stopped+150s: sink sha c66bb9c2791d3964 (unchanged, expired token)
tenant A status 503 keys error … tenant B status 503 keys error
== 2026-11-09T20:08:53Z RECOVERY: re-issue secret_id, start the Agent
{"state":"secret-id-reissued","location":"/state/vault-agent/creds/secret_id"}
== 2026-11-09T20:08:56Z agent health: healthy; sink sha 9eebcf858a079a47; creds dir: role_id
tenant A status 200 … tenant B status 200
```

Verdicts:

| claim | verdict | basis |
|---|---|---|
| (a) a Transit-backed call succeeds after the token TTL has passed, by renewal | **reproduced** | token issued 20:03:41Z, TTL 120 s; `renewed auth token` 20:05:08Z; sink hash unchanged; HTTP 200 at 20:06:22Z |
| (b) control: Agent stopped past TTL → next call fails closed, no environment fallback | **reproduced** | HTTP 503 for both tenants at 20:08:52Z with `NS_VAULT_0/1` present in the api environment and the sink holding the expired token. That the 503 is `SECRETS_PROVIDER_REFUSED` (Vault 403 on the expired token) rather than `_UNAVAILABLE` is read-derived: the api logs no provider lines |
| (c) recovery after `secret-id` + `agent start` | **reproduced** | healthy in 4 s, sink hash changed, HTTP 200 at 20:08:56Z |
| the imported restore demo passes through the overlay | **reproduced** | `{"demo":"tenant-local-logical-restore","state":"passed"}`, exit 0 |
| `secret_id` removed after the first read | **reproduced** | creds dir lists `role_id` only after `up` and after recovery |

Finding from the first run (before the policy fix): with `token_no_default_policy` the Agent's
token got `403` on `auth/token/renew-self` (and `lookup-self`); the Agent logged `lifetime watcher
done channel triggered, re-authenticating` at 20:01:01Z (88 s into a 120 s TTL) and re-authenticated
with its cached `secret_id`; calls still succeeded (HTTP 200 at 20:02:08Z) but by re-login, not
renewal. The policy now grants the two self paths; run two above shows `renewed auth token`.

### UNMEASURED

- Re-authentication after `token_max_ttl` with the in-memory `secret_id` (run used 24 h). The
  first run's re-auth at 20:01:01Z is evidence the cached path works, not a max-TTL measurement.
- Agent behaviour across a Vault seal/unseal cycle (`demo.sh up` re-running the imported
  bootstrap to unseal).
- The `tokenFile` path in `realtime`, `evaluator`, `tenant-admin`: mounted, but at `ed2ced00`
  those roles make no Vault calls.
- The three later call sites (`eadf41f8` branches) are untouched.
- `tools/compose-overlay.sh` with a branch head: the script pins the recorded commit, so the run
  did its two steps by hand (`git worktree add --detach <tree> 0c547958`; `cp -a` of the imported
  tree). The copy was byte-identical, so `build.js`'s clean-source check passed.

## Design point for the maintainer (not decided here)

The imported bootstrap mints one token per tenant with a per-tenant Vault policy. One Agent has
one login, so the overlay creates one AppRole whose policy is the union of those per-tenant
policies: every serving process holds a token that reaches every tenant's Transit keys on the
mount, and tenant separation at Vault moves to the application's authority layer and RLS (the
api selects the tenant's key from the tenant's config after the request is bound to a tenant).
Gained: no login or renewal code in core, rotation without restarts, one credential custody per
host, the same shape as a Kubernetes native sidecar. Alternative keeping Vault-side separation:
one Agent and one sink per tenant (core's `tokenFile` already allows a distinct path per tenant;
cost one container per tenant). Stated in `bindings/compose/vault-agent/README.md`; the decision
belongs in `releases/cgm-remote-monitor-16.0.0/decisions.md`.

## Traps met

1. **Peer commit swept untracked files.** nightscout-deploy moved from `75f0f61` to `b3b29dfe`
   (licence change) while this lane worked; that commit contains the first version of this lane's
   untracked overlay files and the roadmap edit. Symptom: `git status` suddenly showed only two of
   the lane's files modified. Avoidance: in a shared checkout, commit new files early or write
   them in a worktree; never `git add -A`.
2. **Host MongoDB 3.6 on 27017** fails 17 boot-path tests in `test:affected` with a wire-version
   refusal; use a dedicated `mongo:7` container and repoint `CUSTOMCONNSTR_mongo` (memory
   `local-mongod-is-3-6`).
3. **Agent token without the default policy cannot renew itself**; grant `renew-self` and
   `lookup-self` explicitly or the Agent silently re-authenticates each TTL.
4. **Brief's call-site list was read-derived from a later branch**; two of three files do not
   exist at the pinned base.
5. **Shared `demo.sh` project name** is fixed; the wrapper uses its own project name and env file
   so a plain demo on the same host is untouched.
