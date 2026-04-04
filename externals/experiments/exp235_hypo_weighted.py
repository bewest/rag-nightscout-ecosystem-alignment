"""EXP-235: Hypo-Weighted Training with Selective Masking.
Assign higher weight to low-glucose windows during training.
Clinical goal: improve prediction accuracy in dangerous range (<80 mg/dL).
"""
import sys, json, time, os, numpy as np, torch
import torch.nn as nn
sys.path.insert(0, '.')
from tools.cgmencode.real_data_adapter import load_multipatient_nightscout
from tools.cgmencode.experiment_lib import (
    create_model, set_seed, mask_future_channels, get_device, batch_to_device,
    load_checkpoint
)
from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS, NORMALIZATION_SCALES
from torch.utils.data import DataLoader

SCALE = NORMALIZATION_SCALES.get('glucose', 400.0)
HYPO_THRESH = 80.0 / SCALE  # 80 mg/dL in normalized space

def compute_mae(model, val_ds, batch_size=64, hypo_only=False):
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
        
        pred_g = pred[:, half:, :1]
        true_g = x[:, half:, :1]
        
        if hypo_only:
            mask = true_g < HYPO_THRESH
            if mask.sum() == 0: continue
            ae = torch.abs(pred_g[mask] - true_g[mask])
        else:
            ae = torch.abs(pred_g - true_g)
        
        total_ae += ae.sum().item()
        total_n += ae.numel() if not hypo_only else mask.sum().item()
    
    if total_n == 0: return float('nan')
    return float(total_ae / total_n * SCALE)

def hypo_weighted_train(model, train_ds, val_ds, save_path, label,
                        epochs=100, lr=1e-3, patience=15, batch=32,
                        hypo_weight=3.0):
    """Train with higher weight for low-glucose windows."""
    device = get_device()
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    
    train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch)
    
    best, stale = float('inf'), 0
    
    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_input = x.clone()
            mask_future_channels(x_input, half)
            
            pred = model(x_input, causal=True)
            if isinstance(pred, dict): pred = pred['forecast']
            
            pred_g = pred[:, half:, :1]
            true_g = x[:, half:, :1]
            
            # Weighted MSE: higher weight for hypo regions
            weights = torch.ones_like(true_g)
            weights[true_g < HYPO_THRESH] = hypo_weight
            
            loss = (weights * (pred_g - true_g) ** 2).mean()
            
            opt.zero_grad()
            loss.backward()
            opt.step()
            
            ttl += loss.item() * x.shape[0]
            tn += x.shape[0]
        
        tl = ttl / tn if tn else float('inf')
        
        # Standard val loss (unweighted for fair comparison)
        model.eval()
        vtl, vn = 0.0, 0
        crit = nn.MSELoss()
        with torch.no_grad():
            for b in val_dl:
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_input = x.clone()
                mask_future_channels(x_input, half)
                pred = model(x_input, causal=True)
                if isinstance(pred, dict): pred = pred['forecast']
                loss = crit(pred[:, half:, :1], x[:, half:, :1])
                vtl += loss.item() * x.shape[0]
                vn += x.shape[0]
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)
        
        if vl < best:
            best = vl; stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'model_state': model.state_dict(), 'val_loss': vl}, save_path)
        else:
            stale += 1
        
        if (ep + 1) % 20 == 0:
            print(f'  [{label}] {ep+1}/{epochs} train={tl:.6f} val={vl:.6f} best={best:.6f}')
        
        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break
    
    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1

patients_dir = 'externals/ns-data/patients'
patient_paths = sorted([
    os.path.join(patients_dir, p, 'training')
    for p in os.listdir(patients_dir)
    if os.path.isdir(os.path.join(patients_dir, p, 'training'))
])

train_ds, val_ds = load_multipatient_nightscout(patient_paths, task='forecast', window_size=24)
print(f"Data: train={len(train_ds)} val={len(val_ds)}")

# Test hypo_weight values: 1.0 (baseline), 3.0, 5.0, 10.0
weights_to_test = [1.0, 3.0, 5.0, 10.0]
results = {}

for hw in weights_to_test:
    print(f"\n{'='*50}")
    print(f"Hypo weight = {hw}")
    set_seed(42)
    model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    save_path = f'externals/experiments/exp235_hypo_w{int(hw)}.pth'
    
    t0 = time.time()
    hypo_weighted_train(model, train_ds, val_ds, save_path,
                        label=f'EXP-235 w={hw}',
                        epochs=100, lr=1e-3, patience=15,
                        hypo_weight=hw)
    train_time = time.time() - t0
    
    overall_mae = compute_mae(model, val_ds)
    hypo_mae = compute_mae(model, val_ds, hypo_only=True)
    
    results[f'w{int(hw)}'] = {
        'hypo_weight': hw,
        'overall_mae': round(overall_mae, 2),
        'hypo_mae': round(hypo_mae, 2),
        'train_time': round(train_time, 1)
    }
    print(f"  Overall MAE={overall_mae:.1f}, Hypo MAE={hypo_mae:.1f} ({train_time:.0f}s)")

summary = {
    'experiment': 'EXP-235',
    'title': 'Hypo-Weighted Training with Selective Masking',
    'hypothesis': 'Higher weight on <80 mg/dL improves hypo prediction',
    'hypo_threshold': '80 mg/dL',
    'results': results,
    'comparison': {'exp232_individual_unweighted': 12.9}
}

with open('externals/experiments/exp235_hypo_weighted.json', 'w') as f:
    json.dump(summary, f, indent=2)

print(f"\n{'='*60}")
print(f"EXP-235 RESULTS:")
for k, v in results.items():
    print(f"  {k}: Overall={v['overall_mae']:.1f}, Hypo={v['hypo_mae']:.1f}")
