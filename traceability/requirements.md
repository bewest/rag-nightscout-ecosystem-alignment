# Requirements

This document is an index of requirements organized by domain.

## Hosted-tenancy experiment verification (2026-11-02)

The adopted [delivery roadmap](../docs/30-design/tenancy/multitenant-delivery-roadmap-2026-11-02.md)
adds milestone-specific checks under the existing decisions, not new protocol
IDs. Preserve legacy per-tenant header/token/socket forms. Owner configuration
uses the supported headless API and project floors even when a vendor supplies
UI. Initial configuration is a reviewed subset; unsupported settings and
inactive alarm/integration features refuse explicitly. Synthetic token/root
principals must not be audited as verified humans. Celld is out of scope.

The [multitenancy priorities assessment](../docs/10-domain/nightscout-multitenancy-priorities-deep-dive.md)
clarifies existing D1-D4, ST-PG and TEN-LAB acceptance rather than inventing new
protocol requirement IDs. A PG pass executes applicable storage tests on the
real adapter; pending tests are not acceptance. Use two tenants with overlapping
identities and an unbound reader, non-bypass application roles, transaction-local
binding, real pool reuse and paired red controls for reads and writes.

Hosted acceptance additionally needs trusted tenant resolution, per-tenant
credentials/settings, legacy-client surfaces, evaluator/realtime isolation and
operational recovery. A synthetic experiment does not need production human
identity or real onboarding. A Celld spike must distinguish actor routing from
authorization, runtime wake from delivered alarm, and durable cell state from
atomic PG-to-actor delivery; retries must expose duplicate effects. These are
proposed experiment checks, not newly adopted architecture or v16 prerequisites.

## Release-readiness verification (2026-11-02)

The [current v16 ecosystem/acceptance record](../docs/10-domain/nightscout-v16-ecosystem-deep-dive.md)
maps the existing pre-tag requirements (`RT-16-RELEASE`, `RT-16-LIVE-ALARMS`,
`RT-16-RIG-SOAK`, `BFQ-72`, `BFQ-161`) to current integration work. These queue
identifiers are release gates, not new protocol requirement IDs. Restricted-token
WebSocket/reconnect testing and final integrated-head CI remain required evidence;
offline notification tests do not satisfy live transport acceptance.
Merged-head CI is met on `61eb3733`; it must be repeated after private security
integration. `BFQ-227` tracks the callback defect fixed by #8895;
`RT-CI-FIXTURES-8896` tracks test hygiene, not a new protocol requirement.
Hosted suite totals are reported separately from matrix execution totals in the
readiness record; neither replaces final security-tree, live/cohort or rollback
acceptance. Scheduled implementation merges are not unfulfilled test requirements.

Cohort/rig testing is now in progress, not accepted from elapsed time alone.
For each cohort capture server SHA/image, client version and role, API/transport,
units, settings, observation interval, scenario outcome and unresolved failures;
repeat affected checks after the final security integration. Keep credentials,
personal identifiers and real treatment payloads out of public evidence.

Compatibility verification must distinguish legacy/default behavior from
request opt-in item results; HTTP success from per-item storage; re-send from edit;
unset identifier validation from explicit lenient/strict; and index `off` from
`drop`. A new AID release or optional field does not itself justify making all
clients upgrade together. These clarify the existing release/client gates, not
new normative protocol requirements. The reporter's #8829 result and both
maintainers' non-reproduction must coexist in its release disposition:
**nonblocking for v16**, decided by the maintainer November 2, with working
DIY and production/service environments reported. It is not a new pre-tag gate.

The compatibility catalogue covers 15 implementations through 120 shape matches
(11 measured-tier, 109 read-tier), not live execution of every app. The supported
release claim is high confidence in existing-client interoperability without
coordinated upgrades, with documented intentional changes and opt-in boundaries.
Universal new-client/old-server feature compatibility is not demonstrated.
Previously tested contributions are high-confidence according to the maintainer;
record that provenance separately from uncollected live outcome rows.

## Domain Files

