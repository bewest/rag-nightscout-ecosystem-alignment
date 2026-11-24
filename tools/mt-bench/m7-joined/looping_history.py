"""synthetic-history-looping-2d-v1: a closed-loop population over the evaluator's 2-day cold window.

Synthetic data only. Every value comes from a seeded generator; nothing is copied from a real trace.
Field shapes follow the uploads documented in mapping/loop/nightscout-sync.md (Loop) and the
oref0 devicestatus shape (AAPS, Trio).

The spec is part of the fixture-catalog key, so every option that changes stored rows is in it:

    {'mode': 'synthetic-history-looping-2d-v1', 'anchorUnixMs': <multiple of 5 min>,
     'seed': <int>, 'cgmOnlyPercent': 0..100, 'deepHistoryTenants': <int>, 'deepHistoryDays': 3..400}

Roles, fixed per tenant from the seed and the roster size (ordinals in host order, as in the other modes):

    looping   SGV every 5 min, devicestatus every 5 min (a full Loop or oref0 status),
              treatments per 288-cycle day: 144 temp basals, 12 automatic boluses (SMB), 3 meal
              boluses with carbs, 1 carb correction, 2 profile or target changes (oref0: one
              Profile Switch carrying profileJson and one Temporary Target; Loop: two Temporary
              Overrides) = 162 per day, and 3 profile documents (revisions) of 3 named profiles each
              with full schedules
    cgm-only  SGV every 5 min, 4 logged treatments per day (3 meal boluses, 1 correction), one
              profile document; no devicestatus
    deep      a looping tenant over deepHistoryDays instead of 2, with 3 + days // 30 profile
              revisions ("months of all collections")

The roles are chosen by rank of sha256(seed:ordinal): the first round(n * cgmOnlyPercent / 100)
ordinals are CGM-only, the next deepHistoryTenants are deep, the rest looping. Every row carries the
fixture marker (entries `device`, devicestatus `device` suffix, treatments and profile `enteredBy`).
"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
import random
import re
import sys
from threading import Event
import time
from urllib.parse import urlsplit

import edge_base
import populated_history as h

MODE = 'synthetic-history-looping-2d-v1'
DEVICE = 's4_history_fixture_looping_2d_v1'
DAYS = 2
CYCLES_PER_DAY = 288
DAY_MS = 86_400_000
STEP_MS = h.STEP_MS
KEYS = ('mode', 'anchorUnixMs', 'seed', 'cgmOnlyPercent', 'deepHistoryTenants', 'deepHistoryDays')
DEFAULTS = dict(seed=20261121, cgmOnlyPercent=20, deepHistoryTenants=0, deepHistoryDays=90)
MAX_DEEP_DAYS = 400
KINDS = ('loop', 'aaps', 'trio')
DS_PREFIX = {'loop': 'loop://', 'aaps': 'openaps://', 'trio': 'openaps://'}
DS_DEVICES = ("loop://" + DEVICE, "openaps://" + DEVICE)

# treatments per 288-cycle day, by role
LOOPING_DAY = dict(tempBasal=144, smb=12, meal=3, carbCorrection=1, switches=2)
LOOPING_TREATMENTS_PER_DAY = sum(LOOPING_DAY.values())   # 162
CGM_ONLY_TREATMENTS_PER_DAY = 4
LOOPING_PROFILES = 3
CGM_ONLY_PROFILES = 1
MEAL_MINUTES = (450, 750, 1110)        # 07:30, 12:30, 18:30 UTC, jittered per day by up to 30 min
CARB_CORRECTION_MINUTE = 930           # 15:30
CHECKED = ('entries', 'entriesMd5', 'devicestatus', 'dsBattery', 'treatments', 'insulinX100', 'carbs', 'profile')


def require(ok, code):
    h.require(ok, code)


def default_spec(anchor, **changes):
    return dict(mode=MODE, anchorUnixMs=anchor, **(DEFAULTS | changes))


def validate(spec):
    require(isinstance(spec, dict) and tuple(sorted(spec)) == tuple(sorted(KEYS)) and spec['mode'] == MODE,
            'UNSUPPORTED')
    ints = all(type(spec[k]) is int for k in KEYS[1:])
    require(ints and 0 <= spec['seed'] < 2**63 and 0 <= spec['cgmOnlyPercent'] <= 100
            and 0 <= spec['deepHistoryTenants'] <= 1000 and 3 <= spec['deepHistoryDays'] <= MAX_DEEP_DAYS, 'LOOPING_OPTIONS')
    anchor = spec['anchorUnixMs']
    require(max(DAYS, spec['deepHistoryDays']) * CYCLES_PER_DAY * STEP_MS <= anchor < 253402300800000
            and anchor % STEP_MS == 0, 'ANCHOR')


def seed_roles(spec, n):
    return roles(spec, n)


def roles(spec, n):
    """Role per ordinal for a roster of n tenants: 'looping', 'cgm-only' or 'deep'."""
    validate(spec)
    require(type(n) is int and n >= 1, 'ROSTER')
    rank = sorted(range(n), key=lambda i: hashlib.sha256(f"{spec['seed']}:{i}".encode()).hexdigest())
    cgm = (n * spec['cgmOnlyPercent'] + 50) // 100
    require(spec['deepHistoryTenants'] <= n - cgm, 'DEEP_EXCEEDS_LOOPING')
    out = ['looping'] * n
    for i in rank[:cgm]:
        out[i] = 'cgm-only'
    for i in rank[cgm:cgm + spec['deepHistoryTenants']]:
        out[i] = 'deep'
    return out


def kind(spec, ordinal):
    return KINDS[int(hashlib.sha256(f"{spec['seed']}:{ordinal}:kind".encode()).hexdigest(), 16) % len(KINDS)]


def days_for(spec, role):
    """Days of rows for a role. `historyDays` (looping-v2 only, absent = DAYS) deepens every non-deep tenant."""
    return spec['deepHistoryDays'] if role == 'deep' else spec.get('historyDays', DAYS)


def phase_ms(spec, ordinal):
    """Per-tenant offset of the whole history grid, in [0, phaseSpreadMs): the tenant's rows sit `phase` ms
    before the shared 5-minute grid, so tenants stop sharing their due instants. Deterministic from
    (seed, ordinal); 0 for every tenant when the optional `phaseSpreadMs` is absent or 0."""
    spread = spec.get('phaseSpreadMs', 0)
    if not spread:
        return 0
    return int(hashlib.sha256(f"{spec['seed']}:{ordinal}:phase".encode()).hexdigest(), 16) % spread


def rows_per_tenant(spec, role='looping'):
    """Stored rows per tenant by collection for one role (exact: counts do not depend on the seed)."""
    validate(spec)
    days = days_for(spec, role)
    if role == 'cgm-only':
        return dict(entries=days*CYCLES_PER_DAY, devicestatus=0, treatments=days*CGM_ONLY_TREATMENTS_PER_DAY,
                    profile=CGM_ONLY_PROFILES)
    return dict(entries=days*CYCLES_PER_DAY, devicestatus=days*CYCLES_PER_DAY,
                treatments=days*LOOPING_TREATMENTS_PER_DAY, profile=profile_revisions(days))


def profile_revisions(days):
    return LOOPING_PROFILES + (days // 30 if days > DAYS else 0)


# ------------------------------------------------------------------ timeline (cheap, no documents)

# `+ 0.0` turns a rounded -0.0 into 0.0: the PostgreSQL storage refuses -0 in a document
# (lib/storage/postgres-entries-write.js jsonValue: Object.is(value, -0)), answering v1 POST 400
# "Document cannot be represented by this storage".
def _r1(x):
    return round(x, 1) + 0.0


def _r2(x):
    return round(x, 2) + 0.0


def _r4(x):
    return round(x, 4) + 0.0


class Tenant:
    """Everything one tenant's rows are built from; deterministic from (spec, ordinal, role)."""

    def __init__(self, spec, ordinal, role):
        self.spec, self.ordinal, self.role = spec, ordinal, role
        self.kind = kind(spec, ordinal) if role != 'cgm-only' else 'cgm'
        self.days = days_for(spec, role)
        self.n = self.days * CYCLES_PER_DAY
        self.anchor = spec['anchorUnixMs']
        self.phase = phase_ms(spec, ordinal)
        self.first = self.anchor - (self.n - 1) * STEP_MS - self.phase
        self.treatments = self._treatments()
        self._series()

    def stamp(self, index):
        return self.first + index * STEP_MS

    def grid(self, index):
        """The shared 5-minute grid (no phase): clock-slot choices and block seeds use it, so a phase moves
        timestamps only."""
        return self.first + self.phase + index * STEP_MS

    def _rng(self, *parts):
        return random.Random(':'.join(map(str, ('looping-v1', self.spec['seed'], self.ordinal) + parts)))

    def _treatments(self):
        """Treatments by cycle index, built per 288-cycle block counted forward from the first cycle."""
        out = []
        for block in range(self.days):
            base = block * CYCLES_PER_DAY
            block_start = self.grid(base)
            rng = self._rng('block', block_start)
            minute = lambda c: ((block_start + c * STEP_MS) % DAY_MS) // 60_000
            by_minute = {minute(c): c for c in range(CYCLES_PER_DAY)}  # each 5-minute clock slot once

            def at(clock_minute):
                return base + by_minute[(clock_minute // 5 * 5) % 1440]

            meals = [at(m + 5 * rng.randrange(-6, 7)) for m in MEAL_MINUTES]
            carbs = [rng.choice((30, 40, 45, 50, 60, 75)) for _ in meals]
            if self.role == 'cgm-only':
                for c, g in zip(meals, carbs):
                    out.append((c, 'Meal Bolus', _r2(g / 10), g, None))
                out.append((at(1260 + 5 * rng.randrange(0, 12)), 'Correction Bolus', _r2(rng.randrange(2, 7) * 0.5), None, None))
                continue
            for c, g in zip(meals, carbs):
                out.append((c, 'Meal Bolus', _r2(round(g / 10 * 0.7 / 0.05) * 0.05), g, None))
            out.append((at(CARB_CORRECTION_MINUTE + 5 * rng.randrange(-6, 7)), 'Carb Correction', None, rng.choice((8, 10, 15, 20)), None))
            for c in sorted(rng.sample(range(CYCLES_PER_DAY), LOOPING_DAY['tempBasal'])):
                out.append((base + c, 'Temp Basal', None, None, _r2(rng.randrange(0, 33) * 0.05)))
            for c in sorted(rng.sample(range(CYCLES_PER_DAY), LOOPING_DAY['smb'])):
                out.append((base + c, 'Correction Bolus', _r2(rng.randrange(1, 21) * 0.05), None, 'smb'))
            first, second = sorted(rng.sample(range(CYCLES_PER_DAY), 2))
            if self.kind == 'loop':
                out.append((base + first, 'Temporary Override', None, None, 'Exercise'))
                out.append((base + second, 'Temporary Override', None, None, 'Pre-Meal'))
            else:
                out.append((base + first, 'Profile Switch', None, None, rng.choice(('Weekend', 'Exercise', 'Default'))))
                out.append((base + second, 'Temporary Target', None, None, rng.choice(('Activity', 'Eating Soon', 'Hypo'))))
        out.sort(key=lambda t: (t[0], t[1]))
        return out

    def _series(self):
        """Per-cycle SGV, IOB, COB, battery and reservoir."""
        phase = (self.ordinal * 0.37) % (2 * math.pi)
        bolus = collections.defaultdict(float)
        carbs = collections.defaultdict(float)
        tbr = {}
        for c, kind_, insulin, carb, extra in self.treatments:
            if insulin:
                bolus[c] += insulin
            if carb:
                carbs[c] += carb
            if kind_ == 'Temp Basal':
                tbr[c] = extra
        self.tbr = tbr
        sgv, iob, cob, battery, reservoir = [], [], [], [], []
        noise, insulin_on_board, carbs_on_board, rate = 0.0, 0.0, 0.0, 0.8
        rng = self._rng('series')
        meal_effect = collections.defaultdict(float)
        res = 180.0
        for i in range(self.n):
            stamp = self.stamp(i)
            if i in carbs:
                for k in range(48):           # 4 h absorption, peak at 1 h
                    x = k / 12
                    meal_effect[i + k] += carbs[i] * 1.6 * x * math.exp(1 - x)
                carbs_on_board += carbs[i]
            if i in tbr:
                rate = tbr[i]
            delivered = bolus.get(i, 0.0) + rate / 12
            insulin_on_board = insulin_on_board * 0.983 + bolus.get(i, 0.0) + (rate - 0.8) / 12
            carbs_on_board = max(0.0, carbs_on_board - 30 / 12)
            res = res - delivered if res - delivered > 20 else 180.0
            noise = 0.85 * noise + rng.gauss(0, 3.0)
            day = 2 * math.pi * (stamp % DAY_MS) / DAY_MS
            value = 135 + 30 * math.sin(day + phase) + meal_effect.pop(i, 0.0) - 9 * insulin_on_board + noise
            sgv.append(int(max(40, min(400, round(value)))))
            iob.append(_r2(max(-2.0, insulin_on_board)))
            cob.append(int(round(carbs_on_board)))
            battery.append(100 - (i // 6 + self.ordinal) % 70)
            reservoir.append(_r1(res))
        self.sgv, self.iob, self.cob, self.battery, self.reservoir = sgv, iob, cob, battery, reservoir

    def expected(self):
        e = entries(self)
        return dict(entries=len(e), entriesMd5=h.digest(e),
                    devicestatus=0 if self.role == 'cgm-only' else self.n,
                    dsBattery=0 if self.role == 'cgm-only' else sum(self.battery),
                    treatments=len(self.treatments),
                    insulinX100=round(sum(t[2] or 0 for t in self.treatments) * 100),
                    carbs=sum(t[3] or 0 for t in self.treatments),
                    profile=CGM_ONLY_PROFILES if self.role == 'cgm-only' else profile_revisions(self.days))


# ------------------------------------------------------------------ documents

DIRECTIONS = ((-17.5, 'DoubleDown'), (-10, 'SingleDown'), (-5, 'FortyFiveDown'), (5, 'Flat'),
              (10, 'FortyFiveUp'), (17.5, 'SingleUp'))


def _direction(delta15):
    per5 = delta15 / 3
    for limit, name in DIRECTIONS:
        if per5 < limit:
            return name
    return 'DoubleUp'


def entries(t):
    out = []
    for i in range(t.n):
        stamp = t.stamp(i)
        delta = t.sgv[i] - t.sgv[i - 1] if i else 0
        out.append(dict(type='sgv', device=DEVICE, direction=_direction(t.sgv[i] - t.sgv[max(0, i - 3)]),
                        sgv=t.sgv[i], date=stamp, dateString=h._iso(stamp), delta=delta, noise=1,
                        filtered=t.sgv[i] * 1000 + 176, unfiltered=t.sgv[i] * 1000 - 224, rssi=100, utcOffset=0))
    return out


def _prediction(t, i, length, slope_decay, offset=0.0):
    bg, slope = t.sgv[i], (t.sgv[i] - t.sgv[max(0, i - 3)]) / 3
    out, value = [], float(bg)
    for k in range(length):
        value += slope * (slope_decay ** k) - t.iob[i] * 0.6 * math.exp(-k / 24) + offset
        out.append(int(max(39, min(401, round(value)))))
    return out


def _oref(t, i, iso, enacted):
    bg, iob, cob = t.sgv[i], t.iob[i], t.cob[i]
    rate = t.tbr.get(i, 0.8)
    preds = {'IOB': _prediction(t, i, 48, 0.9), 'ZT': _prediction(t, i, 48, 0.8, -0.4),
             'UAM': _prediction(t, i, 48, 0.95)}
    if cob:
        preds['COB'] = _prediction(t, i, 48, 0.97, 0.3)
    eventual = preds['IOB'][-1]
    reason = (f"COB: {cob}, Dev: {bg - 120}, BGI: {_r2(-iob * 2.1)}, ISF: 50, CR: 10, minPredBG {min(preds['IOB'])}, "
              f"minGuardBG {min(preds['ZT'])}, IOBpredBG {eventual}, UAMpredBG {preds['UAM'][-1]}; "
              f"Eventual BG {eventual} >= 100, adj. req. rate: {rate} to maxSafeBasal: 3.2, "
              f"temp {_r2(rate)} >~ req {_r2(rate)}U/hr. ")
    suggested = {
        'temp': 'absolute', 'bg': bg, 'tick': ('+' if i and bg >= t.sgv[i - 1] else '') + str(bg - t.sgv[i - 1] if i else 0),
        'eventualBG': eventual, 'targetBG': 110, 'insulinReq': _r2(max(0.0, (eventual - 110) / 50 - iob)),
        'deliverAt': iso, 'sensitivityRatio': 1, 'predBGs': preds, 'COB': cob, 'IOB': iob, 'reason': reason,
        'duration': 30, 'rate': rate, 'timestamp': iso, 'ISF': 50, 'CR': 10, 'TDD': 38.5, 'current_target': 110,
        'threshold': 70, 'minDelta': _r1((bg - t.sgv[max(0, i - 3)]) / 3), 'expectedDelta': _r1(-iob * 2.1),
        'reservoir': t.reservoir[i], 'insulinForManualBolus': 0.0, 'manualBolusErrorString': 0}
    iob_doc = {'iob': iob, 'basaliob': _r2(iob / 3), 'bolusiob': _r2(iob * 2 / 3), 'netbasalinsulin': _r2(iob / 4),
               'bolusinsulin': _r2(iob * 1.5), 'activity': _r4(iob / 100), 'time': iso,
               'iobWithZeroTemp': {'iob': _r2(iob - 0.1), 'basaliob': _r2(iob / 3 - 0.1), 'bolusiob': _r2(iob * 2 / 3),
                                   'netbasalinsulin': _r2(iob / 4), 'bolusinsulin': _r2(iob * 1.5),
                                   'activity': _r4(iob / 100), 'time': iso},
               'lastTemp': {'date': t.stamp(i) - STEP_MS * (i % 6), 'duration': 30.0, 'rate': rate}}
    openaps = {'version': '0.7.1', 'iob': iob_doc, 'suggested': suggested}
    if enacted:
        openaps['enacted'] = dict(suggested, received=True)
    doc = {'device': DS_PREFIX[t.kind] + DEVICE, 'created_at': iso, 'utcOffset': 0,
           'uploader': {'battery': t.battery[i], 'isCharging': t.battery[i] > 90},
           'pump': {'clock': iso, 'reservoir': t.reservoir[i],
                    'battery': {'percent': 100 - i % 100, 'display': True, 'string': f'{100 - i % 100}%'},
                    'status': {'status': 'normal', 'bolusing': False, 'suspended': False, 'timestamp': iso}},
           'openaps': openaps}
    if t.kind == 'aaps':
        doc['pump']['extended'] = {'Version': '3.2.0.4', 'LastBolus': iso, 'LastBolusAmount': 0.1,
                                   'TempBasalAbsoluteRate': rate, 'TempBasalRemaining': 30, 'BaseBasalRate': 0.8,
                                   'ActiveProfile': 'Default'}
    else:
        doc['pump']['bolusIncrement'] = 0.05
    return doc


def _loop(t, i, iso, enacted):
    rate = t.tbr.get(i, 0.8)
    doc = {'device': DS_PREFIX['loop'] + DEVICE, 'created_at': iso,
           'loop': {'name': 'Loop', 'version': '3.4.4', 'timestamp': iso,
                    'iob': {'iob': t.iob[i], 'timestamp': iso}, 'cob': {'cob': t.cob[i], 'timestamp': iso},
                    'predicted': {'startDate': iso, 'values': _prediction(t, i, 73, 0.93)},
                    'automaticDoseRecommendation': {'timestamp': iso, 'tempBasalAdjustment': {'rate': rate, 'duration': 30},
                                                    'bolusVolume': 0},
                    'recommendedBolus': 0},
           'pump': {'clock': iso, 'pumpID': 'synthetic-' + str(t.ordinal % 997), 'manufacturer': 'Insulet', 'model': 'Dash',
                    'battery': {'percent': 100 - i % 100}, 'suspended': False, 'bolusing': False,
                    'reservoir': t.reservoir[i], 'secondsFromGMT': 0},
           'uploader': {'name': 'iPhone', 'timestamp': iso, 'battery': t.battery[i]},
           'override': {'active': False, 'timestamp': iso}}
    if enacted:
        doc['loop']['enacted'] = {'rate': rate, 'duration': 30, 'timestamp': iso, 'received': True, 'bolusVolume': 0}
    return doc


def devicestatus(t):
    if t.role == 'cgm-only':
        return []
    build = _loop if t.kind == 'loop' else _oref
    return [build(t, i, h._iso(t.stamp(i)), i in t.tbr) for i in range(t.n)]


def _schedule(values, step_hours):
    return [{'time': f'{hour:02d}:00', 'value': value, 'timeAsSeconds': hour * 3600}
            for hour, value in zip(range(0, 24, step_hours), values)]


def _store(rng, scale):
    basal = [_r2(rng.randrange(10, 25) * 0.05 * scale) for _ in range(24)]
    one = lambda isf, cr: {
        'dia': 5, 'carbratio': _schedule([cr, cr + 2, cr + 1, cr], 6), 'sens': _schedule([isf, isf - 5, isf, isf + 5], 6),
        'basal': _schedule(basal, 1), 'target_low': _schedule([100, 95, 100], 8), 'target_high': _schedule([120, 115, 120], 8),
        'units': 'mg/dl', 'timezone': 'UTC', 'delay': 20, 'carbs_hr': 20, 'startDate': '1970-01-01T00:00:00.000Z'}
    isf, cr = rng.randrange(35, 70), rng.randrange(7, 15)
    return {'Default': one(isf, cr), 'Weekend': one(isf + 5, cr + 1), 'Exercise': one(isf + 20, cr + 4)}


def profiles(t):
    count = CGM_ONLY_PROFILES if t.role == 'cgm-only' else profile_revisions(t.days)
    out = []
    for r in range(count):
        stamp = t.first + (t.n - 1) * STEP_MS * r // count
        iso = h._iso(stamp)
        rng = t._rng('profile', r)
        doc = {'defaultProfile': 'Default', 'startDate': iso, 'created_at': iso, 'mills': stamp, 'units': 'mg/dl',
               'enteredBy': DEVICE, 'store': _store(rng, 1 + 0.05 * r)}
        if t.kind == 'loop':
            doc['loopSettings'] = {'dosingEnabled': True, 'dosingStrategy': 'automaticBolus', 'maximumBasalRatePerHour': 3.2,
                                   'maximumBolus': 8, 'minimumBGGuard': 75, 'preMealTargetRange': [80, 90],
                                   'overridePresets': [{'name': 'Exercise', 'symbol': 'E', 'duration': 3600,
                                                        'targetRange': [140, 160], 'insulinNeedsScaleFactor': 0.6},
                                                       {'name': 'Pre-Meal', 'symbol': 'M', 'duration': 3600,
                                                        'targetRange': [80, 90], 'insulinNeedsScaleFactor': 1.0}]}
        out.append(doc)
    return out


def treatments(t):
    store = profiles(t)[-1]['store']
    out = []
    for c, kind_, insulin, carbs, extra in t.treatments:
        stamp = t.stamp(c)
        iso = h._iso(stamp)
        sync = hashlib.sha256(f"{t.spec['seed']}:{t.ordinal}:{c}:{kind_}".encode()).hexdigest()[:24]
        doc = {'eventType': kind_, 'created_at': iso, 'enteredBy': DEVICE, 'utcOffset': 0}
        if t.kind == 'loop':
            doc['syncIdentifier'] = sync
        elif t.kind != 'cgm':
            doc.update(pumpId=int(sync[:12], 16), pumpType='OMNIPOD_DASH', pumpSerial='synthetic', isValid=True, date=stamp)
        if insulin is not None:
            doc['insulin'] = insulin
        if carbs is not None:
            doc['carbs'] = carbs
            if t.kind == 'loop':
                doc['absorptionTime'] = 180
        if kind_ == 'Temp Basal':
            doc.update(duration=30, rate=extra, absolute=extra, temp='absolute')
            if t.kind == 'loop':
                doc['automatic'] = True
            else:
                doc.update(durationInMilliseconds=1_800_000, type='NORMAL')
        elif kind_ == 'Correction Bolus' and extra == 'smb':
            doc.update(type='SMB', isSMB=True) if t.kind != 'loop' else doc.update(automatic=True)
        elif kind_ == 'Temporary Override':
            preset = {'Exercise': ([140, 160], 0.6), 'Pre-Meal': ([80, 90], 1.0)}[extra]
            doc.update(reason=extra, duration=3600, correctionRange=preset[0], insulinNeedsScaleFactor=preset[1])
        elif kind_ == 'Profile Switch':
            doc.update(profile=extra, originalProfileName=extra, duration=0, originalDuration=0, percentage=100,
                       timeshift=0, profileJson=json.dumps(store[extra], separators=(',', ':')))
        elif kind_ == 'Temporary Target':
            low, high = {'Activity': (140, 140), 'Eating Soon': (80, 80), 'Hypo': (120, 120)}[extra]
            doc.update(reason=extra, targetBottom=low, targetTop=high, duration=60, units='mg/dl')
        out.append(doc)
    return out


# ------------------------------------------------------------------ figures

def bytes_per_tenant(spec, role, ordinal=None):
    """JSON bytes the generator sends per tenant per collection (read-derived proxy for stored bytes)."""
    i = ordinal if ordinal is not None else 0
    t = Tenant(spec, i, role)
    size = lambda docs: sum(len(json.dumps(d, separators=(',', ':'))) for d in docs)
    return dict(kind=t.kind, entries=size(entries(t)), devicestatus=size(devicestatus(t)),
                treatments=size(treatments(t)), profile=size(profiles(t)))


def post_cycles_per_day(spec, role, ordinal=0):
    """Distinct 5-minute cycles per day that carry at least one new treatment (one POST each)."""
    t = Tenant(spec, ordinal, role)
    return len({c for c, *_ in t.treatments}) / t.days


# realistic-v1 follower reads per tenant per second (m7-joined/workload.py REALISTIC_CADENCE_MS):
# r_sgv 1/300, r_devicestatus 1/900, r_treatments 1/900, r_status 1/900.
READS_PER_TENANT_S = dict(r_sgv=1/300, r_devicestatus=1/900, r_treatments=1/900, r_status=1/900)


def request_rate(spec, tenants=1000, sample=12):
    """Offered requests/s for a population at loop cadence (read-derived from the generator).

    Writes: every tenant posts one SGV per 5 min; every looping tenant posts one devicestatus per
    5 min and one treatments POST per cycle that carries a new treatment; a CGM-only tenant posts its
    logged treatments. Reads are the realistic-v1 follower polls, unchanged."""
    validate(spec)
    cgm = (tenants * spec['cgmOnlyPercent'] + 50) // 100
    looping = tenants - cgm
    tx_loop = sum(post_cycles_per_day(spec, 'looping', i) for i in range(sample)) / sample
    tx_cgm = post_cycles_per_day(spec, 'cgm-only')
    w = dict(w_sgv=tenants / 300, w_devicestatus=looping / 300,
             w_treatments=(looping * tx_loop + cgm * tx_cgm) / 86400)
    r = {k: v * tenants for k, v in READS_PER_TENANT_S.items()}
    # JSON bytes per devicestatus document, averaged over the three controller kinds (equal shares)
    per_kind = [bytes_per_tenant(spec, 'looping', next(i for i in range(10_000) if kind(spec, i) == k)) for k in KINDS]
    ds_doc = sum(s['devicestatus'] for s in per_kind) / len(per_kind) / (DAYS * CYCLES_PER_DAY)
    return dict(tenants=tenants, looping=looping, cgmOnly=cgm,
                treatmentPostCyclesPerDay={'looping': round(tx_loop, 2), 'cgm-only': tx_cgm},
                treatmentsPerDay={'looping': LOOPING_TREATMENTS_PER_DAY, 'cgm-only': CGM_ONLY_TREATMENTS_PER_DAY},
                writesPerSecond={k: round(v, 3) for k, v in w.items()}, readsPerSecond={k: round(v, 3) for k, v in r.items()},
                writes=round(sum(w.values()), 3), reads=round(sum(r.values()), 3),
                total=round(sum(w.values()) + sum(r.values()), 3),
                devicestatusJsonBytesPerDocument=round(ds_doc),
                devicestatusJsonBytesPerSecond=round(w['w_devicestatus'] * ds_doc),
                basis='read-derived: generator counts x cadence; reads are realistic-v1 follower polls')


def describe(spec, tenants=1000):
    validate(spec)
    per_role = {}
    for role in ('looping', 'cgm-only') + (('deep',) if spec['deepHistoryTenants'] else ()):
        ordinals = (0,) if role == 'cgm-only' else [next(i for i in range(10_000) if kind(spec, i) == k) for k in KINDS]
        sizes = [bytes_per_tenant(spec, role, i) for i in ordinals]
        per_role[role] = dict(rows=rows_per_tenant(spec, role),
                              jsonBytesByKind={s['kind']: {k: v for k, v in s.items() if k != 'kind'} for s in sizes})
    return dict(spec=spec, rowsAndBytesPerTenant=per_role, requestRate=request_rate(spec, tenants),
                basis='read-derived from the generator (JSON bytes as sent, not stored bytes)')


# ------------------------------------------------------------------ seed and readback

def census(sql, tables, at, horizon):
    return census_for(sql, tables, at, horizon, DEVICE, DS_DEVICES)


def census_for(sql, tables, at, horizon, DEVICE, DS_DEVICES):
    """Per-tenant rows, bytes and checked sums of one looping mode's marker (v1 or v2)."""
    fields = " || ',' || ".join(f"(doc->>'{k}')" for k in h.FIELDS)
    measured = collections.defaultdict(dict)
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)),
        count(*) FILTER (WHERE jsonb_typeof(doc->'date') = 'number'
           AND (doc->>'date')::bigint BETWEEN {at+horizon-h.LOOKBACK_MS} AND {at}),
        md5(string_agg({fields}, '|' ORDER BY (doc->>'date')::bigint))
        FROM {tables['entries']} WHERE doc->>'device'='{DEVICE}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, active, checksum = line.split('\t')
        measured[tenant].update(entries=int(rows), entriesBytes=int(size), activeRows=int(active), entriesMd5=checksum)
    devices = ','.join(f"'{d}'" for d in DS_DEVICES)
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)), sum((doc->'uploader'->>'battery')::bigint)
        FROM {tables['devicestatus']} WHERE doc->>'device' IN ({devices}) GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, battery = line.split('\t')
        measured[tenant].update(devicestatus=int(rows), devicestatusBytes=int(size), dsBattery=int(battery))
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)),
        round(coalesce(sum((doc->>'insulin')::numeric),0)*100), coalesce(sum((doc->>'carbs')::numeric),0)
        FROM {tables['treatments']} WHERE doc->>'enteredBy'='{DEVICE}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, insulin, carbs = line.split('\t')
        measured[tenant].update(treatments=int(rows), treatmentsBytes=int(size), insulinX100=int(float(insulin)),
                                carbs=int(float(carbs)))
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)) FROM {tables['profile']}
        WHERE doc->>'enteredBy'='{DEVICE}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size = line.split('\t')
        measured[tenant].update(profile=int(rows), profileBytes=int(size))
    return dict(measured)


