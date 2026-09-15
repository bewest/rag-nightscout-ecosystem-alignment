// Adversarial verification of tenant RESOLUTION -- the half of isolation that
// runs BEFORE the database.
//
// WHY THIS AND NOT RLS. tests/postgres-entries-rls.test.js already measures the
// database half: a NOSUPERUSER NOBYPASSRLS role, transaction-scoped binding, no
// binding left on a pooled connection, cross-tenant read/write refusal, index
// bounds -- each with its own non-vacuity case. RLS enforces WHATEVER TENANT ID
// IT IS HANDED, faithfully. So the interesting question is not whether the
// policy holds; it is whether an HTTP request can be made to hand it the wrong
// id. That is what this file attacks.
//
// WHAT IT ASSUMES ABOUT ITS OWN VERDICTS. A probe that passes because the
// request never reached the resolver looks exactly like one that passes because
// the resolver is correct. So every CONFIRMED-SAFE below is paired with a
// WEAKENED run: the same probe, against a deliberately damaged copy of the same
// module, which must go RED. The weakened copy is written next to the original
// (so its relative requires still resolve), required once, and deleted in a
// finally. Nothing in the checkout is left modified.
//
// Usage:
//   node tools/qc/tenant-resolution-arm.js [section] [--root <server checkout>]
//   sections: host | path | credential | failclosed | mount | admin | all

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const net = require('node:net');

