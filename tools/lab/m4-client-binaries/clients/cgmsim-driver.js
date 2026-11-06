'use strict';
// cgmsim-lib driver for the M4 client-binary lab. Runs inside the client
// container; calls the pinned library's own upload/download/delete functions
// (externals/cgmsim-lib/dist) and prints one JSON line per step. The library
// hashes the secret itself (src/setupParams.ts) and swallows most errors after
// logging them, so the HTTP status is read by the lab's recording proxy, not here.
//
//   CGMSIM_LIB=<checkout> NS_URL=<url> API_SECRET=<plain> node cgmsim-driver.js <step>...
//   steps: upload-entry upload-devicestatus read-entries read-profiles read-activity delete-devicestatus

// Freeze only this synthetic driver's wall clock; the installed client code is unchanged.
const RealDate = Date;
const base = Number(process.env.M4_BASE);
if (Number.isFinite(base)) {
  global.Date = class extends RealDate { constructor (...args) { super(...(args.length ? args : [base])); } static now () { return base; } };
}
const lib = require(process.env.CGMSIM_LIB + '/dist/index.js');
const downloads = require(process.env.CGMSIM_LIB + '/dist/downloads.js');
const url = process.env.NS_URL;
const secret = process.env.API_SECRET === undefined ? '' : process.env.API_SECRET;
const now = Date.now();
const yesterday = new Date(now - 24 * 60 * 60 * 1000).toISOString();

const steps = {
  'upload-entry': () => lib.uploadEntries({ sgv: 118, direction: 'Flat' }, url, secret).then(() => ({ ok: true })),
  'upload-devicestatus': () => lib.uploadDeviceStatus({ created_at: yesterday, device: 'cgmsim',
    openaps: { openaps: { iob: 0.5, time: yesterday, basaliob: 0.1 } } }, url, secret).then(() => ({ ok: true })),
  'read-entries': () => downloads.downloadNightscoutEntries(url, secret, 10).then(rows => ({ ok: true, len: rows.length })),
  'read-profiles': () => downloads.downloadNightscoutProfiles(url, secret).then(rows => ({ ok: true, len: rows.length })),
  'read-activity': () => lib.loadActivity(url, secret, yesterday).then(rows => ({ ok: true, len: Array.isArray(rows) ? rows.length : null })),
  'delete-devicestatus': () => lib.deleteDeviceStatus(0, url, secret).then(() => ({ ok: true }))
};

(async () => {
  for (const name of process.argv.slice(2)) {
    if (!steps[name]) { console.log(JSON.stringify({ step: name, error: 'unknown step' })); process.exitCode = 2; continue; }
    try {
      const result = await steps[name]();
      console.log(JSON.stringify({ step: name, ...result }));
    } catch (error) {
      console.log(JSON.stringify({ step: name, ok: false, error: String(error && error.message || error).slice(0, 200) }));
    }
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
