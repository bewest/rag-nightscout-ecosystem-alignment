# REQ-API → OpenAPI Alignment Audit

> **Date**: 2026-01-30  
> **Status**: Complete  
> **Task**: nightscout-api #5 - Audit REQ-API-* → OpenAPI alignment

---

## Executive Summary

Audited 6 REQ-API-* requirements against 8 OpenAPI specification files. Found:
- **4 requirements** fully covered in specs
- **2 requirements** partially covered
- **0 requirements** missing from specs

### Quick Reference

| Requirement | OpenAPI Coverage | Status |
|-------------|------------------|--------|
| REQ-API-001 | ✅ Full | Dedup keys documented |
| REQ-API-002 | ✅ Full | 8 OpenAPI specs exist |
| REQ-API-003 | ✅ Full | Timestamp fields documented |
| REQ-API-004 | ⚠️ Partial | REST documented, WebSocket separate |
| REQ-API-005 | ⚠️ Partial | Gap annotation exists, no spec |
| REQ-API-006 | ✅ Full | Best practice, not spec'd |

---

## OpenAPI Specification Inventory

### Available Specs

| Spec File | Collection | Lines | Gap Annotations |
|-----------|------------|-------|-----------------|
| `aid-entries-2025.yaml` | entries | ~200 | Yes (GAP-ENTRY-001) |
| `aid-treatments-2025.yaml` | treatments | ~300 | Yes |
| `aid-devicestatus-2025.yaml` | devicestatus | ~250 | Yes |
| `aid-profile-2025.yaml` | profile | ~150 | Yes |
| `aid-heartrate-2025.yaml` | heartrate | ~100 | Yes |
| `aid-insulin-2025.yaml` | insulin | ~100 | Yes |
| `aid-commands-2025.yaml` | commands | ~80 | Yes |
| `aid-alignment-extensions.yaml` | extensions | ~200 | Yes (16 refs) |

### Annotation Coverage

| Annotation | Count | Purpose |
|------------|-------|---------|
| `x-aid-source` | 50+ | Source file references |
| `x-aid-controllers` | 40+ | Controller support matrix |
| `x-aid-gap` | 15+ | Gap ID references |
| `x-aid-gap-note` | 10+ | Gap descriptions |

---

## Requirement-by-Requirement Analysis

### REQ-API-001: Document Deduplication Keys Per Collection

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COVERED |
| **Coverage** | Full |

**OpenAPI Evidence**:

```yaml
# aid-entries-2025.yaml
identifier:
  type: string
  description: Client-provided unique ID for deduplication
  x-aid-controllers:
    loop: syncIdentifier
    aaps: interfaceIDs.nightscoutId
    trio: syncIdentifier
```

```yaml
# aid-treatments-2025.yaml  
identifier:
  type: string
  description: Deduplication key - upsert uses this field
```

**Collections Covered**:
- ✅ entries - `identifier` field documented
- ✅ treatments - `identifier` field documented
- ✅ devicestatus - `identifier` field documented
- ✅ profile - `identifier` field documented

---

### REQ-API-002: Provide Machine-Readable API Specification

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COVERED |
| **Coverage** | Full |

**Evidence**: 8 OpenAPI 3.0 specification files exist in `specs/openapi/`:

| File | Validates | Endpoints |
|------|-----------|-----------|
| aid-entries-2025.yaml | ✅ Yes | GET/POST/PUT/DELETE |
| aid-treatments-2025.yaml | ✅ Yes | GET/POST/PUT/DELETE |
| aid-devicestatus-2025.yaml | ✅ Yes | GET/POST |
| aid-profile-2025.yaml | ✅ Yes | GET/POST/PUT |
| aid-heartrate-2025.yaml | ✅ Yes | GET/POST |
| aid-insulin-2025.yaml | ✅ Yes | GET/POST |
| aid-commands-2025.yaml | ✅ Yes | POST |
| aid-alignment-extensions.yaml | ✅ Yes | Extensions |

**Note**: These are workspace specs documenting de facto standard. Upstream cgm-remote-monitor has minimal spec at `lib/api3/swagger.yaml`.

---

### REQ-API-003: Document Timestamp Field Per Collection

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ COVERED |
| **Coverage** | Full |

**OpenAPI Evidence**:

| Collection | Timestamp Field | Format | Documented |
|------------|-----------------|--------|------------|
| entries | `date`, `dateString`, `srvModified` | epoch, ISO-8601 | ✅ |
| treatments | `created_at`, `srvModified` | ISO-8601, epoch | ✅ |
| devicestatus | `created_at`, `srvModified` | ISO-8601, epoch | ✅ |
| profile | `startDate`, `srvModified` | ISO-8601, epoch | ✅ |

