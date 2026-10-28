'use strict';
// Minimal JWTs (HS256 for per-tenant owner tokens, EdDSA for the identity
// provider's assertions) and AES-256-GCM for secrets at rest. Lab-grade:
// no key rotation, no kid handling, no clock skew.
const crypto = require('crypto');

const b64u = (b) => Buffer.from(b).toString('base64url');
const unb64u = (s) => Buffer.from(s, 'base64url');

function encodeParts (header, payload) {
  return b64u(JSON.stringify(header)) + '.' + b64u(JSON.stringify(payload));
}

function decode (token) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) return null;
  try {
    return { header: JSON.parse(unb64u(parts[0])), payload: JSON.parse(unb64u(parts[1])), parts };
  } catch (e) { return null; }
}

function signHS256 (payload, key) {
  const head = encodeParts({ alg: 'HS256', typ: 'JWT' }, payload);
  return head + '.' + b64u(crypto.createHmac('sha256', key).update(head).digest());
}

function verifyHS256 (token, key) {
  const d = decode(token);
  if (!d || d.header.alg !== 'HS256') return { ok: false, reason: 'malformed' };
  const expect = crypto.createHmac('sha256', key).update(d.parts[0] + '.' + d.parts[1]).digest();
  const got = unb64u(d.parts[2]);
  if (got.length !== expect.length || !crypto.timingSafeEqual(got, expect)) return { ok: false, reason: 'signature' };
  return { ok: true, payload: d.payload };
}

// Replace the payload, keep the original signature: the forged-claim attack.
function forgeClaim (token, patch) {
  const d = decode(token);
  const payload = Object.assign({}, d.payload, patch);
  return encodeParts(d.header, payload) + '.' + d.parts[2];
}

function signEd (payload, privatePem) {
  const head = encodeParts({ alg: 'EdDSA', typ: 'JWT' }, payload);
  return head + '.' + b64u(crypto.sign(null, Buffer.from(head), privatePem));
}

function verifyEd (token, publicPem) {
  const d = decode(token);
  if (!d || d.header.alg !== 'EdDSA') return { ok: false, reason: 'malformed' };
  const ok = crypto.verify(null, Buffer.from(d.parts[0] + '.' + d.parts[1]), publicPem, unb64u(d.parts[2]));
  return ok ? { ok: true, payload: d.payload } : { ok: false, reason: 'signature' };
}

function encrypt (kek, plaintext) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', kek, iv);
  const ct = Buffer.concat([c.update(plaintext, 'utf8'), c.final()]);
  return { iv: b64u(iv), ct: b64u(ct), tag: b64u(c.getAuthTag()), key_ref: 'lab-kek-1' };
}

function decrypt (kek, rec) {
  const d = crypto.createDecipheriv('aes-256-gcm', kek, unb64u(rec.iv));
  d.setAuthTag(unb64u(rec.tag));
  return Buffer.concat([d.update(unb64u(rec.ct)), d.final()]).toString('utf8');
}

const random = (n) => crypto.randomBytes(n || 32).toString('base64url');
const now = () => Math.floor(Date.now() / 1000);

module.exports = { decode, signHS256, verifyHS256, forgeClaim, signEd, verifyEd, encrypt, decrypt, random, now };
