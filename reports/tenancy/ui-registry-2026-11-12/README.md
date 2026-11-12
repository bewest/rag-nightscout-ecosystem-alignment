# Registry-backed UI admission — 2026-11-12

Reproduced against deployment source `167332002bc2811b7b4bd656a9d9479e4fcf5554`
(`codex/ui-registry-20261112`, base parent5935b42), core source and instrumentation
`d20354797e368b03af171f4417ead60a6282d098`. Local/unpushed original history.

The standalone browser-page UI previously used a seed-generated static alias
projection. Version2 UI config selects the product registry resolver through a
dedicated lookup+revision identity, without tenant enumeration, registry attributes,
clinical/settings/secret grants or a static roster. Static version1 remains supported.
Parent owns generated role/config/environment/Compose binding and joined census.

```bash
NS_UI_TEST_CORE=/absolute/path/to/pinned/core node bindings/compose/multitenant/ui-registry.test.js
NS_UI_REGISTRY_NATIVE_TEST=1 NS_UI_TEST_CORE=/absolute/path/to/pinned/core node --test bindings/compose/multitenant/ui-registry.integration.test.js
```

`unit-final.log`: **4 passing**, no skips. Actual product resolver verifies positive
and negative revision cache invalidation, bounded positive/negative cache eviction,
unknown/private/untrusted forwarded selector refusal, explicit config/authority
refusals, bounded in-flight work and idempotent owned close. Invoke the unit file
as shown: a local Node22 `--test` invocation reported only file-level success;
that opaque run was not counted as executed unit evidence.

`native-final.log`: **1 passing compound native case**, no skips. Own PostgreSQL16
container with pinned image (source fixture records exact digest), no existing
services/Vault selected. Actual product registry catalogue/functions and connection,
actual UI HTTP handlers, core templates and existing production assets. The UI
identity cannot SELECT planted clinical data or registry rows or execute tenant
enumeration. An alias initially refused is registered while UI runs, then serves
HTML after revision observation. Private/internal names, unknown aliases and
cross-tenant forwarded selectors refuse. Modern theme, GET assets/no CORS wildcard,
POST refusal and credential-free health remain. Removing A refuses A while B serves.
Planted clinical-column SELECT and changed lookup owner refuse new startup. A real
UI CLI child exits0 on SIGTERM and its owned database sessions disappear. No
credential appears in child output. Observed registry commit→explicit poll→HTML
for a synthetic alias: **10 ms**; this tiny harness is not a deployment/capacity bound.

`freeze-revision-red.log`: actual source mutation at1673320 disables scheduled and
explicit revision observation after startup. Existing alias and initial unknown
refusal succeeded, but the newly registered previously-negative alias returned
421 where native test required200. Exit1 is a semantic admission failure, not setup.
Original source bytes restored in finally; final exact-head native run above passes.
All owned processes/containers/scratch overlays removed. SHA256 manifest retained.

Setup/instrument corrections before final source: the migration runner required
an explicit runtime password field; PostgreSQL evaluated a sequence privilege call
on a non-sequence before relation filtering (now CASE-guarded); product resolver
startup intentionally exposes TENANT_REGISTRY_UNAVAILABLE for unsafe lookup owner
rather than its underlying catalogue error. These exploratory failures were not
counted as semantic controls or final acceptance.

No fresh browser bundle build, full browser suite, full provisioning ceremony,
restore census, full enabled corpus or capacity campaign ran in this lane. UI
native overlay used this lane's previously copied private core bundle artifacts;
joined deployment must build/qualify its own image and pass lifecycle census.
