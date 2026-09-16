'use strict';
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const SP='/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/e2';
const bridgeCompat = require(CRM+'/lib/server/bridge-connect-compat.js');   // on origin/dev
const mmCompat     = require(SP+'/mmconnect-connect-compat.parcel4.js');    // parcel 4 only
const mmplugin     = require(CRM+'/lib/plugins/mmconnect.js');

function env(mm, connect) { return { extendedSettings: { ...(mm?{mmconnect:mm}:{}), ...(connect?{connect}:{}) } }; }
const MM = { userName:'user', password:'pw', server:'EU', sgvLimit:36, interval:120000, storeRawData:true, verbose:true, maxRetryDuration:64 };

console.log('=== 1. origin/dev: is there ANY MiniMed auto-adoption? ===');
let e = env(MM, null);
console.log('applyBridgeToConnectCompatibility(mmconnect only) ->', JSON.stringify(bridgeCompat.applyBridgeToConnectCompatibility(e)));
console.log('env.extendedSettings after                        ->', JSON.stringify(e.extendedSettings));

console.log('\n=== 2. origin/dev: BF-45, does the legacy plugin stand down for Connect? ===');
for (const cn of [null, {source:'minimedcarelink', carelinkUsername:'u', carelinkPassword:'p', countryCode:'gb'}]) {
  const ev = env(MM, cn);
  const r = mmplugin.init(ev, {create(){}}, {create(){}}, null);
  console.log('connect=' + (cn?cn.source:'<none>') + '  mmconnect.init -> ' + (r ? 'RETURNS A RUNNER (legacy will poll)' : 'null'));
}

console.log('\n=== 3. parcel 4 shim: what it maps, and what it drops ===');
function run(label, mm, connect) {
  const ev = env(mm, connect);
  const r = mmCompat.applyMmconnectToConnectCompatibility(ev);
  console.log(label.padEnd(46), JSON.stringify(r));
  console.log(''.padEnd(46), 'connect ->', JSON.stringify(ev.extendedSettings.connect));
  return ev;
}
run('MMCONNECT only, no CONNECT_COUNTRY_CODE', MM, null);
run('MMCONNECT + countryCode gb', MM, {countryCode:'gb'});
run('MMCONNECT server=US', {...MM, server:'US'}, {countryCode:'us'});
run('MMCONNECT server=custom host', {...MM, server:'carelink.example.invalid'}, {countryCode:'gb'});
run('MMCONNECT + CONNECT_SOURCE=dexcomshare', MM, {countryCode:'gb', source:'dexcomshare'});
run('MMCONNECT + BRIDGE-style co-existence', MM, {countryCode:'gb', source:'minimedcarelink'});

console.log('\n=== 4. idempotence: apply twice ===');
const ev2 = env(MM, {countryCode:'gb'});
const a = mmCompat.applyMmconnectToConnectCompatibility(ev2);
const snap = JSON.stringify(ev2.extendedSettings.connect);
const b = mmCompat.applyMmconnectToConnectCompatibility(ev2);
console.log('first ', JSON.stringify(a));
console.log('second', JSON.stringify(b), ' identical connect object:', snap === JSON.stringify(ev2.extendedSettings.connect));

console.log('\n=== 5. half-failure: country missing -> is the partial mapping kept? ===');
const ev3 = env(MM, null);
const r3 = mmCompat.applyMmconnectToConnectCompatibility(ev3);
console.log('result   ', JSON.stringify(r3));
console.log('env after', JSON.stringify(ev3.extendedSettings));
console.log('=> credentials were built into a LOCAL copy and discarded; env untouched:',
  JSON.stringify(ev3.extendedSettings.connect) === undefined || ev3.extendedSettings.connect === undefined);

console.log('\n=== 6. settings the legacy plugin honours vs. what the shim carries over ===');
const legacyOpts = mmplugin.getOptions(env(MM, null));
console.log('legacy getOptions ->', JSON.stringify(legacyOpts));
const ev4 = env(MM, {countryCode:'gb'});
mmCompat.applyMmconnectToConnectCompatibility(ev4);
const carried = Object.keys(ev4.extendedSettings.connect);
console.log('shim writes       ->', JSON.stringify(carried));
console.log('DROPPED           ->', JSON.stringify(Object.keys(legacyOpts).filter(k => !carried.some(c => c.toLowerCase().includes(k.toLowerCase())))));
