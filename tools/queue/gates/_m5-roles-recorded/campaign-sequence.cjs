'use strict';
// Consumed fresh-all boundary: production-composition changes forbid prior-phase reuse.
const assert=require('node:assert/strict');
module.exports=m=>{
 assert.equal(m.campaignMode,'fresh-all','FRESH_ALL_MODE_REQUIRED');
 assert.equal(m.retainedInitialRecovery,null,'HISTORICAL_RECOVERY_REUSE_FORBIDDEN');
 assert.deepEqual(m.phases,['joined-role-recovery','joined-data-parity','joined-consumer-handoff','joined-consumer-plugin-ack','joined-socket-epoch','joined-browser-consumer'],'EXACT_SIX_PHASES_REQUIRED');
 assert.equal(m.controls.length,6,'EXACT_SIX_CONTROLS_REQUIRED');
 assert.equal(new Set(m.controls.map(c=>c.id)).size,6,'CONTROL_IDS_UNIQUE');
 for(const c of m.controls)assert(m.phases.includes(c.phase),'CONTROL_PHASE_REQUIRED');
 return [...m.phases.map(phase=>({phase,id:'ordinary-'+phase})),...m.controls.map(control=>({phase:control.phase,id:control.id,control})),...m.phases.map(phase=>({phase,id:'restored-'+phase}))];
};
