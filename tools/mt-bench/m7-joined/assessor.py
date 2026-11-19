"""One assessor for both platforms: decisions `four-product-failures` and `deadline-from-acceptance`.

A run fails only on four product properties:

* storedWrites   an accepted write has no stored row;
* clinical       an accepted input's durable clinical output (or a viewer frame
                 carrying it) arrived 120 s or more after acceptance, or the
                 output is missing at end of drain;
* isolation      a tenant read another tenant's data, or an authorization
                 breach: a request admitted without the permission at
                 admission time. A request admitted before a concurrent
                 revocation is not a breach (decision
                 `credential-rotation-next-request`, Amendment 1);
* datastore      the datastore was unhealthy (not ready, restarted, or did not
                 answer the end-of-run readback).

Everything else (drops, Pending Pods, missing files, malformed events, idle
tenants, latency) is a figure. Missing evidence makes a property UNMEASURED;
nothing here refuses or voids a run.

Raw events, one JSON object each, emitted by the Compose and Kubernetes
collectors alike (`collect` reads a retained load folder of either layout):

  {"event":"accepted", "tenant","domain","key","writer"}            HTTP 2xx for one write
  {"event":"stored",   "tenant","domain","key","writer"}            row read back from the datastore
  {"event":"output",   "tenant","domain","key","writer",
                       "outputTenant","acceptedToOutputMaxMs",
                       "acceptedToOutputMinMs","atDrain"}           durable output covering the input, timed
                                                                    from its acceptance: Max is the first read
                                                                    that saw it, Min the last read that proved
                                                                    it absent; atDrain is DURABLE, MISSING or
                                                                    UNKNOWN
  {"event":"frame",    "tenant","viewerTenant","key","acceptedToFrameMs"}  frame a viewer received
  {"event":"access",   "principal","target","allowed",
                       "admittedAtMs"?,"revokedAtMs"?}             authorization probe; the principal holds the
                                                                    permission for its own tenant until revokedAtMs
  {"event":"datastore","healthy","source"}                          datastore health observation
  {"event":"readback", "what":"storage"|"output","writer"}          the collector read that source for
                                                                    every accepted input of that writer
"""
import json
import os
import re
from collections import Counter
from pathlib import Path

CONTRACT = 'four-product-failures-v1'
DEADLINE_MS = int(os.environ.get('M7_CLINICAL_DEADLINE_MS', '120000'))
ORDER = {'PASS': 0, 'UNMEASURED': 1, 'FAIL': 2}
SAMPLE = 16
FIELDS = {'accepted': ('tenant', 'domain', 'key', 'writer'), 'stored': ('tenant', 'domain', 'key', 'writer'),
          'output': ('tenant', 'domain', 'key', 'writer'), 'frame': ('tenant', 'viewerTenant', 'key'),
          'access': ('principal', 'target', 'allowed'), 'datastore': ('healthy',), 'readback': ('what', 'writer')}


def worst(*verdicts):
    return max(verdicts, key=ORDER.__getitem__) if verdicts else 'UNMEASURED'


def _number(value):
    return type(value) in (int, float) and value == value and abs(value) != float('inf')


def _stats(values):
    values = sorted(v for v in values if _number(v))
    if not values:
        return None
    pick = lambda q: values[min(len(values)-1, int(q*len(values)))]
    return {'n': len(values), 'p50': pick(.5), 'p95': pick(.95), 'max': values[-1]}


def permitted_at_admission(r):
    """Authorization is checked once, at admission. Another tenant's data is
    never permitted; one's own is permitted unless the revocation took effect
    at or before admission. Without both times the request is not a breach."""
    if r['principal'] != r['target']:
        return False
    admitted, revoked = r.get('admittedAtMs'), r.get('revokedAtMs')
    return not (_number(admitted) and _number(revoked) and admitted >= revoked)


