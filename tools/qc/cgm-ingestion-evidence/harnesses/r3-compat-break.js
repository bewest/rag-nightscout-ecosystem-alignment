// Repro 3: break the auto-adoption shim. Synthetic settings only.
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const compat = require(CRM + '/lib/server/bridge-connect-compat.js');
function show (label, env, extra) {
  Object.assign(process.env, extra || {});
  const r = compat.applyBridgeToConnectCompatibility(env);
  // does bootevent then SKIP the legacy bridge?
  const es = env.extendedSettings;
  const skipsLegacy = !!(es.connect && es.connect.source === 'dexcomskip' ) ;
  const bootSkips = !!(es.connect && es.connect.source === 'dexcomshare' && es.bridge && !compat.bridgeUseLegacy(es.bridge));
  console.log(label);
  console.log('   result  :', JSON.stringify(r));
  console.log('   connect :', JSON.stringify(es.connect));
  console.log('   bootevent skips legacy bridge:', bootSkips);
  for (const k of Object.keys(extra||{})) delete process.env[k];
  return r;
}
const B = (o) => ({ extendedSettings: { bridge: Object.assign({userName:'acct-A', password:'pw-A'}, o) } });

show('1. plain bridge-only settings (the common case)', B());

// idempotency: run the same env twice
{
  const env = B();
  const r1 = compat.applyBridgeToConnectCompatibility(env);
  const snap1 = JSON.stringify(env.extendedSettings.connect);
  const r2 = compat.applyBridgeToConnectCompatibility(env);
  const snap2 = JSON.stringify(env.extendedSettings.connect);
  console.log('2. run twice on the same env');
  console.log('   r1', JSON.stringify(r1), 'r2', JSON.stringify(r2));
  console.log('   idempotent on the settings object:', snap1 === snap2, snap1);
  console.log('   NOTE: second run still reports migrated:true -> the operator warning prints again');
}

show('3. HALF-MIGRATED: connect account already set, password not',
  Object.assign(B(), {extendedSettings: {bridge:{userName:'acct-A',password:'pw-A'}, connect:{source:'dexcomshare', shareAccountName:'acct-B'}}}));

show('4. connect already fully configured for a DIFFERENT dexcom account',
  {extendedSettings:{bridge:{userName:'acct-A',password:'pw-A'}, connect:{source:'dexcomshare', shareAccountName:'acct-B', sharePassword:'pw-B'}}});

show('5. connect configured for a different SOURCE (librelinkup) + bridge set',
  {extendedSettings:{bridge:{userName:'acct-A',password:'pw-A'}, connect:{source:'librelinkup', linkUpUsername:'x', linkUpPassword:'y'}}});

show('6. bridge userName present, password MISSING', {extendedSettings:{bridge:{userName:'acct-A'}}});

show('7. opt-out via extendedSettings.bridge.useLegacy=true', B({useLegacy:true}));
show('8. opt-out via env DEXCOM_BRIDGE_USE_LEGACY=true', B(), {DEXCOM_BRIDGE_USE_LEGACY:'true'});
show('9. opt-out attempted with DEXCOM_BRIDGE_USE_LEGACY=1', B(), {DEXCOM_BRIDGE_USE_LEGACY:'1'});
show('10. opt-out attempted with BRIDGE_USE_LEGACY=true (extendedSettings.bridge.useLegacy coerced to boolean true by env.js)',
  B({useLegacy:true}));
show('11. env.js coercion: BRIDGE_USE_LEGACY=on -> useLegacy===true', B({useLegacy:true}));
show('12. UNEXPECTED VALUE: useLegacy is the STRING "true" (e.g. from IMPORT_CONFIG json)', B({useLegacy:'true'}));
show('13. UNEXPECTED VALUE: bridge.server is a Number (env.js coerces numeric strings)', B({server: 1}));
show('14. bridge.server null', B({server:null}));
