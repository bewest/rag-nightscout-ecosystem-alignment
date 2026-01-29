# Playwright Adoption Proposal for cgm-remote-monitor

> **Target**: `nightscout/cgm-remote-monitor`  
> **Priority**: P1 (High Value, Low Effort)  
> **Status**: Proposal  
> **Date**: 2026-01-29

## Executive Summary

This proposal recommends adopting Playwright for end-to-end (E2E) testing in cgm-remote-monitor to complement the existing Mocha unit test suite. Playwright would enable browser-based testing of the web UI, reports, and real-time Socket.IO interactions that are currently untested or rely on outdated `benv` DOM simulation.

---

## Current Test Infrastructure

### Test Stack

| Component | Technology | Status |
|-----------|------------|--------|
| Unit Tests | Mocha 8.4.0 + should.js | ✅ Active (78 test files) |
| API Tests | supertest | ✅ Active (15 files use HTTP requests) |
| Coverage | nyc/Istanbul | ✅ Active |
| Browser Simulation | benv | ⚠️ Outdated, limited |
| E2E Tests | None | ❌ Missing |
| CI | GitHub Actions | ✅ Node 14/16/20 × MongoDB 4.4/5.0/6.0 |

### Test File Count

```
tests/
├── API tests:        ~30 files (api.*.test.js, api3.*.test.js)
├── Plugin tests:     ~25 files (*.test.js for plugins)
├── Unit tests:       ~20 files (utils, data, etc.)
├── Removed tests:    1 file (client.test.js.temporary_removed)
└── Total:            78 test files
```

### Gap: No Browser E2E Testing

The `client.test.js.temporary_removed` file indicates browser testing was previously attempted using `benv` but has been disabled. This leaves critical UI functionality untested:

- Main glucose dashboard
- Careportal treatment entry
- Report generation (reports.test.js uses DOM simulation)
- Settings panel
- Real-time Socket.IO updates
- Mobile responsiveness

---

## Why Playwright?

### Comparison with Alternatives

| Feature | Playwright | Cypress | Puppeteer | benv |
|---------|------------|---------|-----------|------|
| Multi-browser | ✅ Chrome, Firefox, Safari | ⚠️ Limited | Chrome only | ❌ |
| Parallel execution | ✅ Built-in | ✅ Paid | Manual | ❌ |
| Auto-wait | ✅ Smart waits | ✅ Smart waits | Manual | ❌ |
| Network mocking | ✅ Native | ✅ Native | ✅ Native | ❌ |
| Mobile emulation | ✅ Native | ✅ Plugin | ✅ Native | ❌ |
| TypeScript support | ✅ First-class | ✅ Good | ✅ Good | ❌ |
| CI integration | ✅ Excellent | ✅ Good | ✅ Good | ❌ |
| GitHub Actions | ✅ Official action | ✅ Official action | Manual | N/A |
| Learning curve | Medium | Low | Medium | N/A |
| License | Apache 2.0 | MIT | Apache 2.0 | N/A |

### Why Playwright Over Cypress

1. **Multi-browser support**: Nightscout users use Safari (iOS), Chrome, and Firefox
2. **No limitations**: Cypress has same-origin restrictions that complicate Socket.IO testing
3. **Parallel by default**: Faster CI runs without paid features
4. **Microsoft backing**: Active development, excellent documentation
5. **Native ES modules**: Better alignment with modern JavaScript

---

## Proposed Implementation

### Phase 1: Infrastructure Setup (1-2 days effort)

```bash
# Install Playwright
npm install -D @playwright/test
npx playwright install

# Create config
touch playwright.config.js
mkdir tests/e2e
```

**playwright.config.js**:
```javascript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  
  use: {
    baseURL: 'http://localhost:1337',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  
  webServer: {
    command: 'npm start',
    port: 1337,
    reuseExistingServer: !process.env.CI,
  },
});
```

### Phase 2: Core E2E Tests (3-5 days effort)

| Test File | Coverage |
|-----------|----------|
| `dashboard.spec.js` | Main view loads, SGV displays, direction arrows |
| `careportal.spec.js` | Add treatment, bolus wizard, notes |
| `reports.spec.js` | Generate daily report, AGP, distribution |
| `settings.spec.js` | Change units, enable plugins, save |
| `socket.spec.js` | Real-time data updates via Socket.IO |
| `auth.spec.js` | API secret, read-only access, roles |

### Phase 3: CI Integration (1 day effort)

Add to `.github/workflows/main.yml`:

