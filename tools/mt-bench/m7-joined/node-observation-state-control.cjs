'use strict';
// Exercise cached runtime diagnostics proof on an explicitly selected source.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const core = process.argv[2];
const file = path.resolve(core, 'lib/diagnostics/m7.js');
const helper = path.resolve(__dirname, 'node-observation-preload.cjs');
const child = String.raw`
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { diagnosticsState } = require(process.argv[2]);
const file = process.argv[3], root = process.argv[4], mode = process.argv[5];
const value = require(file);
const original = require.cache[file].exports;
async function main() {
 const client = {query: async () => 17};
 class Pool extends EventEmitter { constructor(){super();this.totalCount=1;this.idleCount=0;this.waitingCount=0;} async connect(){return client;} async end(){} }
 const pool = new Pool(), connect = pool.connect, query = client.query;
 value.observePool(pool, 'storage'); await pool.connect();
 assert.equal(pool.connect !== connect, mode === 'on'); assert.equal(client.query !== query, mode === 'on');
 const config = { diagnosticsMode: mode };
 const normal = diagnosticsState(config, root); assert.equal(normal.status,'VERIFIED');
 require.cache[file].exports = {...original,enabled: !original.enabled};
 const broken = diagnosticsState(config, root); assert.equal(broken.reason,'M7_NODE_DIAGNOSTICS_SELECTION_MISMATCH');
 require.cache[file].exports = original;
 const restored = diagnosticsState(config, root); assert.deepEqual(restored,normal);
 value.close(); process.stdout.write(JSON.stringify({mode,normal,broken,restored,actualQueryWrapped:client.query!==query}));
}
main().catch(error=>{value.close();console.error(error);process.exitCode=1});
`;
const results = [];
for (const mode of ['on', 'off', 'on']) {
 const output = execFileSync(process.execPath, ['-e', child, 'control', helper, file, path.resolve(core), mode],
   {env:{...process.env,NS_M7_DIAGNOSTICS:mode==='on'?'1':'0',NS_M7_DIAGNOSTICS_INTERVAL_MS:'60000'},encoding:'utf8',timeout:10000});
 results.push(JSON.parse(output));
}
assert.equal(results[0].actualQueryWrapped,true);assert.equal(results[1].actualQueryWrapped,false);assert.equal(results[2].actualQueryWrapped,true);
process.stdout.write(JSON.stringify({status:'PASS',node:process.version,results})+'\n');
