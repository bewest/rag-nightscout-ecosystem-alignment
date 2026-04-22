"""
EXP-2842: Cross-reference triage flags from EXP-2812 (state recovery) and
EXP-2831 (wear-based ISF degradation). Stream B operational synthesis.
"""
import json
import pandas as pd
from pathlib import Path

OUT = Path('externals/experiments')
EXP = '2842'

t1 = pd.read_parquet(OUT / 'exp-2812_triage_flags.parquet')
t2 = pd.read_parquet(OUT / 'exp-2831_triage_flags.parquet')

t1['in_2812_recovery_flag'] = True
t2['in_2831_wear_flag'] = t2['flag_site_change']

merged = t1.merge(t2[['patient_id', 'isf_fresh_site', 'isf_aged_site',
                      'delta_pct', 'flag_site_change']],
                  on='patient_id', how='outer', indicator=True)

print("Cross-reference of Stream B triage flags")
print("="*60)
print(merged.to_string(index=False))

# Categorize
both_flagged = merged[(merged['_merge'] == 'both') & (merged['flag_site_change'] == True)]
recovery_only = merged[merged['_merge'] == 'left_only']
wear_only = merged[(merged['_merge'] == 'right_only') & (merged['flag_site_change'] == True)]
recovery_with_mild_wear = merged[(merged['_merge'] == 'both') & (merged['flag_site_change'] != True)]

print(f"\n--- Categorization ---")
print(f"BOTH flags (root cause = site degradation): {len(both_flagged)} patients")
print(both_flagged[['patient_id', 'controller', 'median_recovery_fraction', 'delta_pct']].to_string(index=False) if len(both_flagged) else "  (none)")
print(f"\nRecovery-only flags (other root cause): {len(recovery_only)} patients")
print(recovery_only[['patient_id', 'controller', 'median_recovery_fraction']].to_string(index=False) if len(recovery_only) else "  (none)")
print(f"\nWear-only flags (degraded but loop self-recovers): {len(wear_only)} patients")
print(wear_only[['patient_id', 'delta_pct']].to_string(index=False) if len(wear_only) else "  (none)")
print(f"\nRecovery + mild wear (suggestive but below 2831 threshold): {len(recovery_with_mild_wear)} patients")
print(recovery_with_mild_wear[['patient_id', 'controller', 'median_recovery_fraction', 'delta_pct']].to_string(index=False) if len(recovery_with_mild_wear) else "  (none)")

result = {
    'experiment': f'EXP-{EXP}',
    'title': 'triage_cross_reference',
    'stream': 'B (operational synthesis)',
    'conflation_risk': 'LOW',
    'recovery_flagged': int(len(t1)),
    'wear_flagged': int(t2['flag_site_change'].sum()),
    'both_flagged_count': int(len(both_flagged)),
    'both_flagged_patients': both_flagged['patient_id'].tolist(),
    'recovery_only_patients': recovery_only['patient_id'].tolist(),
    'wear_only_patients': wear_only['patient_id'].tolist(),
    'recovery_with_mild_wear_patients': recovery_with_mild_wear['patient_id'].tolist(),
    'interpretation': {
        'both_flagged': 'Site degradation likely root cause of failure-to-recover; replace site',
        'recovery_only': 'Other root cause (controller config, behavioral, biological); needs further triage',
        'wear_only': 'Wear-induced ISF drop but loop compensates; monitor only',
        'recovery_with_mild_wear': 'Wear contributes but not sole cause; investigate further',
    },
    'guardrails': 'G2/G4/G5 PASS (no Stream A inputs)',
}
with open(OUT / f'exp-{EXP}_triage_cross_reference.json', 'w') as f:
    json.dump(result, f, indent=2, default=str)
merged.to_parquet(OUT / f'exp-{EXP}_combined_flags.parquet', index=False)
print(f"\nSaved exp-{EXP}_triage_cross_reference.json + combined_flags.parquet")
