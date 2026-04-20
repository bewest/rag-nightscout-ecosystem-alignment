'use strict';

/*
 * Simulation of AAPS V1 DataSyncSelectorV1.processChangedProfileStore()
 * to test whether changing `confirmLastProfileStore(now)` to
 * `confirmLastProfileStore(lastChangeAtSyncStart)` fixes the lost-edit race.
 *
 * Faithfully models (from DataSyncSelectorV1.kt:786-805):
 *   1. read lastChange = LocalProfileLastChange preference
 *   2. read lastSync   = ProfileStoreLastSyncedId preference
 *   3. if lastChange == 0 -> return
 *   4. if lastChange > lastSync:
 *        send profile, wait for ack (~60s)
 *        on ack: confirmLastProfileStore(<TIMESTAMP>)
 *
 * The bug: <TIMESTAMP> is dateUtil.now() captured AFTER the ack returns.
 * The fix: <TIMESTAMP> should be the lastChange value captured BEFORE send.
 *
 * Race scenario: user edits at T1, sync starts and sends profile, while we
 * wait for the server ack the user edits AGAIN at T3, ack arrives at T4.
 * After buggy confirm, lastSync = T4 > T3, so the T3 edit is permanently
 * unsyncable until LocalProfileLastChange exceeds T4.
 */

function makeStrategy(name, confirmTimestampFn) {
  return { name, confirmTimestampFn };
}

async function runScenario(strategy) {
  const prefs = {
    LocalProfileLastChange: 0,
    ProfileStoreLastSyncedId: 0,
  };
  const sentProfiles = []; // each entry: {sentAt, lastChangeAtSend}

  // Simulate: pretend initial state — never synced
  function storeSettings(t) { prefs.LocalProfileLastChange = t; }
  function userEdit(t) { storeSettings(t); }

  // The sync loop, modeled as a single invocation taking a "now" generator.
  // Returns whether a profile was actually sent.
  async function processChangedProfileStore(nowAtStart, nowAtAck, concurrentEditAt) {
    if (prefs.LocalProfileLastChange === 0) return { sent: false };
    const lastChange = prefs.LocalProfileLastChange;
    const lastSync = prefs.ProfileStoreLastSyncedId;
    if (!(lastChange > lastSync)) return { sent: false };

    sentProfiles.push({ sentAt: nowAtStart, lastChangeAtSend: lastChange });

    // ---- 60s wait for ack window: simulate concurrent user edit ----
    if (concurrentEditAt != null) {
      userEdit(concurrentEditAt);
    }

    // ack arrived
    const confirmTimestamp = strategy.confirmTimestampFn({
      lastChangeAtSend: lastChange,
      nowAtStart,
      nowAtAck,
    });
    prefs.ProfileStoreLastSyncedId = confirmTimestamp;
    return { sent: true, confirmTimestamp };
  }

  // ---- Scenario timeline (ms) ----
  // T=1000  user edit #1
  // T=1100  sync poll fires, sends profile
  // T=1500  user edit #2 (concurrent, while ack pending)
  // T=2000  ack returns
  // T=2100  next sync poll fires
  userEdit(1000);
  const r1 = await processChangedProfileStore(1100, 2000, /*concurrentEditAt=*/1500);
  const r2 = await processChangedProfileStore(2100, 2200, /*concurrentEditAt=*/null);

  return { strategy: strategy.name, prefs, sentProfiles, r1, r2 };
}

(async function main() {
  const buggy = makeStrategy(
    'BUGGY: confirmLastProfileStore(dateUtil.now())',
    ({ nowAtAck }) => nowAtAck
  );
  const fixed = makeStrategy(
    'FIXED: confirmLastProfileStore(lastChangeAtSend)',
    ({ lastChangeAtSend }) => lastChangeAtSend
  );

  for (const strat of [buggy, fixed]) {
    const out = await runScenario(strat);
    console.log('=== ' + out.strategy + ' ===');
    console.log('  sends:', out.sentProfiles);
    console.log('  final prefs:', out.prefs);
    const editsMade = [1000, 1500];
    const editsSynced = out.sentProfiles.map(p => p.lastChangeAtSend);
    const lostEdits = editsMade.filter(e => !editsSynced.includes(e));
    console.log('  edits made: ', editsMade);
    console.log('  edits sent: ', editsSynced);
    console.log('  LOST edits: ', lostEdits.length ? lostEdits : 'none');
    console.log();
  }
})();
