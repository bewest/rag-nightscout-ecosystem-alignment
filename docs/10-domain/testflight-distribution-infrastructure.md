# TestFlight Distribution Infrastructure

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #10  
> **Related**: App Store Pathway Analysis (cycle 61)

---

## Executive Summary

This document surveys TestFlight and distribution infrastructure across the Nightscout iOS ecosystem, documenting build automation, signing requirements, and barriers to entry.

### Distribution Matrix

| App | App Store | TestFlight | GitHub Actions | Fastlane | Self-Build |
|-----|-----------|------------|----------------|----------|------------|
| **Loop** | ❌ | ✅ Browser Build | ✅ | ✅ | ✅ |
| **Trio** | ❌ | ✅ Browser Build | ✅ | ✅ | ✅ |
| **xDrip4iOS** | ❌ | ✅ Browser Build | ✅ | ✅ | ✅ |
| **LoopFollow** | ❌ | ✅ Browser Build | ✅ | ✅ | ✅ |
| **LoopCaregiver** | ❌ | ✅ Browser Build | ✅ | ✅ | ✅ |
| **Nightguard** | ✅ | ✅ | ❌ | ✅ | ✅ |
| **DiaBLE** | ✅ | ✅ | ❌ | ❌ | ✅ |

### Key Finding

**"Browser Build" pattern dominates** - Most apps support building via GitHub Actions with secrets, eliminating need for local Xcode.

---

## 1. Distribution Models

### 1.1 App Store (Public)

**Apps Available:**
- **Nightguard** - Free on App Store
- **DiaBLE** - Free on App Store

**Requirements:**
- Apple Developer Program ($99/year)
- App Store review approval
- Privacy policy, support URL
- No therapeutic claims

### 1.2 TestFlight via Browser Build

**Apps Supporting:**
- Loop, Trio, xDrip4iOS, LoopFollow, LoopCaregiver

**How It Works:**
1. Fork repository to personal GitHub
2. Add secrets (TEAMID, certificates, API key)
3. Run GitHub Actions workflow
4. App uploads to TestFlight automatically
5. Install via TestFlight app

**Required Secrets:**
```
TEAMID              # Apple Developer Team ID
GH_PAT              # GitHub Personal Access Token
FASTLANE_KEY_ID     # App Store Connect API Key ID
FASTLANE_ISSUER_ID  # App Store Connect Issuer ID
FASTLANE_KEY        # App Store Connect API Key (base64)
MATCH_PASSWORD      # Encryption password for certificates
```

### 1.3 Self-Build (Xcode)

**All apps support** self-build with Xcode on macOS.

**Requirements:**
- Mac with Xcode 15+
- Apple Developer account (free or paid)
- Code signing certificate
- Device registration

---

## 2. Build Automation

### 2.1 GitHub Actions Workflows

| App | Build Workflow | Cert Workflow | Auto-Build |
|-----|----------------|---------------|------------|
| Loop | `build_loop.yml` | `create_certs.yml` | Weekly |
| Trio | `build_trio.yml` | `create_certs.yml` | Weekly |
| xDrip4iOS | `build_xdrip.yml` | - | Manual |
| LoopFollow | `build_LoopFollow.yml` | `create_certs.yml` | Manual |
| LoopCaregiver | `build_loopcaregiver.yml` | `create_certs.yml` | Manual |
| Nightguard | ❌ | ❌ | ❌ |
| DiaBLE | ❌ | ❌ | ❌ |

### 2.2 Trio Build Workflow

```yaml
# .github/workflows/build_trio.yml
name: 4. Build Trio
on:
  workflow_dispatch:
  schedule:
    - cron: "43 6 * * 0"  # Weekly Sunday

jobs:
  check_status:
    # Sync from upstream, check for updates
  build:
    # Build and upload to TestFlight
```

**Features:**
- Syncs from upstream `nightscout/Trio`
- Only builds if new commits or 2nd Sunday
- Uploads to TestFlight automatically
- Uses Fastlane for signing and upload

### 2.3 Fastlane Configuration

All browser-build apps use similar Fastlane setup:

```ruby
# Fastfile
platform :ios do
  lane :build do
    setup_ci if ENV['CI']
    
    update_project_team(
      path: "Project.xcodeproj",
      teamid: ENV["TEAMID"]
    )
    
    api_key = app_store_connect_api_key(
      key_id: ENV["FASTLANE_KEY_ID"],
      issuer_id: ENV["FASTLANE_ISSUER_ID"],
      key_content: ENV["FASTLANE_KEY"]
    )
    
    match(type: "appstore", api_key: api_key)
    
    build_app(scheme: "AppScheme")
    
    upload_to_testflight(
      api_key: api_key,
      skip_waiting_for_build_processing: true
    )
  end
end
```

---

## 3. Signing Requirements

### 3.1 Entitlements by App

| Entitlement | Loop | Trio | xDrip4iOS | Nightguard | DiaBLE |
|-------------|------|------|-----------|------------|--------|
| HealthKit | ✅ | ✅ | ✅ | ✅ | ✅ |
| Background Delivery | ✅ | ✅ | ✅ | ✅ | ✅ |
| App Groups | ✅ | ✅ | ✅ | ✅ | ✅ |
| Critical Alerts | ✅ | ✅ | ✅ | ✅ | ✅ |
| NFC Tag Reading | ❌ | ❌ | ✅ | ❌ | ✅ |
| Bluetooth Central | ✅ | ✅ | ✅ | ❌ | ✅ |