const argv = process.argv.slice(2);
function flag (name, fallback) {
  const i = argv.indexOf('--' + name);
  return i === -1 ? fallback : argv[i + 1];
}
const SECTION = argv.find(a => !a.startsWith('--') && argv[argv.indexOf(a) - 1] !== '--root') || 'all';
const ROOT = path.resolve(flag('root',
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-tenant'));

if (!fs.existsSync(path.join(ROOT, 'lib', 'server', 'tenant-resolver.js'))) {
  console.error('No cgm-remote-monitor checkout at ' + ROOT + '.');
  console.error('Pass --root <checkout>. This harness must NOT be pointed at a checkout another');
  console.error('session is committing to: it writes and deletes a weakened copy of two modules.');
  process.exit(2);
}

const express = require(path.join(ROOT, 'node_modules', 'express'));
const request = require(path.join(ROOT, 'node_modules', 'supertest'));

const lib = name => require(path.join(ROOT, 'lib', name));
const tenantScope = lib('storage/tenant-scope');
const resolverModule = lib('server/tenant-resolver');
const registryModule = lib('server/tenant-registry');
const tenantMiddleware = lib('server/tenant-middleware');
const clientIP = lib('server/client-ip');

// §2.5's shapes, as README.md documents them.
const SUBDOMAIN_RULE = '^([a-z0-9-]+)\\.user-content\\.apex\\.org$';
const PATH_RULE = '^/([a-z0-9-]+)(?=/|$)';

const TENANT_FOO = '11111111-1111-4111-8111-111111111111';
const TENANT_BAR = '22222222-2222-4222-8222-222222222222';
const TENANT_OLD = '33333333-3333-4333-8333-333333333333';
const TENANTS = [
  { id: TENANT_FOO, slug: 'foo', displayName: 'Foo' }
  , { id: TENANT_BAR, slug: 'bar' }
  , { id: TENANT_OLD, slug: 'retired', isActive: false }
];

// ---------------------------------------------------------------- reporting

let failures = 0;
const results = [];

function probe (id, title) {
  const lines = [];
  const rec = { id, title, verdict: null, lines };
  results.push(rec);
  return {
    say: (...a) => { lines.push('    ' + a.join(' ')); },
    verdict: v => { rec.verdict = v; if (v === 'DEFECT') failures++; },
    nonvacuity: t => { rec.nonvacuity = t; }
  };
}

function report () {
  console.log('\n================ VERDICTS ================');
  for (const r of results) {
    console.log(`${r.id}  ${r.verdict || 'NO VERDICT'}  -- ${r.title}`);
    for (const l of r.lines) console.log(l);
    console.log('    non-vacuity: ' + (r.nonvacuity || 'NONE -- label this "no non-vacuity evidence"'));
  }
  console.log('==========================================');
}

// ------------------------------------------------- deliberate weakening

/**
 * Require a copy of `relPath` with `edits` applied, from a sibling file so that
 * its own relative requires still resolve. The copy is always deleted.
 *
 * This is how a CONFIRMED-SAFE earns the label: the probe has to go RED here.
 */
function withWeakened (relPath, edits, fn) {
  const src = path.join(ROOT, 'lib', relPath);
  const original = fs.readFileSync(src, 'utf8');
  let patched = original;
  for (const [ from, to ] of edits) {
    if (!patched.includes(from)) {
      throw new Error(`weakening ${relPath}: anchor not found -- ${JSON.stringify(from.slice(0, 60))}. `
        + 'The module changed under this harness; do not adapt the anchor until you have read why.');
    }
    patched = patched.split(from).join(to);
  }
  const copy = src.replace(/\.js$/, '.__weakened' + process.pid + '.js');
  fs.writeFileSync(copy, patched);
  try {
    return fn(require(copy));
  } finally {
    delete require.cache[require.resolve(copy)];
    fs.unlinkSync(copy);
  }
}

// ------------------------------------------------------------- app builders

/**
 * lib/server/app.js's own top-of-stack, reproduced in order, with a terminal
 * route that records whether storage was reached and under which binding.
 */
function buildApp (settings) {
  const s = settings || { };
  const storageCalls = [];
  const app = express();
  lib('middleware/configure-request')(app);
  app.set('trust proxy', clientIP.compileTrust(s.trustProxy || ''));

  const middleware = (s.middleware || tenantMiddleware.create)({
    resolver: (s.resolverModule || resolverModule).createResolver({
      hostPattern: s.hostPattern, pathPattern: s.pathPattern
    })
    , registry: s.registry || registryModule.fromList(TENANTS)
    , enclave: s.enclave
    , requireTokenClaim: s.requireTokenClaim
    , hostHeader: s.hostHeader
  });
  app.use(middleware);

  if (s.httpsRedirect) {
    // lib/server/app.js:132, verbatim in shape. INSECURE_USE_HTTP defaults
    // false, so this layer is ON by default.
    app.use((req, res, next) => {
      if (req.secure) next();
      else res.redirect(307, `https://${req.header('host')}${req.url}`);
    });
  }
  if (s.bodyParser) app.use(express.json());

  function terminal (req, res) {
    let bound;
    try {
      // What every converted storage call site does first.
      bound = String(tenantScope.requireTenant('probe'));
      storageCalls.push(bound);
    } catch (err) {
      bound = 'THREW: ' + err.message.split('.')[0];
    }
    res.json({ bound, tenant: req.tenant, url: req.url, prefix: req.tenantPathPrefix
      , body: req.body, seen: tenantMiddleware.presentedCredential(req) });
  }

  app.all('/api/v1/entries', terminal);
  app.all('/api/v1/{*rest}', terminal);
  app.all('/', terminal);
  app.use((req, res) => res.status(404).json({ route: 'none', url: req.url }));
  return { app, storageCalls };
}

/**
 * GET each [url, host] against `app` by writing the request line onto a raw
 * socket, so the bytes on the wire are the bytes asked for.
 *
 * An HTTP CLIENT normalises. superagent (supertest) builds a WHATWG URL, which
 * collapses `.` and `..` segments and decodes `%2e` before sending -- so a
 * dot-segment probe written with supertest measures the client library. This
 * one cannot: it never parses the URL.
 */
function rawGet (app, cases) {
  const CRLF = String.fromCharCode(13, 10);
  return new Promise((resolve, reject) => {
    const srv = app.listen(0, '127.0.0.1', async () => {
      const port = srv.address().port;
      const out = [ ];
      for (const [ url, host ] of cases) {
        out.push(await new Promise(r => {
          const s = net.connect(port, '127.0.0.1', () => s.write(
            [ 'GET ' + url + ' HTTP/1.1', 'Host: ' + host, 'Connection: close' ]
              .join(CRLF) + CRLF + CRLF));
          let buf = '';
          s.on('data', d => { buf += d; });
          s.on('close', () => {
            const status = Number((buf.split(CRLF)[0] || '').split(' ')[1]) || 0;
            let body = { };
            try { body = JSON.parse(buf.split(CRLF + CRLF).slice(-1)[0]); } catch { /* not json */ }
            r({ url, status, body });
          });
          s.on('error', e => r({ url, status: 'ERR', body: { error: e.code } }));
          setTimeout(() => s.destroy(), 2000);
        }));
      }
      srv.close();
      resolve(out);
    });
    srv.on('error', reject);
  });
}

function inMulti (fn) {
  const prev = tenantScope.getTenancyMode();
  tenantScope.setTenancyMode('multi');
  return Promise.resolve().then(fn).finally(() => tenantScope.setTenancyMode(prev));
}

// ============================================================== SECTION host

async function sectionHost () {

  // -------------------------------------------------------------------- H1
  {
    const p = probe('H1', 'Unicode case folding in normalizeHost cannot mint an ASCII slug '
      + 'from a non-ASCII host over HTTP');

    // Which code points fold INTO the slug charset at all?
    const SLUG = /^[a-z0-9-]+$/;
    const folders = [];
    for (let cp = 0x80; cp <= 0x10FFFF; cp++) {
      if (cp >= 0xD800 && cp <= 0xDFFF) continue;
      const ch = String.fromCodePoint(cp);
      const lo = ch.toLowerCase();
      if (lo !== ch && SLUG.test(lo)) folders.push({ cp, ch, lo });
    }
    p.say('code points whose toLowerCase() lands inside ^[a-z0-9-]+$:', folders.length,
      folders.map(f => 'U+' + f.cp.toString(16).toUpperCase() + ' -> ' + JSON.stringify(f.lo)).join(', '));

    // At the MODULE boundary the collision is real.
    const r = resolverModule.createResolver({ hostPattern: SUBDOMAIN_RULE });
    const ascii = r.resolve('kfoo.user-content.apex.org', '/');
    const kelvin = r.resolve('Kfoo.user-content.apex.org', '/');
    p.say('module-level: "kfoo..." ->', ascii && ascii.slug, '| "\\u212Afoo..." ->', kelvin && kelvin.slug,
      '| collide:', Boolean(kelvin && ascii && kelvin.slug === ascii.slug));

    // Over a socket, Node decodes header bytes as latin1, so U+212A never
    // arrives as U+212A -- it arrives as three latin1 characters.
    const wire = await overTheWire([
      [ 'kelvin-utf8', 'foo' + Buffer.from('K', 'utf8').toString('latin1') + '.user-content.apex.org' ]
      , [ 'latin1-high', 'foÖ.user-content.apex.org' ]
    ]);
    let anyWireSlug = false;
    for (const w of wire) {
      const res = r.resolve(w.host, '/');
      p.say('wire:', w.name, '| status', w.status, '| header codes', w.codes,
        '| resolver slug:', res ? res.slug : 'NO MATCH');
      if (res) anyWireSlug = true;
    }

    if (!anyWireSlug && folders.length === 1) {
      p.verdict('CONFIRMED-SAFE');
      p.say('The single folding code point (U+212A KELVIN SIGN) is unreachable over HTTP because');
      p.say('Node decodes header octets as latin1; no latin1 character folds into the slug charset.');
      p.say('Residual: normalizeHost() is exported, and a non-HTTP caller CAN feed it U+212A.');
    } else {
      p.verdict('DEFECT');
    }

    // NON-VACUITY: loosen the charset the way an "IDN support" patch would.
    const red = withWeakened('server/tenant-resolver.js',
      [[ 'const SLUG_CHARS_RE = /^[a-z0-9-]+$/;', 'const SLUG_CHARS_RE = /^[a-z0-9\\u0080-\\u024f-]+$/;' ]],
      weak => {
        const wr = weak.createResolver({ hostPattern: '^([a-z0-9\\u0080-\\u024f-]+)\\.user-content\\.apex\\.org$' });
        return wr.resolve(wire.find(w => w.name === 'latin1-high').host, '/');
      });
    p.nonvacuity('SLUG_CHARS_RE loosened to accept Latin-1 Supplement: the same over-the-wire host '
      + 'now yields slug ' + JSON.stringify(red && red.slug) + ' (was NO MATCH). The probe reads the '
      + 'charset gate, not something upstream of it.');
  }

  // -------------------------------------------------------------------- H2
  {
    const p = probe('H2', 'Duplicate, absent, empty and malformed Host headers all fail CLOSED');

    const wire = await overTheWire([
      [ 'dup-host', null, [ 'Host: foo.user-content.apex.org', 'Host: bar.user-content.apex.org' ] ]
      , [ 'no-host-http10', null, [ ], 'GET / HTTP/1.0' ]
      , [ 'empty-host', '' ]
      , [ 'whitespace-host', '   ' ]
      , [ 'port-only', ':8080' ]
      , [ 'nul-host', 'foo' + String.fromCharCode(0) + '.user-content.apex.org' ]
      , [ 'overlong', 'a'.repeat(300) + '.user-content.apex.org' ]
      , [ 'bracketed', '[foo.user-content.apex.org]' ]
      , [ 'trailing-dot-port', 'foo.user-content.apex.org.:8443' ]
    ]);

    const r = resolverModule.createResolver({ hostPattern: SUBDOMAIN_RULE });
    for (const w of wire) {
      const res = w.status === 400 ? null : r.resolve(w.host, '/');
      p.say(w.name.padEnd(18), 'node status', String(w.status).padEnd(4),
        'header', JSON.stringify(w.host), '-> slug', res ? res.slug : 'NO MATCH');
    }

    // Now the whole middleware, end to end, for the two that DO produce a header.
    const { app, storageCalls } = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false });
    await inMulti(async () => {
      const dup = await request(app).get('/api/v1/entries').set('Host', 'foo.user-content.apex.org');
      p.say('control (single valid Host):', dup.status, JSON.stringify(dup.body.bound));
      const none = await request(app).get('/api/v1/entries').set('Host', ':8080');
      p.say('port-only Host end to end:', none.status, JSON.stringify(none.body));
    });
    p.say('storage reached on:', JSON.stringify(storageCalls), '(the control only)');

    const dupHostPicked = wire.find(w => w.name === 'dup-host').host;
    if (dupHostPicked === 'foo.user-content.apex.org' && storageCalls.length === 1) {
      p.verdict('CONFIRMED-SAFE');
      p.say('Node keeps the FIRST Host and discards later ones (host is in its discard-duplicate');
      p.say('set), so there is no ", "-joined value for a pattern to mis-read. NUL is rejected by');
      p.say('the parser with 400. Empty/whitespace/port-only all normalise to null -> 404.');
    } else p.verdict('DEFECT');

    // NON-VACUITY: remove the refusal and fall through to the first tenant.
    const redApp = withWeakened('server/tenant-middleware.js', [[
      `    if (!resolved) {
      refuse(res, 404, 'No Nightscout tenant is served at this address.');
      return;
    }`,
      `    const effective = resolved || { slug: 'foo', source: 'host', consumed: '' };`
    ], [ 'registry.lookup(resolved.slug)', 'registry.lookup(effective.slug)' ]
    , [ "if (resolved.source === 'path' && resolved.consumed)", "if (effective.source === 'path' && effective.consumed)" ]
    , [ 'req.tenantPathPrefix = resolved.consumed;', 'req.tenantPathPrefix = effective.consumed;' ]
    , [ 'req.url = req.url.slice(resolved.consumed.length)', 'req.url = req.url.slice(effective.consumed.length)' ]
    ], weak => buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, middleware: weak.create }));
    const redRes = await inMulti(() => request(redApp.app).get('/api/v1/entries').set('Host', ':8080'));
    p.nonvacuity('the `if (!resolved) refuse(404)` branch replaced by a default tenant: the same '
      + 'port-only Host now returns ' + redRes.status + ' bound to ' + JSON.stringify(redRes.body.bound)
      + ' and reaches storage. The probe measures the refusal, not an unreachable route.');
  }

  // -------------------------------------------------------------------- H3
  {
    const p = probe('H3', 'The configured forwarded host header: is the TRUST_PROXY guard reachable '
      + 'for every setting that leaves the header client-controlled?');

    function tryFromEnv (trustProxy) {
      const env = {
        tenancy: { mode: 'multi', hostPattern: SUBDOMAIN_RULE, hostHeader: 'x-forwarded-host'
          , registry: registryModule.fromList(TENANTS), requireTokenClaim: false }
        , trustProxy
        , enclave: null
      };
      const prev = tenantScope.getTenancyMode();
      try {
        const mw = tenantMiddleware.fromEnv(env);
        return { accepted: true, mw };
      } catch (err) {
        return { accepted: false, message: err.message.split('.')[0] };
      } finally {
        tenantScope.setTenancyMode(prev);
      }
    }

    const cases = [
      [ 'TRUST_PROXY unset (compatibility: trusts everyone)', undefined ]
      , [ 'TRUST_PROXY="" (same)', '' ]
      , [ 'TRUST_PROXY=false (trust NOBODY)', 'false' ]
      , [ 'TRUST_PROXY=10.0.0.0/8 (a real edge)', '10.0.0.0/8' ]
    ];
    const outcome = { };
    for (const [ name, tp ] of cases) {
      const r = tryFromEnv(tp);
      outcome[String(tp)] = r.accepted;
      p.say(name.padEnd(48), r.accepted ? 'ACCEPTED' : 'REFUSED: ' + r.message);
    }

    // And what does acceptance mean in practice? A client sets the header.
    const accepted = tryFromEnv('false');
    if (accepted.accepted) {
      const app = express();
      lib('middleware/configure-request')(app);
      app.set('trust proxy', clientIP.compileTrust('false'));
      app.use(accepted.mw);
      app.all('/api/v1/entries', (req, res) => res.json({
        bound: String(tenantScope.requireTenant('probe')), tenant: req.tenant }));
      const res = await inMulti(() => request(app).get('/api/v1/entries')
        .set('Host', 'foo.user-content.apex.org')
        .set('X-Forwarded-Host', 'bar.user-content.apex.org'));
      p.say('with TRUST_PROXY=false and TENANT_HOST_HEADER=x-forwarded-host, a client-supplied');
      p.say('X-Forwarded-Host on foo\'s own host binds:', res.status, JSON.stringify(res.body));
      if (res.body && res.body.tenant && res.body.tenant.slug === 'bar') {
        p.verdict('DEFECT');
        p.say('The client chose the tenant with a request header. TRUST_PROXY=false is the setting');
        p.say('that says NO proxy is in front, which is exactly when the header is client input --');
        p.say('yet the guard only fires on the compatibility (unset/empty) value.');
      } else p.verdict('CONFIRMED-SAFE');
    } else {
      p.verdict('CONFIRMED-SAFE');
    }

    p.nonvacuity('the same probe run against TRUST_PROXY unset is REFUSED at boot with the guard\'s '
      + 'own message, and against TRUST_PROXY=10.0.0.0/8 is accepted for a deployment that really '
      + 'does have an edge -- so the probe distinguishes the three settings rather than reporting '
      + 'one answer for all of them. Measured above.');
  }

  // -------------------------------------------------------------------- H4
  {
    const p = probe('H4', 'The host comes from req.headers[hostHeader], not req.hostname, under '
      + 'Nightscout\'s trusts-everyone default');
    const { app } = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, trustProxy: '' });
    const res = await inMulti(() => request(app).get('/api/v1/entries')
      .set('Host', 'foo.user-content.apex.org')
      .set('X-Forwarded-Host', 'bar.user-content.apex.org'));
    p.say('Host=foo, X-Forwarded-Host=bar ->', res.status, JSON.stringify(res.body.tenant));
    p.verdict(res.body.tenant && res.body.tenant.slug === 'foo' ? 'CONFIRMED-SAFE' : 'DEFECT');

    const redApp = withWeakened('server/tenant-middleware.js',
      [[ 'resolver.resolve(req.headers && req.headers[hostHeader], req.url)',
        'resolver.resolve(req.hostname, req.url)' ]],
      weak => buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, middleware: weak.create }));
    const red = await inMulti(() => request(redApp.app).get('/api/v1/entries')
      .set('Host', 'foo.user-content.apex.org')
      .set('X-Forwarded-Host', 'bar.user-content.apex.org'));
    p.nonvacuity('`req.headers[hostHeader]` swapped for `req.hostname`: the same request now binds '
      + JSON.stringify(red.body.tenant && red.body.tenant.slug) + ' instead of "foo".');
  }
}

