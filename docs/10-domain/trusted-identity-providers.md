# Trusted Identity Providers in the Nightscout Ecosystem

> **Backlog Item**: nightscout-api.md #23  
> **Date**: 2026-01-31  
> **Purpose**: Inventory of identity providers and authentication mechanisms

## Executive Summary

The Nightscout ecosystem uses **multiple authentication mechanisms** but has **no centralized identity provider (IdP)** for user verification. Current "trusted" identity providers are:

| Provider | Type | Ecosystem Role | Identity Scope |
|----------|------|----------------|----------------|
| **Tidepool** | OAuth 2.0 IdP | Data platform | User accounts |
| **Dexcom** | Session-based | CGM data source | Device access |
| **Medtronic CareLink** | OAuth-like | Pump/CGM data | Patient records |
| **Glooko** | OAuth 2.0 | Data aggregator | User accounts |
| **Abbott FreeStyle** | OAuth 2.0 | CGM data source | User accounts |
| **Tandem t:connect** | OAuth 2.0 | Pump data source | User accounts |

**Key Finding**: Only **Tidepool** functions as a true identity provider that clients can delegate authentication to. Others are data sources with their own auth, not identity providers for the Nightscout ecosystem.

---

## Identity Provider Categories

### 1. True Identity Providers (Authentication Delegation)

These systems can verify user identity on behalf of Nightscout:

| Provider | Protocol | Clients Using It |
|----------|----------|------------------|
| **Tidepool** | OAuth 2.0 | AAPS, Trio, xDrip+ |

#### Tidepool Integration

Tidepool is the **only external IdP** currently integrated with Nightscout ecosystem clients:

| Client | Tidepool Support | Integration Type |
|--------|------------------|------------------|
| **AndroidAPS** | ✅ | OAuth + data upload |
| **Trio** | ✅ | OAuth + data upload |
| **xDrip+** | ✅ | OAuth + data upload |
| **Loop** | ❌ | Not integrated |
| **xDrip4iOS** | ❌ | Not integrated |
| **cgm-remote-monitor** | ❌ | Not integrated |
| **Nocturne** | ✅ | Connector (OAuth) |

**Source**: `mapping/cross-project/interoperability-matrix.md:22-25`

### 2. Data Source Authentication (Not Identity Providers)

These require credentials but don't provide identity services to Nightscout:

#### Dexcom Share

| Aspect | Details |
|--------|---------|
| **Auth Type** | Username/password → session ID |
| **Endpoints** | `/ShareWebServices/Services/General/AuthenticatePublisherAccount` |
| **App ID** | `d89443d2-327c-4a6f-89e5-496bbb0317db` |
| **Regions** | US (`share2.dexcom.com`), OUS (`shareous1.dexcom.com`) |

**Source**: `externals/nightscout-connect/lib/sources/dexcomshare.js`

#### Medtronic CareLink

| Aspect | Details |
|--------|---------|
| **Auth Type** | SSO login → token cookie |
| **Endpoints** | `/patient/sso/login`, `/patient/sso/reauth` |
| **Regions** | US (`carelink.minimed.com`), EU (`carelink.minimed.eu`) |
| **Features** | M2M patient access, multi-patient support |

**Source**: `externals/nightscout-connect/lib/sources/minimedcarelink/index.js`

#### Abbott LibreLink Up

| Aspect | Details |
|--------|---------|
| **Auth Type** | OAuth with `AuthTicket` |
| **Features** | 2FA support, `TrustedDeviceToken` |
| **Response** | User profile, device info |

**Source**: `externals/nightscout-librelink-up/src/interfaces/librelink/login-response.ts`

#### Tandem t:connect

| Aspect | Details |
|--------|---------|
| **Auth Type** | Email/password with caching |
| **Storage** | `.creds_cache` file |
| **Regions** | US/EU |

**Source**: `externals/tconnectsync/tconnectsync/api/`

#### Glooko

| Aspect | Details |
|--------|---------|
| **Auth Type** | OAuth 2.0 |
| **Data Types** | SGV, treatments |

**Source**: `mapping/nocturne/connectors.md:16`

---

## Nightscout Native Authentication

### Current State

Nightscout has its **own authentication system** that is independent of external IdPs:

| Method | Description | Grants |
|--------|-------------|--------|
| **API_SECRET** | SHA1 hash in header | Full admin (*) |
| **JWT Bearer** | HMAC-SHA256 token | Claim-based permissions |
| **Access Tokens** | `{name}-{hash}` format | Subject-based roles |
| **Query Tokens** | `?token=` or `?secret=` | Various |

**Source**: `docs/10-domain/nocturne-auth-compatibility.md`

### Authentication Gaps

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-AUTH-001 | `enteredBy` field is unverified | Under discussion |
| GAP-AUTH-002 | No authority hierarchy | Proposed |
| GAP-AUTH-003 | API_SECRET grants full admin | Known |
| GAP-AUTH-004 | No token revocation | Known |
| GAP-AUTH-005 | JWT secret in node_modules | Known |
| GAP-AUTH-006 | JWT secret storage location | Known |
| GAP-AUTH-007 | No account lockout | Known |

