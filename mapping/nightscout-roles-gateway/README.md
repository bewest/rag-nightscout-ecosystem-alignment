# nightscout-roles-gateway Mapping

**Repository**: nightscout/nightscout-roles-gateway  
**Purpose**: RBAC proxy for multi-site Nightscout access control  
**Language**: JavaScript (Node.js)

## Overview

The roles gateway implements Role-Based Access Control (RBAC) as a reverse proxy in front of Nightscout instances. It enables:

- Multi-site management under single authentication
- Group-based access policies
- Time-based access schedules
- OAuth/OIDC integration via Kratos/Hydra

## Architecture

```
Client → Gateway (Warden) → NGINX → Nightscout Instance
         ↓
    Policy Evaluation
         ↓
    x-upstream-origin header
```

## Key Files

| File | Purpose |
|------|---------|
| `lib/policies/index.js` | Policy decision engine |
| `lib/routes.js` | Warden endpoints |
| `lib/exchanged.js` | JWT token exchange |
| `lib/criteria/core.js` | Site validation |
| `lib/entities/index.js` | Site configuration |

## Related Documents

- [authorization.md](authorization.md) - RBAC model details
- [integration.md](integration.md) - Nightscout integration points