/**
 * Send raw request lines to a bare Node http server and report what
 * req.headers.host actually became.
 */
function overTheWire (cases) {
  const CRLF = String.fromCharCode(13, 10);
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      res.end(JSON.stringify({ host: req.headers.host, url: req.url
        , codes: [ ...(req.headers.host || '') ].map(c => c.codePointAt(0).toString(16)).join(' ') }));
    });
    srv.listen(0, '127.0.0.1', async () => {
      const port = srv.address().port;
      const out = [ ];
      for (const [ name, host, extra, requestLine ] of cases) {
        out.push(await new Promise(r => {
          const lines = [ requestLine || 'GET / HTTP/1.1' ];
          if (host !== null && host !== undefined) lines.push('Host: ' + host);
          for (const e of (extra || [ ])) lines.push(e);
          const s = net.connect(port, '127.0.0.1', () => s.write(lines.join(CRLF) + CRLF + CRLF));
          let buf = '';
          s.on('data', d => { buf += d; });
          s.on('close', () => {
            const status = Number((buf.split(CRLF)[0] || '').split(' ')[1]) || 0;
            let body = { };
            try { body = JSON.parse(buf.split(CRLF + CRLF).slice(-1)[0]); } catch { /* 400 has no body */ }
            r({ name, status, host: body.host, codes: body.codes, url: body.url });
          });
          s.on('error', () => { });
          setTimeout(() => s.destroy(), 1000);
        }));
      }
      srv.close();
      resolve(out);
    });
  });
}