def tenant_factory(spec, n):
    """i -> Tenant for a roster of n (the seed's roles); the seeder's only way to build a tenant."""
    role = roles(spec, n)
    return lambda i: Tenant(spec, i, role[i])


def seed_requests(t):
    """(path, documents) in the order the seed posts them; profile documents go one per request."""
    return (('/api/v1/entries', entries(t)), ('/api/v1/devicestatus', devicestatus(t)),
            ('/api/v1/treatments', treatments(t)), ('/api/v1/profile', profiles(t)))


def _batches(docs, size, max_bytes=None):
    """Request boundaries: at most `size` rows, and (when set) at most `max_bytes` of JSON body, so a day of
    large statuses stays under the API's 1 MB parser for devicestatus (core lib/middleware/index.js:23-24)."""
    if max_bytes is None:
        return [docs[k:k+size] for k in range(0, len(docs), size)]
    out, part, used = [], [], 2
    for d in docs:
        n = len(json.dumps(d)) + 2
        if part and (len(part) == size or used + n > max_bytes):
            out.append(part); part, used = [], 2
        part.append(d); used += n
    return out + ([part] if part else [])


def run(spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=h.post, now=time.time, bulk=None):
    return seed_and_verify(sys.modules[__name__], spec, tenants, base, sql, until, window_seconds,
                           verify_only=verify_only, post_batch=post_batch, now=now, bulk=bulk)


