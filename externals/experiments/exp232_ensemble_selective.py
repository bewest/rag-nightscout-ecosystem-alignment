"""EXP-232: Gen-2 5-seed ensemble with selective masking."""
import sys, json, time, os, numpy as np, torch
sys.path.insert(0, '.')
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
from tools.cgmencode.experiment_lib import (
    create_model, train_forecast, forecast_mse, persistence_mse, set_seed,
    mask_future_channels, get_device, batch_to_device
)
from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS, NORMALIZATION_SCALES, IDX_GLUCOSE
from torch.utils.data import DataLoader

SCALE = NORMALIZATION_SCALES.get('glucose', 400.0)

def compute_mae(model, val_ds, batch_size=64):
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

def compute_ensemble_mae(models, val_ds, batch_size=64):
    device = get_device()
    total_ae, total_n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_input = x.clone()
        mask_future_channels(x_input, half)
        
        preds = []
        for m in models:
            m.eval()
            with torch.no_grad():
                pred = m(x_input, causal=True)
            if isinstance(pred, dict):
                pred = pred['forecast']
            preds.append(pred[:, half:, :1])
        
        ensemble = torch.stack(preds).mean(dim=0)
        ae = torch.abs(ensemble - x[:, half:, :1])
        total_ae += ae.sum().item()
        total_n += ae.numel()
    return float(total_ae / total_n * SCALE)

patients_dir = 'externals/ns-data/patients'
patient_paths = sorted([
    os.path.join(patients_dir, p, 'training')
    for p in os.listdir(patients_dir)
    if os.path.isdir(os.path.join(patients_dir, p, 'training'))
])

train_ds, val_ds = load_multipatient_nightscout(patient_paths, task='forecast', window_size=24)
print(f"Data: train={len(train_ds)} val={len(val_ds)} features={train_ds[0][0].shape[1]}")

persist_mse = persistence_mse(val_ds)
persist_mae = np.sqrt(persist_mse) * SCALE
print(f"Persistence: ~MAE={persist_mae:.1f} mg/dL")

seeds = [42, 123, 456, 789, 1024]
models = []
individual_results = {}

for seed in seeds:
    print(f"\n--- Seed {seed} ---")
    set_seed(seed)
    model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    save_path = f'externals/experiments/exp232_ens_s{seed}.pth'
    
    t0 = time.time()
    train_forecast(model, train_ds, val_ds, save_path,
                   label=f'EXP-232 s{seed}',
                   epochs=100, lr=1e-3, patience=15, batch=32)
    train_time = time.time() - t0
    
    mae = compute_mae(model, val_ds)
    mse = forecast_mse(model, val_ds)
    individual_results[f's{seed}'] = {
        'mae': round(mae, 2), 'mse': round(float(mse), 6), 'train_time': round(train_time, 1)
    }
    models.append(model)
    print(f"  Individual MAE={mae:.1f} mg/dL  ({train_time:.0f}s)")

# Ensemble
ensemble_mae = compute_ensemble_mae(models, val_ds)
mean_individual = np.mean([r['mae'] for r in individual_results.values()])
std_individual = np.std([r['mae'] for r in individual_results.values()])

summary = {
    'experiment': 'EXP-232',
    'title': 'Gen-2 5-Seed Ensemble with Selective Masking',
    'architecture': {'type': 'Gen-2', 'd_model': 64, 'nhead': 4, 'num_layers': 2, 'input_dim': 8},
    'masking': {'type': 'selective', 'channels': FUTURE_UNKNOWN_CHANNELS},
    'results': {
        'individual': individual_results,
        'ensemble_mae': round(float(ensemble_mae), 2),
        'mean_individual_mae': round(float(mean_individual), 2),
        'std_individual_mae': round(float(std_individual), 2),
    },
    'comparison': {
        'gen2_ensemble_leaked': 12.1, 'gen2_single_selective': 18.2,
        'persistence_approx': round(persist_mae, 1)
    }
}

with open('externals/experiments/exp232_ensemble_selective.json', 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\n{'='*60}")
print(f"EXP-232 RESULTS:")
print(f"  Individual mean: {mean_individual:.1f} ± {std_individual:.1f} mg/dL")
print(f"  Ensemble:        {ensemble_mae:.1f} mg/dL")
print(f"  vs leaked ensemble (12.1):  Δ={ensemble_mae-12.1:+.1f}")
print(f"  vs single selective (18.2): Δ={ensemble_mae-18.2:+.1f}")
print(f"  vs persistence ({persist_mae:.1f}):     Δ={ensemble_mae-persist_mae:+.1f}")
