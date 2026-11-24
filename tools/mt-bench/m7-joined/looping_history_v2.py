"""synthetic-history-looping-2d-v2: the looping population over the evaluator's 2-day window, sized per
controller from the AID client model (lane mt-plannable-scale-20261121, artifacts aid-model/RESULTS.md).

Synthetic data only. Every value comes from a seeded generator; nothing is copied from a real trace.
v1 (looping_history.py) stays as it is; this mode has its own fixture key, row marker and readback.

    {'mode': 'synthetic-history-looping-2d-v2', 'anchorUnixMs': <multiple of 5 min>, 'seed': <int>,
     'cgmOnlyPercent': 0..100, 'cgmOnlyWithoutProfilePercent': 0..100,
     'deepHistoryTenants': <int>, 'deepHistoryDays': 3..400}

Roles and controller kinds use v1's hashes (rank of sha256(seed:ordinal), kind sha256(seed:ordinal:kind)),
so a driver reading either mode assigns the same tenants the same roles. Per 288-cycle day (the model's
ranks 1-5; model section 3 for the two-day mix):

    devicestatus  Loop 1.35 per cycle (a second status 1 s later in 7 of every 20 cycles), about 1.5 KB with
                  82 predicted points; Trio 2 per cycle (suggested, then enacted 2 s later), both carrying
                  suggested and enacted, about 3.7 KB; AAPS 1 per cycle, about 2.8 KB; CGM-only 1 per cycle,
                  uploader battery only (about 0.1 KB)
    treatments    Loop 226 Temp Basal, 3 bolus, 3 carbs, 1 Temporary Override, a Site Change every second
                  day; Trio 176 Temp Basal, 50 SMB, 3 bolus, 3 carbs, 1 Exercise or Temporary Target, 1 Note;
                  AAPS 147 Temp Basal, 60 SMB, 3 bolus, 3 carbs, 1 Temporary Target, and one Profile Switch
                  10 days before the anchor (inside the 372-day lookup, outside the 2-day rows);
                  CGM-only 1 meal bolus with carbs and 1 correction
    identity      Loop `syncIdentifier` on doses and carbs, override `_id` = a UUID (stored as `identifier`
                  under UUID_HANDLING), Site Change none; Trio `id` on pump events and carbs, Exercise,
                  Temporary Target and Note none; AAPS `identifier` (what API v3 would store) plus pumpId;
                  CGM-only none (Careportal entries)
    profile       one profile per store (Loop and AAPS `Default`, Trio `default`), about 2.2 KB; Loop 2
                  documents (revisions), Trio and AAPS 1; a CGM-only tenant 1, except the stated share
                  cgmOnlyWithoutProfilePercent of CGM-only tenants, which have none (they log the Basal plugin's
                  "treatment profile" line every cycle, as such a site does in either mode)
    deep          a looping tenant over deepHistoryDays, with one more profile revision per 30 days

The seed posts the profile FIRST, so no tenant is evaluated with entries and no profile while seeding.
"""
import collections
import hashlib
import json
import math
import random
import sys
import time

import looping_history as v1
import populated_history as h

MODE = 'synthetic-history-looping-2d-v2'
DEVICE = 's4_history_fixture_looping_2d_v2'
DAYS = v1.DAYS
CYCLES_PER_DAY = v1.CYCLES_PER_DAY
DAY_MS = v1.DAY_MS
STEP_MS = h.STEP_MS
KEYS = ('mode', 'anchorUnixMs', 'seed', 'cgmOnlyPercent', 'cgmOnlyWithoutProfilePercent', 'deepHistoryTenants',
        'deepHistoryDays')