- [Aid Algorithms](aid-algorithms-requirements.md) - 56 requirements (+3 OREF)
- [Cgm Sources](cgm-sources-requirements.md) - 19 requirements
- [Connectors](connectors-requirements.md) - 55 requirements (+4 BLE)
- [Nightscout Api](nightscout-api-requirements.md) - 57 requirements (+4 IDP)
- [Pumps](pumps-requirements.md) - 10 requirements
- [Sync Identity](sync-identity-requirements.md) - 79 requirements (+4 FOLLOW, +2 PROPOSAL)
- [Telemetry and Observability](telemetry-observability-requirements.md) - 9 requirements
- [Treatments](treatments-requirements.md) - 35 requirements

Total: 323 requirements

## Coverage Status

| Metric | Value | Date |
|--------|-------|------|
| Requirements with scenarios | 27/184 | 2026-01-29 |
| Orphaned assertions | 0 | 2026-01-29 |
| Requirement coverage | 14.7% | 2026-01-29 |

**Source**: `python tools/verify_assertions.py`

### REQ-SYNC-* Coverage (Level 5 #24)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 18 | 15 | 3 | 83% |

**Uncovered**: REQ-SYNC-001 (WebSocket docs), REQ-SYNC-002 (v1/v3 identity), REQ-SYNC-003 (status response)

### REQ-TREAT-* Coverage (Level 5 #25)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 7 | 7 | 0 | 100% |

**All covered** via `treatment-sync.yaml`: REQ-TREAT-040 to REQ-TREAT-046

### REQ-ALARM-* Coverage (Level 5 #28)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 10 | 10 | 0 | 100% |

**All covered** via `alarm-requirements.yaml`: REQ-ALARM-001 to REQ-ALARM-010

**Related gaps**: GAP-ALARM-001 (alarm config sync), GAP-ALARM-002 (predictive horizon)

### REQ-REMOTE-* Coverage (Level 5 #29)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 11 | 11 | 0 | 100% |

**All covered** via `remote-command-requirements.yaml`: REQ-REMOTE-001 to REQ-REMOTE-011

**Related gaps**: GAP-REMOTE-001 (override auth), GAP-REMOTE-002 (command signing), GAP-REMOTE-003 (key rotation)

### REQ-INTEROP-* Coverage (Level 5 #30)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 3 | 3 | 0 | 100% |

**All covered** via `interop-unit-requirements.yaml`: REQ-INTEROP-001 to REQ-INTEROP-003

**Related gaps**: GAP-SYNC-009 (timestamp format), GAP-TREAT-001 (eventType), GAP-SYNC-008 (device ID)

### REQ-UNIT-* Coverage (Level 5 #31)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 4 | 4 | 0 | 100% |

**All covered** via `interop-unit-requirements.yaml`: REQ-UNIT-001 to REQ-UNIT-004

**Related gaps**: GAP-TREAT-002 (duration units), GAP-TZ-004 (utcOffset units)

### REQ-ALG-* Coverage (Level 5 #32)

| Total | Covered | Uncovered | % |
|-------|---------|-----------|---|
| 56 | 22 | 34 | 39% |

**Partially covered** - Degraded operation, safety limits, insulin model, profile schema, prediction complete

**Traceability Matrix**: [`domain-matrices/aid-algorithms-matrix.md`](domain-matrices/aid-algorithms-matrix.md)

**Covered categories**:
- Degraded Operation (REQ-DEGRADE-001-006): ✅ 100% via `degraded-operation.yaml`
- Algorithm Core (REQ-ALG-003): ✅ 25% via `safety-limits.yaml`
- Insulin Model (REQ-INS-001-005): ✅ 100% via `safety-limits.yaml` + `insulin-model.yaml`
- Profile Schema (REQ-PROF-001-007): ✅ 100% via `profile-structure.yaml`
- Prediction (REQ-PRED-001-003): ✅ 100% via `prediction-requirements.yaml`

**Uncovered categories**:
- Carb Absorption (REQ-CARB-001-006): 0%
- Sensitivity/Dosing/Target: 0%

