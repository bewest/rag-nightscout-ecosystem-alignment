'use strict';
/*
 * Triage probe (cgm-remote-monitor issue #8104): with a non-English language,
 * (a) which IFTTT Maker event names does an alarm produce, and (b) when is the
 * same alarm sent again?
 *
 * Usage: node tools/lab/triage-2026-09/maker-language.js <cgm-remote-monitor tree with node_modules>
 *
 * Builds the server's notification path the way lib/server/bootevent.js does
 * (lib/language set and loaded, lib/levels with levels.translate =
 * language.translate, lib/plugins/maker, lib/server/pushnotify) and emits a
 * WARN alarm through pushnotify.emitNotification. NOTHING goes to IFTTT:
 * https.get is replaced with an http.get of the same URL rewritten to a stub
 * on 127.0.0.1 (Node's own URL handling is kept), and the stub records the
 * event name of each trigger. Time is moved by offsetting Date.now, which is
 * what node-cache reads.
 *
 * Half (a), event names. Arms: LANGUAGE=ru and de. Control: en, which must give
 *   ns-event, ns-warning, ns-warning-simplealarms.
 * Half (b), resend. The same alarm is emitted, then again 45 s later and
 *   again 16 min later.
 *   ok-en     stub answers 200 (control): the 45 s emit must be suppressed
 *   ok-ru     the same with ru: shows whether the translated name alone
 *             changes the resend when the call succeeds
 *   fail-en   stub resets the connection (a failed maker call): the 45 s
 *             emit is sent again, because the dedup key keeps its 30 s TTL
 *             unless a send reports success
 *
 * Exit status: 0 when every language gives the untranslated level names;
 * 1 when a non-English language gives translated names (the defect in half a);
 * 2 when a control misbehaves (the probe measures nothing); 3 on a harness error.
 * Half (b) is printed, not scored: what makes a real IFTTT call fail is not
 * measured here.
 */
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const root = path.resolve(process.argv[2] || '.');
process.on('uncaughtException', (e) => { console.error('harness error:', e); process.exit(3); });
process.chdir(root); // lib/language.js reads ./translations relative to cwd
const r = (p) => require(path.join(root, p));

let offset = 0;
const realNow = Date.now.bind(Date);
Date.now = () => realNow() + offset;

let stubMode = 'ok';
const hits = [];
const stub = http.createServer((req, res) => {
  const m = /^\/trigger\/([^/]+)\//.exec(req.url);
  hits.push(m ? decodeURIComponent(m[1]) : req.url);
  if (stubMode === 'fail') { req.socket.destroy(); return; }
  res.end('ok');
});
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

function build (lang) {
  const language = r('lib/language')();
  language.set(lang);
  language.loadLocalization(fs);
  const levels = r('lib/levels');
  levels.translate = language.translate;
  const env = { settings: r('lib/settings')(), extendedSettings: { maker: { key: 'probe-key' } } };
  const ctx = { levels, language };
  ctx.maker = r('lib/plugins/maker')(env);
  ctx.pushnotify = r('lib/server/pushnotify')(env, ctx);
  return ctx;
}
function alarm (ctx) {
  return { level: ctx.levels.WARN, title: 'LOW', message: 'BG Now', group: 'default', plugin: { name: 'simplealarms' } };
}
async function emit (ctx) {
  const before = hits.length;
  ctx.pushnotify.emitNotification(alarm(ctx));
  await sleep(400);
  return hits.slice(before);
}

async function main () {
  await new Promise((res) => stub.listen(0, '127.0.0.1', res));
  const port = stub.address().port;
  https.get = function (url, cb) {
    const u = String(url);
    if (!u.startsWith('https://maker.ifttt.com/')) throw new Error('probe refused a non-maker URL');
    return http.get(u.replace('https://maker.ifttt.com/', `http://127.0.0.1:${port}/`), cb);
  };
  const quiet = console.info; console.info = () => {}; const qerr = console.error; console.error = () => {};
  const names = {};
  for (const lang of ['en', 'ru', 'de']) { stubMode = 'ok'; names[lang] = await emit(build(lang)); }
  const resend = {};
  for (const [label, lang, mode] of [['ok-en', 'en', 'ok'], ['ok-ru', 'ru', 'ok'], ['fail-en', 'en', 'fail']]) {
    stubMode = mode; offset = 0;
    const ctx = build(lang);
    const t0 = (await emit(ctx)).length;
    offset = 45e3; const t45 = (await emit(ctx)).length;
    offset = 16 * 60e3; const t16 = (await emit(ctx)).length;
    resend[label] = [t0, t45, t16];
  }
  console.info = quiet; console.error = qerr;
  stub.close();

  console.log('tree', root);
  console.log('(a) event names per language (triggers the alarm produced):');
  for (const lang of Object.keys(names)) console.log(`  ${lang}: ${names[lang].join(', ')}`);
  console.log('(b) triggers sent at t=0 / t=45 s / t=16 min for the same alarm:');
  for (const k of Object.keys(resend)) console.log(`  ${k}: ${resend[k].join(' / ')}`);

  const want = ['ns-event', 'ns-warning', 'ns-warning-simplealarms'];
  const same = (a) => a.length === want.length && a.every((x, i) => x === want[i]);
  if (!same(names.en) || resend['ok-en'][1] !== 0 || resend['ok-en'][0] === 0) { console.log('a control misbehaved'); return 2; }
  const bad = ['ru', 'de'].filter((l) => !same(names[l]));
  console.log(bad.length ? `RESULT: DEFECT - translated level names in maker events for ${bad.join(', ')}` : 'RESULT: untranslated names in every language');
  return bad.length ? 1 : 0;
}
main().then((v) => process.exit(v), (e) => { console.error('harness error:', e); process.exit(3); });
