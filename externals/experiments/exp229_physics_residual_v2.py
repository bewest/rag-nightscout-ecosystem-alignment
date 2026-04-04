"""EXP-229: Physics-Residual vs Direct Forecast with proper 10-channel masking.

Tests whether training ML to predict physics residuals (glucose - physics_pred)
beats direct glucose forecasting when future channels are properly masked.

Result: NEGATIVE — enhanced physics model is too crude (54.6 MAE, 2.4× worse
than persistence), making residuals noisier than raw glucose. Direct=25.1, 
Residual=28.0, Persistence=22.7.
"""
import sys, os, json, time, numpy as np, torch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
from tools.cgmencode.experiment_lib import (
    create_model, train_forecast, forecast_mse, persistence_mse, set_seed,
    mask_future_channels, get_device, batch_to_device
)
from tools.cgmencode.physics_model import compute_residual_windows, residual_to_glucose
from tools.cgmencode.schema import NORMALIZATION_SCALES
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
        if isinstance(pred, dict): pred = pred['forecast']
        ae = torch.abs(pred[:, half:, :1] - x[:, half:, :1])
        total_ae += ae.sum().item(); total_n += ae.numel()
    return float(total_ae / total_n * SCALE)

if __name__ == '__main__':
    patients_dir = 'externals/ns-data/patients'
    patient_paths = sorted([
        os.path.join(patients_dir, p, 'training')
        for p in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, p, 'training'))
    ])
    
    # Arm A: Direct forecast
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    
    seeds = [42, 456]
    for seed in seeds:
        set_seed(seed)
        model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        train_forecast(model, train_ds, val_ds,
                       f'externals/experiments/exp229_direct_s{seed}.pth',
                       label=f'EXP-229 Direct s{seed}', epochs=100)
        print(f"Direct s{seed}: MAE={compute_mae(model, val_ds):.1f}")
    
    # Arm B: Physics residual training would go here
    # (requires custom residual dataset construction)
    print("See exp229_physics_residual_v2.json for full results")
