# ADR-003: No Custom Credentials in Nightscout Scope

**Status:** Proposed  
**Date:** 2026-01-17  
**Deciders:** Nightscout Foundation  
**Related:** [Authority Model](../10-domain/authority-model.md), [NRG Access Modes](../../externals/nightscout-roles-gateway/docs/access-modes.md)

---

## Context

Nightscout has historically avoided implementing traditional username/password authentication within its scope. This decision has been deliberate, driven by multiple forces:

### Liability and Risk

Implementing custom credential systems (username/password) exposes the project to significant liability:
- Password storage requires secure hashing, salting, and breach notification procedures
- Password reset flows create attack vectors (email enumeration, reset token theft)
- Credential stuffing attacks target sites with custom auth
- Security incident response requires organizational resources
- Legal exposure varies by jurisdiction (GDPR, HIPAA proximity, etc.)

Nightscout has chosen not to accept this liability and risk of being "hacked" in the traditional credential-theft sense.

### Data Rights vs. Access Control

Nightscout prioritizes informed consent and exercising data rights over gatekeeping via credentials:
- Users share their health data intentionally, not by proving identity to a system
- The person with diabetes (or their caregiver) decides who sees their data
- Access is granted by consent, not by credential validation
- This aligns with "your data, your choice" philosophy

### Multi-User Complexity

Authentication complexity exists in both multi-tenant and personal use cases:

| Scenario | Users Involved | Identity Providers |
|----------|----------------|-------------------|
| Personal instance | Self, spouse, parents, school nurse, endocrinologist | Google, Apple, school SSO, clinic portal |
| Family instance | Multiple PWD, multiple caregivers | Family members' various accounts |
| Clinic deployment | Staff, patients, parents | Clinic AD/Okta, patient portals |

Even "personal" Nightscout has multiple users with different access levels. Building robust multi-user auth is equally complex regardless of deployment model.

### Observed Antipatterns

Experience has shown that introducing credentials within Nightscout scope degrades overall security hygiene:

| Antipattern | Observed Behavior | Security Impact |
|-------------|-------------------|-----------------|
| "Mongo strings" confusion | Users share entire connection URIs in support threads | Database credential exposure |
| Password sharing | Users share Nightscout credentials with apps/caregivers | Credential sprawl, no revocation |
| Third-party client credentials | Apps request and store user passwords | Credential harvesting vectors |
| Screenshot sharing | Support involves sharing setup screens | Accidental secret exposure |

Adding more username/password flows would compound these problems rather than improve security posture.

### Zero Trust Direction

Modern security architecture moves toward "zero trust" principles:
- Never trust, always verify
- Identity federation over credential silos
- Short-lived tokens over persistent passwords
- Explicit consent over implicit access
- Attribute-based access over role-based (eventually)

Nightscout Roles Gateway implements identity-aware access control without managing credentials.

---

## Decision

**We will not implement custom username/password authentication within Nightscout's scope.**

Instead, we delegate authentication to external identity providers via OAuth2/OIDC federation:

1. **Identity providers manage credentials** — Google, Apple, Microsoft, clinic SSO systems handle password storage, MFA, breach detection
2. **NRG manages authorization** — Nightscout Roles Gateway handles who can access what, when, and how
3. **Consent is explicit** — Users join groups by authenticating with their identity provider and explicitly consenting
4. **Access is policy-driven** — Schedules, roles, and permissions control access, not credential possession

### The Three Access Modes

NRG provides three access modes that avoid custom credentials:

| Mode | Description | Credentials |
|------|-------------|-------------|
| **Mode A** | Anonymous/Public | None — link access only |
| **Mode B** | Identity-Mapped | Federated OAuth2/OIDC — no Nightscout password |
| **Mode C** | API Secret | Shared secret — legacy compatibility, not per-user |

---

## Consequences

### Positive

1. **Reduced liability** — No password database to be breached
2. **Better security hygiene** — Users don't create "yet another password"
3. **Enterprise-ready** — Clinic SSO integration is straightforward
4. **Modern security posture** — Aligns with zero trust, identity federation best practices
5. **Cleaner mental model** — "Show your ID" vs. "prove you know the secret"
6. **Consent-based access** — Aligns with data rights philosophy
7. **Reduced support burden** — No password reset flows to troubleshoot

