# Nightscout (cgm-remote-monitor) Documentation Inventory

**Repo Alias:** `crm`  
**Source URL:** https://github.com/bewest/cgm-remote-monitor-1.git  
**Ref:** wip/replit/with-mongodb-update  
**Last Inventory:** 2026-01-16

---

## Summary

The cgm-remote-monitor repository contains extensive documentation organized across multiple directories. This inventory catalogs all markdown documentation to support alignment workspace integration.

**Total Documentation Files:** 39 markdown files

---

## Documentation Categories

### 1. Architecture & System Audits

Deep-dive analyses of Nightscout's major subsystems. These are the primary sources for understanding system behavior.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Architecture Overview | `docs/architecture-overview.md` | High-level system architecture, boot sequence, component relationships | **Critical** |
| API Layer Audit | `docs/api-layer-audit.md` | REST API v1/v2/v3 analysis, endpoint inventory | **Critical** |
| Data Layer Audit | `docs/data-layer-audit.md` | MongoDB collections, data flow, sync mechanisms | **Critical** |
| Security Audit | `docs/security-audit.md` | Auth mechanisms, JWT, permissions, threats | **Critical** |
| Plugin Architecture Audit | `docs/plugin-architecture-audit.md` | 38-plugin system, lifecycle, extensibility | High |
| Real-Time Systems Audit | `docs/realtime-systems-audit.md` | Socket.IO namespaces, event bus, WebSocket | High |
| Messaging Subsystem Audit | `docs/messaging-subsystem-audit.md` | Pushover, IFTTT, notification delivery | Medium |
| Dashboard UI Audit | `docs/dashboard-ui-audit.md` | Frontend bundle, D3/jQuery visualization | Low |
| Modernization Roadmap | `docs/modernization-roadmap.md` | Technical debt, refactoring priorities | Reference |

### 2. Data Schemas

Formal field inventories for core data structures. Essential for alignment mapping.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Treatments Schema | `docs/data-schemas/treatments-schema.md` | Full field inventory, eventTypes, client conventions | **Critical** |
| Profiles Schema | `docs/data-schemas/profiles-schema.md` | Profile structure, Loop settings, timezone quirks | **Critical** |

### 3. API Documentation

Official API v3 documentation embedded in the codebase.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| API v3 Tutorial | `lib/api3/doc/tutorial.md` | CRUD operations, auth flow, examples | **Critical** |
| Socket API | `lib/api3/doc/socket.md` | WebSocket protocol, events | High |
| Alarm Sockets | `lib/api3/doc/alarmsockets.md` | Real-time alarm broadcast | High |
| Security | `lib/api3/doc/security.md` | API v3 auth model | High |
| Formats | `lib/api3/doc/formats.md` | Data format specifications | Medium |

### 4. Requirements & Test Specs

Formal requirements documents and test specifications.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| API v1 Compatibility Spec | `docs/requirements/api-v1-compatibility-spec.md` | Client compatibility (AAPS, Loop, xDrip) | **Critical** |
| Authorization Security Spec | `docs/requirements/authorization-security-spec.md` | Auth requirements, 21 test mappings | **Critical** |
| Data Shape Requirements | `docs/requirements/data-shape-requirements.md` | MongoDB 5.x migration, shape handling | High |
| Authorization Test Spec | `docs/test-specs/authorization-test-spec.md` | Auth test coverage, gaps | High |
| Shape Handling Test Spec | `docs/test-specs/shape-handling-test-spec.md` | 38 tests for data shape validation | Medium |

### 5. Design Proposals (RFCs)

Forward-looking design documents proposing new capabilities.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Conflict Resolution | `docs/proposals/conflict-resolution.md` | Multi-writer semantics, authority hierarchy | **Critical** |
| OIDC Actor Identity | `docs/proposals/oidc-actor-identity-proposal.md` | OAuth2/OIDC identity integration | **Critical** |
| Agent Control Plane RFC | `docs/proposals/agent-control-plane-rfc.md` | AI agent integration framework | **Critical** |
| Bridge Rules | `docs/proposals/bridge-rules.md` | Data bridge rule definitions | High |
| API Query Normalization | `docs/proposals/api-query-normalization.md` | Query standardization | Medium |
| Testing Modernization | `docs/proposals/testing-modernization-proposal.md` | Test infrastructure upgrade | Low |
| Integration Questionnaire | `docs/proposals/integration-questionnaire.md` | Integration assessment template | Reference |

### 6. Plugin Documentation

User-facing documentation for specific plugins.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Alexa Plugin | `docs/plugins/alexa-plugin.md` | Amazon Alexa integration | Low |
| Google Home Plugin | `docs/plugins/googlehome-plugin.md` | Google Assistant integration | Low |
| Maker Setup | `docs/plugins/maker-setup.md` | IFTTT Maker webhooks | Low |
| Virtual Assistants | `docs/plugins/interacting-with-virtual-assistants.md` | Voice assistant overview | Low |
| Add VA Support | `docs/plugins/add-virtual-assistant-support-to-plugin.md` | Extending plugins for voice | Low |
| Example Profiles | `docs/plugins/example-profiles.md` | Profile configuration examples | Reference |

### 7. Project Meta

Repository-level documentation.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| README | `README.md` | Project overview, setup instructions | Reference |
| CONTRIBUTING | `CONTRIBUTING.md` | Contribution guidelines | Reference |
| Documentation Progress | `docs/DOCUMENTATION-PROGRESS.md` | Documentation effort tracker | Reference |
| Issue Template | `docs/issue_template.md` | Bug report template | Reference |

