# Registry, persisted realtime settings and durable connector focused evidence

Captured 2026-11-12 UTC (2026-11-11 local). **Reproduced focused capability evidence**,
not joined M7 acceptance. Parent integration owns the full, browser and enabled-corpus
campaign after all planned capabilities join. This immutable record supports the
provisioning retry and registry realtime settings defect findings and the adopted
D15 connector configuration capability.

## Source and instrument attribution

| Boundary | Exact application source | Instrument and observed result |
|---|---|---|
| Registry stepA, human keys/origins and retry completeness | `cced60f193073b4b66b43eb70c48cb3bf45f90fd` | Nine focused files:88 pass; six native files:49 pass. Runtime bytes matched the committed source before the commit. |
| Persisted realtime settings repair | `1c49ea6f2488cb4fdbe5e2ae3f1ae2d910342a29` | Clean git archive of this exact leaf, native settings discriminator:1 pass. |
| Durable connector sources | `718a6bee184b97a955ffd002b95f00d9d4d2c1c4` | Eight native files:58 pass/25s; nine focused files:130 pass/2s. Runtime bytes matched this source before the commit. Includes earlier registry and settings repairs. |

Alignment anchor at report creation: `7d3399ddc731b1719fceee49317476aeb6eec897`.
Node observed `v22.23.4`. Tests load shipping modules directly from the selected core
tree. The connector/registry native runner used the pinned PostgreSQL image
`postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a`.
The registry fixture used Vault
`hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2`.
Each run created uniquely owned disposable containers, synthetic roles/schemas and
credentials held in child environment only; fixtures and runner removed their own
resources. No shared database was used. Native listeners bound loopback only.

The archived [native runner](instruments/native-run.cjs),
[registry controls](instruments/registry-controls.py) and
[connector controls](instruments/connector-controls.py) are the actual local
instruments. Test implementations belong to the quoted application commits.
Raw logs normalize the machine checkout prefix to `<core>`; assertion messages,
relative source locations and results are preserved. Synthetic schema names are
fixture output. No tenant data or plaintext credential values are included.

## Findings and controls

### Provisioning retries must refuse incomplete existing tenants

**Mechanism read-derived from the pre-repair implementation:** registry tenant/host
presence was sufficient for an `existing` result even if bootstrap state was
missing. The repair checks structural completeness of the registry/key, control,
settings and checkpoint families in the provisioning transaction. It refuses
`TENANT_PROVISION_INCOMPLETE`/409 without recreating missing rows or replacing an
existing root secret. Legitimate later changes and audit retention are permitted.

**Controlled reproduction:** disabling only the new completeness decision made all
four native `PV_EXISTING_COMPLETE_*` plants return `existing` rather than refuse:
[0 pass,4 semantic failures](logs/registry-control-incomplete.log). This is a repair
ablation on the completed source, not a claim that a pristine original checkout
was separately measured. Restored source passes in the
[49 native check capture](logs/registry-completion-native-restored.log), and again
in the final [58 native check capture](logs/connector-registry-final-native.log).

An initial activity plant hit a dependent audit foreign key before exercising the
assertion; the fixture was corrected to remove that synthetic dependent audit
first. The setup error was not counted as a semantic failure. The four-case
ablation above is the corrected capture.

### Registry realtime must apply committed D15 settings

**Reproduced:** valid stored mmol units, plugin selection and complete threshold
settings reached API HTTP status while the registry realtime entry remained on
mg/dl defaults. The [pre-repair discriminator](logs/registry-realtime-settings-before.log)
failed with `'mg/dl' !== 'mmol'`. The repair uses a separate readonly D15 presentation
reader for realtime entries and staged live admission; missing state refuses.

The native discriminator reads actual PostgreSQL settings, uses actual HTTP API
status serialization, and compares the actual realtime protocol's
`dataUpdate.status.settings` serialization. It also checks another tenant's defaults,
updates changing effective identity, and missing-state refusal. Projection rows and
socket authority are synthetic; this is not a complete clinical-stream or live
Socket.IO compatibility campaign. The isolated exact-leaf archive
[passes](logs/registry-rt-leaf-native.log). A deliberate constant-settings mutation
[reproduces the units mismatch](logs/connector-control-constant-rt-settings.log),
and the restored final native bundle passes.

### Human keys, resolved origins and bounded provider discovery

The registry capability uses separate human-data and human-management Vault key
purposes, current registry key revisions and current durable session authority.
Origins come from registered host resolution; no internal or unknown forwarded
alias becomes an OIDC origin. Native checks use actual Vault signing, PostgreSQL
sessions and key revocation, not an external IdP.

The restored [88 focused checks](logs/registry-completion-focused-restored.log)
and 49 native checks cover the selected capability. Authored controls were semantic
red then restored:

| Deliberate break | Observed failure |
|---|---|
| Skip registered-origin admission | [Missing expected rejection](logs/registry-control-alias-origin.log) |
| Ignore changed human key entry revision | [Old token accepted; missing rejection](logs/registry-control-human-key-refresh.log) |
| Cache OIDC provider by tenant alone | [Second valid alias403 instead of200](logs/registry-control-origin-binding.log) |
| Remove settled provider cache bound | [3 retained entries instead of2](logs/registry-control-origin-cache-bound.log) |

### Durable connector definitions and bounded refresh

Definitions/history are D15 restorable tenant data, separate from operational tenant
membership. Stable source IDs, generation CAS, idempotent retries and tombstones
retain references to three distinct existing tenant secrets. The writer can inspect
reference IDs and cannot read ciphertext. Metadata writes join the shared tenant
maintenance lock, check active phase inside the transaction, and increment registry
revision once. No clinical-write cost is added.