**Data quality issue**: Duplicate REQ IDs (REQ-CARB-001-003, REQ-INS-001-003)

### REQ-CONNECT-* Completeness (Level 5 #26)

| Total GAPs | GAPs with REQs | Orphaned | % |
|------------|----------------|----------|---|
| 28 | 28 | 0 | 100% |

**Perfect 1:1 mapping**: All 8 connector categories have corresponding requirements

### REQ-API-* OpenAPI Alignment (Level 5 #27) - **LEVEL 5 COMPLETE**

| Total | With Spec | No Spec | Out of Scope | % |
|-------|-----------|---------|--------------|---|
| 35 | 22 | 10 | 3 | 63% |

**Gaps**: REQ-STATS-* (5), REQ-AUTH-* (3), REQ-RG-* (4) need OpenAPI specs

## Mapping Verification (Supporting Evidence)

| Date | Mapping Verified | Requirements Supported |
|------|------------------|------------------------|
| 2026-01-29 | xdrip-android/nightscout-sync.md | REQ-020 (sync identity), REQ-050 (CGM upload) |
| 2026-01-29 | aaps/nsclient-schema.md | REQ-030 (field validation), REQ-010 (timestamp) |
| 2026-01-29 | loop/sync-identity-fields.md | REQ-020-025 (sync identity, ObjectIdCache) |
| 2026-01-29 | trio/nightscout-sync.md | REQ-030 (field validation), REQ-060 (algorithm) |
| 2026-01-29 | terminology-matrix.md (10% sample) | Cross-domain terminology accuracy |

## Deep Dive Verification (Supporting Evidence)

| Date | Deep Dive | Requirements Supported |
|------|-----------|------------------------|
| 2026-01-29 | algorithm-comparison-deep-dive.md | REQ-060-069 (algorithm behavior) |
| 2026-01-29 | g7-protocol-specification.md | REQ-050-059 (CGM data source) |
| 2026-01-29 | cgm-data-sources-deep-dive.md | REQ-050-059 (CGM data source) |
| 2026-01-29 | devicestatus-deep-dive.md | REQ-030 (field validation), REQ-010 (timestamp) |
| 2026-01-29 | entries-deep-dive.md | REQ-050-059 (CGM data source), REQ-030 (field validation) |
| 2026-01-29 | treatments-deep-dive.md | REQ-TREAT (treatments), REQ-020 (sync identity) |
| 2026-01-29 | libre-protocol-deep-dive.md | REQ-050-059 (CGM data source), REQ-030 (field validation) |
| 2026-01-29 | pump-communication-deep-dive.md | REQ-PUMP (pump protocols), REQ-030 (field validation) |
| 2026-01-29 | nightscout-devicestatus-schema-audit.md | REQ-DS-001-004 (devicestatus schema) |
| 2026-01-29 | profile-schema-alignment.md | REQ-PROF-001-004 (profile schema) |
| 2026-01-29 | bolus-wizard-formula-comparison.md | REQ-BOLUS-001-003 (bolus wizard) |
| 2026-01-29 | autosens-dynamic-isf-comparison.md | REQ-SENS-001-003 (sensitivity) |
| 2026-01-29 | carb-absorption-model-comparison.md | REQ-CARB-001-003 (carb absorption) |
| 2026-01-30 | prediction-curve-documentation.md | REQ-PRED-001-003 (predictions) |
| 2026-01-30 | temp-basal-vs-smb-comparison.md | REQ-DOSE-001-003 (dosing) |
| 2026-06-17 | algorithm-comparison-deep-dive.md | REQ-060-069 (algorithm behavior) refreshed for current Loop automatic dosing IOB terminology |
| 2026-06-17 | nightscout-api-comparison.md | REQ-020 (sync identity), REQ-030 (field semantics) refreshed for current Trio v1 client behavior |

**Level 2 Complete**: 5/5 mapping verifications passed (100%)
**Level 3 Complete**: 8/8 deep dive verifications (100%) ✅

*Last updated: 2026-07-16*
