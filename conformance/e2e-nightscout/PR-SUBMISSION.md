# Playwright E2E Tests - PR Submission Guide

> **Target Repository**: nightscout/cgm-remote-monitor  
> **PR Type**: Feature addition  
> **Status**: Ready for submission

---

## PR Title

```
feat: add Playwright E2E testing framework
```

## PR Description

```markdown
## Summary

This PR adds end-to-end testing support using [Playwright](https://playwright.dev/), providing browser-based testing for the Nightscout dashboard and API endpoints.

## Changes

### New Files
- `playwright.config.js` - Playwright configuration with multi-browser support
- `tests/e2e/dashboard.spec.js` - Dashboard UI tests (8 tests)
- `tests/e2e/api.spec.js` - API smoke tests (10 tests)

### Modified Files
- `package.json` - Added npm scripts for E2E testing

## Test Coverage

### Dashboard Tests
| Test | Description |
|------|-------------|
| page loads successfully | Verifies basic page render and title |
| displays current glucose value | Checks BG value is visible |
| shows direction arrow | Validates trend indicator |
| displays time since last reading | Time ago element |
| header plugins render | Plugin container visibility |
| mobile view renders correctly | Responsive layout |
| updates glucose value via Socket.IO | Real-time updates |
| handles no data gracefully | Error resilience |

### API Tests
| Test | Description |
|------|-------------|
| GET /api/v1/status | Server info response |
| GET /api/v1/entries | Entries array |
| POST /api/v1/entries auth | Authentication required |
| POST /api/v1/entries success | Write with API secret |
| GET /api/v1/treatments | Treatments array |
| GET /api/v1/devicestatus | DeviceStatus array |
| GET /api/v3/version | v3 API availability |
| GET /api/v3/entries | v3 entries response |
| GET /api/v3/treatments | v3 treatments response |
| Error handling | 404, malformed JSON |

## Usage

```bash
# Install Playwright
npm install -D @playwright/test
npx playwright install

# Run all tests
npm run test:e2e

# Run with UI (interactive mode)
npm run test:e2e:ui

# Run specific browser
npx playwright test --project=chromium

# View report
npm run test:e2e:report
```

## CI Integration

The config includes CI-friendly settings:
- Automatic retries on CI (2 retries)
- Screenshots and traces on failure
- HTML report generation
- Parallel worker support

Example GitHub Actions job included in README.

## Related Issues

- Addresses need for browser-based testing
- Complements existing Mocha API tests

## Checklist

- [x] Tests pass locally
- [x] Configuration is environment-aware (CI detection)
- [x] Multi-browser support (Chrome, Firefox, Safari, Mobile)
- [x] Documentation included
- [x] No breaking changes to existing tests
```

---

## Submission Steps

### 1. Fork and Clone

```bash
# Fork cgm-remote-monitor on GitHub, then:
git clone https://github.com/YOUR_USERNAME/cgm-remote-monitor.git
cd cgm-remote-monitor
git checkout -b feat/playwright-e2e
```

### 2. Copy Files

```bash
# From this workspace:
cp /path/to/rag-nightscout-ecosystem-alignment/conformance/e2e-nightscout/playwright.config.js .
mkdir -p tests/e2e
cp /path/to/rag-nightscout-ecosystem-alignment/conformance/e2e-nightscout/*.spec.js tests/e2e/
```

### 3. Update package.json

Add to the `scripts` section:

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:report": "playwright show-report"
  }
}
```

Add to `devDependencies`:

```json
{
  "devDependencies": {
    "@playwright/test": "^1.40.0"
  }
}
```

### 4. Install and Test

```bash
npm install
npx playwright install chromium
npm run test:e2e -- --project=chromium
```

### 5. Commit and Push

```bash
git add .
git commit -m "feat: add Playwright E2E testing framework"
git push origin feat/playwright-e2e
```

### 6. Create PR

Open PR from your fork to `nightscout/cgm-remote-monitor:dev`

---

## Environment Requirements

| Requirement | Version |
|-------------|---------|
| Node.js | ≥18.x |
| MongoDB | ≥5.x (for webServer) |
| Playwright | ≥1.40.0 |

## Notes for Maintainers

1. **Browser Installation**: First-time users need `npx playwright install`
2. **CI Workflow**: Example workflow provided; adapt to existing CI
3. **Test Database**: Uses separate `nightscout_test` database
4. **API Secret**: Uses `testapisecrethash` for test auth

---

## Cross-References

- [Playwright Adoption Proposal](../../docs/sdqctl-proposals/playwright-adoption-proposal.md)
- [Nightscout API Backlog](../../docs/sdqctl-proposals/backlogs/nightscout-api.md)
- [cgm-remote-monitor Deep Dive](../../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)
