#!/usr/bin/env node
'use strict';
/*
 * analyze.js - compare a source and its sinks FROM MONGO, plus the writer's
 * ledger and the sampler's first-seen log.
 *
 * Environment:
 *   SOURCE    mongodb URL of the source database
 *   SINKS     comma list name=mongoURL=firstFetchISO
 *             firstFetchISO is when the sink's connector first read the
 *             source (from the proxy log); records older than 48 h before it
 *             are outside the connector's initial window and are not expected.
 *   LEDGER    writer ledger (JSONL)
 *   SEEN_DIR  directory with seen-<name>.jsonl from sampler.js
 *   EXCLUDE   optional file of soakIds (one per line) that are expected to
 *             differ (e.g. records the soak deliberately updated or deleted);
 *             they are reported separately, never silently dropped.
 *   SAMPLE    field-diff sample size per collection (default: every record
 *             present on both sides; an ablation showed a 100-record sample
 *             can miss a changed field)
 *   INFLIGHT_MIN  a missing record the source acknowledged less than this
 *             many minutes ago is reported as in flight, not as lost (45)
 * Prints one JSON document.
 */
const fs = require('fs');
const { MongoClient } = require('mongodb');

const COLLS = { entries: 'date', treatments: 'created_at', devicestatus: 'created_at', profile: null };
const NATKEY = { entries: (d) => d.date + '|' + d.type, treatments: (d) => d.created_at + '|' + d.eventType,
  devicestatus: (d) => d.created_at + '|' + d.device, profile: (d) => String(d._id) };
const SAMPLE = process.env.SAMPLE ? Number(process.env.SAMPLE) : Infinity;
const INFLIGHT = Number(process.env.INFLIGHT_MIN || 45) * 60000;
const WINDOW = 48 * 3600 * 1000;
const tms = (v) => (typeof v === 'number' ? v : Date.parse(v));

function readJsonl (f) { return fs.existsSync(f) ? fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []; }
function pct (xs, p) { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; }
function stable (v) { return JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x) ? Object.keys(x).sort().reduce((o, kk) => { o[kk] = x[kk]; return o; }, {}) : x)); }

