p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# --- §5.3.3 misquote + append 5.3.4 and 5.3.5 ---
rep("""`CONNECT_COUNTRY_CODE` on its own is inert, because `nightscout-connect/index.js` returns early with
*"Skipping disabled connector, no source driver"* when `connect.source` is unset — which is what makes
the narrow pre-stage in §3.3 safe.""",
"""`CONNECT_COUNTRY_CODE` on its own is inert, because `nightscout-connect/index.js:30` returns early
and logs `Skipping disabled nightscout-connect, no source driver spec` when `connect.source` is
unset — which is what makes the narrow pre-stage in §3.3 safe. *(Verified by execution. The previous
revision misquoted this string as "Skipping disabled connector, no source driver"; an operator
searching a log for that sentence would find nothing.)*

#### 5.3.4 The legacy **Dexcom** bridge already does not run on today's release — added in review

This is the single largest omission the adversarial review found, and it cuts in the project's
favour.

On **`origin/master` (15.0.8, what operators run today)** and on `origin/dev`, `setupConnect`
(`bootevent.js:352` on master, `:352` on dev) calls `migrateBridgeToConnect()` **unconditionally**,
before anything checks whether Connect is configured. `lib/server/bridge-connect-compat.js` — which
is **byte-identical on master and dev** (`git diff` returns empty) — then does this: if
`BRIDGE_USER_NAME` and `BRIDGE_PASSWORD` are set and `DEXCOM_BRIDGE_USE_LEGACY` is not true, it sets
`connect.source = 'dexcomshare'` and copies the credentials across. `setupBridge` runs afterwards,
sees `connect.source === 'dexcomshare'`, and stands down.

**Measured by execution of `origin/master:lib/server/bridge-connect-compat.js`, with a control:**

| Configuration | shim result | `connect.source` after | legacy bridge stands down? |
| --- | --- | --- | --- |
| **ARM** `BRIDGE_*` only — today's normal Dexcom setup | `{migrated: true}` | `dexcomshare` | **yes** |
| **ARM** `BRIDGE_*` + `DEXCOM_BRIDGE_USE_LEGACY=true` | `{migrated: false, legacy: true}` | `undefined` | no |
| **CTRL** no bridge settings at all | `{migrated: false, legacy: false}` | `undefined` | no |

The two rows that return `undefined` are the controls: the harness distinguishes the branches.

**Three consequences.**

1. **§3.1 and §3.3 were wrong** and are rewritten. "You are affected if `BRIDGE_*` is set" is not
   true, and `BRIDGE_*` is not a rollback safety net.
2. **Cut 4's Dexcom deletion is smaller than the branch presents it.** It removes a plugin that, on
   today's release, runs only for operators who explicitly set `DEXCOM_BRIDGE_USE_LEGACY=true`.
   Everyone else has already been migrated, silently, by a release they have already taken. That is
   evidence *for* §8.4(a): the Dexcom half has been in production exposure for a whole release cycle
   and the MiniMed half has had none.
3. **It also sharpens §7.1/D2.** The asymmetry is not merely that MiniMed lacks an escape hatch; it
   is that Dexcom operators were moved onto the replacement without being asked, and MiniMed
   operators will be moved onto it by a release that takes their site down if they have not
   pre-configured it.

#### 5.3.5 A forward clock shift switches the stale-data alarm off — added in review

**A safety consequence of §5.3 that the document did not state.**

`lib/plugins/timeago.js` `checkNotifications` opens:

```js
var lastSGVEntry = sbx.lastSGVEntry();

if (!lastSGVEntry || lastSGVEntry.mills >= sbx.time) {
  return;
}
```

That `return` is **before** `checkStatus()` and before any call to `sendAlarm()`. So when the newest
stored reading is at or after "now", no *"Stale data, check rig?"* notification is ever requested —
at neither WARN nor URGENT level. `lib/settings.js:27-30` has `alarmTimeagoWarn: true` at 15 minutes
and `alarmTimeagoUrgent: true` at 30 minutes, both **on by default**, so this is the alarm nearly
every deployment is relying on.

**Measured, with controls**, against a transcription of that guard:

| Case | newest reading, relative to now | stale-data alarm fires? |
| --- | --- | --- |
| **ARM** pump +2 h ahead (Berlin), ingestion dead 3 h | +1 h | **no** |
| **ARM** pump +5:30 ahead (India), ingestion dead | +5.5 h | **no** |
| **CTRL** correct clock, ingestion dead 3 h | −3 h | yes |
| **CTRL** pump −7 h behind (US Pacific), ingestion healthy | −7 h | yes |
| **CTRL** alerts disabled | −3 h | no |

Two controls fire and the arms do not, so the guard is what makes the difference.

**Why this matters more than the chart being wrong.** The §5.3 divergence pushes readings *forward*
for every pump east of UTC. For those operators the defect does two things at once: it files the
trace at the wrong time, **and** it disables the mechanism that would tell them when the trace stops
advancing. The parent-watching-a-child case in §1 is exactly the case this removes cover from. It
also means a MiniMed operator who has already moved to `CONNECT_SOURCE=minimedcarelink` on 15.0.8
may have had no working stale-data alarm since they did so, without any visible sign.

The opposite shift is not harmless either: a pump west of UTC files readings in the past, so the
urgent alarm fires **continuously** and correctly-timed alarms become indistinguishable from noise.
Alarm fatigue on a data-availability alarm is its own hazard.

**This is not a defect in `timeago.js`.** Refusing to alarm on a future-dated reading is defensible
on its own terms. It is a defect in what §5.3 does to the data `timeago.js` is reading. The fix is
§5.3's fix. *(No BF id allocated; returned with §5.3's proposed register entry as a second
consequence of the same defect.)*""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
