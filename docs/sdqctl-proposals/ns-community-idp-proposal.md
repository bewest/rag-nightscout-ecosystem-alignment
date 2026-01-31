# Nightscout Community Identity Provider Proposal

> **Backlog Item**: nightscout-api.md #24  
> **Date**: 2026-01-31  
> **Status**: Draft  
> **Prerequisite**: #23 Trusted Identity Providers Inventory ✅

---

## Executive Summary

This proposal outlines a path toward a **community-hosted identity provider (IdP)** for the Nightscout ecosystem. The goal is to provide a trusted, federated authentication layer that:

1. Enables care team identification and delegation
2. Provides stronger security than API_SECRET alone
3. Supports the fragmented hosting landscape
4. Maintains data sovereignty for users

### Key Recommendation

Establish a **Nightscout Hosting Providers Council** to collaboratively operate a federated OIDC identity layer, using Ory Kratos/Hydra (already in the NRG stack) as the technical foundation.

---

## Problem Statement

### Current Identity Landscape

The Nightscout ecosystem has **no centralized identity management**:

| Component | Authentication | Identity |
|-----------|---------------|----------|
| cgm-remote-monitor | API_SECRET, JWT, tokens | None |
| Loop | Device-local | None |
| AAPS | Device-local | Tidepool optional |
| Trio | Device-local | Tidepool optional |
| xDrip+ | Device-local | Tidepool optional |
| Nightscout hosting | Provider-specific | Provider accounts |

### Consequences

1. **No care team visibility**: Cannot identify who made changes
2. **No delegation model**: Cannot grant limited caregiver access
3. **No audit trails**: HIPAA/privacy compliance difficult
4. **No cross-site identity**: Each Nightscout instance is isolated
5. **Credential fatigue**: Users manage separate credentials everywhere

### Why This Matters Now

- Loop 4 and Trio exploring cross-device sync
- LoopCaregiver and LoopFollow need proper identity
- HIPAA interest from healthcare organizations
- Growing hosting provider ecosystem needs coordination

---

## Stakeholder Analysis

### Primary Stakeholders

| Stakeholder | Interest | Requirements |
|-------------|----------|--------------|
| **People with Diabetes (PwD)** | Single sign-on, data ownership | Easy onboarding, privacy |
| **Caregivers/Parents** | Scoped access, alerts | Delegation, audit |
| **Healthcare Providers** | HIPAA compliance | Attribution, logging |
| **App Developers** | Standard auth | OIDC, simple integration |
| **Hosting Providers** | User management | Federation, reduced support |

### NS Hosting Providers (Potential Council Members)

| Provider | Users (est.) | Region | Notes |
|----------|--------------|--------|-------|
| **t1pal** | 5,000+ | US | Largest managed hosting |
| **NS10BE** | 2,000+ | EU | European data residency |
| **nightscout.sh** | 1,000+ | Global | Heroku-alternative |
| **MongoDB Atlas + DIY** | 10,000+ | Global | Self-hosted users |
| **Fly.io users** | 500+ | Global | New migration target |

---

## Proposed Architecture

### Option A: Federated IdP Council (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nightscout Identity Federation               │
└─────────────────────────────────────────────────────────────────┘

     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
     │   t1pal      │     │   NS10BE     │     │ Tidepool     │
     │   IdP Node   │     │   IdP Node   │     │   (Trusted)  │
     │              │     │              │     │              │
     │ Ory Hydra    │     │ Ory Hydra    │     │ OAuth 2.0    │
     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │   Federation Registry    │
                    │   (OIDC Discovery Hub)   │
                    │                          │
                    │   • Trust relationships  │
                    │   • Provider directory   │
                    │   • Claim normalization  │
                    └────────────┬─────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  User's NS      │    │  LoopCaregiver  │    │  AAPS/Trio      │
│  Instance       │    │                 │    │                 │
│                 │    │                 │    │                 │
│  OIDC Plugin    │    │  OIDC Login     │    │  Tidepool OAuth │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Option B: Single Community IdP

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nightscout Community IdP                      │
│                    (auth.nightscout.community)                   │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │   Ory Kratos + Hydra    │
                    │                          │
                    │   • User registration   │
                    │   • OAuth 2.0 / OIDC    │
                    │   • Session management  │
                    │   • MFA support         │
                    └────────────┬─────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
    NS Instances           Mobile Apps           Web Apps
