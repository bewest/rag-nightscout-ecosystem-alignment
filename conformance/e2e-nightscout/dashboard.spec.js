/**
 * Dashboard E2E Tests for cgm-remote-monitor
 * 
 * Tests the main Nightscout dashboard functionality including:
 * - Page load and basic rendering
 * - Current glucose display
 * - Direction arrows
 * - Real-time Socket.IO updates
 * 
 * @see https://playwright.dev/docs/api/class-test
 */

import { test, expect } from '@playwright/test';

// Test data constants
const TEST_SGV = 120;
const TEST_SGV_UPDATED = 150;
const API_SECRET_HASH = 'testapisecrethash';

test.describe('Dashboard', () => {
  
  test.beforeEach(async ({ request }) => {
    // Seed test data via API before each test
    const response = await request.post('/api/v1/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
        'Content-Type': 'application/json',
      },
      data: [{
        type: 'sgv',
        sgv: TEST_SGV,
        direction: 'Flat',
        date: Date.now(),
        dateString: new Date().toISOString(),
      }],
    });
    expect(response.ok()).toBeTruthy();
  });

  test('page loads successfully', async ({ page }) => {
    await page.goto('/');
    
    // Verify page title contains Nightscout
    await expect(page).toHaveTitle(/Nightscout/i);
    
    // Verify main container is visible
    await expect(page.locator('#container')).toBeVisible();
  });

  test('displays current glucose value', async ({ page }) => {
    await page.goto('/');
    
    // Wait for data to load (Socket.IO connection)
    await page.waitForSelector('.bgValue, #currentBG', { timeout: 10000 });
    
    // Verify glucose value is displayed
    const bgElement = page.locator('.bgValue, #currentBG').first();
    await expect(bgElement).toBeVisible();
    
    // Value should be numeric
    const text = await bgElement.textContent();
    expect(text).toMatch(/\d+/);
  });

  test('shows direction arrow', async ({ page }) => {
    await page.goto('/');
    
    // Wait for direction indicator
    await page.waitForSelector('.direction, .trend-arrow', { timeout: 10000 });
    
    // Verify direction element exists
    const directionElement = page.locator('.direction, .trend-arrow').first();
    await expect(directionElement).toBeVisible();
  });

  test('displays time since last reading', async ({ page }) => {
    await page.goto('/');
    
    // Wait for time display
    await page.waitForSelector('.timeAgo, #staleTime', { timeout: 10000 });
    
    // Verify time element is visible
    const timeElement = page.locator('.timeAgo, #staleTime').first();
    await expect(timeElement).toBeVisible();
  });

  test('header plugins render', async ({ page }) => {
    await page.goto('/');
    
    // Wait for page load
    await page.waitForLoadState('networkidle');
    
    // Check for common plugin elements (IOB, COB, etc.)
    // These depend on ENABLE configuration
    const pluginContainer = page.locator('#pluginPreview, .plugin-container');
    
    // At minimum, the container should exist
    await expect(pluginContainer.first()).toBeVisible({ timeout: 10000 });
  });

  test('mobile view renders correctly', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    
    await page.goto('/');
    
    // Verify page loads in mobile view
    await expect(page.locator('#container, body')).toBeVisible();
    
    // BG value should still be visible on mobile
    await page.waitForSelector('.bgValue, #currentBG', { timeout: 10000 });
    const bgElement = page.locator('.bgValue, #currentBG').first();
    await expect(bgElement).toBeVisible();
  });

});

test.describe('Dashboard - Real-time Updates', () => {
  
  test('updates glucose value via Socket.IO', async ({ page, request }) => {
    // Seed initial data
    await request.post('/api/v1/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
        'Content-Type': 'application/json',
      },
      data: [{
        type: 'sgv',
        sgv: TEST_SGV,
        direction: 'Flat',
        date: Date.now() - 60000,
        dateString: new Date(Date.now() - 60000).toISOString(),
      }],
    });
    
    await page.goto('/');
    
    // Wait for initial load
    await page.waitForSelector('.bgValue, #currentBG', { timeout: 10000 });
    
    // Post new value
    await request.post('/api/v1/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
        'Content-Type': 'application/json',
      },
      data: [{
        type: 'sgv',
        sgv: TEST_SGV_UPDATED,
        direction: 'FortyFiveUp',
        date: Date.now(),
        dateString: new Date().toISOString(),
      }],
    });
    
    // Wait for Socket.IO to push update (may take a few seconds)
    const bgElement = page.locator('.bgValue, #currentBG').first();
    await expect(bgElement).toContainText(TEST_SGV_UPDATED.toString(), { timeout: 15000 });
  });

});

test.describe('Dashboard - Error States', () => {
  
  test('handles no data gracefully', async ({ page }) => {
    // Navigate without seeding data
    await page.goto('/');
    
    // Page should still load
    await expect(page.locator('#container, body')).toBeVisible();
    
    // Should not crash - wait for timeout
    await page.waitForTimeout(2000);
    
    // Page should remain responsive
    await expect(page).toHaveTitle(/Nightscout/i);
  });

});
