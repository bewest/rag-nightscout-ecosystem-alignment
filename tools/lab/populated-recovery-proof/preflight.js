#!/usr/bin/env node
'use strict';

// LOCAL research preflight. Requires actual importer/identity/catalogue modules
// by path; never opens a database, listener, Docker service or key provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const crypto = require('node:crypto');

const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const worktree = option('--worktree');
const control = option('--control');
const controls = ['broken-snapshot', 'wrong-tenant', 'missing-key-reference', 'partial-restore'];
const clone = value => JSON.parse(JSON.stringify(value));
const key = row => [row.tenant, row.kind, row.doc._id].join(':');

async function main () {
  if (!worktree || (control && !controls.includes(control))) {
    throw new Error('Usage: --worktree <actual CRM tree> [--control ' + controls.join('|') + ']');
  }
  const tree = path.resolve(worktree);
  const head = execFileSync('git', ['-C', tree, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const dirty = execFileSync('git', ['-C', tree, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' });
  if (dirty.trim()) throw new Error('CRM_TREE_DIRTY: tracked changes prevent commit-only provenance');
  const importer = require(path.join(tree, 'lib/import/entries'));
  const codec = require(path.join(tree, 'lib/storage/postgres-identity'));
  const catalogue = require(path.join(tree, 'lib/migrations/catalogue'));
  const { ObjectId } = createRequire(path.join(tree, 'package.json'))('mongodb');
  const fixtureFile = path.join(__dirname, 'fixture.json');
  const original = JSON.parse(fs.readFileSync(fixtureFile, 'utf8'));
  const actual = clone(original);
  // Controls damage an independent candidate, never select a forced exit code.
  if (control === 'broken-snapshot') actual.rows[0].doc.extension.ordered.reverse();
  if (control === 'wrong-tenant') actual.rows[0].tenant = original.tenants[1];
  if (control === 'missing-key-reference') actual.recoveryKeyReferences = [];
  if (control === 'partial-restore') actual.rows.pop();
  const checks = [];
  async function check (name, fn) {
    try { await fn(); checks.push({ name, ok: true }); } catch (error) {
      checks.push({ name, ok: false, symptom: error.code || error.message.split('\n')[0] });
    }
  }
  await check('fixture populated typed identities and tenant mapping remain complete', () => {
    assert.deepEqual(actual.rows.map(key), original.rows.map(key));
  });
  await check('logical JSON values preserve null/missing, nested source and array order', () => {
    assert.deepEqual(actual.rows, original.rows);
    assert.equal(Object.hasOwn(actual.rows[1].doc.extension, 'nullable'), false);
    assert.equal(actual.rows[0].doc.extension.nullable, null);
    // Object member order is not part of adopted JSONB equality.
    const doc = original.apiRows[0];
    assert.deepEqual(Object.fromEntries(Object.entries(doc).reverse()), doc);
  });
  await check('synthetic ciphertext metadata has a named recovery key reference', () => {
    for (const reference of actual.ciphertextReferences) {
      assert.ok(actual.recoveryKeyReferences.includes(reference.keyRef), 'missing recovery key reference');
      assert.ok(actual.tenants.includes(reference.tenant), 'unknown ciphertext tenant');
    }
  });
  await check('actual identity codec preserves ObjectId/string twin across JSON serialization', () => {
    const rows = original.rows.map(row => {
      const doc = { ...row.doc, _id: row.kind === 'objectid' ? new ObjectId(row.doc._id) : row.doc._id };
      const encoded = codec.encodeDocument(doc);
      const decoded = codec.decodeDocument(clone(encoded));
      assert.equal(encoded.id_kind, row.kind);
      assert.deepEqual(decoded, doc);
      return [row.tenant, encoded.id_kind, encoded.doc._id].join(':');
    });
    assert.equal(new Set(rows).size, original.rows.length);
  });
  const A = original.tenants[0];
  const sourceFor = docs => ({
    key: 'https://synthetic-source.invalid',
    async baseline ({ limit, skip }) { return clone(docs.slice(skip, skip + limit)); },
    async history ({ cursor }) { return { docs: [], cursor }; }
  });
  await check('actual importer preserves supported API page values and traversal order to injected target', async () => {
    const pages = [];
    const result = await importer.importEntries({ source: sourceFor(original.apiRows),
      target: { async writePage (docs) { pages.push(clone(docs)); } }, tenant: A, pageSize: 2, now: () => 10000 });
    assert.deepEqual(pages.flat(), original.apiRows);
    assert.equal(pages.length, 2);
    assert.equal(result.baselineCount, original.apiRows.length);
    assert.equal(result.phase, 'done');
  });
  await check('actual importer refuses API textual collision of typed twins before first write', async () => {
    let writes = 0;
    const twins = original.rows.slice(0, 2).map(row => clone(row.doc));
    await assert.rejects(importer.importEntries({ source: sourceFor(twins),
      target: { async writePage () { writes++; } }, tenant: A, pageSize: 2 }), { code: 'IMPORT_ID_COLLISION' });
    assert.equal(writes, 0);
  });
  await check('actual importer refuses raw BSON source document rather than flattening its kind', async () => {
    let writes = 0;
    const doc = { ...original.rows[0].doc, _id: new ObjectId(original.rows[0].doc._id) };
    const source = sourceFor([]);
    source.baseline = async () => [doc];
    await assert.rejects(importer.importEntries({ source,
      target: { async writePage () { writes++; } }, tenant: A }), { code: 'IMPORT_DOCUMENT_INVALID' });
    assert.equal(writes, 0);
  });
  await check('actual importer interruption propagates and rerun repeats beginning (no durable checkpoint claim)', async () => {
    const pages = [];
    let first = true;
    const target = { async writePage (docs) {
      pages.push(clone(docs));
      if (first && docs[0]._id === original.apiRows[2]._id) { first = false; throw new Error('synthetic-page-failure'); }
    } };
    await assert.rejects(importer.importEntries({ source: sourceFor(original.apiRows), target, tenant: A, pageSize: 2 }), /synthetic-page-failure/);
    assert.equal((await importer.importEntries({ source: sourceFor(original.apiRows), target, tenant: A, pageSize: 2 })).phase, 'done');
    assert.deepEqual(pages[0], pages[2]);
    assert.deepEqual(pages[1], pages[3]);
  });
  await check('actual importer history carries soft-delete marker to injected target', async () => {
    const source = sourceFor(original.apiRows.slice(0, 1));
    source.history = async ({ cursor }) => cursor < 10001
      ? { docs: [{ ...original.apiRows[0], isValid: false, srvModified: 10001 }], cursor: 10001 }
      : { docs: [], cursor };
    const pages = [];
    const result = await importer.importEntries({ source, target: { async writePage (docs) { pages.push(clone(docs)); } }, tenant: A, now: () => 10000 });
    assert.equal(result.historyCount, 1);
    assert.equal(pages[1][0].isValid, false);
  });
  await check('actual migration catalogue validates candidate checksums and rejects altered SQL', () => {
    const candidate = JSON.parse(fs.readFileSync(path.join(tree, 'migrations/candidates/postgres-entries-v1.json'), 'utf8'));
    const migrations = catalogue.validateCatalogue(candidate);
    assert.ok(migrations.length > 0);
    candidate.migrations[0].up[0] += ' ';
    assert.throws(() => catalogue.validateCatalogue(candidate), { code: 'MIG_CHECKSUM' });
  });
  const report = { scope: 'source-only research preflight; injected callbacks, no database/key recovery', head,
    fixtureSha256: crypto.createHash('sha256').update(fs.readFileSync(fixtureFile)).digest('hex'),
    control: control || null, checks,
    passing: checks.filter(c => c.ok).length, failing: checks.filter(c => !c.ok).length,
    unmeasured: ['real PG/Mongo restore', 'RLS wrong-tenant storage refusal', 'provider decryption/key recovery',
      'migration ledger restore and partial transaction rollback', 'snapshot consistency and natural ordering',
      'hard-delete recovery', 'resource/RPO/RTO bounds'] };
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  if (report.failing) process.exitCode = 1;
}
main().catch(error => { process.stderr.write((error.code || error.message) + '\n'); process.exitCode = 1; });
