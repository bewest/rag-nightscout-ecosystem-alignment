"""Driver shape `looping-v1`: the live k6 writes shaped like the E1 looping fixture
(synthetic-history-looping-2d-v1, looping_history.py). Lane mt-plannable-scale-20261121, E3.

- Roles come from the fixture's own rank hash (looping_history.roles over the provisioned roster in
  host order, as the seed assigns them), so the driver and the seed agree: CGM-only tenants post SGV
  only; looping (and deep) tenants also post one devicestatus per 5 min and treatments.
- Devicestatus bodies are the generator's own Loop, AAPS and Trio documents (a short rotation per
  controller kind), with every timestamp the generator wrote replaced by the post time.
- Treatment posts: one per looping tenant every TREATMENT_CYCLE_MS, the generator's treatment-carrying
  cycles per day (read-derived, about 565 s). CGM-only tenants' four logged treatments a day are not
  driven (about 0.009 req/s per 1,000 tenants).
"""
import json

import looping_history as lh

SHAPE = 'looping-v1'
PLACEHOLDER = '2000-01-01T00:00:00.000Z'
ROTATION = 6  # documents per controller kind (env size: about 40 KB in all)


def reference_spec():
    """Templates depend only on the generator's document shapes, not on the run's seed."""
    return dict(mode=lh.MODE, anchorUnixMs=1_700_000_100_000 // 300_000 * 300_000, seed=20261121,
                cgmOnlyPercent=20, deepHistoryTenants=0, deepHistoryDays=90)


def treatment_cycle_ms(spec=None, sample=12):
    spec = spec or reference_spec()
    per_day = sum(lh.post_cycles_per_day(spec, 'looping', i) for i in range(sample)) / sample
    return round(86_400_000 / per_day)


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


def environment():
    docs, mean = templates()
    return {'M7_DRIVER_SHAPE': SHAPE,
            'M7_LOOPING_TEMPLATES': json.dumps({'placeholder': PLACEHOLDER, 'documents': docs}, separators=(',', ':')),
            'M7_LOOPING_TREATMENT_CYCLE_MS': str(treatment_cycle_ms())}


def annotate(spec, provisioned, ordinary):
    """Rows of `ordinary` with loopKind ('loop', 'aaps', 'trio') or None (CGM-only), from the seed's roles."""
    lh.validate(spec)
    hosts = sorted(row['host'] for row in provisioned)
    roles = lh.roles(spec, len(hosts))
    by_host = {host: (None if roles[i] == 'cgm-only' else lh.kind(spec, i)) for i, host in enumerate(hosts)}
    return [{**row, 'loopKind': by_host[row['host']]} for row in ordinary]


if __name__ == '__main__':
    docs, mean = templates()
    print(json.dumps({'treatmentCycleMs': treatment_cycle_ms(), 'meanDevicestatusBytes': round(mean),
                      'bytesByKind': {k: [len(d) for d in v] for k, v in docs.items()},
                      'envBytes': len(environment()['M7_LOOPING_TEMPLATES'])}))