```

### Option Comparison

| Aspect | Federated (A) | Single (B) |
|--------|--------------|------------|
| **Complexity** | High | Medium |
| **Data Sovereignty** | ✅ Regional | ❌ Centralized |
| **Single Point of Failure** | ✅ Distributed | ❌ Central |
| **Governance** | Council required | Simpler |
| **User Choice** | ✅ Pick provider | ❌ One provider |
| **Implementation Time** | 12-18 months | 6-9 months |

---

## Organizational Requirements

### Nightscout Hosting Providers Council

#### Charter

1. **Membership**: NS hosting providers serving 500+ active users
2. **Governance**: Consensus-based decisions, annual elections
3. **Responsibilities**:
   - Operate federated IdP nodes
   - Maintain trust relationships
   - Fund shared infrastructure
   - Respond to security incidents

#### Operating Principles

| Principle | Implementation |
|-----------|----------------|
| **Data Sovereignty** | User data stays with chosen provider |
| **Privacy First** | Minimal claims, no tracking |
| **Open Source** | All components OSS |
| **Interoperability** | Standard OIDC, no vendor lock-in |
| **Sustainability** | Self-funding model |

### Trust Framework

```yaml
# Example trust policy
federation:
  name: nightscout-community
  version: 1.0
  
trust_levels:
  - level: verified_provider
    requirements:
      - oidc_compliant: true
      - security_audit: annual
      - gdpr_compliant: true  # if EU users
      - incident_response: 24h
      - uptime_sla: 99.5%
    
  - level: trusted_partner
    requirements:
      - organization_verification: true
      - terms_of_service: accepted
      - example: Tidepool
```

---

## Technical Requirements

### OIDC Implementation

#### Required Claims

| Claim | Purpose | Example |
|-------|---------|---------|
| `sub` | Unique user ID | `user_abc123` |
| `iss` | Issuing provider | `https://auth.t1pal.com` |
| `email` | Optional contact | `user@example.com` |
| `ns_role` | Nightscout role | `readable`, `admin`, `careportal` |
| `ns_sites` | Authorized sites | `["site1.ns.com", "site2.ns.com"]` |
| `act` | Delegation (optional) | `{"sub": "caregiver_id"}` |

#### Discovery Endpoint

```json
// GET /.well-known/openid-configuration
{
  "issuer": "https://auth.nightscout.community",
  "authorization_endpoint": "https://auth.nightscout.community/oauth2/auth",
  "token_endpoint": "https://auth.nightscout.community/oauth2/token",
  "userinfo_endpoint": "https://auth.nightscout.community/userinfo",
  "jwks_uri": "https://auth.nightscout.community/.well-known/jwks.json",
  "scopes_supported": ["openid", "profile", "email", "ns:read", "ns:write", "ns:admin"],
  "claims_supported": ["sub", "iss", "email", "ns_role", "ns_sites", "act"]
}
```

### cgm-remote-monitor Integration

#### Plugin Architecture

```javascript
// lib/server/oidc-plugin.js
module.exports = function oidcPlugin(env, ctx) {
  return {
    name: 'oidc',
    
    // Verify OIDC tokens
    verifyToken: async (token) => {
      const claims = await verifyJWT(token, {
        issuer: env.OIDC_ISSUERS.split(','),
        audience: env.OIDC_AUDIENCE
      });
      return claims;
    },
    
    // Map OIDC claims to NS permissions
    mapPermissions: (claims) => {
      return {
        readable: claims.ns_role !== 'none',
        careportal: ['careportal', 'admin'].includes(claims.ns_role),
        admin: claims.ns_role === 'admin',
        actor: claims.sub,
        delegatedBy: claims.act?.sub
      };
    }
  };
};
```

#### Environment Configuration

```bash
# .env additions for OIDC
OIDC_ENABLED=true
OIDC_ISSUERS=https://auth.t1pal.com,https://auth.ns10be.com,https://auth.tidepool.org
OIDC_AUDIENCE=nightscout
OIDC_JWKS_CACHE_TTL=3600
```

### Mobile App Integration

#### Swift (Loop/Trio/LoopCaregiver)

```swift
// NightscoutKit OIDC Extension
import AuthenticationServices

extension NightscoutClient {
    func authenticateOIDC(provider: OIDCProvider) async throws -> OIDCSession {
        let session = ASWebAuthenticationSession(
            url: provider.authorizationURL,
            callbackURLScheme: "nightscout"
        )
        
        let callbackURL = try await session.start()
        let code = extractCode(from: callbackURL)
        let tokens = try await provider.exchange(code: code)
        
        return OIDCSession(
            accessToken: tokens.access,
            idToken: tokens.id,
            refreshToken: tokens.refresh
        )
    }
}
```

