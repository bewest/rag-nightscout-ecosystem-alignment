"""EXP-2523: Causal analysis of ISF confounding.

Tests whether the power-law ISF finding (β=0.9) is causal or
confounded by glucose state, IOB, time of day, etc.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from sklearn.linear_model import Ridge, LinearRegression

BETA = 0.9
PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2523_causal_isf.json'
STEPS_2H = 24  # 2 hours at 5-min intervals


def find_correction_events(df):
    """Extract correction events with context."""
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        raise ValueError("No bolus column found")

    # Map actual column names for time-of-day encoding
    hour_sin_col = 'time_sin' if 'time_sin' in df.columns else 'hour_sin'
    hour_cos_col = 'time_cos' if 'time_cos' in df.columns else 'hour_cos'

    events = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].fillna(0).values
        iob = pdf['iob'].fillna(0).values if 'iob' in pdf.columns else np.zeros(len(pdf))
        cob = pdf['cob'].fillna(0).values if 'cob' in pdf.columns else np.zeros(len(pdf))
        hour_sin = pdf[hour_sin_col].values if hour_sin_col in pdf.columns else np.zeros(len(pdf))
        hour_cos = pdf[hour_cos_col].values if hour_cos_col in pdf.columns else np.zeros(len(pdf))

        correction_idx = np.where(bolus > 0.3)[0]

        for idx in correction_idx:
            if idx + STEPS_2H >= len(glucose) or idx < 2:
                continue

            dose = bolus[idx]
            start_bg = glucose[idx]
            end_bg = glucose[idx + STEPS_2H]

            if np.isnan(start_bg) or np.isnan(end_bg) or start_bg < 100:
                continue

            # Check no other large bolus in window
            window_boluses = bolus[idx+1:idx+STEPS_2H]
            if np.any(window_boluses > 0.3):
                continue

            drop = start_bg - end_bg
            trend = glucose[idx] - glucose[idx-2]  # 10-min trend before bolus

            events.append({
                'patient_id': pid,
                'dose': float(dose),
                'start_bg': float(start_bg),
                'end_bg': float(end_bg),
                'drop': float(drop),
                'isf': float(drop / dose) if dose > 0 else 0,
                'iob': float(iob[idx]),
                'cob': float(cob[idx]),
                'hour_sin': float(hour_sin[idx]),
                'hour_cos': float(hour_cos[idx]),
                'trend': float(trend),
            })

    return pd.DataFrame(events)


def exp_2523a_confounding_direction(events):
    """Test the direction of confounding bias."""
    print("=== EXP-2523a: Confounding Direction Test ===\n")

    results = {}

    # 1. Dose vs starting glucose correlation
    r_dose_bg, p_dose_bg = stats.spearmanr(events['dose'], events['start_bg'])
    results['dose_vs_start_bg'] = {'spearman_r': round(r_dose_bg, 4), 'p': round(p_dose_bg, 6)}
    print(f"Dose vs Starting BG: r={r_dose_bg:.4f}, p={p_dose_bg:.2e}")

    # 2. Starting glucose vs ISF correlation
    r_bg_isf, p_bg_isf = stats.spearmanr(events['start_bg'], events['isf'])
    results['start_bg_vs_isf'] = {'spearman_r': round(r_bg_isf, 4), 'p': round(p_bg_isf, 6)}
    print(f"Starting BG vs ISF: r={r_bg_isf:.4f}, p={p_bg_isf:.2e}")

    # 3. Dose vs ISF (the power-law signal)
    r_dose_isf, p_dose_isf = stats.spearmanr(events['dose'], events['isf'])
    results['dose_vs_isf'] = {'spearman_r': round(r_dose_isf, 4), 'p': round(p_dose_isf, 6)}
    print(f"Dose vs ISF: r={r_dose_isf:.4f}, p={p_dose_isf:.2e}")

    # 4. Confounding direction inference
    if r_dose_bg > 0 and r_bg_isf > 0:
        direction = "INFLATES_LARGE_DOSE_ISF"
        note = "Confounding makes large-dose ISF appear HIGHER → our finding of LOWER ISF is CONSERVATIVE"
    elif r_dose_bg > 0 and r_bg_isf < 0:
        direction = "DEFLATES_LARGE_DOSE_ISF"
        note = "Confounding makes large-dose ISF appear LOWER → our finding might be INFLATED"
    else:
        direction = "COMPLEX"
        note = "Confounding direction is not straightforward"

    results['confounding_direction'] = direction
    results['interpretation'] = note
    print(f"\nConfounding direction: {direction}")
    print(f"Interpretation: {note}")

    # 5. Additional confounders
    for var in ['iob', 'cob', 'trend']:
        r, p = stats.spearmanr(events[var], events['isf'])
        results[f'{var}_vs_isf'] = {'spearman_r': round(r, 4), 'p': round(p, 6)}
        print(f"{var} vs ISF: r={r:.4f}, p={p:.2e}")

    return results


def exp_2523b_stratified_powerlaw(events):
    """Fit power-law β within glucose strata."""
    print("\n=== EXP-2523b: Stratified Power-Law Fit ===\n")

    bins = [(150, 200), (200, 250), (250, 300), (300, 500)]
    results = {}

    for lo, hi in bins:
        stratum = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]
        if len(stratum) < 20:
            print(f"  BG {lo}-{hi}: n={len(stratum)} (too few)")
            continue

        # Fit power-law: log(ISF) = log(ISF_base) - β × log(dose)
        valid = stratum[(stratum['dose'] > 0) & (stratum['isf'] > 0)]
        if len(valid) < 20:
            continue

        log_dose = np.log(valid['dose'].values)
        log_isf = np.log(valid['isf'].values)

        slope, intercept, r_value, p_value, std_err = stats.linregress(log_dose, log_isf)
        beta = -slope  # ISF = ISF_base × dose^(-β) → log(ISF) = const - β×log(dose)
        isf_base = np.exp(intercept)

        results[f'{lo}-{hi}'] = {
            'n': len(valid),
            'beta': round(beta, 3),
            'isf_base': round(isf_base, 1),
            'r_squared': round(r_value**2, 4),
            'p_value': round(p_value, 6),
            'std_err': round(std_err, 3),
        }
        print(f"  BG {lo}-{hi}: n={len(valid)}, β={beta:.3f} ± {std_err:.3f}, "
              f"ISF_base={isf_base:.1f}, R²={r_value**2:.4f}")

    # Check β consistency across strata
    betas = [v['beta'] for v in results.values()]
    if len(betas) >= 2:
        beta_cv = np.std(betas) / np.mean(betas) * 100 if np.mean(betas) > 0 else 999
        results['beta_consistency'] = {
            'mean': round(np.mean(betas), 3),
            'std': round(np.std(betas), 3),
            'cv_pct': round(beta_cv, 1),
            'consistent': beta_cv < 50,
        }
        print(f"\nβ across strata: mean={np.mean(betas):.3f} ± {np.std(betas):.3f}, "
              f"CV={beta_cv:.1f}% ({'CONSISTENT' if beta_cv < 50 else 'VARIES'})")

    return results


def exp_2523c_propensity_adjusted(events):
    """Propensity-adjusted ISF estimation."""
    print("\n=== EXP-2523c: Propensity-Adjusted ISF ===\n")

    # Confounders
    confounders = ['start_bg', 'iob', 'cob', 'hour_sin', 'hour_cos', 'trend']
    available = [c for c in confounders if c in events.columns]

    X_conf = events[available].values
    dose = events['dose'].values
    isf = events['isf'].values

    # Remove rows with NaN
    valid = ~(np.isnan(X_conf).any(axis=1) | np.isnan(dose) | np.isnan(isf) | (isf <= 0) | (dose <= 0))
    X_conf = X_conf[valid]
    dose = dose[valid]
    isf = isf[valid]

    # Step 1: Predict dose from confounders
    dose_model = LinearRegression()
    dose_model.fit(X_conf, dose)
    dose_predicted = dose_model.predict(X_conf)
    dose_residual = dose - dose_predicted
    r2_dose = 1 - np.sum((dose - dose_predicted)**2) / np.sum((dose - dose.mean())**2)

    print(f"Dose prediction R² = {r2_dose:.4f} (how much confounders explain dose choice)")

    # Step 2: Fit power-law on raw dose
    log_dose = np.log(dose)
    log_isf = np.log(isf)
    slope_raw, intercept_raw, r_raw, p_raw, se_raw = stats.linregress(log_dose, log_isf)
    beta_raw = -slope_raw

    # Step 3: Fit ISF vs dose_residual (deconfounded)
    # Can't take log of residuals (can be negative), so use linear on log(ISF)
    slope_deconf, intercept_deconf, r_deconf, p_deconf, se_deconf = stats.linregress(dose_residual, log_isf)

    # Step 4: Partial correlation approach
    # Regress log(ISF) on confounders, get residual
    isf_model = LinearRegression()
    isf_model.fit(X_conf, log_isf)
    log_isf_residual = log_isf - isf_model.predict(X_conf)

    # Fit residual ISF vs residual dose
    slope_partial, intercept_partial, r_partial, p_partial, se_partial = stats.linregress(
        dose_residual, log_isf_residual)

    results = {
        'dose_prediction_r2': round(r2_dose, 4),
        'raw_beta': round(beta_raw, 3),
        'raw_r': round(r_raw, 4),
        'raw_p': round(p_raw, 6),
        'deconfounded_slope': round(slope_deconf, 4),
        'deconfounded_r': round(r_deconf, 4),
        'deconfounded_p': round(p_deconf, 6),
        'partial_slope': round(slope_partial, 4),
        'partial_r': round(r_partial, 4),
        'partial_p': round(p_partial, 6),
        'n_events': int(len(dose)),
    }

    print(f"\nRaw power-law: β={beta_raw:.3f}, r={r_raw:.4f}, p={p_raw:.2e}")
    print(f"Deconfounded: slope={slope_deconf:.4f}, r={r_deconf:.4f}, p={p_deconf:.2e}")
    print(f"Partial correlation: slope={slope_partial:.4f}, r={r_partial:.4f}, p={p_partial:.2e}")

    # Interpretation
    if abs(r_partial) > 0.05 and p_partial < 0.05:
        results['interpretation'] = "Dose-ISF relationship SURVIVES deconfounding → likely CAUSAL"
    else:
        results['interpretation'] = "Dose-ISF relationship DOES NOT survive deconfounding → may be ARTIFACT"

    print(f"\n{results['interpretation']}")

    return results


def exp_2523d_natural_experiment(events):
    """Natural experiment: same patient, similar glucose, different dose."""
    print("\n=== EXP-2523d: Natural Experiment (Matched Pairs) ===\n")

    BG_TOLERANCE = 20  # mg/dL
    results = {'by_patient': {}, 'population': []}
    all_pairs = []

    for pid in events['patient_id'].unique():
        pt_events = events[events['patient_id'] == pid].copy()
        if len(pt_events) < 20:
            continue

        # Find pairs with similar starting BG but different doses
        pairs_found = []
        used = set()

        pt_sorted = pt_events.sort_values('start_bg').reset_index(drop=True)

        for i in range(len(pt_sorted)):
            if i in used:
                continue
            for j in range(i+1, len(pt_sorted)):
                if j in used:
                    continue
                bg_diff = abs(pt_sorted.iloc[i]['start_bg'] - pt_sorted.iloc[j]['start_bg'])
                dose_diff = abs(pt_sorted.iloc[i]['dose'] - pt_sorted.iloc[j]['dose'])

                if bg_diff <= BG_TOLERANCE and dose_diff > 0.5:
                    small = pt_sorted.iloc[i] if pt_sorted.iloc[i]['dose'] < pt_sorted.iloc[j]['dose'] else pt_sorted.iloc[j]
                    large = pt_sorted.iloc[j] if pt_sorted.iloc[i]['dose'] < pt_sorted.iloc[j]['dose'] else pt_sorted.iloc[i]

                    pairs_found.append({
                        'small_dose': float(small['dose']),
                        'large_dose': float(large['dose']),
                        'small_isf': float(small['isf']),
                        'large_isf': float(large['isf']),
                        'bg_diff': float(bg_diff),
                        'mean_bg': float((small['start_bg'] + large['start_bg']) / 2),
                    })
                    used.add(i)
                    used.add(j)
                    break

        if len(pairs_found) >= 3:
            # Compare ISF: do larger doses have lower ISF?
            n_saturation = sum(1 for p in pairs_found if p['large_isf'] < p['small_isf'])
            pct_saturation = n_saturation / len(pairs_found) * 100

            results['by_patient'][pid] = {
                'n_pairs': len(pairs_found),
                'pct_saturation': round(pct_saturation, 1),
            }
            all_pairs.extend(pairs_found)
            print(f"  {pid}: {len(pairs_found)} pairs, {pct_saturation:.0f}% show saturation")

    if all_pairs:
        n_sat = sum(1 for p in all_pairs if p['large_isf'] < p['small_isf'])
        total = len(all_pairs)
        pct = n_sat / total * 100

        # Binomial test: is saturation significantly > 50%?
        binom_p = stats.binom_test(n_sat, total, 0.5) if hasattr(stats, 'binom_test') else stats.binomtest(n_sat, total, 0.5).pvalue

        results['population'] = {
            'total_pairs': total,
            'n_saturation': n_sat,
            'pct_saturation': round(pct, 1),
            'binomial_p': round(float(binom_p), 6),
            'significant': pct > 50 and binom_p < 0.05,
        }

        # Mean ISF ratio
        ratios = [p['large_isf'] / p['small_isf'] for p in all_pairs if p['small_isf'] > 0]
        if ratios:
            results['population']['mean_isf_ratio'] = round(np.mean(ratios), 3)
            results['population']['median_isf_ratio'] = round(np.median(ratios), 3)

        print(f"\nPopulation: {n_sat}/{total} ({pct:.1f}%) pairs show saturation")
        print(f"Binomial test p={binom_p:.4f} ({'SIGNIFICANT' if binom_p < 0.05 else 'not significant'})")
        if ratios:
            print(f"Mean ISF ratio (large/small dose): {np.mean(ratios):.3f}")

    return results


def run_experiment():
    """Run all EXP-2523 sub-experiments."""
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nExtracting correction events...")
    events = find_correction_events(df)
    print(f"Found {len(events)} correction events from {events['patient_id'].nunique()} patients")
    print(f"Dose range: {events['dose'].min():.1f} - {events['dose'].max():.1f} U")
    print(f"BG range: {events['start_bg'].min():.0f} - {events['start_bg'].max():.0f} mg/dL")

    results = {
        'experiment': 'EXP-2523',
        'title': 'Causal analysis of ISF confounding',
        'n_events': int(len(events)),
        'n_patients': int(events['patient_id'].nunique()),
    }

    results['exp_2523a'] = exp_2523a_confounding_direction(events)
    results['exp_2523b'] = exp_2523b_stratified_powerlaw(events)
    results['exp_2523c'] = exp_2523c_propensity_adjusted(events)
    results['exp_2523d'] = exp_2523d_natural_experiment(events)

    # Overall conclusion
    conclusions = []
    if 'confounding_direction' in results['exp_2523a']:
        conclusions.append(f"Confounding direction: {results['exp_2523a']['confounding_direction']}")
    if 'beta_consistency' in results['exp_2523b']:
        conclusions.append(f"β consistent across glucose strata: {results['exp_2523b']['beta_consistency'].get('consistent', 'unknown')}")
    if 'interpretation' in results['exp_2523c']:
        conclusions.append(results['exp_2523c']['interpretation'])
    if 'population' in results['exp_2523d'] and isinstance(results['exp_2523d']['population'], dict):
        pop = results['exp_2523d']['population']
        conclusions.append(f"Natural experiment: {pop.get('pct_saturation', 0):.1f}% pairs show saturation (p={pop.get('binomial_p', 1):.4f})")

    results['conclusions'] = conclusions
    print("\n=== CONCLUSIONS ===")
    for c in conclusions:
        print(f"  • {c}")

    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results

if __name__ == '__main__':
    run_experiment()
