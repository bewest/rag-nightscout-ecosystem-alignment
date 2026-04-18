"""EXP-2524: DIA Paradox Mechanism Investigation.

Investigates why glucose effects persist 5-20h while IOB decays in 3-5h.
Tests power-law tail extension, counter-regulatory rebound, and loop compensation.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

BETA = 0.9
PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2524_dia_paradox.json'


def find_isolated_corrections(df, min_bolus=0.5, isolation_window=36):
    """Find correction boluses with no other bolus within isolation_window steps."""
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        raise ValueError("No bolus column found")
    
    events = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].values
        iob = pdf['iob'].fillna(0).values if 'iob' in pdf.columns else np.zeros(len(pdf))
        net_flux = pdf['net_flux'].fillna(0).values if 'net_flux' in pdf.columns else np.zeros(len(pdf))
        
        correction_idx = np.where(bolus > min_bolus)[0]
        
        for idx in correction_idx:
            # Need 12h (144 steps) of data after bolus
            if idx + 144 >= len(glucose) or idx < isolation_window:
                continue
            
            # Check isolation: no other bolus > 0.3U in ±isolation_window
            window_before = bolus[max(0, idx-isolation_window):idx]
            window_after = bolus[idx+1:idx+isolation_window]
            
            if np.any(window_before > 0.3) or np.any(window_after > 0.3):
                continue
            
            start_bg = glucose[idx]
            if np.isnan(start_bg) or start_bg < 130:
                continue
            
            # Track glucose at various horizons
            horizons = {
                'h1': 12, 'h2': 24, 'h3': 36, 'h4': 48,
                'h5': 60, 'h6': 72, 'h8': 96, 'h10': 120, 'h12': 144
            }
            
            glucose_at = {}
            iob_at = {}
            flux_at = {}
            all_valid = True
            
            for name, steps in horizons.items():
                if idx + steps < len(glucose) and not np.isnan(glucose[idx + steps]):
                    glucose_at[name] = float(glucose[idx + steps])
                    iob_at[name] = float(iob[idx + steps]) if idx + steps < len(iob) else 0
                    flux_at[name] = float(net_flux[idx + steps]) if idx + steps < len(net_flux) else 0
                else:
                    all_valid = False
                    break
            
            if not all_valid:
                continue
            
            # Find nadir
            glucose_window = glucose[idx:idx+144]
            valid_window = glucose_window[~np.isnan(glucose_window)]
            nadir = float(np.min(valid_window)) if len(valid_window) > 0 else start_bg
            nadir_time = float(np.argmin(valid_window) * 5 / 60) if len(valid_window) > 0 else 0  # hours
            
            events.append({
                'patient_id': pid,
                'dose': float(bolus[idx]),
                'start_bg': float(start_bg),
                'nadir': nadir,
                'nadir_time_h': round(nadir_time, 1),
                'iob_at_bolus': float(iob[idx]),
                'glucose_at': glucose_at,
                'iob_at': iob_at,
                'flux_at': flux_at,
            })
    
    return events


def exp_2524a_response_curves(events):
    """Measure glucose response curves at multiple horizons."""
    print("=== EXP-2524a: Response Curve Duration ===\n")
    
    horizons = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h8', 'h10', 'h12']
    hours = [1, 2, 3, 4, 5, 6, 8, 10, 12]
    
    # Per-horizon: mean glucose change from baseline
    drops_by_horizon = {h: [] for h in horizons}
    drops_per_unit = {h: [] for h in horizons}
    
    for event in events:
        start = event['start_bg']
        dose = event['dose']
        for h in horizons:
            if h in event['glucose_at']:
                drop = start - event['glucose_at'][h]
                drops_by_horizon[h].append(drop)
                drops_per_unit[h].append(drop / dose)
    
    results = {}
    print(f"{'Horizon':>8s} | {'Mean Drop':>10s} | {'Drop/Unit':>10s} | {'Pct of Max':>10s} | {'n':>5s}")
    print("-" * 55)
    
    max_drop = 0
    for h, hr in zip(horizons, hours):
        if drops_by_horizon[h]:
            mean_drop = np.mean(drops_by_horizon[h])
            mean_per_unit = np.mean(drops_per_unit[h])
            max_drop = max(max_drop, abs(mean_drop))
            results[h] = {
                'hours': hr,
                'mean_drop': round(mean_drop, 1),
                'mean_drop_per_unit': round(mean_per_unit, 1),
                'std_drop': round(np.std(drops_by_horizon[h]), 1),
                'n': len(drops_by_horizon[h]),
            }
    
    # Compute pct of max
    for h in horizons:
        if h in results:
            pct = abs(results[h]['mean_drop']) / max_drop * 100 if max_drop > 0 else 0
            results[h]['pct_of_max'] = round(pct, 1)
            print(f"{results[h]['hours']:>8d}h | {results[h]['mean_drop']:>+10.1f} | "
                  f"{results[h]['mean_drop_per_unit']:>+10.1f} | {pct:>10.1f}% | {results[h]['n']:>5d}")
    
    # Find when drop crosses zero (glucose returns to baseline)
    for h in horizons:
        if h in results and results[h]['mean_drop'] < 0:
            results['first_positive_horizon'] = h
            results['effect_crosses_zero_at_hours'] = results[h]['hours']
            print(f"\nEffect crosses zero (glucose returns above baseline) at {results[h]['hours']}h")
            break
    else:
        # Find when effect drops to <10% of max
        for h in horizons:
            if h in results and results[h].get('pct_of_max', 100) < 10:
                results['effect_negligible_at_hours'] = results[h]['hours']
                print(f"\nEffect negligible (<10% of max) at {results[h]['hours']}h")
                break
    
    return results


def exp_2524b_powerlaw_tail(events):
    """Test whether power-law ISF explains the extended tail."""
    print("\n=== EXP-2524b: Power-Law Tail Extension ===\n")
    
    # Theory: with β=0.9, effective DIA = nominal_DIA / (1-β)
    nominal_dia_hours = 5.0
    effective_dia_theory = nominal_dia_hours / (1 - BETA)
    
    print(f"Nominal DIA: {nominal_dia_hours}h")
    print(f"Theoretical effective DIA (power-law): {effective_dia_theory:.0f}h")
    print(f"Extension factor: {1/(1-BETA):.1f}×")
    
    # Model prediction: glucose_drop(t) ∝ dose^(1-β) × (1 - exp(-(1-β)×t/τ))
    # where τ = DIA / ln(2) ≈ 7.2h for DIA=5h
    tau = nominal_dia_hours / np.log(2)
    effective_tau = tau / (1 - BETA)
    
    horizons = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h8', 'h10', 'h12']
    hours = [1, 2, 3, 4, 5, 6, 8, 10, 12]
    
    # Compute empirical response curve (normalized)
    empirical = {}
    for h, hr in zip(horizons, hours):
        drops = [e['start_bg'] - e['glucose_at'][h] for e in events if h in e['glucose_at']]
        if drops:
            empirical[hr] = np.mean(drops)
    
    if not empirical:
        return {'error': 'No empirical data'}
    
    max_empirical = max(abs(v) for v in empirical.values())
    
    # Compare with linear and power-law decay models
    results = {'models': {}}
    
    for model_name, decay_factor in [('linear_dia', 1.0), ('powerlaw_dia', 1.0/(1-BETA))]:
        model_tau = tau * decay_factor if model_name == 'powerlaw_dia' else tau
        
        # Model: normalized response = 1 - exp(-t/model_tau)
        model_response = {}
        for hr in hours:
            model_response[hr] = 1.0 - np.exp(-hr / model_tau)
        
        # Scale model to match empirical max
        max_model = max(model_response.values())
        scale = max_empirical / max_model if max_model > 0 else 1.0
        
        # Compute MSE between model and empirical
        mse = 0
        n = 0
        for hr in hours:
            if hr in empirical:
                model_scaled = model_response[hr] * scale
                mse += (empirical[hr] - model_scaled) ** 2
                n += 1
        mse /= n if n > 0 else 1
        
        results['models'][model_name] = {
            'tau': round(model_tau, 1),
            'effective_dia': round(model_tau * np.log(2), 1),
            'mse': round(mse, 1),
            'scale': round(scale, 1),
        }
        print(f"\n{model_name}: τ={model_tau:.1f}h, effective DIA={model_tau*np.log(2):.1f}h, MSE={mse:.1f}")
    
    # Which model fits better?
    linear_mse = results['models']['linear_dia']['mse']
    powerlaw_mse = results['models']['powerlaw_dia']['mse']
    
    results['linear_mse'] = linear_mse
    results['powerlaw_mse'] = powerlaw_mse
    results['powerlaw_wins'] = powerlaw_mse < linear_mse
    results['effective_dia_theory_hours'] = round(effective_dia_theory, 1)
    results['extension_factor'] = round(1/(1-BETA), 1)
    
    print(f"\nLinear DIA MSE: {linear_mse:.1f}")
    print(f"Power-law DIA MSE: {powerlaw_mse:.1f}")
    print(f"Power-law wins: {powerlaw_mse < linear_mse}")
    
    return results


def exp_2524c_counter_regulatory(events):
    """Detect counter-regulatory rebounds after corrections."""
    print("\n=== EXP-2524c: Counter-Regulatory Rebound Detection ===\n")
    
    # A rebound = glucose goes ABOVE starting level within 4-12h after correction
    rebounds = []
    no_rebounds = []
    
    for event in events:
        start = event['start_bg']
        nadir = event['nadir']
        
        # Check if glucose exceeds starting level at any horizon 4-12h out
        rebound_detected = False
        rebound_magnitude = 0
        rebound_time = None
        
        for h in ['h4', 'h5', 'h6', 'h8', 'h10', 'h12']:
            if h in event['glucose_at']:
                overshoot = event['glucose_at'][h] - start
                if overshoot > 10:  # At least 10 mg/dL above starting
                    if not rebound_detected or overshoot > rebound_magnitude:
                        rebound_magnitude = overshoot
                        rebound_time = h
                    rebound_detected = True
        
        event_data = {
            'dose': event['dose'],
            'start_bg': start,
            'nadir': nadir,
            'drop_to_nadir': start - nadir,
            'went_below_70': nadir < 70,
            'went_below_54': nadir < 54,
            'nadir_time_h': event['nadir_time_h'],
        }
        
        if rebound_detected:
            event_data['rebound_magnitude'] = round(rebound_magnitude, 1)
            event_data['rebound_time'] = rebound_time
            rebounds.append(event_data)
        else:
            no_rebounds.append(event_data)
    
    n_total = len(rebounds) + len(no_rebounds)
    pct_rebound = len(rebounds) / n_total * 100 if n_total > 0 else 0
    
    results = {
        'n_total': n_total,
        'n_rebounds': len(rebounds),
        'pct_rebound': round(pct_rebound, 1),
    }
    
    print(f"Total corrections: {n_total}")
    print(f"Rebounds detected: {len(rebounds)} ({pct_rebound:.1f}%)")
    
    if rebounds:
        mean_magnitude = np.mean([r['rebound_magnitude'] for r in rebounds])
        mean_nadir_rebound = np.mean([r['nadir'] for r in rebounds])
        mean_nadir_no = np.mean([r['nadir'] for r in no_rebounds]) if no_rebounds else 0
        
        # Do rebounds correlate with how low glucose went?
        all_events = rebounds + no_rebounds
        nadirs = [e['nadir'] for e in all_events]
        is_rebound = [1 if e in rebounds else 0 for e in all_events]
        
        # Correlation: lower nadir → more rebound?
        r_nadir, p_nadir = stats.pointbiserialr(is_rebound, nadirs)
        
        # Below 70 → rebound?
        below_70_rebound = sum(1 for r in rebounds if r['went_below_70'])
        below_70_no = sum(1 for r in no_rebounds if r['went_below_70'])
        below_70_pct_rebound = below_70_rebound / len(rebounds) * 100 if rebounds else 0
        below_70_pct_no = below_70_no / len(no_rebounds) * 100 if no_rebounds else 0
        
        results.update({
            'mean_rebound_magnitude': round(mean_magnitude, 1),
            'mean_nadir_rebounds': round(mean_nadir_rebound, 1),
            'mean_nadir_no_rebounds': round(mean_nadir_no, 1),
            'nadir_rebound_correlation': round(r_nadir, 4),
            'nadir_rebound_p': round(p_nadir, 6),
            'pct_below_70_in_rebounds': round(below_70_pct_rebound, 1),
            'pct_below_70_in_no_rebounds': round(below_70_pct_no, 1),
        })
        
        print(f"Mean rebound magnitude: +{mean_magnitude:.1f} mg/dL above starting")
        print(f"Mean nadir (rebounds): {mean_nadir_rebound:.0f} mg/dL")
        print(f"Mean nadir (no rebounds): {mean_nadir_no:.0f} mg/dL")
        print(f"Nadir-rebound correlation: r={r_nadir:.4f}, p={p_nadir:.4f}")
        print(f"Below 70 in rebounds: {below_70_pct_rebound:.1f}%")
        print(f"Below 70 in no-rebounds: {below_70_pct_no:.1f}%")
    
    return results


def exp_2524d_loop_compensation(events):
    """Test whether AID loop compensation extends the effect window."""
    print("\n=== EXP-2524d: Loop Compensation Window ===\n")
    
    horizons = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h8', 'h10', 'h12']
    
    # Split by IOB at bolus time (high vs low)
    iob_values = [e['iob_at_bolus'] for e in events]
    median_iob = np.median(iob_values) if iob_values else 0
    
    high_iob = [e for e in events if e['iob_at_bolus'] > median_iob]
    low_iob = [e for e in events if e['iob_at_bolus'] <= median_iob]
    
    results = {'median_iob_split': round(median_iob, 2)}
    
    for group_name, group in [('high_iob', high_iob), ('low_iob', low_iob)]:
        group_results = {}
        for h in horizons:
            drops = [e['start_bg'] - e['glucose_at'][h] for e in group if h in e['glucose_at']]
            if drops:
                group_results[h] = round(np.mean(drops), 1)
        results[group_name] = group_results
        
        print(f"\n{group_name} (n={len(group)}):")
        for h in horizons:
            if h in group_results:
                print(f"  {h}: {group_results[h]:+.1f} mg/dL")
    
    # Compare effect duration
    if results.get('high_iob') and results.get('low_iob'):
        # Find where each group's effect decays to <25% of max
        for group_name in ['high_iob', 'low_iob']:
            vals = results[group_name]
            if vals:
                max_effect = max(abs(v) for v in vals.values())
                for h in horizons:
                    if h in vals and abs(vals[h]) < 0.25 * max_effect:
                        results[f'{group_name}_decay_25pct'] = h
                        break
    
    # Track net_flux after bolus
    print("\nNet flux trajectory after correction:")
    for h in horizons:
        fluxes = [e['flux_at'][h] for e in events if h in e.get('flux_at', {})]
        if fluxes:
            mean_flux = np.mean(fluxes)
            print(f"  {h}: net_flux = {mean_flux:+.4f}")
            results[f'flux_{h}'] = round(mean_flux, 4)
    
    return results


def run_experiment():
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")
    
    print("\nFinding isolated correction events...")
    events = find_isolated_corrections(df)
    print(f"Found {len(events)} isolated corrections")
    
    if len(events) < 10:
        print("Too few isolated events. Relaxing isolation window...")
        events = find_isolated_corrections(df, min_bolus=0.3, isolation_window=18)
        print(f"Found {len(events)} events with relaxed criteria")
    
    results = {
        'experiment': 'EXP-2524',
        'title': 'DIA Paradox Mechanism Investigation',
        'n_events': len(events),
        'n_patients': len(set(e['patient_id'] for e in events)),
    }
    
    results['exp_2524a'] = exp_2524a_response_curves(events)
    results['exp_2524b'] = exp_2524b_powerlaw_tail(events)
    results['exp_2524c'] = exp_2524c_counter_regulatory(events)
    results['exp_2524d'] = exp_2524d_loop_compensation(events)
    
    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")
    
    return results

if __name__ == '__main__':
    run_experiment()
