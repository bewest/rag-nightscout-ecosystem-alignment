#!/usr/bin/env python3
"""Audit repeated bounded matrix pins; unknown semantic changes are failures.

Run with --pins DIR containing {v1509,dev,pr8898}-run{1,2}.json and
control-no-write.json. Full pins remain local; --out retains synthetic aggregates.
Historical pins inform classification, never substitute for fresh repeats.
"""
import argparse
import collections
import copy
import hashlib
import json
import re
from pathlib import Path

from classify_compat import classify, diff_fields
from wcdiff import diff

ROOT = Path(__file__).resolve().parents[3]
HIST = ROOT / 'tools/qc/results/write-contract-matrix/compat-16.0.0-refresh-2026-11-01/run1'
SET_ASIDE = {f'{c} ws idread-fail' for c in
             ('entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity')}


def load(path):
    value = json.loads(path.read_text())
    # The test-name adaptation preceded the existing 60-character error
    # truncation. Remove only its exact random database token, never an error
    # category, collection, status, count, or write outcome.
    for cell in value.get('cells', {}).values():
        for field, text in cell.items():
            if isinstance(text, str):
                cell[field] = re.sub(r'wcm_test_[0-9a-f]{8}', 'wcm_test_*', text)
    return value


def delta(a, b, exclude=()):
    semantic, racy = diff(a, b)
    semantic = [(key, fields) for key, fields in semantic if key not in exclude]
    groups = collections.Counter(classify(key, a['cells'][key], b['cells'][key])[0]
                                 for key, _ in semantic
                                 if key in a['cells'] and key in b['cells'])
    return {'semantic': len(semantic), 'cache_wire_only': len(racy),
            'groups': dict(sorted(groups.items())),
            'cells': {key: fields for key, fields in semantic}}


def semantic_equal(a, b):
    return set(a['cells']) == set(b['cells']) and not diff(a, b)[0]