def seed_and_verify(g, spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=h.post,
                    now=time.time, bulk=None):
    """Seed through the API and read back, for a looping generator module `g` (this one or looping_history_v2)."""
    g.validate(spec)
    require(tenants and type(window_seconds) is int and window_seconds >= 0, 'INPUT')
    require(edge_base.ok(base, seeding=not verify_only), 'EDGE')
    port = urlsplit(base).port
    require(port and len({row['id'] for row in tenants}) == len(tenants)
            and len({row['host'] for row in tenants}) == len(tenants), 'ROSTER')
    anchor = spec['anchorUnixMs']
    workers, batch = h.seed_limits()
    treatment_batch = int(os.environ.get('S4_HISTORY_SEED_TREATMENT_BATCH', batch))
    require(1 <= treatment_batch <= h.SGV_BATCH, 'SEED_LIMITS')
    roster = sorted(tenants, key=lambda row: row['host'])
    role = g.seed_roles(spec, len(roster))
    make = g.tenant_factory(spec, len(roster))
    seeded = len(roster) - spec.get('unseededTailTenants', 0)
    require(seeded > 0, 'UNSEEDED_TAIL_SIZE')
    seeded_ids = {row['id'] for row in roster[:seeded]}
    empty_ids = {row['id'] for row in roster[seeded:]}
    tables = h._tables(sql)

    def inspect():
        at = int(now() * 1000)
        horizon = max(window_seconds*1000, math.ceil(until*1000)-at if until is not None else 0)
        require(anchor <= at and at + horizon - anchor <= h.MAX_STALE_4W_MS, 'OUTSIDE_CLINICAL_WINDOW')
        measured = g.census(sql, tables, at, horizon)
        require(not empty_ids.intersection(measured), 'UNSEEDED_TENANT_HAS_HISTORY')
        require(measured.keys() <= {t['id'] for t in roster}, 'FOREIGN_TENANT')
        return at, measured

    at, measured = inspect()
    expected = {}

    def expect(i):
        tenant = roster[i]['id']
        if tenant not in expected:
            expected[tenant] = make(i).expected()
        return expected[tenant]

    def complete(i, value):
        want = expect(i)
        return all(value.get(k, 0) == want[k] for k in g.CHECKED)

    index = {t['id']: i for i, t in enumerate(roster)}
    require(all(complete(index[t], v) for t, v in measured.items()), 'READBACK_MISMATCH')
    missing = [(i, tenant) for i, tenant in enumerate(roster[:seeded]) if tenant['id'] not in measured]
    if missing:
        require(not verify_only, 'RESTORED_ROWS_MISSING')
        ids = ','.join("'" + t['id'] + "'" for _, t in missing)
        oldest = anchor - (max(g.DAYS, spec['deepHistoryDays'], spec.get('historyDays', 0)) * g.CYCLES_PER_DAY - 1) * STEP_MS
        collisions = sql(f"""SELECT DISTINCT tenant_id::text FROM {tables['entries']}
            WHERE tenant_id::text IN ({ids}) AND doc->>'type'='sgv' AND doc->>'device' IS DISTINCT FROM '{g.DEVICE}'
              AND jsonb_typeof(doc->'date')='number' AND (doc->>'date')::bigint BETWEEN {oldest} AND {anchor};""").splitlines()
        require(not collisions, 'UPSERT_KEY_IN_USE')
        failed = Event()

        def seed(item):
            if failed.is_set():
                return
            i, tenant = item
            try:
                for path, docs in g.seed_requests(make(i)):
                    if path == '/api/v1/profile':
                        for doc in docs:
                            post_batch(port, tenant, doc, until, path=path)
                        continue
                    size = min(batch, treatment_batch) if path == '/api/v1/treatments' else batch
                    for part in _batches(docs, size, getattr(g, 'SEED_BODY_MAX_BYTES', None)):
                        post_batch(port, tenant, part, until, path=path)
            except Exception:
                failed.set()
                raise
        if bulk is not None:
            bulk(g, spec, missing, len(roster), until)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(seed, missing))
        at, measured = inspect()
    require(measured.keys() == seeded_ids, 'ROWS_MISSING')
    if empty_ids and not verify_only:
        # A current SGV from any source advances a connector's cursor. Catch an unrelated primer
        # upload too: the history census above intentionally counts only this generator's marker.
        from uuid import UUID
        ids = ','.join("'" + str(UUID(value)) + "'" for value in sorted(empty_ids))
        queries = [f"SELECT tenant_id FROM {tables[name]} WHERE tenant_id IN ({ids})"
                   for name in ('entries', 'devicestatus', 'treatments')]
        occupied = sql("SELECT DISTINCT tenant_id FROM (" + " UNION ALL ".join(queries) + ") AS connector_history LIMIT 1;")
        require(not occupied.strip(), 'UNSEEDED_TENANT_HAS_HISTORY')
    for tenant, value in measured.items():
        require(complete(index[tenant], value), 'READBACK_MISMATCH')
    logical = hashlib.sha256()
    per_tenant = []
    for i, tenant in enumerate(roster):
        value = measured.get(tenant['id'], {})
        logical.update((tenant['host'] + ':' + json.dumps({k: value.get(k, 0) for k in g.CHECKED}, sort_keys=True) + '\n').encode())
        per_tenant.append(dict(ordinal=i, role=role[i] if i < seeded else 'unseeded', **value))
    total = lambda k, rows=per_tenant: sum(r.get(k, 0) for r in rows)
    by_role = {}
    for r in sorted({p['role'] for p in per_tenant}):
        rows = [p for p in per_tenant if p['role'] == r]
        by_role[r] = dict(tenants=len(rows), **{c: dict(rows=total(c, rows), storedDocBytes=total(c + 'Bytes', rows))
                                                 for c in ('entries', 'devicestatus', 'treatments', 'profile')})
    return dict(version=1, history=spec, observedUnixMs=at, anchorAgeMs=at-anchor,
                eligibilityThroughUnixMs=max(at+window_seconds*1000, math.ceil(until*1000) if until else 0),
                measuredWindowSeconds=window_seconds, coldEntriesLookbackMs=h.LOOKBACK_MS,
                rowsPerTenant={r: ({c: 0 for c in ('entries', 'devicestatus', 'treatments', 'profile')}
                                   if r == 'unseeded' else g.rows_per_tenant(spec, r)) for r in by_role},
                seededBatches=len(missing), logicalSha256=logical.hexdigest(),
                rows=total('entries'), activeRows=total('activeRows'), storedDocBytes=total('entriesBytes'),
                collections={k: dict(rows=total(k), storedDocBytes=total(k + 'Bytes'))
                             for k in ('entries', 'devicestatus', 'treatments', 'profile')},
                roles=by_role, tenants=per_tenant)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('describe',))
    parser.add_argument('--anchor', type=int, default=1_800_000_000_000 // STEP_MS * STEP_MS)
    parser.add_argument('--tenants', type=int, default=1000)
    for key, value in DEFAULTS.items():
        parser.add_argument('--' + key, type=int, default=value)
    args = parser.parse_args()
    spec = default_spec(args.anchor, **{k: getattr(args, k) for k in DEFAULTS})
    print(json.dumps(describe(spec, args.tenants), indent=2))


if __name__ == '__main__':
    main()