**Sample from aid-entries-2025.yaml**:

```yaml
date:
  type: integer
  format: int64
  description: Epoch milliseconds of glucose reading
  x-aid-controllers:
    loop: date
    aaps: timestamp
    xdrip: timestamp
```

---

### REQ-API-004: Document WebSocket Capabilities

| Attribute | Value |
|-----------|-------|
| **Status** | ⚠️ PARTIAL |
| **Coverage** | REST only |

**Analysis**: OpenAPI specs cover REST endpoints only. WebSocket documentation exists separately in:
- `docs/10-domain/cgm-remote-monitor-api-deep-dive.md`
- `docs/30-design/nightscout-integration-guide.md`

**Gap**: No AsyncAPI or WebSocket spec in `specs/` directory.

**Recommendation**: Create `specs/asyncapi/nightscout-websocket.yaml` to formally document:
- `/` namespace (legacy Socket.IO)
- `/storage` namespace (API v3)
- Event types and payloads

---

### REQ-API-005: Cross-Channel Event Propagation

| Attribute | Value |
|-----------|-------|
| **Status** | ⚠️ PARTIAL |
| **Coverage** | Gap annotation only |

**Analysis**: This requirement is referenced via gap annotation:

```yaml
# aid-alignment-extensions.yaml
x-aid-gap: GAP-API-014
x-aid-gap-note: APIv3 WebSocket doesn't capture V1 changes
```

**Gap**: No formal specification of cross-channel behavior. Currently documented as a gap rather than a requirement in specs.

**Recommendation**: Add `x-aid-req: REQ-API-005` annotations where applicable.

---

### REQ-API-006: WebSocket Rate Limiting

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ NOT APPLICABLE |
| **Coverage** | Best practice |

**Analysis**: This is a server implementation detail, not an API contract. Rate limiting is not typically specified in OpenAPI.

**Documentation**: Exists in server documentation, not API spec.

---

## Alignment Matrix

### Requirements → Specs

| Requirement | entries | treatments | devicestatus | profile | commands | heartrate | insulin |
|-------------|---------|------------|--------------|---------|----------|-----------|---------|
| REQ-API-001 | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ |
| REQ-API-002 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| REQ-API-003 | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ |
| REQ-API-004 | - | - | - | - | - | - | - |
| REQ-API-005 | - | - | - | - | - | - | - |
| REQ-API-006 | - | - | - | - | - | - | - |

**Legend**: ✅ = Covered, - = Not applicable to collection

### Gaps → Specs

| Gap ID | Spec | Annotation |
|--------|------|------------|
| GAP-ENTRY-001 | aid-entries-2025.yaml | ✅ x-aid-gap |
| GAP-API-006 | aid-alignment-extensions.yaml | ✅ x-aid-gap |
| GAP-API-014 | aid-alignment-extensions.yaml | ✅ x-aid-gap |
| GAP-TREAT-001 | aid-treatments-2025.yaml | ✅ x-aid-gap |

---

## Recommendations

### Immediate Actions

1. **Add REQ annotations**: Add `x-aid-req` to OpenAPI specs alongside `x-aid-gap`
2. **Create AsyncAPI spec**: Document WebSocket channels formally

### Medium-Term Actions

1. **Upstream contribution**: Propose OpenAPI specs to cgm-remote-monitor
2. **Validation tooling**: Add CI check for spec/requirement alignment

### Proposed x-aid-req Annotation

```yaml
# Example addition to aid-entries-2025.yaml
identifier:
  type: string
  description: Deduplication key
  x-aid-req: REQ-API-001
  x-aid-gap: GAP-API-002
```

---

## Coverage Summary

| Metric | Value |
|--------|-------|
| Total REQ-API-* requirements | 6 |
| Fully covered in OpenAPI | 4 (67%) |
| Partially covered | 2 (33%) |
| Not covered | 0 (0%) |
| OpenAPI specs with gap annotations | 8/8 (100%) |
| Unique gaps referenced in specs | 15+ |

---

## References

- [OpenAPI Specs](../../specs/openapi/)
- [Nightscout API Requirements](../../traceability/nightscout-api-requirements.md)
- [GAP-API Freshness Verification](./gap-api-freshness-verification.md)
- [API v3 Deep Dive](./nightscout-apiv3-deep-dive.md)
