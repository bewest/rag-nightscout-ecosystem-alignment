'use strict';
/*
 * upload-body-limits.js  — BF-241 .. BF-245, request-body size policy
 *
 *   node tools/queue/gates/upload-body-limits.js --bf <241|242|243|244|245> [--ref <ref>]
 *
 * Reads one ref of cgm-remote-monitor with `git show` (default official/dev)
 * and checks the source shape of one backfix. Exit 0 when the property holds.
 * Static: it reads code, it does not serve requests. The behaviour each check
 * stands for was reproduced over HTTP by tests/api.body-limits.test.js on the
 * fix branch claude/upload-body-limit-20261121 (BF-241) and by the same test's
 * wider form on dev 79144cbd0 (BF-242, BF-243), 2026-11-21.
 *
 *   241  entries, treatments and device status take their JSON limit from
 *        lib/middleware/body-limits.js (UPLOAD_BODY_LIMIT, default 50mb);
 *        device status no longer uses the 1 MB shared jsonParser.
 *   242  lib/api/notifications-api.js registers no parser with app.use: one
 *        there caps every v1 router mounted after it (activity, food) at 100kb.
 *   243  lib/server/app.js registers no app-wide express.json: the CSP report
 *        parser caps every API upload at 100kb when SECURE_CSP=true.
 *   244  API v3's parser error handler keeps a 4xx status (413, 400) instead of
 *        answering 500 for every parser error.
 *   245  profile and food take their JSON limit from body-limits, like 241.
 *
 * Reads only.
 */

const { show, report } = require('./_gate');

const arg = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined;
const BF = arg('--bf');
const REF = arg('--ref') || 'official/dev';
const findings = [];
const check = (ok, text) => findings.push({ ok: !!ok, text: `${REF}: ${text}` });

function source (file) {
  try { return show(REF, file); } catch (e) { return null; }
}

const USES_LIMITS = /bodyParser\.json\(\{\s*limit:\s*require\('\.\.\/\.\.\/middleware\/body-limits'\)\(env\)\.upload\s*\}\)/;

function routesUseLimits (routes) {
  const limits = source('lib/middleware/body-limits.js');
  check(limits && /DEFAULT_UPLOAD = 50 \* 1024 \* 1024/.test(limits) && /UPLOAD_BODY_LIMIT/.test(limits),
    'lib/middleware/body-limits.js exists, reads UPLOAD_BODY_LIMIT, default 50mb');
  for (const route of routes) {
    const file = `lib/api/${route}/index.js`;
    const text = source(file) || '';
    check(USES_LIMITS.test(text), `${file} JSON parser limit comes from body-limits`);
    check(!/api\.use\(wares\.jsonParser\)/.test(text), `${file} does not use the 1 MB shared jsonParser`);
  }
}

switch (BF) {
  case '241':
    routesUseLimits(['entries', 'treatments', 'devicestatus']);
    break;
  case '245':
    routesUseLimits(['profile', 'food']);
    break;
  case '242': {
    const text = source('lib/api/notifications-api.js') || '';
    check(text.length > 0, 'lib/api/notifications-api.js read');
    check(!/app\.use\(\s*(express|bodyParser)\.(json|urlencoded)\(/.test(text),
      'notifications-api.js registers no parser on the shared v1 app');
    break;
  }
  case '243': {
    const text = source('lib/server/app.js') || '';
    check(text.length > 0, 'lib/server/app.js read');
    check(!/app\.use\(\s*(express|bodyParser)\.json\(/.test(text), 'app.js registers no app-wide JSON parser');
    break;
  }
  case '244': {
    const text = source('lib/api3/index.js') || '';
    const handler = /express\.json\([\s\S]*?\),\s*function errorHandler[\s\S]*?\n {4}\}\);/.exec(text);
    check(handler, 'lib/api3/index.js parser error handler found');
    check(handler && /err\.status|err\.statusCode|err\.type/.test(handler[0]),
      'API v3 parser error handler reads the parser\'s status instead of always answering 500');
    break;
  }
  default:
    console.error('usage: upload-body-limits.js --bf <241|242|243|244|245> [--ref <ref>]');
    process.exit(2);
}

report(`upload-body-limits BF-${BF}`, findings);
