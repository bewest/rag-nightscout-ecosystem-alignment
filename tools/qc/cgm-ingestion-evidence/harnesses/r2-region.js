// Repro 2: region/host selection, legacy vs connect-after-compat, for the
// BRIDGE_SERVER values an operator can actually have set today.
const {execFileSync} = require('child_process');
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const compat = require(CRM + '/lib/server/bridge-connect-compat.js');
const url = require('url');

const _known = { ous:'shareous1.dexcom.com', us:'share2.dexcom.com' };
function connect_base (spec) { // copy of connect base_for, exercised below against the real one too
  const server = spec.shareServer ? spec.shareServer : _known[spec.shareRegion || 'us'];
  return url.format({protocol:'https', host: server});
}

function legacy_host (bridgeServerEnv) {
  // resolved in a child process because share2nightscout-bridge freezes it at require() time
  const src = `process.env.BRIDGE_SERVER=${JSON.stringify(bridgeServerEnv === undefined ? '' : bridgeServerEnv)};`
    + (bridgeServerEnv === undefined ? 'delete process.env.BRIDGE_SERVER;' : '')
    + `const e=require(${JSON.stringify(CRM + '/node_modules/share2nightscout-bridge')});`
    + `process.stdout.write(e.Defaults.auth.split('/')[2]);`;
  return execFileSync(process.execPath, ['-e', src], {encoding:'utf8'});
}

const VALUES = [undefined, 'EU', 'eu', 'Eu', 'US', 'us', 'shareous1.dexcom.com', 'share2.dexcom.com', 'EU1', ''];
console.log('BRIDGE_SERVER'.padEnd(24), 'LEGACY host'.padEnd(26), 'CONNECT host after compat'.padEnd(28), 'SAME?');
for (const v of VALUES) {
  const env = { extendedSettings: { bridge: { userName:'u', password:'p' } } };
  if (v !== undefined) env.extendedSettings.bridge.server = v;
  const r = compat.applyBridgeToConnectCompatibility(env);
  const c = env.extendedSettings.connect;
  const lh = legacy_host(v);
  const ch = connect_base(c);
  const chost = ch.replace(/^https:\/\//,'').replace(/\/$/,'');
  console.log(String(v).padEnd(24), lh.padEnd(26), (chost + '  [region=' + (c.shareRegion||'-') + ' server=' + (c.shareServer||'-') + ']').padEnd(28), lh.toLowerCase()===chost.toLowerCase() ? 'yes' : '*** NO ***');
}
