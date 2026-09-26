'use strict';
/*
 * journey-lab/clients.js -- request builders that replay what real Nightscout clients send.
 *
 * CONTRIBUTOR-FACING lab code. Every value produced here is SYNTHETIC (fake device tokens,
 * lab bundle ids, made-up glucose/insulin numbers). Nothing here is copied from real user
 * data, and nothing here is medical advice: the numbers exist only to exercise a Nightscout
 * server, never to guide therapy.
 *
 * Pure module: no network, no fs. Each builder returns a request descriptor
 *   { label, method, path, body?, auth, socket?, source: [...], notes? }
 * that a separate runner executes. `auth` is one of
 *   'secret'      api-secret header = SHA-1 hex of API_SECRET (Loop, Trio, LoopCaregiver, xDrip)
 *   'jwt'         Authorization: Bearer <jwt from /api/v2/authorization/request/<token>> (AAPS v3, nightguard v3)
 *   'token-query' ?token=<accessToken> appended by the runner (LoopFollow, Nightscout Reporter)
 *   'token-path'  the access token substituted for <accessToken> in the path (nightguard's JWT request)
 *   'token-header' the RAW access token in an API-SECRET header (nightguard's v1 reads)
 * A descriptor with `form: true` is sent application/x-www-form-urlencoded, as the web page's jQuery does.
 *   'socket'      AAPS NSClient v1 socket.io: authorize with the secret, then emit socket.event
 * Query strings are already encoded the way each client encodes them. Where the encoding is
 * produced by a platform library (Foundation URLComponents, a browser), the encoding here is a
 * reading of that library, not a capture; see ENCODING NOTES below.
 *
 * Client revisions cited (repo@sha as used in `source` strings):
 * | client                        | cite prefix                  | how read                                             |
 * |-------------------------------|------------------------------|------------------------------------------------------|
 * | NightscoutKit (Loop's pin)    | NightscoutKit@4ec9fd1        | externals/NightscoutKit HEAD = LoopWorkspace Package.resolved revision |
 * | NightscoutService             | NightscoutService@fe075ef    | LoopWorkspace submodule HEAD                          |
 * | LoopKit                       | LoopKit@325bd820             | LoopWorkspace submodule HEAD                          |
 * | Loop app                      | Loop@c2fddb76                | LoopWorkspace submodule HEAD                          |
 * | LoopOnboarding                | LoopOnboarding@4aca97d       | LoopWorkspace submodule HEAD                          |
 * | LoopWorkspace                 | LoopWorkspace@f841285        | HEAD                                                  |
 * | NightscoutRemoteCGM           | NightscoutRemoteCGM@e2230e3  | LoopWorkspace submodule HEAD                          |
 * | OmnipodKit (Trio submodule)   | OmnipodKit@4e923d7           | Trio submodule HEAD (onboarding basal grid)           |
 * | Trio                          | Trio@e41c9db37               | HEAD                                                  |
 * | AndroidAPS 3.4.x (NSClient v1+v3) | AndroidAPS@598e2eb39c    | git show origin/master:<path>                        |
 * | AndroidAPS 4.0-dev            | AndroidAPS@7e1d537d49        | working tree HEAD                                     |
 * | LoopFollow                    | LoopFollow@4a74b781          | HEAD                                                  |
 * | LoopCaregiver                 | LoopCaregiver@2305718        | HEAD (its NightscoutKit fork gestrich/NightscoutKit@d63fb73 is NOT available locally; v1 notification payloads cited from NightscoutKit@4ec9fd1, which has the same functions) |
 * | nightguard                    | nightguard@75404bd           | HEAD                                                  |
 * | xDrip (Android)               | xDrip@1ed760048              | HEAD                                                  |
 * | Nightscout Reporter           | nightscout-reporter@518d61f  | HEAD                                                  |
 * | Nightscout web (15.0.9 RC)    | cgm-remote-monitor@e3adc91d  | externals/work/crm-6a-soak-rc HEAD                    |
 *
 * ENCODING NOTES
 *  - Foundation URLComponents.queryItems (Loop/NightscoutKit, Trio, LoopFollow, LoopCaregiver,
 *    nightguard): '[' and ']' are percent-encoded (%5B/%5D, not in urlQueryAllowed); '$', ':',
 *    '+', '/', ',' stay literal; space -> %20. Trio's value "Temporary+Target" therefore goes out
 *    with a literal '+', which the server's query parser reads as a space. Inferred from the
 *    Foundation character set, not captured on the wire.
 *  - Retrofit @Query(encoded = true) (xDrip) and string concatenation in a browser (Reporter):
 *    brackets and '$' literal.
 */

const crypto = require('crypto');

// ---------------------------------------------------------------------------
// small pure helpers
// ---------------------------------------------------------------------------

/** Deterministic UUID from a caller seed (SHA-1 name-based, v5 layout). Apple clients use
 * UPPER-case uuidString; AAPS/kotlin use lower-case. */
function uuid (seed, opts) {
  const upper = !!(opts && opts.upper);
  const h = crypto.createHash('sha1').update(String(seed)).digest('hex').slice(0, 32).split('');
  h[12] = '5';
  h[16] = ((parseInt(h[16], 16) & 0x3) | 0x8).toString(16);
  const s = h.join('');
  const u = [s.slice(0, 8), s.slice(8, 12), s.slice(12, 16), s.slice(16, 20), s.slice(20, 32)].join('-');
  return upper ? u.toUpperCase() : u;
}
/** 24-hex id derived from a seed (stands in for a server-returned ObjectId string). */
function hex24 (seed) { return crypto.createHash('sha1').update('oid:' + seed).digest('hex').slice(0, 24); }

const pad2 = (n) => String(n).padStart(2, '0');
const secs = (hhmm) => { const [h, m] = String(hhmm).split(':').map(Number); return h * 3600 + m * 60; };
/** ISO-8601 without fractional seconds ("...:00Z") -- ISO8601DateFormatter .withInternetDateTime */
const isoS = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
/** ISO-8601 with milliseconds ("...:00.000Z") */
const isoMs = (ms) => new Date(ms).toISOString();
/** AAPS DateUtil.toISOAsUTC: pattern "yyyy-MM-dd'T'HH:mm:ss.SSS'0000Z'" -> 7 fraction digits */
const aapsIsoAsUTC = (ms) => new Date(ms).toISOString().replace(/Z$/, '0000Z');
/** Swift "\(Double)" interpolation: 60 -> "60.0", 1.5 -> "1.5" */
const swiftDouble = (n) => (Number.isInteger(Number(n)) ? Number(n).toFixed(1) : String(Number(n)));
const round = (v, d) => Math.round(v * Math.pow(10, d)) / Math.pow(10, d);

