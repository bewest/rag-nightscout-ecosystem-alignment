# Code Reference Registry

This file defines code references used throughout the documentation. References use a stable format that can be validated against the `workspace.lock.json` lockfile.

## Reference Format

```
[repo-alias]:[path]#[anchor]
```

- **repo-alias**: Short name defined in workspace.lock.json
- **path**: Relative path within the repository
- **anchor**: Optional line range (L10-L50) or symbol name

## Usage in Documentation

Instead of raw GitHub links, use reference IDs in your markdown:

    See the entries normalization logic (ref: crm:lib/server/api3/entries.ts#L120-L188)

Tooling will expand this to:
- A link to the file in externals/
- A GitHub permalink at the pinned SHA

---

## Registry

Example entries (update with actual paths after running bootstrap):

### Nightscout (cgm-remote-monitor)

| Ref ID | Path | Purpose |
|--------|------|---------|
| crm:lib/server/treatments.js | lib/server/treatments.js | Core treatment handling |
| crm:lib/api3/generic/update/operation.js | lib/api3/generic/update/operation.js | API v3 update logic |
| crm:lib/profilefunctions.js | lib/profilefunctions.js | Profile loading and value lookup |
| crm:lib/authorization/index.js | lib/authorization/index.js | Auth system entry point |
| crm:lib/server/enclave.js | lib/server/enclave.js | JWT signing and token generation |
| crm:lib/authorization/delaylist.js | lib/authorization/delaylist.js | Brute-force protection |
| crm:lib/server/bootevent.js | lib/server/bootevent.js | Server boot sequence |
| crm:lib/bus.js | lib/bus.js | Internal event bus |
| crm:lib/plugins/careportal.js | lib/plugins/careportal.js | Core event type definitions |
| crm:lib/plugins/openaps.js | lib/plugins/openaps.js | OpenAPS event types |
| crm:lib/plugins/loop.js | lib/plugins/loop.js | Loop event types |
| crm:lib/data/ddata.js | lib/data/ddata.js | Data processing |
| crm:lib/server/websocket.js | lib/server/websocket.js | Real-time treatment ingestion |
| crm:lib/api3/storageSocket.js | lib/api3/storageSocket.js | API v3 storage events |
| crm:lib/api3/alarmSocket.js | lib/api3/alarmSocket.js | API v3 alarm events |
| crm:lib/report_plugins/treatments.js | lib/report_plugins/treatments.js | Treatment report (field usage) |

### Nightscout Roles Gateway

| Ref ID | Path | Purpose |
|--------|------|---------|
| ns-gateway:lib/policies/index.js | lib/policies/index.js | Policy decision logic |
| ns-gateway:lib/owner/index.js | lib/owner/index.js | Site owner operations |
| ns-gateway:lib/privy/index.js | lib/privy/index.js | Identity handling |
| ns-gateway:lib/registrations/index.js | lib/registrations/index.js | Site registration flow |

### Nightscout Connect

| Ref ID | Path | Purpose |
|--------|------|---------|
| ns-connect:lib/sources/dexcomshare.js | lib/sources/dexcomshare.js | Dexcom Share bridge |
| ns-connect:lib/sources/linkup.js | lib/sources/linkup.js | Libre Link Up bridge |

### Loop

| Ref ID | Path | Purpose |
|--------|------|---------|
| loop:Loop/Models/Override.swift | Loop/Models/Override.swift | Override data model |

### AAPS

| Ref ID | Path | Purpose |
|--------|------|---------|
| aaps:database/entities/ProfileSwitch.kt | database/entities/ProfileSwitch.kt | ProfileSwitch entity |

### Trio

| Ref ID | Path | Purpose |
|--------|------|---------|
| trio:FreeAPS/Sources/Models/Override.swift | FreeAPS/Sources/Models/Override.swift | Override model |

---

## Validation

Run `tools/linkcheck.py` to verify all references resolve correctly.