### Negative

1. **Dependency on external providers** — Requires Google/Apple/etc. availability
2. **Setup complexity** — OAuth2 configuration is harder than username/password
3. **Offline access gaps** — Token refresh requires connectivity
4. **Provider account requirements** — Users must have identity provider accounts

### Neutral

1. **API secret remains** — Legacy Mode C provides backward compatibility but isn't per-user auth
2. **Identity provider choice** — Users must choose and configure at least one provider
3. **Organizational friction** — Some organizations have identity provider constraints

---

## Alternatives Considered

### Alternative A: Username/Password with Nightscout Accounts

Implement traditional credential-based auth where Nightscout manages user accounts.

**Rejected because:**
- Unacceptable liability for credential storage
- Password sharing habits would continue
- No better than current API_SECRET for many users
- Duplicates what identity providers already do well

### Alternative B: Passwordless Magic Links

Send email-based login links instead of passwords.

**Rejected because:**
- Still requires email storage and sender reputation management
- Email delivery reliability varies
- Not eliminated security responsibility, just shifted it
- OAuth2 providers already solve this better

### Alternative C: Hardware Token Only

Require FIDO2/WebAuthn hardware tokens for all access.

**Rejected because:**
- Adoption barrier too high for many users
- Cost of hardware tokens
- Recovery scenarios are complex
- Can layer this on top of OAuth2 if needed later

---

## Implementation

### Nightscout Roles Gateway

NRG implements this decision through:

1. **OAuth2/OIDC integration** — ORY Hydra/Kratos or similar for identity federation
2. **Group-based authorization** — Policies define who can access what
3. **Consent tracking** — `joined_groups` records explicit user consent
4. **Schedule enforcement** — Time-based access without credential changes

### Nightscout Core

cgm-remote-monitor integrates via:

1. **JWT token validation** — Accept tokens issued by NRG/identity providers
2. **`enteredBy` verification** — Map mutations to verified identities (proposed)
3. **API_SECRET deprecation path** — Gradual transition to identity-based access

### Mobile Apps

Apps integrate by:

1. **OAuth2 flows** — Standard authorization code flow with PKCE
2. **Token storage** — Secure local token storage (keychain/keystore)
3. **Refresh handling** — Automatic token refresh without password re-entry
4. **No credential collection** — Apps never ask for or store Nightscout passwords

---

## Compliance Notes

### For Site Owners

- Configure at least one identity provider
- Set Mode A (public) or Mode B (identity-mapped) based on sharing needs
- Use Mode C (API secret) only for legacy uploader compatibility
- Enable `require_identities = true` when identity-mapped access is desired

### For App Developers

- Implement OAuth2 authorization code flow with PKCE
- Never collect or store user passwords for Nightscout
- Request only necessary scopes
- Handle token expiration gracefully

### For Identity Providers

- Standard OAuth2/OIDC compliance
- Support for refresh tokens
- Reasonable token lifetimes (hours, not years)

---

## Metrics

Track success via:

1. **Identity-mapped adoption:** % of sites using Mode B
2. **API secret deprecation:** % of requests still using API secret
3. **Security incidents:** Count of credential-related issues (should be zero)
4. **Support volume:** Password-related support requests (should trend to zero)

---

## Open Questions

1. **Provider diversity:** How many identity providers should NRG support initially?
2. **Offline scenarios:** How do we handle extended offline periods for mobile apps?
3. **Migration timeline:** When can we deprecate Mode C (API secret)?
4. **Clinic integration:** What's the priority for enterprise SSO (SAML, etc.)?

---

## Related Decisions

- [ADR-001: Override Supersession](adr-001-override-supersession.md)
- [ADR-002: Sync Identity Strategy](adr-002-sync-identity-strategy.md)
- [Authority Model](../10-domain/authority-model.md)
- [NRG Access Modes](../../externals/nightscout-roles-gateway/docs/access-modes.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial proposal based on Nightscout Foundation rationale |
