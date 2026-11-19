'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { stats } = require('./durable-lag.cjs');
const contract = 'clinical-deadline-from-warm-v1';
const deadlineMs = 120000;

function source(file, directory) {
  let rows = {}, last, until = null, requested = false;
  return {
    refresh() {
      if (directory && until === null) {
        try { until = JSON.parse(fs.readFileSync(path.join(directory,'clinical-tail-clock.json'))).untilMonoMs; }
        catch { /* The normal runner supplies the original clock as its drain starts. */ }
      }
      try {
        const stamp = fs.statSync(file, {bigint:true}).mtimeNs;
        if (stamp !== last) {
          const packet = JSON.parse(fs.readFileSync(file, 'utf8'));
          rows = packet.contract === contract ? packet.byTenant : {};
          last = stamp;
        }
      } catch { rows = {}; last = undefined; }
    },
    row(tenant) { return rows[tenant]; },
    inTail() { return Number.isFinite(until); },
    timeLeftMs() { return until === null ? Infinity : until - Number(process.hrtime.bigint())/1e6; },
    needsObservation(witnesses) {
      const need = this.inTail() && witnesses.some(w => Number.isFinite(w.acceptedMono) &&
        !w.hardClinical && !Number.isFinite(rows[w.tenant]?.warmByMs) && !rows[w.tenant]?.sourceChanged);
      if (need !== requested && directory) {
        const marker = path.join(directory, 'clinical-tail-needs-warm');
        if (need) fs.writeFileSync(marker, '', {mode:0o600});
        else fs.rmSync(marker, {force:true});
        requested = need;
      }
      return need && this.timeLeftMs() > 0;
    },
  };
}

// Runtime inspection and the local probe share the workstation monotonic clock.
// The first warm observation is an upper bound, not an exact transition time.
// Use the last proven cold read for PASS and the first warm read for FAIL.
function assess(w, frames, row) {
  const accepted = Number.isFinite(w.acceptedMono) && Number.isFinite(w.acceptedHostMs);
  const durable = w.durableObservation;
  const wanted = new Set(w.expectedSockets);
  const matched = frames.filter(f => durable && wanted.has(f.socket) && f.sgv._id === durable.storedId &&
    f.sgv.mills === w.date && Number.isFinite(durable.storedSgv) && f.sgv.mgdl === durable.storedSgv &&
    Number.isSafeInteger(f.connects) && f.connects > 0 && typeof f.transportId === 'string' && f.transportId.length &&
    Number.isFinite(f.atMono) && f.atMono >= w.sentMono);
  const acceptanceToCompletionMs = accepted && durable ?
    w.sentMono + durable.upperMs - w.acceptedMono : null;
  // The frame can arrive before the HTTP acknowledgement. Keep the signed delay.
  const acceptanceToFrameMs = accepted ? matched.map(f => f.atMono - w.acceptedMono) : [];
  const valid = row && !row.sourceChanged && Number.isFinite(row.warmByMs);
  const delay = w.semantic?.ready && acceptanceToCompletionMs !== null ?
    Math.max(acceptanceToCompletionMs, ...acceptanceToFrameMs) : null;
  const earliest = Math.max(0, (row?.coldThroughMs ?? -Infinity) - w.acceptedHostMs);
  const latest = valid ? Math.max(0, row.warmByMs - w.acceptedHostMs) : null;
  let verdict = 'UNMEASURED', code = 'M7_CLINICAL_WARM_UNMEASURED';
  if (w.evaluatedAt === -1) { verdict = 'FAIL'; code = 'M7_CLINICAL_WRITE_REFUSED'; }
  else if (!accepted) { code = 'M7_CLINICAL_ACCEPTANCE_UNMEASURED'; }
  else if (w.hardClinical) { verdict = 'FAIL'; code = w.hardClinical; }
  else if (valid) {
    if (delay !== null && delay < earliest + deadlineMs) { verdict = 'PASS'; code = null; }
    else if (delay !== null && delay >= latest + deadlineMs ||
             Number.isFinite(w.lastCheckedMono) && w.lastCheckedMono - w.acceptedMono >= latest + deadlineMs &&
             !w.semantic?.ready) { verdict = 'FAIL'; code = 'M7_COMPLETION_DEADLINE'; }
    else { code = delay === null ? 'M7_CLINICAL_OBSERVATION_INCOMPLETE' : 'M7_CLINICAL_TRANSITION_INTERVAL'; }
  }
  const nominalMiss = !accepted ? null : delay !== null ? delay >= deadlineMs :
    Number.isFinite(w.lastCheckedMono) && w.lastCheckedMono-w.acceptedMono >= deadlineMs ? true : null;
  let preWarmDeadlineMiss = null;
  if (nominalMiss === false) preWarmDeadlineMiss = false;
  if (nominalMiss && row && !row.sourceChanged) {
    if (Number.isFinite(row.coldThroughMs) && row.coldThroughMs >= w.acceptedHostMs + deadlineMs)
      preWarmDeadlineMiss = true;
    else if (valid && row.warmByMs <= w.acceptedHostMs + deadlineMs) preWarmDeadlineMiss = false;
  }
  return {verdict, code, accepted, acceptanceToCompletionMs, acceptanceToFrameMs,
    expectedFrames: w.expectedSockets.length, matchedFrames: matched.length,
    durableObserved: !!durable, semanticReady: !!w.semantic?.ready,
    nominalMiss, preWarmDeadlineMiss,
    acceptedMono: w.acceptedMono ?? null, acceptedHostMs: w.acceptedHostMs ?? null,
    warmAfterAcceptanceMs: latest === null ? null : {lower:earliest,upper:latest}};
}

