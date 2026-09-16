'use strict';
/*
 * count0-two-paths.js — what `?count=0` actually does, on both paths.
 *
 * WHY THIS EXISTS. The read-defects report measured `?count=0` returning the
 * whole collection and noted, in one clause, that it used a `find` to force the
 * read past the runtime cache. Nobody wrote down what happens WITHOUT that
 * find. The answer is different: the cache serves it and returns 0 rows, which
 * is what the client asked for. So dev answers one request two ways, and the
 * bf/reads PR body stated only the dangerous half until this was run.
 *
 * ARMS, stated here so the numbers are comparable to a re-run:
 *   24 sgv entries stored, five minutes apart, deleted afterwards.
 *   count=0 with no find      — the cache path
 *   count=0 with find[sgv]    — forced to the database
 *   count=5 with find         — control, must be 5
 *   no count with find        — control, must be the endpoint default (10)
 *
 * A `?count=0` arm on /treatments was here and was REMOVED: nothing stores a
 * treatment, so it returned 0 rows on every tree and distinguished nothing.
 *
 * USAGE:  node tools/probes/count0-two-paths.js [worktree]
 * Default worktree is externals/work/crm-base-verify (dev @ a8888f0d). Point it
 * at a branch worktree to see the after-state. Needs the mongod named in that
 * worktree's my.test.env to be up.
 */
const fs = require('fs');
const W = process.argv[2] ||
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-base-verify';
process.chdir(W);

for (const line of fs.readFileSync(W + '/my.test.env', 'utf8').split('\n')) {
  const t = line.trim();
  if (!t || t.startsWith('#') || !t.includes('=')) continue;
  process.env[t.slice(0, t.indexOf('=')).trim()] = t.slice(t.indexOf('=') + 1).trim();
}

const request  = require(W + '/node_modules/supertest');
const express  = require(W + '/node_modules/express');
const language = require(W + '/lib/language')();
const api      = require(W + '/lib/api/');

const FIVE_MINUTES = 1000 * 60 * 5, STORED = 24;

process.env.API_SECRET = 'this is my long pass phrase';
const env = require(W + '/lib/server/env')();
env.settings.authDefaultRoles = 'readable';
env.settings.enable = ['careportal', 'api'];
const app = express();
app.enable('api');

require(W + '/lib/server/bootevent')(env, language).boot(async function booted (ctx) {
  ctx.ddata = require(W + '/lib/data/ddata')();
  app.use('/api/v1', api(env, ctx));
  const archive = require(W + '/lib/server/entries')(env, ctx);

  await new Promise(function (res) {
    const creating = [];
    for (let i = 0; i < STORED; i++) {
      creating.push({ type: 'sgv', sgv: 100 + i, date: Date.now() - FIVE_MINUTES * i });
    }
    archive.create(creating, function () { setTimeout(res, 300); });
  });

  const cases = [
    ['count=0,  no find   (cache path)',    '/api/v1/entries.json?count=0'],
    ['count=0,  with find (database path)', '/api/v1/entries.json?find[sgv][$gte]=1&count=0'],
    ['count=5,  with find (control)',       '/api/v1/entries.json?find[sgv][$gte]=1&count=5'],
    ['no count, with find (control)',       '/api/v1/entries.json?find[sgv][$gte]=1'],
  ];

  console.log('\n' + W + '\n' + STORED + ' sgv entries stored\n');
  for (const [label, url] of cases) {
    const res = await request(app).get(url);
    const n = Array.isArray(res.body) ? res.body.length + ' rows'
            : JSON.stringify(res.body).slice(0, 50);
    console.log('  ' + label.padEnd(38) + 'HTTP ' + res.status + '   ' + n);
  }
  await archive().deleteMany({});
  process.exit(0);
});
