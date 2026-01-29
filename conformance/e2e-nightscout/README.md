# Nightscout E2E Test Suite

Playwright-based end-to-end tests for cgm-remote-monitor.

## Overview

This directory contains E2E test artifacts that can be submitted as a PR to `nightscout/cgm-remote-monitor` to add Playwright testing support.

## Files

| File | Purpose |
|------|---------|
| `playwright.config.js` | Playwright configuration (copy to cgm-remote-monitor root) |
| `dashboard.spec.js` | Dashboard UI tests (copy to tests/e2e/) |
| `api.spec.js` | API smoke tests (copy to tests/e2e/) |

## Usage

### In cgm-remote-monitor

1. **Install Playwright**:
   ```bash
   npm install -D @playwright/test
   npx playwright install
   ```

2. **Copy configuration**:
   ```bash
   cp playwright.config.js /path/to/cgm-remote-monitor/
   mkdir -p /path/to/cgm-remote-monitor/tests/e2e
   cp *.spec.js /path/to/cgm-remote-monitor/tests/e2e/
   ```

3. **Add npm script** to package.json:
   ```json
   {
     "scripts": {
       "test:e2e": "playwright test",
       "test:e2e:ui": "playwright test --ui",
       "test:e2e:report": "playwright show-report"
     }
   }
   ```

4. **Run tests**:
   ```bash
   npm run test:e2e
   ```

### In This Workspace

For development/testing of the E2E tests themselves:

```bash
cd conformance/e2e-nightscout
npx playwright test --config=playwright.config.js
```

Note: Requires a running Nightscout instance at localhost:1337.

## Test Categories

### Dashboard Tests (`dashboard.spec.js`)

| Test | Validates |
|------|-----------|
| page loads successfully | Basic page render, title |
| displays current glucose value | BG value visible |
| shows direction arrow | Trend indicator |
| displays time since last reading | Time ago element |
| header plugins render | Plugin container |
| mobile view renders correctly | Responsive layout |
| updates glucose value via Socket.IO | Real-time updates |
| handles no data gracefully | Error resilience |

### API Tests (`api.spec.js`)

| Test | Validates |
|------|-----------|
| GET /api/v1/status | Server info response |
| GET /api/v1/entries | Entries array |
| POST /api/v1/entries auth | Authentication required |
| POST /api/v1/entries success | Write with API secret |
| GET /api/v3/version | v3 API availability |
| Error handling | 404, malformed JSON |

## CI Integration

Add to `.github/workflows/main.yml`:

```yaml
e2e:
  name: E2E Tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: 20
    
    - name: Start MongoDB
      uses: supercharge/mongodb-github-action@1.10.0
      with:
        mongodb-version: 6.0
    
    - name: Install dependencies
      run: npm ci
    
    - name: Install Playwright browsers
      run: npx playwright install --with-deps chromium
    
    - name: Run E2E tests
      run: npx playwright test --project=chromium
    
    - name: Upload test results
      uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: playwright-report
        path: playwright-report/
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NIGHTSCOUT_URL` | `http://localhost:1337` | Base URL for tests |
| `API_SECRET` | `testapisecrethash` | API secret for authentication |
| `MONGODB_URI` | `mongodb://localhost:27017/nightscout_test` | MongoDB connection |
| `CI` | - | Set in CI to enable retries |

## Extending Tests

### Adding New Tests

Create `tests/e2e/<feature>.spec.js`:

```javascript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test('does something', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#element')).toBeVisible();
  });
});
```

### Testing Authenticated Features

```javascript
test('admin feature', async ({ page, request }) => {
  // Authenticate
  await request.post('/api/v2/authorization/request/token', {
    data: { token: 'your-token' },
  });
  
  // Now access authenticated page
  await page.goto('/admin');
});
```

## Cross-References

- [Playwright Adoption Proposal](../../docs/sdqctl-proposals/playwright-adoption-proposal.md)
- [cgm-remote-monitor API Deep Dive](../../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)
- [Nightscout API Backlog](../../docs/sdqctl-proposals/backlogs/nightscout-api.md)