Registry worker assignment refresh uses one aggregate revision read on unchanged
polls. Changed revisions rebuild bounded per-tenant source pages and atomically
publish a stable snapshot. Drivers retain bookmark/session when decrypted values
are unchanged; each registry poll rereads references. Actual source/output requests
recheck current generation and activity eligibility. Paused polling continues;
suspended/deleted/disabled or configuration-refused work sends no new request.

Native tests exercise CRUD/CAS, tenant RLS, foreign references, ciphertext refusal,
actual admin HTTP, refresh/add/remove/alias, maintenance lock/phase refusal, history
FORCE-RLS refusal and exact alias-definer body admission. A held-open source writer
was classified by the actual restore backend census. Granting it clinical-clock
write privilege made unknown-backend refusal; revoking the grant restored acceptance.
That census uses controlled peer reporting for other actual fixture backends; it
is not a full real-role restore acceptance.

Seven authored mutations were restored after their semantic red captures:

| Deliberate break | Independent symptom |
|---|---|
| Reuse connector before rereading references | [Decrypt call count fails](logs/connector-control-credential-reread.log) |
| Skip actual HTTP request admission | [Missing expected rejection](logs/connector-control-request-admission.log) |
| Ignore changed source generation before request | [Missing expected rejection](logs/connector-control-source-generation.log) |
| Bypass generation CAS | [Stale update accepted](logs/connector-control-generation-cas.log) |
| Ignore failed maintenance lock acquisition | [Write accepted; missing rejection](logs/connector-control-maintenance-lock.log) |
| Enumerate on unchanged revision | [Enumeration count3 instead of2](logs/connector-control-normal-revision-cost.log) |
| Return constant realtime presentation | [mg/dl instead of mmol](logs/connector-control-constant-rt-settings.log) |

Intrinsic native controls also disable history FORCE RLS, replace the exact alias
function body, attempt foreign-tenant access and broaden clock privileges, then
restore each condition. The final restored source passes
[58 native](logs/connector-registry-final-native.log) and
[130 focused](logs/connector-registry-final-focused.log) checks. The private
connector-inspection strict schema deliberately becomes version2 for source identity,
generation and configuration-refusal status; peer upgrade must be coordinated.
Other private versions and browser/uploader data protocols are unchanged here.

## Final guards and limits

Reproduced final inventory:678 test files/8tiers. Changed-source lint:
[0 errors,3 warnings](logs/connector-registry-final-lint.log), two regex warnings
and one synthetic-fixture chmod warning. No-trigger-NOTIFY guard:13 trigger bodies,
2 trigger functions,0 notifying functions. The existing write-boundary guard checks
9 clinical adapter entry points and canonical socket delegation; it is not a claim
that all metadata writers are covered. Diff whitespace check passed.

The lifecycle/deployment fixture census expectations deliberately increased by the
two registered source tables (49→51 and50→52); both source/history families are
populated for both synthetic tenants. Initial assumed parameter support in the
registry global scan API was rejected; alias lookup instead uses an explicit
bound-tenant transaction. No scanner exception or census weakening was used.

Full unit, browser, enabled-corpus, capacity, real external IdP, deploy bindings,
complete real-role restore and complete clinical frame compatibility remain
**UNMEASURED by this report**. Initial sandbox subprocess/listener refusals were
setup-only and rerun with the required local execution permissions. Earlier shared
cache or borrowed dependency use is not browser acceptance; no browser bundle was
loaded. Parent must join all planned changes before the comprehensive campaign.

## Reproduction commands

From a core checkout at the chosen source, with its dependencies installed and
Docker available, place the archived runner at `/tmp/registry-native-run.cjs` (the
control instruments use that path). The runner generates credentials and owns its
resources; it accepts test paths and Mocha flags. For the final native boundary:

```bash
node /tmp/registry-native-run.cjs \
  tests/tenant-registry.integration.test.js \
  tests/tenant-registry-provision.integration.test.js \
  tests/admin-provisioning.integration.test.js \
  tests/registry-tenant-set.integration.test.js \
  tests/api-registry.integration.test.js \
  tests/registry-human-session.integration.test.js \
  tests/connector-sources.integration.test.js \
  tests/registry-realtime-settings.integration.test.js
```

For the final focused boundary:

```bash
node node_modules/mocha/bin/mocha.js --fail-zero --reporter dot \
  tests/internal-api-contracts.test.js tests/internal-api-transport.test.js \
  tests/connector-sources.test.js tests/tenant-connector.test.js \
  tests/tenant-deployment-operations.test.js tests/tenant-lifecycle.test.js \
  tests/registry-realtime.test.js tests/provisioning-private.test.js tests/admin-role.test.js
```

Control scripts must run only in an owned disposable checkout; they mutate shipping
source temporarily and restore exact bytes in `finally`. They are evidence
instruments, not read-only queue gates. No remote write or push was performed.

Report-branch consistency: all24 links in this report resolve and diff whitespace
passes. `make queue-check` passes queue validation/coverage/generated checks but
fails the baseline link check on six references to the absent
`docs/30-design/tenancy/claimed-public-names-and-deploy-companion-2026-11-09.md`.
Those references predate this report and none is a report link. The report branch
uses the main workspace's ignored lane inventory for cwd validation; it does not
alter those worktrees. That baseline failure remains with the coordinator.