// ============================================================== SECTION path

async function sectionPath () {

  // -------------------------------------------------------------------- P1
  {
    const p = probe('P1', 'The path fallback\'s req.url rewrite never routes a request somewhere '
      + 'the un-prefixed URL could not reach');

    const r = resolverModule.createResolver({ pathPattern: PATH_RULE });
    const CASES = [
      '/foo/api/v1/entries'
      , '/foo/../bar/api/v1/entries'
      , '/foo/%2e%2e/bar/api/v1/entries'
      , '/foo/..%2fbar/api/v1/entries'
      , '//foo//api/v1/entries'
      , '/foo//api/v1/entries'
      , '/foo%2Fbar/api/v1/entries'
      , '/foo/./api/v1/entries'
      , '/foo/api/v1/entries/../../../../etc/passwd'
      , '/api/v1/entries'
      , '/foo/api/v1/entries?count=10&find[sgv][$gte]=100'
      , '/FOO/api/v1/entries'
      , '/foo'
      , '/foo/'
    ];

    // SUPERTEST CANNOT BE USED FOR THIS PROBE, and that is a finding in itself.
    // superagent builds a WHATWG URL, which collapses `..`/`.` and decodes
    // `%2e` BEFORE the bytes leave the client: `request(app).get('/foo/../bar/x')`
    // arrives at the server as `/bar/x`. A dot-segment probe written with
    // supertest therefore measures the HTTP CLIENT, not the middleware, and it
    // reports a cross-tenant binding that no real request can produce. Every
    // case below is written onto a raw socket instead, and `rawGet` proves the
    // difference by reporting what the server actually received.
    const { app, storageCalls } = buildApp({ pathPattern: PATH_RULE, requireTokenClaim: false });
    let crossed = false;
    await inMulti(async () => {
      const shots = await rawGet(app, CASES.map(u => [ u, 'apex.org' ]));
      for (const shot of shots) {
        const resolved = r.resolve('apex.org', shot.url);
        p.say(JSON.stringify(shot.url).padEnd(48), 'slug', String(resolved && resolved.slug).padEnd(6),
          '-> rewritten', String(JSON.stringify(shot.body.url)).padEnd(40), 'status', shot.status,
          'bound', JSON.stringify(shot.body.tenant && shot.body.tenant.slug));
        // The property: whatever slug was taken is the FIRST path segment, and
        // the binding is that slug's tenant -- never another's.
        if (shot.body.tenant && resolved && shot.body.tenant.slug !== resolved.slug) crossed = true;
        if (shot.body.tenant && !resolved) crossed = true;
      }
    });
    p.say('storage reached', storageCalls.length, 'times; distinct bindings:',
      JSON.stringify([ ...new Set(storageCalls) ]));

    // The control: the same list through supertest, which is what a test in
    // tests/ would use. If these two disagree the instrument is the story.
    const viaClient = [ ];
    await inMulti(async () => {
      for (const url of [ '/foo/../bar/api/v1/entries', '/foo/%2e%2e/bar/api/v1/entries' ]) {
        const res = await request(app).get(url).set('Host', 'apex.org');
        viaClient.push(url + ' -> ' + res.status + ' bound '
          + JSON.stringify(res.body.tenant && res.body.tenant.slug));
      }
    });
    p.say('SAME cases through supertest (client-normalised, NOT what a server sees):');
    for (const l of viaClient) p.say('  ' + l);

    if (!crossed) {
      p.verdict('CONFIRMED-SAFE');
      p.say('Findings worth naming even though none is a cross-tenant defect:');
      p.say(' - `//foo//...`, `/foo%2Fbar/...` and `/FOO/...` produce NO match -> 404, fail closed.');
      p.say(' - Dot segments survive the rewrite verbatim (`/foo/./x` -> `/./x`, `/foo/../bar/x`');
      p.say('   -> `/../bar/x`) and Express 5 collapses NEITHER: both 404. The `..` never reaches');
      p.say('   a second slug, and nothing is served under a slug other than the first segment.');
      p.say(' - `/api/v1/entries` with no prefix reads `api` AS the slug: a deployment in path mode');
      p.say('   has no unprefixed API, and a tenant legitimately named `api` would shadow it.');
      p.say('   lib/admin/slug.js names reserved labels as a deliberate non-rule (DNS hijack); the');
      p.say('   PATH-mode consequence is not covered by that note.');
    } else p.verdict('DEFECT');

    // NON-VACUITY: drop the `match.index === 0` requirement.
    const red = withWeakened('server/tenant-resolver.js',
      [[ 'if (match && match.index === 0 && isSlug(match[1])) {', 'if (match && isSlug(match[1])) {' ]],
      weak => {
        const wr = weak.createResolver({ pathPattern: '/v1/([a-z0-9-]+)' });
        return wr.resolve('apex.org', '/api/v1/entries');
      });
    const strict = resolverModule.createResolver({ pathPattern: '/v1/([a-z0-9-]+)' })
      .resolve('apex.org', '/api/v1/entries');
    p.nonvacuity('`match.index === 0` removed: `/api/v1/entries` under pattern `/v1/([a-z0-9-]+)` now '
      + 'resolves to ' + JSON.stringify(red && red.slug) + ' with consumed ' + JSON.stringify(red && red.consumed)
      + ' -- a slug taken from the MIDDLE of the path, whose length would then slice the wrong prefix '
      + 'off req.url. Unweakened the same call returns ' + JSON.stringify(strict) + '.');
  }

  // -------------------------------------------------------------------- P2
  {
    const p = probe('P2', 'An absolute-form request line (GET http://host/path) desynchronises the '
      + 'resolver\'s view of the path from the router\'s -- in the fail-closed direction');

    const r = resolverModule.createResolver({ pathPattern: PATH_RULE });
    const absolute = 'http://apex.org/foo/api/v1/entries';
    p.say('resolver sees req.url =', JSON.stringify(absolute), '-> ', JSON.stringify(r.resolve('apex.org', absolute)));
    const parseurl = require(path.join(ROOT, 'node_modules', 'parseurl'));
    p.say('but Express routes on parseurl().pathname =',
      JSON.stringify(parseurl({ url: absolute }).pathname));

    const { app, storageCalls } = buildApp({ pathPattern: PATH_RULE, requireTokenClaim: false });
    const res = await inMulti(() => new Promise((resolve, reject) => {
      const srv = app.listen(0, '127.0.0.1', () => {
        const CRLF = String.fromCharCode(13, 10);
        const s = net.connect(srv.address().port, '127.0.0.1', () => s.write(
          [ 'GET ' + absolute + ' HTTP/1.1', 'Host: apex.org', 'Connection: close' ].join(CRLF) + CRLF + CRLF));
        let buf = '';
        s.on('data', d => { buf += d; });
        s.on('close', () => { srv.close(); resolve(buf.split(CRLF)[0]); });
        s.on('error', e => { srv.close(); reject(e); });
      });
    }));
    p.say('over a real socket, absolute-form ->', res, '| storage reached:', storageCalls.length);
    p.verdict(/404/.test(res) && storageCalls.length === 0 ? 'CONFIRMED-SAFE' : 'DEFECT');
    p.say('The resolver matches `req.url` raw; Express routes `parseurl(req).pathname`. They disagree');
    p.say('for absolute-form, and the disagreement refuses the request rather than routing it');
    p.say('unbound -- but the disagreement is real, and the anchor (`^/`) is what makes it safe.');

    const redApp = withWeakened('server/tenant-resolver.js',
      [[ 'const match = pathRe.exec(pathname);', 'const match = pathRe.exec(require(\'url\').parse(pathname).pathname || pathname);' ]],
      weak => buildApp({ pathPattern: PATH_RULE, requireTokenClaim: false, resolverModule: weak }));
    const redOut = await inMulti(() => new Promise(resolve => {
      const srv = redApp.app.listen(0, '127.0.0.1', () => {
        const CRLF = String.fromCharCode(13, 10);
        const s = net.connect(srv.address().port, '127.0.0.1', () => s.write(
          [ 'GET ' + absolute + ' HTTP/1.1', 'Host: apex.org', 'Connection: close' ].join(CRLF) + CRLF + CRLF));
        let buf = '';
        s.on('data', d => { buf += d; });
        s.on('close', () => { srv.close(); resolve(buf); });
      });
    }));
    p.nonvacuity('the resolver taught to parse absolute-form (pathname extracted before matching): '
      + 'the same request line now returns ' + JSON.stringify(redOut.split(String.fromCharCode(13, 10))[0])
      + ' and, because `consumed` is then sliced off a URL whose prefix is the SCHEME, the rewritten '
      + 'url is ' + JSON.stringify((() => { try { return JSON.parse(redOut.split('\r\n\r\n').slice(-1)[0]).url; } catch { return 'n/a'; } })())
      + '. So the probe is reading the anchor, not an unreachable route.');
  }
}