```yaml
  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 20
      
      - name: Start MongoDB
        uses: supercharge/mongodb-github-action@1.3.0
        with:
          mongodb-version: 6.0
      
      - name: Install dependencies
        run: npm ci
      
      - name: Install Playwright browsers
        run: npx playwright install --with-deps
      
      - name: Run E2E tests
        run: npx playwright test
      
      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

### Phase 4: Advanced Scenarios (Ongoing)

- Mobile viewport testing (iPhone, Android)
- Accessibility audits with `@axe-core/playwright`
- Visual regression testing with `@playwright/test` snapshots
- Performance metrics collection
- Socket.IO connection resilience testing

---

## Example Test

**tests/e2e/dashboard.spec.js**:
```javascript
import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Seed test data via API
    await page.request.post('/api/v1/entries', {
      data: [{
        type: 'sgv',
        sgv: 120,
        direction: 'Flat',
        date: Date.now(),
        dateString: new Date().toISOString()
      }]
    });
  });

  test('displays current glucose value', async ({ page }) => {
    await page.goto('/');
    
    // Wait for Socket.IO connection and data load
    await expect(page.locator('#currentBG')).toBeVisible();
    await expect(page.locator('#currentBG')).toContainText('120');
  });

  test('shows direction arrow', async ({ page }) => {
    await page.goto('/');
    
    await expect(page.locator('.trend-arrow')).toHaveClass(/flat/);
  });

  test('updates in real-time', async ({ page }) => {
    await page.goto('/');
    
    // Wait for initial load
    await expect(page.locator('#currentBG')).toContainText('120');
    
    // Push new value via API
    await page.request.post('/api/v1/entries', {
      data: [{
        type: 'sgv',
        sgv: 150,
        direction: 'FortyFiveUp',
        date: Date.now(),
        dateString: new Date().toISOString()
      }]
    });
    
    // Verify real-time update (may need to wait for Socket.IO)
    await expect(page.locator('#currentBG')).toContainText('150', { timeout: 10000 });
  });
});
```

---

## Benefits

### For Development

1. **Catch UI regressions**: Changes to templates, CSS, or client JavaScript
2. **Document expected behavior**: Tests serve as executable specifications
3. **Faster debugging**: Trace viewer shows exact failure point
4. **Cross-browser confidence**: Ensure Safari, Firefox, Chrome compatibility

### For Modernization

1. **Safe refactoring**: E2E tests validate behavior during migration
2. **Bundle changes**: Verify Webpack modifications don't break UI
3. **React/Vue migration**: Tests remain valid regardless of framework
4. **API changes**: Catch client-server contract breaks

### For Ecosystem

1. **Loop/AAPS integration**: Test data flows from controllers to UI
2. **Plugin testing**: Verify plugins render correctly
3. **Report accuracy**: Ensure statistical calculations display correctly
4. **Accessibility**: Add axe-core for WCAG compliance

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Flaky tests | Use Playwright auto-wait, avoid fixed timeouts |
| Slow CI | Run E2E on merge only, parallel execution |
| MongoDB state | Use test fixtures, clean between runs |
| Socket.IO timing | Use `waitForResponse` or explicit socket events |
| Browser download | Cache in CI, use official GitHub Action |

---

## Effort Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Infrastructure | 1-2 days | None |
| Core tests (6) | 3-5 days | Infrastructure |
| CI integration | 1 day | Core tests |
| Advanced | Ongoing | Core tests |

**Total initial investment**: ~5-8 days

---

## Success Metrics

| Metric | Target |
|--------|--------|
| E2E test count | 20+ scenarios |
| Browser coverage | Chrome, Firefox, Safari |
| CI pass rate | >95% (flakiness <5%) |
| Run time | <5 minutes |
| UI regression detection | Catch before merge |

---

## Recommendation

**Adopt Playwright for E2E testing** in cgm-remote-monitor with the following priorities:

1. **Immediate**: Set up infrastructure and CI integration
2. **Short-term**: Cover critical paths (dashboard, careportal, reports)
3. **Ongoing**: Expand coverage as features are modified

This investment will significantly improve confidence in UI changes, especially during the modernization effort, and align with best practices in the broader JavaScript ecosystem.

---

## Related

- [cgm-remote-monitor Database Deep Dive](../10-domain/cgm-remote-monitor-database-deep-dive.md)
- [Nocturne Modernization Analysis](nocturne-modernization-analysis.md)
- [Tooling Backlog](backlogs/tooling.md)
