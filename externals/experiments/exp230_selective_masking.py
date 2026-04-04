"""EXP-230: Selective Masking Strategy — the breakthrough experiment.

Hypothesis: IOB/COB decay curves are deterministic from current state.
Only truly unpredictable channels need masking. Tests 3 strategies:
  - Full mask (10 channels): masks IOB, COB, basal, bolus, carbs, glucose, derivatives
  - Selective mask (7 channels): keeps IOB, COB, basal (deterministic)
  - Oracle (ch0 only): masks only glucose (upper bound, leaks bolus/carb info)

Result: Selective=18.2, Oracle=17.9, Full=25.1. Selective captures 95% of oracle.
Led to updating FUTURE_UNKNOWN_CHANNELS in schema.py.
"""
import sys, os, json, time, numpy as np, torch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
from tools.cgmencode.experiment_lib import (
    create_model, train_forecast, set_seed, get_device, batch_to_device
)
from tools.cgmencode.schema import NORMALIZATION_SCALES, IDX_GLUCOSE
from torch.utils.data import DataLoader

SCALE = NORMALIZATION_SCALES.get('glucose', 400.0)
TRULY_UNKNOWN = [0, 4, 5, 12, 13, 14, 15]   # selective: glucose, bolus, carbs, derivatives
ORACLE_MASK   = [0]                           # oracle: glucose only

def custom_mask(x_input, half, channels):
    for ch in channels:
        if ch < x_input.shape[2]:
            x_input[:, half:, ch] = 0.0

def train_with_mask(model, train_ds, val_ds, save_path, label, mask_channels,
                    epochs=100, lr=1e-3, patience=15, batch=32):
    """Custom training loop with configurable mask channels."""
    device = get_device()
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    crit = torch.nn.MSELoss()
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    best, stale = float('inf'), 0
    
    for ep in range(epochs):
        model.train()
        for b in train_dl:
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            custom_mask(x_in, half, mask_channels)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict): pred = pred['forecast']
            loss = crit(pred[:, half:, :1], x[:, half:, :1])
            opt.zero_grad(); loss.backward(); opt.step()
        
        model.eval()
        vl = 0.0; vn = 0
        with torch.no_grad():
            for b in val_dl:
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_in = x.clone()
                custom_mask(x_in, half, mask_channels)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict): pred = pred['forecast']
                vl += crit(pred[:, half:, :1], x[:, half:, :1]).item() * x.shape[0]
                vn += x.shape[0]
        vl /= vn
        sched.step(vl)
        if vl < best:
            best = vl; stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'val_loss': vl}, save_path)
        else:
            stale += 1
        if patience > 0 and stale >= patience: break
    
    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])

def compute_mae(model, val_ds, mask_channels, batch_size=64):
    device = get_device()
    model.eval()
    total_ae, total_n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        custom_mask(x_in, half, mask_channels)
        with torch.no_grad():
            pred = model(x_in, causal=True)
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
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    
    for name, channels in [('selective', TRULY_UNKNOWN), ('oracle_ch0', ORACLE_MASK)]:
        for seed in [42, 456]:
            set_seed(seed)
            model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
            save_path = f'externals/experiments/exp230_{name}_s{seed}.pth'
            train_with_mask(model, train_ds, val_ds, save_path,
                           f'EXP-230 {name} s{seed}', channels)
            mae = compute_mae(model, val_ds, channels)
            print(f"{name} s{seed}: MAE={mae:.1f}")