def assess(events, ids=(), *, deadline_ms=DEADLINE_MS, figures=None):
    """Judge the four properties from raw events. Never raises on event shape."""
    ids = set(ids)
    figures = dict(figures or {})
    by = {kind: [] for kind in FIELDS}
    malformed = 0
    for row in events:
        kind = row.get('event') if isinstance(row, dict) else None
        if kind not in FIELDS or any(row.get(f) is None for f in FIELDS[kind]):
            malformed += 1
            continue
        by[kind].append(row)
    ident = lambda r: (r['tenant'], r['domain'], str(r['key']), r['writer'])
    accepted = {ident(r) for r in by['accepted']}
    readback = {(r['what'], r['writer']) for r in by['readback']}
    examples = lambda items: sorted(items)[:SAMPLE]

    # storedWrites
    stored = {ident(r) for r in by['stored']}
    judged = {a for a in accepted if ('storage', a[3]) in readback}
    missing = judged - stored
    storage = {'verdict': 'FAIL' if missing else 'UNMEASURED' if judged != accepted or not accepted else 'PASS',
               'codes': ['ACCEPTED_WRITE_NOT_STORED'] if missing else [] if judged == accepted and accepted
               else ['STORAGE_READBACK_MISSING'],
               'accepted': len(accepted), 'stored': len(accepted & stored), 'notStored': len(missing),
               'unread': len(accepted - judged), 'notStoredExamples': examples(missing)}

    # clinical deadline from acceptance, through end of drain
    outputs, frames = {}, {}
    for r in by['output']:
        outputs.setdefault(ident(r), []).append(r)
    for r in by['frame']:
        frames.setdefault((r['tenant'], str(r['key'])), []).append(r)
    status = Counter()
    late_examples, missing_examples = [], []
    for a in sorted(accepted):
        rows = outputs.get(a, [])
        frame_ms = [f.get('acceptedToFrameMs') for f in frames.get((a[0], a[2]), [])]
        if (any(_number(r.get('acceptedToOutputMinMs')) and r['acceptedToOutputMinMs'] >= deadline_ms for r in rows)
                or any(_number(ms) and ms >= deadline_ms for ms in frame_ms)):
            status['LATE'] += 1
            late_examples.append(a)
        elif any(r.get('atDrain') == 'DURABLE' and _number(r.get('acceptedToOutputMaxMs'))
                 and r['acceptedToOutputMaxMs'] < deadline_ms for r in rows):
            status['ON_TIME'] += 1
        elif any(r.get('atDrain') == 'MISSING' for r in rows) or not rows and ('output', a[3]) in readback:
            status['MISSING_AT_DRAIN'] += 1
            missing_examples.append(a)
        else:
            status['UNMEASURED'] += 1
    clinical_codes = (['CLINICAL_DEADLINE'] if status['LATE'] else []) + (
        ['CLINICAL_OUTPUT_MISSING_AT_DRAIN'] if status['MISSING_AT_DRAIN'] else []) + (
        ['CLINICAL_TIMING_UNMEASURED'] if status['UNMEASURED'] or not accepted else [])
    clinical = {'verdict': 'FAIL' if status['LATE'] or status['MISSING_AT_DRAIN'] else
                'UNMEASURED' if status['UNMEASURED'] or not accepted else 'PASS',
                'codes': clinical_codes, 'deadlineMs': deadline_ms, 'acceptedInputs': len(accepted),
                'classifications': dict(status), 'lateExamples': late_examples[:SAMPLE],
                'missingExamples': missing_examples[:SAMPLE],
                'acceptedToOutputMaxMs': _stats(r.get('acceptedToOutputMaxMs') for r in by['output']),
                'acceptedToFrameMs': _stats(r.get('acceptedToFrameMs') for r in by['frame'])}

    # isolation: data observed by, or granted to, a tenant other than its owner
    breaches = Counter()
    for r in by['output']:
        if r.get('outputTenant') not in (None, r['tenant']):
            breaches['FOREIGN_OUTPUT'] += 1
    for r in by['frame']:
        if r['viewerTenant'] != r['tenant']:
            breaches['FOREIGN_FRAME'] += 1
    for r in by['access']:
        if r['allowed'] is True and not permitted_at_admission(r):
            breaches['CROSS_TENANT_ACCESS' if r['principal'] != r['target'] else 'ADMITTED_AFTER_REVOCATION'] += 1
    if ids:
        foreign = {r['tenant'] for r in by['stored'] if r['tenant'] not in ids}
        if foreign:
            breaches['FOREIGN_STORED_ROW'] += len(foreign)
    witnessed = len(by['output']) + len(by['frame']) + len(by['access'])
    isolation = {'verdict': 'FAIL' if breaches else 'PASS' if witnessed else 'UNMEASURED',
                 'codes': sorted(breaches) if breaches else [] if witnessed else ['ISOLATION_UNWITNESSED'],
                 'breaches': dict(breaches), 'witnesses': witnessed}

    # datastore health
    health = [r['healthy'] for r in by['datastore']]
    datastore = {'verdict': 'FAIL' if False in health else 'PASS' if True in health else 'UNMEASURED',
                 'codes': ['DATASTORE_UNHEALTHY'] if False in health else [] if health else ['DATASTORE_UNOBSERVED'],
                 'observations': Counter(r.get('source', 'unknown') + ':' + ('healthy' if r['healthy'] is True
                                         else 'unhealthy') for r in by['datastore'])}

    components = {'storedWrites': storage, 'clinical': clinical, 'isolation': isolation, 'datastore': datastore}
    active = {r['tenant'] for r in by['accepted']}
    figures.update(events={k: len(v) for k, v in by.items()}, malformedEvents=malformed,
                   rosterTenants=len(ids), tenantsWithInput=len(active), idleTenants=len(ids - active) if ids else None,
                   acceptedByWriter=dict(Counter(a[3] for a in accepted)))
    return {'kind': 'product-assessment', 'contract': CONTRACT, 'instrument': {'contract': CONTRACT},
            'verdict': worst(*(c['verdict'] for c in components.values())),
            'components': components, 'figures': figures,
            'scope': 'four product properties only; everything else is a figure'}


