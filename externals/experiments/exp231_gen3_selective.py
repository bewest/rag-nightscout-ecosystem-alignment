"""EXP-231: Gen-3 (semantic groups) with selective masking."""
import sys, json, time, os, numpy as np, torch
sys.path.insert(0, '.')
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
from tools.cgmencode.experiment_lib import (
    create_model, train_forecast, forecast_mse, persistence_mse, set_seed,
    mask_future_channels, get_device, batch_to_device
)
from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS, NORMALIZATION_SCALES
from torch.utils.data import DataLoader

SCALE = NORMALIZATION_SCALES.get('glucose', 400.0)

def compute_mae(model, val_ds, batch_size=64):
    """Compute true MAE in mg/dL."""
    device = get_device()
    model.eval()
    total_ae, total_n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_input = x.clone()
        mask_future_channels(x_input, half)
        with torch.no_grad():
            pred = model(x_input, causal=True)
        if isinstance(pred, dict):
            pred = pred['forecast']
        ae = torch.abs(pred[:, half:, :1] - x[:, half:, :1])
        total_ae += ae.sum().item()
        total_n += ae.numel()
    return float(total_ae / total_n * SCALE)

patients_dir = 'externals/ns-data/patients'
patient_paths = sorted([
    os.path.join(patients_dir, p, 'training')
    for p in os.listdir(patients_dir)
    if os.path.isdir(os.path.join(patients_dir, p, 'training'))
])

train_ds, val_ds = load_multipatient_nightscout(
    patient_paths, task='forecast', window_size=24, extended_features=True
)
n_feat = train_ds[0][0].shape[1]
print(f"Data: train={len(train_ds)} val={len(val_ds)} features={n_feat}")

persist_mse = persistence_mse(val_ds)
persist_mae = np.sqrt(persist_mse) * SCALE
print(f"Persistence: MSE={persist_mse:.6f}, ~MAE={persist_mae:.1f} mg/dL")

results = {}
seeds = [42, 456, 789]

for seed in seeds:
    print(f"\n{'='*60}")
    print(f"Seed {seed}: Gen-3 (semantic_groups, d=128, nhead=8, layers=3)")
    set_seed(seed)
    
    model = create_model(
        arch='grouped', input_dim=n_feat, d_model=128, nhead=8,
        num_layers=3, semantic_groups=True
    )
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {n_params:,}")
    
    save_path = f'externals/experiments/exp231_gen3_sel_s{seed}.pth'
    t0 = time.time()
    train_forecast(model, train_ds, val_ds, save_path,
                   label=f'EXP-231 Gen3-Sel s{seed}',
                   epochs=100, lr=5e-4, patience=20, batch=32)
    train_time = time.time() - t0
    
    mse = forecast_mse(model, val_ds)
    mae = compute_mae(model, val_ds)
    results[f's{seed}'] = {
        'mae': round(mae, 2), 'mse': round(float(mse), 6),
        'rmse': round(float(np.sqrt(mse)) * SCALE, 2),
        'params': n_params, 'train_time': round(train_time, 1)
    }
    print(f"  MAE={mae:.1f} mg/dL  RMSE={np.sqrt(mse)*SCALE:.1f}  time={train_time:.0f}s")

mean_mae = np.mean([r['mae'] for r in results.values()])
std_mae = np.std([r['mae'] for r in results.values()])

summary = {
    'experiment': 'EXP-231',
    'title': 'Gen-3 Semantic Groups with Selective Masking',
    'hypothesis': 'Gen-3 with selective mask should beat Gen-2 selective (18.2 MAE)',
    'architecture': {'type': 'Gen-3', 'd_model': 128, 'nhead': 8,
                     'num_layers': 3, 'input_dim': n_feat, 'semantic_groups': True},
    'masking': {'type': 'selective', 'channels': FUTURE_UNKNOWN_CHANNELS},
    'results': results,
    'summary': {'mean_mae': round(float(mean_mae), 2), 'std_mae': round(float(std_mae), 2)},
    'comparison': {
        'gen3_full_mask_10ch': 22.7, 'gen2_selective_7ch': 18.2,
        'gen2_oracle_ch0': 17.9, 'persistence_approx': round(persist_mae, 1)
    }
}

with open('externals/experiments/exp231_gen3_selective.json', 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\n{'='*60}")
print(f"EXP-231: Gen-3 Selective = {mean_mae:.1f} ± {std_mae:.1f} mg/dL")
print(f"  vs Gen-3 full mask: 22.7 (Δ={mean_mae-22.7:+.1f})")
print(f"  vs Gen-2 selective: 18.2 (Δ={mean_mae-18.2:+.1f})")
print(f"  vs persistence:     {persist_mae:.1f}")
