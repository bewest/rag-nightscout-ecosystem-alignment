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
