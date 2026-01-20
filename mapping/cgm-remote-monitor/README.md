# cgm-remote-monitor Mapping

**Repository**: nightscout/cgm-remote-monitor  
**Branch Analyzed**: `wip/bewest/mongodb-5x`  
**Purpose**: Core Nightscout server - CGM data storage and API  
**Language**: JavaScript (Node.js)

## Overview

cgm-remote-monitor is the core Nightscout server that provides:
- REST API (v1, v2, v3) for CGM data
- Real-time WebSocket broadcasts
- Multi-client deduplication
- MongoDB storage layer

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `lib/api/` | v1 API endpoints |
| `lib/api3/` | v3 API endpoints |
| `lib/authorization/` | Auth and permissions |
| `lib/server/` | Core server (entries, treatments, websocket) |
| `lib/data/` | Data processing and delta calculation |

## Related Documents

- [api-versions.md](api-versions.md) - v1 vs v3 API comparison
- [deduplication.md](deduplication.md) - Client deduplication strategies
- [authorization.md](authorization.md) - Auth and permissions
- [websocket.md](websocket.md) - Real-time broadcasts
- [mongodb-5x.md](mongodb-5x.md) - MongoDB 5.x migration changes
