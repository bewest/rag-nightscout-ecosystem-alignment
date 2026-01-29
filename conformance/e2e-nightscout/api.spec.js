/**
 * API Smoke Tests for cgm-remote-monitor
 * 
 * Tests basic API functionality to ensure server is responding correctly.
 * These tests complement the existing Mocha API tests with browser-based
 * request context.
 * 
 * @see https://playwright.dev/docs/api/class-apirequestcontext
 */

import { test, expect } from '@playwright/test';

const API_SECRET_HASH = 'testapisecrethash';

test.describe('API v1', () => {

  test('GET /api/v1/status returns server info', async ({ request }) => {
    const response = await request.get('/api/v1/status.json');
    
    expect(response.ok()).toBeTruthy();
    expect(response.status()).toBe(200);
    
    const data = await response.json();
    expect(data).toHaveProperty('status');
    expect(data).toHaveProperty('version');
    expect(data).toHaveProperty('name');
  });

  test('GET /api/v1/entries returns array', async ({ request }) => {
    const response = await request.get('/api/v1/entries.json');
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('POST /api/v1/entries requires authentication', async ({ request }) => {
    const response = await request.post('/api/v1/entries', {
      data: [{
        type: 'sgv',
        sgv: 100,
        date: Date.now(),
        dateString: new Date().toISOString(),
      }],
    });
    
    // Should fail without API secret
    expect(response.status()).toBe(401);
  });

  test('POST /api/v1/entries succeeds with API secret', async ({ request }) => {
    const response = await request.post('/api/v1/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
        'Content-Type': 'application/json',
      },
      data: [{
        type: 'sgv',
        sgv: 100,
        direction: 'Flat',
        date: Date.now(),
        dateString: new Date().toISOString(),
      }],
    });
    
    expect(response.ok()).toBeTruthy();
  });

  test('GET /api/v1/treatments returns array', async ({ request }) => {
    const response = await request.get('/api/v1/treatments.json');
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('GET /api/v1/devicestatus returns array', async ({ request }) => {
    const response = await request.get('/api/v1/devicestatus.json');
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

});

test.describe('API v3', () => {

  test('GET /api/v3/version returns API version', async ({ request }) => {
    const response = await request.get('/api/v3/version');
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('version');
    expect(data).toHaveProperty('apiVersion');
  });

  test('GET /api/v3/entries returns documents', async ({ request }) => {
    const response = await request.get('/api/v3/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
      },
    });
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('result');
  });

  test('GET /api/v3/treatments returns documents', async ({ request }) => {
    const response = await request.get('/api/v3/treatments', {
      headers: {
        'api-secret': API_SECRET_HASH,
      },
    });
    
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('result');
  });

});

test.describe('API - Error Handling', () => {

  test('invalid endpoint returns 404', async ({ request }) => {
    const response = await request.get('/api/v1/nonexistent');
    expect(response.status()).toBe(404);
  });

  test('malformed JSON returns error', async ({ request }) => {
    const response = await request.post('/api/v1/entries', {
      headers: {
        'api-secret': API_SECRET_HASH,
        'Content-Type': 'application/json',
      },
      data: 'not valid json',
    });
    
    // Should return 400 or similar
    expect(response.ok()).toBeFalsy();
  });

});
