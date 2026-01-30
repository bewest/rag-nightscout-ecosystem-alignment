# Connector Bridge Deprecation Plan

> **Created**: 2026-01-30  
> **Purpose**: Consolidate legacy bridges into nightscout-connect  
> **Status**: Proposal  
> **Dependencies**: [Node.js LTS Analysis](node-lts-upgrade-analysis.md), [PR Sequencing](pr-adoption-sequencing-proposal.md)

---

## Executive Summary

Two legacy Nightscout connector bridges should be **deprecated and archived** in favor of `nightscout-connect`:

| Bridge | Status | Replacement |
|--------|--------|-------------|
| share2nightscout-bridge | ⚠️ Deprecated 2020 (`request` pkg) | nightscout-connect |
| minimed-connect-to-nightscout | ⚠️ EOL Node versions | nightscout-connect |

**Rationale**:
1. Both bridges depend on deprecated/EOL dependencies
2. `nightscout-connect` already implements both data sources
3. Consolidation reduces maintenance burden
4. Modern dependency stack (axios, xstate)

**Timeline**: Complete by **2026-03-31** (before Node 20 EOL)

---

## Current State Analysis

### share2nightscout-bridge

| Attribute | Value |
|-----------|-------|
| Repository | `nightscout/share2nightscout-bridge` |
| Version | 0.2.10 |
| Node.js | 16.x, 14.x, 12.x, 10.x, 8.x (all EOL) |
| Dependencies | `request` (deprecated 2020-02-11) |
| Function | Dexcom Share → Nightscout |
| Last commit | ~2022 |

**Technical Debt**:
- `request` package deprecated, no security updates
- No Node 18+ compatibility
- Single-source bridge (only Dexcom Share)

### minimed-connect-to-nightscout

| Attribute | Value |
|-----------|-------|
| Repository | `nightscout/minimed-connect-to-nightscout` |
| Function | Medtronic CareLink → Nightscout |
| Status | Maintenance mode |

**Technical Debt**:
- Separate codebase duplicating HTTP handling
- Not integrated with Nightscout plugin ecosystem

### nightscout-connect (Replacement)

| Attribute | Value |
|-----------|-------|
| Repository | `nightscout/nightscout-connect` |
| Version | 0.0.12 |
| Node.js | No engines field (modern, works on 18+) |
| Dependencies | axios 1.3.4, xstate 4.37.1, tough-cookie |
| Sources | 5 (Dexcom Share, LibreLinkUp, Minimed CareLink, Glooko, Nightscout) |
| Integration | Nightscout plugin + CLI sidecar |

**Advantages**:
- Modern dependency stack (axios, not `request`)
- State machine architecture (xstate) for robust sync
- Multiple data sources in single package
- Active development
- Plugin + sidecar deployment modes

---

## Feature Parity Matrix

### Dexcom Share Support

| Feature | share2nightscout-bridge | nightscout-connect |
|---------|------------------------|-------------------|
| US server (share2.dexcom.com) | ✅ | ✅ |
| OUS server (shareous1.dexcom.com) | ✅ | ✅ |
| Authentication | ✅ | ✅ |
| Glucose values | ✅ | ✅ |
| Trend arrows | ✅ | ✅ |
| Direction mapping | ✅ | ✅ |
| Gap filling | ✅ | ✅ |
| Retry/backoff | Basic | ✅ xstate-based |
| Node 18+ | ❌ | ✅ |
| Node 22+ | ❌ | ✅ |

**Parity**: ✅ Full feature parity

### Minimed CareLink Support

| Feature | minimed-connect-to-nightscout | nightscout-connect |
|---------|------------------------------|-------------------|
| EU server | ✅ | ✅ |
| US server | ✅ | ✅ |
| M2M authentication | ✅ | ✅ |
| Glucose values (SGS→SGV) | ✅ | ✅ |
| Cookie handling | ✅ | ✅ tough-cookie |
| Multi-patient (M2M) | ? | ✅ |
| Node 18+ | ? | ✅ |

**Parity**: ✅ Full feature parity (enhanced)

---

## Migration Guide

### For share2nightscout-bridge Users

#### Step 1: Update Environment Variables

| Old Variable | New Variable | Notes |
|--------------|--------------|-------|
| `BRIDGE_USER_NAME` | `CONNECT_DEXCOM_USERNAME` | Dexcom Share username |
| `BRIDGE_PASSWORD` | `CONNECT_DEXCOM_PASSWORD` | Dexcom Share password |
| `BRIDGE_SERVER` | `CONNECT_DEXCOM_REGION` | `us` or `ous` |
| `ENABLE=bridge` | `ENABLE=connect` | Plugin name change |
| - | `CONNECT_SOURCE=dexcomshare` | Required |

#### Step 2: For Heroku Deployments

