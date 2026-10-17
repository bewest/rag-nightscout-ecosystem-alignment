# TestFlight Distribution Infrastructure

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #10  
> **Related**: App Store Pathway Analysis (cycle 61)

**Corrected 2026-10-17:** facts about Apple's programs were checked against Apple's pages, read on
2026-10-17, and corrected in place: TestFlight limits, including the 90-day build expiry (§1.2);
the fee, regional pricing and the nonprofit fee waiver, and the App Store requirements on health
apps (§1.1); the Xcode version, the free-account limits and the first-launch check-in (§1.3);
which entitlements need a paid membership (§3.1, §3.2); the certificate-expiry figure and what
happens when a membership expires (§4.3); and an open question for counsel on certificate custody
(§1.2). The findings and sources are in [Apple accountability §7.1](../60-research/structures-2026-10-17/apple-accountability.md#7-corrections-to-existing-repository-pages).
Apple changes these pages often; re-read the source before quoting a figure. The descriptions of
Apple's agreements are a non-lawyer's reading, to be checked by counsel.

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
- Apple Developer Program ($99/year; Apple says "Prices may vary by region"). A nonprofit that is
  a legal entity recognised by a relevant authority (in the US, the IRS), enrolling as an
  organisation, may apply for a fee waiver if it does not offer paid apps or in-app purchases and
  does not otherwise sell digital goods or services through its apps
  ([fee waivers](https://developer.apple.com/help/account/membership/fee-waivers/), read
  2026-10-17). Individuals and sole proprietors are not eligible.
- App Store review approval
- Privacy policy, support URL
- Apple's App Review Guidelines on health apps
  ([guidelines](https://developer.apple.com/app-store/review/guidelines/), read 2026-10-17). Apple
  does not use the phrase "no therapeutic claims"; the relevant guidelines are:
  - 1.4.1: medical apps "may be reviewed with greater scrutiny"; apps must disclose data and
    methodology behind health-measurement accuracy claims; if the app has regulatory clearance,
    submit a link to that documentation.
  - 1.4.2: drug dosage calculators must come from an approved kind of organisation (for example a
    drug manufacturer, hospital or pharmacy) or be approved by the FDA or an international
    counterpart.
  - 5.1.1(ix): apps that provide services in highly regulated fields such as healthcare "should be
    submitted by a legal entity that provides the services, and not by an individual developer."
- A regulated medical device status declaration, for apps distributed in the EEA, UK or US in the
  Health & Fitness or Medical categories (or that report frequent medical or treatment
  information in the age rating). Required for new apps since March 26, 2026; existing apps "must
  provide a status by early 2027", after which updates cannot be submitted
  ([Apple news, 2026-03-26](https://developer.apple.com/news/?id=nyqbfz1y)).
- A trader status declaration under the EU Digital Services Act (DSA). Every developer must declare
  a status, "Even if you don't distribute apps in the EU"
  ([DSA trader requirements](https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements), read 2026-10-17).

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

**TestFlight limits** (Apple's beta-testing service;
[TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview)
and [TestFlight](https://developer.apple.com/testflight/), read 2026-10-17):
- A build can be tested for up to 90 days; after 90 days it becomes unavailable to testers. This
  is why the browser-build workflows rebuild on a schedule (§2.1).
- Up to 100 internal testers, who must be App Store Connect users with a role on the team.
- Up to 10,000 external testers. The first build added to a tester group is sent to App Review.
- Up to 100 builds can be shared.

**Certificate custody (open question for counsel).** In this pattern the distribution certificate
is stored, encrypted, in the user's own private repository (the Match repository) and used by
hosted CI runners (GitHub's build machines) for the user's own builds. Apple's Developer Program
License Agreement (DPLA) §5.1 says the developer will "safeguard Your Apple Certificates and keys
from compromise (e.g., You will not upload Your Apple Certificate for App Store distribution to a
cloud repository for use by a third party)", and that certificates used for App Store distribution
may not be provided or transferred to a Service Provider
([DPLA](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/), read
2026-10-17). How that wording applies when developers store their own certificate for their own
builds has not been reviewed. This is a question for counsel, not a finding that anyone is in breach
([Apple accountability §8, item 3](../60-research/structures-2026-10-17/apple-accountability.md#8-points-for-a-reviewer-to-verify)).

### 1.3 Self-Build (Xcode)

**All apps support** self-build with Xcode on macOS.

**Requirements:**
- Mac with a current Xcode. The minimum depends on each app's build instructions. For uploads to
  App Store Connect, including TestFlight, Apple has required Xcode 26 or later since April 28, 2026
  ([upcoming requirements](https://developer.apple.com/news/upcoming-requirements/), read
  2026-10-17).
- Apple Developer account (free or paid). A free account (Xcode calls it a "personal team") has
  these limits ([developer account overview](https://developer.apple.com/help/account/basics/about-your-developer-account), read 2026-10-17):
  - provisioning profiles (the signed files that let a self-built app install and run on a
    device) expire 7 days after issue, so the app must be rebuilt and reinstalled every 7 days;
  - up to 3 devices and up to 10 App IDs, each expiring after 7 days;
  - up to 3 apps per device;
  - no Push notifications, Time Sensitive Notifications or NFC Tag Reading
    ([supported capabilities](https://developer.apple.com/help/account/reference/supported-capabilities-ios));
  - no access to Certificates, Identifiers & Profiles, where Critical Alerts must be requested
    ([capability requests](https://developer.apple.com/help/account/capabilities/capability-requests/)),
    so a free account cannot get Critical Alerts;
  - no TestFlight or App Store Connect.
- Code signing certificate
- Device registration
- Internet access at first launch, for paid teams created after June 6, 2021: development- and
  ad hoc-signed apps "check in with the PPQ service when the app is first launched … If the device
  can't successfully make a connection, the app may not launch." An offline profile valid for 7
  days is available
  ([provisioning profile updates](https://developer.apple.com/help/account/provisioning-profiles/provisioning-profile-updates), read 2026-10-17).

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

NFC Tag Reading and Critical Alerts need a paid Apple Developer Program membership; a free account
cannot use them (§1.3). HealthKit, background modes and App Groups are available to free accounts.

### 3.2 Special Entitlements

**Critical Alerts** (`com.apple.developer.usernotifications.critical-alerts`):
- Requires Apple approval, requested by the team's Account Holder through Certificates,
  Identifiers & Profiles; not available to free accounts
- Bypasses Do Not Disturb
- Essential for glucose alarms

**NFC Tag Reading** (`com.apple.developer.nfc.readersession.formats`):
- Required for Libre sensor scanning
- Only xDrip4iOS and DiaBLE
- Not available to free accounts

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

1. **Certificate expiration** - Certs expire after 1 year (not stated on the Apple pages read on
   2026-10-17; unverified). Separately: TestFlight builds stop working after 90 days regardless of
   certificates (§1.2), and when a paid membership expires, apps already installed from the App
   Store keep working, but no new apps or updates can be submitted
   ([renewal](https://developer.apple.com/help/account/membership/renewal), read 2026-10-17).
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