const FOUNDATION_QUERY_ALLOWED = /[A-Za-z0-9\-._~!$&'()*+,;=:@/?]/;
function foundationEncode (s) {
  let out = '';
  for (const ch of String(s)) {
    if (FOUNDATION_QUERY_ALLOWED.test(ch)) out += ch;
    else out += Array.from(Buffer.from(ch, 'utf8')).map((b) => '%' + b.toString(16).toUpperCase().padStart(2, '0')).join('');
  }
  return out;
}
/** Query string as URLComponents.queryItems would produce it, keeping item order. */
function qFoundation (pairs) { return pairs.map(([k, v]) => foundationEncode(k) + '=' + foundationEncode(v)).join('&'); }
/** Query string concatenated literally (browser/Retrofit encoded=true). */
function qLiteral (pairs) { return pairs.map(([k, v]) => k + '=' + v).join('&'); }

function d (label, method, path, auth, source, extra) {
  const out = { label, method, path, auth, source };
  if (extra) {
    if (extra.body !== undefined) out.body = extra.body;
    if (extra.socket) out.socket = extra.socket;
    if (extra.notes) out.notes = extra.notes;
  }
  return out;
}
function notDone (client, action, source) {
  return function () { throw new Error(client + ' does not ' + action + ': ' + source.join('; ')); };
}
function dropUndef (o) { const r = {}; for (const k of Object.keys(o)) if (o[k] !== undefined) r[k] = o[k]; return r; }

const LAB_DEVICE_TOKEN = '1ab0' + '0'.repeat(60); // obviously fake APNs token (64 hex)

// ---------------------------------------------------------------------------
// Loop  (all HTTP goes through NightscoutKit; NightscoutService builds the models)
// ---------------------------------------------------------------------------
const NSK = 'NightscoutKit@4ec9fd1 Sources/NightscoutKit/';
const NSS = 'NightscoutService@fe075ef NightscoutServiceKit/';
const LK = 'LoopKit@325bd820 LoopKit/';
const SRC_NSK_CALL = NSK + 'NightscoutClient.swift:519-526'; // api-secret = sha1, JSON content type
const SRC_NSK_ENDPOINTS = NSK + 'NightscoutClient.swift:12-21';
const SRC_NSK_POST = NSK + 'NightscoutClient.swift:479-511'; // POST array; response length must match
const SRC_NSK_TREAT_BASE = NSK + 'Models/Treatments/NightscoutTreatment.swift:105-120';
const SRC_NSK_TIMEFMT = NSK + 'Extensions/TimeFormat.swift:15-17';
const NRC = 'NightscoutRemoteCGM@e2230e3 NightscoutRemoteCGM/'; // LoopWorkspace submodule HEAD; uses Loop's NightscoutKit pin

/** ProfileSet.swift:8-12: TimeZone(secondsFromGMT: 3600*h).identifier -> String(format:"ETC/GMT%+d", -h) */
function loopTz (offsetHours) {
  const h = -Number(offsetHours || 0);
  return 'ETC/GMT' + (h >= 0 ? '+' : '-') + Math.abs(h);
}
/** ProfileSet.swift:35-43 ScheduleItem.dictionaryRepresentation */
function loopItem (hhmm, value) {
  const s = secs(hhmm);
  return { time: pad2(Math.floor(s / 3600)) + ':' + pad2(Math.floor((s % 3600) / 60)), value, timeAsSeconds: s };
}
const loopDevice = (name) => 'loop://' + (name || 'Lab iPhone'); // "loop://\(UIDevice.current.name)"
const GLUCOSE_TREND = { DoubleUp: 1, SingleUp: 2, FortyFiveUp: 3, Flat: 4, FortyFiveDown: 5, SingleDown: 6, DoubleDown: 7, NotComputable: 8, RateOutOfRange: 9 };

function loopOverrideBody ({ now, uuid: id, reason, durationMin, correctionRange, insulinNeedsScaleFactor, remote, remoteAddress }) {
  // OverrideTreatment.swift:62-80 over NightscoutTreatment.swift:105-120
  const b = {
    created_at: isoS(now),
    timestamp: isoS(now),
    enteredBy: remote ? 'Loop (via remote command)' : 'Loop',
    _id: id,
    eventType: 'Temporary Override',
    reason
  };
  if (durationMin === null || durationMin === undefined) b.durationType = 'indefinite';
  else b.duration = durationMin; // timeInterval.minutes (Double, may be fractional)
  if (insulinNeedsScaleFactor !== undefined && insulinNeedsScaleFactor !== null) b.insulinNeedsScaleFactor = insulinNeedsScaleFactor;
  if (remote) b.remoteAddress = remoteAddress || 'lab-caregiver';
  if (correctionRange) b.correctionRange = [correctionRange[0], correctionRange[1]]; // always mg/dL (OverrideTreament.swift:17-18)
  return b;
}

const loop = {
  profileUpload ({ now, units = 'mg/dL', schedules, presets = [], deviceToken = LAB_DEVICE_TOKEN, bundleIdentifier = 'org.lab.Loop', isAPNSProduction = false, timezoneOffsetHours = 0, minimumBGGuard, maximumBasalRatePerHour = 3, maximumBolus = 5, preMealTargetRange }) {
    const sch = schedules || defaultSchedules(units);
    const store = {
      Default: {
        dia: 6, // StoredSettings.swift:83 dia: .hours(6)
        carbs_hr: '0',
        delay: '0',
        timezone: loopTz(timezoneOffsetHours),
        target_low: sch.target.map(([t, lo]) => loopItem(t, lo)),
        target_high: sch.target.map(([t, , hi]) => loopItem(t, hi)),
        sens: sch.sens.map(([t, v]) => loopItem(t, v)),
        basal: sch.basal.map(([t, v]) => loopItem(t, v)),
        carbratio: sch.carbratio.map(([t, v]) => loopItem(t, v)),
        units
      }
    };
    const loopSettings = {
      dosingEnabled: true,
      overridePresets: presets.map((p) => dropUndef({
        duration: (p.durationMin || 0) * 60, // seconds; 0 = indefinite (TemporaryScheduleOverride.swift ns:25-31)
        symbol: p.symbol,
        targetRange: p.targetRange ? [p.targetRange[0], p.targetRange[1]] : undefined, // in profile units
        insulinNeedsScaleFactor: p.scale,
        name: p.name
      })),
      minimumBGGuard: minimumBGGuard !== undefined ? minimumBGGuard : (units === 'mmol/L' ? 4.2 : 75),
      maximumBasalRatePerHour,
      maximumBolus,
      deviceToken,
      dosingStrategy: 'automaticBolus',
      bundleIdentifier
    };
    if (preMealTargetRange) loopSettings.preMealTargetRange = [preMealTargetRange[0], preMealTargetRange[1]];
    const body = [{
      defaultProfile: 'Default',
      startDate: isoS(now),
      mills: String(Math.round(now)), // String(format: "%.0f", ms) -- a STRING
      units,
      enteredBy: 'Loop',
      loopSettings,
      store,
      isAPNSProduction
    }];
    return d('Loop profile upload', 'POST', '/api/v1/profile', 'secret', [
      NSK + 'NightscoutClient.swift:407-409',
      NSK + 'Models/ProfileSet.swift:8-12,35-43,81-95,143-165',
      NSK + 'Models/LoopSettings.swift:38-62',
      NSK + 'Models/TemporaryScheduleOverride.swift:28-50',
      NSS + 'Extensions/StoredSettings.swift:37-106',
      NSS + 'Extensions/TemporaryScheduleOverride.swift:15-39',
      NSS + 'NightscoutService.swift:359-368',
      SRC_NSK_CALL
    ], { body, notes: 'JSON array (batches of up to 400). No _id, no created_at. scheduleOverride is included in loopSettings only while an override is active (omitted here). isAPNSProduction is top-level; deviceToken/bundleIdentifier sit inside loopSettings.' });
  },

  overrideStart (a) {
    return d('Loop override start', 'POST', '/api/v1/treatments', 'secret', [
      NSS + 'NightscoutService.swift:157-186',
      NSS + 'Extensions/OverrideTreament.swift:14-60',
      NSK + 'Models/Treatments/OverrideTreatment.swift:25-32,62-80',
      SRC_NSK_TREAT_BASE, SRC_NSK_POST, SRC_NSK_TIMEFMT
    ], { body: [loopOverrideBody(a)], notes: 'reason is built by Loop as "<symbol> <name>" for presets, "Custom Override", "Pre-Meal" or "Workout" (OverrideTreament.swift:29-39). _id is the override syncIdentifier.uuidString (UPPER-case UUID).' });
  },

  // Code contradicts "delete then re-POST": an early end marks the event .early(date)
  // (TemporaryScheduleOverrideHistory.swift:171-186), queryByAnchor sets scheduledEndDate=end so
  // duration becomes finite(end-start) (TemporaryScheduleOverrideHistory.swift:287-300,
  // TemporaryScheduleOverride.swift:77-88), and NightscoutService POSTs it again under the same
  // UUID _id. The DELETE step only runs for overrides marked .deleted, and with an empty list it
  // sends nothing (NightscoutClient.swift:106-128, 479-483).
  overrideEnd ({ uuid: id, startedAt, endedAt, reason, correctionRange, insulinNeedsScaleFactor, remote, remoteAddress }) {
    const durationMin = (endedAt - startedAt) / 60000;
    return d('Loop override ended early (re-POST, same _id, actual duration)', 'POST', '/api/v1/treatments', 'secret', [
      LK + 'TemporaryScheduleOverrideHistory.swift:171-186,287-305',
      LK + 'TemporaryScheduleOverride.swift:77-88',
      'Loop@c2fddb76 Loop/Managers/RemoteDataServicesManager.swift:520-546',
      NSS + 'NightscoutService.swift:157-186',
      NSK + 'Models/Treatments/OverrideTreatment.swift:62-80',
      NSK + 'NightscoutClient.swift:106-128,479-483'
    ], { body: [loopOverrideBody({ now: startedAt, uuid: id, reason, durationMin, correctionRange, insulinNeedsScaleFactor, remote, remoteAddress })], notes: 'No DELETE precedes this POST. duration is (end-start) in minutes as a Double (not rounded); durationType is absent. Relies on the server upserting a string (UUID) _id.' });
  },

  overrideDelete ({ uuid: id }) {
    return d('Loop override delete', 'DELETE', '/api/v1/treatments/' + id, 'secret', [
      NSS + 'NightscoutService.swift:163-173',
      NSK + 'NightscoutClient.swift:106-128,430-445',
      LK + 'TemporaryScheduleOverrideHistory.swift:136-143,175-179,296-297'
    ], { notes: 'Sent for overrides whose actualEnd is .deleted (e.g. replaced before they started). Path carries the UPPER-case UUID, no query. A non-200 here leaves Loop\'s override queue waiting (completion never called, NightscoutService.swift:167-170).' });
  },

  bolus ({ now, syncIdentifier, units, automatic = false, programmed, durationMin = 0, device }) {
    const body = [{
      created_at: isoS(now), timestamp: isoS(now), enteredBy: loopDevice(device),
      eventType: 'Correction Bolus', syncIdentifier,
      type: durationMin >= 30 ? 'square' : 'normal',
      insulin: units, programmed: programmed !== undefined ? programmed : units, unabsorbed: 0,
      duration: durationMin, automatic
    }];
    return d('Loop bolus', 'POST', '/api/v1/treatments', 'secret', [
      NSS + 'Extensions/DoseEntry.swift:14-33',
      NSS + 'Extensions/NightscoutUploader.swift:120-147',
      NSK + 'Models/Treatments/BolusNightscoutTreatment.swift:13-16,26-33,56-65',
      SRC_NSK_TREAT_BASE, SRC_NSK_POST
    ], { body, notes: 'No _id (id argument commented out, DoseEntry.swift:30); syncIdentifier is a Loop-only field. insulinType (brand name) is added when known; omitted here.' });
  },

  carbs ({ now, grams, absorptionHours = 3, foodType, syncIdentifier, device }) {
    const b = {
      created_at: isoS(now), timestamp: isoS(now), enteredBy: loopDevice(device),
      eventType: 'Carb Correction', syncIdentifier: syncIdentifier || uuid('loop-carb:' + now, { upper: true }),
      carbs: Math.round(grams), absorptionTime: absorptionHours * 60
    };
    if (foodType) b.foodType = foodType;
    b.userEnteredAt = isoS(now);
    return d('Loop carbs', 'POST', '/api/v1/treatments', 'secret', [
      NSS + 'Extensions/SyncCarbObject.swift:16-28',
      NSS + 'Extensions/NightscoutUploader.swift:15-28',
      NSS + 'NightscoutService.swift:197-215',
      NSK + 'Models/Treatments/CarbCorrectionNightscoutTreatment.swift:22-31,85-106',
      SRC_NSK_TREAT_BASE, SRC_NSK_POST
    ], { body: [b], notes: 'No _id on create; Loop caches the _id strings from the response array for 24 h (NightscoutService.swift:27,207-213) and uses them for later PUT/DELETE.' });
  },

  carbEdit ({ nsId, now, grams, absorptionHours = 3, foodType, syncIdentifier, device, userEnteredAt, modifiedAt }) {
    const b = {
      created_at: isoS(now), timestamp: isoS(now), enteredBy: loopDevice(device), _id: nsId,
      eventType: 'Carb Correction', syncIdentifier: syncIdentifier || uuid('loop-carb:' + now, { upper: true }),
      carbs: Math.round(grams), absorptionTime: absorptionHours * 60
    };
    if (foodType) b.foodType = foodType;
    b.userEnteredAt = isoS(userEnteredAt || now);
    b.userLastModifiedAt = isoS(modifiedAt || now);
    return d('Loop carb edit', 'PUT', '/api/v1/treatments', 'secret', [
      NSS + 'Extensions/NightscoutUploader.swift:30-50',
      NSK + 'NightscoutClient.swift:74-100,447-456',
      NSK + 'Models/Treatments/CarbCorrectionNightscoutTreatment.swift:85-106',
      SRC_NSK_TREAT_BASE
    ], { body: b, notes: 'One PUT per edited entry with a single JSON OBJECT (not an array), _id = cached 24-hex string. Skipped entirely if the _id is not in the 24 h cache.' });
  },

  carbDelete ({ nsId }) {
    return d('Loop carb delete', 'DELETE', '/api/v1/treatments/' + nsId, 'secret', [
      NSS + 'Extensions/NightscoutUploader.swift:52-73',
      NSK + 'NightscoutClient.swift:134-156,430-445'
    ], { notes: 'nsId is the cached 24-hex _id from the create response.' });
  },

  tempBasal ({ now, syncIdentifier, rate, durationMin = 30, amount, automatic = true, device }) {
    const b = {
      created_at: isoS(now), timestamp: isoS(now), enteredBy: loopDevice(device),
      eventType: 'Temp Basal', syncIdentifier,
      temp: 'absolute', rate, absolute: rate, duration: durationMin, automatic
    };
    if (amount !== undefined) b.amount = amount;
    return d('Loop temp basal', 'POST', '/api/v1/treatments', 'secret', [
      NSS + 'Extensions/DoseEntry.swift:51-64',
      NSK + 'Models/Treatments/TempBasalNightscoutTreatment.swift:13-16,27-37,61-71',
      SRC_NSK_TREAT_BASE, SRC_NSK_POST
    ], { body: [b], notes: 'amount (delivered units) is present only once the dose is finalized.' });
  },

  suspend ({ now, syncIdentifier, durationMin, device }) {
    const b = {
      created_at: isoS(now), timestamp: isoS(now), enteredBy: loopDevice(device),
      eventType: 'Temp Basal', syncIdentifier,
      temp: 'absolute', rate: 0, absolute: 0, duration: durationMin, automatic: true, reason: 'suspend'
    };
    return d('Loop pump suspend (as Temp Basal rate 0)', 'POST', '/api/v1/treatments', 'secret', [
      NSS + 'Extensions/DoseEntry.swift:36-50',
      NSK + 'Models/Treatments/TempBasalNightscoutTreatment.swift:61-71',
      SRC_NSK_TREAT_BASE
    ], { body: [b], notes: 'Nightscout has no Suspend type; Loop records it as Temp Basal rate 0, reason "suspend". absolute is the dose unitsPerHour (0 for a suspend). Resume produces no treatment (DoseEntry.swift:34-35).' });
  },

  entries ({ readings, device }) {
    const body = readings.map((r) => {
      const e = { date: r.t, dateString: isoS(r.t), device: device || loopDevice(), type: 'sgv', sgv: r.sgv };
      if (r.direction && GLUCOSE_TREND[r.direction]) { e.trend = GLUCOSE_TREND[r.direction]; e.direction = r.direction; }
      e.isCalibration = false;
      return e;
    });
    return d('Loop CGM entries', 'POST', '/api/v1/entries', 'secret', [
      NSS + 'Extensions/StoredGlucoseSample.swift:14-43',
      NSS + 'Extensions/NightscoutUploader.swift:79-93',
      NSK + 'Models/GlucoseEntry.swift:44-66,101-131',
      NSK + 'NightscoutClient.swift:669-671'
    ], { body, notes: 'Loop uploads the glucose it stores (from its CGM manager). device is "<manufacturer> <model> <name>" of the HealthKit device when known, else loop://<phone>. trendRate (mg/dL/min) added when the CGM supplies one. No _id.' });
  },

  devicestatus ({ now, iob, cob, predicted = [], enacted, override, reservoir, battery, deviceName = 'Lab iPhone' }) {
    const t = isoS(now);
    const loopStatus = {
      name: 'Loop', version: '3.x-lab', timestamp: t,
      iob: { timestamp: t, iob },
      cob: { timestamp: t, cob },
      predicted: { startDate: t, values: predicted.map((v) => round(v, 2)) }
    };
    if (enacted) {
      loopStatus.automaticDoseRecommendation = { timestamp: t, tempBasalAdjustment: { rate: enacted.rate, duration: enacted.durationMin }, bolusVolume: enacted.bolus || 0 };
      loopStatus.enacted = { rate: enacted.rate, duration: enacted.durationMin, timestamp: t, received: true, bolusVolume: enacted.bolus || 0 };
    }
    let ov = { timestamp: t, active: false };
    if (override) {
      ov = dropUndef({
        timestamp: t, active: true, name: override.name,
        currentCorrectionRange: override.targetRange ? { minValue: override.targetRange[0], maxValue: override.targetRange[1] } : undefined,
        duration: override.activeUntil ? Math.round((override.activeUntil - now) / 1000) : undefined, // SECONDS remaining; absent when indefinite
        multiplier: override.multiplier
      });
    }
    const body = [{
      device: loopDevice(deviceName),
      created_at: t,
      pump: dropUndef({ clock: t, pumpID: 'LAB-PUMP-01', manufacturer: 'Lab', model: 'Synthetic', battery: battery !== undefined ? { percent: battery } : undefined, suspended: false, bolusing: false, reservoir, secondsFromGMT: 0 }),
      uploader: { name: deviceName, timestamp: t, battery: 90, isCharging: false },
      loop: loopStatus,
      override: ov
    }];
    return d('Loop devicestatus', 'POST', '/api/v1/devicestatus', 'secret', [
      NSS + 'Extensions/StoredDosingDecision.swift:16-164',
      NSS + 'NightscoutService.swift:274-313',
      NSK + 'Models/DeviceStatus.swift:34-65',
      NSK + 'Models/LoopStatus.swift:48-89',
      NSK + 'Models/IOBStatus.swift:24-39', NSK + 'Models/COBStatus.swift:22-29',
      NSK + 'Models/PredictedBG.swift:20-45', NSK + 'Models/LoopEnacted.swift:28-40',
      NSK + 'Models/TempBasalAdjustment.swift:22-29', NSK + 'Models/OverrideStatus.swift:30-53',
      NSK + 'Models/PumpStatus.swift:49-66', NSK + 'Models/UploaderStatus.swift:36-51',
      NSK + 'Models/CorrectionRange.swift:18-33'
    ], { body, notes: 'Loop uploads devicestatus only for decisions with reason updateRemoteRecommendation/normalBolus/simpleBolus/watchBolus, paired with the last "loop" decision (NightscoutService.swift:284-293). enacted.duration and tempBasalAdjustment.duration are MINUTES (seconds/60); override.duration is SECONDS. Glucose values are mg/dL.' });
  },

  /** Emulates LoopOnboarding's "import therapy settings from Nightscout":
   * GET /api/v1/profile/current -> ProfileSet(rawValue:) -> therapySettings. */
  canImport (doc) {
    const source = [
      'LoopOnboarding@4aca97d LoopOnboardingKitUI/View Controllers/OnboardingUICoordinator.swift:326',
      NSS + 'NightscoutService.swift:370-389',
      NSK + 'NightscoutClient.swift:166-182',
      NSK + 'Models/ProfileSet.swift:14-16,45-56,97-120,167-190',
      NSK + 'Models/LoopSettings.swift:64-94',
      NSK + 'Extensions/TimeFormat.swift:19-26',
      NSS + 'Extensions/ProfileSet.swift:14-96'
    ];
    const no = (reason) => ({ ok: false, reason, source });
    if (!doc || typeof doc !== 'object' || Array.isArray(doc)) return no('response is not a JSON object (profile/current returns one object)');
    const isStr = (v) => typeof v === 'string';
    const isNum = (v) => typeof v === 'number' && Number.isFinite(v); // Swift `as? Double` accepts JSON numbers only
    if (!isStr(doc.startDate) || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$/.test(doc.startDate)) return no('startDate missing or not ISO-8601 (internet date time, optional fraction)');
    for (const k of ['units', 'enteredBy', 'defaultProfile']) if (!isStr(doc[k])) return no(k + ' missing or not a string');
    if (!doc.store || typeof doc.store !== 'object') return no('store missing');
    const ls = doc.loopSettings;
    if (!ls || typeof ls !== 'object') return no('loopSettings missing (only Loop-uploaded profiles have it)');
    if (typeof ls.dosingEnabled !== 'boolean') return no('loopSettings.dosingEnabled missing or not boolean');
    if (!Array.isArray(ls.overridePresets)) return no('loopSettings.overridePresets missing or not an array');
    if (!isStr(doc._id)) return no('_id missing or not a string');
    const p = doc.store.Default;
    if (!p) return no('store has no "Default" entry (key is case-sensitive; defaultProfile is ignored)');
    if (!isStr(p.timezone) || !/^ETC\/GMT[+-](1[0-8]|[0-9])$/.test(p.timezone)) return no('store.Default.timezone must be ETC/GMT+N / ETC/GMT-N (Loop\'s own form); IANA names are dropped');
    if (!isNum(p.dia)) return no('store.Default.dia missing or not a number');
    for (const k of ['sens', 'carbratio', 'basal', 'target_low', 'target_high']) if (!Array.isArray(p[k])) return no('store.Default.' + k + ' missing or not an array');
    if (!isNum(ls.minimumBGGuard)) return no('loopSettings.minimumBGGuard (suspend threshold) missing');
    const unitOk = (u) => u === 'mg/dL' || u === 'mmol/L';
    if (!unitOk(doc.units)) return no('units must be "mg/dL" or "mmol/L" exactly (got ' + JSON.stringify(doc.units) + ')');
    const dropped = [];
    for (const k of ['sens', 'carbratio', 'basal', 'target_low', 'target_high']) {
      const bad = p[k].filter((it) => !(it && isNum(it.timeAsSeconds) && isNum(it.value))).length;
      if (bad) dropped.push(k + ':' + bad);
    }
    return { ok: true, reason: dropped.length ? 'importable; schedule items without numeric timeAsSeconds/value are silently dropped (' + dropped.join(', ') + ')' : 'importable', source };
  },

  /** NightscoutRemoteCGM (Loop's "Nightscout" CGM): the one GET it sends, both for the setup
   * check (checkServiceStatus -> fetchRecent()) and for every CGM poll (fetchNewDataIfNeeded ->
   * fetchRecent()). Same request both times: fetchRecent(minutes: 60) -> maxCount (60/5)*2 = 24. */
  remoteCgmFetch ({ now }) {
    const minutes = 60;
    const q = qFoundation([
      ['find[dateString][$gte]', isoS(now - minutes * 60000)], // TimeFormat.timestampStrFromDate: .withInternetDateTime, no fraction
      ['find[dateString][$lte]', isoS(now)],
      ['count', String((minutes / 5) * 2)]
    ]);
    const src = [
      NRC + 'NightscoutFetcher.swift:23-30',
      NSK + 'NightscoutClient.swift:298-310',
      NSK + 'NightscoutClient.swift:43-50',
      SRC_NSK_TIMEFMT, NSK + 'Extensions/ISO8601DateFormatter.swift:14-19',
      SRC_NSK_CALL
    ];
    return [
      d('Loop NightscoutRemoteCGM setup check (verify)', 'GET', '/api/v1/entries?' + q, 'secret', src.concat([NRC + 'NightscoutAPIService.swift:40-65']), {
        notes: 'Sent when the user saves the URL + API secret. An empty array fails setup with "No recent glucose values available." (NightscoutAPIService.swift:55-56, 100-101). NightscoutKit rebuilds the URL from scheme/host/port only, so any sub-path in the site URL is dropped.'
      }),
      d('Loop NightscoutRemoteCGM poll', 'GET', '/api/v1/entries?' + q, 'secret', src.concat([NRC + 'NightscoutRemoteCGM.swift:96-114']), {
        notes: 'Identical request on every CGM poll, skipped while the newest stored reading is under 4.5 min old. No .json suffix, no find[type]: every entry type in the window comes back and GlucoseEntry(rawValue:) keeps what it can parse. $gte/$lte compare dateString as a STRING against second-precision "...Z" values. Headers: api-secret (SHA-1), Content-Type and Accept application/json.'
      })
    ];
  },

  /** What Loop's onboarding "import settings from Nightscout" pre-fills, given the
   * /api/v1/profile/current document. Emulates ProfileSet.therapySettings plus the
   * correction-range screen reset. Numbers are whatever the document carries: nothing here
   * judges whether they are suitable for anyone. */
  importSummary (doc) {
    const source = [
      NSS + 'Extensions/ProfileSet.swift:14-135',
      NSK + 'Models/ProfileSet.swift:45-56,97-120',
      NSK + 'Models/LoopSettings.swift:64-94',
      NSK + 'Models/TemporaryScheduleOverride.swift:52-66',
      LK + 'DailyValueSchedule.swift:105-115',
      'LoopOnboarding@4aca97d LoopOnboardingKitUI/View Controllers/OnboardingUICoordinator.swift:162-181,324-343,447-468'
    ];
    const notImported = [
      'insulin model (defaultRapidActingModel: nil, "Not stored in NS yet"; chosen separately)',
      'closed-loop on/off (loopSettings.dosingEnabled is parsed but not used)',
      'dosing strategy (loopSettings.dosingStrategy is parsed but not used)',
      'active override (loopSettings.scheduleOverride)',
      'notification / APNs settings (deviceToken, bundleIdentifier)',
      'workout correction range (always cleared: "workout mode obviated in DIY by overrides")',
      'DIA (store.Default.dia is required to parse but not imported)'
    ];
    const c = loop.canImport(doc);
    if (!c.ok) return { ok: false, reason: c.reason, imported: null, notImported, source: source.concat(c.source), notes: 'Loop shows no error: a failed fetch/parse just skips the import screen (OnboardingUICoordinator.swift:334-336).' };
    const p = doc.store.Default;
    const ls = doc.loopSettings;
    const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
    const unitOk = (u) => u === 'mg/dL' || u === 'mmol/L';
    const settingsUnit = doc.units;
    const scheduleUnit = unitOk(p.units) ? p.units : settingsUnit; // schedule units win when valid
    const items = (arr) => arr.filter((it) => it && isNum(it.timeAsSeconds) && isNum(it.value)).map((it) => ({ start: it.timeAsSeconds, value: it.value })).sort((a, b) => a.start - b.start);
    const orNull = (a) => (a.length ? a : null); // DailyValueSchedule init? returns nil for no items
    const lo = items(p.target_low); const hi = items(p.target_high);
    // zip() pairs by position (after the compactMap), so unequal lengths truncate; start = the LOW item's time
    const lowRaw = p.target_low.filter((it) => it && isNum(it.timeAsSeconds) && isNum(it.value));
    const highRaw = p.target_high.filter((it) => it && isNum(it.timeAsSeconds) && isNum(it.value));
    const n = Math.min(lowRaw.length, highRaw.length);
    let target = orNull(Array.from({ length: n }, (_, i) => ({ start: lowRaw[i].timeAsSeconds, low: lowRaw[i].value, high: highRaw[i].value })).sort((a, b) => a.start - b.start));
    const preMealRaw = Array.isArray(ls.preMealTargetRange) && ls.preMealTargetRange.length === 2 && ls.preMealTargetRange.every(isNum) ? ls.preMealTargetRange : null;
    let preMealTargetRange = preMealRaw ? [preMealRaw[0], preMealRaw[1]] : null;
    const presets = ls.overridePresets.filter((o) => o && isNum(o.duration) && typeof o.name === 'string' && typeof o.symbol === 'string');
    const suspend = ls.minimumBGGuard;
    const toMg = (v, u) => (u === 'mmol/L' ? v * 18.01559 : v); // HKUnit blood-glucose molar mass 180.1559
    const suspendMg = toMg(suspend, settingsUnit);
    const extra = [];
    if (lo.length !== hi.length) extra.push('target_low has ' + lo.length + ' usable items and target_high ' + hi.length + ': zip() keeps the first ' + n + ' pairs by position');
    const droppedPresets = ls.overridePresets.length - presets.length;
    if (droppedPresets) extra.push(droppedPresets + ' override preset(s) dropped (need numeric duration, name and symbol)');
    if (target && Math.min(...target.map((t) => toMg(t.low, scheduleUnit))) < suspendMg) {
      extra.push('correction range schedule CLEARED on the correction-range screen: its lowest value is below the suspend threshold (' + suspend + ' ' + settingsUnit + '); the whole schedule is reset, not only the conflicting entries, and the user must re-enter it');
      target = null;
    }
    if (preMealTargetRange && toMg(preMealTargetRange[0], settingsUnit) < suspendMg) {
      extra.push('pre-meal range CLEARED on the correction-range screen: lower bound below the suspend threshold');
      preMealTargetRange = null;
    }
    return {
      ok: true,
      reason: c.reason,
      imported: {
        units: { schedules: scheduleUnit, settings: settingsUnit },
        basal: orNull(items(p.basal)),
        sens: orNull(items(p.sens)),
        carbratio: orNull(items(p.carbratio)),
        target,
        preMealTargetRange,
        overridePresets: presets.map((o) => o.name),
        maximumBasalRatePerHour: isNum(ls.maximumBasalRatePerHour) ? ls.maximumBasalRatePerHour : null,
        maximumBolus: isNum(ls.maximumBolus) ? ls.maximumBolus : null,
        suspendThreshold: suspend
      },
      notImported: notImported.concat(extra),
      source,
      notes: 'Times are seconds from midnight (timeAsSeconds). Every imported value is shown on an editor screen for the user to confirm, so the result is a pre-fill, not a silent change. Preset target ranges and the pre-meal range are read in the top-level units; schedules use store.Default.units when it is valid.'
    };
  }
};

function defaultSchedules (units) {
  const mmol = /mmol/.test(units || '');
  return {
    basal: [['00:00', 0.8], ['06:00', 1.0]],
    sens: [['00:00', mmol ? 2.5 : 45]],
    carbratio: [['00:00', 10]],
    target: [['00:00', mmol ? 5.5 : 100, mmol ? 6.1 : 110]]
  };
}

// ---------------------------------------------------------------------------
// Trio
// ---------------------------------------------------------------------------
const TR = 'Trio@e41c9db37 Trio/Sources/';
const TR_API = TR + 'Services/Network/Nightscout/NightscoutAPI.swift';
const SRC_TR_TREAT_KEYS = TR + 'Models/NightscoutTreatment.swift:40-64';
const SRC_TR_ENCODER = TR + 'Helpers/JSON.swift:84-89';
const TR_EXCLUDED = ['Trio', 'AndroidAPS', 'openaps://AndroidAPS', 'iAPS', 'loop://iPhone']; // NightscoutAPI.swift:23-29
const trioUnits = (u) => (/mmol/i.test(u || '') ? 'mmol' : 'mg/dl');
const asMmol = (v) => round(v * 0.0555, 1);
/** Trio.rounded(_, scale, .plain): NSDecimalRound, halves away from zero */
const trioRound = (v, s) => { const f = Math.pow(10, s); return Math.sign(v) * Math.round(Math.abs(v) * f + 1e-9) / f; };
const TRIO_DISTANT_PAST = '0001-01-01T00:00:00.000Z'; // Date.distantPast through ISO8601DateFormatter (inferred)

const trio = {
  connect () {
    return d('Trio connected Note (connection check)', 'POST', '/api/v1/treatments.json', 'secret', [TR_API + ':45-66'], {
      body: { eventType: 'Note', enteredBy: 'Trio', notes: 'Trio connected' },
      notes: 'Single JSON object (not an array), no created_at, no id. Sent when the user checks the connection with a secret; without a secret Trio does a GET instead.'
    });
  },

  profileUpload ({ now, units = 'mg/dL', schedules, dia = 6, presets = [], deviceToken = LAB_DEVICE_TOKEN, bundleIdentifier = 'org.lab.Trio', teamID = 'LABTEAM001', isAPNSProduction = false, timezone = 'Etc/UTC', expirationDate }) {
    const nsUnits = trioUnits(units);
    const mmol = nsUnits === 'mmol';
    const sch = schedules || defaultSchedules('mg/dL'); // Trio stores glucose in mg/dL; converts on upload
    const tv = (t, v) => ({ time: String(t).slice(0, 5), value: v, timeAsSeconds: secs(t) });
    const g = (v) => (mmol ? asMmol(v) : v);
    const body = {
      defaultProfile: 'default',
      startDate: isoMs(now),
      mills: Math.floor(now / 1000) * 1000, // Int(now.timeIntervalSince1970) * 1000 -- a NUMBER, whole seconds
      units: nsUnits,
      enteredBy: 'Trio',
      store: {
        default: {
          dia, carbs_hr: 0, delay: 0, timezone,
          target_low: sch.target.map(([t, lo]) => tv(t, g(lo))),
          target_high: sch.target.map(([t, , hi]) => tv(t, g(hi))),
          sens: sch.sens.map(([t, v]) => tv(t, g(v))),
          basal: sch.basal.map(([t, v]) => tv(t, v)),
          carbratio: sch.carbratio.map(([t, v]) => tv(t, v)),
          units: nsUnits
        }
      },
      bundleIdentifier, deviceToken, isAPNSProduction,
      overridePresets: presets.map((p) => dropUndef({ name: p.name, duration: p.durationMin || undefined, percentage: p.percentage || undefined, target: p.target || undefined })),
      teamID
    };
    if (expirationDate) body.expirationDate = isoMs(expirationDate);
    return d('Trio profile upload', 'POST', '/api/v1/profile.json', 'secret', [
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:765-857',
      TR + 'Models/NightscoutStatus.swift:34-73',
      TR_API + ':407-441', SRC_TR_ENCODER
    ], { body, notes: 'Single JSON object. No _id, no created_at. carbs_hr is Int(min5mCarbimpact*12/isf*cr) (0 here). overridePresets entries drop 0-valued duration/percentage/target (OverrideStorage.swift:396-406). Succeeds only on HTTP 200 exactly (NightscoutAPI.swift:438). mmol users: sens/targets converted with asMmolL (rounding approximated here).' });
  },

  overrideStart ({ now, name, durationMin }) {
    const body = [{ duration: durationMin === null || durationMin === undefined ? 43200 : Math.trunc(durationMin), eventType: 'Exercise', created_at: isoMs(now), enteredBy: 'Trio', notes: name || 'Custom Override' }];
    return d('Trio override start (Exercise)', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/OverrideStorage.swift:270-280',
      TR + 'Models/NightscoutExercise.swift:3-30',
      'Trio@e41c9db37 Model/Helper/OverrideStored+helper.swift:35',
      TR_API + ':477-510'
    ], { body, notes: 'Indefinite = 43200 min. id is excluded by NightscoutExercise CodingKeys, so nothing identifies the entry except created_at+eventType.' });
  },

  overrideEnd ({ startedAt, endedAt, name, originalDurationMin }) {
    const createdAt = isoMs(startedAt);
    const dur = Math.max(1, Math.trunc((endedAt - startedAt) / 60000));
    return [
      d('Trio override end: DELETE placeholder by created_at+eventType', 'DELETE',
        '/api/v1/treatments.json?' + qFoundation([['find[created_at][$eq]', createdAt], ['find[eventType][$eq]', 'Exercise']]), 'secret', [
          TR + 'Services/Network/Nightscout/NightscoutManager.swift:1198-1219',
          TR_API + ':445-475'
        ], { notes: 'created_at is the encoded ISO string (fractional seconds, Z). A failed DELETE aborts the batch before the POST (retried later). originalDurationMin=' + originalDurationMin + ' is what the deleted placeholder carried.' }),
      d('Trio override end: re-POST run with actual duration', 'POST', '/api/v1/treatments.json', 'secret', [
        TR + 'APS/Storage/OverrideStorage.swift:283-316',
        TR + 'Services/Network/Nightscout/NightscoutManager.swift:1216-1219',
        TR_API + ':477-510'
      ], { body: [{ duration: dur, eventType: 'Exercise', created_at: createdAt, enteredBy: 'Trio', notes: name || 'Custom Override' }], notes: 'duration = Int(max(1, (end-start)/60)).' })
    ];
  },

  tempTargetStart ({ now, id, target, durationMin = 60, name }) {
    const body = [{ duration: Math.trunc(durationMin), eventType: 'Temporary Target', created_at: isoMs(now), enteredBy: 'Trio', notes: name || 'Temp Target', targetTop: target, targetBottom: target }];
    return d('Trio temp target start', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/TempTargetsStorage.swift:311-330',
      'Trio@e41c9db37 Model/Helper/PumpEvent+helper.swift:66',
      SRC_TR_TREAT_KEYS, TR_API + ':298-336'
    ], { body, notes: 'Code contradicts the summary: no id, no units, no reason are sent (id ' + (id || '-') + ' stays local). targetTop == targetBottom; the fallback default is 100 mg/dL or 100.asMmolL, so the value follows the user\'s units.' });
  },

  tempTargetEnd ({ id, startedAt, endedAt, target, name }) {
    const dur = Math.max(1, Math.trunc((endedAt - startedAt) / 60000));
    return [d('Trio temp target end: second POST, same created_at, actual duration', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/TempTargetsStorage.swift:355-376',
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:1298-1306',
      SRC_TR_TREAT_KEYS
    ], { body: [{ duration: dur, eventType: 'Temporary Target', created_at: isoMs(startedAt), enteredBy: 'Trio', notes: name || 'Temp Target', targetTop: target, targetBottom: target }], notes: 'No DELETE first; relies on the server de-duplicating by created_at+eventType. id ' + (id || '-') + ' is never sent.' })];
  },

  bolus ({ now, id, units, smb = false }) {
    return d('Trio bolus', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/PumpHistoryStorage.swift:391-401,423-444',
      'Trio@e41c9db37 Model/Helper/PumpEvent+helper.swift:43-47',
      SRC_TR_TREAT_KEYS, TR_API + ':298-336'
    ], { body: [{ eventType: smb ? 'SMB' : 'Bolus', created_at: isoMs(now), enteredBy: 'Trio', insulin: units, id }], notes: 'No isSMB/type field: only eventType ("SMB" | "Bolus" | "External Insulin") distinguishes them.' });
  },

  carbs ({ now, id, grams, fat = 0, protein = 0, note }) {
    const b = dropUndef({ eventType: 'Carb Correction', created_at: isoMs(now), enteredBy: 'Trio', notes: note, carbs: grams, fat, protein, foodType: note, id });
    return d('Trio carbs', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/CarbsStorage.swift:503-525', SRC_TR_TREAT_KEYS, TR_API + ':298-336'
    ], { body: [b], notes: 'Fat/protein equivalents are separate Carb Correction docs sharing id = fpuID (CarbsStorage.swift:546-565).' });
  },

  carbDelete ({ id }) {
    return d('Trio carb delete', 'DELETE', '/api/v1/treatments.json?' + qFoundation([['find[id][$eq]', id]]), 'secret', [
      TR_API + ':160-190',
      TR + 'Modules/History/HistoryStateModel+Deletion/HistoryStateModel+Carbs.swift:83,100'
    ], { notes: 'For fat/protein meals the id is the shared fpuID, so one DELETE removes every equivalent entry.' });
  },

  tempBasal ({ now, id, rate, durationMin = 30 }) {
    return d('Trio temp basal', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/PumpHistoryStorage.swift:445-464', SRC_TR_TREAT_KEYS
    ], { body: [{ duration: Math.trunc(durationMin), absolute: rate, rate, eventType: 'Temp Basal', created_at: isoMs(now), enteredBy: 'Trio', id }] });
  },

  suspend ({ now, id }) {
    return d('Trio pump suspend (Note)', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/PumpHistoryStorage.swift:465-483', TR + 'Models/PumpHistoryEvent.swift:73'
    ], { body: [{ eventType: 'Note', created_at: isoMs(now), enteredBy: 'Trio', notes: 'PumpSuspend' }], notes: 'No id is sent (id ' + (id || '-') + ' stays local).' });
  },

  resume ({ now, id }) {
    return d('Trio pump resume (Note)', 'POST', '/api/v1/treatments.json', 'secret', [
      TR + 'APS/Storage/PumpHistoryStorage.swift:484-502', TR + 'Models/PumpHistoryEvent.swift:74'
    ], { body: [{ eventType: 'Note', created_at: isoMs(now), enteredBy: 'Trio', notes: 'PumpResume' }], notes: 'No id is sent (id ' + (id || '-') + ' stays local).' });
  },

  entries ({ readings, idSeed = 'trio-sgv' }) {
    const body = readings.map((r) => dropUndef({
      id: uuid(idSeed + ':' + r.t, { upper: true }), sgv: r.sgv, direction: r.direction,
      date: Math.round(r.t), dateString: isoMs(r.t), unfiltered: r.sgv, filtered: r.sgv, glucose: r.sgv, type: 'sgv'
    }));
    return d('Trio CGM entries', 'POST', '/api/v1/entries.json', 'secret', [
      TR + 'APS/Storage/GlucoseStorage.swift:559-587', TR + 'Models/BloodGlucose.swift:60-76', TR_API + ':338-371'
    ], { body, notes: 'Chunks of 100. No device field, no _id.' });
  },

  devicestatus ({ now, iob, cob, bg, eventualBG, predBGs, rate, durationMin = 30, smb = 0, reservoir, battery }) {
    const t = isoMs(now);
    const det = dropUndef({ reason: 'lab synthetic', units: smb || undefined, eventualBG, rate, duration: durationMin, IOB: iob, COB: cob, predBGs: predBGs ? { IOB: predBGs } : undefined, deliverAt: t, temp: 'absolute', bg, timestamp: t });
    const body = {
      device: 'Trio',
      openaps: {
        iob: { iob, activity: 0, basaliob: 0, bolusiob: iob, netbasalinsulin: 0, bolusinsulin: 0, time: t },
        suggested: det,
        enacted: Object.assign({}, det, { received: true }),
        version: '0.0.0-lab',
        dosingMode: 'closed'
      },
      pump: dropUndef({ clock: t, battery: battery !== undefined ? { percent: battery, string: 'normal', display: true } : undefined, reservoir, status: { status: 'normal', bolusing: false, suspended: false, timestamp: t }, bolusIncrement: 0.05 }),
      uploader: { battery: 90, isCharging: false }
    };
    return d('Trio devicestatus', 'POST', '/api/v1/devicestatus.json', 'secret', [
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:654-689',
      TR + 'Models/NightscoutStatus.swift:3-32', TR + 'Models/Determination.swift:50-85',
      TR + 'Models/IOBEntry.swift:3-13', TR_API + ':373-405'
    ], { body, notes: 'Single object; NO created_at and no _id (server must stamp it). enacted omitted when automation is off. uploader.batteryVoltage is always nil (omitted). dosingMode raw value is a placeholder here.' });
  },

  /** Emulates onboarding import: GET /api/v1/profile.json?count=1, decode [FetchedNightscoutProfileStore],
   * read store["default"], then OnboardingStateModel+Nightscout validation. */
  canImport (resp) {
    const source = [
      TR_API + ':512-556', TR + 'Models/RawFetchedProfile.swift:3-11', TR + 'Models/NightscoutStatus.swift:34-51',
      TR + 'Modules/Onboarding/OnboardingStateModel+Nightscout.swift:60-150'
    ];
    const no = (reason) => ({ ok: false, reason, source });
    if (!Array.isArray(resp)) return no('response is not a JSON array');
    const doc = resp[0];
    if (!doc) return no('empty array');
    const isStr = (v) => typeof v === 'string';
    const isNum = (v) => typeof v === 'number' && Number.isFinite(v); // Swift Decimal decodes JSON numbers only
    for (const k of ['_id', 'defaultProfile', 'startDate', 'enteredBy', 'created_at']) if (!isStr(doc[k])) return no('decode fails: ' + k + ' missing or not a string');
    if (!isNum(doc.mills)) return no('decode fails: mills must be a JSON number (Loop uploads it as a string)');
    if (!doc.store || typeof doc.store !== 'object') return no('decode fails: store missing');
    for (const [name, p] of Object.entries(doc.store)) {
      if (!p || typeof p !== 'object') return no('decode fails: store.' + name + ' not an object');
      if (!isNum(p.dia) || !Number.isInteger(p.carbs_hr) || !isNum(p.delay) || !isStr(p.timezone) || !isStr(p.units)) return no('decode fails: store.' + name + ' needs numeric dia, integer carbs_hr, numeric delay, string timezone and units (every store entry is decoded, not only "default")');
      for (const k of ['target_low', 'target_high', 'sens', 'basal', 'carbratio']) {
        if (!Array.isArray(p[k]) || p[k].some((it) => !it || !isStr(it.time) || !isNum(it.value) || (it.timeAsSeconds !== undefined && !Number.isInteger(it.timeAsSeconds)))) return no('decode fails: store.' + name + '.' + k + ' items need string time, numeric value, integer timeAsSeconds if present');
      }
    }
    const p = doc.store.default;
    if (!p) return no('Cannot find the Nightscout Profile named "default" (key hard-coded; defaultProfile ignored)');
    if (p.carbratio.some((x) => x.value <= 0)) return no('Invalid Carb Ratio settings in Nightscout. Import aborted.');
    if (p.basal.some((x) => x.value <= 0)) return no('Invalid Nightscout basal rates found. Import aborted.');
    if (p.basal.reduce((s, x) => s + x.value, 0) <= 0) return no('Invalid Nightscout basal rates found. Basal rate total cannot be 0 U/hr. Import aborted.'); // reachable only for an empty basal array
    const toMgdl = p.units.includes('mmol') || p.target_low.some((x) => x.value <= 39) || p.target_high.some((x) => x.value <= 39);
    if (p.sens.some((x) => x.value <= 0)) return no('Invalid Nightscout insulin sensitivity profile. Import aborted.');
    return { ok: true, reason: 'importable' + (toMgdl ? '; ISF/targets treated as mmol/L and converted' : '') + '; targets taken from target_low only (high = low); response mime type must be exactly application/json', source };
  },

  /** What "Allow downloads" would import from a treatments response (last 24 h). */
  downloads (treatments, opts) {
    const source = [
      TR_API + ':23-29,108-137,260-274', TR + 'Services/Network/Nightscout/NightscoutManager.swift:409-437',
      TR + 'APS/FetchTreatmentsManager.swift:30-72', TR + 'APS/Storage/CarbsStorage.swift:79-106',
      TR + 'Models/CarbsEntry.swift:3-39', TR + 'Models/TempTarget.swift:3-18,49-61'
    ];
    const now = (opts && opts.now) || Date.now();
    const since = now - 86400000; // syncDate() = now - 1 day
    const existingCarbDates = new Set(((opts && opts.existingCarbDates) || []));
    const existingTTDates = new Set(((opts && opts.existingTempTargetDates) || []));
    const out = { carbs: [], tempTargets: [], skipped: [], source };
    const list = Array.isArray(treatments) ? treatments : [];
    const tOf = (x) => Date.parse(x && x.created_at);
    const serverSide = (x) => !TR_EXCLUDED.includes(x.enteredBy) && tOf(x) > since;
    const carbDocs = list.filter((x) => x && x.carbs !== undefined && x.carbs !== null && serverSide(x));
    // [CarbsEntry] decodes as one array: a single bad element makes fetchCarbs throw -> [] for all
    const badCarb = carbDocs.find((x) => typeof x.carbs !== 'number' || isNaN(tOf(x)));
    if (badCarb) carbDocs.forEach((x) => out.skipped.push({ t: x.created_at, why: 'carbs: whole array decode fails (a document has non-numeric carbs or bad created_at)' }));
    else {
      for (const x of carbDocs) {
        const dt = Date.parse(x.actualDate || x.created_at);
        if (existingCarbDates.has(dt)) out.skipped.push({ t: x.created_at, why: 'carbs: same date as a stored entry' });
        else out.carbs.push(x);
      }
    }
    const ttDocs = list.filter((x) => x && x.eventType === 'Temporary Target' && x.duration !== undefined && x.duration !== null && serverSide(x));
    const badTT = ttDocs.find((x) => typeof x.duration !== 'number' || isNaN(tOf(x)));
    if (badTT) ttDocs.forEach((x) => out.skipped.push({ t: x.created_at, why: 'temp target: whole array decode fails' }));
    else {
      const sorted = ttDocs.slice().sort((a, b) => tOf(a) - tOf(b));
      sorted.forEach((x, i) => {
        if (existingTTDates.has(tOf(x))) out.skipped.push({ t: x.created_at, why: 'temp target: one with the same created_at exists' });
        else if (x.reason === 'Cancel') out.skipped.push({ t: x.created_at, why: 'temp target: reason "Cancel"' });
        else out.tempTargets.push(Object.assign({}, x, { enabled: i === sorted.length - 1 }));
      });
    }
    for (const x of list) {
      if (x && (TR_EXCLUDED.includes(x.enteredBy))) out.skipped.push({ t: x.created_at, why: 'server-side $ne filter on enteredBy ' + x.enteredBy });
    }
    return out;
  },

  /** Trio with Nightscout as its CGM: the entries GET. syncDate = date of the newest stored
   * reading from the last 24 h, else Date.distantPast (fresh install / gap > 1 day). */
  nsCgmFetch ({ syncDate }) {
    const since = syncDate === undefined || syncDate === null ? TRIO_DISTANT_PAST : isoMs(syncDate);
    return d('Trio Nightscout-as-CGM fetch', 'GET', '/api/v1/entries/sgv.json?' + qFoundation([['count', '1600'], ['find[dateString][$gte]', since]]), 'secret', [
      TR_API + ':13-14,68-106',
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:355-384,394-402',
      TR + 'APS/Storage/GlucoseStorage.swift:364-391',
      TR + 'Helpers/Formatters.swift:19-23'
    ], { notes: 'count first, then find[dateString][$gte] with fractional seconds ("...:00.000Z"); ":" stays literal, brackets percent-encoded. api-secret only (no Content-Type). Any decode error (e.g. an unknown direction string, a missing dateString) makes the whole response count as [] (NightscoutAPI.swift:100-103). Each returned reading gets glucose = sgv. ' + (since === TRIO_DISTANT_PAST ? 'distantPast rendering by ISO8601DateFormatter is inferred, not captured.' : '') });
  },

  /** What Trio POSTs back after storing readings fetched from Nightscout, when "upload" and
   * "upload glucose" are on (uploadGlucose defaults to true and the NS source has no CGM manager
   * to override it). opts: { syncDate, existingDates }. */
  reuploadFetched ({ entries, syncDate = null, existingDates = [] }) {
    const source = [
      TR + 'APS/FetchGlucoseManager.swift:268-303',
      TR + 'APS/Storage/GlucoseStorage.swift:45-46,116-143,172-213,254-262,419-433,544-586',
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:87-88,895-898,966-984',
      TR + 'Models/BloodGlucose.swift:60-121',
      TR_API + ':68-106,338-371', SRC_TR_ENCODER
    ];
    const list = (Array.isArray(entries) ? entries : []).filter((e) => e && typeof e.dateString === 'string' && !isNaN(Date.parse(e.dateString)));
    // decode: glucose = Int(sgv); date re-derived later from dateString (NOT the fetched `date`)
    const fetched = list.map((e) => ({ t: Date.parse(e.dateString), sortKey: typeof e.date === 'number' ? e.date : Date.parse(e.dateString), sgv: Math.max(39, Math.trunc(Number(e.sgv) || 0)), direction: e.direction }));
    const cut = syncDate === null || syncDate === undefined ? -Infinity : syncDate;
    const newer = fetched.filter((r) => r.t > cut).sort((a, b) => a.sortKey - b.sortKey);
    const kept = []; let last = cut;
    for (const r of newer) { if (r.t - 210000 > last) { kept.push(r); last = r.t; } } // filterTooFrequentGlucose: 3.5 min
    const stored = kept.filter((r) => !existingDates.some((x) => Math.abs(x - r.t) <= 1000)); // storeGlucose: 1 s de-dup
    const out = trio.entries({ readings: stored.map((r) => ({ t: r.t, sgv: r.sgv, direction: r.direction })), idSeed: 'trio-reupload' });
    return d('Trio re-upload of readings fetched from Nightscout', 'POST', '/api/v1/entries.json', 'secret', source, {
      body: out.body,
      notes: 'Same body shape as trio.entries (one BloodGlucose per stored reading): the only link to the fetched document is dateString. id is a NEW upper-case UUID per stored reading (random UUID() in GlucoseStorage.swift:255; derived from the date here); the Nightscout _id and device are not carried over, no device key is added. date = round(dateString ms). filtered/unfiltered/glucose = sgv, clamped to >= 39. Readings within 3.5 min of the previous kept one (or of syncDate) are not stored, so they are not re-uploaded. Readings at or before syncDate go through backfill instead (not modelled). Chunks of 100; marked uploaded on 2xx. ' + (list.length - stored.length) + ' of ' + list.length + ' fetched readings not re-posted.'
    });
  },

  /** Onboarding "import from Nightscout" (GET /api/v1/profile.json?count=1): what lands in the
   * therapy editors. Emulates OnboardingStateModel+Nightscout.swift and finalizeImport's picker
   * snapping. opts: { pumpBasalGrid } overrides the default (Omnipod) basal grid. */
  importSummary (resp, opts) {
    const source = [
      TR + 'Modules/Onboarding/OnboardingStateModel+Nightscout.swift:53-240',
      TR_API + ':512-556',
      TR + 'Services/Network/Nightscout/NightscoutManager.swift:881-893',
      TR + 'Modules/Onboarding/View/OnboardingSteps/Nightscout/NightscoutImportStepView.swift:77-91',
      TR + 'Modules/Onboarding/OnboardingStateModel.swift:116-161,603-638,791-795',
      TR + 'Models/DecimalPickerSettings.swift:11-32,135',
      TR + 'Models/BloodGlucose.swift:196-200,219-226',
      TR + 'Helpers/Rounding.swift:3-8',
      TR + 'APS/Devices/DeviceCatalog.swift:118-149,402-411,485-488',
      'OmnipodKit@4e923d7 OmnipodKit/PumpManager/OmniPumpManager.swift:2353-2362',
      'OmnipodKit@4e923d7 OmnipodKit/OmnipodCommon/Pod.swift:15-18'
    ];
    const DEFAULT_MSG = 'Cannot find the Nightscout Profile named "default".';
    const ALERT_TAIL = '\n\nTry again in a moment, or configure your Therapy Settings manually instead.';
    const fail = (reason, userMessage) => ({ ok: false, reason, userMessage, alert: { title: 'Import Failed', message: userMessage + ALERT_TAIL }, imported: null, losses: [], source });
    const c = trio.canImport(resp);
    if (!c.ok) {
      const shown = /Import aborted\.$/.test(c.reason) ? c.reason : DEFAULT_MSG;
      return fail(c.reason + (shown === DEFAULT_MSG ? ' (importSettings() returns nil; the API\'s own error text is not shown)' : ''), shown);
    }
    const p = resp[0].store.default;
    const losses = [];
    const convert = p.units.includes('mmol') || p.target_low.some((x) => x.value <= 39) || p.target_high.some((x) => x.value <= 39);
    const unitsMmol = p.units.includes('mmol');
    if (convert && !unitsMmol) losses.push('units say ' + JSON.stringify(p.units) + ' but a target is <= 39, so ISF and targets are treated as mmol/L and converted; Trio units stay mg/dL');
    const asMgdL = (v) => trioRound(v / 0.0555, 0);
    const asMmolL = (v) => trioRound(v * 0.0555, 1);
    const sensMg = p.sens.map((x) => ({ time: x.time, value: convert ? asMgdL(x.value) : x.value }));
    if (sensMg.some((x) => x.value <= 0)) return fail('ISF <= 0 after mmol conversion/rounding', 'Invalid Nightscout insulin sensitivity profile. Import aborted.');
    // offset(): Int(prefix(2)) hours, Int(suffix(2)) minutes, 0 when unparsable
    const offMin = (t) => { const s = String(t); const h = parseInt(s.slice(0, 2), 10); const m = parseInt(s.slice(-2), 10); return (/^\d+$/.test(s.slice(0, 2)) ? h : 0) * 60 + (/^\d+$/.test(s.slice(-2)) ? m : 0); };
    const grid = (min, max, step) => { const out = []; for (let i = 0; min + i * step <= max + 1e-9; i++) out.push(round(min + i * step, 4)); return out; };
    const glucoseGrid = (min, max) => {
      const g = grid(min, max, 1);
      if (!unitsMmol) return g;
      const seen = new Set(); return g.filter((v) => { const k = asMmolL(v).toFixed(1); if (seen.has(k)) return false; seen.add(k); return true; });
    };
    const basalGrid = (opts && opts.pumpBasalGrid) || grid(0.05, 30, 0.05); // Omnipod onboarding grid (default pump before one is chosen)
    const grids = { carbratio: grid(1, 50, 0.1), basal: basalGrid, sens: glucoseGrid(9, 540), target: glucoseGrid(72, 180) };
    const closest = (v, g) => g.reduce((bi, x, i) => (Math.abs(x - v) < Math.abs(g[bi] - v) ? i : bi), 0); // min(by:) keeps the first on ties
    const snap = (kind, arr) => {
      const g = grids[kind];
      let rows = arr.map((x) => {
        const m = offMin(x.time);
        const onGrid = m % 30 === 0 && m < 1440;
        if (!onGrid) losses.push(kind + ' ' + x.time + ': not on the 30-minute grid -> 00:00');
        const v = g[closest(x.value, g)];
        if (round(v, 4) !== round(x.value, 4)) losses.push(kind + ' ' + x.time + ': ' + x.value + ' -> ' + v + ' (picker step/range)');
        return { timeIndex: onGrid ? m / 30 : 0, value: v };
      });
      // validated(): Set on (timeIndex, value), sort by time, first entry forced to 00:00
      const seen = new Set(); const before = rows.length;
      rows = rows.filter((r) => { const k = r.timeIndex + '|' + r.value; if (seen.has(k)) return false; seen.add(k); return true; }).sort((a, b) => a.timeIndex - b.timeIndex);
      if (rows.length < before) losses.push(kind + ': ' + (before - rows.length) + ' identical time+value entr' + (before - rows.length === 1 ? 'y' : 'ies') + ' collapsed');
      const dupTimes = rows.filter((r, i) => i && rows[i - 1].timeIndex === r.timeIndex).length;
      if (dupTimes) losses.push(kind + ': ' + dupTimes + ' entr' + (dupTimes === 1 ? 'y shares' : 'ies share') + ' a start time with a different value; both stay, order not defined (Set)');
      if (rows.length && rows[0].timeIndex !== 0) { losses.push(kind + ': first entry moved to 00:00'); rows[0].timeIndex = 0; }
      return rows.map((r) => ({ time: pad2(Math.floor(r.timeIndex / 2)) + ':' + (r.timeIndex % 2 ? '30' : '00'), value: r.value }));
    };
    const tLow = p.target_low.map((x) => ({ time: x.time, value: convert ? asMgdL(x.value) : x.value }));
    if (p.target_high.some((h, i) => !p.target_low[i] || h.value !== p.target_low[i].value)) losses.push('target_high ignored: every target is imported as low = high = target_low');
    const target = snap('target', tLow).map((r) => ({ time: r.time, low: r.value, high: r.value }));
    const imported = {
      units: unitsMmol ? 'mmol/L' : 'mg/dL',
      basal: snap('basal', p.basal),
      sens: snap('sens', sensMg),
      carbratio: snap('carbratio', p.carbratio),
      target_low_used_for_both: target,
      dia: { fromNightscout: p.dia, imported: false, atCompletion: 10 }
    };
    losses.push('DIA not imported: store.default.dia = ' + p.dia + ' h is ignored; onboarding saves the picker default (10 h) as insulinActionCurve');
    const others = Object.keys(resp[0].store).filter((k) => k !== 'default');
    if (others.length) losses.push('other profiles ignored (' + others.join(', ') + '); defaultProfile ' + JSON.stringify(resp[0].defaultProfile) + ' is not consulted');
    return { ok: true, reason: c.reason, userMessage: null, imported, losses, source, notes: 'sens and targets are in mg/dL (Trio stores mg/dL; mmol users see asMmolL of the same value). Picker grids: CR 1-50 step 0.1, ISF 9-540 mg/dL, targets 72-180 mg/dL, basal = default pump grid. The user reviews each editor afterwards; losses listed here happen before that review.' };
  }
};