# --------------------------------------------------------------- collector

def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _writer(marker, run):
    return 'probe' if isinstance(marker, str) and marker.endswith('-probe') else 'ordinary'


def k6_acks(folder):
    """`m7-input-accepted` lines that k6 logs at each HTTP success."""
    events, bad = [], 0
    for path in sorted(Path(folder).glob('k6-shard-*.log')) or [Path(folder)/'k6.log']:
        if not path.is_file():
            continue
        with path.open(errors='replace') as stream:
            for line in stream:
                if 'm7-input-accepted' not in line:
                    continue
                try:
                    match = re.search(r'\bmsg=("(?:[^"\\]|\\.)*")', line)
                    row = json.loads(json.loads(match[1]) if match else json.loads(line)['msg'])
                    events.append({'event': 'accepted', 'tenant': row['tenant'], 'domain': row['domain'],
                                   'key': str(row['key']), 'writer': 'ordinary', 'requestMs': row.get('requestToAcceptanceMs')})
                except (ValueError, KeyError, TypeError):
                    bad += 1
    return events, bad


def probe_events(completed, viewers):
    """Probe witnesses: acceptance, durable-output timing and viewer frames."""
    events = []
    for w in (completed or {}).get('witnesses') or []:
        timing = w.get('clinicalTiming') if isinstance(w, dict) and isinstance(w.get('clinicalTiming'), dict) else {}
        if not isinstance(w, dict) or w.get('tenant') is None or w.get('acceptedAt') is None and timing.get('accepted') is not True:
            continue
        base = {'tenant': w['tenant'], 'domain': 'entries', 'key': str(w.get('date')), 'writer': 'probe'}
        events.append({'event': 'accepted', **base})
        output = ((w.get('rawRow') or {}).get('state') or {}).get('output') or {}
        durable = timing.get('durableObserved') is True
        events.append({'event': 'output', **base, 'outputTenant': output.get('tenant') if durable else None,
                       'acceptedToOutputMaxMs': timing.get('acceptanceToCompletionMs') if durable else None,
                       'acceptedToOutputMinMs': timing.get('acceptanceToCompletionLowerMs'),
                       'atDrain': 'DURABLE' if durable else 'UNKNOWN'})
        accepted = timing.get('acceptedMono')
        observed = [f for f in w.get('clientObservations') or [] if isinstance(f, dict) and f.get('socket') in viewers]
        for f in observed:
            events.append({'event': 'frame', 'tenant': w['tenant'], 'viewerTenant': viewers[f['socket']], 'key': base['key'],
                           'acceptedToFrameMs': f['atMono'] - accepted if _number(f.get('atMono')) and _number(accepted) else None})
        if not observed:   # matched frames on the tenant's own viewers, timed by the probe
            events += [{'event': 'frame', 'tenant': w['tenant'], 'viewerTenant': w['tenant'], 'key': base['key'],
                        'acceptedToFrameMs': ms} for ms in timing.get('acceptanceToFrameMs') or []]
    return events


