/**
 * Playwright Configuration for cgm-remote-monitor E2E Tests
 * 
 * This configuration file should be copied to the cgm-remote-monitor root
 * when submitting a PR to add Playwright support.
 * 
 * Usage:
 *   npx playwright test
 *   npx playwright test --project=chromium
 *   npx playwright show-report
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  // Test directory
  testDir: './tests/e2e',
  
  // Test timeout (30 seconds per test)
  timeout: 30000,
  
  // Expect timeout (5 seconds for assertions)
  expect: {
    timeout: 5000,
  },
  
  // Fail fast in CI
  forbidOnly: !!process.env.CI,
  
  // Retry on CI
  retries: process.env.CI ? 2 : 0,
  
  // Parallel workers
  workers: process.env.CI ? 2 : undefined,
  
  // Reporter
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  
  // Shared settings for all projects
  use: {
    // Base URL for navigation
    baseURL: process.env.NIGHTSCOUT_URL || 'http://localhost:1337',
    
    // Collect trace on first retry
    trace: 'on-first-retry',
    
    // Screenshot on failure
    screenshot: 'only-on-failure',
    
    // Video on failure (useful for debugging)
    video: 'on-first-retry',
    
    // API request context for seeding data
    extraHTTPHeaders: {
      'api-secret': process.env.API_SECRET || 'testapisecrethash',
    },
  },
  
  // Browser projects
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile viewports
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  
  // Local dev server configuration
  webServer: {
    command: 'npm start',
    port: 1337,
    reuseExistingServer: !process.env.CI,
    env: {
      MONGODB_URI: process.env.MONGODB_URI || 'mongodb://localhost:27017/nightscout_test',
      API_SECRET: process.env.API_SECRET || 'testapisecrethash',
      DISPLAY_UNITS: 'mg/dl',
      ENABLE: 'careportal iob cob bwp cage sage iage bage',
      AUTH_DEFAULT_ROLES: 'readable',
      INSECURE_USE_HTTP: 'true',
    },
  },
});