// ---------------------------------------------------------------------------
// AndroidAPS
// ---------------------------------------------------------------------------
const A34 = 'AndroidAPS@598e2eb39c ';
const A40 = 'AndroidAPS@7e1d537d49 ';
const A34_V3X = A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/';
const A40_V3X = A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/';
const A34_V1X = A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/';
const A34_MAPPER = A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/mapper/TreatmentMapper.kt';
const A40_MAPPER = A40 + 'core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/TreatmentMapper.kt';
const A34_CLIENT = A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/NSAndroidClientImpl.kt';
const A40_CLIENT = A40 + 'core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/NSAndroidClientImpl.kt';
const A34_API = A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NightscoutRemoteService.kt';
const A40_API = A40 + 'core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/networking/NightscoutApi.kt';
const A34_SOCK = A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/services/NSClientService.kt:361-374,595-621';
const A34_V1PLUGIN = A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/NSClientPlugin.kt:196-248';
const A34_AUTH = A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NightscoutAuthRefreshService.kt:14';
const A40_AUTH = A40 + 'core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/networking/NsAuth.kt:45-46,90';
const A34_DATE = A34 + 'shared/impl/src/main/kotlin/app/aaps/shared/impl/utils/DateUtilImpl.kt:64-73';

function variantOf (v) {
  const variant = v || 'v3-34';
  if (!['v3-34', 'v1-34', 'v3-40'].includes(variant)) throw new Error('unknown AAPS variant ' + variant);
  return variant;
}
function aapsV3Src (variant, ext, extLines34, extLines40, mapperLines34, mapperLines40) {
  return variant === 'v3-40'
    ? [A40_V3X + ext + ':' + extLines40, A40_MAPPER + ':' + mapperLines40, A40_API + ':160-173', A40_CLIENT + ':370-380', A40_AUTH]
    : [A34_V3X + ext + ':' + extLines34, A34_MAPPER + ':' + mapperLines34, A34_API + ':65-71', A34_CLIENT + ':293-300', A34_AUTH];
}
function v3Create (label, variant, collection, body, src, notes) {
  return d(label, 'POST', '/api/v3/' + collection, 'jwt', src, { body: Object.assign(body, { app: 'AAPS' }), notes: (notes ? notes + ' ' : '') + 'identifier is omitted on create: it is ids.nightscoutId, null for a new local record (server assigns; AAPS stores the returned one).' });
}
function v1Emit (label, event, collection, data, src, notes, id) {
  const payload = { collection, data };
  if (id) payload._id = id;
  return d(label, 'POST', '/socket.io/', 'socket', src.concat([A34_SOCK, A34_V1PLUGIN]), { socket: { event, collection, data: payload }, notes: 'Not HTTP: socket.io emit("' + event + '", ' + (id ? '{collection,_id,data}' : '{collection,data}') + ') after emit("authorize", {client:"Android_AAPS", history:48, status:true, from, secret:sha1(API_SECRET)}). socket.data is the exact emitted message.' + (notes ? ' ' + notes : '') });
}
const pumpIds = (now) => ({ pumpId: Math.floor(now / 1000), pumpType: 'GENERIC_AAPS', pumpSerial: 'LAB0001' });
function aapsProfileEntry (variant, p, units) {
  const items = (arr) => arr.map(([t, v]) => ({ time: String(t).slice(0, 5), timeAsSeconds: secs(t), value: v }));
  const e = {};
  if (variant !== 'v3-40') e.dia = p.dia !== undefined ? p.dia : 5;
  e.carbratio = items(p.carbratio);
  e.sens = items(p.sens);
  e.basal = items(p.basal);
  e.target_low = p.target.map(([t, lo]) => ({ time: String(t).slice(0, 5), timeAsSeconds: secs(t), value: lo }));
  e.target_high = p.target.map(([t, , hi]) => ({ time: String(t).slice(0, 5), timeAsSeconds: secs(t), value: hi }));
  e.units = units;
  e.timezone = p.timezone || 'Etc/UTC';
  return e;
}
const TT_REASON = { custom: 'Custom', hypo: 'Hypo', activity: 'Activity', eatingsoon: 'Eating Soon', automation: 'Automation', wear: 'Wear' };
const ttReason = (r) => TT_REASON[String(r || 'custom').toLowerCase().replace(/[\s_]/g, '')] || r;

