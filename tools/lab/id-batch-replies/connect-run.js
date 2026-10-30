'use strict';
// Runs the REAL nightscout-connect Nightscout output (lib/outputs/nightscout.js
// of externals/nightscout-connect, pinned in clients.js) headless against a
// lab server, for a few cycles, the way its source loop drives it: each cycle
// hands record_batch() the source's records newer than the bookmark
// record_batch() left (the source reads `last_known` from that bookmark).
// Only the transport is wrapped: an axios interceptor adds the ID-BATCH
// opt-in to POSTs, so the server answers with the variant under test.
//
//   node connect-run.js <spec.json>   (NODE_PATH must reach axios and qs)
// spec: { connectDir, url, apiSecret, optIn, collection, cycles: [[records], ...] }
// A cycle's records are the source's records available at that cycle; the
// runner sends those newer than the bookmark. Prints one JSON result.

const path = require('path');
const axios = require('axios');

async function main ( ) {
  const spec = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
  const quiet = { debug ( ) { }, info ( ) { }, warn ( ) { }, error ( ) { }, log ( ) { } };
  const transport = {
    create (opts) {
      const inst = axios.create(opts);
      inst.interceptors.request.use(function optIn (config) {
        if (spec.optIn && config.method === 'post') config.headers['Nightscout-Write-Results'] = spec.optIn;
        return config;
      });
      inst.interceptors.response.use(function seen (resp) {
        if (resp.config.method === 'post') posts.push({ status: resp.status, length: Array.isArray(resp.data) ? resp.data.length : null });
        return resp;
      }, function failed (err) {
        if (err.config && err.config.method === 'post') posts.push({ status: err.response && err.response.status, length: null });
        return Promise.reject(err);
      });
      return inst;
    }
  };
  const posts = [];
  const output = require(path.join(spec.connectDir, 'lib/outputs/nightscout.js'))(
    { url: spec.url, apiSecret: spec.apiSecret, logger: quiet }, transport);
  const field = spec.collection === 'entries' ? 'dateString' : 'created_at';
  const key = spec.collection === 'entries' ? 'entries' : spec.collection === 'devicestatus' ? 'devicestatus' : 'treatments';
  let bookmark = await output.gap_for();
  const cycles = [];
  for (const available of spec.cycles) {
    const mark = bookmark[key] ? new Date(bookmark[key]).getTime() : 0;
    const send = available.filter(r => Date.parse(r[field]) > mark);
    const before = posts.length;
    let error = null;
    try {
      bookmark = await output({ [key]: send });
    } catch (err) {
      error = (err && (err.status || err.message)) || String(err);
    }
    cycles.push({ sent: send.map(r => r.idbTag), posts: posts.slice(before), error
      , bookmark: bookmark[key] ? new Date(bookmark[key]).toISOString() : null });
  }
  process.stdout.write(JSON.stringify({ cycles }) + '\n');
}

main().catch(err => { process.stdout.write(JSON.stringify({ crash: String(err && err.stack || err) }) + '\n'); process.exit(1); });