// ======================================================== SECTION credential

async function sectionCredential () {
  const p = probe('C1', 'TENANT_REQUIRE_TOKEN_CLAIM does not see a credential presented in the '
    + 'request BODY, so the only control standing in for T3.3 can be stepped around');

  const enclave = { verifyJWT: v => (v === 'tok-foo' ? { tenant: TENANT_FOO } : null) };
  const { app, storageCalls } = buildApp({
    hostPattern: SUBDOMAIN_RULE, enclave, bodyParser: true
    // requireTokenClaim left at its default, which is TRUE.
  });
  const VICTIM = 'bar.user-content.apex.org';

  const shots = [ ];
  await inMulti(async () => {
    async function shot (name, run) {
      const res = await run();
      shots.push({ name, status: res.status, body: res.body });
      p.say(name.padEnd(44), String(res.status).padEnd(4),
        JSON.stringify(res.body).slice(0, 150));
    }
    await shot('foo JWT in ?token= on bar\'s host', () =>
      request(app).get('/api/v1/entries?token=tok-foo').set('Host', VICTIM));
    await shot('foo JWT as Bearer on bar\'s host', () =>
      request(app).get('/api/v1/entries').set('Host', VICTIM).set('Authorization', 'Bearer tok-foo'));
    await shot('opaque token in ?token= on bar\'s host', () =>
      request(app).get('/api/v1/entries?token=opaque-foo').set('Host', VICTIM));
    await shot('api-secret HEADER on bar\'s host', () =>
      request(app).get('/api/v1/entries').set('Host', VICTIM).set('api-secret', 'deadbeef'));
    // Not an attack -- an operational consequence of the same rule, on the
    // tenant's OWN host: any Authorization header that is not a verifiable
    // Bearer claim counts as "a credential that names no site".
    await shot('Basic auth header on foo\'s OWN host', () =>
      request(app).get('/api/v1/entries').set('Host', 'foo.user-content.apex.org')
        .set('Authorization', 'Basic ' + Buffer.from('user:pass').toString('base64')));
    await shot('foo JWT in the BODY on bar\'s host', () =>
      request(app).post('/api/v1/entries').set('Host', VICTIM).send({ token: 'tok-foo' }));
    await shot('opaque token in the BODY on bar\'s host', () =>
      request(app).post('/api/v1/entries').set('Host', VICTIM).send({ token: 'opaque-foo' }));
    await shot('api secret in the BODY on bar\'s host', () =>
      request(app).post('/api/v1/entries').set('Host', VICTIM).send({ secret: 'deadbeef' }));
    await shot('api secret in a BODY ARRAY on bar\'s host', () =>
      request(app).post('/api/v1/entries').set('Host', VICTIM).send([ { secret: 'deadbeef', sgv: 100 } ]));
  });

  const query = shots.find(s => s.name.startsWith('foo JWT in ?token='));
  const body = shots.find(s => s.name.startsWith('foo JWT in the BODY'));

  // The downstream half: lib/authorization DOES read those body fields.
  const authSrc = fs.readFileSync(path.join(ROOT, 'lib/authorization/index.js'), 'utf8');
  const readsBodyToken = /req\.body\.token/.test(authSrc) && /req\.body\[0\]\.token/.test(authSrc);
  const readsBodySecret = /req\.body\.secret/.test(authSrc) && /req\.body\[0\]\.secret/.test(authSrc);
  p.say('lib/authorization/index.js reads req.body.token / req.body[0].token:', readsBodyToken);
  p.say('lib/authorization/index.js reads req.body.secret / req.body[0].secret:', readsBodySecret);
  p.say('storage reached under binding:', JSON.stringify(storageCalls));

  if (query.status === 403 && body.status === 200 && readsBodyToken) {
    p.verdict('DEFECT');
    p.say('The SAME credential is refused in the query string and accepted in the body. It then');
    p.say('reaches lib/authorization, whose subject list is process-wide (the module doc says so),');
    p.say('so it authorises its holder against the tenant the HOST bound -- which is the other one.');
  } else {
    p.verdict('CONFIRMED-SAFE');
  }

  p.nonvacuity('This is a DEFECT, so the evidence is a DIFFERENTIAL rather than a weakening: the '
    + 'identical credential returns ' + query.status + ' as `?token=` and ' + body.status + ' in the '
    + 'body, on the same host, against the same middleware instance, in the same process. The probe '
    + 'cannot be passing for an unrelated reason because one arm of it goes red and the other green.');
}

