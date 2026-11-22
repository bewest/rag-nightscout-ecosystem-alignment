"""Driver shapes for the looping fixtures: the live k6 writes shaped like real AID uploaders.
Lane mt-plannable-scale-20261121.

`looping-v1` (E3): writes shaped like the E1 fixture (synthetic-history-looping-2d-v1, looping_history.py).
- Roles come from the fixture's own rank hash (looping_history.roles over the provisioned roster in
  host order, as the seed assigns them), so the driver and the seed agree: CGM-only tenants post SGV
  only; looping (and deep) tenants also post one devicestatus per 5 min and treatments.
- Devicestatus bodies are the generator's own Loop, AAPS and Trio documents (a short rotation per
  controller kind), with every timestamp the generator wrote replaced by the post time.
- Treatment posts: one per looping tenant every TREATMENT_CYCLE_MS, the generator's treatment-carrying
  cycles per day (read-derived, about 565 s). CGM-only tenants' four logged treatments a day are not
  driven (about 0.009 req/s per 1,000 tenants).

`looping-v2` (the AID client model, artifacts aid-model/RESULTS.md, diffs D1-D5; live load only, no reseed).
Roles are the same hash; the v2 history (looping_history_v2.py) assigns identical roles and kinds.
- D1 devicestatus per controller: Loop 1.35 per cycle (a second status in 7 of every 20 cycles) at about
  1.5 KB; Trio 2 per cycle (suggested, then enacted) at about 3.7 KB; AAPS 1 at about 2.8 KB. Bodies are
  looping_history_v2's documents.
- D4 CGM-only tenants post a battery-only devicestatus (about 0.1 KB) per cycle.
  One request per k6 iteration (the driver accounting's invariant): the w_devicestatus scenario walks a
  20-cycle wheel, cycle-major, each tenant's posts adjacent in tenant order (so phases stay spread and a
  Trio pair lands back to back). Rate = wheel slots per 20 cycles.
- D2 treatments: one request per looping tenant per 400 s (216 a day).
- D3 routes: Loop and Trio POST /api/v1/treatments arrays (Loop 1-2 documents, 1.1 per request, with
  `syncIdentifier`; Trio 1-2, 1.2 per request, with `id`); AAPS POST /api/v3/treatments, one document, no
  identifier (the server computes it). Identity-less documents: Loop a Site Change in 1 of 200 requests
  (0.45 % of documents), Trio an Exercise, Temporary Target or Note in 1 of 42 requests (1.98 %).
- D5 Loop profile: in 1 of every 648 rounds (3 days at 400 s) a Loop tenant's treatment slot posts its
  profile (POST /api/v1/profile, about 2.2 KB) instead; the request rate is unchanged.
- The k6 scenario keys stay the seven accounting names: under looping-v2 `w_treatments_v3` carries every
  treatment and profile request (v1 and v3 routes); the per-route split is the bounded counter
  m7_looping_requests{request_shape}.
- Not part of steady load: the network-restored backlog (D6) is its own scenario, looping_backlog.py.
"""
import json
import math
from functools import cache

import looping_history as lh

