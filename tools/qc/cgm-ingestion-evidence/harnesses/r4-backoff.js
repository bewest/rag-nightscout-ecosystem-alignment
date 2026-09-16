// Repro 4: three-way retry/backoff comparison. No network.
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const NC='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect';
const {execFileSync} = require('child_process');
const fs=require('fs');
const os=require('os');
const path=require('path');

const pinned = require(CRM + '/node_modules/nightscout-connect/lib/backoff.js');  // == the tarball dev pins today
// v0.0.14 backoff (== fix/connect-timer-jitter c1cce2a)
const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'bo-'));
fs.writeFileSync(path.join(tmp,'fixed.js'), execFileSync('git',['-C',NC,'show','v0.0.14:lib/backoff.js'],{encoding:'utf8'}));
const fixed = require(path.join(tmp,'fixed.js'));

// What the Dexcom source actually asks for (lib/sources/dexcomshare.js, both versions):
const CYCLE_CFG = { interval_ms: 2.5*60*1000 };
const EXPECTED = 5*60*1000;
// builder.js applies the ceilings only in v0.0.14; the pinned builder passes cfg.*.backoff straight in.
const pinnedCycle = pinned(CYCLE_CFG);
const pinnedFrame = pinned(CYCLE_CFG);
const fixedCycle  = fixed({ max_interval_ms: EXPECTED*6, ...CYCLE_CFG, jitter:'none' });
const fixedFrame  = fixed({ max_interval_ms: EXPECTED,   ...CYCLE_CFG, jitter:'none' });

function ms(n){ if(n<1000) return n+' ms'; if(n<60000) return (n/1000).toFixed(1)+' s'; if (n<3600000) return (n/60000).toFixed(1)+' min'; return (n/3600000).toFixed(1)+' h'; }
console.log('consecutive-failure ladder, Dexcom Share (source asks interval_ms=150000)');
console.log('attempt | PINNED cycle | PINNED frame | v0.0.14 cycle (max 30m) | v0.0.14 frame (max 5m)');
for (let n=0;n<=12;n++){
  console.log(String(n).padStart(7),'|',ms(pinnedCycle(n)).padStart(12),'|',ms(pinnedFrame(n)).padStart(12),'|',ms(fixedCycle(n)).padStart(23),'|',ms(fixedFrame(n)).padStart(21));
}
console.log('\npinned backoff option merge (the BF-34 defect) — caller asks 150000 ms, gets:', pinnedCycle(1), 'ms at attempt 1');
console.log('v0.0.14 at attempt 1, no jitter:', fixedCycle(1), 'ms');
console.log('ratio:', (fixedCycle(1)/pinnedCycle(1)).toFixed(0)+'x');

// legacy: no backoff at all — the poll gate is a constant
const bridge = require(CRM + '/lib/plugins/bridge.js');
const o = bridge.options({extendedSettings:{bridge:{userName:'u',password:'p'}}});
console.log('\nLEGACY bridge, computed from lib/plugins/bridge.js options():');
console.log('  poll interval:', ms(o.interval), '(constant; there is no backoff term anywhere in bridge.js or share2nightscout-bridge)');
console.log('  maxFailures  :', o.maxFailures);
// show interval clamp
for (const v of [500, 1000, 156000, 300000, 300001, 'abc']) {
  const oo = bridge.options({extendedSettings:{bridge:{userName:'u',password:'p',interval:v}}});
  console.log('   BRIDGE_INTERVAL=' + String(v).padEnd(8), '-> interval', ms(oo.interval));
}