// ======================================================== SECTION failclosed

async function sectionFailclosed () {

  // -------------------------------------------------------------------- F1
  {
    const p = probe('F1', 'An unrecognised, unknown, deleted or disabled tenant fails CLOSED -- '
      + 'never to a default and never to single-tenant mode');

    const { app, storageCalls } = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false });
    await inMulti(async () => {
      for (const [ name, host ] of [
        [ 'known + active', 'foo.user-content.apex.org' ]
        , [ 'never existed', 'nosuchtenant.user-content.apex.org' ]
        , [ 'deleted (row gone)', 'gone.user-content.apex.org' ]
        , [ 'registered but INACTIVE', 'retired.user-content.apex.org' ]
        , [ 'host matches no rule', 'apex.org' ]
        , [ 'apex with a port', 'apex.org:8443' ]
      ]) {
        const res = await request(app).get('/api/v1/entries').set('Host', host);
        p.say(name.padEnd(26), String(res.status).padEnd(4), JSON.stringify(res.body).slice(0, 110));
      }
    });
    p.say('storage reached', storageCalls.length, 'time(s):', JSON.stringify(storageCalls));

    // A registry that cannot answer.
    const brokenRegistry = { lookup: async () => { throw Object.assign(new Error('boom'), { code: '42501' }); } };
    const broken = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, registry: brokenRegistry });
    const bres = await inMulti(() => request(broken.app).get('/api/v1/entries')
      .set('Host', 'foo.user-content.apex.org'));
    p.say('registry throws ->', bres.status, JSON.stringify(bres.body), '| storage reached',
      broken.storageCalls.length);

    p.verdict(storageCalls.length === 1 && broken.storageCalls.length === 0 ? 'CONFIRMED-SAFE' : 'DEFECT');

    // NON-VACUITY: a registry that answers with a default for anything it does
    // not know -- the classic fail-open.
    const openRegistry = {
      lookup: async slug => {
        const hit = TENANTS.find(t => t.slug === slug);
        return hit ? { id: hit.id, slug: hit.slug, isActive: hit.isActive !== false, displayName: '' }
          : { id: TENANT_FOO, slug: 'foo', isActive: true, displayName: '' };
      }
    };
    const openApp = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, registry: openRegistry });
    const ores = await inMulti(() => request(openApp.app).get('/api/v1/entries')
      .set('Host', 'nosuchtenant.user-content.apex.org'));
    p.nonvacuity('registry stubbed to answer with a default tenant for any unknown slug: the same '
      + 'unknown host now returns ' + ores.status + ' bound to ' + JSON.stringify(ores.body.bound)
      + ' and reaches storage. The probe distinguishes a refusal from an unreachable route.');
  }

  // -------------------------------------------------------------------- F2
  {
    const p = probe('F2', 'A request that reaches a storage call with no tenant bound is refused '
      + 'by the scope, not served under a default');
    const results = [ ];
    await inMulti(() => {
      try { results.push('multi: ' + String(tenantScope.requireTenant('probe'))); }
      catch (e) { results.push('multi: THREW -- ' + e.message.split('.')[0]); }
    });
    try { results.push('single: ' + String(tenantScope.requireTenant('probe'))); }
    catch (e) { results.push('single: THREW -- ' + e.message.split('.')[0]); }
    for (const r of results) p.say(r);
    p.verdict(/multi: THREW/.test(results[0]) ? 'CONFIRMED-SAFE' : 'DEFECT');
    p.nonvacuity('the same call under tenancy mode `single` returns ' + JSON.stringify(results[1])
      + ' instead of throwing -- so the throw is the multi-mode assertion firing, not the call '
      + 'being impossible to make.');
  }
}

