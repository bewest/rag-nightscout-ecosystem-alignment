// Transcription of origin/dev lib/plugins/timeago.js checkNotifications guard (lines 20-28)
function wouldAlarm(enableAlerts, lastSGVmills, now, statusIsUrgent) {
  if (!enableAlerts) return false;
  const lastSGVEntry = {mills: lastSGVmills};
  if (!lastSGVEntry || lastSGVEntry.mills >= now) return false;   // <-- line 26
  return statusIsUrgent;                                          // checkStatus/sendAlarm below
}
const now = Date.parse('2026-09-01T12:00:00.000Z');
const H = 3600000;
const cases = [
  ['ARM  pump +2h ahead, ingestion dead 3h', now + 2*H - 3*H + 2*H, true], // newest reading filed 2h in future
  ['ARM  pump +5:30 ahead, ingestion dead',  now + 5.5*H,           true],
  ['CTRL correct clock, ingestion dead 3h',  now - 3*H,             true],
  ['CTRL pump -7h behind, ingestion healthy',now - 7*H,             true],
  ['CTRL alerts disabled',                   now - 3*H,             true],
];
console.log('guard: lastSGVEntry.mills >= sbx.time  => return (no alarm requested)');
cases.forEach(([l, mills, urgent], i) => {
  const enable = !l.includes('alerts disabled');
  console.log(l.padEnd(42), '| newest reading offset_h=', ((mills-now)/H).toFixed(2).padStart(6),
    '| stale-data alarm fires:', wouldAlarm(enable, mills, now, urgent));
});