DEFAULTS = dict(seed=20261121, cgmOnlyPercent=20, cgmOnlyWithoutProfilePercent=50, deepHistoryTenants=0, deepHistoryDays=90)
# Optional realism keys (lane fixture-realism-20261123). Absent = the 2026-11-21 fixture, byte for byte and key for
# key; present, they are part of the spec and so of the fixture-catalog key.
#   phaseSpreadMs 1..299999  each tenant's history grid sits phase ms before the shared 5-minute grid, phase in
#                            [0, phaseSpreadMs) from sha256(seed:ordinal:phase). Tenants stop sharing due instants.
#   historyDays   3..60      every non-deep tenant carries this many days instead of 2 (deepHistoryDays still
#                            governs the deep role)
#   unseededTailTenants     keep this many host-ordered trailing tenants free of fixture history
#                         for connector catch-up. Their identities remain in the full provisioned roster.
OPTIONAL_KEYS = ('phaseSpreadMs', 'historyDays', 'unseededTailTenants')
MAX_HISTORY_DAYS = 60
PRESETS = {   # name -> option changes over DEFAULTS; each is its own fixture key
    'spread-v1': dict(phaseSpreadMs=299_000),
    'depth-14d-v1': dict(historyDays=14),
    'depth-30d-v1': dict(historyDays=30),
    'spread-depth-14d-v1': dict(phaseSpreadMs=299_000, historyDays=14),
}
MAX_DEEP_DAYS = v1.MAX_DEEP_DAYS
KINDS = v1.KINDS
DS_PREFIX = {'loop': 'loop://', 'aaps': 'openaps://', 'trio': 'openaps://', 'cgm': 'xdrip://'}
DS_DEVICES = tuple(sorted({p + DEVICE for p in DS_PREFIX.values()}))

# Per 288-cycle day, by controller kind (model section 2 planner's table, section 3 two-day mix).
DAY = {
    'loop': dict(tempBasal=226, bolus=3, carbs=3, override=1),       # + Site Change every second day
    'trio': dict(tempBasal=176, smb=50, bolus=3, carbs=3, overrideOrTarget=1, note=1),
    'aaps': dict(tempBasal=147, smb=60, bolus=3, carbs=3, tempTarget=1),
    'cgm': dict(meal=1, correction=1),
}
LOOP_SITE_CHANGE_EVERY_DAYS = 2
AAPS_SWITCH_AGE_DAYS = 10
# Devicestatus per cycle: Loop 1 + 7/20 (1.35), Trio 2, AAPS 1, CGM-only 1 (battery).
LOOP_EXTRA = (7, 20)
TRIO_ENACTED_DELAY_MS = 2_000
LOOP_EXTRA_DELAY_MS = 1_000
PROFILES = dict(loop=2, trio=1, aaps=1, cgm=1)
MEAL_MINUTES = v1.MEAL_MINUTES
# A request body bound (the seed's boundaries only, not its rows): a Trio day of statuses is about 1.1 MB.
SEED_BODY_MAX_BYTES = 900_000
CHECKED = v1.CHECKED

_r1, _r2, _r4 = v1._r1, v1._r2, v1._r4
require = v1.require


def default_spec(anchor, **changes):
    return dict(mode=MODE, anchorUnixMs=anchor, **(DEFAULTS | changes))


def validate(spec):
    require(isinstance(spec, dict) and spec.get('mode') == MODE and set(KEYS) <= set(spec) <= set(KEYS) | set(OPTIONAL_KEYS),
            'UNSUPPORTED')
    ints = all(type(spec[k]) is int for k in KEYS[1:] + tuple(k for k in OPTIONAL_KEYS if k in spec))
    require(ints and 1 <= spec.get('phaseSpreadMs', 1) < STEP_MS and 3 <= spec.get('historyDays', 3) <= MAX_HISTORY_DAYS
            and spec.get('unseededTailTenants', 1) >= 1,
            'LOOPING_OPTIONS')
    require(ints and 0 <= spec['seed'] < 2**63 and 0 <= spec['cgmOnlyPercent'] <= 100
            and 0 <= spec['cgmOnlyWithoutProfilePercent'] <= 100
            and 0 <= spec['deepHistoryTenants'] <= 1000 and 3 <= spec['deepHistoryDays'] <= MAX_DEEP_DAYS, 'LOOPING_OPTIONS')
    anchor = spec['anchorUnixMs']
    require(max(DAYS, spec['deepHistoryDays'], spec.get('historyDays', 0), AAPS_SWITCH_AGE_DAYS + 1) * CYCLES_PER_DAY * STEP_MS <= anchor < 253402300800000
            and anchor % STEP_MS == 0, 'ANCHOR')


def _v1_view(spec):
    """The v1 spec with the same role inputs: roles and kinds are v1's hashes."""
    return dict(mode=v1.MODE, anchorUnixMs=spec['anchorUnixMs'],
                **{k: spec[k] for k in ('seed', 'cgmOnlyPercent', 'deepHistoryTenants', 'deepHistoryDays')})


def roles(spec, n):
    """'looping', 'cgm-only' or 'deep' per ordinal: identical to v1 for the same seed and options."""
    validate(spec)
    return v1.roles(_v1_view(spec), n)


