'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { redactPath, stableJSON, summarise, Lab } = require('./lab');
test('redacts exchange credentials and every query value, retaining endpoint and keys', () => {
  const original = '/api/v2/authorization/request/synthetic-token?secret=synthetic-secret&count=10';
  const safe = redactPath(original);
  assert.equal(safe, '/api/v2/authorization/request/[redacted]?secret=…&count=…');
  assert.ok(!safe.includes('synthetic-token'));
  assert.ok(!safe.includes('synthetic-secret'));
});
test('nested values survive canonicalization and shape-preserving corruption differs', () => {
  const a = { device: 'synthetic', nested: { iob: 0.5, deep: [{ sgv: 118 }] } };
  const reordered = { nested: { deep: [{ sgv: 118 }], iob: 0.5 }, device: 'synthetic' };
  assert.equal(stableJSON(a), stableJSON(reordered));
  const broken = structuredClone(a);
  broken.nested.deep[0].sgv = 119;
  assert.notEqual(stableJSON(a), stableJSON(broken));
  broken.nested.deep[0].sgv = 118;
  assert.equal(stableJSON(a), stableJSON(broken));
});

test('BSON Date values remain visible to the stored-value oracle', () => {
  const a = { at: new Date('2026-11-06T00:00:00Z') };
  assert.equal(stableJSON(a), '{\"at\":\"2026-11-06T00:00:00.000Z\"}');
  assert.notEqual(stableJSON(a), stableJSON({ at: new Date('2026-11-06T00:00:01Z') }));
});

test('records compressed client replies after decoding', () => {
  const zlib = require('node:zlib');
  const plain = Buffer.from(JSON.stringify([{ sgv: 118, _id: 'synthetic' }]));
  const expected = summarise(plain, { 'content-type': 'application/json' });
  for (const [encoding, encode] of [['gzip', zlib.gzipSync], ['deflate', zlib.deflateSync], ['br', zlib.brotliCompressSync]]) {
    assert.deepEqual(summarise(encode(plain), { 'content-type': 'application/json', 'content-encoding': encoding }), expected);
  }
});

test('redacts dynamically issued bearer tokens without a pre-known token list', () => {
  const safe = Lab.prototype.redactSecrets.call({ secretValues: () => [] }, 'Authorization: Bearer synthetic.jwt.signature /api/v2/authorization/request/synthetic-token');
  assert.ok(!safe.includes('synthetic.jwt.signature'));
  assert.ok(!safe.includes('synthetic-token'));
});
