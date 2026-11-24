'use strict';

// Exercise a ref's history operation and Mongo read adapter in process. Mingo
// executes the driver's read against synthetic rows. No DB or listener is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { isDeepStrictEqual, parseArgs } = require('node:util');
const { CRM, git, report } = require('./_gate');

const start = Date.UTC(2020, 0, 1);
const records = Array.from({ length: 6 }, (_, i) => ({
  identifier: 'fixture-' + i, srvModified: start + 1 + Math.floor(i / 3)
}));

function memoryCollection(find) {
  return {
    find(filter) {
      let order, count, offset, fields;
      return {
        sort(value) { order = value; return this; },
        limit(value) { count = value; return this; },
        skip(value) { offset = value; return this; },
        project(value) { fields = value; return this; },
        toArray() {
          const cursor = find(structuredClone(records), filter, fields);
          if (order) cursor.sort(order);
          if (offset) cursor.skip(offset);
          if (count) cursor.limit(count);
          return cursor.all();
        }
      };
    }
  };
}

function historyReader(root, find) {
  const Collection = require(path.join(root, 'lib/api3/generic/collection'));
  const history = require(path.join(root, 'lib/api3/generic/history/operation'));
  const store = { collection: () => memoryCollection(find), ensureIndexes() {} };
  const ctx = { store };
  const app = { get() {}, setENVTruthy() { return false; } };
  const env = {};
  const collection = new Collection({ ctx, env, app, colName: 'treatments', storageColName: 'treatments' });
  const read = history(ctx, env, app, collection);

  return async function page(stamp, limit) {
    const req = { params: { lastModified: String(stamp) }, query: { limit: String(limit) } };
    const headers = {};
    const res = {
      setHeader(key, value) { headers[key.toLowerCase()] = value; },
      status(code) { this.code = code; return this; },
      format(formats) { formats.json(); },
      send(body) { this.body = body; },
      json(body) { this.body = body; }
    };
    await read(req, res);
    assert.equal(res.code, 200, 'history read must succeed');
    assert.ok(Array.isArray(res.body.result));
    return { docs: res.body.result, etag: headers.etag };
  };
}

async function scan(page, limit, source) {
  let stamp = start;
  const ids = [];
  for (let i = 0; i <= records.length; i++) {
    const { docs, etag } = await page(stamp, limit);
    if (!docs.length) {
      const expected = records.map(row => row.identifier).sort();
      const ok = isDeepStrictEqual(ids.sort(), expected);
      return { ok, text: source + ' cursor, page size ' + limit + ': returned ' +
        ids.length + '/' + expected.length + ' identities; ended after ' + i + ' nonempty pages' };
    }
    if (docs.length > limit) {
      return { ok: false, text: source + ' cursor returned ' + docs.length + ' identities for a limit of ' + limit };
    }
    ids.push(...docs.map(row => row.identifier));
    const next = source === 'body' ? docs.at(-1).srvModified : Number(/^W\/"(\d+)"$/.exec(etag)?.[1]);
    if (!Number.isSafeInteger(next) || next <= stamp) {
      return { ok: false, text: source + ' cursor did not advance on a nonempty page' };
    }
    stamp = next;
  }
  return { ok: false, text: source + ' cursor did not reach the end of the fixture' };
}

async function main() {
  const { values } = parseArgs({ options: {
    ref: { type: 'string', default: 'official/dev' }, 'whole-groups': { type: 'boolean' }
  } });
  const rev = git(['rev-parse', '--verify', values.ref + '^{commit}']);
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'history-'));
  try {
    const archive = execFileSync('git', ['-C', CRM, 'archive', rev, 'lib', 'package.json'],
      { maxBuffer: 64 * 1024 * 1024 });
    execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
    fs.symlinkSync(path.join(CRM, 'node_modules'), path.join(scratch, 'node_modules'));
    const { find } = require(require.resolve('mingo', { paths: [path.resolve(__dirname, '../../qc')] }));
    const page = historyReader(scratch, find);
    const results = [];
    for (const limit of values['whole-groups'] ? [3] : [3, 2]) {
      for (const source of ['ETag', 'body']) results.push(await scan(page, limit, source));
    }
    return { rev, results };
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}

main().then(({ rev, results }) => report('history continuation at ' + rev, results))
  .catch(error => { console.error('CONTROL-INVALID:', error.message); process.exitCode = 2; });