def kind(spec, ordinal):
    return v1.kind(spec, ordinal)


def without_profile(spec, n):
    """Ordinals of CGM-only tenants with no profile document: the first round(share) by rank sha256(seed:ordinal:profile)."""
    role = roles(spec, n)
    cgm = [i for i in range(n) if role[i] == 'cgm-only']
    cgm.sort(key=lambda i: hashlib.sha256(f"{spec['seed']}:{i}:profile".encode()).hexdigest())
    return frozenset(cgm[:(len(cgm) * spec['cgmOnlyWithoutProfilePercent'] + 50) // 100])


def seed_roles(spec, n):
    """Roles as the receipt groups them: CGM-only tenants without a profile are 'cgm-only-no-profile'."""
    role, bare = roles(spec, n), without_profile(spec, n)
    return [('cgm-only-no-profile' if i in bare else r) for i, r in enumerate(role)]


def tenant_factory(spec, n):
    role, bare = roles(spec, n), without_profile(spec, n)
    return lambda i: Tenant(spec, i, role[i], profile=i not in bare)


def days_for(spec, role):
    return v1.days_for(spec, role)


def loop_extra(index):
    """Whether cycle `index` (counted from the tenant's first cycle) carries Loop's second status."""
    return (index * LOOP_EXTRA[0]) % LOOP_EXTRA[1] < LOOP_EXTRA[0]


def devicestatus_rows(kind_, n):
    if kind_ == 'trio':
        return 2 * n
    if kind_ == 'loop':
        return n + sum(loop_extra(i) for i in range(n))
    return n


def treatments_rows(kind_, days):
    if kind_ == 'cgm':
        return days * sum(DAY['cgm'].values())
    count = days * sum(DAY[kind_].values())
    if kind_ == 'loop':
        count += days // LOOP_SITE_CHANGE_EVERY_DAYS
    if kind_ == 'aaps':
        count += 1
    return count


def profile_rows(kind_, days, profile=True):
    if not profile:
        return 0
    return PROFILES[kind_] + (days // 30 if days > DAYS else 0)


def rows_per_tenant(spec, role='looping', kind_=None):
    """Stored rows per tenant by collection (exact; counts do not depend on the seed). A looping role
    without a kind is the mean over the three controllers (they are equal shares by hash)."""
    validate(spec)
    days = days_for(spec, role)
    n = days * CYCLES_PER_DAY
    if role in ('cgm-only', 'cgm-only-no-profile'):
        return dict(entries=n, devicestatus=n, treatments=treatments_rows('cgm', days),
                    profile=profile_rows('cgm', days, role == 'cgm-only'))
    if kind_ is None:
        rows = [rows_per_tenant(spec, role, k) for k in KINDS]
        return {c: round(sum(r[c] for r in rows) / len(rows), 2) for c in rows[0]}
    return dict(entries=n, devicestatus=devicestatus_rows(kind_, n), treatments=treatments_rows(kind_, days),
                profile=profile_rows(kind_, days))


def _uuid(*parts):
    x = hashlib.sha256(':'.join(map(str, parts)).encode()).hexdigest()
    return f'{x[:8]}-{x[8:12]}-4{x[13:16]}-8{x[17:20]}-{x[20:32]}'


class Tenant(v1.Tenant):
    """v1's series (SGV, IOB, COB, battery, reservoir) over v2's treatments."""

    def __init__(self, spec, ordinal, role, profile=True):
        self.has_profile = profile or role != 'cgm-only'
        super().__init__(spec, ordinal, role)

    def _rng(self, *parts):
        return random.Random(':'.join(map(str, ('looping-v2', self.spec['seed'], self.ordinal) + parts)))

    def _treatments(self):
        """(cycle, eventType, insulin, carbs, extra) per 288-cycle block counted forward from the first cycle."""
        out = []
        for block in range(self.days):
            base = block * CYCLES_PER_DAY
            block_start = self.grid(base)
            rng = self._rng('block', block_start)
            minute = lambda c: ((block_start + c * STEP_MS) % DAY_MS) // 60_000
            by_minute = {minute(c): c for c in range(CYCLES_PER_DAY)}

            def at(clock_minute):
                return base + by_minute[(clock_minute // 5 * 5) % 1440]

            meals = [at(m + 5 * rng.randrange(-6, 7)) for m in MEAL_MINUTES]
            carbs = [rng.choice((30, 40, 45, 50, 60, 75)) for _ in meals]
            if self.kind == 'cgm':
                out.append((meals[1], 'Meal Bolus', _r2(carbs[1] / 10), carbs[1], None))
                out.append((at(1260 + 5 * rng.randrange(0, 12)), 'Correction Bolus', _r2(rng.randrange(2, 7) * 0.5), None, None))
                continue
            d = DAY[self.kind]
            bolus_type = {'loop': 'Correction Bolus', 'trio': 'Bolus', 'aaps': 'Correction Bolus'}[self.kind]
            for c, g in zip(meals, carbs):
                out.append((c, 'Carb Correction', None, g, None))
                out.append((c, bolus_type, _r2(round(g / 10 * 0.7 / 0.05) * 0.05), None, 'manual'))
            for c in sorted(rng.sample(range(CYCLES_PER_DAY), d['tempBasal'])):
                out.append((base + c, 'Temp Basal', None, None, _r2(rng.randrange(0, 33) * 0.05)))
            if 'smb' in d:
                smb_type = 'SMB' if self.kind == 'trio' else 'Correction Bolus'
                taken = {c - base for c, kind_, *_ in out if kind_ == smb_type and c >= base}
                free = [c for c in range(CYCLES_PER_DAY) if c not in taken]
                for c in sorted(rng.sample(free, d['smb'])):
                    out.append((base + c, smb_type, _r2(rng.randrange(1, 21) * 0.05), None, 'smb'))
            first, second = sorted(rng.sample(range(CYCLES_PER_DAY), 2))
            if self.kind == 'loop':
                out.append((base + first, 'Temporary Override', None, None, rng.choice(('Exercise', 'Pre-Meal'))))
                if block % LOOP_SITE_CHANGE_EVERY_DAYS == LOOP_SITE_CHANGE_EVERY_DAYS - 1:
                    out.append((base + second, 'Site Change', None, None, None))
            elif self.kind == 'trio':
                if block % 2 == 0:
                    out.append((base + first, 'Exercise', None, None, 'Exercise'))
                else:
                    out.append((base + first, 'Temporary Target', None, None, rng.choice(('Activity', 'Eating Soon', 'Hypo'))))
                out.append((base + second, 'Note', None, None, rng.choice(('Pump suspended', 'Pump resumed', 'Rewind'))))
            else:
                out.append((base + first, 'Temporary Target', None, None, rng.choice(('Activity', 'Eating Soon', 'Hypo'))))
        if self.kind == 'aaps':
            # one older switch: inside the evaluator's 372-day lookup, outside the 2-day rows
            out.append((self.n - 1 - AAPS_SWITCH_AGE_DAYS * CYCLES_PER_DAY, 'Profile Switch', None, None, 'Default'))
        out.sort(key=lambda t: (t[0], t[1]))
        return out

    def ds_stamps(self):
        """(cycle index, offset ms, which) for every devicestatus row, in time order."""
        out = []
        for i in range(self.n):
            if self.kind == 'trio':
                out += [(i, 0, 'suggested'), (i, TRIO_ENACTED_DELAY_MS, 'enacted')]
            elif self.kind == 'loop':
                out.append((i, 0, 'loop'))
                if loop_extra(i):
                    out.append((i, LOOP_EXTRA_DELAY_MS, 'recommendation'))
            else:
                out.append((i, 0, self.kind))
        return out

    def expected(self):
        e = v1.entries(self)
        e = [dict(r, device=DEVICE) for r in e]
        ds = self.ds_stamps()
        return dict(entries=len(e), entriesMd5=h.digest(e), devicestatus=len(ds),
                    dsBattery=sum(self.battery[i] for i, _, _ in ds),
                    treatments=len(self.treatments),
                    insulinX100=round(sum(t[2] or 0 for t in self.treatments) * 100),
                    carbs=sum(t[3] or 0 for t in self.treatments),
                    profile=len(profiles(self)))

    @property
    def store_name(self):
        return 'default' if self.kind == 'trio' else 'Default'


# ------------------------------------------------------------------ documents

def entries(t):
    return [dict(r, device=DEVICE) for r in v1.entries(t)]


def _loop_status(t, i, iso, which):
    """Loop: a stored recommendation; the first of a cycle carries the enacted dose (about 1.5 KB)."""
    rate = t.tbr.get(i, 0.8)
    doc = {'device': DS_PREFIX['loop'] + DEVICE, 'created_at': iso,
           'loop': {'name': 'Loop', 'version': '3.4.4', 'timestamp': iso,
                    'iob': {'iob': t.iob[i], 'timestamp': iso}, 'cob': {'cob': t.cob[i], 'timestamp': iso},
                    'predicted': {'startDate': iso, 'values': v1._prediction(t, i, 82, 0.93)},
                    'automaticDoseRecommendation': {'timestamp': iso, 'tempBasalAdjustment': {'rate': rate, 'duration': 30},
                                                    'bolusVolume': 0},
                    'recommendedBolus': 0},
           'pump': {'clock': iso, 'pumpID': 'synthetic-' + str(t.ordinal % 997), 'manufacturer': 'Insulet', 'model': 'Dash',
                    'battery': {'percent': 100 - i % 100}, 'suspended': False, 'bolusing': False,
                    'reservoir': t.reservoir[i], 'secondsFromGMT': 0},
           'uploader': {'name': 'iPhone', 'timestamp': iso, 'battery': t.battery[i], 'model': 'iPhone15,2',
                        'systemVersion': '17.5.1', 'batteryState': 'unplugged'},
           'override': {'active': False, 'timestamp': iso, 'currentCorrectionRange': {'minValue': 100, 'maxValue': 115}},
           'radioAdapter': {'hardware': 'RileyLink', 'name': 'synthetic', 'firmwareVersion': 'ble_rfspy 2.0',
                            'RSSI': -60 - i % 20, 'pumpRSSI': -70 - i % 15}}
    if which == 'loop':
        doc['loop']['enacted'] = {'rate': rate, 'duration': 30, 'timestamp': iso, 'received': True, 'bolusVolume': 0}
    return doc


def _trio_status(t, i, iso, which):
    """Trio: one object with the latest suggested and enacted (the previous one reused), about 3.7 KB."""
    doc = v1._oref(t, i, iso, True)
    doc['device'] = DS_PREFIX['trio'] + DEVICE
    suggested = doc['openaps']['suggested']
    preds = suggested['predBGs']
    preds.setdefault('COB', v1._prediction(t, i, 48, 0.97, 0.3))
    for k in ('IOB', 'ZT', 'UAM', 'COB'):
        preds[k] = preds[k][:{'IOB': 48, 'ZT': 29, 'UAM': 48, 'COB': 48}[k]]
    tdd = 38.5 + (t.ordinal % 7)
    suggested['reason'] += ('Dynamic ISF/CR: On/Off, Logarithmic formula, AF: 0.8, Basal ratio: 1.0, '
                            f'SMB Ratio: 0.5, Smoothing: On, TDD: {_r1(tdd)} U, ')
    suggested['insulin'] = {'TDD': _r2(tdd), 'bolus': _r2(tdd * 0.45), 'temp_basal': _r2(tdd * 0.3),
                            'scheduled_basal': _r2(tdd * 0.25)}
    suggested.update(carbsReq=0, smbToDeliver=0, units=0, predictedBG=suggested['eventualBG'], received=False)
    enacted = dict(suggested, received=True)
    if which == 'suggested':                       # the enacted carried is the previous cycle's
        enacted['timestamp'] = enacted['deliverAt'] = h._iso(t.stamp(max(0, i - 1)))
    doc['openaps']['enacted'] = enacted
    doc['openaps']['version'] = '0.7.1'
    doc['openaps']['iob']['lastTemp'] = {'date': t.stamp(i), 'duration': 30.0, 'rate': suggested['rate']}
    doc['pump']['bolusIncrement'] = 0.05
    doc['uploader']['isCharging'] = t.battery[i] > 90
    return doc


def _aaps_status(t, i, iso, which):
    doc = v1._oref(t, i, iso, i in t.tbr)
    doc['device'] = DS_PREFIX['aaps'] + DEVICE
    return doc


def _cgm_status(t, i, iso, which):
    return {'device': DS_PREFIX['cgm'] + DEVICE, 'created_at': iso, 'uploader': {'battery': t.battery[i]}}


STATUS = dict(loop=_loop_status, trio=_trio_status, aaps=_aaps_status, cgm=_cgm_status)


def devicestatus(t):
    build = STATUS[t.kind]
    return [build(t, i, h._iso(t.stamp(i) + offset), which) for i, offset, which in t.ds_stamps()]


def _store(t, rng, scale):
    hours = 2 if t.kind == 'loop' else 1      # Loop's document also carries loopSettings
    basal = [_r2(rng.randrange(10, 25) * 0.05 * scale) for _ in range(24 // hours)]
    isf, cr = rng.randrange(35, 70), rng.randrange(7, 15)
    return {t.store_name: {
        'dia': 6 if t.kind == 'loop' else 5, 'carbratio': v1._schedule([cr, cr + 2, cr + 1, cr], 6),
        'sens': v1._schedule([isf, isf - 5, isf, isf + 5], 6), 'basal': v1._schedule(basal, hours),
        'target_low': v1._schedule([100, 95, 100], 8), 'target_high': v1._schedule([120, 115, 120], 8),
        'units': 'mg/dl', 'timezone': 'UTC', 'delay': 20, 'carbs_hr': 20, 'startDate': '1970-01-01T00:00:00.000Z'}}


def profiles(t):
    if not t.has_profile:
        return []
    count = profile_rows(t.kind, t.days)
    out = []
    for r in range(count):
        stamp = t.first + (t.n - 1) * STEP_MS * r // count
        iso = h._iso(stamp)
        rng = t._rng('profile', r)
        doc = {'defaultProfile': t.store_name, 'startDate': iso, 'created_at': iso, 'mills': stamp, 'units': 'mg/dl',
               'enteredBy': DEVICE, 'store': _store(t, rng, 1 + 0.05 * r)}
        if t.kind == 'loop':
            doc['loopSettings'] = {'dosingEnabled': True, 'dosingStrategy': 'tempBasalOnly', 'maximumBasalRatePerHour': 3.2,
                                   'maximumBolus': 8, 'minimumBGGuard': 75, 'preMealTargetRange': [80, 90],
                                   'deviceToken': hashlib.sha256(f'device:{t.ordinal}'.encode()).hexdigest(),
                                   'bundleIdentifier': 'org.example.synthetic.loop',
                                   'overridePresets': [{'name': 'Exercise', 'symbol': 'E', 'duration': 3600,
                                                        'targetRange': [140, 160], 'insulinNeedsScaleFactor': 0.6},
                                                       {'name': 'Pre-Meal', 'symbol': 'M', 'duration': 3600,
                                                        'targetRange': [80, 90], 'insulinNeedsScaleFactor': 1.0}]}
        elif t.kind == 'trio':
            doc['overridePresets'] = [{'name': 'Exercise', 'duration': 60, 'percentage': 80, 'target': 140},
                                      {'name': 'Sick', 'duration': 240, 'percentage': 120, 'target': 110}]
            doc['bundleIdentifier'] = 'org.example.synthetic.trio'
            doc['isAPNSProduction'] = False
            doc['teamID'] = 'SYNTHETIC0'
            doc['expirationDate'] = h._iso(t.anchor + 90 * DAY_MS)
        elif t.kind == 'aaps':
            doc['app'] = 'AAPS'
        out.append(doc)
    return out


def treatments(t):
    store = (profiles(t) or [{'store': _store(t, t._rng('profile', 0), 1)}])[-1]['store']
    out = []
    for c, kind_, insulin, carbs, extra in t.treatments:
        stamp = t.stamp(c)
        iso = h._iso(stamp)
        ident = (t.spec['seed'], t.ordinal, c, kind_)
        doc = {'eventType': kind_, 'created_at': iso, 'enteredBy': DEVICE, 'utcOffset': 0}
        if insulin is not None:
            doc['insulin'] = insulin
        if carbs is not None:
            doc['carbs'] = carbs
        if t.kind == 'loop':
            if kind_ == 'Temporary Override':
                doc['_id'] = _uuid(*ident).upper()
            elif kind_ != 'Site Change':
                doc['syncIdentifier'] = hashlib.sha256(':'.join(map(str, ident)).encode()).hexdigest()
            if kind_ == 'Temp Basal':
                doc.update(duration=30, rate=extra, absolute=extra, temp='absolute', automatic=True,
                           amount=_r2(extra / 2), insulinType='Novolog', timestamp=iso, reason='loop')
            elif kind_ == 'Correction Bolus':
                doc.update(automatic=False, type='normal', duration=0, programmed=insulin, unabsorbed=0,
                           insulinType='Novolog', timestamp=iso)
            elif kind_ == 'Carb Correction':
                doc['absorptionTime'] = 180
            elif kind_ == 'Temporary Override':
                preset = {'Exercise': ([140, 160], 0.6), 'Pre-Meal': ([80, 90], 1.0)}[extra]
                doc.update(reason=extra, duration=3600, correctionRange=preset[0], insulinNeedsScaleFactor=preset[1])
        elif t.kind == 'trio':
            if kind_ in ('Temp Basal', 'SMB', 'Bolus', 'Carb Correction'):
                doc['id'] = _uuid(*ident).upper()
            if kind_ == 'Temp Basal':
                doc.update(duration=30, rate=extra, absolute=extra, temp='absolute')
            elif kind_ == 'SMB':
                doc['isSMB'] = True
            elif kind_ == 'Exercise':
                doc.update(duration=60, notes='Exercise')
            elif kind_ == 'Temporary Target':
                low, high = {'Activity': (140, 140), 'Eating Soon': (80, 80), 'Hypo': (120, 120)}[extra]
                doc.update(reason=extra, targetBottom=low, targetTop=high, duration=60, units='mg/dl')
            elif kind_ == 'Note':
                doc['notes'] = extra
        elif t.kind == 'aaps':
            sync = hashlib.sha256(':'.join(map(str, ident)).encode()).hexdigest()
            doc.update(identifier=_uuid(*ident), pumpId=int(sync[:12], 16), pumpType='OMNIPOD_DASH',
                       pumpSerial='synthetic', isValid=True, date=stamp, app='AAPS')
            if kind_ == 'Temp Basal':
                doc.update(duration=30, durationInMilliseconds=1_800_000, rate=extra, absolute=extra, type='NORMAL')
            elif kind_ == 'Correction Bolus':
                doc.update(type='SMB', isSMB=True) if extra == 'smb' else doc.update(type='NORMAL', isSMB=False)
            elif kind_ == 'Carb Correction':
                doc['duration'] = 0
            elif kind_ == 'Temporary Target':
                low, high = {'Activity': (140, 140), 'Eating Soon': (80, 80), 'Hypo': (120, 120)}[extra]
                doc.update(reason=extra, targetBottom=low, targetTop=high, duration=60, units='mg/dl')
            elif kind_ == 'Profile Switch':
                profile = store[t.store_name]
                doc.update(profile=extra, originalProfileName=extra, duration=0, originalDuration=0, percentage=100,
                           timeshift=0, profileJson=json.dumps(profile, separators=(',', ':')))
        out.append(doc)
    return out


def seed_requests(t):
    """Profile FIRST (no seed-window evaluation without a profile), then entries, devicestatus, treatments."""
    return (('/api/v1/profile', profiles(t)), ('/api/v1/entries', entries(t)), ('/api/v1/devicestatus', devicestatus(t)),
            ('/api/v1/treatments', treatments(t)))


def identity_share(t):
    """Share of treatments with no client identity (v1 fallback key without syncIdentifier/id/uuid/NSCLIENT_ID,
    `identifier` or `_id`)."""
    docs = treatments(t)
    none = [d for d in docs if not any(d.get(k) for k in ('syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID', 'identifier', '_id'))]
    return len(none) / len(docs) if docs else 0.0


# ------------------------------------------------------------------ figures

WINDOWS_MS = dict(entries=2 * DAY_MS, treatments=60 * 3_600_000, devicestatus=DAY_MS)


def _ms(iso):
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() * 1000)


def window_rows(t):
    """Rows the evaluator's windowed reads hold at the anchor (core lib/storage/clinical-working-set-policy.js:
    entries 2 d, treatments 60 h, devicestatus 1 d), plus the newest profile document if any."""
    a = t.anchor
    inside = lambda ms, w: a - w < ms <= a
    return dict(entries=sum(inside(r['date'], WINDOWS_MS['entries']) for r in entries(t)),
                treatments=sum(inside(_ms(r['created_at']), WINDOWS_MS['treatments']) for r in treatments(t)),
                devicestatus=sum(inside(_ms(r['created_at']), WINDOWS_MS['devicestatus']) for r in devicestatus(t)),
                profile=min(1, len(profiles(t))))


def _sample(spec, role, kind_):
    for i in range(100_000):
        if role.startswith('cgm-only') or kind(spec, i) == kind_:
            return Tenant(spec, i, 'cgm-only' if role.startswith('cgm-only') else role,
                          profile=role != 'cgm-only-no-profile')
    raise AssertionError('no sample')


def bytes_per_tenant(t):
    size = lambda docs: sum(len(json.dumps(d, separators=(',', ':'))) for d in docs)
    return dict(entries=size(entries(t)), devicestatus=size(devicestatus(t)), treatments=size(treatments(t)),
                profile=size(profiles(t)))


def describe(spec, tenants=10_000):
    """Rows, JSON bytes as sent and evaluator window rows per tenant per role and controller, and a population
    total at the expected role and kind shares (read-derived from the generator)."""
    validate(spec)
    shapes = {}
    for role, kinds in (('looping', KINDS), ('cgm-only', ('cgm',)), ('cgm-only-no-profile', ('cgm',))):
        for k in kinds:
            t = _sample(spec, role, k)
            rows = rows_per_tenant(spec, role, None if role.startswith('cgm') else k)
            sizes = bytes_per_tenant(t)
            ds = devicestatus(t)
            shapes[f'{role}/{k}'] = dict(rows=rows, jsonBytes=sizes, jsonBytesTotal=sum(sizes.values()),
                                         devicestatusBytesPerRow=round(sizes['devicestatus'] / len(ds)) if ds else 0,
                                         treatmentBytesPerRow=round(sizes['treatments'] / max(1, rows['treatments'])),
                                         profileBytesPerDocument=round(sizes['profile'] / rows['profile']) if rows['profile'] else 0,
                                         windowRows=window_rows(t), identityLessTreatmentShare=round(identity_share(t), 4))
    cgm = (tenants * spec['cgmOnlyPercent'] + 50) // 100
    bare = (cgm * spec['cgmOnlyWithoutProfilePercent'] + 50) // 100
    unseeded = spec.get('unseededTailTenants', 0)
    require(unseeded < tenants, 'UNSEEDED_TAIL_SIZE')
    if unseeded:
        assigned = seed_roles(spec, tenants)[:-unseeded]
        bare = assigned.count('cgm-only-no-profile')
        cgm = assigned.count('cgm-only') + bare
    looping = tenants - unseeded - cgm
    weights = {f'looping/{k}': looping / len(KINDS) for k in KINDS}
    weights.update({'cgm-only/cgm': cgm - bare, 'cgm-only-no-profile/cgm': bare})
    total = collections.Counter()
    for key, w in weights.items():
        for c, v in shapes[key]['rows'].items():
            total[c + 'Rows'] += v * w
        for c, v in shapes[key]['jsonBytes'].items():
            total[c + 'JsonBytes'] += v * w
    return dict(spec=spec, tenants=tenants, roleCounts={'looping': looping, 'cgm-only': cgm - bare,
                'cgm-only-no-profile': bare, **({'unseeded': unseeded} if unseeded else {})}, perTenant=shapes,
                population={k: round(v) for k, v in sorted(total.items())},
                populationJsonBytes=round(sum(v for k, v in total.items() if k.endswith('JsonBytes'))),
                basis='read-derived from the generator; JSON bytes as sent, not stored bytes; looping kinds at equal '
                      'expected shares (the kind hash), not one roster\'s draw')


# ------------------------------------------------------------------ seed and readback

def census(sql, tables, at, horizon):
    return v1.census_for(sql, tables, at, horizon, DEVICE, DS_DEVICES)


def run(spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=h.post, now=time.time, bulk=None):
    return v1.seed_and_verify(sys.modules[__name__], spec, tenants, base, sql, until, window_seconds,
                              verify_only=verify_only, post_batch=post_batch, now=now, bulk=bulk)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=('describe', 'spec'))
    p.add_argument('--preset', choices=sorted(PRESETS))
    p.add_argument('--phaseSpreadMs', type=int)
    p.add_argument('--historyDays', type=int)
    p.add_argument('--unseededTailTenants', type=int)
    p.add_argument('--anchor', type=int, default=1_800_000_000_000 // STEP_MS * STEP_MS)
    p.add_argument('--tenants', type=int, default=10_000)
    for key, value in DEFAULTS.items():
        p.add_argument('--' + key, type=int, default=value)
    a = p.parse_args()
    changes = {k: getattr(a, k) for k in DEFAULTS}
    changes.update(PRESETS.get(a.preset, {}))
    changes.update({k: getattr(a, k) for k in OPTIONAL_KEYS if getattr(a, k) is not None})
    spec = default_spec(a.anchor, **changes)
    validate(spec)
    print(json.dumps(spec if a.action == 'spec' else describe(spec, a.tenants), indent=2))
