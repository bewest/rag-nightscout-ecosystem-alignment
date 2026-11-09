<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — MT-VAULT-TOKEN-FILE

**M6c: read the Vault token from a sink file per call (Vault Agent
compatibility)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/vault-token-file-20261109` |
| base | `workspace/multitenant-20261102@ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-VAULT-TOKEN-FILE` is the measurement |
| semver | `minor` |

## What this changes

Three getToken call sites (lib/server/serve/preview-config.js, lib/human-
session/access-config.js, lib/server/serve/owner-credential-config.js) gain a
`tokenFile` alternative to `tokenEnv`, read at call time. Exactly one of the
two must be configured. No Transit client change.

## Why that semver

additive configuration on the preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 5000 --require `** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-vault-token-file-20261109`

tokenFile unit family on branch head 0c547958: per-call sink read picked up
after rewrite; both-set and neither-set refuse at load; unreadable or empty
sink fails SECRETS_PROVIDER_UNAVAILABLE with no env fallback. 5 passing on
2026-11-09. Ablations recorded in the report: load-time cache 2 failing, env
fallback 1 failing, restored 5 passing.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Decision vault-agent-sidecar (2026-11-09). Small core change; the sidecar is
DEPLOY-VAULT-AGENT. 2026-11-09 (reproduced): implemented at the one getToken
site that exists at ed2 (lib/server/serve/preview-config.js); the other three
sites named in the brief live on the owner/OIDC candidate branch and get the
same shape at MT-M6A-JOIN. test:affected on mongo:7: unit 191 / harness 27 /
integration 24 passing, 0 failing. Report reports/tenancy/vault-
agent-2026-11-09/.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-VAULT-TOKEN-FILE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