def sampled_clinical(completed):
    """The clinical property over the probe's witnesses alone."""
    events = probe_events(completed, {}) + [{'event': 'readback', 'what': 'output', 'writer': 'probe'}]
    return assess(events)['components']['clinical']


def count_events(findings, keyed):
    """Count-level storage readback where per-row keys were not logged."""
    events = []
    for row in (findings or {}).get('rows') or []:
        if not isinstance(row, dict) or not isinstance(row.get('tenant'), str):
            continue
        for writer, acc, sto in (('ordinary', 'accepted', 'stored'), ('probe', 'probeAccepted', 'probeStored')):
            stored = row.get(sto) if type(row.get(sto)) is int else 0
            if writer in keyed:
                for key in sorted(keyed[writer].get(row['tenant'], ()))[:stored]:
                    events.append({'event': 'stored', 'tenant': row['tenant'], 'domain': key[0], 'key': key[1], 'writer': writer})
                continue
            for i in range(max(row.get(acc) or 0, 0) if type(row.get(acc)) is int else 0):
                events.append({'event': 'accepted', 'tenant': row['tenant'], 'domain': 'count', 'key': '#%d' % i, 'writer': writer})
            for i in range(stored):
                events.append({'event': 'stored', 'tenant': row['tenant'], 'domain': 'count', 'key': '#%d' % i, 'writer': writer})
    return events


def datastore_events(folder):
    events = []
    folder = Path(folder)
    before, after = _read(folder/'before.json'), _read(folder/'after.json')
    if isinstance(after, dict) and isinstance(after.get('pods'), dict):          # Kubernetes
        restarts = lambda doc: {(n, c): v.get('restartCount') for n, p in ((doc or {}).get('pods') or {}).items()
                                for c, v in (p.get('containers') or {}).items() if 'postgres' in n or 'postgres' in c}
        first, last = restarts(before), restarts(after)
        for (pod, name), count in last.items():
            ready = ((after['pods'][pod].get('containers') or {}).get(name) or {}).get('ready')
            events.append({'event': 'datastore', 'source': 'kubernetes-pod',
                           'healthy': ready is True and first.get((pod, name), count) == count})
    before, after = _read(folder/'before-cgroups.json'), _read(folder/'after-cgroups.json')
    if isinstance(after, dict) and isinstance(after.get('roles'), dict) and 'postgres' in after['roles']:  # Compose
        a, b = ((before or {}).get('roles') or {}).get('postgres') or {}, after['roles']['postgres']
        events.append({'event': 'datastore', 'source': 'compose-container',
                       'healthy': not b.get('unavailable') and (not a or a.get('id') == b.get('id'))})
    return events


def figures_from(folder):
    folder = Path(folder)
    figures, missing = {}, []
    summary = _read(folder/'k6-summary.json')
    metrics = summary.get('metrics') if isinstance(summary, dict) else None
    if isinstance(metrics, dict):
        for name in ('dropped_iterations', 'scenario_transport_failures', 'http_reqs'):
            value = metrics.get(name)
            value = value.get('values', value) if isinstance(value, dict) else {}
            figures[name] = value.get('count', 'UNMEASURED') if isinstance(value, dict) else 'UNMEASURED'
    else:
        missing.append('k6-summary.json')
    after = _read(folder/'after.json')
    if isinstance(after, dict) and isinstance(after.get('pods'), dict):
        figures['pendingPods'] = sum(p.get('phase') == 'Pending' for p in after['pods'].values())
    progress = _read(folder/'progress-after.json')
    if isinstance(progress, dict):
        rows = [r for service in (progress.get('allRows') or {}).values() for r in service.values() if isinstance(r, dict)]
        figures['failedCompletions'] = sum(r['failedCompletions'] for r in rows if type(r.get('failedCompletions')) is int)
    for name in ('oracle-findings.json', 'evaluator-catchup.json', 'runid'):
        if not (folder/name).is_file():
            missing.append(name)
    figures['missingFiles'] = missing
    return figures


