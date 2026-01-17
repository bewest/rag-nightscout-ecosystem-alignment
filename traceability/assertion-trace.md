# Assertion Trace Report

Generated: 2026-01-17T21:08:41.015991+00:00

## Summary

| Metric | Value |
|--------|-------|
| Total Assertion Groups | 24 |
| Total Test Cases | 0 |
| Known Requirements | 26 |
| Requirements with Assertions | 7 |
| Uncovered Requirements | 19 |
| Known Gaps | 70 |
| Gaps with Assertions | 7 |
| Orphaned Assertions | 23 |

**Requirement Coverage: 26.9%**

## Uncovered Requirements

These requirements have no assertions:

- REQ-001
- REQ-002
- REQ-003
- REQ-010
- REQ-020
- REQ-030
- REQ-031
- REQ-032
- REQ-033
- REQ-034
- REQ-035
- REQ-050
- REQ-051
- REQ-052
- REQ-053
- REQ-054
- REQ-055
- REQ-056
- REQ-057

## Orphaned Assertions

These assertions have no linked requirements or gaps:

- **superseded-status-change** (`conformance/assertions/override-supersede.yaml`)
- **superseded-by-reference** (`conformance/assertions/override-supersede.yaml`)
- **superseded-at-timestamp** (`conformance/assertions/override-supersede.yaml`)
- **new-override-active** (`conformance/assertions/override-supersede.yaml`)
- **original-preserved** (`conformance/assertions/override-supersede.yaml`)
- **query-active-single** (`conformance/assertions/override-supersede.yaml`)
- **query-history-both** (`conformance/assertions/override-supersede.yaml`)
- **syncidentifier-preserved** (`conformance/assertions/sync-deduplication.yaml`)
- **identifier-preserved** (`conformance/assertions/sync-deduplication.yaml`)
- **enteredby-preserved** (`conformance/assertions/sync-deduplication.yaml`)
- **utcoffset-preserved** (`conformance/assertions/sync-deduplication.yaml`)
- **softdelete-isvalid-false** (`conformance/assertions/sync-deduplication.yaml`)
- **pump-composite-key-immutable** (`conformance/assertions/sync-deduplication.yaml`)
- **core-treatment-fields-immutable** (`conformance/assertions/sync-deduplication.yaml`)
- **server-timestamps-immutable** (`conformance/assertions/sync-deduplication.yaml`)
- **enteredby-filter-excludes-self** (`conformance/assertions/sync-deduplication.yaml`)
- **history-returns-modified-after** (`conformance/assertions/sync-deduplication.yaml`)
- **history-includes-soft-deleted** (`conformance/assertions/sync-deduplication.yaml`)
- **query-by-identifier** (`conformance/assertions/sync-deduplication.yaml`)
- **cross-controller-coexistence** (`conformance/assertions/sync-deduplication.yaml`)
- **nightscoutid-references-server** (`conformance/assertions/sync-deduplication.yaml`)
- **srvmodified-updated-on-change** (`conformance/assertions/sync-deduplication.yaml`)
- **srvcreated-set-on-create** (`conformance/assertions/sync-deduplication.yaml`)

## Assertions by File

| File | Assertions | Tests | Requirements | Gaps |
|----|------------|-------|--------------|------|
| `conformance/assertions/override-supersede.yaml` | 7 | 0 | 0 | 0 |
| `conformance/assertions/sync-deduplication.yaml` | 16 | 0 | 0 | 0 |
| `conformance/assertions/treatment-sync.yaml` | 1 | 0 | 7 | 7 |

## Requirement to Assertion Mapping

| Requirement | Assertions |
|-------------|------------|
| REQ-040 | treatment-sync |
| REQ-041 | treatment-sync |
| REQ-042 | treatment-sync |
| REQ-043 | treatment-sync |
| REQ-044 | treatment-sync |
| REQ-045 | treatment-sync |
| REQ-046 | treatment-sync |