```bash
# Remove old bridge
heroku config:unset BRIDGE_USER_NAME BRIDGE_PASSWORD BRIDGE_SERVER

# Add new connect
heroku config:set ENABLE=connect
heroku config:set CONNECT_SOURCE=dexcomshare
heroku config:set CONNECT_DEXCOM_USERNAME=your_username
heroku config:set CONNECT_DEXCOM_PASSWORD=your_password
heroku config:set CONNECT_DEXCOM_REGION=us
```

#### Step 3: For Docker Deployments

```yaml
# docker-compose.yml
environment:
  - ENABLE=connect
  - CONNECT_SOURCE=dexcomshare
  - CONNECT_DEXCOM_USERNAME=${DEXCOM_USER}
  - CONNECT_DEXCOM_PASSWORD=${DEXCOM_PASS}
  - CONNECT_DEXCOM_REGION=us
```

### For minimed-connect-to-nightscout Users

#### Step 1: Update Environment Variables

| Old Variable | New Variable | Notes |
|--------------|--------------|-------|
| `CARELINK_USERNAME` | `CONNECT_CARELINK_USERNAME` | CareLink username |
| `CARELINK_PASSWORD` | `CONNECT_CARELINK_PASSWORD` | CareLink password |
| `CARELINK_REGION` | `CONNECT_CARELINK_REGION` | `us` or `eu` |
| - | `ENABLE=connect` | Plugin name |
| - | `CONNECT_SOURCE=minimedcarelink` | Required |

#### Step 2: Sidecar Mode (Standalone)

```bash
# Install
npm install -g nightscout-connect

# Run
export CONNECT_SOURCE=minimedcarelink
export CONNECT_CARELINK_USERNAME=your_username
export CONNECT_CARELINK_PASSWORD=your_password
export CONNECT_CARELINK_REGION=us
export NIGHTSCOUT_URL=https://your-site.herokuapp.com
export NIGHTSCOUT_API_SECRET=your_api_secret

nightscout-connect forever
```

---

## Deprecation Actions

### Phase 1: Announce Deprecation (2026-02-15)

#### share2nightscout-bridge

1. **Add deprecation banner to README.md**:
```markdown
> ⚠️ **DEPRECATED**: This repository is deprecated and will be archived on 2026-03-31.
> 
> **Migration**: Use [nightscout-connect](https://github.com/nightscout/nightscout-connect) instead.
> See [Migration Guide](https://nightscout.github.io/connect-migration).
```

2. **Create GitHub issue** linking to migration guide

3. **Update Nightscout documentation** to recommend nightscout-connect

#### minimed-connect-to-nightscout

1. **Add deprecation banner** (same format)

2. **Link to nightscout-connect CareLink source**

### Phase 2: Final Release (2026-03-01)

1. **Publish final npm version** with deprecation warning in postinstall
2. **Add `npm deprecate` message**:
```bash
npm deprecate share2nightscout-bridge "This package is deprecated. Use nightscout-connect instead."
npm deprecate minimed-connect-to-nightscout "This package is deprecated. Use nightscout-connect instead."
```

### Phase 3: Archive Repositories (2026-03-31)

1. **Archive repositories** on GitHub (read-only)
2. **Keep npm packages** available but deprecated
3. **Update all documentation** to remove references

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Users miss deprecation notice | Medium | Medium | Multiple announcements, banner in README |
| nightscout-connect regression | Low | High | Feature parity testing before deprecation |
| CareLink API changes | Medium | Medium | nightscout-connect actively maintained |
| Dexcom API changes | Low | Medium | nightscout-connect actively maintained |
| Heroku rebuild issues | Low | Low | Clear migration guide |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Migration announcements | 100% | README, npm, issues, docs |
| User complaints | <10 | GitHub issues |
| nightscout-connect adoption | +50% | npm downloads |
| Support requests | <20 | Community forums |

---

## Timeline

| Date | Action |
|------|--------|
| 2026-02-15 | Deprecation banners added to READMEs |
| 2026-02-28 | Final npm releases with deprecation warnings |
| 2026-03-15 | npm deprecate commands run |
| 2026-03-31 | Repositories archived |
| 2026-04-30 | Node 20 EOL (deadline for all migrations) |

---

## Gaps Addressed

| Gap ID | Title | Status After Deprecation |
|--------|-------|-------------------------|
| GAP-NODE-002 | Deprecated `request` package | ✅ Closed |
| GAP-NODE-003 | Scattered bridge maintenance | ✅ Closed |

---

## Requirements Satisfied

| Requirement | Description |
|-------------|-------------|
| REQ-NODE-002 | Migrate away from deprecated packages |
| REQ-CONNECT-001 | Single unified connector interface |

---

## Cross-References

- [Node.js LTS Upgrade Analysis](node-lts-upgrade-analysis.md)
- [PR Adoption Sequencing Proposal](pr-adoption-sequencing-proposal.md)
- [Connector Gaps](../../traceability/connectors-gaps.md)
- [nightscout-connect README](https://github.com/nightscout/nightscout-connect)
