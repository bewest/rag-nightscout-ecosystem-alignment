// Repro 1: same synthetic vendor payload -> legacy entry vs connect entry.
// No network: 'request' is replaced before share2nightscout-bridge loads.
const Module = require('module');
const path = require('path');
const CRM = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';

const calls = [];
function fakeRequest (req, then) {
  calls.push({uri: req.uri, method: req.method, rejectUnauthorized: req.rejectUnauthorized, body: req.body});
  let body;
  if (/AuthenticatePublisherAccount/.test(req.uri)) body = 'ACCT-UUID-0000';
  else if (/LoginPublisherAccountById/.test(req.uri)) body = 'SESSION-UUID-1111';
  else if (/ReadPublisherLatestGlucoseValues/.test(req.uri)) body = VENDOR;
  else body = null;
  process.nextTick(() => then(null, {statusCode: 200}, body));
  return {};
}
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'request') return fakeRequest;
  return origLoad.apply(this, arguments);
};

// A synthetic Dexcom Share LatestGlucose response. Values invented.
const VENDOR = [
  { DT: '/Date(1757900100000-0700)/', ST: '/Date(1757900100000)/', WT: '/Date(1757900100000)/', Trend: 4, Value: 101 },
  { DT: '/Date(1757900400000-0700)/', ST: '/Date(1757900400000)/', WT: '/Date(1757900400000)/', Trend: 'FortyFiveUp', Value: 112 },
  { DT: '/Date(1757900700000-0700)/', ST: '/Date(1757900700000)/', WT: '/Date(1757900700000)/', Trend: 'NOT COMPUTABLE', Value: 40 }
];

const engine = require(path.join(CRM, 'node_modules/share2nightscout-bridge'));
const legacyEntries = [];
const opts = {
  login: { accountName: 'synthetic-account', password: 'synthetic-password' },
  fetch: { maxCount: 3, minutes: 15 },
  nightscout: { },
  maxFailures: 3,
  firstFetchCount: 3,
  callback: (err, entries) => { if (entries) legacyEntries.push(...entries); }
};
engine(opts);

setTimeout(() => {
  const connectSrc = require(path.join(CRM, 'node_modules/nightscout-connect/lib/sources/dexcomshare.js'));
  const fakeAxios = { create: () => ({ post: () => Promise.resolve({data: VENDOR}) }) };
  const impl = connectSrc({ shareAccountName: 'synthetic-account', sharePassword: 'synthetic-password' }, fakeAxios, {debug(){},error(){}});
  const connectOut = impl.transformGlucose(VENDOR).entries;

  console.log('--- legacy HTTP calls made for ONE engine() invocation ---');
  calls.forEach(c => console.log(' ', c.method, c.uri.replace(/\?.*/,''), 'rejectUnauthorized=' + c.rejectUnauthorized));
  console.log('legacy auth round-trips per engine() call:',
    calls.filter(c=>/Authenticate|Login/.test(c.uri)).length);

  console.log('\n--- entry-by-entry ---');
  for (let i=0;i<legacyEntries.length;i++) {
    const L = legacyEntries[i], C = connectOut[i];
    const keys = Array.from(new Set([...Object.keys(L), ...Object.keys(C)]));
    const diffs = keys.filter(k => JSON.stringify(L[k]) !== JSON.stringify(C[k]));
    console.log(`[${i}] legacy=${JSON.stringify(L)}`);
    console.log(`     connect=${JSON.stringify(C)}`);
    console.log(`     DIFFERING FIELDS: ${diffs.length ? diffs.join(',') : '(none)'}`);
  }
  console.log('\nlegacy key set :', JSON.stringify(Object.keys(legacyEntries[0])));
  console.log('connect key set:', JSON.stringify(Object.keys(connectOut[0])));
}, 200);