#### Kotlin (AAPS)

```kotlin
// AAPS OIDC Integration
class NightscoutOIDCAuth(
    private val context: Context,
    private val provider: OIDCProvider
) {
    suspend fun authenticate(): OIDCTokens {
        val authIntent = CustomTabsIntent.Builder().build()
        val authUrl = provider.buildAuthorizationUrl()
        
        // Handle callback via deep link
        return suspendCancellableCoroutine { cont ->
            AuthCallbackReceiver.register { code ->
                CoroutineScope(Dispatchers.IO).launch {
                    val tokens = provider.exchangeCode(code)
                    cont.resume(tokens)
                }
            }
            authIntent.launchUrl(context, authUrl.toUri())
        }
    }
}
```

---

## Implementation Roadmap

### Phase 1: Foundation (Months 1-3)

| Task | Owner | Deliverable |
|------|-------|-------------|
| Establish Council charter | Community | `ns-idp-council-charter.md` |
| Recruit founding providers | Nightscout Foundation | 3+ providers |
| Select tech stack | Council | Decision document |
| Set up federation registry | Lead provider | `federation.nightscout.community` |

### Phase 2: Technical Build (Months 4-9)

| Task | Owner | Deliverable |
|------|-------|-------------|
| Deploy Ory stack at t1pal | t1pal | First IdP node |
| Deploy Ory stack at NS10BE | NS10BE | Second IdP node |
| Implement cgm-remote-monitor plugin | NS maintainers | PR to cgm-remote-monitor |
| Update NightscoutKit | NightscoutKit maintainers | OIDC support |

### Phase 3: Rollout (Months 10-12)

| Task | Owner | Deliverable |
|------|-------|-------------|
| Beta with 100 users | Council | Feedback report |
| Security audit | External auditor | Audit report |
| Documentation | Community | User guides |
| General availability | Council | Announcement |

---

## Gaps Identified

| ID | Gap | Impact |
|----|-----|--------|
| GAP-IDP-004 | No NS-native identity provider | No care team visibility |
| GAP-IDP-005 | No federation standard | Fragmented ecosystem |
| GAP-IDP-006 | OIDC plugin not in cgm-remote-monitor | Manual integration required |

---

## Requirements

| ID | Requirement |
|----|-------------|
| REQ-IDP-004 | Community IdP MUST be OIDC-compliant |
| REQ-IDP-005 | Federation MUST support multiple providers |
| REQ-IDP-006 | User data MUST remain with chosen provider |
| REQ-IDP-007 | All components MUST be open source |

---

## Success Criteria

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Participating providers | ≥3 | Month 6 |
| Users with OIDC accounts | 1,000 | Month 12 |
| Apps with OIDC support | ≥3 (NS, Loop, AAPS) | Month 12 |
| Uptime | 99.5% | Ongoing |
| Security incidents | 0 critical | Year 1 |

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Provider non-participation | Medium | High | Start with committed core |
| Technical complexity | High | Medium | Phased rollout, proven stack |
| User adoption resistance | Medium | Medium | Opt-in, gradual migration |
| Governance disputes | Low | High | Clear charter, voting rules |
| Security breach | Low | Critical | Audit, incident response |

---

## Related Documents

- `docs/10-domain/trusted-identity-providers.md` - Prerequisite inventory
- `externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md` - NRG OIDC RFC
- `specs/openapi/nocturne-v4-extension.yaml` - V4 API (uses OIDC)
- `docs/sdqctl-proposals/nightscout-v4-integration-proposal.md` - V4 integration context

---

## Conclusion

A community identity provider is **feasible and valuable** for the Nightscout ecosystem. The recommended approach is:

1. **Federated architecture** with Hosting Providers Council
2. **Ory Kratos/Hydra** as technical foundation (NRG-compatible)
3. **Phased rollout** starting with willing providers
4. **OIDC standard** for maximum interoperability

The primary challenge is **organizational** (forming the council) rather than technical (the stack exists). Success depends on buy-in from t1pal, NS10BE, and other hosting providers.

### Next Steps

1. Socialize proposal with hosting providers
2. Gauge interest in council formation
3. If positive, proceed to Phase 1 charter development
