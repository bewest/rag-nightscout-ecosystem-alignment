# Nightscout Connect Documentation Inventory

**Repo Alias:** `ns-connect`  
**Source URL:** https://github.com/nightscout/nightscout-connect.git  
**Ref:** main  
**Last Inventory:** 2026-01-16

---

## Summary

Nightscout Connect is a data bridge module that synchronizes glucose data from various diabetes cloud providers into Nightscout. It replaces legacy bridges like `share2nightscout-bridge`.

**Total Documentation Files:** 2 markdown files

---

## Documentation

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| README | `README.md` | Project overview, data source configuration | High |
| Machines | `machines.md` | State machine documentation | Medium |

---

## Supported Data Sources

| Source | Environment Variable | Status | Notes |
|--------|---------------------|--------|-------|
| **Dexcom Share** | `CONNECT_SOURCE=dexcomshare` | Complete | US and OUS servers |
| **Glooko** | `CONNECT_SOURCE=glooko` | Experimental | EU support |
| **Libre Link Up** | `CONNECT_SOURCE=linkup` | Complete | Multiple regions |
| **Minimed Carelink** | `CONNECT_SOURCE=minimedcarelink` | Complete | EU and US |
| **Nightscout** | `CONNECT_SOURCE=nightscout` | WIP | Site-to-site sync |
| Tidepool | - | TODO | Not implemented |
| Tandem | - | TODO | Not implemented |

---

## Key Concepts

### Data Flow

```
Vendor Cloud → nightscout-connect → Nightscout API → MongoDB
     ↑                                    ↓
   Dexcom/Glooko/Libre            entries collection
```

### Configuration Pattern

All sources use `CONNECT_` prefix for environment variables:
- `CONNECT_SOURCE` - Data source name
- `CONNECT_API_SECRET` - Target Nightscout API secret
- `CONNECT_NIGHTSCOUT_ENDPOINT` - Target Nightscout URL
- Source-specific credentials follow pattern: `CONNECT_{SOURCE}_{PARAM}`

### Operation Modes

| Mode | Usage |
|------|-------|
| Plugin | Enable with `ENABLE=connect` in Nightscout |
| Sidecar | Run from CLI as separate process |
| Capture | Run with fixture capture for testing |

---

## Integration Recommendations

### For Alignment Workspace

1. **Document bridge data shapes** → How each vendor's data maps to Nightscout entries
2. **Sync identity patterns** → How bridge identifies itself to Nightscout (via `app` field?)
3. **Gap detection** → How nightscout-connect handles data gaps

### Minimal Priority for Initial Alignment

Since nightscout-connect is primarily a data ingestion layer rather than a semantic model, its integration priority is lower than core cgm-remote-monitor and gateway documentation.

---

## Source Files Summary

```
externals/nightscout-connect/
├── README.md     ← Primary documentation
└── machines.md   ← State machine internals
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial inventory |