SHAPE = 'looping-v1'
SHAPE_V2 = 'looping-v2'
SHAPES = (SHAPE, SHAPE_V2)
DEFAULT_SHAPE = SHAPE_V2          # the plannable profile's shape on a looping fixture
PLACEHOLDER = '2000-01-01T00:00:00.000Z'
ID_PLACEHOLDER = 'SYNTHETIC-IDENTITY-PLACEHOLDER'
ROTATION = 6  # documents per controller kind (env size: about 40 KB in all)
V2_ROTATION = 4  # documents per controller and post kind (env size bounded by V2_ENV_MAX_BYTES)
V2_ENV_MAX_BYTES = 100_000      # under Linux MAX_ARG_STRLEN (128 KiB) for one environment string
DS_PERIOD = 20                  # cycles in the v2 devicestatus wheel
LOOP_EXTRA = (7, 20)            # Loop: a second status in 7 of every 20 cycles (1.35 per cycle)
V2_TREATMENT_CYCLE_MS = 400_000
PROFILE_EVERY_ROUNDS = 648      # 648 x 400 s = 3 days
LOOP_TWO_DOCS, TRIO_TWO_DOCS = 10, 5            # 1 request in N carries two documents
LOOP_IDLESS, TRIO_IDLESS = 200, 42              # 1 request in N leads with an identity-less document
AAPS_SMB = (2, 7)                               # AAPS: SMB in 2 of every 7 requests, else Temp Basal
REQUEST_SHAPES = ('ds_loop', 'ds_loop_extra', 'ds_trio_suggested', 'ds_trio_enacted', 'ds_aaps', 'ds_cgm_battery',
                  'tx_loop_v1', 'tx_trio_v1', 'tx_aaps_v3', 'profile_loop_v1')


def history_module(spec):
    """The generator whose roles the seed used (v1 and v2 assign identical roles and kinds)."""
    if isinstance(spec, dict) and spec.get('mode') == 'synthetic-history-looping-2d-v2':
        import looping_history_v2
        return looping_history_v2
    return lh


def reference_spec():
    """Templates depend only on the generator's document shapes, not on the run's seed."""
    return dict(mode=lh.MODE, anchorUnixMs=1_700_000_100_000 // 300_000 * 300_000, seed=20261121,
                cgmOnlyPercent=20, deepHistoryTenants=0, deepHistoryDays=90)


def treatment_cycle_ms(spec=None, sample=12):
    spec = spec or reference_spec()
    per_day = sum(lh.post_cycles_per_day(spec, 'looping', i) for i in range(sample)) / sample
    return round(86_400_000 / per_day)


@cache
def live_treatment_cycle_ms():
    return treatment_cycle_ms()


def kind_counts(spec, tenants):
    """{'loop', 'aaps', 'trio', 'cgm'}: tenants of each kind in a roster of `tenants` (the seed's roles)."""
    hm = history_module(spec)
    hm.validate(spec)
    roles = hm.roles(spec, tenants)
    out = dict(loop=0, aaps=0, trio=0, cgm=0)
    for i, role in enumerate(roles):
        out['cgm' if role == 'cgm-only' else hm.kind(spec, i)] += 1
    return out


def wheel_slots(counts):
    """Devicestatus posts per DS_PERIOD cycles: 20 per tenant, plus Loop's 7 and Trio's 20 second posts."""
    return DS_PERIOD * sum(counts.values()) + LOOP_EXTRA[0] * counts['loop'] + DS_PERIOD * counts['trio']


def write_offers(spec, tenants, uniform_scale, write_scale, device_cycle, shape=SHAPE):
    """Return the selected population (iterations per time unit) and k6 time unit for the two looping writes."""
    hm = history_module(spec)
    hm.validate(spec)
    cgm_only = (tenants * spec['cgmOnlyPercent'] + 50) // 100
    loopers = tenants - cgm_only
    lh.require(loopers >= max(1, spec['deepHistoryTenants']), 'LOOPING_ROSTER')
    if shape == SHAPE_V2:
        unit = math.floor(V2_TREATMENT_CYCLE_MS / uniform_scale / write_scale + .5)
        lh.require(1 <= unit <= 9223372036854 and 1 <= DS_PERIOD * device_cycle <= 9223372036854, 'TREATMENT_TIME_UNIT')
        return {'w_devicestatus': (wheel_slots(kind_counts(spec, tenants)), DS_PERIOD * device_cycle),
                'w_treatments_v3': (loopers, unit)}
    lh.require(shape == SHAPE, 'DRIVER_SHAPE')
    unit = math.floor(live_treatment_cycle_ms() / uniform_scale / write_scale + .5)
    lh.require(1 <= unit <= 9223372036854, 'TREATMENT_TIME_UNIT')
    return {'w_devicestatus': (loopers, device_cycle), 'w_treatments_v3': (loopers, unit)}


