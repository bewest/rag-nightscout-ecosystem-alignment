#!/usr/bin/env python3
"""
generate_training_data.py — Batch synthetic data generation via parameter sweep.

Calls in-silico-bridge.js with systematically varied patient parameters to
produce diverse training data for cgmencode models.

Usage:
    python3 -m tools.cgmencode.generate_training_data [--n-patients 50] [--engine uva-padova] [--dry-run]

Patient parameters are sampled via Latin Hypercube to cover the physiological
space: ISF 15-80, CR 5-20, basal 0.3-3.0, weight 45-110, DIA 4-8.
"""

import subprocess
import sys
import json
import os
import argparse
import numpy as np
from pathlib import Path


# Physiological parameter ranges (clinically realistic)
PARAM_RANGES = {
    'isf':        (15, 80),    # mg/dL per unit insulin
    'cr':         (5, 20),     # grams carbs per unit insulin
    'basal_rate': (0.3, 3.0),  # units/hour
    'weight':     (45, 110),   # kg
    'dia':        (4, 8),      # hours
}


def latin_hypercube_sample(n: int, ranges: dict, seed: int = 42) -> list:
    """
    Generate n parameter sets using Latin Hypercube Sampling.
    Ensures uniform coverage of each parameter dimension.
    """
    rng = np.random.RandomState(seed)
    dim = len(ranges)
    keys = list(ranges.keys())

    # Create LHS grid: each dimension divided into n equal intervals
    samples = np.zeros((n, dim))
    for j in range(dim):
        perm = rng.permutation(n)
        for i in range(n):
            samples[i, j] = (perm[i] + rng.random()) / n

    # Scale to parameter ranges
    result = []
    for i in range(n):
        params = {}
        for j, key in enumerate(keys):
            lo, hi = ranges[key]
            params[key] = round(lo + samples[i, j] * (hi - lo), 2)
        result.append(params)

    return result


def run_bridge(params: dict, patient_id: str, engine: str, scenarios: str = 'all',
               modes: str = 'both', bridge_path: str = None, dry_run: bool = False) -> int:
    """Run in-silico-bridge.js with the given patient parameters. Returns vector count."""
    if bridge_path is None:
        bridge_path = os.path.join(os.path.dirname(__file__), '..', 'aid-autoresearch', 'in-silico-bridge.js')

    cmd = [
        'node', bridge_path,
        '--scenario', scenarios,
        '--mode', modes,
        '--engine', engine,
        '--isf', str(params['isf']),
        '--cr', str(params['cr']),
        '--basal-rate', str(params['basal_rate']),
        '--weight', str(params['weight']),
        '--dia', str(params['dia']),
        '--id-prefix', patient_id,
        '--vectors',
    ]

    if dry_run:
        print(f"  [DRY RUN] {' '.join(cmd)}")
        return 0

    result = subprocess.run(cmd, capture_output=True, text=True)
    # Parse vector count from stderr output like "Generated 35 conformance vectors..."
    for line in result.stderr.split('\n'):
        if 'Generated' in line and 'vectors' in line:
            try:
                return int(line.split('Generated')[1].split('conformance')[0].strip())
            except (ValueError, IndexError):
                pass

    if result.returncode != 0:
        print(f"  [ERROR] {patient_id}: {result.stderr.strip()[:200]}", file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(description='Generate diverse synthetic training data')
    parser.add_argument('--n-patients', type=int, default=50, help='Number of synthetic patients')
    parser.add_argument('--engine', default='cgmsim', choices=['cgmsim', 'uva-padova'],
                        help='Simulation engine')
    parser.add_argument('--scenarios', default='all', help='Scenario(s) to run')
    parser.add_argument('--modes', default='both', choices=['open-loop', 'oref0-loop', 'both'],
                        help='Controller mode(s)')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')
    parser.add_argument('--dry-run', action='store_true', help='Print commands without executing')
    parser.add_argument('--json', action='store_true', help='Output parameter table as JSON')
    args = parser.parse_args()

    print(f"=== Synthetic Training Data Generation ===")
    print(f"Engine: {args.engine}")
    print(f"Patients: {args.n_patients}")
    print(f"Scenarios: {args.scenarios}")
    print(f"Modes: {args.modes}")
    print()

    # Sample patient parameters
    patients = latin_hypercube_sample(args.n_patients, PARAM_RANGES, seed=args.seed)

    if args.json:
        print(json.dumps(patients, indent=2))
        return

    # Show parameter ranges being covered
    for key in PARAM_RANGES:
        values = [p[key] for p in patients]
        print(f"  {key:12s}: {min(values):6.1f} – {max(values):6.1f}  (range: {PARAM_RANGES[key]})")
    print()

    total_vectors = 0
    for i, params in enumerate(patients):
        patient_id = f"P{i:03d}"
        label = f"ISF={params['isf']:.0f} CR={params['cr']:.0f} W={params['weight']:.0f}kg DIA={params['dia']:.1f}h"
        print(f"[{i+1:3d}/{args.n_patients}] {patient_id}: {label}", end='')

        n_vectors = run_bridge(
            params, patient_id, args.engine,
            scenarios=args.scenarios, modes=args.modes,
            dry_run=args.dry_run,
        )
        total_vectors += n_vectors
        if not args.dry_run:
            print(f" → {n_vectors} vectors")
        else:
            print()

    print()
    print(f"Total vectors generated: {total_vectors}")
    print(f"Estimated training samples (12-step windows): ~{total_vectors * 10}")
    print(f"Output: conformance/in-silico/vectors/SIM-P*.json")


if __name__ == '__main__':
    main()
