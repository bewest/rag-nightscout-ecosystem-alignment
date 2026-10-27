'use strict';
// Boot one crm tree's API v1 in-process against a given database and answer a
// list of GET requests; write {request: {status, type, body}} as JSON.
// Usage: node tools/seam/v1-http-differential-child.js <tree> <mongo uri with db> <requests.json> <out.json>
const path = require('path');
const fs = require('fs');
const [tree, uri, reqFile, outFile] = process.argv.slice(2);
const SECRET = 'httpdiff-secret-' + 'x'.repeat(12);
process.env.API_SECRET = SECRET;
process.env.MONGODB_URI = uri;
process.env.ENABLE = 'careportal api food';
process.env.INSECURE_USE_HTTP = 'true';
process.env.DISPLAY_UNITS = 'mg/dl';
process.env.AUTH_DEFAULT_ROLES = 'denied';
const R = p => require(path.join(tree, p));
const request = R('node_modules/supertest');
const hash = require('crypto').createHash('sha1').update(SECRET).digest('hex');

const env = R('lib/server/env')();
const language = R('lib/language')();
const app = R('node_modules/express')();
app.enable('api');
R('lib/server/bootevent')(env, language).boot(async function booted (ctx) {
  ctx.ddata = R('lib/data/ddata')();
  app.use('/api/v1', R('lib/api/')(env, ctx));
  const reqs = JSON.parse(fs.readFileSync(reqFile, 'utf8'));
  const out = {};
  for (const url of reqs) {
    try {
      const r = await request(app).get(url).set('api-secret', hash).timeout(15000);
      out[url] = { status: r.status, type: (r.headers['content-type'] || '').split(';')[0], body: r.body, text: r.body && Object.keys(r.body).length ? undefined : r.text };
    } catch (e) {
      out[url] = { error: String(e.message || e) };
    }
  }
  fs.writeFileSync(outFile, JSON.stringify(out));
  process.exit(0);
});
