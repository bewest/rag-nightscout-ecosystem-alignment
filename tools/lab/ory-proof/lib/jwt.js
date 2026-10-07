'use strict';
// Minimal HS256 JWT, node:crypto only. The lab's per-tenant Nightscout token (D14).
const crypto = require('crypto');
const b64u = (b) => Buffer.from(b).toString('base64url');

function sign (payload, key) {
  const head = b64u(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = b64u(JSON.stringify(payload));
  const sig = crypto.createHmac('sha256', key).update(`${head}.${body}`).digest('base64url');
  return `${head}.${body}.${sig}`;
}

// Returns {ok:true, payload} or {ok:false, reason:'malformed'|'signature'|'expired'}
function verify (token, key, now = Math.floor(Date.now() / 1000)) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) return { ok: false, reason: 'malformed' };
  const expect = crypto.createHmac('sha256', key).update(`${parts[0]}.${parts[1]}`).digest();
  const got = Buffer.from(parts[2], 'base64url');
  if (got.length !== expect.length || !crypto.timingSafeEqual(got, expect)) return { ok: false, reason: 'signature' };
  let payload;
  try { payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString()); } catch (e) { return { ok: false, reason: 'malformed' }; }
  if (typeof payload.exp === 'number' && payload.exp < now) return { ok: false, reason: 'expired' };
  return { ok: true, payload };
}

function decode (token) {
  try { return JSON.parse(Buffer.from(String(token).split('.')[1], 'base64url').toString()); } catch (e) { return null; }
}

module.exports = { sign, verify, decode };