// ============================================================= SECTION mount

async function sectionMount () {

  // -------------------------------------------------------------------- M1
  {
    const p = probe('M1', 'What mounts above and below the tenant middleware in lib/server/app.js');
    const src = fs.readFileSync(path.join(ROOT, 'lib/server/app.js'), 'utf8');
    const lines = src.split('\n');
    const mountIdx = lines.findIndex(l => l.includes('app.use(resolveTenant)'));
    const above = lines.slice(0, mountIdx).map((l, i) => [ i + 1, l ])
      .filter(([ , l ]) => /app\.(use|get|post|all|set)\(/.test(l) || /\)\(app\)/.test(l));
    p.say('layers registered BEFORE app.use(resolveTenant) (line ' + (mountIdx + 1) + '):');
    for (const [ n, l ] of above) p.say('  app.js:' + n, l.trim());
    p.say('everything else -- static files, /translations, /api, /api/v1..v3, /clock, /pebble,');
    p.say('swagger, /bundle, the error handler -- is registered after, so every request that can');
    p.say('reach a storage call has passed the middleware.');
    p.verdict(above.length <= 2 ? 'CONFIRMED-SAFE' : 'DEFECT');
    p.say('The one layer above it is lib/middleware/configure-request, which sets the query parser');
    p.say('and defaults req.body to {}; it touches no storage.');
    p.nonvacuity('the assertion is over the SOURCE ORDER of a file this harness reads at run time; '
      + 'if the mount moved below a storage-touching layer the list above would grow and the '
      + 'verdict would flip. Demonstrated by F1/F2: a request that does reach storage without a '
      + 'binding throws rather than being served.');
  }

  // -------------------------------------------------------------------- M2
  {
    const p = probe('M2', 'The HTTP->HTTPS redirect (app.js:132) is mounted BELOW the tenant '
      + 'middleware and rebuilds the URL from the REWRITTEN req.url, dropping the tenant prefix');

    const pathMode = buildApp({ pathPattern: PATH_RULE, requireTokenClaim: false, httpsRedirect: true });
    const hostMode = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false, httpsRedirect: true });

    const a = await inMulti(() => request(pathMode.app).get('/foo/api/v1/entries?count=10')
      .set('Host', 'apex.org'));
    p.say('path mode : GET /foo/api/v1/entries?count=10 ->', a.status, 'Location:', a.headers.location);
    const b = await inMulti(() => request(hostMode.app).get('/api/v1/entries?count=10')
      .set('Host', 'foo.user-content.apex.org'));
    p.say('host mode : GET /api/v1/entries?count=10 ->', b.status, 'Location:', b.headers.location);

    const lost = a.headers.location && !a.headers.location.includes('/foo/');
    if (lost) {
      p.verdict('DEFECT');
      p.say('The redirect target has no tenant prefix. On the follow-up request the path rule reads');
      p.say('`api` as the slug, which is not a tenant, so the client gets a 404 for a URL it was');
      p.say('just told to use. INSECURE_USE_HTTP defaults false, so this layer is ON by default.');
      p.say('Not a cross-tenant read: the wrong slug is refused. It is an availability defect that');
      p.say('makes path-prefix tenancy unusable over plain HTTP, and it is caused by mount order.');
    } else p.verdict('CONFIRMED-SAFE');

    p.nonvacuity('the identical layer in HOST mode preserves the URL exactly (' + b.headers.location
      + '), because nothing rewrote req.url. One arm red, one green, same code, same process -- so '
      + 'the probe is measuring the rewrite and not the redirect.');
  }
}

// ============================================================= SECTION admin

