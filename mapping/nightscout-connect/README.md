# nightscout-connect Mapping

**Repository**: nightscout/nightscout-connect  
**Purpose**: Data bridge between CGM sources and Nightscout  
**Language**: JavaScript (Node.js)

## Overview

nightscout-connect is a data synchronization bridge that reads CGM data from various sources and uploads to Nightscout instances. It supports bidirectional Nightscout-to-Nightscout sync.

## Key Files

| File | Purpose |
|------|---------|
| `lib/sources/nightscout.js` | Read from Nightscout API |
| `lib/outputs/nightscout.js` | Write to Nightscout API |
| `lib/machines/fetch.js` | Data fetching state machine |

## Related Documents

- [nightscout-sync.md](nightscout-sync.md) - Sync implementation details
- [authentication.md](authentication.md) - Auth patterns
