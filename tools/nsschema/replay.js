#!/usr/bin/env node
/**
 * replay.js — measure what a strictness policy would actually cost.
 *
 * Compiles each generated JSON Schema with Ajv and replays the real corpus
 * through it, reporting per collection, per policy and per site:
 *
 *   - the share of live documents the validator would REJECT
 *   - which fields caused the rejections, ranked
 *   - for the strip-unknown reading of a strict policy, how many field
 *     values would be DROPPED rather than rejected
 *   - throughput, in documents per second, on compiled validators
 *
 * "Strict vs permissive" is not a style preference: on this corpus the
 * difference is measured in millions of rejected or silently discarded
 * values. Run it, do not guess.
 *
 * Usage:
 *   node tools/nsschema/replay.js --out reports/schema-census/impact.json
 *   node tools/nsschema/replay.js --max-docs 20000       (smoke run)
 */

'use strict';

const fs = require('fs');
const path = require('path');
// The default Ajv export is draft-07; the generated schemas declare 2020-12.
const Ajv = require('ajv/dist/2020');
const addFormats = require('ajv-formats');

const ROOT = path.resolve(__dirname, '..', '..');
const SCHEMA_DIR = path.join(ROOT, 'specs', 'jsonschema', 'generated');
const COLLECTIONS = ['entries', 'treatments', 'devicestatus', 'profile'];
const PROFILES = ['write', 'read'];
const STRICTNESS = ['permissive', 'tolerant', 'extension-bag', 'strict'];

const SNAPSHOTS = [
  { id: '2026-04-01', root: 'externals/ns-data/patients', layout: 'site_dir' },
  { id: '2026-04-26', root: 'externals/ns-resync-2026-04-26/raw', layout: 'flat_site' },
];

function discover(collection) {
  const out = [];
  for (const snap of SNAPSHOTS) {
    const root = path.join(ROOT, snap.root);
    if (!fs.existsSync(root)) continue;
    for (const site of fs.readdirSync(root).sort()) {
      const base = snap.layout === 'site_dir'
        ? path.join(root, site, 'raw')
        : path.join(root, site);
      const file = path.join(base, `${collection}.json`);
      if (fs.existsSync(file) && fs.statSync(file).size > 0) {
        out.push({ snapshot: snap.id, site, file });
      }
    }
  }
  return out;
}

/** Documents from one Nightscout REST response file. */
function readDocs(file) {
  const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  return Array.isArray(parsed) ? parsed : [parsed];
}

/** Top-level keys of `doc` that the schema does not name. */
function unknownTopLevel(doc, known) {
  let n = 0;
  for (const k of Object.keys(doc)) if (!known.has(k)) n += 1;
  return n;
}

function errorField(err) {
  const p = err.instancePath || '';
  if (err.keyword === 'required') {
    return `${p}/${err.params.missingProperty}`.replace(/^\//, '');
  }
  if (err.keyword === 'additionalProperties') {
    return `${p}/${err.params.additionalProperty}`.replace(/^\//, '');
  }
  return p.replace(/^\//, '') || '(document)';
}

function main() {
  const args = process.argv.slice(2);
  const outIdx = args.indexOf('--out');
  const outPath = outIdx >= 0 ? args[outIdx + 1] : 'reports/schema-census/impact.json';
  const maxIdx = args.indexOf('--max-docs');
  const maxDocs = maxIdx >= 0 ? parseInt(args[maxIdx + 1], 10) : Infinity;

  const ajv = new Ajv({ allErrors: true, strict: false, allowUnionTypes: true });
  addFormats(ajv);

  const results = { generated_by: 'tools/nsschema/replay.js', ajv: require('ajv/package.json').version, collections: {} };

  for (const collection of COLLECTIONS) {
    const sources = discover(collection);
    if (!sources.length) continue;

    const validators = {};
    const knownKeys = {};
    for (const profile of PROFILES) {
      for (const strictness of STRICTNESS) {
        const key = `${profile}/${strictness}`;
        const file = path.join(SCHEMA_DIR, `${collection}.${profile}.${strictness}.schema.json`);
        const schema = JSON.parse(fs.readFileSync(file, 'utf8'));
        validators[key] = ajv.compile(schema);
        knownKeys[key] = new Set(Object.keys(schema.properties || {}));
      }
    }

    const policies = {};
    for (const key of Object.keys(validators)) {
      policies[key] = {
        documents: 0, rejected: 0,
        rejected_by_site: {}, documents_by_site: {},
        error_fields: {}, error_keywords: {},
        unknown_values_dropped: 0, documents_with_unknown: 0,
        elapsed_ms: 0,
      };
    }

    let total = 0;
    for (const src of sources) {
      const docs = readDocs(src.file).slice(0, maxDocs);
      total += docs.length;
      for (const key of Object.keys(validators)) {
        const v = validators[key];
        const p = policies[key];
        const known = knownKeys[key];
        const t0 = process.hrtime.bigint();
        for (const doc of docs) {
          p.documents += 1;
          p.documents_by_site[src.site] = (p.documents_by_site[src.site] || 0) + 1;
          const dropped = unknownTopLevel(doc, known);
          if (dropped) {
            p.unknown_values_dropped += dropped;
            p.documents_with_unknown += 1;
          }
          if (!v(doc)) {
            p.rejected += 1;
            p.rejected_by_site[src.site] = (p.rejected_by_site[src.site] || 0) + 1;
            const seen = new Set();
            for (const err of v.errors) {
              const f = errorField(err);
              const sig = `${f}|${err.keyword}`;
              if (seen.has(sig)) continue;
              seen.add(sig);
              p.error_fields[f] = (p.error_fields[f] || 0) + 1;
              p.error_keywords[err.keyword] = (p.error_keywords[err.keyword] || 0) + 1;
            }
          }
        }
        p.elapsed_ms += Number(process.hrtime.bigint() - t0) / 1e6;
      }
    }

    for (const [key, p] of Object.entries(policies)) {
      p.rejection_rate = p.documents ? p.rejected / p.documents : 0;
      p.docs_per_second = p.elapsed_ms ? Math.round(p.documents / (p.elapsed_ms / 1000)) : null;
      p.elapsed_ms = Math.round(p.elapsed_ms);
      p.top_error_fields = Object.entries(p.error_fields)
        .sort((a, b) => b[1] - a[1]).slice(0, 15)
        .map(([field, count]) => ({ field, count, share_of_documents: count / p.documents }));
      delete p.error_fields;
      p.rejection_rate_by_site = {};
      for (const [site, n] of Object.entries(p.documents_by_site)) {
        p.rejection_rate_by_site[site] = (p.rejected_by_site[site] || 0) / n;
      }
    }

    results.collections[collection] = { documents: total, sources: sources.length, policies };
    const line = Object.entries(policies)
      .map(([k, p]) => `${k}=${(p.rejection_rate * 100).toFixed(1)}%`).join('  ');
    console.log(`${collection.padEnd(13)} ${total.toLocaleString().padStart(9)} docs   ${line}`);
  }

  const dest = path.join(ROOT, outPath);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, JSON.stringify(results, null, 1) + '\n');
  console.log(`-> ${outPath}`);
}

main();
