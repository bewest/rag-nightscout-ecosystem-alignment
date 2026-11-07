'use strict';
const ensure=(v,m)=>{if(!v)throw new Error(m);};
const canon=v=>JSON.stringify(v,(k,x)=>x&&!Array.isArray(x)&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(a=>[a,x[a]])):x);
const same=(a,b,m)=>ensure(canon(a)===canon(b),m);
const mean=v=>v?.result?.properties?.bgnow?.mean;
function acquiredBucket (value, physical, id) {
  const bg=value?.result?.properties?.bgnow;
  ensure(bg?.mean === 166.5 && bg.last === 222, 'EXPLICIT_ACQUISITION_FAILED');
  same(bg.sgvs.map(row=>[row._id,row.mgdl]).sort((a,b)=>a[0].localeCompare(b[0])),
    [[id,222],['preview-reading',111]].sort((a,b)=>a[0].localeCompare(b[0])), 'ACQUIRED_BUCKET_INPUT_MISMATCH');
  ensure(value.inputCheckpoint === physical.floor && value.result.checkpoint === physical.floor, 'ACQUIRED_CHECKPOINT_MISMATCH');
}
function physical(records, control) {
  const get = phase => records.find(r => r.phase === phase), starts = records.filter(r => r.phase === 'preview-startup');
  ensure(records.length === (control === 'listener' ? 1 : control ? 2 : 21), 'UNEXPECTED_RAW_OBSERVATION_COUNT');
  if (control === 'listener') {
    ensure(starts.length === 1 && starts[0].startup.ready === true && !starts[0].startup.bootError, 'BOOT_CONTROL_WRONG_LAYER');
    same(starts[0].startup.contexts, [], 'LISTENER_ONLY_ABLATION_DID_NOT_REMOVE_ROLE');
    ensure(starts[0].physical.A.tables.entries.length === 1 && starts[0].physical.B.tables.entries.length === 1,
      'BOOT_CONTROL_CURRENT_TABLES_NOT_REACHED'); return;
  }
  ensure(starts.length === (control ? 1 : 7), 'MISSING_ROLE_STARTUPS');
  for (const r of starts) {
    same(r.startup.contexts, ['evaluator'], 'WRONG_SELECTED_ROLE'); ensure(r.startup.servers === 0, 'UNEXPECTED_LISTENER');
    ensure(r.startup.health.tenants.length === 2 && r.startup.health.tenants.every(t => t.ready), 'INITIAL_ACQUISITION_SETUP_REFUSED');
  }
  if (!control) {
    const first = get('preview-first-result'); ensure(mean(first.first) === 111 && first.first.eligible, 'INITIAL_CLINICAL_OUTPUT');
    const restart = get('preview-cli-restart');
    ensure(restart.afterRestart.A.tables.entries.length === 0 && restart.afterRestart.A.checkpoint.projection.length === 1 &&
      restart.afterRestart.A.checkpoint.projection[0].domain === 'activity', 'CLI_RESTART_CURRENT_STATE');
    same(restart.beforeRestart.B, restart.afterRestart.B, 'RESTART_FOREIGN_CHANGED');
    ensure(restart.beforeRestart.A.floor === restart.afterRestart.A.floor && /Evaluator preview started/.test(restart.logs.stdout), 'ACTUAL_CLI_RESTART_NOT_REACHED');
  }
  if (!control || control === 'backstop') {
    const r = get('preview-backstop'); ensure(r.physical.A.tables.entries.length === 0 && r.physical.A.tables.activity[0].doc.steps === 2,
      'BACKSTOP_PHYSICAL_ABSENCE_ACTIVITY_NOT_REACHED');
    ensure(r.last.outputRevision >= r.afterWrites.outputRevision + 3, 'NO_POST_WRITE_JOB_PROGRESS');
    ensure(r.removed.events[0].event.stamp === null && r.activity.events[0].event.stamp === null && r.physical.A.floor === r.removed.before.floor,
      'CANONICAL_UNSTAMPED_DELETE_ACTIVITY_PRECONDITION');
    ensure(r.physical.A.checkpoint.projection.length === 1 && r.physical.A.checkpoint.projection[0].domain === (control ? 'entries' : 'activity'),
      'BACKSTOP_ABLATION_OR_RECOVERY_NOT_REACHED');
  }
  if (!control || control === 'time') {
    const r = get('preview-retained-time'); ensure(r.first.eligible && mean(r.first) === 111 && r.before.A.tables.entries.length === 2,
      'RETAINED_TIME_PRECONDITION');
    ensure(mean(r.tick) === (control ? 166.5 : 111), 'TIME_PATH_CONTROL_OR_POSITIVE_NOT_REACHED');
    ensure(r.tick.outputRevision > r.first.outputRevision, 'TIME_OUTPUT_REVISION_NOT_ADVANCED');
    if (control) acquiredBucket(r.tick, r.before.A, 'new-physical');
    if (!control) { same(r.before.A.checkpoint, r.after.A.checkpoint, 'TIME_TICK_ADVANCED_INPUT');
      const acquired=get('preview-time-acquired'); acquiredBucket(acquired.acquired, acquired.physical.A, 'new-physical');
      ensure(acquired.acquired.inputCheckpoint > r.first.inputCheckpoint, 'ACQUIRED_CHECKPOINT_NOT_ADVANCED'); }
    else ensure(r.after.A.checkpoint.projection.length === 2, 'TIME_ABLATION_DID_NOT_ACQUIRE_NEW_ROW');
  }
  if (!control || control === 'config') {
    const r = get('preview-config-identity'); ensure(r.first.eligible && r.expectedIdentity !== r.first.identity, 'CONFIG_CONTENT_CHANGE_NOT_REACHED');
    if (control) ensure(r.tick && r.tick.identity === r.first.identity && r.tick.eligible, 'CONFIG_ABLATION_DID_NOT_RETAIN_OLD_FRAME');
    else { ensure(r.tick === null, 'CONFIG_DID_NOT_DISCARD_RETAINED_FRAME');
      const disabled = get('preview-config-disabled'); ensure(disabled.current === false && disabled.last === null, 'DISABLED_CONFIG_STILL_ELIGIBLE'); }
  }
  if (!control) for (const kind of ['row', 'byte']) {
    const r = get('preview-refusal-' + kind);
    ensure(r.physical.A.tables.entries.length === 2 && r.refused.outputRevision === r.first.outputRevision && !r.refused.eligible,
      'TENANT_REFUSAL_DID_NOT_RETAIN_LAST_GOOD');
    same(r.physical.A.checkpoint, r.checkpoint, 'REFUSAL_ADVANCED_INPUT');
    ensure(r.b.eligible && mean(r.b) === 333, 'FOREIGN_TENANT_DID_NOT_PROGRESS');
  }
  if (!control || control === 'close') {
    const r = get('preview-close-fence'); ensure(r.physicalWhileHeld.A.tables.entries.length === 2 && r.health.closed && r.finished,
      'HELD_REAL_READ_SHUTDOWN_NOT_REACHED');
    ensure(r.last.outputRevision === r.first.outputRevision + (control ? 1 : 0) && mean(r.last) === (control ? 166.5 : 111) && !r.last.eligible,
      'SHUTDOWN_FENCE_CONTROL_OR_POSITIVE_NOT_REACHED');
    if (control) acquiredBucket(r.last, r.physicalWhileHeld.A, 'pending-new');
  }
  if (!control) {
    const refused = records.filter(r => r.phase === 'preview-unsafe-grant'); ensure(refused.length === 4, 'MISSING_ACTUAL_UNSAFE_GRANTS');
    for (const r of refused) { ensure(r.allowed === true && r.startup.bootError?.previewConfigError === true &&
        r.startup.bootError.message === 'evaluator preview readiness or initialization refused' &&
        !Object.hasOwn(r.startup, 'ready'), 'UNSAFE_GRANT_NOT_PHYSICAL_OR_REFUSED');
      same(r.before, r.after, 'REFUSED_STARTUP_MUTATED_STATE'); }
  }
}
module.exports=(records,control)=>physical(records,control);
