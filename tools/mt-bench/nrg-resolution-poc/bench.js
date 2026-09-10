// Measures the actual cost of the resolution step nightscout-roles-gateway's
// find_expected_name (lib/policies/index.js:33-49) performs on every request: a
// hostname -> tenant/upstream lookup via a two-table LEFT JOIN over the network, versus
// the same lookup held in-process (a Map, as cgm-remote-monitor's own tenant-resolution
// middleware, §5.1/§9.1, would do it if folded into core instead of run as a sidecar).
//
// This is the concrete number behind §9.3's "every added hop is another place tenant
// identity must be correctly re-derived" argument, and directly informs "does a Node
// server scale with additional services, or do we fan out sidecars" for this specific
// piece: host/tenant resolution.
const knex = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15434, user: 'nrg_reader', password: 'poc', database: 'nrgpoc' },
  pool: { min: 2, max: 10 },
});

const N = 5000;

async function benchKnexJoin() {
  const names = [];
  for (let i = 0; i < N; i++) names.push('site-' + (1 + (i % 2000)) + '.example.com');
  const times = [];
  for (const expected_name of names) {
    const t0 = process.hrtime.bigint();
    // Mirrors find_expected_name exactly: LEFT JOIN, not a single-table PK lookup.
    await knex('registered_sites')
      .select('registered_sites.*', 'nightscout_authenticity_records.upstream_origin as confirmed_upstream',
               'nightscout_authenticity_records.status', 'nightscout_authenticity_records.acceptable')
      .leftJoin('nightscout_authenticity_records', 'nightscout_authenticity_records.expected_name', 'registered_sites.expected_name')
      .where('registered_sites.expected_name', expected_name);
    const t1 = process.hrtime.bigint();
    times.push(Number(t1 - t0) / 1e6);
  }
  return times;
}

async function benchInProcessMap() {
  // The alternative: this table loaded once into a Map<hostname, siteRow>, refreshed
  // on a change feed/poll, and consulted in-process — no network hop at all, the shape
  // §9.1 already proposed for tenant resolution folded into core.
  const rows = await knex('registered_sites')
    .select('registered_sites.*', 'nightscout_authenticity_records.upstream_origin as confirmed_upstream',
             'nightscout_authenticity_records.status', 'nightscout_authenticity_records.acceptable')
    .leftJoin('nightscout_authenticity_records', 'nightscout_authenticity_records.expected_name', 'registered_sites.expected_name');
  const map = new Map(rows.map(r => [r.expected_name, r]));

  const names = [];
  for (let i = 0; i < N; i++) names.push('site-' + (1 + (i % 2000)) + '.example.com');
  const times = [];
  for (const expected_name of names) {
    const t0 = process.hrtime.bigint();
    const row = map.get(expected_name); // eslint-disable-line no-unused-vars
    const t1 = process.hrtime.bigint();
    times.push(Number(t1 - t0) / 1e6);
  }
  return times;
}

function percentile(sorted, p) {
  const idx = Math.floor(sorted.length * p);
  return sorted[Math.min(idx, sorted.length - 1)];
}

function report(name, times) {
  const sorted = [...times].sort((a, b) => a - b);
  console.log(`  ${name}: p50=${percentile(sorted, 0.5).toFixed(4)}ms p99=${percentile(sorted, 0.99).toFixed(4)}ms (n=${times.length})`);
}

async function main() {
  console.log(`=== NRG-shaped host->tenant resolution, ${N} lookups over 2000 sites ===`);
  console.log('Sidecar shape (knex LEFT JOIN over the network, as NRG runs it today):');
  report('knex/postgres LEFT JOIN', await benchKnexJoin());

  console.log('In-core shape (loaded once, Map lookup, no network hop):');
  report('in-process Map', await benchInProcessMap());

  await knex.destroy();
}

main().catch((e) => { console.error(e); process.exit(1); });