### 8. Other/Assets

Miscellaneous documentation.

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Fonts README | `assets/fonts/README.md` | Font license info | Skip |
| Colorbrewer README | `static/colorbrewer/README.md` | Color palette info | Skip |
| Bug Report Template | `.github/ISSUE_TEMPLATE/--bug-report.md` | GitHub issue template | Skip |
| Feature Request Template | `.github/ISSUE_TEMPLATE/--feature-request--.md` | GitHub issue template | Skip |

---

## Key Concepts Extracted

### Core Domain Entities

From schema documentation:

| Entity | Collection | Key Documents |
|--------|------------|---------------|
| **Entries** | `entries` | SGV (glucose) readings from CGM | 
| **Treatments** | `treatments` | Insulin, carbs, overrides, notes |
| **Profiles** | `profile` | Basal rates, ISF, ICR, targets |
| **DeviceStatus** | `devicestatus` | Loop/AAPS device state |
| **Food** | `food` | Food database |

### Event Types (from treatments-schema.md)

Core event types:
- `BG Check`, `Snack Bolus`, `Meal Bolus`, `Correction Bolus`
- `Carb Correction`, `Combo Bolus`
- `Temp Basal Start`, `Temp Basal End`
- `Profile Switch`
- `Sensor Start`, `Sensor Change`, `Sensor Stop`
- `Site Change`, `Insulin Change`, `Pump Battery Change`
- `Note`, `Announcement`, `Question`
- `Exercise`, `D.A.D. Alert`

OpenAPS/AAPS extensions:
- `Temporary Target`, `Temporary Target Cancel`
- `OpenAPS Offline`

### API Versions

| Version | Path | Auth | Status |
|---------|------|------|--------|
| v1 | `/api/v1` | API_SECRET | Legacy, widely used |
| v2 | `/api/v2` | JWT tokens | Current |
| v3 | `/api/v3` | JWT, OpenAPI 3.0 | Modern, recommended |

### Controller Sync Identity Fields

Different AID controllers use different fields for deduplication:

| Controller | Identity Field | Notes |
|------------|----------------|-------|
| AAPS | `identifier` | Custom UUID field |
| Loop | pump fields (`pumpId`, `pumpType`, `pumpSerial`) | Pump-centric |
| xDrip | `uuid` | Standard UUID |

---

## Integration Recommendations

### Phase 1: Core Schema Integration

1. **Extract `treatments` schema** → `specs/jsonschema/treatments.json`
2. **Extract `profiles` schema** → `specs/jsonschema/profiles.json`
3. **Map event types** → `docs/10-domain/nightscout-event-types.md`

### Phase 2: API Specification

1. **Document API v3** → `specs/openapi/nightscout-api3.yaml`
2. **Document sync protocols** → `docs/20-specs/nightscout-sync.md`
3. **Map auth model** → `mapping/nightscout/authorization.md`

### Phase 3: Proposals for Alignment

1. **Conflict resolution** → Inform `specs/` alignment decisions
2. **Agent control plane** → Inform agent integration design
3. **OIDC identity** → Inform cross-project identity model

---

## Cross-References

### Already Referenced in Workspace

| Workspace Location | Nightscout Source |
|--------------------|-------------------|
| `docs/_includes/code-refs.md` | `lib/server/treatments.js`, `lib/api3/generic/update/operation.js` |
| `mapping/nightscout/override-supersede.md` | Treatments with `eventType: "Temporary Override"` |

### Gaps Identified

| Gap | Description | Source |
|-----|-------------|--------|
| GAP-001 | No `superseded` or `superseded_by` fields in Nightscout | mapping/nightscout/override-supersede.md |
| GAP-002 | Controller sync identity not standardized | treatments-schema.md |
| GAP-003 | No formal schema validation layer | treatments-schema.md |

---

## Source Files Summary

```
externals/cgm-remote-monitor/
├── README.md
├── CONTRIBUTING.md
├── docs/
│   ├── DOCUMENTATION-PROGRESS.md
│   ├── architecture-overview.md        ← CRITICAL
│   ├── api-layer-audit.md              ← CRITICAL
│   ├── data-layer-audit.md             ← CRITICAL
│   ├── security-audit.md               ← CRITICAL
│   ├── plugin-architecture-audit.md
│   ├── realtime-systems-audit.md
│   ├── messaging-subsystem-audit.md
│   ├── dashboard-ui-audit.md
│   ├── modernization-roadmap.md
│   ├── data-schemas/
│   │   ├── treatments-schema.md        ← CRITICAL
│   │   └── profiles-schema.md          ← CRITICAL
│   ├── requirements/
│   │   ├── api-v1-compatibility-spec.md
│   │   ├── authorization-security-spec.md
│   │   └── data-shape-requirements.md
│   ├── test-specs/
│   │   ├── authorization-test-spec.md
│   │   └── shape-handling-test-spec.md
│   └── proposals/
│       ├── conflict-resolution.md      ← CRITICAL
│       ├── oidc-actor-identity-proposal.md
│       ├── agent-control-plane-rfc.md
│       ├── bridge-rules.md
│       ├── api-query-normalization.md
│       ├── testing-modernization-proposal.md
│       └── integration-questionnaire.md
└── lib/api3/doc/
    ├── tutorial.md                     ← CRITICAL
    ├── socket.md
    ├── alarmsockets.md
    ├── security.md
    └── formats.md
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial inventory from filesystem scan and document review |