def audit(directory):
    pins = {key: [load(directory / f'{key}-run{i}.json') for i in (1, 2)]
            for key in ('v1509', 'dev', 'pr8898')}
    result = {'grade': 'reproduced', 'scope': '--batch --no-idf --no-idfmt',
              'excluded_semantic_fields': ['cache', 'wire'],
              'normalization': 'Exact wcm_test_<8 hex> random database token only; other error text retained',
              'pass_scope': 'fresh dev/candidate equality, all fresh repeatability and controls; historical projection is diagnostic only',
              'old_release_incomparable_cells': sorted(SET_ASIDE), 'endpoints': {}}
    for key, pair in pins.items():
        a, b = pair
        result['endpoints'][key] = {
            'head': a['head'], 'repeat_head': b['head'], 'node': a['node'], 'mongod': a['mongod'],
            'cells_per_run': [len(p['cells']) for p in pair],
            'dirty_lib': [bool(p['dirty_lib']) for p in pair],
            'invalid_per_run': [sum('INVALID' in c.get('st', '') for c in p['cells'].values()) for p in pair],
            'repeat': delta(a, b),
            'pin_sha256': [hashlib.sha256((directory / f'{key}-run{i}.json').read_bytes()).hexdigest() for i in (1, 2)]}
    a, d, b = (pins[key][0] for key in ('v1509', 'dev', 'pr8898'))
    result['comparisons'] = {
        'release_to_dev': delta(a, d, SET_ASIDE),
        'release_to_candidate': delta(a, b, SET_ASIDE),
        'dev_to_candidate': delta(d, b)}
    result['historical_reference_residuals'] = {}
    for key, old_file in [('v1509', 'v1509-c6a0d8ed.json'), ('dev', 'dev-497d08c9.json')]:
        current = pins[key][0]
        historical = load(HIST / old_file)
        projected = dict(historical, cells={k: historical['cells'][k] for k in current['cells']})
        result['historical_reference_residuals'][key] = delta(projected, current, SET_ASIDE)
    historical_a = load(HIST / 'v1509-c6a0d8ed.json')
    historical_b = load(HIST / 'dev-497d08c9.json')
    historical_a['cells'] = {k: historical_a['cells'][k] for k in a['cells']}
    historical_b['cells'] = {k: historical_b['cells'][k] for k in b['cells']}
    prior_delta = delta(historical_a, historical_b, SET_ASIDE)
    fresh_delta = result['comparisons']['release_to_candidate']
    result['historical_classification_shape'] = {
        'same_changed_cell_set': set(prior_delta['cells']) == set(fresh_delta['cells']),
        'same_group_per_changed_cell': all(
            classify(k, historical_a['cells'][k], historical_b['cells'][k])[0]
            == classify(k, a['cells'][k], b['cells'][k])[0]
            for k in fresh_delta['cells']),
        'meaning': 'Descriptive classification only; old full corpus is not a fresh bounded repeat'}
    # Authored comparator control: an unexpected field on a successful create
    # must fail even if the broad behavior classifier calls it "other".
    changed = copy.deepcopy(b)
    changed['cells']['treatments v3 create']['unexpected'] = 'authored-control'
    comparator_red = not semantic_equal(b, changed)
    # Authored application control: private source omits v3 insertOne while
    # returning its identifier. Liveness remains valid; persisted state must fail.
    control = load(directory / 'control-no-write.json')
    good = b['cells']['treatments v3 create']
    bad = control['cells']['treatments v3 create']
    control_fields = diff_fields(good, bad)
    persistence_red = ('store' in control_fields and good['store'].startswith('n=1 ')
                       and bad['store'] == 'none' and 'INVALID' not in bad['st'])
    changed_error = copy.deepcopy(b)
    changed_error['cells']['treatments v3 create']['st'] = '500 authored-error-control'
    missing = copy.deepcopy(b)
    missing['cells'].pop('treatments v3 create')
    comparator_red = comparator_red and not semantic_equal(b, changed_error) and not semantic_equal(b, missing)
    restored = load(directory / 'control-restored.json')['cells']['treatments v3 create']
    restored_green = not diff_fields(good, restored)
    result['controls'] = {'unexpected_field_rejected': comparator_red,
                          'restored_source_green': restored_green,
                          'no_write_rejected': persistence_red,
                          'no_write_changed_fields': control_fields,
                          'no_write_good_store': good['store'], 'no_write_bad_store': bad['store'],
                          'no_write_reply': bad['st']}
    failures = []
    for key, info in result['endpoints'].items():
        if info['head'] != info['repeat_head']: failures.append(f'{key}: endpoint changed between runs')
        if info['cells_per_run'] != [768, 768]: failures.append(f'{key}: bounded corpus is incomplete')
        if info['repeat']['semantic']: failures.append(f'{key}: nonrepeatable semantic cells')
        if any(info['invalid_per_run']): failures.append(f'{key}: invalid liveness')
        if any(info['dirty_lib']): failures.append(f'{key}: dirty library source')
    if result['comparisons']['dev_to_candidate']['semantic']:
        failures.append('dev-to-candidate: unexpected semantic differences')
    if not comparator_red or not persistence_red or not restored_green: failures.append('control did not detect its authored break')
    result['failures'] = failures
    result['passed'] = not failures
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pins', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--detail', type=Path, help='Optional local per-cell diagnostics')
    args = parser.parse_args()
    result = audit(args.pins)
    if args.detail:
        args.detail.write_text(json.dumps(result, indent=2) + '\n')
    # Public output is aggregate only. The exact local cell maps remain
    # reproducible from the pins; hashes detect a changed diagnostic set.
    for section in (result['comparisons'], result['historical_reference_residuals']):
        for entry in section.values():
            entry['changed_cells_sha256'] = hashlib.sha256(
                json.dumps(entry.pop('cells'), sort_keys=True).encode()).hexdigest()
    for entry in result['endpoints'].values():
        entry['repeat'].pop('cells')
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'failures': result['failures'],
                      'comparisons': {k: v['semantic'] for k, v in result['comparisons'].items()},
                      'controls': result['controls']}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