def collect(folder):
    """Raw events from one retained load folder (Compose `<run>/load` or Kubernetes `packet/load`)."""
    folder = Path(folder)
    events, bad = k6_acks(folder)
    probe = _read(folder/'probe.json') or {}
    completed = probe.get('completedOutput') if isinstance(probe.get('completedOutput'), dict) else _read(
        folder/'clinical-witnesses-partial.json')
    viewers = {row.get('socket'): row.get('tenant') for row in probe.get('viewerBindings') or [] if isinstance(row, dict)}
    if isinstance(completed, dict) and isinstance(completed.get('witnesses'), list):
        events += probe_events(completed, viewers)
        events.append({'event': 'readback', 'what': 'output', 'writer': 'probe'})
        # Every frame a Kubernetes viewer received, by stored id: a probe row on another tenant's socket is a breach.
        owners = {w.get('storedId'): (w.get('tenant'), str(w.get('date'))) for w in completed['witnesses']
                  if isinstance(w, dict) and w.get('storedId')}
        for row in (probe.get('kubernetesFrames') or {}).get('rows') or []:
            for stored in row.get('ids') or [] if isinstance(row, dict) else []:
                if stored in owners and row.get('tenant') is not None:
                    events.append({'event': 'frame', 'tenant': owners[stored][0], 'viewerTenant': row['tenant'],
                                   'key': owners[stored][1], 'acceptedToFrameMs': None})
    catchup = _read(folder/'evaluator-catchup.json')
    if isinstance(catchup, dict) and isinstance(catchup.get('events'), list):
        events += catchup['events']                     # the live SQL observer already emits raw events
    keyed = {}
    for e in events:
        if isinstance(e, dict) and e.get('event') == 'accepted':
            keyed.setdefault(e.get('writer'), {}).setdefault(e.get('tenant'), set()).add((e.get('domain'), e.get('key')))
    if not any(e.get('event') == 'stored' for e in events if isinstance(e, dict)):
        findings = _read(folder/'oracle-findings.json')
        if isinstance(findings, dict) and isinstance(findings.get('rows'), list):
            events += count_events(findings, keyed)
            events += [{'event': 'readback', 'what': 'storage', 'writer': w} for w in ('ordinary', 'probe')]
            events.append({'event': 'datastore', 'source': 'storage-readback', 'healthy': True})
    events += datastore_events(folder)
    figures = figures_from(folder)
    figures['unparsedAckLines'] = bad
    figures['storageKeyBasis'] = 'row' if isinstance(catchup, dict) and catchup.get('events') else 'count'
    if isinstance(catchup, dict) and isinstance(catchup.get('figures'), dict):
        figures['observer'] = catchup['figures']
    return events, figures


def roster(folder):
    """Tenant ids: `roster.json` (ids only, kept after cleanup), else a private roster the fixture still holds."""
    for path in (Path(folder)/'roster.json', Path(folder).parent/'tenants.private.json', Path(folder)/'tenants.private.json'):
        value = _read(path)
        if isinstance(value, list):
            return [row if isinstance(row, str) else row['id'] for row in value
                    if isinstance(row, str) or isinstance(row, dict) and isinstance(row.get('id'), str)]
    return []


def judge(folder, ids=None, *, deadline_ms=DEADLINE_MS):
    events, figures = collect(folder)
    return assess(events, ids if ids is not None else roster(folder), deadline_ms=deadline_ms, figures=figures)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('load', type=Path)
    parser.add_argument('--events', action='store_true', help='print the raw events instead of the assessment')
    args = parser.parse_args()
    if args.events:
        for event in collect(args.load)[0]:
            print(json.dumps(event, sort_keys=True))
    else:
        print(json.dumps(judge(args.load), indent=1, sort_keys=True, default=dict))