def offered(spec, tenants, shape=SHAPE_V2, uniform_scale=1, write_scale=1, reads=True):
    """Offered requests/s by k6 scenario and by request shape (read-derived from the driver's own rules)."""
    import workload
    cycles = workload.realistic_cycle_ms(uniform_scale, write_scale)
    rates = {name: (5 if name == 'r_sgv' else 1) * tenants * 1000 / ms for name, ms in cycles.items()}
    for name, (count, unit) in write_offers(spec, tenants, uniform_scale, write_scale, cycles['w_devicestatus'], shape).items():
        rates[name] = count * 1000 / unit
    if not reads:
        rates = {k: v for k, v in rates.items() if k.startswith('w_')}
    out = dict(scenarios={k: round(v, 4) for k, v in rates.items()}, total=round(sum(rates.values()), 4))
    if shape == SHAPE_V2:
        c = kind_counts(spec, tenants)
        per_cycle = 1000 / cycles['w_devicestatus']
        tx = 1000 / write_offers(spec, tenants, uniform_scale, write_scale, cycles['w_devicestatus'], shape)['w_treatments_v3'][1]
        profile = tx * c['loop'] / PROFILE_EVERY_ROUNDS
        shapes = dict(ds_loop=c['loop'] * per_cycle, ds_loop_extra=c['loop'] * per_cycle * LOOP_EXTRA[0] / LOOP_EXTRA[1],
                      ds_trio_suggested=c['trio'] * per_cycle, ds_trio_enacted=c['trio'] * per_cycle,
                      ds_aaps=c['aaps'] * per_cycle, ds_cgm_battery=c['cgm'] * per_cycle,
                      tx_loop_v1=tx * c['loop'] - profile, tx_trio_v1=tx * c['trio'], tx_aaps_v3=tx * c['aaps'],
                      profile_loop_v1=profile)
        out['requestShapes'] = {k: round(v, 4) for k, v in shapes.items()}
        out['kinds'] = c
        out['documentsPerRequest'] = dict(tx_loop_v1=1 + 1 / LOOP_TWO_DOCS, tx_trio_v1=1 + 1 / TRIO_TWO_DOCS, tx_aaps_v3=1)
        out['identityLessDocumentShare'] = dict(tx_loop_v1=round(1 / LOOP_IDLESS / (1 + 1 / LOOP_TWO_DOCS), 5),
                                                tx_trio_v1=round(1 / TRIO_IDLESS / (1 + 1 / TRIO_TWO_DOCS), 5), tx_aaps_v3=0)
    return out