(async () => {
  const exclude = new Set(process.env.EXCLUDE && fs.existsSync(process.env.EXCLUDE) ? fs.readFileSync(process.env.EXCLUDE, 'utf8').split('\n').filter(Boolean) : []);
  const ledger = readJsonl(process.env.LEDGER);
  const byId = new Map(ledger.map((r) => [r.soakId + '|' + r.coll, r]));
  const src = new MongoClient(process.env.SOURCE); await src.connect();
  const sdb = src.db();
  const report = { at: new Date().toISOString(), ledger_records: ledger.length, excluded: [...exclude], sinks: {} };
  const sdocs = {};
  for (const c of Object.keys(COLLS)) sdocs[c] = await sdb.collection(c).find({}).toArray();
  report.source = Object.fromEntries(Object.entries(sdocs).map(([c, d]) => [c, { count: d.length, soak: d.filter((x) => x.soakId).length }]));
  // The ledger is what the source acknowledged; the source must hold all of it.
  report.source.ledger_not_in_source = ledger.filter((r) => !sdocs[r.coll === 'profile' ? 'profile' : r.coll].some((d) => d.soakId === r.soakId) && !exclude.has(r.soakId)).length;

  for (const spec of process.env.SINKS.split(',')) {
    const [name, url, first] = spec.split('=');
    const cutoff = Date.parse(first) - WINDOW;
    const cli = new MongoClient(url); await cli.connect();
    const kdb = cli.db();
    const seen = new Map(readJsonl(`${process.env.SEEN_DIR}/seen-${name}.jsonl`).map((r) => [r.soakId + '|' + r.coll, Date.parse(r.firstSeen)]));
    const ackAge = (d, c) => { const l = byId.get(d.soakId + '|' + c); return l && l.kind === 'live' ? Date.now() - Date.parse(l.storedAt) : Infinity; };
    const out = { first_fetch: first, window_cutoff: new Date(cutoff).toISOString() };
    for (const [c, field] of Object.entries(COLLS)) {
      const kd = await kdb.collection(c).find({}).toArray();
      const sById = new Map(sdocs[c].filter((d) => d.soakId).map((d) => [d.soakId, d]));
      const kIds = kd.filter((d) => d.soakId).map((d) => d.soakId);
      const kSet = new Set(kIds);
      const expected = [...sById.values()].filter((d) => !field || tms(d[field]) > cutoff);
      const missing = expected.filter((d) => !kSet.has(d.soakId));
      const extra = [...kSet].filter((id) => !sById.has(id));
      const idCount = new Map(); kIds.forEach((id) => idCount.set(id, (idCount.get(id) || 0) + 1));
      const natCount = new Map(); kd.forEach((d) => { const k = NATKEY[c](d); natCount.set(k, (natCount.get(k) || 0) + 1); });
      // Field-level diff on a deterministic sample of records present on both sides.
      const both = expected.filter((d) => kSet.has(d.soakId) && !exclude.has(d.soakId));
      const step = Number.isFinite(SAMPLE) ? Math.max(1, Math.floor(both.length / SAMPLE)) : 1;
      const diffs = {}; let sampled = 0; const idRel = {};
      const kById = new Map(kd.filter((d) => d.soakId).map((d) => [d.soakId, d]));
      for (let i = 0; i < both.length && sampled < SAMPLE; i += step, sampled++) {
        const s = both[i], k = kById.get(s.soakId);
        const rel = (String(s._id) === String(k._id) ? 'same-value' : 'different-value') + '/' + (k._id && k._id.constructor ? k._id.constructor.name : typeof k._id);
        idRel[rel] = (idRel[rel] || 0) + 1;
        const keys = new Set([...Object.keys(s), ...Object.keys(k)]);
        keys.delete('_id');
        for (const key of keys) if (stable(s[key]) !== stable(k[key])) diffs[key] = (diffs[key] || 0) + 1;
      }
      // Lag: ledger acknowledgement -> first sampler observation in the sink.
      const lags = [], lateLags = [];
      for (const d of expected) {
        const l = byId.get(d.soakId + '|' + c); const s = seen.get(d.soakId + '|' + c);
        // Only records the source acknowledged after this sink's first fetch:
        // earlier ones measure when the sink was started, not sync lag.
        if (!l || l.kind !== 'live' || s === undefined || Date.parse(l.storedAt) < Date.parse(first)) continue;
        (l.late ? lateLags : lags).push((s - Date.parse(l.storedAt)) / 1000);
      }
      // sgv gaps in the sink that the source does not have.
      let gaps = [];
      if (c === 'entries') {
        const sg = new Set(sdocs.entries.filter((d) => d.type === 'sgv' && d.date > cutoff).map((d) => d.date));
        const kg = kd.filter((d) => d.type === 'sgv').map((d) => d.date).sort((a, b) => a - b);
        for (let i = 1; i < kg.length; i++) {
          if (kg[i] - kg[i - 1] > 330000) {
            const inSource = [...sg].filter((t) => t > kg[i - 1] && t < kg[i]).length;
            if (inSource) gaps.push({ from: new Date(kg[i - 1]).toISOString(), to: new Date(kg[i]).toISOString(), source_has: inSource });
          }
        }
      }
      out[c] = {
        source: sdocs[c].length, sink: kd.length, expected: expected.length,
        missing: missing.filter((d) => !exclude.has(d.soakId)).length,
        missing_in_flight: missing.filter((d) => !exclude.has(d.soakId) && ackAge(d, c) < INFLIGHT).length,
        missing_stale: missing.filter((d) => !exclude.has(d.soakId) && !(ackAge(d, c) < INFLIGHT)).length,
        missing_ids: missing.filter((d) => !exclude.has(d.soakId)).slice(0, 20).map((d) => d.soakId),
        missing_excluded: missing.filter((d) => exclude.has(d.soakId)).map((d) => d.soakId),
        extra_not_in_source: extra.filter((id) => !exclude.has(id)).length, extra_excluded: extra.filter((id) => exclude.has(id)).length, extra_ids: extra.filter((id) => !exclude.has(id)).slice(0, 20),
        dup_soakId: [...idCount.values()].filter((n) => n > 1).length,
        dup_natural_key: [...natCount.values()].filter((n) => n > 1).length,
        no_soakId: kd.filter((d) => !d.soakId).length,
        field_diff_sampled: sampled, field_diffs: diffs, id_relation: idRel,
        lag_s: { n: lags.length, p50: pct(lags, 0.5), p95: pct(lags, 0.95), max: lags.length ? Math.max(...lags) : null },
        late_lag_s: { n: lateLags.length, max: lateLags.length ? Math.max(...lateLags) : null },
        ...(c === 'entries' ? { sgv_gaps_source_has: gaps } : {})
      };
      // Records the soak changed on purpose: what does the sink hold for them?
      if (exclude.size) {
        out[c].excluded_state = [...exclude].filter((id) => sById.has(id) || kSet.has(id)).map((id) => {
          const s = sById.get(id), k = kById.get(id);
          const d = {};
          if (s && k) for (const key of new Set([...Object.keys(s), ...Object.keys(k)])) if (key !== '_id' && stable(s[key]) !== stable(k[key])) d[key] = { source: s[key], sink: k[key] };
          return { soakId: id, in_source: Boolean(s), in_sink: Boolean(k), differs: d };
        });
      }
    }
    report.sinks[name] = out;
    await cli.close();
  }
  await src.close();
  console.log(JSON.stringify(report, null, 1));
})().catch((err) => { console.error(err); process.exit(1); });