async function sectionAdmin () {
  const p = probe('A1', 'The admin plane (T3.2) is not reachable from the consumer app, and its '
    + '"secured by unreachability" claim holds against a real socket');

  // 1. Is the admin router mounted anywhere in the consumer app?
  const serverSrc = [ 'lib/server/app.js', 'lib/server/server.js', 'lib/api/index.js'
    , 'lib/api2/index.js', 'lib/api3/index.js' ]
    .map(f => ({ f, src: fs.existsSync(path.join(ROOT, f)) ? fs.readFileSync(path.join(ROOT, f), 'utf8') : '' }));
  const mounted = serverSrc.filter(x => /require\(['"][./]*(\.\.\/)?admin(\/(app|index))?['"]\)/.test(x.src));
  p.say('consumer-app files requiring lib/admin:', mounted.length ? mounted.map(m => m.f).join(', ') : 'NONE');

  const { app } = buildApp({ hostPattern: SUBDOMAIN_RULE, requireTokenClaim: false });
  const probe404 = await inMulti(() => request(app).get('/api/admin/tenants')
    .set('Host', 'foo.user-content.apex.org'));
  p.say('GET /api/admin/tenants on the consumer app ->', probe404.status,
    JSON.stringify(probe404.body).slice(0, 90));

  // 2. The bind refusal, against a real listener rather than the comment.
  const bindGuard = lib('admin/bind-guard');
  const routable = Object.values(require('node:os').networkInterfaces()).flat()
    .filter(i => i && i.family === 'IPv4' && !i.internal).map(i => i.address)[0];
  p.say('a routable address on this host:', routable || '(none found)');

  let refused = null;
  try {
    await bindGuard.resolveBind({ ADMIN_BIND: '0.0.0.0', ADMIN_PORT: '18337' });
    refused = 'NOT REFUSED';
  } catch (err) { refused = err.code; }
  p.say('resolveBind(ADMIN_BIND=0.0.0.0) ->', refused);

  let refusedRoutable = null;
  if (routable) {
    try {
      await bindGuard.resolveBind({ ADMIN_BIND: routable, ADMIN_PORT: '18337' });
      refusedRoutable = 'NOT REFUSED';
    } catch (err) { refusedRoutable = err.code; }
    p.say('resolveBind(ADMIN_BIND=' + routable + ') ->', refusedRoutable);
  }

  // 3. And the crown jewels: with the acknowledgement, the SAME address binds
  //    and answers with no credential at all. This is what the refusal is worth.
  const adminIndex = lib('admin/index');
  const adminApp = lib('admin/app');
  const fakeStore = {
    listTenants: async () => [ { id: TENANT_FOO, slug: 'foo', is_active: true } ]
    , health: async () => ({ sources: { database: { status: 'ok' } } })
    , end: async () => { }
  };
  let unauthenticated = null;
  if (routable) {
    const bind = await bindGuard.resolveBind({
      ADMIN_BIND: routable, ADMIN_PORT: '18337', ADMIN_INSECURE_BIND_ACKNOWLEDGED: 'true' });
    const running = await adminIndex.listen(fakeStore, bind, { log: () => { } });
    try {
      unauthenticated = await new Promise(resolve => {
        http.get({ host: routable, port: 18337, path: '/api/admin/tenants' }, res => {
          let b = ''; res.on('data', d => { b += d; }); res.on('end', () => resolve({ status: res.statusCode, body: b }));
        }).on('error', e => resolve({ status: 'ERR', body: e.code }));
      });
    } finally {
      await adminIndex.stop(running);
    }
    p.say('with the acknowledgement set, the same bind opens and answers an UNAUTHENTICATED');
    p.say('GET /api/admin/tenants from ' + routable + ':18337 ->', unauthenticated.status,
      String(unauthenticated.body).slice(0, 90));
  }

  const safe = mounted.length === 0 && probe404.status === 404
    && refused === 'ERR_ADMIN_INSECURE_BIND'
    && (!routable || refusedRoutable === 'ERR_ADMIN_INSECURE_BIND');
  p.verdict(safe ? 'CONFIRMED-SAFE' : 'DEFECT');
  p.say('lib/admin is required by bin/admin.js and by nothing under lib/server or lib/api*.');
  p.say('It is a separate process with a separate listener; there is no route into it from 1337.');

  // NON-VACUITY: mount the admin router on the consumer app and ask again.
  const redApp = express();
  lib('middleware/configure-request')(redApp);
  redApp.use(tenantMiddleware.create({
    resolver: resolverModule.createResolver({ hostPattern: SUBDOMAIN_RULE })
    , registry: registryModule.fromList(TENANTS), requireTokenClaim: false }));
  redApp.use(adminApp.create(fakeStore, { log: () => { } }));
  const red = await inMulti(() => request(redApp).get('/api/admin/tenants')
    .set('Host', 'foo.user-content.apex.org'));
  p.nonvacuity('the admin router mounted onto the consumer app: the same unauthenticated request '
    + 'returns ' + red.status + ' ' + JSON.stringify(red.body).slice(0, 80) + ' -- every tenant on '
    + 'the deployment, from the consumer port, through the tenant middleware. So the 404 above is '
    + 'the absence of a mount, not the absence of a route that would answer. '
    + (unauthenticated ? 'And the acknowledged non-loopback bind answered ' + unauthenticated.status
      + ' with no credential, which is what the bind refusal is protecting.' : ''));
}

// ------------------------------------------------------------------- driver

(async () => {
  const sections = {
    host: sectionHost, path: sectionPath, credential: sectionCredential
    , failclosed: sectionFailclosed, mount: sectionMount, admin: sectionAdmin
  };
  const chosen = SECTION === 'all' ? Object.keys(sections) : [ SECTION ];
  for (const name of chosen) {
    if (!sections[name]) {
      console.error('unknown section ' + name + '; one of ' + Object.keys(sections).join(' | ') + ' | all');
      process.exit(2);
    }
    console.log('\n######## ' + name + ' ########');
    await sections[name]();
  }
  report();
  console.log(failures ? failures + ' DEFECT verdict(s).' : 'no DEFECT verdicts.');
})().catch(err => { console.error(err); process.exit(1); });