const aaps = {
  profileStore ({ variant, now, units = 'mg/dl', defaultProfile, profiles }) {
    variant = variantOf(variant);
    const names = Object.keys(profiles || {});
    const store = {};
    for (const n of names) store[n] = aapsProfileEntry(variant, profiles[n], units === 'mmol' ? 'mmol' : 'mg/dl');
    const body = {};
    if (names.length) body.defaultProfile = variant === 'v3-40' ? names[0] : (defaultProfile || names[0]);
    body.date = now; body.created_at = aapsIsoAsUTC(now); body.startDate = aapsIsoAsUTC(now); body.store = store;
    const src34 = [A34 + 'plugins/main/src/main/kotlin/app/aaps/plugins/main/profile/ProfilePlugin.kt:398-424', A34_DATE];
    if (variant === 'v1-34') return v1Emit('AAPS v1 profile store (dbAdd)', 'dbAdd', 'profile', body, src34.concat([A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt:786-803']), 'No app field on v1. now = LocalProfileLastChange (ms); created_at has 7 fraction digits ("...SSS0000Z").');
    const src = variant === 'v3-40'
      ? [A40 + 'implementation/src/commonMain/kotlin/app/aaps/implementation/profile/ProfileRepositoryImpl.kt:641-663', A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt:966-984', A40_API + ':237-239', A40_CLIENT + ':516-519', A40_AUTH]
      : src34.concat([A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt:712-727', A34_API + ':102', A34_CLIENT + ':436-440', A34_AUTH]);
    return d('AAPS ' + variant + ' profile store', 'POST', '/api/v3/profile', 'jwt', src, {
      body: Object.assign(body, { app: 'AAPS' }),
      notes: 'No top-level units (per profile only). date/created_at/startDate = LocalProfileLastChange. ' + (variant === 'v3-40' ? '4.0-dev: defaultProfile is the FIRST profile (cosmetic), no dia per profile, AAPSCLIENT never uploads.' : 'defaultProfile = currently active profile name; dia present per profile.') + ' created_at has 7 fraction digits ("...SSS0000Z").'
    });
  },

  profileSwitch ({ variant, now, identifier, profileName, percentage = 100, timeshiftH = 0, durationMin = 0, profileJson, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    const timeshift = timeshiftH * 3600000; // PS.timeshift is milliseconds (core/data PS.kt:22)
    const durMs = durationMin * 60000;
    let custom = profileName;
    if (timeshift !== 0 || percentage !== 100) custom += ' (' + percentage + '%' + (timeshift !== 0 ? ',' + timeshiftH + 'h' : '') + ')';
    const pj = JSON.stringify(profileJson || {});
    if (variant === 'v1-34') {
      const data = { timeshift, percentage, duration: durationMin, profile: custom, originalProfileName: profileName, originalDuration: durMs, created_at: isoMs(now), enteredBy: 'openaps://AndroidAPS', isValid: true, eventType: 'Profile Switch', profileJson: pj };
      return v1Emit('AAPS v1 profile switch (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'ProfileSwitchExtension.kt:16-38', A34 + 'core/objects/src/main/kotlin/app/aaps/core/objects/extensions/ProfileSwitchExtension.kt:15-26'], 'timeshift and originalDuration are milliseconds; duration is minutes. identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = { date: now, utcOffset: utcOffsetMin, isValid: true, eventType: 'Profile Switch', profileJson: pj, profile: custom, originalProfileName: profileName, originalDuration: durMs, duration: durationMin, durationInMilliseconds: durMs, timeshift, percentage };
    return v3Create('AAPS ' + variant + ' profile switch', variant, 'treatments', body,
      aapsV3Src(variant, 'ProfileSwitchExtension.kt', '45-67', '52-77', '512-538', '517-544').concat([A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteTreatment.kt:85']),
      'Wire key is lowercase "timeshift" (ms). profileJson is a STRING of the de-customized profile (timeshift 0, percentage 100). originalDuration stays ms, duration is minutes. No originalPercentage on a PS.' + (variant === 'v3-40' ? ' 4.0-dev also sends iCfg (insulin config); omitted here.' : ''));
  },

  effectiveProfileSwitch ({ variant, now, identifier, profileName, profileJson, percentage = 100, timeshiftH = 0, durationMin = 0, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    let custom = profileName;
    if (timeshiftH !== 0 || percentage !== 100) custom += ' (' + percentage + '%' + (timeshiftH ? ',' + timeshiftH + 'h' : '') + ')';
    const common = { profileJson: JSON.stringify(profileJson || {}), originalProfileName: profileName, originalCustomizedName: custom, originalTimeshift: timeshiftH * 3600000, originalPercentage: percentage, originalDuration: durationMin * 60000, originalEnd: now + durationMin * 60000, notes: custom };
    if (variant === 'v1-34') {
      return v1Emit('AAPS v1 effective profile switch (Note, dbAdd)', 'dbAdd', 'treatments', Object.assign({ created_at: isoMs(now), enteredBy: 'openaps://AndroidAPS', isValid: true, eventType: 'Note' }, common), [A34_V1X + 'EffectiveProfileSwitchExtension.kt:12-31'], 'identifier ' + (identifier || '-') + ' not sent.');
    }
    return v3Create('AAPS ' + variant + ' effective profile switch (Note)', variant, 'treatments',
      Object.assign({ date: now, utcOffset: utcOffsetMin, isValid: true, eventType: 'Note' }, common),
      aapsV3Src(variant, 'EffectiveProfileSwitchExtension.kt', '38-57', '45-66', '486-511', '490-516'),
      'EPS travels as eventType "Note" with original* fields; profileJson has percentage/timeshift applied.' + (variant === 'v3-40' ? ' 4.0-dev adds originalPsId and iCfg; omitted here.' : ''));
  },

  tempTargetStart ({ variant, now, identifier, low, high, durationMin, reason = 'Activity', units = 'mg/dl', utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    const durMs = durationMin * 60000;
    if (variant === 'v1-34') {
      const conv = (v) => (units === 'mmol' ? round(v / 18, 1) : v);
      const data = { eventType: 'Temporary Target', duration: durationMin, durationInMilliseconds: durMs, isValid: true, created_at: isoMs(now), timestamp: now, enteredBy: 'AndroidAPS', reason: ttReason(reason), targetBottom: conv(low), targetTop: conv(high), units };
      return v1Emit('AAPS v1 temp target (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'TemporaryTargetExtension.kt:56-71'], 'v1 sends targets in the USER\'s units with units = profileUtil.units.asText ("mg/dl"|"mmol"); `timestamp` is epoch ms. low/high are given in mg/dL. identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = { date: now, utcOffset: utcOffsetMin, isValid: true, eventType: 'Temporary Target', units: 'mg/dl', duration: durationMin, durationInMilliseconds: durMs, targetBottom: low, targetTop: high, reason: ttReason(reason) };
    return v3Create('AAPS ' + variant + ' temp target', variant, 'treatments', body,
      aapsV3Src(variant, 'TemporaryTargetExtension.kt', '27-44', '26-40', '436-459', '440-463'),
      'v3 always mg/dl.');
  },

  // Cancel = the same record with end = now, sent as an UPDATE because nightscoutId is known
  // (CancelCurrentTemporaryTargetIfAnyTransaction.kt:14; DataSyncSelectorV3.kt:311-312; DataSyncSelectorV1.kt:342-343).
  tempTargetCancel ({ variant, identifier, nsId, startedAt, endedAt, low = 140, high = 140, reason = 'Activity', units = 'mg/dl' }) {
    variant = variantOf(variant);
    const durMs = Math.max(0, endedAt - startedAt);
    const durMin = Math.floor(durMs / 60000);
    if (variant === 'v1-34') {
      const conv = (v) => (units === 'mmol' ? round(v / 18, 1) : v);
      const data = { eventType: 'Temporary Target', duration: durMin, durationInMilliseconds: durMs, isValid: true, created_at: isoMs(startedAt), timestamp: startedAt, enteredBy: 'AndroidAPS', reason: ttReason(reason), targetBottom: conv(low), targetTop: conv(high), units };
      return v1Emit('AAPS v1 temp target cancel (dbUpdate by _id, shortened duration)', 'dbUpdate', 'treatments', data,
        [A34_V1X + 'TemporaryTargetExtension.kt:56-71', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt:336-345'], 'toJson(isAdd=false): no _id inside data; _id rides on the message.', nsId);
    }
    const id = nsId || identifier;
    const body = { identifier: id, isValid: true, eventType: 'Temporary Target', units: 'mg/dl', duration: durMin, durationInMilliseconds: durMs, targetBottom: low, targetTop: high, reason: ttReason(reason) };
    const src = variant === 'v3-40'
      ? [A40_CLIENT + ':411-421', A40_API + ':165-168', A40_V3X + 'TemporaryTargetExtension.kt:26-40']
      : [A34_CLIENT + ':331-341', A34_API + ':68', A34_V3X + 'TemporaryTargetExtension.kt:27-44', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt:301-312'];
    return d('AAPS ' + variant + ' temp target cancel (PATCH, shortened duration)', 'PATCH', '/api/v3/treatments/' + id, 'jwt', src.concat([variant === 'v3-40' ? A40_AUTH : A34_AUTH]), { body, notes: 'updateTreatment nulls date and utcOffset before mapping, so neither is sent. 404 counts as success.' });
  },

  bolus ({ variant, now, identifier, units, smb = false, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    if (variant === 'v1-34') {
      const data = Object.assign({ eventType: smb ? 'Correction Bolus' : 'Meal Bolus', insulin: units, created_at: isoMs(now), date: now, type: smb ? 'SMB' : 'NORMAL', isValid: true, isSMB: smb }, pumpIds(now));
      return v1Emit('AAPS v1 bolus (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'BolusExtension.kt:10-27'], 'notes omitted when null. identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = Object.assign({ date: now, utcOffset: utcOffsetMin, isValid: true, eventType: smb ? 'Correction Bolus' : 'Meal Bolus', insulin: units, type: smb ? 'SMB' : 'NORMAL', isBasalInsulin: false }, pumpIds(now));
    return v3Create('AAPS ' + variant + ' bolus', variant, 'treatments', body,
      aapsV3Src(variant, 'BolusExtension.kt', '26-41', '34-50', '396-414', '399-419'),
      'v3 never sends isSMB (only type "SMB"). Non-SMB boluses are eventType "Meal Bolus".' + (variant === 'v3-40' ? ' 4.0-dev adds iCfg {insulinLabel, insulinEndTime, insulinPeakTime, concentration}; omitted here.' : ''));
  },

  carbs ({ variant, now, identifier, grams, durationMin = 0, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    const ev = grams < 12 ? 'Carb Correction' : 'Meal Bolus';
    if (variant === 'v1-34') {
      const data = { eventType: ev, carbs: grams, created_at: isoMs(now), isValid: true, date: now };
      if (durationMin) data.duration = durationMin * 60000; // v1 sends duration raw in ms
      return v1Emit('AAPS v1 carbs (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'CarbsExtension.kt:13-26'], 'eventType is "Carb Correction" below 12 g else "Meal Bolus". identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = { date: now, utcOffset: utcOffsetMin, isValid: true, eventType: ev, carbs: grams };
    if (durationMin) { body.duration = durationMin; body.durationInMilliseconds = durationMin * 60000; }
    return v3Create('AAPS ' + variant + ' carbs', variant, 'treatments', body,
      aapsV3Src(variant, 'CarbsExtension.kt', '24-38', '23-38', '416-435', '420-439'),
      'eventType "Carb Correction" below 12 g, else "Meal Bolus".');
  },

  tempBasal ({ variant, now, identifier, rate, durationMin = 30, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    const durMs = durationMin * 60000;
    if (variant === 'v1-34') {
      const data = Object.assign({ created_at: isoMs(now), enteredBy: 'openaps://AndroidAPS', eventType: 'Temp Basal', isValid: true, duration: durationMin, durationInMilliseconds: durMs, type: 'NORMAL', rate, absolute: rate }, pumpIds(now));
      return v1Emit('AAPS v1 temp basal (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'TemporaryBasalExtension.kt:13-33'], 'Absolute TBR shown; a percent TBR sends percent = rate-100 instead of absolute. identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = Object.assign({ date: now, utcOffset: utcOffsetMin, isValid: true, eventType: 'Temp Basal', duration: durationMin, durationInMilliseconds: durMs, absolute: rate, rate, type: 'NORMAL' }, pumpIds(now));
    return v3Create('AAPS ' + variant + ' temp basal', variant, 'treatments', body,
      aapsV3Src(variant, 'TemporaryBasalExtension.kt', '28-45', '27-44', '460-485', '464-489'),
      'rate is always the absolute-converted value; absolute only for absolute TBRs, else percent = rate-100.');
  },

  runningMode ({ variant, now, identifier, mode = 'CLOSED_LOOP', durationMin = 0, utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    const durMs = durationMin * 60000;
    const zeroModes = ['OPEN_LOOP', 'CLOSED_LOOP', 'CLOSED_LOOP_LGS'];
    let wireMs = zeroModes.includes(mode) ? 0 : durMs;
    let origMs = durMs;
    if (variant === 'v3-40' && mode === 'DISABLED_LOOP' && !durationMin) { wireMs = 365 * 10 * 86400000; origMs = 0; }
    if (variant === 'v1-34') {
      const data = { created_at: isoMs(now), enteredBy: 'openaps://AAPS', eventType: 'OpenAPS Offline', isValid: true, duration: Math.floor(wireMs / 60000), durationInMilliseconds: wireMs, originalDuration: origMs, mode };
      return v1Emit('AAPS v1 running mode (dbAdd)', 'dbAdd', 'treatments', data, [A34_V1X + 'RunningModeExtension.kt:11-40'], 'identifier ' + (identifier || '-') + ' not sent.');
    }
    const body = { date: now, utcOffset: utcOffsetMin, isValid: true, eventType: 'OpenAPS Offline', duration: Math.floor(wireMs / 60000), durationInMilliseconds: wireMs, reason: 'OTHER', originalDuration: origMs, mode, autoForced: false };
    return v3Create('AAPS ' + variant + ' running mode', variant, 'treatments', body,
      aapsV3Src(variant, 'RunningModeExtension.kt', '24-72', '25-90', '586-612', '592-618'),
      'Loop modes (OPEN/CLOSED/LGS) send duration 0 with originalDuration = real ms; suspend/disable modes send the real duration.' + (variant === 'v3-40' ? ' 4.0-dev: open-ended DISABLED_LOOP sends 10 years and originalDuration 0.' : ''));
  },

  remove ({ variant, identifier, nsId, collection = 'treatments', record }) {
    variant = variantOf(variant);
    if (variant === 'v1-34') {
      const data = Object.assign({}, record || {}, { isValid: false });
      delete data._id;
      return v1Emit('AAPS v1 soft delete (dbUpdate isValid:false)', 'dbUpdate', collection, data, [A34_V1X + 'BolusExtension.kt:10-27', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/NSClientPlugin.kt:218-248'],
        'v1 has no dbRemove/dbUpdateUnset: invalidation re-sends the whole record (toJson(isAdd=false)) with isValid:false. Pass `record` for the full document.', nsId);
    }
    const id = nsId || identifier;
    const coll = collection === 'entries' ? 'entries' : 'treatments';
    const src = variant === 'v3-40'
      ? [A40_CLIENT + (coll === 'entries' ? ':229-230' : ':411-421'), A40_API + (coll === 'entries' ? ':137-139' : ':170-172'), A40_AUTH]
      : [A34_CLIENT + (coll === 'entries' ? ':210-211' : ':331-341'), A34_API + (coll === 'entries' ? ':56' : ':71'), A34_AUTH];
    return d('AAPS ' + variant + ' delete (HTTP DELETE, server soft-deletes)', 'DELETE', '/api/v3/' + coll + '/' + id, 'jwt', src,
      { notes: 'Code contradicts "PATCH isValid:false": when the local record is invalid, updateTreatment calls DELETE /v3/<coll>/{identifier} with no permanent flag (server marks isValid:false). 404 counts as success.' });
  },

  entries ({ variant, readings, sensor = 'Dexcom G6 Native', utcOffsetMin = 0 }) {
    variant = variantOf(variant);
    if (variant === 'v1-34') {
      return readings.map((r) => v1Emit('AAPS v1 sgv (dbAdd)', 'dbAdd', 'entries', { device: sensor, date: r.t, dateString: isoMs(r.t), isValid: true, sgv: r.sgv, direction: r.direction, type: 'sgv' },
        [A34 + 'core/objects/src/main/kotlin/app/aaps/core/objects/extensions/GlucoseValueExtension.kt:12-21'], 'one emit per reading'));
    }
    const src = variant === 'v3-40'
      ? [A40_V3X + 'GlucoseValueExtension.kt:26-40', A40 + 'core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/SvgMapper.kt:42-60', A40_API + ':127-130', A40_CLIENT + ':186', A40_AUTH]
      : [A34_V3X + 'GlucoseValueExtension.kt:27-40', A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/mapper/SvgMapper.kt:42-60', A34_API + ':50', A34_CLIENT + ':167', A34_AUTH];
    return readings.map((r) => d('AAPS ' + variant + ' sgv', 'POST', '/api/v3/entries', 'jwt', src, {
      body: { type: 'sgv', date: r.t, device: sensor, utcOffset: utcOffsetMin, direction: r.direction, sgv: r.sgv, isValid: true, filtered: r.sgv, unfiltered: 0.0, units: 'mg/dl', app: 'AAPS' },
      notes: 'One POST per reading; device = sourceSensor.text; identifier omitted on create. Only when AAPS is set to upload CGM data.'
    }));
  },

  devicestatus ({ variant, now, iob, cob, bg, eventualBG, predBGs, rate, durationMin = 30, smb = 0, reservoir, battery, deviceModel = 'Lab Phone' }) {
    variant = variantOf(variant);
    const t = isoMs(now);
    const suggested = dropUndef({ bg, eventualBG, reason: 'lab synthetic', COB: cob, IOB: iob, rate, duration: durationMin, units: smb || undefined, predBGs: predBGs ? { IOB: predBGs } : undefined, timestamp: t });
    const openaps = { suggested, enacted: Object.assign({}, suggested, { received: true }), iob: { iob, basaliob: 0, activity: 0, time: t } };
    const pump = dropUndef({ clock: t, reservoir, battery: battery !== undefined ? { percent: battery } : undefined, status: { status: 'normal', timestamp: t } });
    const device = 'openaps://' + deviceModel;
    if (variant === 'v1-34') {
      return v1Emit('AAPS v1 devicestatus (dbAdd)', 'dbAdd', 'devicestatus', { created_at: t, device, pump, openaps, uploaderBattery: 80, isCharging: false, configuration: { insulin: 5, sensitivity: 2, smbAlgorithm: 'SMB' } },
        [A34_V1X + 'DeviceStatusExtension.kt:8-22', A34 + 'plugins/aps/src/main/kotlin/app/aaps/plugins/aps/loop/LoopPlugin.kt:1031'], 'device = "openaps://" + Build.MANUFACTURER + " " + Build.MODEL. configuration values are placeholders.');
    }
    const body = { date: now, device, pump, openaps, uploaderBattery: 80, isCharging: false };
    if (variant === 'v3-34') body.configuration = { insulin: 5, sensitivity: 2, smbAlgorithm: 'SMB' };
    body.app = 'AAPS';
    const src = variant === 'v3-40'
      ? [A40_V3X + 'DeviceStatusExtension.kt:7-23', A40_API + ':177-179', A40_CLIENT + ':355', A40_AUTH]
      : [A34_V3X + 'DeviceStatusExtension.kt:10-34', A34_API + ':74', A34_CLIENT + ':274', A34_AUTH];
    return d('AAPS ' + variant + ' devicestatus', 'POST', '/api/v3/devicestatus', 'jwt', src, { body, notes: 'v3 sends date (ms), no created_at, no identifier.' + (variant === 'v3-40' ? ' 4.0-dev drops configuration (moved to /api/v3/settings docs "aaps"/"aaps-state"); device = "openaps://" + config.deviceModelForUpload.' : ' configuration values are placeholders.') });
  },

  /** Would AAPS load this profile store from Nightscout? */
  acceptsProfile ({ variant, nsProfileDoc, localLastChange = 0, acceptSetting, AAPSCLIENT = false, paired = false, doFullSync = false }) {
    variant = variantOf(variant);
    const is40 = variant === 'v3-40';
    const source = is40
      ? [A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NsIncomingDataProcessor.kt:273-293', A40 + 'core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:221', A40 + 'implementation/src/commonMain/kotlin/app/aaps/implementation/profile/ProfileStoreObject.kt:73']
      : [A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NsIncomingDataProcessor.kt:283-294', A34 + 'core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:82', A34 + 'implementation/src/main/kotlin/app/aaps/implementation/profile/ProfileStoreObject.kt:52'];
    if (variant === 'v1-34') source.push(A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/services/NSClientService.kt:476-483');
    const setting = acceptSetting === undefined ? !is40 : !!acceptSetting;
    const gate = is40 ? (AAPSCLIENT ? !paired : (setting || doFullSync)) : (setting || AAPSCLIENT || (variant !== 'v1-34' && doFullSync));
    const fresh = localLastChange === 0 ? 'fresh install (LocalProfileLastChange 0): ' : '';
    const res = (accept, reason) => ({ accept, verdict: accept ? 'ACCEPT' : 'IGNORE', reason: fresh + reason, source });
    if (!gate) return res(false, 'NsClientAcceptProfileStore is ' + setting + ' (default ' + (!is40) + ' on ' + variant + ')' + (is40 && AAPSCLIENT ? '; paired AAPSCLIENT never accepts' : '') + (fresh ? '; the Nightscout profile is not loaded, the user must create one locally or turn the setting on' : ''));
    const doc = nsProfileDoc || {};
    const str = (typeof doc.created_at === 'string' && doc.created_at) || (typeof doc.startDate === 'string' && doc.startDate) || null;
    const createdAt = str ? parseIsoMs(str) : 0;
    if (createdAt > localLastChange) return res(true, 'createdAt ' + createdAt + ' > LocalProfileLastChange ' + localLastChange + (fresh ? ' (any dated store is newer)' : ''));
    if (createdAt % 1000 === 0) return res(true, 'createdAt ' + createdAt + ' is a whole second ("edited in NS")' + (createdAt === 0 ? ' -- note 0 (unparseable/missing date) also passes' : ''));
    return res(false, 'createdAt ' + createdAt + ' <= LocalProfileLastChange and not a whole second (treated as AAPS\'s own echo)');
  },

  /** NSClient first-load reads, in order, on a fresh install (every collection cursor 0).
   * v3: the WorkManager chain (3.4) / NsLoadExecutor chain (4.0-dev), first page of each.
   * v1-34: the socket authorize with from = 0 (the server then pushes its dataUpdate). */
  firstLoad ({ variant, now, nsBgSource = false, nsReceiveCgm = false }) {
    variant = variantOf(variant);
    if (variant === 'v1-34') {
      return [d('AAPS v1 socket authorize (first load, from=0)', 'POST', '/socket.io/', 'socket', [
        A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/services/NSClientService.kt:123-132,308-314,361-375,381',
        A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/services/NSClientService.kt:266',
        A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/services/NSClientService.kt:458-500'
      ], {
        socket: { event: 'authorize', data: { client: 'Android_AAPS', history: 48, status: true, from: 0, secret: '<sha1(API_SECRET)>' } },
        notes: 'Not HTTP: socket.io emit("authorize", data, ack) on connect. Key order as put(): client, history, status, from, secret. secret is the lower-case SHA-1 hex of API_SECRET (the runner substitutes it). from = latestDateInReceivedData, 0 after install or after a URL/secret/pause change. The server answers with a full dataUpdate; AAPS takes the LAST element of "profiles" and queues "treatments" whose action is absent or "update".'
      })];
    }
    const is40 = variant === 'v3-40';
    const since = now - 100 * 86400000; // maxAge = 100 days; first load uses max(0, now - maxAge)
    const W = is40 ? A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/workers/' : A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/workers/';
    const ext = is40 ? 'Runner.kt' : 'Worker.kt';
    const plugin = is40
      ? A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:184,228,1131-1170'
      : A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:144,174,408-412,766-781';
    const api = (l34, l40) => (is40 ? A40_API + ':' + l40 : A34_API + ':' + l34);
    const client = (l34, l40) => (is40 ? A40_CLIENT + ':' + l40 : A34_CLIENT + ':' + l34);
    const base = is40 ? A40_API + ':49-55' : A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NetworkStackBuilder.kt:40';
    const auth = is40 ? A40_AUTH : A34_AUTH;
    const out = [
      d('AAPS ' + variant + ' first load: status', 'GET', '/api/v3/status', 'jwt', [plugin, W + 'LoadStatus' + ext + (is40 ? ':29' : ':26'), api('35-36', '96-97'), client('102-104', '103-105'), base, auth]),
      d('AAPS ' + variant + ' first load: lastModified', 'GET', '/api/v3/lastModified', 'jwt', [W + 'LoadLastModification' + ext + (is40 ? ':29' : ':25'), api('38-39', '99-100'), client('106-110', '123-126'), auth], { notes: 'newestDataOnServer: a collection whose lastModified is not newer than the cursor is skipped below.' })
    ];
    if (nsBgSource || nsReceiveCgm) {
      out.push(d('AAPS ' + variant + ' first load: entries (first page)', 'GET', '/api/v3/entries?' + qLiteral([['sort', 'date'], ['date$gt', String(since)], ['limit', '500']]), 'jwt',
        [W + 'LoadBg' + ext + (is40 ? ':39-63' : ':38-52'), api('44-45', '113-119'), client('149-151', '167-169'), is40 ? A40 + 'core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:220' : A34 + 'core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:81', auth],
        { notes: 'Only when the BG source is "NSClient BG" or ns_receive_cgm is on (or a full sync is running). date$gt is epoch ms, literal "$". Next pages continue from the newest date processed.' }));
    }
    out.push(
      d('AAPS ' + variant + ' first load: treatments (first page)', 'GET', '/api/v3/treatments?' + qLiteral([['sort', 'created_at'], ['created_at$gt', isoMs(since)], ['limit', '500']]), 'jwt',
        [W + 'LoadTreatments' + ext + (is40 ? ':40-52' : ':39-50'), api('59-60', '146-152'), client('230-232', '312-314'), is40 ? A40 + 'shared/impl/src/commonMain/kotlin/app/aaps/shared/impl/utils/DateUtilImpl.kt:76-79' : A34_DATE, auth],
        { notes: 'created_at$gt = toISOString(now - 100 days), "yyyy-MM-ddTHH:mm:ss.SSSZ", sent unencoded (":" literal). Later pages start after the newest treatment of the previous page; once a page is empty the cursor switches to /history/{srvModified}.' }),
      d('AAPS ' + variant + ' first load: food', 'GET', '/api/v3/food?limit=1000', 'jwt', [W + 'LoadFoods' + ext + (is40 ? ':34-35' : ':36-37'), api('80-81', '189-192'), auth], { notes: 'Food has no modification cursor: the whole collection is read on every 5th round, starting with the first.' }),
      d('AAPS ' + variant + ' first load: last profile store', 'GET', '/api/v3/profile?' + qLiteral([['sort$desc', 'date'], ['limit', '1']]), 'jwt',
        [W + 'LoadProfileStore' + ext + (is40 ? ':38-41' : ':38-43'), api('99-100', '230-235'), client('459-461', '541-543'), auth], { notes: 'getLastProfileStore; the store is then handed to processProfile (see acceptsProfile).' + (is40 ? ' 4.0-dev runs a SETTINGS step next; it reads only on an AAPSCLIENT build (LoadSettingsRunner.kt:46).' : '') }),
      d('AAPS ' + variant + ' first load: devicestatus (last 7 min)', 'GET', '/api/v3/devicestatus/history/' + String(now - 7 * 60000), 'jwt',
        [W + 'LoadDeviceStatus' + ext + (is40 ? ':32-33' : ':36-37'), api('77-78', '182-185'), client('261-263', '342-344'), auth], { notes: 'Marks initialLoadFinished; DataSync (uploads) runs after this.' })
    );
    return out;
  },

  /** Which treatments from a first-load page AAPS keeps. Default switches (3.4 and 4.0-dev):
   * every ns_receive_* accept switch false; Bolus Wizard results are not gated. aapsClient = the
   * AAPSCLIENT build flavour, which accepts everything. */
  firstLoadKeeps ({ variant, treatments, aapsClient = false, doFullSync = false }) {
    variant = variantOf(variant);
    const is40 = variant === 'v3-40';
    const v1 = variant === 'v1-34';
    const source = v1
      ? [A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/workers/NSClientAddUpdateWorker.kt:57-159', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TemporaryTargetExtension.kt:13-43', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/EffectiveProfileSwitchExtension.kt:80', A34 + 'core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:83-89']
      : is40
        ? [A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NsIncomingDataProcessor.kt:153-236', A40_MAPPER + ':36-394', A40 + 'core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:222-228', A40 + 'core/data/src/commonMain/kotlin/app/aaps/core/data/configuration/Constants.kt:41']
        : [A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NsIncomingDataProcessor.kt:143-231', A34_MAPPER + ':33-391', A34 + 'core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteTreatment.kt:90-92', A34 + 'core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:83-89', A34 + 'core/data/src/main/kotlin/app/aaps/core/data/configuration/Constants.kt:30-31'];
    const TE = ['Site Change', 'Insulin Change', 'Sensor Change', 'BG Check', '<none>', 'Announcement', 'Question', 'Exercise', 'Note', 'Pump Battery Change'];
    const ttMax = is40 ? 180.16 : 180;
    const all = aapsClient || (!v1 && doFullSync);
    const on = () => all; // every accept switch defaults to false; AAPSCLIENT / full sync override all
    const kept = []; const dropped = [];
    const keep = (t, kind) => kept.push({ eventType: t.eventType, created_at: t.created_at, kind });
    const drop = (t, why) => dropped.push({ eventType: t.eventType, why });
    const num = (v) => typeof v === 'number' && Number.isFinite(v);
    const gate = (t, kind, key) => (on(key) ? keep(t, kind) : drop(t, kind + ': ' + key + ' off (default false)'));
    for (const t of (Array.isArray(treatments) ? treatments : [])) {
      if (!t) continue;
      const ev = t.eventType;
      if (v1) {
        if (ev == null) { drop(t, 'no eventType: ignored'); continue; }
        const ins = num(t.insulin) ? t.insulin : 0; const carbs = num(t.carbs) ? t.carbs : 0;
        if (ins > 0) gate(t, 'bolus', 'NsClientAcceptInsulin');
        if (carbs !== 0) gate(t, 'carbs', 'NsClientAcceptCarbs'); // same document can yield both
        if (ins > 0 || carbs > 0) continue;
        if (ev === 'Temporary Target') {
          if (!on('NsClientAcceptTempTarget')) { drop(t, 'temp target: NsClientAcceptTempTarget off (default false)'); continue; }
          const dur = t.duration;
          const mg = (v) => (/mmol/i.test(t.units || '') ? v * 18 : v);
          if (dur == null) drop(t, 'temp target without duration');
          else if (dur !== 0 && t.reason == null) drop(t, 'temp target without reason');
          else if (dur > 0 && (mg(t.targetBottom) < 72 || mg(t.targetBottom) > 180 || mg(t.targetTop) < 72 || mg(t.targetTop) > 180 || mg(t.targetBottom) > mg(t.targetTop))) drop(t, 'temp target outside 72..180 mg/dL or bottom > top');
          else keep(t, 'temp target');
        } else if (ev === 'Note' && t.originalProfileName !== undefined) gate(t, 'effective profile switch', 'NsClientAcceptProfileSwitch');
        else if (ev === 'Bolus Wizard') keep(t, 'bolus wizard (not gated)');
        else if (TE.includes(ev)) gate(t, 'therapy event', 'NsClientAcceptTherapyEvent');
        else if (ev === 'Combo Bolus' || ev === 'Temp Basal') gate(t, ev === 'Temp Basal' ? 'temp basal' : 'extended bolus', 'NsClientAcceptTbrEb');
        else if (ev === 'Profile Switch') gate(t, 'profile switch', 'NsClientAcceptProfileSwitch');
        else if (ev === 'OpenAPS Offline') { if (aapsClient) keep(t, 'running mode'); else drop(t, 'running mode: needs NsClientAcceptRunningMode AND engineering mode'); }
        else drop(t, 'eventType ' + JSON.stringify(ev) + ' not handled by the v1 worker');
        continue;
      }
      const ts = t.date || t.mills || t.timestamp || (t.created_at ? parseIsoMs(t.created_at) : 0);
      if (num(t.insulin) && t.insulin > 0) { gate(t, 'bolus' + (num(t.carbs) && t.carbs !== 0 ? ' (carbs on the same document are NOT read: the mapper takes the insulin branch)' : ''), 'NsClientAcceptInsulin'); continue; }
      if (t.carbs != null && t.carbs !== 0) { gate(t, 'carbs', 'NsClientAcceptCarbs'); continue; }
      const durMs = t.durationInMilliseconds != null ? t.durationInMilliseconds : (t.duration != null ? t.duration * 60000 : null);
      if (ev === 'Temporary Target') {
        if (!ts) drop(t, 'temp target: no date -> mapper returns null');
        else if (durMs == null) drop(t, 'temp target without duration -> mapper returns null');
        else if (!on('NsClientAcceptTempTarget')) drop(t, 'temp target: NsClientAcceptTempTarget off (default false)');
        else {
          const mg = (v) => (/mmol/i.test(t.units || '') ? v * 18 : v);
          const lo = mg(t.targetBottom); const hi = mg(t.targetTop);
          if (durMs > 0 && (!(lo >= 72 && lo <= ttMax) || !(hi >= 72 && hi <= ttMax) || lo > hi)) drop(t, 'temp target outside 72..' + ttMax + ' mg/dL or bottom > top');
          else keep(t, 'temp target');
        }
      } else if (ev === 'Temp Basal' && t.extendedEmulated != null) gate(t, 'extended bolus (emulated TBR)', 'NsClientAcceptTbrEb');
      else if (ev === 'Temp Basal') {
        if (!ts || (t.absolute == null && t.percent == null) || durMs == null || t.durationInMilliseconds === 0) drop(t, 'temp basal missing date/absolute|percent/duration (or durationInMilliseconds 0) -> mapper returns null');
        else gate(t, 'temp basal', 'NsClientAcceptTbrEb');
      } else if (ev === 'Note' && t.originalProfileName != null) {
        if (!ts || t.profileJson == null || t.originalCustomizedName == null || t.originalTimeshift == null || t.originalPercentage == null) drop(t, 'effective profile switch missing profileJson/original* fields -> mapper returns null');
        else gate(t, 'effective profile switch', 'NsClientAcceptProfileSwitch');
      } else if (ev === 'Profile Switch') {
        if (!ts || t.profile == null) drop(t, 'profile switch without `profile` -> mapper returns null');
        else gate(t, 'profile switch', 'NsClientAcceptProfileSwitch');
      } else if (ev === 'Bolus Wizard') {
        if (t.bolusCalculatorResult == null) drop(t, 'Bolus Wizard without bolusCalculatorResult -> mapper returns null');
        else keep(t, 'bolus wizard (not gated)');
      } else if (TE.includes(ev)) gate(t, 'therapy event', 'NsClientAcceptTherapyEvent');
      else if (ev === 'OpenAPS Offline') gate(t, 'running mode', 'NsClientAcceptRunningMode');
      else if (ev === 'Combo Bolus') {
        if (t.enteredinsulin == null) drop(t, 'Combo Bolus without enteredinsulin -> mapper returns null');
        else gate(t, 'extended bolus', 'NsClientAcceptTbrEb');
      } else drop(t, 'eventType ' + JSON.stringify(ev) + ' is not mapped by the v3 TreatmentMapper (returns null)');
    }
    return { kept, dropped, source, notes: (v1 ? 'v1 has no full-sync override for downloads.' : 'doFullSync (Full sync) accepts like AAPSCLIENT.') + (is40 ? ' The 4.0-dev paired-client rule applies to the profile store only (acceptsProfile), not to treatments.' : '') + ' Kept records are matched by nsId/pumpId in the database, not duplicated.' };
  },

  /** What "Full synchronization" does, and the two dialogs the user sees. */
  fullSyncNote ({ variant }) {
    variant = variantOf(variant);
    const is40 = variant === 'v3-40';
    const q1 = 'Full synchronization? It may take many hours and until finish you\'ll not see new data in NS.';
    const q2 = 'Do you want to cleanup the database?\nIt will remove tracked changes and historic data older than 3 months.\nDoing it will speedup full synchronization dramatically.';
    const source = is40
      ? [A40 + 'plugins/sync/src/androidMain/res/values/strings.xml:73-74', A40 + 'core/ui/src/androidMain/res/values/strings.xml:1009', A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/compose/NSClientComposeContent.kt:37,70-122', A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:228,683-690,1150-1153']
      : [A34 + 'plugins/sync/src/main/res/values/strings.xml:29,45-46', A34 + 'core/ui/src/main/res/values/strings.xml:662', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NSClientFragment.kt:118,146-183'];
    if (variant === 'v1-34') source.push(A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/NSClientPlugin.kt:190-192', A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/DataSyncSelectorV1.kt:143-146');
    else if (!is40) source.push(A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:174,424-433,760-766');
    const dialogs = 'Menu item "Full synchronization" -> dialog "NSClient": "' + q1 + '" -> OK -> second dialog "' + q2 + '" (OK = delete local data older than 93 days and tracked changes first; Cancel = skip the cleanup but still full-sync).';
    const text = variant === 'v1-34'
      ? dialogs + ' On v1 resetToFullSync only clears the UPLOAD cursors (every local record is re-sent); downloads are not reset and the socket "from" is unchanged.'
      : dialogs + ' Then resetToFullSync: every download cursor (lastLoadedSrvModified, firstLoadContinueTimestamp) goes back to 0, initialLoadFinished = false, the upload cursors are reset, and the next round runs with doingFullSync = true: entries, treatments and the profile store are re-read from now - 100 days, and every accept switch is treated as ON for that pass (bolus, carbs, temp targets, TBR/EB, profile switches, therapy events, running mode, CGM). Everything local is re-uploaded as well.';
    return { text, dialogs: [{ title: 'NSClient', message: q1 }, { title: 'NSClient', message: q2 }], source };
  },

  /** Would AAPS apply this incoming treatment? settings: {NsClientAcceptInsulin, ...Carbs, ...TempTarget,
   * ...TbrEb, ...ProfileSwitch, ...TherapyEvent, ...RunningMode, AAPSCLIENT, doFullSync}. All default false. */
  acceptsTreatment ({ variant, treatment, settings = {} }) {
    variant = variantOf(variant);
    const is40 = variant === 'v3-40';
    const source = is40
      ? [A40 + 'plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NsIncomingDataProcessor.kt:153-234', A40 + 'core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt:222-228', A40_MAPPER + ':1-396']
      : [A34 + 'plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NsIncomingDataProcessor.kt:143-229', A34 + 'core/keys/src/main/kotlin/app/aaps/core/keys/BooleanKey.kt:83-89', A34_MAPPER + ':33-393', A34 + 'core/data/src/main/kotlin/app/aaps/core/data/configuration/Constants.kt:30-31'];
    const t = treatment || {};
    const on = (k) => !!settings[k] || !!settings.AAPSCLIENT || !!settings.doFullSync;
    const res = (accept, reason) => ({ accept, reason, source });
    const ts = t.date || Date.parse(t.created_at || '') || 0;
    let kind; let key;
    if (typeof t.insulin === 'number' && t.insulin > 0) { kind = 'bolus'; key = 'NsClientAcceptInsulin'; }
    else if (typeof t.carbs === 'number' && t.carbs !== 0) { kind = 'carbs'; key = 'NsClientAcceptCarbs'; }
    else if (t.eventType === 'Temporary Target') { kind = 'temp target'; key = 'NsClientAcceptTempTarget'; }
    else if (t.eventType === 'Temp Basal') { kind = 'temp basal'; key = 'NsClientAcceptTbrEb'; }
    else if (t.eventType === 'Note' && t.originalProfileName != null) { kind = 'effective profile switch'; key = 'NsClientAcceptProfileSwitch'; }
    else if (t.eventType === 'Profile Switch') { kind = 'profile switch'; key = 'NsClientAcceptProfileSwitch'; }
    else if (t.eventType === 'Bolus Wizard') { kind = 'bolus wizard'; key = null; }
    else if (t.eventType === 'OpenAPS Offline') { kind = 'running mode'; key = 'NsClientAcceptRunningMode'; }
    else { kind = 'therapy event'; key = 'NsClientAcceptTherapyEvent'; }
    if (!ts) return res(false, kind + ': no parseable date/created_at -> mapper returns null');
    if (kind === 'profile switch' && t.profile == null) return res(false, 'profile switch without `profile` field is dropped by the mapper');
    if (kind === 'temp basal' && t.absolute == null && t.percent == null) return res(false, 'temp basal without absolute/percent is dropped by the mapper');
    if (key && !on(key)) return res(false, kind + ': ' + key + ' is off (default false on ' + variant + ')');
    if (kind === 'temp target') {
      const durMs = t.durationInMilliseconds != null ? t.durationInMilliseconds : (t.duration != null ? t.duration * 60000 : null);
      if (durMs == null) return res(false, 'temp target without duration is dropped');
      if (durMs === 0) return res(true, 'temp target with duration 0 = cancel/end event');
      if (t.targetBottom == null || t.targetTop == null) return res(false, 'temp target without targetBottom/targetTop is dropped');
      const mg = (v) => (/mmol/i.test(t.units || '') ? v * 18 : v);
      const lo = mg(t.targetBottom); const hi = mg(t.targetTop);
      if (lo < 72 || lo > 180 || hi < 72 || hi > 180 || lo > hi) return res(false, 'temp target outside 72..180 mg/dL or bottom > top');
    }
    return res(true, kind + (key ? ': ' + key + ' on' : ': not gated') + (t.isValid === false ? ' (isValid:false -> applied as an invalidation of a known record)' : '') + '. Known nsId/pumpId records are matched, not duplicated.');
  }
};

function parseIsoMs (s) {
  const m = /^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:?\d\d)?$/.exec(s);
  if (!m) { const v = Date.parse(s); return isNaN(v) ? 0 : v; }
  const frac = m[2] ? '.' + m[2].slice(0, 3).padEnd(3, '0') : '';
  const v = Date.parse(m[1] + frac + (m[3] || 'Z'));
  return isNaN(v) ? 0 : v;
}

// ---------------------------------------------------------------------------
// followers
// ---------------------------------------------------------------------------
const LF = 'LoopFollow@4a74b781 LoopFollow/';
const LC = 'LoopCaregiver@2305718 ';
const NG = 'nightguard@75404bd nightguard/external/NightscoutService.swift';
const XD = 'xDrip@1ed760048 app/src/main/java/com/eveningoutpost/dexdrip/';
const NR = 'nightscout-reporter@518d61f lib/src/';
const lfDate = (ms) => new Date(ms).toISOString().slice(0, 19); // "yyyy-MM-dd'T'HH:mm:ss" UTC, no Z
const LC_NOTE = 'LoopCaregiver pins gestrich/NightscoutKit@d63fb73 (branch feature/2023-07/bg/remote-commands), not available locally; payload cited from LoopKit NightscoutKit@4ec9fd1, which defines the same functions.';

const followers = {
  loopFollowSetup () {
    return [
      d('LoopFollow: list subjects', 'GET', '/api/v2/authorization/subjects', 'secret', [LF + 'Helpers/NightscoutUtils.swift:416,443-470,488-501'], { notes: 'Looks for a subject named "LoopFollow"; if present uses its accessToken.' }),
      d('LoopFollow: create read-only subject if absent', 'POST', '/api/v2/authorization/subjects', 'secret', [LF + 'Helpers/NightscoutUtils.swift:503-527,536-544'], {
        body: { name: 'LoopFollow', roles: ['readable'] },
        notes: 'Only when the GET found none. Response may be an array or an object; LoopFollow takes _id and COMPUTES the token locally as "loopfollow-" + sha1(sha1(secret) + _id)[0..16] instead of reading it back -- it breaks if the server changes its token derivation.'
      })
    ];
  },

  loopFollowPoll ({ now, downloadDays = 1 }) {
    const fromMs = now - downloadDays * 86400000;
    return [
      d('LoopFollow: entries', 'GET', '/api/v1/entries.json?' + qFoundation([['count', String(downloadDays * 4 * 24 * 60 / 5)], ['find[date][$gte]', String(Math.trunc(fromMs))], ['find[type][$ne]', 'cal']]), 'token-query',
        [LF + 'Controllers/Nightscout/BGData.swift:10-13,70-76', LF + 'Helpers/Globals.swift:26', LF + 'Helpers/NightscoutUtils.swift:50-65,180-199'], { notes: 'LoopFollow puts token= FIRST, then parameters in Swift dictionary order (not stable). count = bgFetchDays*maxExpectedUploaders(4)*288.' }),
      d('LoopFollow: treatments', 'GET', '/api/v1/treatments.json?' + qFoundation([['find[created_at][$gte]', lfDate(fromMs)], ['find[created_at][$lte]', lfDate(now + 6 * 3600000)], ['count', String(Math.max(downloadDays * 100, 5000))]]), 'token-query',
        [LF + 'Controllers/Nightscout/Treatments.swift:45-53', LF + 'Helpers/DateTime.swift:86-92'], { notes: 'Dates "yyyy-MM-ddTHH:mm:ss" UTC with no Z and no millis.' }),
      d('LoopFollow: devicestatus', 'GET', '/api/v1/devicestatus.json?' + qFoundation([['count', '1']]), 'token-query', [LF + 'Controllers/Nightscout/DeviceStatus.swift:8-11']),
      d('LoopFollow: profile', 'GET', '/api/v1/profiles.json?' + qFoundation([['count', '1'], ['find[startDate][$lte]', isoMs(now + 60000)]]), 'token-query', [LF + 'Controllers/Nightscout/Profile.swift:8-15', LF + 'Helpers/NightscoutUtils.swift:56'], { notes: 'Uses /api/v1/profiles.json (plural), never profile/current.' })
    ];
  },

  loopCaregiverOverride ({ now, presetName, displayName, durationMin }) {
    return d('LoopCaregiver: remote override', 'POST', '/api/v2/notifications/loop', 'secret', [
      'NightscoutKit@4ec9fd1 Sources/NightscoutKit/NightscoutClient.swift:336-347,388-394,604-625',
      LC + 'LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift:158-166',
      LC + 'LoopCaregiverKit/Package.swift:17'
    ], { body: { reason: presetName, reasonDisplay: 'Caregiver Update', eventType: 'Temporary Override', duration: swiftDouble(durationMin), notes: '' }, notes: 'All values are strings ("60.0"). reasonDisplay is always "Caregiver Update" (displayName ' + JSON.stringify(displayName || null) + ' is not sent). No otp, no remoteAddress. Non-200 is an error. ' + LC_NOTE });
  },

  loopCaregiverCancel () {
    return d('LoopCaregiver: cancel override', 'POST', '/api/v2/notifications/loop', 'secret', [
      'NightscoutKit@4ec9fd1 Sources/NightscoutKit/NightscoutClient.swift:349-357,604-625',
      LC + 'LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift:169-177'
    ], { body: { eventType: 'Temporary Override Cancel', duration: '0' }, notes: 'Remote commands v2 (when enabled) go through the fork-only uploadRemoteCommand instead. ' + LC_NOTE });
  },

  loopCaregiverCarbs ({ now, grams, absorptionH = 3, otp = '000000', consumedAt }) {
    return d('LoopCaregiver: remote carbs', 'POST', '/api/v2/notifications/loop', 'secret', [
      'NightscoutKit@4ec9fd1 Sources/NightscoutKit/NightscoutClient.swift:370-386,604-625',
      LC + 'LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift:136-144'
    ], { body: { eventType: 'Remote Carbs Entry', remoteCarbs: swiftDouble(grams), remoteAbsorption: swiftDouble(absorptionH), otp, created_at: isoMs(consumedAt || now) }, notes: 'created_at has fractional seconds; the caregiver app always passes a consumed date. otp is a synthetic placeholder -- Loop validates the real TOTP. ' + LC_NOTE });
  },

  loopCaregiverBolus ({ now, units, otp = '000000' }) {
    return d('LoopCaregiver: remote bolus', 'POST', '/api/v2/notifications/loop', 'secret', [
      'NightscoutKit@4ec9fd1 Sources/NightscoutKit/NightscoutClient.swift:359-368,604-625',
      LC + 'LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift:147-155'
    ], { body: { eventType: 'Remote Bolus Entry', remoteBolus: swiftDouble(units), otp }, notes: 'otp is a synthetic placeholder. ' + LC_NOTE });
  },

  nightguardPoll ({ now }) {
    const sorted = (o) => Object.keys(o).sort().map((k) => [k, o[k]]);
    return [
      d('nightguard: JWT exchange', 'GET', '/api/v2/authorization/request/token=<accessToken>', 'token-path', [NG + ':438-466'], { notes: 'The literal text "token=" is part of the PATH segment (the server matches the subject by the part after the last "-"). The runner must substitute <accessToken> into the path; do not append ?token=. The returned JWT is then sent as Authorization: Bearer.' }),
      d('nightguard: v3 latest entries', 'GET', '/api/v3/entries?' + qFoundation(sorted({ limit: '2', 'sort$desc': 'date', fields: 'identifier,_id,date,dateString,sgv,direction,units' })), 'jwt', [NG + ':1495-1504', NG + ':587-595'], { notes: 'Keys sorted by makeURL. Falls back to api/v1/entries.json?count=2 on failure.' }),
      d('nightguard: v3 entry stream', 'GET', '/api/v3/entries?' + qFoundation(sorted({ 'date$gte': String(now - 86400000), 'sort$desc': 'date', 'type$in': 'sgv|mbg', limit: '500', fields: 'identifier,_id,date,dateString,mills,type,sgv,mbg,direction,units' })), 'jwt', [NG + ':804-817'], { notes: '"|" is percent-encoded by Foundation.' }),
      d('nightguard: status', 'GET', '/api/v1/status.json', 'token-header', [NG + ':972-976', NG + ':366-376'], { notes: 'nightguard actually sends the RAW access token in an API-SECRET header here (useAccessTokenHeader), not ?token=; the runner should emulate that header if it can.' }),
      d('nightguard: devicestatus', 'GET', '/api/v1/devicestatus.json?' + qFoundation([['count', '5']]), 'token-header', [NG + ':1980-1984', NG + ':366-376'], { notes: 'Raw access token in API-SECRET header (see status).' }),
      d('nightguard: properties', 'GET', '/api/v2/properties', 'token-header', [NG + ':1588-1592', 'nightguard@75404bd nightguard/repository/UserDefaultsRepository.swift:280-283'])
    ];
  },

  reporterDay ({ dayStart }) {
    const beg = dayStart; const end = dayStart + 86400000 - 1;
    const src = [NR + 'globals.dart:1965-1988'];
    return [
      d('Reporter: entries for day', 'GET', '/api/v1/entries.json?' + qLiteral([['find[date][$gte]', String(beg)], ['find[date][$lte]', String(end)], ['count', '100000']]), 'token-query', src.concat([NR + 'start_component.dart:1210-1216']), { notes: 'Reporter puts ?token=<t>& FIRST. Brackets and $ are literal (browser does not encode them).' }),
      d('Reporter: treatments for day', 'GET', '/api/v1/treatments.json?' + qLiteral([['find[created_at][$gte]', isoMs(beg)], ['find[created_at][$lte]', isoMs(end)], ['count', '100000']]), 'token-query', src.concat([NR + 'start_component.dart:1255-1260'])),
      d('Reporter: devicestatus for day', 'GET', '/api/v1/devicestatus.json?' + qLiteral([['find[created_at][$gte]', isoMs(beg)], ['find[created_at][$lte]', isoMs(end)], ['count', '100000']]), 'token-query', src.concat([NR + 'start_component.dart:1304-1309'])),
      d('Reporter: activity for day', 'GET', '/api/v1/activity.json?' + qLiteral([['find[created_at][$gte]', isoMs(beg)], ['find[created_at][$lte]', isoMs(end)], ['count', '100000']]), 'token-query', src.concat([NR + 'start_component.dart:1317-1322']))
    ].concat([
      d('Reporter: last temp basal of day before (first day only)', 'GET', '/api/v1/treatments.json?' + qLiteral([['find[created_at][$lt]', isoMs(beg)], ['find[created_at][$gt]', isoMs(beg - 86400000)], ['count', '100'], ['find[eventType][$eq]', 'Temp%20Basal']]), 'token-query', src.concat([NR + 'start_component.dart:1240-1246']), { notes: 'Only while no last temp basal is known. "Temp%20Basal" is hand-encoded in the source. Day bounds are local midnight shifted by the profile timezone; this builder takes dayStart already in UTC ms.' })
    ]);
  },

  xdripFollow ({ now, lastReadingAt }) {
    const src = [XD + 'cgm/nsfollow/NightscoutFollow.java:52-62', XD + 'cgm/nsfollow/utils/NightscoutUrl.java:80-85'];
    const entries = lastReadingAt
      ? d('xDrip follow: entries since', 'GET', '/api/v1/entries.json?' + qLiteral([['count', '2880'], ['find[date][$gt]', String(Math.max(lastReadingAt, now - 86400000))], ['rr', String(now)]]), 'secret', src.concat([XD + 'cgm/nsfollow/NightscoutFollow.java:108-114']), { notes: 'find[date][$gt] is @Query(encoded=true): literal brackets. rr is a cache buster (now ms).' })
      : d('xDrip follow: first entries', 'GET', '/api/v1/entries.json?' + qLiteral([['count', '10'], ['rr', String(now)]]), 'secret', src.concat([XD + 'cgm/nsfollow/NightscoutFollow.java:115-117']));
    return [
      entries,
      d('xDrip follow: treatments', 'GET', '/api/v1/treatments', 'secret', src.concat([XD + 'cgm/nsfollow/NightscoutFollow.java:124-133']), { notes: 'No query at all (server default count). At most every 60 s, only with treatment download enabled.' }),
      d('xDrip follow: devicestatus', 'GET', '/api/v1/devicestatus.json?count=1', 'secret', src.concat([XD + 'cgm/nsfollow/NightscoutFollow.java:134-137']), { notes: 'At most every 5 min, only if NsServerCapabilities allows.' })
    ];
  }
};

// ---------------------------------------------------------------------------
// careportal: what the Nightscout web page itself sends (RC tree)
// ---------------------------------------------------------------------------
const RC = 'cgm-remote-monitor@e3adc91d ';
const RC_FORM_NOTE = 'jQuery $.ajax with a plain object and no contentType: sent as application/x-www-form-urlencoded, so every value arrives as a STRING. Header is Authorization: Bearer when the page is token-authorized, else api-secret (lib/client/index.js:29-40).';

function careportalNormalize (raw, units, now) {
  // lib/client-core/careportal/normalize-treatment.js:38-120 (re-implemented, pure)
  const data = Object.assign({}, raw);
  data.preBolus = parseInt(data.preBolus, 10);
  if (isNaN(data.preBolus)) delete data.preBolus;
  if (units === 'mmol') {
    if (data.targetTop !== '' && data.targetTop != null) data.targetTop = data.targetTop * 18;
    if (data.targetBottom !== '' && data.targetBottom != null) data.targetBottom = data.targetBottom * 18;
  }
  if (raw.absoluteRaw !== undefined) { if (raw.absoluteRaw !== '' && !isNaN(raw.absoluteRaw)) data.absolute = Number(raw.absoluteRaw); delete data.absoluteRaw; }
  data.created_at = isoMs(now);
  if (data.eventType !== 'Profile Switch') delete data.profile;
  if (String(data.eventType).indexOf('Temp Basal') > -1) data.eventType = 'Temp Basal';
  if (String(data.eventType).indexOf('Temporary Target Cancel') > -1) { data.duration = 0; data.eventType = 'Temporary Target'; data.targetBottom = ''; data.targetTop = ''; }
  if (String(data.eventType).indexOf('Combo Bolus') > -1) { data.splitNow = parseInt(raw.splitNowRaw, 10) || 0; data.splitExt = parseInt(raw.splitExtRaw, 10) || 0; }
  delete data.splitNowRaw; delete data.splitExtRaw;
  const out = {};
  for (const k of Object.keys(data)) if (data[k] !== '' && data[k] !== null && data[k] !== undefined) out[k] = String(data[k]);
  return out;
}

const careportal = {
  treatment ({ now, eventType, fields = {}, units = 'mg/dl', enteredBy = 'lab-tester' }) {
    const raw = Object.assign({ enteredBy, eventType, preBolus: '0', units }, fields);
    const body = careportalNormalize(raw, units, now);
    if (body.eventType === 'Combo Bolus' && body.insulin) {
      const ins = Number(body.insulin);
      body.enteredinsulin = String(ins);
      body.insulin = String(ins * Number(body.splitNow) / 100);
      body.relative = String(ins * Number(body.splitExt) / 100 / Number(body.duration) * 60);
    }
    return d('Careportal treatment: ' + eventType, 'POST', '/api/v1/treatments/', 'secret', [
      RC + 'lib/client/careportal.js:280-338,389-411',
      RC + 'lib/client-core/careportal/normalize-treatment.js:38-120',
      RC + 'lib/client/index.js:29-40'
    ], { body, form: true, notes: RC_FORM_NOTE + ' One object, not an array. preBolus "0" is always present (form resets it to 0). With "other time" checked the page also posts eventTime as Date.toString() (host-timezone text); omitted here.' });
  },

  loopOverride ({ now, reason, reasonDisplay, durationMin, otp, notes, units = 'mg/dl', enteredBy = 'lab-tester' }) {
    const raw = { enteredBy, eventType: 'Temporary Override', otp: otp || '', reason, duration: durationMin, notes: notes || '', preBolus: '0', units };
    const body = careportalNormalize(raw, units, now || 0);
    if (reasonDisplay) body.reasonDisplay = reasonDisplay; // set from inputMatrix reasons: preset.symbol + " " + preset.name
    return d('Careportal Loop override (remote command)', 'POST', '/api/v2/notifications/loop', 'secret', [
      RC + 'lib/plugins/loop.js:86-117,139-154',
      RC + 'lib/client/careportal.js:290-338',
      RC + 'lib/client-core/careportal/normalize-treatment.js:38-120',
      RC + 'lib/server/loop.js:60-117'
    ], { body, form: true, notes: RC_FORM_NOTE + ' Presets come from profile.loopSettings.overridePresets (duration seconds/60). The server maps reason -> override-name and duration -> override-duration-minutes.' });
  },

  profileEditorSave ({ record, now = 0, units = 'mg/dl', currentProfile }) {
    const r = JSON.parse(JSON.stringify(record || {}));
    r.startDate = r.startDate || isoMs(now);
    r.created_at = isoMs(now);
    r.srvModified = now;
    for (const k of Object.keys(r.store || {})) {
      const p = r.store[k];
      if (p && !p.perGIvalues) { for (const f of ['perGIvalues', 'carbs_hr_high', 'carbs_hr_medium', 'carbs_hr_low', 'delay_high', 'delay_medium', 'delay_low']) delete p[f]; }
    }
    r.defaultProfile = currentProfile || r.defaultProfile || Object.keys(r.store || {})[0];
    r.units = units;
    delete r.convertedOnTheFly;
    return d('Profile editor save', 'PUT', '/api/v1/profile/', 'secret', [
      RC + 'lib/profile/profileeditor.js:614-690',
      RC + 'lib/client-core/profile-editor/records.js:7-13'
    ], { body: r, notes: 'JSON (Content-Type application/json), one object. Same PUT for new records (no _id) and existing ones (_id kept). Any other loaded keys (e.g. mills) are sent back unchanged.' });
  }
};

module.exports = { uuid, loop, trio, aaps, followers, careportal };

// ---------------------------------------------------------------------------
// example printout: node tools/review/journey-lab/clients.js
// ---------------------------------------------------------------------------
if (require.main === module) {
  const now = Date.UTC(2026, 8, 25, 12);
  const min = 60000;
  const sched = { basal: [['00:00', 0.8], ['06:00', 1.0]], sens: [['00:00', 45]], carbratio: [['00:00', 10]], target: [['00:00', 100, 110]] };
  const readings = [0, 1, 2].map((i) => ({ t: now - (2 - i) * 5 * min, sgv: 110 + i * 3, direction: 'Flat' }));
  const oid = hex24('lab-carb-1');
  const loopUuid = uuid('lab-override-1', { upper: true });
  const aapsProf = { dia: 5, basal: sched.basal, sens: sched.sens, carbratio: sched.carbratio, target: sched.target, timezone: 'Etc/UTC' };
  const loopProfileDoc = loop.profileUpload({ now, schedules: sched, presets: [{ name: 'Run', symbol: 'R', durationMin: 60, targetRange: [140, 160], scale: 0.8 }] }).body[0];
  const out = [];
  const add = (x) => { (Array.isArray(x) ? x : [x]).forEach((y) => out.push(y)); };
  add(loop.profileUpload({ now, schedules: sched, presets: [{ name: 'Run', symbol: 'R', durationMin: 60, targetRange: [140, 160], scale: 0.8 }] }));
  add(loop.overrideStart({ now, uuid: loopUuid, reason: 'R Run', durationMin: 60, correctionRange: [140, 160], insulinNeedsScaleFactor: 0.8, remote: false }));
  add(loop.overrideEnd({ uuid: loopUuid, startedAt: now, endedAt: now + 25 * min, reason: 'R Run', correctionRange: [140, 160], insulinNeedsScaleFactor: 0.8 }));
  add(loop.overrideDelete({ uuid: loopUuid }));
  add(loop.bolus({ now, syncIdentifier: 'lab-bolus-0001', units: 1.2, automatic: false }));
  add(loop.carbs({ now, grams: 30, absorptionHours: 3, foodType: 'lab snack' }));
  add(loop.carbEdit({ nsId: oid, now, grams: 35 }));
  add(loop.carbDelete({ nsId: oid }));
  add(loop.tempBasal({ now, syncIdentifier: 'lab-tb-0001', rate: 1.1, durationMin: 30 }));
  add(loop.suspend({ now, syncIdentifier: 'lab-susp-0001', durationMin: 15 }));
  add(loop.entries({ readings }));
  add(loop.devicestatus({ now, iob: 1.1, cob: 20, predicted: [110, 112, 115], enacted: { rate: 0.9, durationMin: 30, bolus: 0 }, override: null, reservoir: 120, battery: 80 }));
  out.push({ label: 'loop.canImport(own upload + _id)', result: loop.canImport(Object.assign({ _id: hex24('p') }, loopProfileDoc)) });
  add(trio.connect({ now }));
  add(trio.profileUpload({ now, schedules: sched, presets: [{ name: 'Exercise', durationMin: 60, percentage: 80, target: 140 }] }));
  add(trio.overrideStart({ now, name: 'Exercise', durationMin: null }));
  add(trio.overrideEnd({ startedAt: now, endedAt: now + 40 * min, name: 'Exercise', originalDurationMin: 43200 }));
  add(trio.tempTargetStart({ now, id: uuid('tt1', { upper: true }), target: 140, durationMin: 60, name: 'Activity' }));
  add(trio.tempTargetEnd({ id: uuid('tt1', { upper: true }), startedAt: now, endedAt: now + 20 * min, target: 140, name: 'Activity' }));
  add(trio.bolus({ now, id: uuid('tb1', { upper: true }), units: 0.3, smb: true }));
  add(trio.carbs({ now, id: uuid('tc1', { upper: true }), grams: 25 }));
  add(trio.carbDelete({ id: uuid('tc1', { upper: true }) }));
  add(trio.tempBasal({ now, id: uuid('ttb1', { upper: true }), rate: 0.7, durationMin: 30 }));
  add(trio.suspend({ now, id: uuid('ts1', { upper: true }) }));
  add(trio.resume({ now: now + 10 * min, id: uuid('tr1', { upper: true }) }));
  add(trio.entries({ readings }));
  add(trio.devicestatus({ now, iob: 0.8, cob: 10, bg: 112, eventualBG: 105, predBGs: [112, 110, 108], rate: 0.6, durationMin: 30, smb: 0.2, reservoir: 150, battery: 70 }));
  const trioDoc = Object.assign({ _id: hex24('tp'), created_at: isoMs(now) }, trio.profileUpload({ now, schedules: sched }).body);
  out.push({ label: 'trio.canImport(own upload)', result: trio.canImport([trioDoc]) });
  out.push({ label: 'trio.canImport(Loop upload)', result: trio.canImport([Object.assign({ _id: 'x', created_at: isoMs(now) }, loopProfileDoc)]) });
  out.push({ label: 'trio.downloads', result: trio.downloads([{ eventType: 'Carb Correction', carbs: 20, created_at: isoMs(now - 10 * min), enteredBy: 'lab-careportal' }, { eventType: 'Temporary Target', duration: 30, targetTop: 140, targetBottom: 140, created_at: isoMs(now - 5 * min), enteredBy: 'lab-careportal' }], { now }) });
  for (const variant of ['v3-34', 'v1-34', 'v3-40']) {
    add(aaps.profileStore({ variant, now, units: 'mg/dl', defaultProfile: 'LabA', profiles: { LabA: aapsProf } }));
    add(aaps.profileSwitch({ variant, now, identifier: uuid('ps1'), profileName: 'LabA', percentage: 90, timeshiftH: 0, durationMin: 60, profileJson: { units: 'mg/dl', dia: 5 } }));
    add(aaps.effectiveProfileSwitch({ variant, now, identifier: uuid('eps1'), profileName: 'LabA', profileJson: { units: 'mg/dl', dia: 5 }, percentage: 90 }));
    add(aaps.tempTargetStart({ variant, now, identifier: uuid('att1'), low: 140, high: 140, durationMin: 60, reason: 'Activity' }));
    add(aaps.tempTargetCancel({ variant, identifier: uuid('att1'), nsId: uuid('att1'), startedAt: now, endedAt: now + 15 * min }));
    add(aaps.bolus({ variant, now, identifier: uuid('ab1'), units: 0.4, smb: true }));
    add(aaps.carbs({ variant, now, identifier: uuid('ac1'), grams: 20 }));
    add(aaps.tempBasal({ variant, now, identifier: uuid('atb1'), rate: 1.2, durationMin: 30 }));
    add(aaps.runningMode({ variant, now, identifier: uuid('arm1'), mode: 'SUSPENDED_BY_USER', durationMin: 30 }));
    add(aaps.remove({ variant, identifier: uuid('ab1'), nsId: uuid('ab1'), collection: 'treatments', record: { eventType: 'Correction Bolus', insulin: 0.4, date: now } }));
    add(aaps.entries({ variant, readings: readings.slice(0, 1) }));
    add(aaps.devicestatus({ variant, now, iob: 0.5, cob: 5, bg: 112, eventualBG: 108, predBGs: [112, 110], rate: 0.8, durationMin: 30, smb: 0.1, reservoir: 100, battery: 60 }));
    out.push({ label: 'aaps.acceptsProfile ' + variant, result: aaps.acceptsProfile({ variant, nsProfileDoc: { created_at: '2026-09-25T12:00:00.000Z' }, localLastChange: now + 1 }) });
    out.push({ label: 'aaps.acceptsTreatment ' + variant, result: aaps.acceptsTreatment({ variant, treatment: { eventType: 'Temporary Target', duration: 30, targetTop: 140, targetBottom: 140, units: 'mg/dl', date: now }, settings: {} }) });
  }
  add(loop.remoteCgmFetch({ now }));
  out.push({ label: 'loop.importSummary(own upload + _id)', result: loop.importSummary(Object.assign({ _id: hex24('p') }, loopProfileDoc)) });
  add(trio.nsCgmFetch({ syncDate: now - 5 * min }));
  add(trio.reuploadFetched({ entries: readings.map((r) => ({ _id: hex24('e' + r.t), sgv: r.sgv, direction: r.direction, date: r.t, dateString: isoMs(r.t), device: 'lab-uploader', type: 'sgv' })), syncDate: now - 20 * min }));
  out.push({ label: 'trio.importSummary(own upload)', result: trio.importSummary([trioDoc]) });
  for (const variant of ['v3-34', 'v1-34', 'v3-40']) {
    add(aaps.firstLoad({ variant, now, nsBgSource: false }));
    out.push({ label: 'aaps.firstLoadKeeps ' + variant, result: aaps.firstLoadKeeps({ variant, treatments: [{ eventType: 'Temporary Target', duration: 30, targetTop: 140, targetBottom: 140, reason: 'Activity', created_at: isoMs(now), date: now }, { eventType: 'Bolus Wizard', created_at: isoMs(now), date: now, bolusCalculatorResult: '{}' }, { eventType: 'Temporary Override', created_at: isoMs(now), date: now }], aapsClient: false }) });
    out.push({ label: 'aaps.fullSyncNote ' + variant, result: aaps.fullSyncNote({ variant }) });
    out.push({ label: 'aaps.acceptsProfile fresh install ' + variant, result: aaps.acceptsProfile({ variant, nsProfileDoc: { created_at: '2026-09-25T12:00:00.000Z' }, localLastChange: 0 }) });
  }
  add(followers.loopFollowSetup());
  add(followers.loopFollowPoll({ now }));
  add(followers.loopCaregiverOverride({ now, presetName: 'Run', displayName: 'R Run', durationMin: 60 }));
  add(followers.loopCaregiverCancel({ now }));
  add(followers.loopCaregiverCarbs({ now, grams: 15, absorptionH: 3, otp: '000000' }));
  add(followers.loopCaregiverBolus({ now, units: 0.5, otp: '000000' }));
  add(followers.nightguardPoll({ now }));
  add(followers.reporterDay({ dayStart: Date.UTC(2026, 8, 24) }));
  add(followers.xdripFollow({ now, lastReadingAt: now - 5 * min }));
  add(careportal.treatment({ now, eventType: 'Temporary Target', fields: { reason: 'Activity', targetTop: 140, targetBottom: 140, duration: 60 } }));
  add(careportal.loopOverride({ now, reason: 'Run', reasonDisplay: 'R Run', durationMin: 60 }));
  add(careportal.profileEditorSave({ record: { defaultProfile: 'Default', store: { Default: { dia: 5, units: 'mg/dl', timezone: 'Etc/UTC' } } }, now }));
  for (const x of out) console.log(JSON.stringify(x));
}