function shouldPoll(w, row, writing, now, source) {
  if (source?.timeLeftMs() <= 0) return false;
  if (!Number.isFinite(w.acceptedHostMs)) return writing;
  if (!row || row.sourceChanged || !Number.isFinite(row.warmByMs)) {
    return writing || source?.inTail() || now - w.acceptedMono < deadlineMs;
  }
  const ends = w.acceptedMono + Math.max(0, row.warmByMs - w.acceptedHostMs) + deadlineMs;
  return now < ends || !(w.lastQueryStartMono >= ends);
}

function observe(w, result, now) {
  w.semantic = result;
  w.lastCheckedMono = now;
  // Missing evidence cannot establish a deadline miss. A checked negative
  // result for a stored/output/frame witness can.
  const pending = ['M7_COMPLETION_PENDING','M7_COMPLETION_OUTPUT_CLOCK','M7_COMPLETION_FRAME',
    'M7_COMPLETION_BG_NOW','M7_COMPLETION_STORED','M7_COMPLETION_CLIENT'];
  const unverifiable = ['M7_COMPLETION_READER_MISMATCH','M7_COMPLETION_BINDING','M7_COMPLETION_TYPED_STATE',
    'M7_COMPLETION_CLOCK','M7_COMPLETION_STATE'];
  if (!result.ready && unverifiable.includes(result.code)) w.lastCheckedMono = null;
  else if (!result.ready && (!pending.includes(result.code) || result.clientFailure &&
      !['M7_CLIENT_COUNT'].includes(result.clientFailure))) w.hardClinical = result.clientFailure || result.code;
}

function summary(witnesses) {
  const timings = witnesses.map(w => w.clinicalTiming);
  return {contract, deadlineMs, witnesses:timings.length, accepted:timings.filter(t => t.accepted).length,
    nominalDeadlineMisses:timings.filter(t => t.nominalMiss).length,
    nominalUnmeasured:timings.filter(t => t.accepted && t.nominalMiss === null).length,
    preWarmDeadlineMisses:timings.filter(t => t.preWarmDeadlineMiss).length,
    nominalMissesWithoutWarmAttribution:timings.filter(t => t.nominalMiss && t.preWarmDeadlineMiss === null).length,
    durableObserved:timings.filter(t => t.durableObserved && t.accepted).length,
    expectedFrames:timings.reduce((n,t) => n+t.expectedFrames,0),
    matchedFrames:timings.reduce((n,t) => n+t.matchedFrames,0),
    acceptanceToCompletionMs:stats(timings.map(t => t.acceptanceToCompletionMs).filter(Number.isFinite)),
    acceptanceToFrameMs:stats(timings.flatMap(t => t.acceptanceToFrameMs)),
    coverage:Object.fromEntries(['PASS','FAIL','UNMEASURED'].map(k => [k,timings.filter(t => t.verdict===k).length])),
    scope:'HTTP 200 acknowledgement to first observed durable clinical output and matched viewer callbacks; signed frame delays include callbacks before acknowledgement'};
}
function checkpoint(directory, witnesses, pending, source) {
  const rows = witnesses.map(w => {
    const frames = [...(pending.get(w.tenant+':'+w.date)?.clientFrames?.values() || [])];
    return {tenant:w.tenant,date:w.date,clinicalTiming:assess(w,frames,source.row(w.tenant))};
  });
  const clinicalTiming = summary(rows);
  const checkpoint = {clinicalTiming, witnesses:rows, partial:true,
    verdict:clinicalTiming.coverage.FAIL ? 'FAIL' : 'UNMEASURED'};
  const dest = path.join(directory,'clinical-witnesses-partial.json');
  fs.writeFileSync(dest+'.new',JSON.stringify(checkpoint),{mode:0o600});
  fs.renameSync(dest+'.new',dest);
}

module.exports = {contract, deadlineMs, source, assess, observe, summary, shouldPoll, checkpoint};