**Source**: `traceability/nightscout-api-gaps.md:261-345`

---

## OIDC Proposal (Future State)

### NRG Gateway OIDC Plugin

An RFC exists for integrating OpenID Connect into Nightscout:

| Component | Status | Description |
|-----------|--------|-------------|
| OAuth2 credentials storage | ✅ Implemented | `oauth2_credentials` table |
| Hydra client lifecycle | ✅ Implemented | Create/delete clients |
| Kratos session resolution | ✅ Implemented | Session lookup |
| NSJWT token exchange | ✅ Implemented | Token conversion |
| **OIDC discovery proxy** | ❌ Needed | Forward `.well-known` |
| **Actor claims in JWT** | ❌ Needed | Identity metadata |
| **Nightscout OIDC plugin** | ❌ Needed | Redirect/extract claims |

**Source**: `externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md`

### Benefits of OIDC

| Feature | Current State | With OIDC |
|---------|---------------|-----------|
| Actor identification | Freeform `enteredBy` | Cryptographic claims |
| Care team visibility | Not possible | Per-action attribution |
| Delegation tracking | Not possible | `act` claim support |
| Audit trails | Limited | HIPAA-grade |

---

## Identity Provider Taxonomy

### Do Dexcom/Medtronic/Glooko "Count" as IDPs?

**Answer: No** - they are **data sources**, not identity providers.

| Characteristic | True IdP (Tidepool) | Data Source (Dexcom) |
|----------------|---------------------|----------------------|
| Issues identity tokens | ✅ | ❌ |
| OAuth/OIDC discovery | ✅ | ❌ |
| User profile claims | ✅ | ❌ |
| Delegation support | ✅ | ❌ |
| Federation-ready | ✅ | ❌ |
| Purpose | Authentication | Data access |

### Why the Distinction Matters

- **Identity Provider**: Can verify "who you are" to other systems
- **Data Source**: Can only verify "you have access to this data"

Dexcom can confirm you have access to a CGM account, but cannot provide identity claims to Nightscout for care team management.

---

## Current Ecosystem Identity Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Identity Landscape                      │
└─────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   End User      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Tidepool      │    │ Dexcom        │    │ CareLink      │
│ (IdP)         │    │ (Data Source) │    │ (Data Source) │
│               │    │               │    │               │
│ OAuth 2.0     │    │ Session Auth  │    │ SSO/Token     │
│ Identity      │    │ CGM Data      │    │ Pump Data     │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                    │                    │
        │                    └────────┬───────────┘
        │                             │
        ▼                             ▼
┌───────────────┐    ┌───────────────────────────────────────────┐
│ AAPS/Trio/    │    │ nightscout-connect                        │
│ xDrip+        │    │ (polls data sources)                      │
│               │    │                                           │
│ • Upload to   │    │ No identity - only data relay             │
│   Tidepool    │    │                                           │
│ • Upload to   │    └───────────────────────────────────────────┘
│   Nightscout  │                      │
└───────┬───────┘                      │
        │                              │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ Nightscout Instance          │
        │                              │
        │ API_SECRET / JWT / Tokens    │
        │ (self-contained auth)        │
        │                              │
        │ No external IdP integration  │
        └──────────────────────────────┘
```

---

## Recommendations

### For Item #24 (Community IdP Proposal)

Based on this inventory, a community identity provider should:

1. **Be OIDC-compliant** - Standard protocol, not proprietary
2. **Support federation** - Allow multiple IdPs (Tidepool + community)
3. **Provide actor claims** - Enable care team visibility
4. **Be hosted by trusted parties** - NS hosting providers council

### Candidate Providers for Community IdP

| Option | Pros | Cons |
|--------|------|------|
| **Ory Kratos/Hydra** | Already in NRG stack | Complex deployment |
| **Keycloak** | Full-featured, widely used | Heavy resource needs |
| **Auth0** | Managed, easy setup | Vendor lock-in, cost |
| **Tidepool** | Already trusted, diabetes-focused | Third-party dependency |

### Trust Hierarchy

```
1. User/Patient (highest authority)
   ↓
2. Designated Caregivers (parents, partners)
   ↓
3. Healthcare Providers (clinics, doctors)
   ↓
4. Institutional Access (schools, camps)
   ↓
5. Automated Agents (AID controllers)
   ↓
6. Read-only Followers (lowest authority)
```

---

## Related Documentation

- [OIDC Actor Identity Proposal](../../externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md)
- [Nocturne Auth Compatibility](nocturne-auth-compatibility.md)
- [Interoperability Matrix](../../mapping/cross-project/interoperability-matrix.md)
- [Nocturne Connectors](../../mapping/nocturne/connectors.md)

---

## Gaps Identified

| ID | Description |
|----|-------------|
| GAP-IDP-001 | No ecosystem-wide identity provider |
| GAP-IDP-002 | Tidepool is only external IdP, limited client support |
| GAP-IDP-003 | No care team management in Nightscout |

---

## References

- `mapping/cross-project/interoperability-matrix.md`
- `mapping/nocturne/connectors.md`
- `traceability/nightscout-api-gaps.md`
- `externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md`
- `externals/nocturne/docs/plans/authentication-oidc-implementation.md`