def templates(spec=None):
    """{kind: [document JSON text with PLACEHOLDER for the post time]} and their mean JSON bytes."""
    spec = spec or reference_spec()
    out, sizes = {}, []
    for kind_ in lh.KINDS:
        ordinal = next(i for i in range(10_000) if lh.kind(spec, i) == kind_)
        t = lh.Tenant(spec, ordinal, 'looping')
        build = lh._loop if kind_ == 'loop' else lh._oref
        enacted = sorted(t.tbr)[:ROTATION // 2]
        plain = [i for i in range(t.n) if i not in t.tbr][:ROTATION - len(enacted)]
        docs = []
        for i in sorted(enacted + plain):
            iso = lh.h._iso(t.stamp(i))
            text = json.dumps(build(t, i, iso, i in t.tbr), separators=(',', ':')).replace(iso, PLACEHOLDER)
            docs.append(text)
            sizes.append(len(text))
        out[kind_] = docs
    return out, sum(sizes) / len(sizes)


def environment(shape=SHAPE):
    if shape == SHAPE_V2:
        return environment_v2()
    lh.require(shape == SHAPE, 'DRIVER_SHAPE')
    docs, mean = templates()
    return {'M7_DRIVER_SHAPE': SHAPE,
            'M7_LOOPING_TEMPLATES': json.dumps({'placeholder': PLACEHOLDER, 'documents': docs}, separators=(',', ':')),
            'M7_LOOPING_TREATMENT_CYCLE_MS': str(live_treatment_cycle_ms())}


def reference_spec_v2():
    import looping_history_v2 as v2
    return v2.default_spec(1_700_000_100_000 // 300_000 * 300_000)


def _text(doc, *stamps):
    text = json.dumps(doc, separators=(',', ':'))
    for iso in stamps:
        text = text.replace(iso, PLACEHOLDER)
    return text


@cache
def templates_v2():
    """looping-v2 bodies: {'devicestatus': {post kind: [JSON text]}, 'treatments': {name: JSON text},
    'profile': {'loop': JSON text}}. PLACEHOLDER marks the post time and ID_PLACEHOLDER the client identity."""
    import looping_history_v2 as v2
    spec = reference_spec_v2()
    h = v2.h
    ds = {}
    for kind_ in v2.KINDS + ('cgm',):
        ordinal = next(i for i in range(10_000) if kind_ == 'cgm' or v2.kind(spec, i) == kind_)
        t = v2.Tenant(spec, ordinal, 'cgm-only' if kind_ == 'cgm' else 'looping')
        build = v2.STATUS[kind_]
        cycles = [t.n * (2 * k + 1) // (2 * V2_ROTATION) for k in range(V2_ROTATION)]   # spread over the two days
        if kind_ == 'aaps':   # AAPS carries `enacted` only when it set a temp basal: half the rotation each way
            tbr, plain = sorted(t.tbr), [i for i in range(t.n) if i not in t.tbr]
            half = V2_ROTATION // 2
            cycles = sorted([tbr[len(tbr) * (2 * k + 1) // (2 * half)] for k in range(half)]
                            + [plain[len(plain) * (2 * k + 1) // (2 * half)] for k in range(V2_ROTATION - half)])
        if kind_ == 'loop':
            ds['loop'] = [_text(build(t, i, h._iso(t.stamp(i)), 'loop'), h._iso(t.stamp(i))) for i in cycles]
            ds['loop_extra'] = [_text(build(t, i, h._iso(t.stamp(i)), 'recommendation'), h._iso(t.stamp(i))) for i in cycles]
        elif kind_ == 'trio':
            ds['trio_suggested'] = [_text(build(t, i, h._iso(t.stamp(i)), 'suggested'), h._iso(t.stamp(i)),
                                          h._iso(t.stamp(i - 1))) for i in cycles]
            ds['trio_enacted'] = [_text(build(t, i, h._iso(t.stamp(i)), 'enacted'), h._iso(t.stamp(i))) for i in cycles]
        else:
            ds[kind_] = [_text(build(t, i, h._iso(t.stamp(i)), kind_), h._iso(t.stamp(i))) for i in cycles]
    P, I = PLACEHOLDER, ID_PLACEHOLDER
    base = {'created_at': P, 'utcOffset': 0}
    tb = dict(duration=30, rate=0.85, absolute=0.85, temp='absolute')
    treatments = {
        'loop_temp_basal': dict(base, eventType='Temp Basal', syncIdentifier=I, automatic=True, amount=0.43,
                                insulinType='Novolog', timestamp=P, reason='loop', **tb),
        'loop_bolus': dict(base, eventType='Correction Bolus', syncIdentifier=I, insulin=0.35, automatic=False,
                           type='normal', duration=0, programmed=0.35, unabsorbed=0, insulinType='Novolog', timestamp=P),
        'loop_site_change': dict(base, eventType='Site Change'),
        'trio_temp_basal': dict(base, eventType='Temp Basal', id=I, **tb),
        'trio_smb': dict(base, eventType='SMB', id=I, insulin=0.2, isSMB=True),
        'trio_exercise': dict(base, eventType='Exercise', duration=60, notes='Exercise'),
        'trio_temp_target': dict(base, eventType='Temporary Target', reason='Activity', targetBottom=140, targetTop=140,
                                 duration=60, units='mg/dl'),
        'trio_note': dict(base, eventType='Note', notes='Pump resumed'),
        # v3 single documents; `date` is set per post, the identifier is the server's
        'aaps_temp_basal': dict(base, eventType='Temp Basal', app='AAPS', pumpId=0, pumpType='OMNIPOD_DASH',
                                pumpSerial='synthetic', isValid=True, durationInMilliseconds=1_800_000, type='NORMAL', **tb),
        'aaps_smb': dict(base, eventType='Correction Bolus', app='AAPS', pumpId=0, pumpType='OMNIPOD_DASH',
                         pumpSerial='synthetic', isValid=True, insulin=0.2, type='SMB', isSMB=True),
    }
    t = v2.Tenant(spec, next(i for i in range(10_000) if v2.kind(spec, i) == 'loop'), 'looping')
    profile = dict(v2.profiles(t)[-1], startDate=P, created_at=P, mills=0)
    return {'devicestatus': ds, 'treatments': {k: json.dumps(v, separators=(',', ':')) for k, v in treatments.items()},
            'profile': {'loop': json.dumps(profile, separators=(',', ':'))}}


def environment_v2():
    body = json.dumps({'placeholder': PLACEHOLDER, 'idPlaceholder': ID_PLACEHOLDER, **templates_v2()}, separators=(',', ':'))
    lh.require(len(body) <= V2_ENV_MAX_BYTES, 'TEMPLATES_TOO_LARGE')
    return {'M7_DRIVER_SHAPE': SHAPE_V2, 'M7_LOOPING_TEMPLATES': body,
            'M7_LOOPING_TREATMENT_CYCLE_MS': str(V2_TREATMENT_CYCLE_MS),
            'M7_LOOPING_V2_RULES': json.dumps(dict(dsPeriod=DS_PERIOD, loopExtra=LOOP_EXTRA, profileEvery=PROFILE_EVERY_ROUNDS,
                                                   loopTwo=LOOP_TWO_DOCS, trioTwo=TRIO_TWO_DOCS, loopIdless=LOOP_IDLESS,
                                                   trioIdless=TRIO_IDLESS, aapsSmb=AAPS_SMB), separators=(',', ':'))}


def annotate(spec, provisioned, ordinary):
    """Rows of `ordinary` with loopKind ('loop', 'aaps', 'trio') or None (CGM-only), from the seed's roles."""
    hm = history_module(spec)
    hm.validate(spec)
    hosts = sorted(row['host'] for row in provisioned)
    roles = hm.roles(spec, len(hosts))
    by_host = {host: (None if roles[i] == 'cgm-only' else hm.kind(spec, i)) for i, host in enumerate(hosts)}
    return [{**row, 'loopKind': by_host[row['host']]} for row in ordinary]


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--shape', default=SHAPE, choices=SHAPES)
    p.add_argument('--tenants', type=int, default=1000)
    a = p.parse_args()
    if a.shape == SHAPE:
        docs, mean = templates()
        print(json.dumps({'treatmentCycleMs': treatment_cycle_ms(), 'meanDevicestatusBytes': round(mean),
                          'bytesByKind': {k: [len(d) for d in v] for k, v in docs.items()},
                          'envBytes': len(environment()['M7_LOOPING_TEMPLATES'])}))
    else:
        t = templates_v2()
        print(json.dumps({'offered': offered(reference_spec_v2(), a.tenants),
                          'devicestatusBytes': {k: round(sum(map(len, v)) / len(v)) for k, v in t['devicestatus'].items()},
                          'treatmentBytes': {k: len(v) for k, v in t['treatments'].items()},
                          'profileBytes': len(t['profile']['loop']),
                          'envBytes': len(environment_v2()['M7_LOOPING_TEMPLATES'])}, indent=1))
