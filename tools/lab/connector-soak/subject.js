#!/usr/bin/env node
'use strict';
/*
 * subject.js - on a source Nightscout, create (or find) an authorization
 * subject with the given roles, and write its access token to a file.
 * The token is never printed.
 *
 *   node subject.js <sourceURL> <secretFile> <subjectName> <roles,comma> <tokenOutFile>
 * roles may be the literal "none" to create a subject with no roles.
 * Also: node subject.js <sourceURL> <secretFile> --list
 *   prints name, roles and whether a token exists (never the token).
 */
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');

const [url, secretFile, name, roles, out] = process.argv.slice(2);
const hash = crypto.createHash('sha1').update(fs.readFileSync(secretFile, 'utf8').trim()).digest('hex');

function call (method, path, body) {
  const u = new URL(path, url);
  const data = body ? Buffer.from(JSON.stringify(body)) : null;
  return new Promise((resolve, reject) => {
    const r = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method,
      headers: { 'api-secret': hash, 'content-type': 'application/json', ...(data ? { 'content-length': data.length } : {}) } }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => res.statusCode === 200 ? resolve(buf ? JSON.parse(buf) : null) : reject(new Error(method + ' ' + u.pathname + ' HTTP ' + res.statusCode)));
    });
    r.on('error', reject);
    r.end(data || undefined);
  });
}

(async () => {
  let list = await call('GET', '/api/v2/authorization/subjects');
  if (name === '--list') {
    list.forEach((s) => console.log(JSON.stringify({ name: s.name, roles: s.roles, role: s.role, hasToken: Boolean(s.accessToken) })));
    return;
  }
  let match = list.find((s) => s.name === name);
  if (!match) {
    await call('POST', '/api/v2/authorization/subjects', { name, roles: roles === 'none' ? [] : roles.split(','), notes: 'cksoak lab subject' });
    list = await call('GET', '/api/v2/authorization/subjects');
    match = list.find((s) => s.name === name);
  }
  if (!match || !match.accessToken) throw new Error('subject has no access token');
  fs.writeFileSync(out, match.accessToken, { mode: 0o600 });
  console.log(JSON.stringify({ name: match.name, roles: match.roles }));
})().catch((err) => { console.error(err.message); process.exit(1); });