### 3.2 Special Entitlements

**Critical Alerts** (`com.apple.developer.usernotifications.critical-alerts`):
- Requires Apple approval
- Bypasses Do Not Disturb
- Essential for glucose alarms

**NFC Tag Reading** (`com.apple.developer.nfc.readersession.formats`):
- Required for Libre sensor scanning
- Only xDrip4iOS and DiaBLE

### 3.3 Certificate Types

| Type | Purpose | Browser Build | Self-Build |
|------|---------|---------------|------------|
| Development | Testing on device | Match | Xcode auto |
| Distribution | TestFlight/App Store | Match | Manual |
| Push Notification | Remote notifications | Match | Manual |

---

## 4. Barriers to Entry

### 4.1 For End Users

| Barrier | Browser Build | Self-Build | App Store |
|---------|---------------|------------|-----------|
| Apple Developer ($99/yr) | ⚠️ Required | ⚠️ For TestFlight | ❌ Not needed |
| GitHub Account | ⚠️ Required | ❌ Not needed | ❌ Not needed |
| Technical Knowledge | Medium | High | Low |
| Mac Computer | ❌ Not needed | ⚠️ Required | ❌ Not needed |
| Build Time | ~15 min | ~30 min | Instant |

### 4.2 Complexity Ranking

| Method | Complexity | Time to First Install |
|--------|------------|----------------------|
| App Store (Nightguard/DiaBLE) | ⭐ Easy | 5 minutes |
| Browser Build | ⭐⭐ Medium | 1-2 hours (first time) |
| Self-Build Xcode | ⭐⭐⭐ Hard | 2-4 hours (first time) |

### 4.3 Common Issues

1. **Certificate expiration** - Certs expire after 1 year
2. **Provisioning profile mismatch** - App Group IDs must match
3. **GitHub secrets misconfiguration** - Base64 encoding issues
4. **TestFlight processing delays** - Can take 10-30 minutes
5. **App ID conflicts** - Bundle ID already registered

---

## 5. Standardization Opportunities

### 5.1 Shared Build Template

**Proposal:** Create standardized GitHub Actions workflow template.

```yaml
# .github/workflows/build_ios_app.yml (template)
name: Build iOS App
on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 0"  # Weekly

jobs:
  build:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: nightscout/ios-build-action@v1
        with:
          scheme: ${{ inputs.scheme }}
          team_id: ${{ secrets.TEAMID }}
          # ... standardized inputs
```

### 5.2 Unified Documentation

**Current state:** Each app has separate build docs.

**Proposal:** Centralized build guide at `docs.nightscout.org/ios-build`.

### 5.3 Shared Match Repository

**Current state:** Each user creates own match repo.

**Proposal:** Document best practices for match repo organization.

---

## 6. Gap Analysis

### GAP-DIST-001: No Standardized Build Template

**Description**: Each app has slightly different GitHub Actions workflow configuration.

**Affected Systems**: Loop, Trio, xDrip4iOS, LoopFollow, LoopCaregiver

**Evidence**:
- Different cron schedules
- Different secret names
- Different Fastfile structures

**Impact**: 
- Harder to maintain multiple apps
- Inconsistent user experience
- Duplicate documentation effort

**Remediation**: Create shared workflow template action.

### GAP-DIST-002: DiaBLE/Nightguard No Browser Build

**Description**: DiaBLE and Nightguard lack GitHub Actions build automation.

**Affected Systems**: DiaBLE, Nightguard

**Evidence**:
- No `.github/workflows/` build files
- No Matchfile for certificate management
- Relies on App Store or manual Xcode build

**Impact**: 
- Users must use App Store version (may lag updates)
- Or self-build with Xcode (high barrier)

**Remediation**: Add browser build workflow to these apps.

### GAP-DIST-003: No Unified Build Documentation

**Description**: Build documentation scattered across app repos and wikis.

**Affected Systems**: All iOS apps

**Evidence**:
- Loop: LoopDocs site
- Trio: README + docs folder
- xDrip4iOS: Wiki
- Different terminology, different steps

**Impact**: 
- Confusing for new users
- Hard to maintain across apps
- Duplicate effort

**Remediation**: Create unified iOS build guide.

---

## 7. Recommendations

### Short-term

1. **Document current patterns** - Reference this survey in app READMEs
2. **Standardize secret names** - Agree on TEAMID, GH_PAT, etc.
3. **Add browser build to Nightguard** - Fastlane already present

### Medium-term

1. **Create shared workflow action** - `nightscout/ios-build-action`
2. **Unified build documentation** - Single source of truth
3. **Certificate management guide** - Best practices for Match

### Long-term

1. **Ecosystem build dashboard** - Status of all app builds
2. **Automated update notifications** - Alert users of new versions
3. **One-click fork and build** - Simplified onboarding

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [app-store-pathway-analysis.md](app-store-pathway-analysis.md) | App Store viability |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM adoption |
| [cross-platform-testing-infrastructure-design.md](cross-platform-testing-infrastructure-design.md) | CI patterns |
