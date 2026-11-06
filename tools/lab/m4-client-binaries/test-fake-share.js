'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { fixtureSeries, selectReadings } = require('./clients/fake-share');
const base = Date.parse('2026-11-06T12:00:00Z');
test('later polls preserve every overlapping timestamp and value', () => {
  const series = fixtureSeries(base);
  const snapshot = JSON.stringify(series);
  const first = selectReadings(series, base, 2880, 576);
  const later = selectReadings(series, base + 5 * 60000, 2880, 576);
  assert.equal(first.length, 240);
  assert.deepEqual(later, first);
  assert.equal(selectReadings(series, base + 5 * 60000, 1440, 576).length, 240);
  assert.equal(JSON.stringify(series), snapshot);
  const broken = structuredClone(later); broken[0].Value += 1;
  assert.notDeepEqual(broken, first);
  broken[0].Value -= 1; assert.deepEqual(broken, first);
});
test('range and maxCount select a bounded subset without inventing new samples', () => {
  const series = fixtureSeries(base);
  const selected = selectReadings(series, base, 15, 2);
  assert.equal(selected.length, 2);
  assert.deepEqual(selected.map(r => r.Value), series.slice(-2).reverse().map(r => r.sgv));
  assert.deepEqual(selectReadings(series, base, 1, 576), []);
  assert.deepEqual(selectReadings(series, base, 2880, 0), []);
});
