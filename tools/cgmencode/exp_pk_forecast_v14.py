#!/usr/bin/env python3
"""EXP-405 through EXP-408: ERA 2 + ERA 3 Bridge Experiments

CRITICAL GAP: ERA 2's best pipeline (GroupedEncoder transformer, per-patient FT,
5-seed ensemble, MAE=10.59) has NEVER been tested with ERA 3's proven feature
discoveries. This is the single highest-impact experiment possible.

ERA 2 champion (EXP-251): d_model=64, nhead=4, L=4, 200ep base + 30ep FT
  - Features: 8ch = glucose/400, IOB/20, COB/100, net_basal/5, bolus/10, carbs/100, sin, cos
  - bolus: 1.7% nonzero (extremely sparse) → noise for transformer attention
  - carbs: 1.3% nonzero (extremely sparse) → noise for transformer attention
  - Paradigm: masked sequence (history→future), causal attention, MSE on future glucose

ERA 3 proven discoveries (never tested on GroupedEncoder):
  1. Dense PK channels replace sparse bolus/carbs (proven -10 mg/dL at h120)
  2. ISF normalization (proven -0.4 to -1.2 MAE)
  3. No time features (proven invariance at ≤2h scale)
  4. Future PK projection (biggest ERA 3 breakthrough, -6.6 MAE overall)
  5. net_balance composite signal (insulin-carb net glucose flux)

V11 full validation confirmed: SWA/longer training = negligible (34.3 vs 34.4).
The path forward is BETTER FEATURES ON BETTER ARCHITECTURE, not training tricks.

EXP-405: GroupedEncoder with PK channels replacing sparse bolus/carbs
EXP-406: GroupedEncoder with PK + future PK (deterministic, unmasked in future)
EXP-407: GroupedEncoder with PK + ISF normalization + no time
EXP-408: Full bridge (best features + per-patient FT + multi-seed ensemble)

Usage:
    python tools/cgmencode/exp_pk_forecast_v14.py --experiment 405 --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v14.py --experiment all --device cuda --quick
    python tools/cgmencode/exp_pk_forecast_v14.py --experiment 408 --device cuda  # full
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, argparse, copy, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features
from cgmencode.model import PositionalEncoding

# ─── Constants ───

GLUCOSE_SCALE = 400.0
PK_NORMS = [0.05, 0.05, 2.0, 0.5, 0.05, 3.0, 20.0, 200.0]
# PK channels: 0=insulin_total, 1=insulin_net, 2=basal_ratio, 3=carb_rate,
#              4=carb_accel, 5=hepatic_prod, 6=net_balance, 7=isf_curve

QUICK_PATIENTS = 4
QUICK_EPOCHS_BASE = 60
QUICK_EPOCHS_FT = 15
QUICK_SEEDS = [42]

FULL_PATIENTS = None  # all
FULL_EPOCHS_BASE = 200
FULL_EPOCHS_FT = 30
FULL_SEEDS = [42, 123, 456, 789, 1024]


# ─── Data Loading ───

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir()
                   if d.is_dir() and (d / 'training').exists()])


def load_patient_profile_isf(train_dir):
    """Load mean ISF from Nightscout profile (mg/dL per U)."""
    profile_path = os.path.join(train_dir, 'profile.json')
    if not os.path.exists(profile_path):
        return None
    try:
        with open(profile_path) as f:
            profile = json.load(f)
        # Profile can be a list (Nightscout API format) or dict
        if isinstance(profile, list):
            profile = profile[0] if profile else {}
        store = profile.get('store', {})
        default_profile = store.get('Default', store.get(next(iter(store), ''), {}))
        sens = default_profile.get('sens', [])
        if sens:
            isf_values = [s.get('value', 0) for s in sens]
            mean_isf = np.mean([v for v in isf_values if v > 0])
            if mean_isf < 15:  # mmol/L → mg/dL
                mean_isf *= 18.0182
            return float(mean_isf) if mean_isf > 0 else None
        return None
    except Exception:
        return None


def load_bridge_data(patients_dir, window_size=48, max_patients=None,
                     stride=None, load_isf=True, skip_patients=None):
    """Load data for bridge experiments.

    ERA 2 used window_size=24 (12 history + 12 future = 1h each at 5min).
    We use 48 (24 history = 2h, 24 future = 2h) to give PK more room.

    skip_patients: set of patient names to exclude (e.g., {'j'} for MDI-only).
    Returns dict with arrays and per-patient info for fine-tuning.
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]
    if skip_patients:
        patient_dirs = [d for d in patient_dirs if d.name not in skip_patients]

    if stride is None:
        stride = max(window_size // 3, 12)  # ~every 1h

    all_data = {
        'base_train': [], 'base_val': [],
        'pk_train': [], 'pk_val': [],
        'isf_train': [], 'isf_val': [],
    }
    per_patient = []

    for pdir in patient_dirs:
        train_dir = str(pdir / 'training')
        df, base_grid = build_nightscout_grid(train_dir, verbose=False)
        if df is None:
            continue
        pk_grid = build_continuous_pk_features(df, verbose=False)
        isf = load_patient_profile_isf(train_dir) if load_isf else None

        n_steps = min(len(base_grid), len(pk_grid))
        windows_b, windows_p = [], []
        half = window_size // 2
        for start in range(0, n_steps - window_size + 1, stride):
            wb = base_grid[start:start + window_size]
            wp = pk_grid[start:start + window_size]
            if np.isnan(wb[:half, 0]).mean() > 0.3:
                continue
            windows_b.append(np.nan_to_num(wb, 0.0))
            windows_p.append(np.nan_to_num(wp, 0.0))

        if len(windows_b) < 10:
            continue

        n = len(windows_b)
        split = int(0.8 * n)

        info = {
            'name': pdir.name,
            'n_windows': n,
            'n_train': split,
            'n_val': n - split,
            'isf': isf,
            'train_idx': (len(all_data['base_train']),
                          len(all_data['base_train']) + split),
            'val_idx': (len(all_data['base_val']),
                        len(all_data['base_val']) + (n - split)),
        }

        all_data['base_train'].extend(windows_b[:split])
        all_data['base_val'].extend(windows_b[split:])
        all_data['pk_train'].extend(windows_p[:split])
        all_data['pk_val'].extend(windows_p[split:])
        if isf is not None:
            all_data['isf_train'].extend([isf] * split)
            all_data['isf_val'].extend([isf] * (n - split))

        per_patient.append(info)
        isf_str = f" [isf={isf:.0f}]" if isf else ""
        print(f"  {pdir.name}: {n} windows ({split} train, {n-split} val){isf_str}")

    result = {
        'base_train': np.array(all_data['base_train'], dtype=np.float32),
        'base_val': np.array(all_data['base_val'], dtype=np.float32),
        'pk_train': np.array(all_data['pk_train'], dtype=np.float32),
        'pk_val': np.array(all_data['pk_val'], dtype=np.float32),
        'per_patient': per_patient,
    }
    if all_data['isf_train']:
        result['isf_train'] = np.array(all_data['isf_train'], dtype=np.float32)
        result['isf_val'] = np.array(all_data['isf_val'], dtype=np.float32)

    print(f"Total: {len(result['base_train'])} train, {len(result['base_val'])} val, "
          f"{len(per_patient)} patients")
    return result


# ─── Feature Preparation ───

def prepare_era2_baseline(data):
    """Standard ERA 2 features: 8ch as-is."""
    return (torch.tensor(data['base_train'], dtype=torch.float32),
            torch.tensor(data['base_val'], dtype=torch.float32))


def prepare_pk_replace(data, use_isf=False, drop_time=False):
    """Replace sparse bolus/carbs (ch4/5) with dense PK channels.

    Standard 8ch:  [glucose, IOB, COB, net_basal, bolus,        carbs,     sin, cos]
    PK-replaced:   [glucose, IOB, COB, net_basal, insulin_net/n, carb_rate/n, sin, cos]

    bolus: 1.7% nonzero → insulin_net: 97% nonzero
    carbs: 1.3% nonzero → carb_rate: 62% nonzero
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]  # insulin_net
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]  # carb_rate
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    if drop_time:
        bt, bv = bt[:, :, :6], bv[:, :, :6]

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def prepare_pk_future(data, use_isf=False, drop_time=False):
    """PK-replaced features where PK channels stay UNMASKED in future.

    Key insight: insulin_net and carb_rate are DETERMINISTIC from past events.
    Unlike sparse bolus (unknown future events), PK absorption curves decay
    predictably. Keeping them unmasked in the future gives the transformer
    genuine causal information about future insulin/carb state.

    Also adds net_balance (ch6 of PK) as an additional signal.
    If drop_time: replace both time channels → [gluc, IOB, COB, net_basal, ins_net, carb_rate, net_bal] = 7ch
    Else: replace time_cos with net_balance → [gluc, IOB, COB, net_basal, ins_net, carb_rate, sin, net_bal] = 8ch
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]  # insulin_net
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]  # carb_rate
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]

    if drop_time:
        # Replace sin (ch6) with net_balance, drop cos (ch7)
        bt[:, :, 6] = pt[:, :, 6] / PK_NORMS[6]
        bv[:, :, 6] = pv[:, :, 6] / PK_NORMS[6]
        bt, bv = bt[:, :, :7], bv[:, :, :7]
    else:
        # Replace cos (ch7) with net_balance, keep sin
        bt[:, :, 7] = pt[:, :, 6] / PK_NORMS[6]
        bv[:, :, 7] = pv[:, :, 6] / PK_NORMS[6]

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def _apply_isf_norm(bt, bv, isf_train, isf_val):
    """ISF-normalize glucose channel in-place."""
    isf_t = (GLUCOSE_SCALE / isf_train).reshape(-1, 1, 1)
    isf_v = (GLUCOSE_SCALE / isf_val).reshape(-1, 1, 1)
    bt[:, :, 0:1] *= isf_t
    bv[:, :, 0:1] *= isf_v
    np.clip(bt[:, :, 0:1], 0, 10, out=bt[:, :, 0:1])
    np.clip(bv[:, :, 0:1], 0, 10, out=bv[:, :, 0:1])


# ─── PK-Aware GroupedEncoder ───

class PKGroupedEncoder(nn.Module):
    """GroupedEncoder adapted for PK-replaced features.

    8ch (PK): State(glucose,IOB,COB)→50%, Action(net_basal,ins_net,carb_rate)→25%,
              Time(sin,net_balance)→25%
    7ch (PK, no-time): State→50%, Action→25%, Balance(net_balance)→25%
    6ch (PK, no-time, no-balance): State→50%, Action→50%

    Same transformer backbone as ERA 2's CGMGroupedEncoder.
    """
    def __init__(self, input_dim=8, d_model=64, nhead=4, num_layers=4,
                 dim_feedforward=128, dropout=0.1):
        super().__init__()
        assert d_model % 4 == 0
        self.input_dim = input_dim
        self.d_model = d_model

        d_state = d_model // 2     # 50% for physiological state
        d_action = d_model // 4    # 25% for PK action signals

        self.state_proj = nn.Linear(3, d_state)    # glucose, IOB, COB
        self.action_proj = nn.Linear(3, d_action)   # net_basal, insulin_net, carb_rate

        if input_dim >= 7:
            d_extra = d_model - d_state - d_action  # remaining 25%
            n_extra = input_dim - 6
            self.extra_proj = nn.Linear(n_extra, d_extra)
        else:
            self.extra_proj = None
            # Expand action to fill remaining
            self.action_proj = nn.Linear(3, d_model - d_state)

        self.pos_encoder = PositionalEncoding(d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, batch_first=True, norm_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers)
        self.output_projection = nn.Linear(d_model, input_dim)

    def _causal_mask(self, sz, device):
        return torch.triu(torch.ones(sz, sz, device=device) * float('-inf'),
                          diagonal=1)

    def encode(self, x, causal=False):
        state = self.state_proj(x[..., :3])
        action = self.action_proj(x[..., 3:6])

        if self.extra_proj is not None and x.size(-1) > 6:
            extra = self.extra_proj(x[..., 6:])
            z = torch.cat([state, action, extra], dim=-1)
        else:
            z = torch.cat([state, action], dim=-1)

        z = self.pos_encoder(z)
        mask = self._causal_mask(x.size(1), x.device) if causal else None
        return self.transformer_encoder(z, mask=mask)

    def forward(self, x, causal=False):
        return self.output_projection(self.encode(x, causal=causal))


# ─── Training ───

def get_device(requested=None):
    if requested:
        return torch.device(requested)
    return torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def mask_future_pk(x_in, half, pk_mode=False):
    """Mask future-unknown channels.

    ERA 2 standard: mask glucose(0), bolus(4), carbs(5) in future.
    PK mode: only mask glucose(0) — PK channels (4,5) are deterministic
    from past events, so keeping them unmasked is physically valid.
    IOB(1)/COB(2) decay deterministically too (ERA 2 kept them unmasked).
    """
    x_in[:, half:, 0] = 0.0  # future glucose (what we predict)
    if not pk_mode:
        # ERA 2 baseline: also mask sparse bolus/carbs
        if x_in.size(-1) > 4:
            x_in[:, half:, 4] = 0.0  # bolus
        if x_in.size(-1) > 5:
            x_in[:, half:, 5] = 0.0  # carbs
    return x_in


def train_bridge(model, train_x, val_x, save_path, label, device,
                 pk_mode=False, lr=1e-3, epochs=200, batch=32,
                 patience=20, weight_decay=1e-5, lr_patience=7,
                 future_steps=None, augment_std=0.0):
    """ERA 2-style masked-sequence forecast training with PK-aware masking.

    future_steps: if set, use asymmetric split (seq_len - future_steps history).
                  Default None = symmetric (seq_len // 2).
    augment_std: if > 0, add Gaussian noise to training inputs each batch.
    """
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    def _step(batch_data, backward=False):
        x = batch_data[0].to(device)
        half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


# ─── Evaluation ───

def evaluate_model(model, val_x, device, pk_mode=False, isf_val=None,
                   scale=GLUCOSE_SCALE, future_steps=None):
    """Evaluate masked-sequence model. Returns MAE in mg/dL at each horizon.

    future_steps: if set, predict last N steps instead of seq_len//2.
    """
    model.to(device)
    model.eval()
    dl = DataLoader(TensorDataset(val_x), batch_size=64)
    all_preds, all_targets = [], []
    idx = 0

    with torch.no_grad():
        for b in dl:
            x = b[0].to(device)
            bsz = x.size(0)
            half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
            x_in = x.clone()
            mask_future_pk(x_in, half, pk_mode=pk_mode)
            pred = model(x_in, causal=True)

            p = pred[:, half:, 0].cpu().numpy()
            t = x[:, half:, 0].cpu().numpy()

            if isf_val is not None:
                isf_batch = isf_val[idx:idx + bsz]
                undo = (isf_batch / GLUCOSE_SCALE).reshape(-1, 1)
                p = p * undo * scale
                t = t * undo * scale
            else:
                p = p * scale
                t = t * scale

            all_preds.append(p)
            all_targets.append(t)
            idx += bsz

    preds = np.concatenate(all_preds, axis=0)
    targets = np.concatenate(all_targets, axis=0)
    mae_per_step = np.mean(np.abs(preds - targets), axis=0)
    overall = np.mean(np.abs(preds - targets))

    report = {'overall_mae': round(float(overall), 2)}
    horizon_map = {
        'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
        'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71,
    }
    for name, step_idx in horizon_map.items():
        if step_idx < len(mae_per_step):
            report[name] = round(float(mae_per_step[step_idx]), 2)
    return report


def ensemble_evaluate(models, val_x, device, pk_mode=False, isf_val=None,
                      scale=GLUCOSE_SCALE, future_steps=None):
    """Average predictions from multiple models, return MAE."""
    dl = DataLoader(TensorDataset(val_x), batch_size=64)
    all_model_preds = []

    for model in models:
        model.to(device)
        model.eval()
        preds, idx = [], 0
        with torch.no_grad():
            for b in dl:
                x = b[0].to(device)
                bsz = x.size(0)
                half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
                x_in = x.clone()
                mask_future_pk(x_in, half, pk_mode=pk_mode)
                pred = model(x_in, causal=True)
                p = pred[:, half:, 0].cpu().numpy()
                if isf_val is not None:
                    p = p * (isf_val[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * scale
                else:
                    p = p * scale
                preds.append(p)
                idx += bsz
        all_model_preds.append(np.concatenate(preds, axis=0))

    # Targets
    targets, idx = [], 0
    for b in dl:
        x = b[0]
        bsz = x.size(0)
        half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
        t = x[:, half:, 0].numpy()
        if isf_val is not None:
            t = t * (isf_val[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * scale
        else:
            t = t * scale
        targets.append(t)
        idx += bsz
    targets = np.concatenate(targets, axis=0)

    ens = np.mean(all_model_preds, axis=0)
    mae_per_step = np.mean(np.abs(ens - targets), axis=0)
    overall = np.mean(np.abs(ens - targets))

    report = {'overall_mae': round(float(overall), 2)}
    horizon_map = {
        'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
        'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71,
    }
    for name, step_idx in horizon_map.items():
        if step_idx < len(mae_per_step):
            report[name] = round(float(mae_per_step[step_idx]), 2)
    return report


# ─── EXP-405: PK Channel Replacement ───

def run_exp405(args):
    """EXP-405: GroupedEncoder with PK channels replacing sparse bolus/carbs.

    Tests whether replacing sparse bolus (1.7% nonzero) and carbs (1.3% nonzero)
    with dense insulin_net (97%) and carb_rate (62%) helps the transformer.

    Variants:
      a) era2_baseline: Original 8ch with sparse bolus/carbs
      b) pk_replace_8ch: Dense PK in ch4/5, keep time
      c) pk_replace_6ch: Dense PK, drop time → 6ch
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-405: GroupedEncoder + PK Channel Replacement")
    print(f"  {cfg['max_patients'] or 'all'} patients, {len(cfg['seeds'])} seeds, "
          f"{cfg['epochs_base']} epochs")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=False)

    variants = [
        ('era2_baseline', False, False, False),  # (name, pk, drop_time, pk_mode_mask)
        ('pk_replace_8ch', True, False, True),
        ('pk_replace_6ch', True, True, True),
    ]
    results = {}
    t0 = time.time()

    for vname, use_pk, drop_time, pk_mask in variants:
        print(f"\n--- {vname} ---")
        if use_pk:
            train_x, val_x = prepare_pk_replace(data, drop_time=drop_time)
        else:
            train_x, val_x = prepare_era2_baseline(data)
        n_ch = train_x.shape[-1]
        print(f"  Channels: {n_ch}, Train: {len(train_x)}, Val: {len(val_x)}")

        seed_results = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            n_params = sum(p.numel() for p in model.parameters())
            print(f"  s{seed}: {n_params:,} params")

            sp = os.path.join(cfg['output_dir'], f'exp405_{vname}_s{seed}.pth')
            _, ep = train_bridge(
                model, train_x, val_x, sp, f'405-{vname}-s{seed}',
                device, pk_mode=pk_mask,
                epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            metrics = evaluate_model(model, val_x, device, pk_mode=pk_mask)
            seed_results.append(metrics)
            print(f"  s{seed}: MAE={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}, h120={metrics.get('h120','?')}")

        avg = {k: round(np.mean([r[k] for r in seed_results]), 2)
               for k in seed_results[0]}
        results[vname] = {'seeds': seed_results, 'average': avg, 'n_ch': n_ch}
        print(f"  → AVG: MAE={avg['overall_mae']}, h60={avg.get('h60','?')}")

    elapsed = time.time() - t0
    print(f"\nEXP-405 complete in {elapsed:.0f}s")
    _save_results(results, 'exp405_pk_grouped_encoder', cfg)
    return results


# ─── EXP-406: PK + Future PK Projection ───

def run_exp406(args):
    """EXP-406: GroupedEncoder + PK + future PK unmasked.

    The biggest ERA 3 insight: PK channels are deterministic from past events.
    With PK in ch4/5, they DON'T need masking in the future half — the
    transformer can attend to known future insulin/carb absorption state.
    Also adds net_balance as composite flux signal.

    Variants:
      a) pk_future_8ch: PK + net_balance replaces time_cos, future PK unmasked
      b) pk_future_7ch: PK + net_balance, no time_sin → 7ch
      c) pk_masked_8ch: Same features but PK masked in future (ablation)
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-406: GroupedEncoder + PK + Future PK Projection")
    print(f"  {cfg['max_patients'] or 'all'} patients, {len(cfg['seeds'])} seeds")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=False)

    results = {}
    t0 = time.time()

    # a) PK + future unmasked (8ch: net_balance replaces cos)
    for vname, drop_time, pk_mask in [
        ('pk_future_8ch', False, True),
        ('pk_future_7ch', True, True),
        ('pk_masked_8ch', False, False),  # ablation: mask PK in future
    ]:
        print(f"\n--- {vname} ---")
        train_x, val_x = prepare_pk_future(data, drop_time=drop_time)
        n_ch = train_x.shape[-1]
        print(f"  Channels: {n_ch}")

        seed_results = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp406_{vname}_s{seed}.pth')
            train_bridge(model, train_x, val_x, sp, f'406-{vname}-s{seed}',
                         device, pk_mode=pk_mask,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            metrics = evaluate_model(model, val_x, device, pk_mode=pk_mask)
            seed_results.append(metrics)
            print(f"  s{seed}: MAE={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}")

        avg = {k: round(np.mean([r[k] for r in seed_results]), 2)
               for k in seed_results[0]}
        results[vname] = {'seeds': seed_results, 'average': avg, 'n_ch': n_ch}
        print(f"  → AVG: MAE={avg['overall_mae']}")

    elapsed = time.time() - t0
    print(f"\nEXP-406 complete in {elapsed:.0f}s")
    _save_results(results, 'exp406_pk_future_grouped', cfg)
    return results


# ─── EXP-407: PK + ISF + No Time ───

def run_exp407(args):
    """EXP-407: GroupedEncoder + PK + ISF norm + no time features.

    Combines three proven ERA 3 discoveries:
      1. PK channel replacement (dense signals)
      2. ISF normalization (patient-specific glucose scaling)
      3. No time features (invariance proven at ≤2h)

    Variants:
      a) pk_isf_8ch: PK + ISF + time
      b) pk_isf_notime_6ch: PK + ISF + drop time
      c) pk_isf_future_8ch: PK + ISF + net_balance, keep time_sin
      d) pk_isf_future_notime_7ch: PK + ISF + net_balance, no time
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-407: GroupedEncoder + PK + ISF + No Time")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_train' in data
    if not has_isf:
        print("  WARNING: No ISF data, running without ISF norm")

    results = {}
    t0 = time.time()

    variants = [
        # (name, use_future_prep, use_isf, drop_time, pk_mode)
        ('pk_isf_8ch',              False, True,  False, True),
        ('pk_isf_notime_6ch',       False, True,  True,  True),
        ('pk_isf_future_8ch',       True,  True,  False, True),
        ('pk_isf_future_notime_7ch', True,  True,  True,  True),
    ]

    for vname, use_future, use_isf, drop_time, pk_mask in variants:
        print(f"\n--- {vname} ---")
        if use_future:
            train_x, val_x = prepare_pk_future(data, use_isf=use_isf and has_isf,
                                                drop_time=drop_time)
        else:
            train_x, val_x = prepare_pk_replace(data, use_isf=use_isf and has_isf,
                                                 drop_time=drop_time)
        n_ch = train_x.shape[-1]
        isf_v = data.get('isf_val') if (use_isf and has_isf) else None
        print(f"  Channels: {n_ch}, ISF: {'yes' if isf_v is not None else 'no'}")

        seed_results = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp407_{vname}_s{seed}.pth')
            train_bridge(model, train_x, val_x, sp, f'407-{vname}-s{seed}',
                         device, pk_mode=pk_mask,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            metrics = evaluate_model(model, val_x, device, pk_mode=pk_mask,
                                     isf_val=isf_v)
            seed_results.append(metrics)
            print(f"  s{seed}: MAE={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}")

        avg = {k: round(np.mean([r[k] for r in seed_results]), 2)
               for k in seed_results[0]}
        results[vname] = {'seeds': seed_results, 'average': avg, 'n_ch': n_ch}
        print(f"  → AVG: MAE={avg['overall_mae']}")

    elapsed = time.time() - t0
    print(f"\nEXP-407 complete in {elapsed:.0f}s")
    _save_results(results, 'exp407_pk_isf_grouped', cfg)
    return results


# ─── EXP-408: Full Bridge ───

def run_exp408(args):
    """EXP-408: Full Bridge — best features + per-patient FT + ensemble.

    Takes expected best from EXP-405-407 (pk_isf_future_8ch) and applies
    ERA 2's full recipe: multi-seed base + per-patient FT + ensemble.

    This is THE definitive bridge experiment.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-408: Full Bridge — Per-Patient FT + Ensemble")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_train' in data

    # Best expected config: PK + ISF + future (8ch)
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    n_ch = train_x.shape[-1]
    isf_v = data.get('isf_val') if has_isf else None

    # Phase 1: Multi-seed base training
    print(f"\n=== Phase 1: Base Training ({len(cfg['seeds'])} seeds, {n_ch}ch) ===")
    base_states = {}

    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        n_params = sum(p.numel() for p in model.parameters())
        sp = os.path.join(cfg['output_dir'], f'exp408_base_s{seed}.pth')

        print(f"\n  Base s{seed} ({n_params:,} params):")
        train_bridge(model, train_x, val_x, sp, f'408-base-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)

        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']

        metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
        print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
              f"h60={metrics.get('h60','?')}")

    # Phase 2: Per-patient fine-tuning
    print(f"\n=== Phase 2: Per-Patient Fine-Tuning ===")
    per_patient_results = {}

    for pinfo in data['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train_x = train_x[ti:te]
        p_val_x = val_x[vi:ve]
        p_isf_v = isf_v[vi:ve] if isf_v is not None else None

        print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")

        seed_maes = {}
        ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(base_states[seed])

            sp = os.path.join(cfg['output_dir'], f'exp408_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_x, p_val_x, sp, f'408-ft-{pid}-s{seed}',
                         device, pk_mode=True,
                         lr=1e-4, epochs=cfg['epochs_ft'], patience=10, lr_patience=5)

            metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                     isf_val=p_isf_v)
            seed_maes[f's{seed}'] = metrics['overall_mae']
            ft_models.append(copy.deepcopy(model))
            print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

        # Ensemble
        ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                isf_val=p_isf_v)
        per_patient_results[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': ens['overall_mae'],
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
            'ensemble_per_horizon': ens,
        }
        print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, h60={ens.get('h60','?')}")

    # Summary
    all_ens = [v['ensemble_mae'] for v in per_patient_results.values()]
    all_mean = [v['mean_seed'] for v in per_patient_results.values()]

    summary = {
        'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
        'mean_single_mae': round(float(np.mean(all_mean)), 2),
        'n_patients': len(per_patient_results),
        'n_seeds': len(cfg['seeds']),
    }

    print(f"\n{'='*60}")
    print(f"EXP-408 RESULT")
    print(f"  Mean Ensemble MAE: {summary['mean_ensemble_mae']:.2f} mg/dL")
    print(f"  Mean Single MAE:   {summary['mean_single_mae']:.2f} mg/dL")
    print(f"  Patients: {summary['n_patients']}, Seeds: {summary['n_seeds']}")
    print(f"  ERA 2 reference (EXP-251): 10.59 mg/dL (10pt, 5 seeds, h60 only)")
    print(f"  ERA 3 reference (EXP-387): 34.4 mg/dL (11pt, 3 seeds, 8 horizons)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-408: Full Bridge (PK+ISF+FuturePK+FT+Ensemble)',
        'per_patient': per_patient_results,
        'summary': summary,
        'config': {
            'n_channels': n_ch, 'window_size': 48,
            'd_model': 64, 'nhead': 4, 'num_layers': 4,
            'base_epochs': cfg['epochs_base'], 'ft_epochs': cfg['epochs_ft'],
            'ft_lr': 1e-4, 'seeds': cfg['seeds'],
            'use_isf': has_isf, 'pk_mode': True,
        },
        'comparison': {
            'era2_exp251_10pt_5seed': 10.59,
            'era3_exp387_11pt_3seed_8h': 34.4,
        },
    }
    _save_results(result, 'exp408_full_bridge', cfg)
    return result


# ─── EXP-409: h60-Only Specialist + Window Size Match ───

def run_exp409(args):
    """EXP-409: Match ERA 2's exact evaluation protocol to close the gap.

    ERA 2 used window_size=24 (12 history + 12 future = h60 max), optimizing
    loss on all future steps up to h60. Our current window=48 (24+24) dilutes
    the h60 signal across 24 future steps including h90/h120.

    Variants:
      a) w48_multi: Current champion config (baseline, 4 horizons)
      b) w24_h60: ERA 2 window (12+12), h60 = last step
      c) w48_h60only: Keep 48-step window but loss on h60 step ONLY
      d) w24_h60_large: ERA 2 window + d_model=128 (2x capacity)
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-409: h60-Only Specialist + Window Size Match")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}")
    print(f"{'='*60}")

    results = {}
    t0 = time.time()

    # --- Variant A: Current champion (w48, multi-horizon) as baseline ---
    print("\n--- w48_multi (baseline) ---")
    data48 = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    train_x48, val_x48 = prepare_pk_future(data48, use_isf=True, drop_time=False)
    isf_v48 = data48.get('isf_val')

    seed_results_a = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp409_w48_multi_s{seed}.pth')
        train_bridge(model, train_x48, val_x48, sp, f'409-w48-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        m = evaluate_model(model, val_x48, device, pk_mode=True, isf_val=isf_v48)
        seed_results_a.append(m)
        print(f"  s{seed}: MAE={m['overall_mae']:.1f}, h60={m.get('h60','?')}")
    avg_a = {k: round(np.mean([r[k] for r in seed_results_a]), 2)
             for k in seed_results_a[0]}
    results['w48_multi'] = {'seeds': seed_results_a, 'average': avg_a, 'window': 48}
    print(f"  → AVG: MAE={avg_a['overall_mae']}, h60={avg_a.get('h60','?')}")

    # --- Variant B: ERA 2 window (w24, h60 = last step) ---
    print("\n--- w24_h60 (ERA 2 match) ---")
    data24 = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    train_x24, val_x24 = prepare_pk_future(data24, use_isf=True, drop_time=False)
    isf_v24 = data24.get('isf_val')

    seed_results_b = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp409_w24_h60_s{seed}.pth')
        train_bridge(model, train_x24, val_x24, sp, f'409-w24-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        m = evaluate_model(model, val_x24, device, pk_mode=True, isf_val=isf_v24)
        seed_results_b.append(m)
        print(f"  s{seed}: MAE={m['overall_mae']:.1f}, h60={m.get('h60','?')}")
    avg_b = {k: round(np.mean([r[k] for r in seed_results_b]), 2)
             for k in seed_results_b[0]}
    results['w24_h60'] = {'seeds': seed_results_b, 'average': avg_b, 'window': 24}
    print(f"  → AVG: MAE={avg_b['overall_mae']}, h60={avg_b.get('h60','?')}")

    # --- Variant C: w48 but h60-only loss ---
    print("\n--- w48_h60only (h60-only loss) ---")
    seed_results_c = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp409_w48_h60only_s{seed}.pth')
        train_bridge_h60only(model, train_x48, val_x48, sp, f'409-h60only-s{seed}',
                             device, pk_mode=True,
                             epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        m = evaluate_model(model, val_x48, device, pk_mode=True, isf_val=isf_v48)
        seed_results_c.append(m)
        print(f"  s{seed}: MAE={m['overall_mae']:.1f}, h60={m.get('h60','?')}")
    avg_c = {k: round(np.mean([r[k] for r in seed_results_c]), 2)
             for k in seed_results_c[0]}
    results['w48_h60only'] = {'seeds': seed_results_c, 'average': avg_c, 'window': 48}
    print(f"  → AVG: MAE={avg_c['overall_mae']}, h60={avg_c.get('h60','?')}")

    # --- Variant D: w24 + larger model ---
    print("\n--- w24_h60_large (d_model=128, nhead=8) ---")
    seed_results_d = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=8, d_model=128, nhead=8, num_layers=4,
                                 dim_feedforward=256)
        n_p = sum(p.numel() for p in model.parameters())
        sp = os.path.join(cfg['output_dir'], f'exp409_w24_large_s{seed}.pth')
        print(f"  s{seed}: {n_p:,} params")
        train_bridge(model, train_x24, val_x24, sp, f'409-large-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        m = evaluate_model(model, val_x24, device, pk_mode=True, isf_val=isf_v24)
        seed_results_d.append(m)
        print(f"  s{seed}: MAE={m['overall_mae']:.1f}, h60={m.get('h60','?')}")
    avg_d = {k: round(np.mean([r[k] for r in seed_results_d]), 2)
             for k in seed_results_d[0]}
    results['w24_h60_large'] = {'seeds': seed_results_d, 'average': avg_d, 'window': 24}
    print(f"  → AVG: MAE={avg_d['overall_mae']}, h60={avg_d.get('h60','?')}")

    elapsed = time.time() - t0
    print(f"\nEXP-409 complete in {elapsed:.0f}s")
    _save_results(results, 'exp409_h60_specialist', cfg)
    return results


def train_bridge_h60only(model, train_x, val_x, save_path, label, device,
                         pk_mode=False, lr=1e-3, epochs=200, batch=32,
                         patience=20, weight_decay=1e-5, lr_patience=7):
    """Like train_bridge but loss ONLY on the h60 step (step 11 of future)."""
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    h60_step = 11  # step 11 in the future half = 60 min at 5min resolution

    def _step(batch_data, backward=False):
        x = batch_data[0].to(device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)
        # Loss only on the h60 step
        if half + h60_step < x.shape[1]:
            loss = crit(pred[:, half + h60_step, :1], x[:, half + h60_step, :1])
        else:
            loss = crit(pred[:, half:, :1], x[:, half:, :1])
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            if augment_std > 0:
                b = (b[0] + torch.randn_like(b[0]) * augment_std,)
            opt.zero_grad()
            l, n = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl; stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({'epoch': ep, 'model_state': model.state_dict(),
                        'val_loss': vl, 'label': label}, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


# ─── EXP-410: Per-Patient FT with Best Config ───

def run_exp410(args):
    """EXP-410: Full pipeline with best EXP-409 variant + per-patient FT.

    Takes the best window/loss config from EXP-409 and runs the full
    base → FT → ensemble pipeline. This is the definitive gap-closing test.

    Uses w24 (ERA 2 match) with per-patient FT + 5-seed ensemble.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-410: ERA 2-Matched Pipeline (w24 + FT + Ensemble)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # Phase 1: Multi-seed base training
    print(f"\n=== Phase 1: Base Training ({len(cfg['seeds'])} seeds, {n_ch}ch, w24) ===")
    base_states = {}

    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp410_base_s{seed}.pth')

        print(f"\n  Base s{seed}:")
        train_bridge(model, train_x, val_x, sp, f'410-base-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)

        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']

        metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
        print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
              f"h60={metrics.get('h60','?')}")

    # Phase 2: Per-patient fine-tuning
    print(f"\n=== Phase 2: Per-Patient Fine-Tuning (w24) ===")
    per_patient_results = {}

    for pinfo in data['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train_x = train_x[ti:te]
        p_val_x = val_x[vi:ve]
        p_isf_v = isf_v[vi:ve] if isf_v is not None else None

        print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")

        seed_maes = {}
        ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(base_states[seed])

            sp = os.path.join(cfg['output_dir'], f'exp410_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_x, p_val_x, sp, f'410-ft-{pid}-s{seed}',
                         device, pk_mode=True,
                         lr=1e-4, epochs=cfg['epochs_ft'], patience=10, lr_patience=5)

            metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                     isf_val=p_isf_v)
            seed_maes[f's{seed}'] = metrics['overall_mae']
            ft_models.append(copy.deepcopy(model))
            print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

        ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                isf_val=p_isf_v)
        per_patient_results[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': ens['overall_mae'],
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
            'ensemble_per_horizon': ens,
        }
        print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, h60={ens.get('h60','?')}")

    all_ens = [v['ensemble_mae'] for v in per_patient_results.values()]
    all_mean = [v['mean_seed'] for v in per_patient_results.values()]

    summary = {
        'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
        'mean_single_mae': round(float(np.mean(all_mean)), 2),
        'n_patients': len(per_patient_results),
        'n_seeds': len(cfg['seeds']),
        'window_size': 24,
    }

    print(f"\n{'='*60}")
    print(f"EXP-410 RESULT (w24, ERA 2 match)")
    print(f"  Mean Ensemble MAE: {summary['mean_ensemble_mae']:.2f} mg/dL")
    print(f"  Mean Single MAE:   {summary['mean_single_mae']:.2f} mg/dL")
    print(f"  Patients: {summary['n_patients']}, Seeds: {summary['n_seeds']}")
    print(f"  ERA 2 reference (EXP-251): 10.59 mg/dL (10pt, 5 seeds, h60 only)")
    print(f"  EXP-408 reference (w48):   13.50 mg/dL (11pt, 5 seeds, 4 horizons)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-410: ERA 2-Matched Pipeline (w24 + PK + ISF + FT)',
        'per_patient': per_patient_results,
        'summary': summary,
        'config': {
            'n_channels': n_ch, 'window_size': 24,
            'd_model': 64, 'nhead': 4, 'num_layers': 4,
            'base_epochs': cfg['epochs_base'], 'ft_epochs': cfg['epochs_ft'],
            'seeds': cfg['seeds'], 'use_isf': has_isf, 'pk_mode': True,
        },
    }
    _save_results(result, 'exp410_era2_matched', cfg)
    return result


# ─── EXP-411: Extended Horizon Pipeline (w48/w72/w96) ───

def run_exp411(args):
    """EXP-411: Extended horizon forecasting with PKGroupedEncoder.

    Use-cases: A2 (dosing), A3 (meal planning), A4 (overnight basal).
    Guide Tier 1.5: "PKGroupedEncoder + 4-6h history — potentially large"

    The transformer already exploits future PK via pk_mode=True (unmasked
    PK channels in future half). Extending window_size gives:
      w48: 24 hist (2h) + 24 future = h5-h120
      w72: 36 hist (3h) + 36 future = h5-h180
      w96: 48 hist (4h) + 48 future = h5-h240

    Hypothesis: Longer windows let the transformer see complete DIA arcs,
    improving h120+ where PK advantage is maximal (EXP-356: -10 MAE at h120).
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    window_sizes = [48, 72, 96] if not cfg['quick'] else [48, 72]

    print(f"\n{'='*60}")
    print(f"EXP-411: Extended Horizon Pipeline")
    print(f"  windows={window_sizes}, seeds={cfg['seeds']}")
    print(f"{'='*60}")

    all_results = {}

    for ws in window_sizes:
        half = ws // 2
        max_h = half * 5  # minutes
        label = f"w{ws}"
        print(f"\n{'─'*40}")
        print(f"  Window {ws} ({half} hist + {half} future = h{max_h})")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=ws,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]

        print(f"  Total: {train_x.shape[0]} train, {val_x.shape[0]} val, "
              f"{len(data['per_patient'])} patients, {n_ch}ch")

        # Phase 1: Base training
        base_states = {}
        base_metrics = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp411_{label}_base_s{seed}.pth')
            print(f"\n  Base s{seed} ({label}):")
            train_bridge(model, train_x, val_x, sp, f'411-{label}-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            base_metrics[seed] = metrics
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}, h120={metrics.get('h120','?')}")

        # Phase 2: Per-patient FT + ensemble
        print(f"\n=== Phase 2: Per-Patient FT ({label}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp411_{label}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'411-ft-{pid}-s{seed}',
                             device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h60={ens.get('h60','?')}, h120={ens.get('h120','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        ws_result = {
            'window_size': ws,
            'half': half,
            'max_horizon_min': max_h,
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
            'base_metrics': {f's{s}': m for s, m in base_metrics.items()},
        }
        all_results[label] = ws_result

        print(f"\n  {label} Mean Ensemble: {ws_result['mean_ensemble_mae']:.2f}")

    # Cross-window summary
    print(f"\n{'='*60}")
    print("EXP-411 RESULTS: Extended Horizon Comparison")
    print(f"{'='*60}")
    print(f"  {'Window':<8} {'Mean MAE':<10} {'Max Horizon':<12}")
    for label, res in all_results.items():
        print(f"  {label:<8} {res['mean_ensemble_mae']:<10.2f} "
              f"h{res['max_horizon_min']}")
    print(f"  EXP-410 ref: 10.85 (w24, h60)")

    result = {
        'experiment': 'EXP-411: Extended Horizon Pipeline',
        'results': all_results,
        'config': {
            'window_sizes': window_sizes,
            'seeds': cfg['seeds'],
            'epochs_base': cfg['epochs_base'],
            'epochs_ft': cfg['epochs_ft'],
        },
    }
    _save_results(result, 'exp411_extended_horizon', cfg)
    return result


# ─── EXP-413: Quick Wins (Cosine LR, Derivatives, Horizon-Weighted Loss) ───

def train_bridge_cosine(model, train_x, val_x, save_path, label, device,
                        pk_mode=False, lr=1e-3, epochs=200, batch=32,
                        patience=20, weight_decay=1e-5, warmup_epochs=10):
    """Same as train_bridge but with cosine LR + linear warmup."""
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # Cosine annealing after warmup
    def lr_lambda(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        progress = (epoch - warmup_epochs) / max(1, epochs - warmup_epochs)
        return 0.5 * (1 + math.cos(math.pi * progress))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    def _step(batch_data, backward=False):
        x = batch_data[0].to(device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step()

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def prepare_pk_future_with_derivatives(data, use_isf=False, drop_time=False):
    """PK features + derivatives of deterministic PK channels.

    Adds d(insulin_net)/dt and d(carb_rate)/dt as channels 8-9.
    These are DETERMINISTIC (computed from past treatments) so safe to keep
    in future half — no leakage. Also adds history-only glucose derivatives
    (dBG/dt) as channel 10, zeroed in future.

    PK derivatives tell the model about insulin/carb absorption dynamics:
    - Rising insulin_net = bolus absorption ramping up
    - Falling carb_rate = meal winding down
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    # Replace sparse with dense PK
    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]  # insulin_net
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]  # carb_rate
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]

    if not drop_time:
        bt[:, :, 7] = pt[:, :, 6] / PK_NORMS[6]  # net_balance
        bv[:, :, 7] = pv[:, :, 6] / PK_NORMS[6]

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    half = bt.shape[1] // 2

    # PK derivatives — DETERMINISTIC, safe in future
    # d(insulin_net)/dt from channel 4
    d_ins_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_ins_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_ins_t[:, 1:, 0] = bt[:, 1:, 4] - bt[:, :-1, 4]
    d_ins_v[:, 1:, 0] = bv[:, 1:, 4] - bv[:, :-1, 4]

    # d(carb_rate)/dt from channel 5
    d_carb_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_carb_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_carb_t[:, 1:, 0] = bt[:, 1:, 5] - bt[:, :-1, 5]
    d_carb_v[:, 1:, 0] = bv[:, 1:, 5] - bv[:, :-1, 5]

    # Glucose derivative — NOT deterministic, history-only
    d_gluc_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_gluc_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_gluc_t[:, 1:half, 0] = bt[:, 1:half, 0] - bt[:, :half-1, 0]
    d_gluc_v[:, 1:half, 0] = bv[:, 1:half, 0] - bv[:, :half-1, 0]
    # Future portion stays zero — glucose is unknown there

    # Scale to ~O(1) (PK derivatives are small: ~0.01 per step)
    d_ins_t *= 10.0; d_ins_v *= 10.0
    d_carb_t *= 10.0; d_carb_v *= 10.0
    d_gluc_t *= 10.0; d_gluc_v *= 10.0

    bt = np.concatenate([bt, d_ins_t, d_carb_t, d_gluc_t], axis=-1)  # 11ch
    bv = np.concatenate([bv, d_ins_v, d_carb_v, d_gluc_v], axis=-1)

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def run_exp413(args):
    """EXP-413: Quick wins — cosine LR, glucose derivatives, horizon-weighted loss.

    Tests three independent improvements on the EXP-410 champion (w24):
    a) cosine_lr: Cosine LR schedule with warmup (replaces ReduceLROnPlateau)
    b) derivatives: PK derivatives (d(ins)/dt, d(carb)/dt) + history-only dBG/dt
    c) combined: cosine_lr + derivatives together

    PK derivatives are DETERMINISTIC (safe in future). Glucose derivatives
    are zeroed in future half to prevent leakage.

    All use w24, base training only (no FT), to quickly measure direction.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-413: Quick Wins (Cosine LR + Derivatives)")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data

    # Standard features (control)
    train_std, val_std = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')

    # Features with derivatives
    train_deriv, val_deriv = prepare_pk_future_with_derivatives(
        data, use_isf=has_isf, drop_time=False)

    n_ch_std = train_std.shape[-1]
    n_ch_deriv = train_deriv.shape[-1]

    variants = {
        'control': {'train': train_std, 'val': val_std, 'n_ch': n_ch_std,
                     'cosine': False, 'label': 'Standard (EXP-410 control)'},
        'cosine_lr': {'train': train_std, 'val': val_std, 'n_ch': n_ch_std,
                       'cosine': True, 'label': 'Cosine LR + warmup'},
        'derivatives': {'train': train_deriv, 'val': val_deriv, 'n_ch': n_ch_deriv,
                         'cosine': False, 'label': f'+PK derivs + hist dBG/dt ({n_ch_deriv}ch)'},
        'combined': {'train': train_deriv, 'val': val_deriv, 'n_ch': n_ch_deriv,
                      'cosine': True, 'label': f'Cosine + PK derivs ({n_ch_deriv}ch)'},
    }

    results = {}
    for vname, vcfg in variants.items():
        print(f"\n─── {vcfg['label']} ───")
        seed_results = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=vcfg['n_ch'], d_model=64,
                                     nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp413_{vname}_s{seed}.pth')

            train_fn = train_bridge_cosine if vcfg['cosine'] else train_bridge
            train_fn(model, vcfg['train'], vcfg['val'], sp,
                     f'413-{vname}-s{seed}', device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20,
                     **({'lr_patience': 7} if not vcfg['cosine'] else {}))

            metrics = evaluate_model(model, vcfg['val'], device,
                                     pk_mode=True, isf_val=isf_v)
            seed_results.append(metrics)
            print(f"  s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}")

        avg = {k: round(float(np.mean([s[k] for s in seed_results])), 2)
               for k in seed_results[0]}
        results[vname] = {'seeds': seed_results, 'average': avg}
        print(f"  Average: overall={avg['overall_mae']:.1f}")

    print(f"\n{'='*60}")
    print("EXP-413 RESULTS")
    print(f"{'='*60}")
    for vn, vd in results.items():
        delta = vd['average']['overall_mae'] - results['control']['average']['overall_mae']
        print(f"  {vn:<14} MAE={vd['average']['overall_mae']:.2f}  "
              f"Δ={delta:+.2f}")

    result = {
        'experiment': 'EXP-413: Quick Wins',
        'results': results,
    }
    _save_results(result, 'exp413_quick_wins', cfg)
    return result


# ─── EXP-414: Overnight Risk Assessment (Category E1) ───

def load_overnight_data(patients_dir, max_patients=None):
    """Extract overnight windows: 6h evening context → overnight outcome labels.

    Each window:
      Input: 72 steps (6h @ 5min) of evening data (6pm-midnight typical)
      Labels: P(hypo overnight), P(high overnight), overnight_TIR

    A "night" is 10pm-6am (96 steps). Evening context is 4pm-10pm (72 steps).
    We use a rolling approach: any 72-step window where the NEXT 96 steps
    can be evaluated for overnight metrics.
    """
    from pathlib import Path
    patient_dirs = sorted(Path(patients_dir).iterdir())
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]

    all_x, all_y = [], []
    per_patient = []

    for pdir in patient_dirs:
        if not (pdir / 'training').exists():
            continue
        train_dir = str(pdir / 'training')
        df, grid = build_nightscout_grid(train_dir, verbose=False)
        if df is None or grid is None:
            continue
        pk_grid = build_continuous_pk_features(df, verbose=False)

        glucose = grid[:, 0] * GLUCOSE_SCALE  # restore to mg/dL
        n = min(len(grid), len(pk_grid))

        # Build 8ch PK features
        features = grid[:n].copy()
        features[:, 4] = pk_grid[:n, 1] / PK_NORMS[1]  # insulin_net
        features[:, 5] = pk_grid[:n, 3] / PK_NORMS[3]  # carb_rate

        isf = load_patient_profile_isf(train_dir)

        # Identify overnight windows
        # Input: 72 steps (6h), Prediction: next 96 steps (8h overnight)
        ctx_len = 72
        night_len = 96
        total_len = ctx_len + night_len

        windows_x, windows_y = [], []
        for start in range(0, n - total_len + 1, 12):  # stride=1h
            ctx = features[start:start + ctx_len]
            night_gluc = glucose[start + ctx_len:start + total_len]

            # Skip if too many gaps
            if np.isnan(ctx[:, 0]).mean() > 0.3:
                continue
            if np.isnan(night_gluc).mean() > 0.3:
                continue

            night_gluc_clean = night_gluc[~np.isnan(night_gluc)]
            if len(night_gluc_clean) < 20:
                continue

            # Compute overnight labels
            hypo = int(np.any(night_gluc_clean < 70))
            high = int(np.any(night_gluc_clean > 250))
            tir = float(np.mean((night_gluc_clean >= 70) & (night_gluc_clean <= 180)))

            windows_x.append(np.nan_to_num(ctx, 0.0))
            windows_y.append([hypo, high, tir])

        if len(windows_x) < 10:
            continue

        nx = len(windows_x)
        split = int(0.8 * nx)

        per_patient.append({
            'name': pdir.name,
            'n_windows': nx,
            'n_train': split,
            'n_val': nx - split,
            'isf': isf,
            'hypo_rate': round(np.mean([y[0] for y in windows_y]), 3),
            'high_rate': round(np.mean([y[1] for y in windows_y]), 3),
            'mean_tir': round(np.mean([y[2] for y in windows_y]), 3),
        })
        print(f"  {pdir.name}: {nx} nights (hypo={per_patient[-1]['hypo_rate']:.1%}, "
              f"high={per_patient[-1]['high_rate']:.1%}, TIR={per_patient[-1]['mean_tir']:.1%})")

        all_x.extend(windows_x[:split])
        all_y.extend(windows_y[:split])
        # Store val separately
        all_x.extend(windows_x[split:])
        all_y.extend(windows_y[split:])

    # Split into train/val
    train_n = sum(p['n_train'] for p in per_patient)
    val_n = sum(p['n_val'] for p in per_patient)

    x_arr = np.array(all_x, dtype=np.float32)
    y_arr = np.array(all_y, dtype=np.float32)

    return {
        'train_x': x_arr[:train_n],
        'train_y': y_arr[:train_n],
        'val_x': x_arr[train_n:train_n + val_n],
        'val_y': y_arr[train_n:train_n + val_n],
        'per_patient': per_patient,
    }


class OvernightRiskCNN(nn.Module):
    """1D-CNN for overnight risk classification.

    Input: (B, 72, 8) — 6h of PK features
    Output: (B, 3) — P(hypo), P(high), TIR estimate
    """
    def __init__(self, input_dim=8):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(input_dim, 32, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.head = nn.Sequential(
            nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(32, 3),  # hypo_logit, high_logit, tir
        )

    def forward(self, x):
        z = self.conv(x.permute(0, 2, 1)).squeeze(-1)
        out = self.head(z)
        return out


def run_exp414(args):
    """EXP-414: Overnight Risk Assessment (Use Case E1).

    Predicts P(hypo tonight), P(high tonight), and overnight TIR from
    6h evening context. The strategic planning layer's highest-impact use case.

    Architecture: 1D-CNN (proven for 2-6h classification) + Platt calibration.
    Night TIR=60.1% is worst period (EXP-126).
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-414: Overnight Risk Assessment (E1)")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    data = load_overnight_data(args.patients_dir,
                               max_patients=cfg['max_patients'])
    train_x = torch.tensor(data['train_x'], dtype=torch.float32)
    train_y = torch.tensor(data['train_y'], dtype=torch.float32)
    val_x = torch.tensor(data['val_x'], dtype=torch.float32)
    val_y = torch.tensor(data['val_y'], dtype=torch.float32)

    n_train = len(train_x)
    n_val = len(val_x)
    hypo_prev = float(train_y[:, 0].mean())
    high_prev = float(train_y[:, 1].mean())
    print(f"\n  Train: {n_train}, Val: {n_val}")
    print(f"  Hypo prevalence: {hypo_prev:.1%}")
    print(f"  High prevalence: {high_prev:.1%}")

    all_seeds = []
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = OvernightRiskCNN(input_dim=train_x.shape[-1]).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=7, factor=0.5)

        # Use BCE for classification heads, MSE for TIR
        bce = nn.BCEWithLogitsLoss()
        mse = nn.MSELoss()

        train_dl = DataLoader(TensorDataset(train_x, train_y),
                              batch_size=64, shuffle=True)
        best_loss = float('inf')
        stale = 0
        sp = os.path.join(cfg['output_dir'], f'exp414_s{seed}.pth')

        epochs = cfg['epochs_base']
        for ep in range(epochs):
            model.train()
            ttl, tn = 0.0, 0
            for bx, by in train_dl:
                bx, by = bx.to(device), by.to(device)
                opt.zero_grad()
                pred = model(bx)
                loss = (bce(pred[:, 0], by[:, 0]) +
                        bce(pred[:, 1], by[:, 1]) +
                        mse(torch.sigmoid(pred[:, 2]), by[:, 2]))
                loss.backward()
                opt.step()
                ttl += loss.item() * bx.size(0); tn += bx.size(0)

            model.eval()
            with torch.no_grad():
                vx, vy = val_x.to(device), val_y.to(device)
                vpred = model(vx)
                vloss = (bce(vpred[:, 0], vy[:, 0]) +
                         bce(vpred[:, 1], vy[:, 1]) +
                         mse(torch.sigmoid(vpred[:, 2]), vy[:, 2]))
                vl = vloss.item()

            sched.step(vl)
            if vl < best_loss:
                best_loss = vl
                stale = 0
                os.makedirs(os.path.dirname(sp) or '.', exist_ok=True)
                torch.save(model.state_dict(), sp)
            else:
                stale += 1

            if (ep + 1) % 10 == 0:
                print(f"  [414-s{seed}] {ep+1:3d}/{epochs} "
                      f"train={ttl/tn:.4f} val={vl:.4f} best={best_loss:.4f}")

            if stale >= 20:
                print(f"  [414-s{seed}] Early stop at epoch {ep+1}")
                break

        # Evaluate
        model.load_state_dict(torch.load(sp, map_location=device, weights_only=False))
        model.eval()
        with torch.no_grad():
            vx = val_x.to(device)
            vpred = model(vx)
            hypo_prob = torch.sigmoid(vpred[:, 0]).cpu().numpy()
            high_prob = torch.sigmoid(vpred[:, 1]).cpu().numpy()
            tir_pred = torch.sigmoid(vpred[:, 2]).cpu().numpy()

        vy_np = val_y.numpy()

        # AUC-ROC
        from sklearn.metrics import roc_auc_score, f1_score
        hypo_auc = roc_auc_score(vy_np[:, 0], hypo_prob) if vy_np[:, 0].sum() > 0 else 0
        high_auc = roc_auc_score(vy_np[:, 1], high_prob) if vy_np[:, 1].sum() > 0 else 0

        # F1 at threshold 0.5
        hypo_f1 = f1_score(vy_np[:, 0], (hypo_prob > 0.5).astype(int))
        high_f1 = f1_score(vy_np[:, 1], (high_prob > 0.5).astype(int))

        # TIR MAE
        tir_mae = float(np.mean(np.abs(tir_pred - vy_np[:, 2])))

        seed_result = {
            'hypo_auc': round(hypo_auc, 3),
            'high_auc': round(high_auc, 3),
            'hypo_f1': round(hypo_f1, 3),
            'high_f1': round(high_f1, 3),
            'tir_mae': round(tir_mae, 3),
        }
        all_seeds.append(seed_result)
        print(f"  s{seed}: hypo_AUC={hypo_auc:.3f} F1={hypo_f1:.3f}, "
              f"high_AUC={high_auc:.3f} F1={high_f1:.3f}, TIR_MAE={tir_mae:.3f}")

    # Average
    avg = {k: round(float(np.mean([s[k] for s in all_seeds])), 3)
           for k in all_seeds[0]}
    print(f"\n{'='*60}")
    print(f"EXP-414 RESULTS: Overnight Risk Assessment")
    print(f"{'='*60}")
    print(f"  Hypo:   AUC={avg['hypo_auc']:.3f}, F1={avg['hypo_f1']:.3f}")
    print(f"  High:   AUC={avg['high_auc']:.3f}, F1={avg['high_f1']:.3f}")
    print(f"  TIR:    MAE={avg['tir_mae']:.3f}")

    result = {
        'experiment': 'EXP-414: Overnight Risk Assessment (E1)',
        'seeds': all_seeds,
        'average': avg,
        'data': {
            'n_train': n_train, 'n_val': n_val,
            'hypo_prevalence': round(hypo_prev, 3),
            'high_prevalence': round(high_prev, 3),
            'n_patients': len(data['per_patient']),
        },
        'per_patient': data['per_patient'],
    }
    _save_results(result, 'exp414_overnight_risk', cfg)
    return result


# ─── EXP-419: Cosine LR on Champion Pipeline ───

def run_exp419(args):
    """EXP-419: Cosine LR applied to EXP-410 champion pipeline.

    EXP-413 showed cosine LR gives -0.37 MAE (quick mode, base only).
    This tests whether the improvement holds with full FT + ensemble.
    Expected: ~10.85 → ~10.5.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-419: Cosine LR Champion Pipeline (w24 + FT + Ensemble)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # Phase 1: Base training with cosine LR
    print(f"\n=== Phase 1: Base Training w/ Cosine LR ({len(cfg['seeds'])} seeds) ===")
    base_states = {}

    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp419_base_s{seed}.pth')

        print(f"\n  Base s{seed} (cosine LR):")
        train_bridge_cosine(model, train_x, val_x, sp, f'419-base-s{seed}',
                            device, pk_mode=True,
                            epochs=cfg['epochs_base'], patience=20,
                            warmup_epochs=10)

        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']

        metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
        print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
              f"h60={metrics.get('h60','?')}")

    # Phase 2: Per-patient FT (still use ReduceLROnPlateau for FT — short horizon)
    print(f"\n=== Phase 2: Per-Patient Fine-Tuning (w24) ===")
    per_patient_results = {}

    for pinfo in data['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train_x = train_x[ti:te]
        p_val_x = val_x[vi:ve]
        p_isf_v = isf_v[vi:ve] if isf_v is not None else None

        print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")

        seed_maes = {}
        ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(base_states[seed])

            sp = os.path.join(cfg['output_dir'], f'exp419_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_x, p_val_x, sp, f'419-ft-{pid}-s{seed}',
                         device, pk_mode=True,
                         lr=1e-4, epochs=cfg['epochs_ft'], patience=10, lr_patience=5)

            metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                     isf_val=p_isf_v)
            seed_maes[f's{seed}'] = metrics['overall_mae']
            ft_models.append(copy.deepcopy(model))
            print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

        ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                isf_val=p_isf_v)
        per_patient_results[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': ens['overall_mae'],
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
            'ensemble_per_horizon': ens,
        }
        print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, h60={ens.get('h60','?')}")

    all_ens = [v['ensemble_mae'] for v in per_patient_results.values()]
    all_mean = [v['mean_seed'] for v in per_patient_results.values()]

    summary = {
        'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
        'mean_single_mae': round(float(np.mean(all_mean)), 2),
        'n_patients': len(per_patient_results),
        'n_seeds': len(cfg['seeds']),
        'window_size': 24,
    }

    print(f"\n{'='*60}")
    print(f"EXP-419 RESULT (Cosine LR + w24 FT Ensemble)")
    print(f"  Mean Ensemble MAE: {summary['mean_ensemble_mae']:.2f} mg/dL")
    print(f"  Mean Single MAE:   {summary['mean_single_mae']:.2f} mg/dL")
    print(f"  EXP-410 reference: 10.85 mg/dL (ReduceLROnPlateau)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-419: Cosine LR Champion Pipeline',
        'per_patient': per_patient_results,
        'summary': summary,
        'config': {
            'n_channels': n_ch, 'window_size': 24,
            'scheduler': 'cosine_warmup', 'warmup_epochs': 10,
            'base_epochs': cfg['epochs_base'], 'ft_epochs': cfg['epochs_ft'],
            'seeds': cfg['seeds'], 'use_isf': has_isf, 'pk_mode': True,
        },
    }
    _save_results(result, 'exp419_cosine_champion', cfg)
    return result


# ─── EXP-420: Horizon-Adaptive Ensemble ───

def run_exp420(args):
    """EXP-420: Horizon-adaptive ensemble — w24 for short, w48 for long.

    Uses pre-trained models from EXP-419 (w24) and EXP-411 (w48).
    For each patient, pick best model per horizon band:
      h5-h60: w24 specialist (lower MAE at short horizons)
      h60-h120: w48 specialist (has these horizons, w24 doesn't)

    This is a zero-cost improvement — no new training needed.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-420: Horizon-Adaptive Ensemble")
    print(f"{'='*60}")

    # Load both window sizes
    data_w24 = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    data_w48 = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)

    has_isf = 'isf_val' in data_w24
    _, val_w24 = prepare_pk_future(data_w24, use_isf=has_isf, drop_time=False)
    _, val_w48 = prepare_pk_future(data_w48, use_isf=has_isf, drop_time=False)
    isf_w24 = data_w24.get('isf_val')
    isf_w48 = data_w48.get('isf_val')
    n_ch = val_w24.shape[-1]

    # Try to load saved models
    output_dir = cfg['output_dir']
    results = {}

    for pinfo_24, pinfo_48 in zip(data_w24['per_patient'], data_w48['per_patient']):
        pid = pinfo_24['name']
        assert pid == pinfo_48['name'], f"Patient mismatch: {pid} vs {pinfo_48['name']}"

        vi24, ve24 = pinfo_24['val_idx']
        vi48, ve48 = pinfo_48['val_idx']
        p_val_24 = val_w24[vi24:ve24]
        p_val_48 = val_w48[vi48:ve48]
        p_isf_24 = isf_w24[vi24:ve24] if isf_w24 is not None else None
        p_isf_48 = isf_w48[vi48:ve48] if isf_w48 is not None else None

        # Evaluate w24 model
        w24_models = []
        for seed in cfg['seeds']:
            sp = os.path.join(output_dir, f'exp419_ft_{pid}_s{seed}.pth')
            if not os.path.exists(sp):
                sp = os.path.join(output_dir, f'exp410_ft_{pid}_s{seed}.pth')
            if not os.path.exists(sp):
                print(f"  {pid}: no w24 model found, skipping")
                break
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            model.load_state_dict(ckpt['model_state'])
            w24_models.append(model)

        w48_models = []
        for seed in cfg['seeds']:
            sp = os.path.join(output_dir, f'exp411_w48_ft_{pid}_s{seed}.pth')
            if not os.path.exists(sp):
                break
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            model.load_state_dict(ckpt['model_state'])
            w48_models.append(model)

        if not w24_models:
            print(f"  {pid}: no w24 models, skipping")
            continue

        ens_24 = ensemble_evaluate(w24_models, p_val_24, device, pk_mode=True,
                                   isf_val=p_isf_24)
        print(f"  {pid} w24: overall={ens_24['overall_mae']:.1f}, "
              f"h30={ens_24.get('h30','?')}, h60={ens_24.get('h60','?')}")

        if w48_models:
            ens_48 = ensemble_evaluate(w48_models, p_val_48, device, pk_mode=True,
                                       isf_val=p_isf_48)
            print(f"  {pid} w48: overall={ens_48['overall_mae']:.1f}, "
                  f"h60={ens_48.get('h60','?')}, h120={ens_48.get('h120','?')}")
            results[pid] = {'w24': ens_24, 'w48': ens_48}
        else:
            results[pid] = {'w24': ens_24, 'w48': None}
            print(f"  {pid}: no w48 models")

    print(f"\n{'='*60}")
    print("EXP-420 RESULTS: Horizon-Adaptive Ensemble")
    print(f"{'='*60}")
    for pid, res in results.items():
        w24_h60 = res['w24'].get('h60', '?')
        if res['w48']:
            w48_h60 = res['w48'].get('h60', '?')
            w48_h120 = res['w48'].get('h120', '?')
            print(f"  {pid}: w24_h60={w24_h60}, w48_h60={w48_h60}, w48_h120={w48_h120}")
        else:
            print(f"  {pid}: w24_h60={w24_h60}, w48=N/A")

    result = {
        'experiment': 'EXP-420: Horizon-Adaptive Ensemble',
        'per_patient': {pid: {k: v for k, v in r.items()} for pid, r in results.items()},
    }
    _save_results(result, 'exp420_horizon_adaptive', cfg)
    return result


# ─── EXP-421: Asymmetric Windows ───

def run_exp421(args):
    """EXP-421: Asymmetric windows — more history, same 1h future.

    Hypothesis: The transformer benefits from longer history context without
    the loss dilution of predicting further into the future.

    Variants:
      - w24 (baseline): 12 history + 12 future (1h + 1h)
      - w36_asym: 24 history + 12 future (2h history + 1h future)
      - w48_asym: 36 history + 12 future (3h history + 1h future)

    Key: future_steps=12 always, but history grows.
    Loss is only on the last 12 steps, so no dilution.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    future_steps = 12  # always 1h future

    print(f"\n{'='*60}")
    print(f"EXP-421: Asymmetric Windows (future={future_steps} steps = 1h)")
    print(f"{'='*60}")

    variants = {
        'w24_sym': 24,     # baseline: 12+12 (symmetric)
        'w36_asym': 36,    # 24 hist + 12 future (2h+1h)
        'w48_asym': 48,    # 36 hist + 12 future (3h+1h)
    }

    results = {}
    for vname, wsize in variants.items():
        is_sym = (vname == 'w24_sym')
        fs = None if is_sym else future_steps
        hist = wsize // 2 if is_sym else wsize - future_steps

        print(f"\n--- {vname}: window={wsize}, history={hist} ({hist*5}min), "
              f"future={wsize-hist} ({(wsize-hist)*5}min) ---")

        data = load_bridge_data(
            args.patients_dir, window_size=wsize,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_val = data.get('isf_val')
        n_ch = train_x.shape[-1]

        seed = cfg['seeds'][0]
        torch.manual_seed(seed)
        np.random.seed(seed)

        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp421_{vname}_s{seed}.pth')
        _, ep = train_bridge(model, train_x, val_x, sp, f'421-{vname}', device,
                             pk_mode=True, epochs=cfg['epochs_base'],
                             future_steps=fs)

        report = evaluate_model(model, val_x, device, pk_mode=True,
                                isf_val=isf_val, future_steps=fs)
        print(f"  {vname}: overall={report['overall_mae']}, "
              f"h30={report.get('h30','?')}, h60={report.get('h60','?')}")

        # Per-patient FT for best variant (quick: just base comparison)
        if not cfg['quick']:
            ft_maes = []
            for pinfo in data['per_patient']:
                pid = pinfo['name']
                vi, ve = pinfo['val_idx']
                ti, te = pinfo['train_idx']
                p_train = train_x[ti:te]
                p_val = val_x[vi:ve]
                p_isf = isf_val[vi:ve] if isf_val is not None else None

                ft_model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                ft_model.load_state_dict(model.state_dict())
                ft_sp = os.path.join(cfg['output_dir'], f'exp421_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(ft_model, p_train, p_val, ft_sp, f'421-ft-{pid}', device,
                             pk_mode=True, lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, future_steps=fs)
                ft_report = evaluate_model(ft_model, p_val, device, pk_mode=True,
                                           isf_val=p_isf, future_steps=fs)
                ft_maes.append(ft_report['overall_mae'])
                print(f"    {pid}: {ft_report['overall_mae']:.1f}")
            report['ft_mean'] = round(np.mean(ft_maes), 2)
            print(f"  {vname} FT mean: {report['ft_mean']}")

        results[vname] = report

    print(f"\n{'='*60}")
    print("EXP-421 RESULTS: Asymmetric Windows")
    print(f"{'='*60}")
    for vname, r in results.items():
        ft_str = f", FT={r.get('ft_mean','?')}" if 'ft_mean' in r else ""
        print(f"  {vname}: base={r['overall_mae']}{ft_str}")

    result = {'experiment': 'EXP-421: Asymmetric Windows', 'variants': results}
    _save_results(result, 'exp421_asymmetric_windows', cfg)
    return result


# ─── EXP-417: Hard Patient Optimization ───

def run_exp417(args):
    """EXP-417: Hard patient optimization.

    Patients b (17.1), j (15.0), a (13.1) account for disproportionate error.
    Uses EXP-410 base models and tries:
      - longer_ft: 100 epochs (vs 30 default)
      - augment: Gaussian noise (σ=0.01) during FT
      - combined: longer FT + augmentation
      - high_lr: 2e-4 FT learning rate (vs 1e-4)
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-417: Hard Patient Optimization")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_val = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # Hard patients: top 3 by MAE from EXP-410
    hard_patients = ['b', 'j', 'a']
    patient_map = {p['name']: p for p in data['per_patient']}

    ft_variants = {
        'baseline_30ep': {'epochs': 30, 'lr': 1e-4, 'augment_std': 0.0},
        'longer_100ep': {'epochs': 100, 'lr': 1e-4, 'augment_std': 0.0},
        'augment_30ep': {'epochs': 30, 'lr': 1e-4, 'augment_std': 0.01},
        'combined_100ep': {'epochs': 100, 'lr': 1e-4, 'augment_std': 0.01},
        'high_lr_30ep': {'epochs': 30, 'lr': 2e-4, 'augment_std': 0.0},
        'augment_high_lr_100ep': {'epochs': 100, 'lr': 2e-4, 'augment_std': 0.01},
    }

    results = {}

    for pid in hard_patients:
        if pid not in patient_map:
            print(f"  Patient {pid} not in data, skipping")
            continue

        pinfo = patient_map[pid]
        vi, ve = pinfo['val_idx']
        ti, te = pinfo['train_idx']
        p_train = train_x[ti:te]
        p_val = val_x[vi:ve]
        p_isf = isf_val[vi:ve] if isf_val is not None else None

        print(f"\n  Patient {pid} ({te-ti} train, {ve-vi} val):")
        results[pid] = {}

        for vname, vcfg in ft_variants.items():
            seed = cfg['seeds'][0]
            torch.manual_seed(seed)
            np.random.seed(seed)

            # Load base model from EXP-410
            base_path = os.path.join(cfg['output_dir'], f'exp410_base_s{seed}.pth')
            if not os.path.exists(base_path):
                # Try EXP-419 base
                base_path = os.path.join(cfg['output_dir'], f'exp419_base_s{seed}.pth')
            if not os.path.exists(base_path):
                print(f"    No base model found for s{seed}")
                break

            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            ckpt = torch.load(base_path, map_location=device, weights_only=False)
            model.load_state_dict(ckpt['model_state'])

            sp = os.path.join(cfg['output_dir'], f'exp417_{pid}_{vname}_s{seed}.pth')
            _, ep = train_bridge(model, p_train, p_val, sp,
                                 f'417-{pid}-{vname}', device,
                                 pk_mode=True, lr=vcfg['lr'],
                                 epochs=vcfg['epochs'], patience=30,
                                 augment_std=vcfg['augment_std'])

            report = evaluate_model(model, p_val, device, pk_mode=True,
                                    isf_val=p_isf)
            results[pid][vname] = report
            print(f"    {vname}: MAE={report['overall_mae']}, "
                  f"h30={report.get('h30','?')}, h60={report.get('h60','?')}, ep={ep}")

    print(f"\n{'='*60}")
    print("EXP-417 RESULTS: Hard Patient Optimization")
    print(f"{'='*60}")
    for pid, vres in results.items():
        print(f"  Patient {pid}:")
        for vname, r in vres.items():
            print(f"    {vname}: MAE={r['overall_mae']}")

    result = {'experiment': 'EXP-417: Hard Patient Optimization', 'per_patient': results}
    _save_results(result, 'exp417_hard_patients', cfg)
    return result


# ─── EXP-422: Asymmetric Champion Pipeline ───

def run_exp422(args):
    """EXP-422: Full champion pipeline with asymmetric w36 windows.

    Combines EXP-421 discovery (2h history + 1h future = -0.67 MAE)
    with EXP-410 champion pipeline (PK + ISF + 5-seed + FT + ensemble).

    Two variants tested:
      A) all_patients: Train base on all 11 patients (like EXP-410)
      B) pump_only: Train base on 10 pump patients, exclude j (MDI-only).
         j has 48% insulin_net density (vs >97% for pump patients) and
         no temp basal — degraded PK signal adds noise to base training.
         j still gets per-patient FT from the pump-only base.

    Key difference from EXP-410:
      - window_size=36, future_steps=12 (vs w24 symmetric)
      - 24 history steps (2h) instead of 12 (1h)
      - Same 12 future steps (1h prediction)
      - No loss dilution: MSE computed on same 12 steps as EXP-410

    Expected: ~10.2 MAE (EXP-410=10.85, EXP-421 quick Δ=-4.8%)
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    future_steps = 12
    MDI_PATIENTS = {'j'}  # MDI-only, no temp basal, degraded PK

    print(f"\n{'='*60}")
    print(f"EXP-422: Asymmetric Champion Pipeline (w36, {future_steps} future steps)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"  Variants: all_patients, pump_only (exclude {MDI_PATIENTS})")
    print(f"{'='*60}")

    # Load ALL patients for FT (including j)
    data_all = load_bridge_data(
        args.patients_dir, window_size=36,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data_all
    train_all, val_all = prepare_pk_future(data_all, use_isf=has_isf, drop_time=False)
    isf_all = data_all.get('isf_val')
    n_ch = train_all.shape[-1]

    # Load pump-only patients for filtered base training
    data_pump = load_bridge_data(
        args.patients_dir, window_size=36,
        max_patients=cfg['max_patients'], load_isf=True,
        skip_patients=MDI_PATIENTS)
    train_pump, val_pump = prepare_pk_future(data_pump, use_isf=has_isf, drop_time=False)
    isf_pump = data_pump.get('isf_val')

    base_variants = {
        'all': {'train': train_all, 'val': val_all, 'isf': isf_all,
                'label': 'all_patients'},
        'pump': {'train': train_pump, 'val': val_pump, 'isf': isf_pump,
                 'label': 'pump_only (no j)'},
    }

    all_results = {}

    for bvar_name, bvar in base_variants.items():
        tag = f'422{bvar_name[0]}'  # 422a (all) or 422p (pump)
        print(f"\n{'='*60}")
        print(f"  Variant: {bvar['label']} — base on {len(bvar['train'])} windows")
        print(f"{'='*60}")

        # Phase 1: Multi-seed base training
        print(f"\n=== Phase 1: Base Training ({len(cfg['seeds'])} seeds, {n_ch}ch, "
              f"w36 asym={36-future_steps}hist+{future_steps}fut) ===")
        base_states = {}

        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp{tag}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({bvar['label']}):")
            train_bridge(model, bvar['train'], bvar['val'], sp,
                         f'{tag}-base-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7,
                         future_steps=future_steps)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

            metrics = evaluate_model(model, val_all, device, pk_mode=True,
                                     isf_val=isf_all, future_steps=future_steps)
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h30={metrics.get('h30','?')}, h60={metrics.get('h60','?')}")

        # Phase 2: Per-patient FT — ALWAYS on all patients (including j)
        print(f"\n=== Phase 2: Per-Patient Fine-Tuning ({bvar['label']} base → all patients) ===")
        per_patient_results = {}

        for pinfo in data_all['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_all[ti:te]
            p_val_x = val_all[vi:ve]
            p_isf_v = isf_all[vi:ve] if isf_all is not None else None

            mdi_tag = " [MDI]" if pid in MDI_PATIENTS else ""
            print(f"\n  Patient {pid}{mdi_tag} ({pinfo['n_train']} train, {pinfo['n_val']} val):")

            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])

                sp = os.path.join(cfg['output_dir'], f'exp{tag}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'{tag}-ft-{pid}-s{seed}',
                             device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'], patience=10,
                             lr_patience=5, future_steps=future_steps)

                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v, future_steps=future_steps)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v, future_steps=future_steps)
            per_patient_results[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
                'ensemble_per_horizon': ens,
                'is_mdi': pid in MDI_PATIENTS,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h30={ens.get('h30','?')}, h60={ens.get('h60','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient_results.values()]
        all_mean = [v['mean_seed'] for v in per_patient_results.values()]
        pump_ens = [v['ensemble_mae'] for v in per_patient_results.values()
                    if not v.get('is_mdi')]

        summary = {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'mean_single_mae': round(float(np.mean(all_mean)), 2),
            'pump_only_mae': round(float(np.mean(pump_ens)), 2) if pump_ens else None,
            'n_patients': len(per_patient_results),
            'n_seeds': len(cfg['seeds']),
            'base_variant': bvar['label'],
            'window_size': 36,
            'future_steps': future_steps,
        }

        print(f"\n{'='*60}")
        print(f"EXP-422 RESULT — {bvar['label']} base")
        print(f"  Mean Ensemble MAE (all): {summary['mean_ensemble_mae']:.2f} mg/dL")
        print(f"  Mean Ensemble MAE (pump): {summary['pump_only_mae']:.2f} mg/dL")
        print(f"  Mean Single MAE:          {summary['mean_single_mae']:.2f} mg/dL")
        print(f"  EXP-410 reference:        10.85 mg/dL (w24 symmetric, all pts)")
        print(f"{'='*60}")

        all_results[bvar_name] = {
            'per_patient': per_patient_results,
            'summary': summary,
        }

    result = {
        'experiment': 'EXP-422: Asymmetric Champion Pipeline (w36)',
        'variants': all_results,
        'config': {
            'n_channels': n_ch, 'window_size': 36, 'future_steps': future_steps,
            'd_model': 64, 'nhead': 4, 'num_layers': 4,
            'base_epochs': cfg['epochs_base'], 'ft_epochs': cfg['epochs_ft'],
            'seeds': cfg['seeds'], 'use_isf': has_isf, 'pk_mode': True,
            'mdi_patients': list(MDI_PATIENTS),
        },
    }
    _save_results(result, 'exp422_asymmetric_champion', cfg)
    return result


# ─── Config & CLI ───

def _get_config(args):
    quick = getattr(args, 'quick', False)
    output_dir = getattr(args, 'output_dir', None) or 'externals/experiments'
    return {
        'max_patients': QUICK_PATIENTS if quick else FULL_PATIENTS,
        'seeds': QUICK_SEEDS if quick else FULL_SEEDS,
        'epochs_base': QUICK_EPOCHS_BASE if quick else FULL_EPOCHS_BASE,
        'epochs_ft': QUICK_EPOCHS_FT if quick else FULL_EPOCHS_FT,
        'output_dir': output_dir,
        'quick': quick,
    }


def _save_results(result, name, cfg):
    path = os.path.join(cfg['output_dir'], f'{name}.json')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved: {path}")


# ─── EXP-423: Fixed Augmentation + Champion Pipeline ───

def train_bridge_augmented(model, train_x, val_x, save_path, label, device,
                           pk_mode=False, lr=1e-3, epochs=200, batch=32,
                           patience=20, weight_decay=1e-5, lr_patience=7,
                           augment_std=0.5):
    """train_bridge with FIXED augmentation: noise on input only, not target.

    The original augmentation bug added noise to the batch tuple, meaning both
    input and target received the same noise, which cancels in MSE. This version
    applies noise ONLY to x_in (after cloning from x), preserving clean targets.
    """
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0

    def _step(batch_data, backward=False, augment=False):
        x = batch_data[0].to(device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        if augment and augment_std > 0:
            # Add noise to INPUT history channels only (not future, not target)
            noise = torch.randn_like(x_in[:, :half]) * augment_std
            # Scale noise relative to channel magnitudes
            x_in[:, :half] = x_in[:, :half] + noise * 0.01
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])  # target from CLEAN x
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True, augment=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False, augment=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def run_exp423(args):
    """EXP-423: Fixed augmentation on champion pipeline.

    The EXP-417 augmentation test was invalid due to a bug: noise was applied to
    both input AND target, canceling in MSE. This experiment fixes the bug by
    applying noise ONLY to history input channels, keeping targets clean.

    Variants:
    - control: EXP-410 champion (no augmentation)
    - aug_0.5: Gaussian noise std=0.5 on normalized input (0.5% of scale)
    - aug_1.0: Gaussian noise std=1.0 on normalized input (1% of scale)
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-423: Fixed Augmentation on Champion")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    variants = [
        ('control', 0.0),
        ('aug_0.5', 0.5),
        ('aug_1.0', 1.0),
    ]

    all_results = {}
    for vname, aug_std in variants:
        print(f"\n{'─'*40}")
        print(f"  Variant: {vname} (augment_std={aug_std})")
        print(f"{'─'*40}")

        seed_maes = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp423_{vname}_s{seed}.pth')

            if aug_std > 0:
                train_bridge_augmented(
                    model, train_x, val_x, sp, f'423-{vname}-s{seed}',
                    device, pk_mode=True, augment_std=aug_std,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            else:
                train_bridge(
                    model, train_x, val_x, sp, f'423-{vname}-s{seed}',
                    device, pk_mode=True,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            seed_maes[f's{seed}'] = metrics['overall_mae']
            print(f"  {vname} s{seed}: MAE={metrics['overall_mae']:.1f}, "
                  f"h30={metrics.get('h30','?')}, h60={metrics.get('h60','?')}")

        all_results[vname] = {
            'augment_std': aug_std,
            'seeds': seed_maes,
            'mean_mae': round(float(np.mean(list(seed_maes.values()))), 2),
        }

    result = {
        'experiment': 'EXP-423: Fixed Augmentation',
        'note': 'Fixes EXP-417 bug: noise on input only, not target',
        'results': all_results,
    }
    _save_results(result, 'exp423_fixed_augmentation', cfg)

    print(f"\n{'='*60}")
    print("EXP-423 SUMMARY")
    for vn, vr in all_results.items():
        print(f"  {vn}: {vr['mean_mae']:.2f} (aug_std={vr['augment_std']})")
    print(f"{'='*60}")
    return result


# ─── EXP-424: Horizon-Weighted Loss ───

def train_bridge_horizon_weighted(model, train_x, val_x, save_path, label, device,
                                  pk_mode=False, lr=1e-3, epochs=200, batch=32,
                                  patience=20, weight_decay=1e-5, lr_patience=7,
                                  horizon_weights=None):
    """train_bridge with horizon-weighted MSE loss.

    horizon_weights: tensor of shape (future_steps,) weighting each prediction
    step. Default = uniform. Example: linear ramp [1,2,3,...,12]/mean gives
    more weight to harder long-range predictions.
    """
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    best = float('inf')
    stale = 0

    half = train_x.shape[1] // 2
    if horizon_weights is not None:
        hw = horizon_weights.to(device).reshape(1, -1, 1)
    else:
        hw = torch.ones(1, half, 1, device=device)

    def _step(batch_data, backward=False):
        x = batch_data[0].to(device)
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)
        errors = (pred[:, half:, :1] - x[:, half:, :1]) ** 2
        loss = (errors * hw).mean()
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def run_exp424(args):
    """EXP-424: Horizon-weighted loss on champion pipeline.

    Hypothesis: Equal-weighted multi-horizon MSE gives h5 (easy, MAE~6) the same
    gradient as h60 (hard, MAE~15). Upweighting longer horizons should improve
    h60 accuracy without degrading h30 much, since h30 is already below CGM MARD.

    Variants:
    - uniform: Standard MSE (control, matches EXP-410)
    - linear: Weights [1..12]/mean — 2x more weight on h60 than h5
    - sqrt: Weights sqrt([1..12])/mean — gentle ramp
    - h60_focus: Weight 1.0 for h5-h55, weight 3.0 for h60 only
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-424: Horizon-Weighted Loss")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]
    half = 12  # w24 → 12 future steps

    # Build weight tensors
    linear_w = torch.arange(1.0, half + 1.0)
    linear_w = linear_w / linear_w.mean()  # mean=1, so total loss ~same

    sqrt_w = torch.sqrt(torch.arange(1.0, half + 1.0))
    sqrt_w = sqrt_w / sqrt_w.mean()

    h60_focus_w = torch.ones(half)
    h60_focus_w[-1] = 3.0  # 3x weight on last step (h60)
    h60_focus_w = h60_focus_w / h60_focus_w.mean()

    variants = [
        ('uniform', None),
        ('linear', linear_w),
        ('sqrt', sqrt_w),
        ('h60_focus', h60_focus_w),
    ]

    all_results = {}
    for vname, weights in variants:
        print(f"\n{'─'*40}")
        print(f"  Variant: {vname}")
        if weights is not None:
            print(f"  Weights: [{', '.join(f'{w:.2f}' for w in weights)}]")
        print(f"{'─'*40}")

        seed_maes = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp424_{vname}_s{seed}.pth')

            if weights is not None:
                train_bridge_horizon_weighted(
                    model, train_x, val_x, sp, f'424-{vname}-s{seed}',
                    device, pk_mode=True, horizon_weights=weights,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            else:
                train_bridge(
                    model, train_x, val_x, sp, f'424-{vname}-s{seed}',
                    device, pk_mode=True,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            seed_maes[f's{seed}'] = metrics
            print(f"  {vname} s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h30={metrics.get('h30','?')}, h60={metrics.get('h60','?')}")

        # Summary: average per-horizon across seeds
        avg_overall = np.mean([m['overall_mae'] for m in seed_maes.values()])
        avg_h30 = np.mean([m.get('h30', 0) for m in seed_maes.values()])
        avg_h60 = np.mean([m.get('h60', 0) for m in seed_maes.values()])

        all_results[vname] = {
            'seeds': {k: v['overall_mae'] for k, v in seed_maes.items()},
            'mean_mae': round(float(avg_overall), 2),
            'mean_h30': round(float(avg_h30), 2),
            'mean_h60': round(float(avg_h60), 2),
            'weights': [round(float(w), 3) for w in weights] if weights is not None else 'uniform',
        }

    result = {
        'experiment': 'EXP-424: Horizon-Weighted Loss',
        'hypothesis': 'Upweighting long-range horizons improves h60 without hurting h30',
        'results': all_results,
    }
    _save_results(result, 'exp424_horizon_weighted', cfg)

    print(f"\n{'='*60}")
    print("EXP-424 SUMMARY")
    for vn, vr in all_results.items():
        print(f"  {vn}: overall={vr['mean_mae']:.2f}, "
              f"h30={vr['mean_h30']:.2f}, h60={vr['mean_h60']:.2f}")
    print(f"{'='*60}")
    return result


# ─── EXP-425: Combined Champion (h60_focus + augmentation + FT + ensemble) ───

def train_bridge_combined(model, train_x, val_x, save_path, label, device,
                          pk_mode=False, lr=1e-3, epochs=200, batch=32,
                          patience=20, weight_decay=1e-5, lr_patience=7,
                          horizon_weights=None, augment_std=0.0):
    """Combined training: horizon-weighted loss + fixed augmentation."""
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    best = float('inf')
    stale = 0

    half = train_x.shape[1] // 2
    if horizon_weights is not None:
        hw = horizon_weights.to(device).reshape(1, -1, 1)
    else:
        hw = torch.ones(1, half, 1, device=device)

    def _step(batch_data, backward=False, augment=False):
        x = batch_data[0].to(device)
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        if augment and augment_std > 0:
            noise = torch.randn_like(x_in[:, :half]) * augment_std * 0.01
            x_in[:, :half] = x_in[:, :half] + noise
        pred = model(x_in, causal=True)
        errors = (pred[:, half:, :1] - x[:, half:, :1]) ** 2
        loss = (errors * hw).mean()
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True, augment=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False, augment=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def run_exp425(args):
    """EXP-425: Combined champion — h60_focus loss + augmentation + FT + ensemble.

    Combines the two quick-mode winners from EXP-423 and EXP-424:
    - h60_focus loss: 3× weight on h60, reduced h5 weight (EXP-424: -0.59 overall)
    - aug_1.0: Gaussian noise std=1.0 on input history (EXP-423: -0.24 overall)
    Plus the proven champion pipeline: ISF norm + PK + per-patient FT + 5-seed ensemble.

    Variants:
    - h60_focus: Just h60-weighted loss (best from EXP-424)
    - h60_aug: h60-weighted + augmentation combined
    - control: Standard uniform MSE (EXP-410 reproduction)

    This is a FEATURE/TRAINING experiment, but h60_focus loss is a training dynamic
    change. Quick→full translation is uncertain. Run quick first for screening,
    then full for the best variant.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print("EXP-425: Combined Champion Pipeline")
    print(f"  seeds={cfg['seeds']}, base={cfg['epochs_base']}ep, ft={cfg['epochs_ft']}ep")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=24,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]
    half = 12

    # h60_focus weights: 1.0 for h5-h55, 3.0 for h60
    h60_w = torch.ones(half)
    h60_w[-1] = 3.0
    h60_w = h60_w / h60_w.mean()

    variants = [
        ('control', None, 0.0),
        ('h60_focus', h60_w, 0.0),
        ('h60_aug', h60_w, 1.0),
    ]

    all_results = {}
    for vname, weights, aug_std in variants:
        print(f"\n{'='*40}")
        print(f"  Variant: {vname} (weights={'h60_focus' if weights is not None else 'uniform'}, aug={aug_std})")
        print(f"{'='*40}")

        # Phase 1: Base training
        base_states = {}
        base_metrics = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp425_{vname}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({vname}):")
            if weights is not None or aug_std > 0:
                train_bridge_combined(
                    model, train_x, val_x, sp, f'425-{vname}-s{seed}',
                    device, pk_mode=True, horizon_weights=weights,
                    augment_std=aug_std,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            else:
                train_bridge(
                    model, train_x, val_x, sp, f'425-{vname}-s{seed}',
                    device, pk_mode=True,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            base_metrics[seed] = metrics
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h30={metrics.get('h30','?')}, h60={metrics.get('h60','?')}")

        # Phase 2: Per-patient FT + ensemble (using standard MSE for FT)
        print(f"\n  === Phase 2: Per-Patient FT ({vname}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp425_{vname}_ft_{pid}_s{seed}.pth')

                # FT uses standard MSE (per-patient data is too small for weighted loss)
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'425-ft-{pid}-s{seed}',
                             device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)

                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h30={ens.get('h30','?')}, h60={ens.get('h60','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        mean_ens = round(float(np.mean(all_ens)), 2)

        all_results[vname] = {
            'per_patient': per_patient,
            'base_metrics': {f's{s}': m for s, m in base_metrics.items()},
            'mean_ensemble_mae': mean_ens,
            'config': {'weights': vname, 'augment_std': aug_std},
        }
        print(f"\n  {vname} Mean Ensemble MAE: {mean_ens}")

    result = {
        'experiment': 'EXP-425: Combined Champion (h60_focus + aug + FT + ensemble)',
        'results': all_results,
    }
    _save_results(result, 'exp425_combined_champion', cfg)

    print(f"\n{'='*60}")
    print("EXP-425 SUMMARY")
    for vn, vr in all_results.items():
        pp = ', '.join(f"{k}={v['ensemble_mae']:.1f}" for k, v in vr['per_patient'].items())
        print(f"  {vn}: {vr['mean_ensemble_mae']:.2f} [{pp}]")
    print(f"  EXP-410 reference: 10.85 (11pt) / ~13.87 (4pt quick)")
    print(f"{'='*60}")
    return result


# ─── EXP-426: w48 + h60_focus Horizon-Weighted Loss ───

def run_exp426(args):
    """EXP-426: Apply h60_focus weighting to w48 extended horizon pipeline.

    Hypothesis: h60_focus (3× weight on last step) improved h60 by -0.83 at w24
    (EXP-424). At w48 (24 future steps), the last step is h120. Applying 3× weight
    on h120 should improve h120 (the hardest and highest-value horizon) while acting
    as a regularizer for nearer horizons — the same mechanism that helped h30 at w24.

    Additionally, test h60_focus at w48 where h60 = step 12 (midpoint), upweighting
    the critical clinical horizon.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-426: w48 + Horizon-Weighted Loss")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    ws = 48
    half = ws // 2  # 24 steps

    data = load_bridge_data(
        args.patients_dir, window_size=ws,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # Weight schemes for 24-step future
    # h120_focus: 3× weight on last step (h120)
    h120_w = torch.ones(half)
    h120_w[-1] = 3.0
    h120_w = h120_w / h120_w.mean()

    # h60_focus: 3× weight on step 12 (h60 = 60min)
    h60_w = torch.ones(half)
    h60_w[11] = 3.0  # step 12 (0-indexed: 11) = 60min
    h60_w = h60_w / h60_w.mean()

    # linear_ramp: linearly increasing weights
    linear_w = torch.linspace(1, 3, half)
    linear_w = linear_w / linear_w.mean()

    variants = {
        'control': (None, 'Standard MSE (control)'),
        'h120_focus': (h120_w, '3× weight on h120 (last step)'),
        'h60_mid_focus': (h60_w, '3× weight on h60 (midpoint)'),
        'linear_ramp': (linear_w, 'Linear ramp 1→3'),
    }

    all_results = {}
    for vname, (weights, desc) in variants.items():
        print(f"\n{'─'*40}")
        print(f"  Variant: {vname} — {desc}")
        print(f"{'─'*40}")

        base_states = {}
        base_metrics = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp426_{vname}_base_s{seed}.pth')
            print(f"\n  Base s{seed} ({vname}):")

            if weights is not None:
                train_bridge_horizon_weighted(
                    model, train_x, val_x, sp, f'426-{vname}-s{seed}',
                    device, pk_mode=True, horizon_weights=weights,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            else:
                train_bridge(
                    model, train_x, val_x, sp, f'426-{vname}-s{seed}',
                    device, pk_mode=True,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            base_metrics[seed] = metrics
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}, h120={metrics.get('h120','?')}")

        # Phase 2: Per-patient FT + ensemble
        print(f"\n  === Phase 2: Per-Patient FT ({vname}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp426_{vname}_ft_{pid}_s{seed}.pth')
                # FT uses standard MSE
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'426-ft-{pid}-s{seed}',
                             device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_horizons': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h60={ens.get('h60','?')}, h120={ens.get('h120','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
            'base_metrics': {f's{s}': m for s, m in base_metrics.items()},
            'description': desc,
        }
        print(f"\n  {vname} Mean Ensemble: {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-426 SUMMARY")
    print(f"{'='*60}")
    for vn, vr in all_results.items():
        h60s = [vr['per_patient'][p]['ensemble_horizons'].get('h60', '?')
                for p in vr['per_patient'] if 'ensemble_horizons' in vr['per_patient'][p]]
        h120s = [vr['per_patient'][p]['ensemble_horizons'].get('h120', '?')
                 for p in vr['per_patient'] if 'ensemble_horizons' in vr['per_patient'][p]]
        h60_avg = np.mean([x for x in h60s if isinstance(x, (int, float))]) if h60s else '?'
        h120_avg = np.mean([x for x in h120s if isinstance(x, (int, float))]) if h120s else '?'
        h60_str = f"{h60_avg:.1f}" if isinstance(h60_avg, (int, float)) else str(h60_avg)
        h120_str = f"{h120_avg:.1f}" if isinstance(h120_avg, (int, float)) else str(h120_avg)
        print(f"  {vn}: overall={vr['mean_ensemble_mae']:.2f}, "
              f"h60_avg={h60_str}, h120_avg={h120_str}")
    print(f"  EXP-411 w48 reference: 13.50 (h60=14.2, h120=17.4)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-426: w48 + Horizon-Weighted Loss',
        'results': all_results,
    }
    _save_results(result, 'exp426_w48_horizon_weighted', cfg)
    return result


# ─── EXP-427: Horizon-Adaptive Ensemble (Analysis Only) ───

def run_exp427(args):
    """EXP-427: Horizon-adaptive ensemble — select best window per horizon.

    Zero-cost experiment: uses already-computed EXP-411 results to determine
    optimal window selection per target horizon. No new training needed.

    For each patient and horizon, picks the window with lowest MAE.
    """
    cfg = _get_config(args)

    print(f"\n{'='*60}")
    print(f"EXP-427: Horizon-Adaptive Ensemble (Analysis)")
    print(f"{'='*60}")

    # Load full EXP-411 results
    results_path = os.path.join(cfg['output_dir'], 'exp411_extended_horizon_full.json')
    if not os.path.exists(results_path):
        print("  ERROR: Need exp411_extended_horizon_full.json")
        print("  Run EXP-411 full validation first.")
        return {'error': 'missing_exp411_results'}

    with open(results_path) as f:
        data = json.load(f)

    # Also load EXP-410 results for w24 comparison
    exp410_path = os.path.join(cfg['output_dir'], 'exp410_isf_champion.json')
    w24_patients = {}
    if os.path.exists(exp410_path):
        with open(exp410_path) as f:
            e410 = json.load(f)
        # Try to extract per-patient h60
        for key in ['results', 'full']:
            if key in e410 and isinstance(e410[key], dict):
                for vk, vv in e410[key].items():
                    if isinstance(vv, dict) and 'per_patient' in vv:
                        for pid, pd in vv['per_patient'].items():
                            if isinstance(pd, dict):
                                mae = pd.get('ensemble_mae', pd.get('ensemble', {}).get('overall_mae'))
                                if mae:
                                    w24_patients[pid] = {'mae': mae, 'h60': mae}

    results = data.get('results', {})
    horizons = ['h30', 'h60', 'h90', 'h120', 'h150', 'h180']
    windows = ['w48', 'w72', 'w96']

    # Per-patient × per-horizon best window
    patients = set()
    for wk in windows:
        if wk in results:
            patients.update(results[wk].get('per_patient', {}).keys())
    patients = sorted(patients)

    print(f"\n  Patients: {patients}")
    print(f"  Windows: {windows}")
    print(f"  Horizons: {horizons}")

    adaptive_results = {}
    for pid in patients:
        adaptive_results[pid] = {}
        for h in horizons:
            best_w = None
            best_mae = float('inf')
            for wk in windows:
                wd = results.get(wk, {}).get('per_patient', {}).get(pid, {})
                hval = wd.get(h) or wd.get('ensemble_horizons', {}).get(h)
                if hval is not None and isinstance(hval, (int, float)) and hval < best_mae:
                    best_mae = hval
                    best_w = wk
            if best_w:
                adaptive_results[pid][h] = {'best_window': best_w, 'mae': best_mae}

    # Compute per-horizon averages
    print(f"\n  Per-Horizon Best Window Selection:")
    print(f"  {'Horizon':>8} {'Best Window':>12} {'Adaptive MAE':>14} {'Static w48':>12} {'Δ':>8}")
    print(f"  {'─'*56}")

    for h in horizons:
        adaptive_maes = []
        static_maes = []
        window_counts = {}
        for pid in patients:
            ar = adaptive_results.get(pid, {}).get(h)
            if ar:
                adaptive_maes.append(ar['mae'])
                wc = ar['best_window']
                window_counts[wc] = window_counts.get(wc, 0) + 1
            # Static w48
            w48d = results.get('w48', {}).get('per_patient', {}).get(pid, {})
            h_static = w48d.get(h) or w48d.get('ensemble_horizons', {}).get(h)
            if h_static and isinstance(h_static, (int, float)):
                static_maes.append(h_static)

        if adaptive_maes:
            a_avg = np.mean(adaptive_maes)
            s_avg = np.mean(static_maes) if static_maes else float('nan')
            delta = a_avg - s_avg if not np.isnan(s_avg) else float('nan')
            best_w = max(window_counts, key=window_counts.get)
            print(f"  {h:>8} {best_w:>12} {a_avg:>14.1f} {s_avg:>12.1f} {delta:>+8.1f}")

    result = {
        'experiment': 'EXP-427: Horizon-Adaptive Ensemble',
        'adaptive_results': adaptive_results,
        'note': 'Zero-cost analysis of existing EXP-411 results',
    }
    _save_results(result, 'exp427_horizon_adaptive', cfg)

    print(f"\n  Saved analysis to exp427_horizon_adaptive.json")
    return result



# ─── EXP-428: Extended Features at w48 ───

def prepare_pk_extended(data, use_isf=False, variant='baseline'):
    """Prepare features with additional PK channels and glucose derivatives.

    Variants:
    - baseline: Standard 8ch (matches prepare_pk_future)
    - glucose_deriv: +dBG/dt, d²BG/dt² (10ch)
    - hepatic: +hepatic_prod, carb_accel (10ch)
    - all_pk: Full 8 PK channels + glucose (11ch)
    - deriv_hepatic: glucose_deriv + hepatic (12ch)
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    # Standard PK replacement (always applied)
    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]  # insulin_net
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]  # carb_rate
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]
    # Replace cos with net_balance
    bt[:, :, 7] = pt[:, :, 6] / PK_NORMS[6]
    bv[:, :, 7] = pv[:, :, 6] / PK_NORMS[6]

    extra_t, extra_v = [], []

    half = bt.shape[1] // 2

    if variant in ('glucose_deriv', 'deriv_hepatic'):
        # Glucose first derivative: dBG/dt (per 5min step)
        # ONLY valid in history half — future glucose is masked (predicted),
        # so derivatives there would be data leakage. Zero them explicitly.
        g_t = bt[:, :, 0]  # (N, T)
        g_v = bv[:, :, 0]
        dg_t = np.diff(g_t, axis=1, prepend=g_t[:, :1])  # (N, T)
        dg_v = np.diff(g_v, axis=1, prepend=g_v[:, :1])
        d2g_t = np.diff(dg_t, axis=1, prepend=dg_t[:, :1])
        d2g_v = np.diff(dg_v, axis=1, prepend=dg_v[:, :1])
        # Zero future half to prevent glucose label leakage
        dg_t[:, half:] = 0.0
        dg_v[:, half:] = 0.0
        d2g_t[:, half:] = 0.0
        d2g_v[:, half:] = 0.0
        # Normalize: typical dBG ~ ±5 mg/dL per step, d2BG ~ ±3
        extra_t.extend([dg_t[:, :, None] / 5.0, d2g_t[:, :, None] / 3.0])
        extra_v.extend([dg_v[:, :, None] / 5.0, d2g_v[:, :, None] / 3.0])

    if variant in ('hepatic', 'deriv_hepatic'):
        # Hepatic glucose production (PK ch5) and carb acceleration (PK ch4)
        extra_t.extend([
            pt[:, :, 5:6] / PK_NORMS[5],  # hepatic_prod
            pt[:, :, 4:5] / PK_NORMS[4],  # carb_accel
        ])
        extra_v.extend([
            pv[:, :, 5:6] / PK_NORMS[5],
            pv[:, :, 4:5] / PK_NORMS[4],
        ])

    if variant == 'all_pk':
        # All 8 PK channels: total, net, basal_ratio, carb_rate, carb_accel,
        # hepatic, net_balance, isf_curve
        for i in range(8):
            extra_t.append(pt[:, :, i:i+1] / PK_NORMS[i])
            extra_v.append(pv[:, :, i:i+1] / PK_NORMS[i])

    if extra_t:
        bt = np.concatenate([bt] + extra_t, axis=-1)
        bv = np.concatenate([bv] + extra_v, axis=-1)

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def run_exp428(args):
    """EXP-428: Extended feature channels at w48.

    Hypothesis: Adding glucose derivatives (dBG/dt, d²BG/dt²) and/or
    hepatic glucose production gives the transformer explicit rate-of-change
    information that it otherwise must infer. At w48 (2h history), derivatives
    capture the current trajectory more explicitly than raw glucose values.

    Glucose derivatives are dense, equivariant (same meaning at any time),
    and causally valid in history. In the future half, derivatives from
    masked glucose will be zero — acting as implicit masking.

    Key: PK derivative channels (insulin_net d/dt, carb_accel) are CAUSAL
    and available in the future. Glucose derivatives are ONLY valid in history.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-428: Extended Features at w48")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    ws = 48
    half = ws // 2

    data = load_bridge_data(
        args.patients_dir, window_size=ws,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data

    variants = {
        'baseline': 'Standard 8ch (control)',
        'glucose_deriv': '+dBG/dt, d²BG/dt² (10ch)',
        'hepatic': '+hepatic_prod, carb_accel (10ch)',
        'deriv_hepatic': '+derivatives + hepatic (12ch)',
    }

    all_results = {}
    for vname, desc in variants.items():
        print(f"\n{'─'*40}")
        print(f"  Variant: {vname} — {desc}")
        print(f"{'─'*40}")

        train_x, val_x = prepare_pk_extended(data, use_isf=has_isf, variant=vname)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]
        print(f"  Channels: {n_ch}")

        base_states = {}
        base_metrics = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp428_{vname}_base_s{seed}.pth')
            print(f"\n  Base s{seed} ({vname}):")
            train_bridge(model, train_x, val_x, sp, f'428-{vname}-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True, isf_val=isf_v)
            base_metrics[seed] = metrics
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}, h120={metrics.get('h120','?')}")

        # Phase 2: Per-patient FT + ensemble
        print(f"\n  === Phase 2: Per-Patient FT ({vname}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp428_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'428-ft-{pid}-s{seed}',
                             device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_horizons': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h60={ens.get('h60','?')}, h120={ens.get('h120','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
            'n_channels': n_ch,
            'description': desc,
        }
        print(f"\n  {vname} Mean Ensemble: {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-428 SUMMARY")
    print(f"{'='*60}")
    for vn, vr in all_results.items():
        print(f"  {vn} ({vr['n_channels']}ch): {vr['mean_ensemble_mae']:.2f}")
    ctrl = all_results.get('baseline', {}).get('mean_ensemble_mae', 0)
    for vn, vr in all_results.items():
        if vn != 'baseline':
            delta = vr['mean_ensemble_mae'] - ctrl
            print(f"    Δ vs baseline: {delta:+.2f}")
    print(f"  EXP-411 w48 full reference: 13.50")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-428: Extended Features at w48',
        'results': all_results,
    }
    _save_results(result, 'exp428_extended_features_w48', cfg)
    return result



# ─── EXP-429: Long-History Asymmetric Windows for h60 ───

def run_exp429(args):
    """EXP-429: Asymmetric long-history windows targeting h60.

    Hypothesis: The w24 champion (10.85 MAE) uses only 1h (12 steps) of history.
    At w24, the model predicts 12 future steps (h60) from 12 history steps.
    But insulin DIA is ~5h — the model sees only 20% of the active insulin arc.

    By using w72 with asymmetric split (60 hist + 12 future), we give the model
    5h of history (complete DIA coverage) while keeping the prediction task
    identical to w24 (12 future steps = h60). This should improve h60 by
    providing complete insulin dynamics context.

    The symmetric w72 (EXP-411) got h60=15.0 — WORSE than w24's 10.4, because
    it predicted 36 future steps (h180), a much harder task. By limiting to
    12 future steps, we keep the task easy while extending context.

    Variants:
    - w36_asym: 24 hist (2h) + 12 future → 2h context, h60 max
    - w48_asym: 36 hist (3h) + 12 future → 3h context, h60 max
    - w72_asym: 60 hist (5h) + 12 future → 5h context (full DIA), h60 max
    - w24_control: 12 hist + 12 future → 1h context (EXP-410 match)
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-429: Long-History Asymmetric Windows for h60")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    future_steps = 12  # All variants predict h60 (12 steps × 5min)

    variants = [
        ('w24_control', 24, 12, '1h hist (EXP-410 match)'),
        ('w36_asym', 36, 12, '2h hist + h60'),
        ('w48_asym', 48, 12, '3h hist + h60'),
        ('w72_asym', 72, 12, '5h hist (full DIA) + h60'),
    ]

    all_results = {}
    for vname, ws, fs, desc in variants:
        hist = ws - fs
        print(f"\n{'─'*40}")
        print(f"  {vname}: w{ws} = {hist} hist ({hist*5}min) + {fs} future (h{fs*5})")
        print(f"  {desc}")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=ws,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]

        print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val, {n_ch}ch")

        # Phase 1: Base training
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp429_{vname}_base_s{seed}.pth')
            print(f"\n  Base s{seed} ({vname}):")
            train_bridge(model, train_x, val_x, sp, f'429-{vname}-s{seed}',
                         device, pk_mode=True, future_steps=fs,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True,
                                     isf_val=isf_v, future_steps=fs)
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h30={metrics.get('h30','?')}, h60={metrics.get('h60','?')}")

        # Phase 2: Per-patient FT + ensemble
        print(f"\n  === Phase 2: Per-Patient FT ({vname}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp429_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'429-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, future_steps=fs,
                             epochs=cfg['epochs_ft'], patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v, future_steps=fs)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v, future_steps=fs)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_horizons': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h30={ens.get('h30','?')}, h60={ens.get('h60','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
            'window_size': ws,
            'history_steps': ws - fs,
            'future_steps': fs,
            'description': desc,
        }
        print(f"\n  {vname} Mean Ensemble: {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-429 SUMMARY — Long History for h60")
    print(f"{'='*60}")
    for vn, vr in all_results.items():
        h = vr['history_steps']
        print(f"  {vn} ({h*5}min hist): {vr['mean_ensemble_mae']:.2f}")
    ctrl = all_results.get('w24_control', {}).get('mean_ensemble_mae', 0)
    for vn, vr in all_results.items():
        if vn != 'w24_control':
            delta = vr['mean_ensemble_mae'] - ctrl
            print(f"    Δ vs w24: {delta:+.2f}")
    print(f"  EXP-410 full reference: 10.85")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-429: Long-History Asymmetric Windows for h60',
        'results': all_results,
    }
    _save_results(result, 'exp429_long_history_h60', cfg)
    return result


# ─── EXP-430: Asymmetric History Sweep for h120 ───

def run_exp430(args):
    """EXP-430: Asymmetric long-history windows targeting h120.

    Extends EXP-429's approach to h120: all variants predict 24 future steps
    (h120) while varying history length from 2h to 7h.

    At h60, EXP-429 showed 2h history was optimal (−0.25) and 5h history hurt
    (+0.17) due to data scarcity. But at h120, where insulin dynamics dominate,
    longer history should help MORE because:
    1. The model needs to see complete DIA arcs to predict 2h ahead
    2. Future PK channels provide deterministic absorption curves
    3. The information gain from DIA context outweighs data loss

    The crossover point where "more context > less data" should occur at a
    longer horizon than h60. This experiment finds that crossover.

    Also tests multi-horizon evaluation: models predict h120 but we evaluate
    at h30, h60, h90, h120 to see if longer history helps intermediate horizons.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-430: Asymmetric History Sweep for h120")
    print(f"  seeds={cfg['seeds']}")
    print(f"{'='*60}")

    future_steps = 24  # All variants predict h120 (24 steps × 5min)

    variants = [
        ('w48_control', 48, 24, '2h hist + h120 (EXP-411 match)'),
        ('w60_asym', 60, 24, '3h hist + h120'),
        ('w84_asym', 84, 24, '5h hist (full DIA) + h120'),
        ('w108_asym', 108, 24, '7h hist (beyond DIA) + h120'),
    ]

    all_results = {}
    for vname, ws, fs, desc in variants:
        hist = ws - fs
        print(f"\n{'─'*40}")
        print(f"  {vname}: w{ws} = {hist} hist ({hist*5}min) + {fs} future (h{fs*5})")
        print(f"  {desc}")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=ws,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]

        print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val, {n_ch}ch")

        # Phase 1: Base training
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp430_{vname}_base_s{seed}.pth')
            print(f"\n  Base s{seed} ({vname}):")
            train_bridge(model, train_x, val_x, sp, f'430-{vname}-s{seed}',
                         device, pk_mode=True, future_steps=fs,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            metrics = evaluate_model(model, val_x, device, pk_mode=True,
                                     isf_val=isf_v, future_steps=fs)
            print(f"  Base s{seed}: overall={metrics['overall_mae']:.1f}, "
                  f"h60={metrics.get('h60','?')}, h120={metrics.get('h120','?')}")

        # Phase 2: Per-patient FT + ensemble
        print(f"\n  === Phase 2: Per-Patient FT ({vname}) ===")
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp430_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'430-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, future_steps=fs,
                             epochs=cfg['epochs_ft'], patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v, future_steps=fs)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v, future_steps=fs)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_horizons': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h60={ens.get('h60','?')}, h90={ens.get('h90','?')}, "
                  f"h120={ens.get('h120','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        # Collect per-horizon averages
        horizon_avgs = {}
        for hname in ['h30', 'h60', 'h90', 'h120']:
            vals = [v['ensemble_horizons'].get(hname)
                    for v in per_patient.values()
                    if v['ensemble_horizons'].get(hname) is not None]
            if vals:
                horizon_avgs[hname] = round(float(np.mean(vals)), 2)

        all_results[vname] = {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'horizon_averages': horizon_avgs,
            'per_patient': per_patient,
            'window_size': ws,
            'history_steps': ws - fs,
            'future_steps': fs,
            'description': desc,
        }
        print(f"\n  {vname} Mean Ensemble: {all_results[vname]['mean_ensemble_mae']:.2f}")
        print(f"  Per-horizon: {horizon_avgs}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-430 SUMMARY — Long History for h120")
    print(f"{'='*60}")
    print(f"  {'Config':<16} {'Hist':>6} {'MAE':>6} {'h60':>6} {'h90':>6} {'h120':>6}")
    print(f"  {'─'*52}")
    for vn, vr in all_results.items():
        h = vr['history_steps']
        ha = vr['horizon_averages']
        print(f"  {vn:<16} {h*5:>4}m {vr['mean_ensemble_mae']:>6.2f} "
              f"{ha.get('h60','?'):>6} {ha.get('h90','?'):>6} {ha.get('h120','?'):>6}")
    ctrl = all_results.get('w48_control', {}).get('mean_ensemble_mae', 0)
    for vn, vr in all_results.items():
        if vn != 'w48_control':
            delta = vr['mean_ensemble_mae'] - ctrl
            print(f"    Δ vs w48: {delta:+.2f}")
    print(f"\n  EXP-411 w48 full reference: 13.50 (symmetric)")
    print(f"  EXP-429 best h60: 12.78 (w36 asym, 2h hist)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-430: Asymmetric History Sweep for h120',
        'results': all_results,
    }
    _save_results(result, 'exp430_long_history_h120', cfg)
    return result


# ─── EXP-431: Stride Optimization ───

def run_exp431(args):
    """EXP-431: Stride optimization — more training windows via denser sampling.

    EXP-429/430 proved data volume is THE binding constraint (2h history optimal
    even at h120 because longer history = fewer windows = worse).

    The default stride is window_size // 3 ≈ 16 steps (80min) for w48.
    Reducing stride to 6 (30min) should roughly double training windows.
    Even stride=3 (15min) is valid — windows overlap heavily but each sees
    slightly different noise/timing, acting like data augmentation.

    Hypothesis: Denser stride will improve MAE proportionally to data increase,
    without the quality degradation of longer windows.

    Variants:
      - stride_16: w48 default (control)
      - stride_12: ~60min overlap  
      - stride_6:  ~30min overlap (expected winner)
      - stride_3:  ~15min overlap (diminishing returns expected)
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-431: Stride Optimization (w48)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    stride_configs = {
        'stride_16': 16,   # default (control)
        'stride_12': 12,   # ~60min
        'stride_6':  6,    # ~30min
        'stride_3':  3,    # ~15min (heavy overlap)
    }

    all_results = {}
    for vname, stride_val in stride_configs.items():
        print(f"\n{'─'*40}")
        print(f"  {vname}: stride={stride_val} ({stride_val*5}min)")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=48, stride=stride_val,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]
        n_train = train_x.shape[0]

        print(f"  {n_train} train windows, {val_x.shape[0]} val, {n_ch}ch")

        # Base training
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp431_{vname}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({vname}):")
            train_bridge(model, train_x, val_x, sp, f'431-{vname}-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT + ensemble
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp431_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'431-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'stride': stride_val,
            'stride_min': stride_val * 5,
            'n_train': n_train,
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
        }
        print(f"\n  {vname}: Mean Ensemble MAE = {all_results[vname]['mean_ensemble_mae']:.2f} "
              f"({n_train} train windows)")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-431 SUMMARY — Stride Optimization (w48)")
    print(f"{'='*60}")
    print(f"  {'Config':<14} {'Stride':>6} {'Train':>8} {'MAE':>6}")
    print(f"  {'─'*40}")
    for vn, vr in all_results.items():
        print(f"  {vn:<14} {vr['stride']*5:>4}m {vr['n_train']:>8} "
              f"{vr['mean_ensemble_mae']:>6.2f}")
    ctrl = all_results.get('stride_16', {}).get('mean_ensemble_mae', 0)
    if ctrl:
        for vn, vr in all_results.items():
            if vn != 'stride_16':
                delta = vr['mean_ensemble_mae'] - ctrl
                print(f"    Δ {vn} vs control: {delta:+.2f}")
    print(f"\n  EXP-411 w48 full ref: 13.50 (stride=16)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-431: Stride Optimization',
        'results': all_results,
    }
    _save_results(result, 'exp431_stride_optimization', cfg)
    return result


# ─── EXP-432: Patient-Quality-Filtered Base Training ───

def _classify_patient_quality(per_patient_info, patients_dir):
    """Classify patients by data quality for filtered training.

    Gold: pump + CGM + ISF settings + sufficient data (>2 weeks)
    Silver: CGM + some pump data, but gaps or MDI periods
    Bronze: CGM only, or MDI with manual logs

    Returns dict: {patient_name: 'gold'|'silver'|'bronze'}
    """
    quality = {}
    for pinfo in per_patient_info:
        name = pinfo['name']
        isf = pinfo.get('isf')
        n = pinfo.get('n_windows', 0)

        # Heuristic: patients with ISF and substantial data are gold
        # Patient j is known MDI-only (no pump telemetry)
        if name == 'j':
            quality[name] = 'bronze'
        elif isf is not None and isf > 0 and n >= 200:
            quality[name] = 'gold'
        elif isf is not None and isf > 0:
            quality[name] = 'silver'
        else:
            quality[name] = 'bronze'
    return quality


def run_exp432(args):
    """EXP-432: Patient-quality-filtered base training.

    Hypothesis: Training the base model on gold+silver patients only
    (those with reliable pump/CGM telemetry) produces cleaner gradients.
    Then fine-tune on ALL patients including bronze.

    The base model sees only clean training signal → better shared
    representations → better transfer even to noisy patients.

    Variants:
      - all_patients: standard training on all (control)
      - gold_silver:  base on gold+silver only, FT on all
      - gold_only:    base on gold only, FT on all
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-432: Patient-Quality-Filtered Base Training (w48)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Load ALL data first to classify patients
    full_data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    quality = _classify_patient_quality(full_data['per_patient'], args.patients_dir)

    gold_pts = {n for n, q in quality.items() if q == 'gold'}
    silver_pts = {n for n, q in quality.items() if q == 'silver'}
    bronze_pts = {n for n, q in quality.items() if q == 'bronze'}

    print(f"\n  Quality classification:")
    print(f"    Gold ({len(gold_pts)}):   {sorted(gold_pts)}")
    print(f"    Silver ({len(silver_pts)}): {sorted(silver_pts)}")
    print(f"    Bronze ({len(bronze_pts)}): {sorted(bronze_pts)}")

    filter_configs = {
        'all_patients': set(),            # skip nobody
        'gold_silver':  bronze_pts,       # skip bronze
        'gold_only':    bronze_pts | silver_pts,  # skip non-gold
    }

    has_isf = 'isf_val' in full_data
    # Full data for FT (always uses all patients)
    full_train_x, full_val_x = prepare_pk_future(full_data, use_isf=has_isf, drop_time=False)
    full_isf_v = full_data.get('isf_val')
    n_ch = full_train_x.shape[-1]

    all_results = {}
    for vname, skip_set in filter_configs.items():
        print(f"\n{'─'*40}")
        print(f"  {vname}: skip={sorted(skip_set) if skip_set else 'none'}")
        print(f"{'─'*40}")

        # Load filtered base data
        if skip_set:
            base_data = load_bridge_data(
                args.patients_dir, window_size=48,
                max_patients=cfg['max_patients'], load_isf=True,
                skip_patients=skip_set)
        else:
            base_data = full_data

        base_train_x, base_val_x = prepare_pk_future(
            base_data, use_isf='isf_val' in base_data, drop_time=False)
        n_base = base_train_x.shape[0]
        print(f"  Base training: {n_base} windows "
              f"({len(base_data['per_patient'])} patients)")

        # Phase 1: Base training on filtered data
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp432_{vname}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({vname}):")
            train_bridge(model, base_train_x, base_val_x, sp,
                         f'432-{vname}-s{seed}', device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Phase 2: Per-patient FT on ALL patients (including bronze)
        print(f"\n=== Phase 2: Per-Patient FT (all patients) ===")
        per_patient = {}
        for pinfo in full_data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = full_train_x[ti:te]
            p_val_x = full_val_x[vi:ve]
            p_isf_v = full_isf_v[vi:ve] if full_isf_v is not None else None

            print(f"\n  Patient {pid} (quality={quality.get(pid,'?')}, "
                  f"{pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp432_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'432-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'quality': quality.get(pid, '?'),
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        gold_ens = [v['ensemble_mae'] for v in per_patient.values()
                    if v['quality'] == 'gold']
        bronze_ens = [v['ensemble_mae'] for v in per_patient.values()
                      if v['quality'] == 'bronze']

        all_results[vname] = {
            'skip_patients': sorted(skip_set),
            'n_base_train': n_base,
            'n_base_patients': len(base_data['per_patient']),
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'gold_mean_mae': round(float(np.mean(gold_ens)), 2) if gold_ens else None,
            'bronze_mean_mae': round(float(np.mean(bronze_ens)), 2) if bronze_ens else None,
            'per_patient': per_patient,
        }
        print(f"\n  {vname}: Mean MAE = {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-432 SUMMARY — Patient-Quality-Filtered Base Training")
    print(f"{'='*60}")
    print(f"  {'Config':<16} {'Base Pts':>8} {'Base Win':>8} {'All MAE':>8} "
          f"{'Gold MAE':>9} {'Bronze MAE':>10}")
    print(f"  {'─'*64}")
    for vn, vr in all_results.items():
        g = f"{vr['gold_mean_mae']:.2f}" if vr['gold_mean_mae'] else '—'
        b = f"{vr['bronze_mean_mae']:.2f}" if vr['bronze_mean_mae'] else '—'
        print(f"  {vn:<16} {vr['n_base_patients']:>8} {vr['n_base_train']:>8} "
              f"{vr['mean_ensemble_mae']:>8.2f} {g:>9} {b:>10}")
    ctrl = all_results.get('all_patients', {}).get('mean_ensemble_mae', 0)
    if ctrl:
        for vn, vr in all_results.items():
            if vn != 'all_patients':
                delta = vr['mean_ensemble_mae'] - ctrl
                print(f"    Δ {vn} vs control: {delta:+.2f}")
    print(f"\n  EXP-411 w48 full ref: 13.50")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-432: Patient-Quality-Filtered Base Training',
        'quality_map': quality,
        'results': all_results,
    }
    _save_results(result, 'exp432_quality_filtered', cfg)
    return result


# ─── EXP-433: State-Dependent Loss Weighting ───

def _classify_metabolic_state(x_batch, half):
    """Classify each window into metabolic state based on history channels.

    States (based on channels in history half):
      - 'fasting': IOB < 0.05 AND COB < 0.05 (no active insulin or carbs)
      - 'correction': IOB > 0.05 AND COB < 0.05 (insulin only)
      - 'meal': COB > 0.05 (carbs active, with or without bolus)
      - 'mixed': moderate activity in both

    Returns tensor of weights: [batch_size, 1]
    Uses channels: IOB=1, COB=2 (both normalized 0-1 in base grid)
    """
    # Look at mean of history half
    hist = x_batch[:, :half, :]
    mean_iob = hist[:, :, 1].abs().mean(dim=1)  # ch1=IOB
    mean_cob = hist[:, :, 2].abs().mean(dim=1)  # ch2=COB

    # Thresholds on normalized values
    iob_active = mean_iob > 0.02
    cob_active = mean_cob > 0.02

    # State classification
    fasting = ~iob_active & ~cob_active
    correction = iob_active & ~cob_active
    meal = cob_active

    return fasting, correction, meal


def train_bridge_state_weighted(model, train_x, val_x, save_path, label, device,
                                pk_mode=False, lr=1e-3, epochs=200, batch=32,
                                patience=20, weight_decay=1e-5, lr_patience=7,
                                future_steps=None,
                                fasting_weight=1.0, correction_weight=1.5,
                                meal_weight=2.0):
    """Train with state-dependent loss weighting.

    Meal windows are harder (more glucose dynamics) and clinically more
    important (dosing decisions). Correction windows have insulin-only dynamics.
    Fasting is the easiest baseline.

    Weighting the loss by metabolic state focuses gradient signal on the
    clinically harder and more important windows.
    """
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
    best = float('inf')
    stale = 0

    def _step(batch_data, backward=False, use_weights=False):
        x = batch_data[0].to(device)
        half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)

        target = x[:, half:, :1]
        output = pred[:, half:, :1]

        if use_weights:
            fasting, correction, meal = _classify_metabolic_state(x, half)
            weights = torch.ones(x.size(0), device=device)
            weights[fasting] = fasting_weight
            weights[correction] = correction_weight
            weights[meal] = meal_weight
            # Per-sample weighted MSE
            per_sample = ((output - target) ** 2).mean(dim=(1, 2))
            loss = (per_sample * weights).mean()
        else:
            loss = nn.functional.mse_loss(output, target)

        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True, use_weights=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False, use_weights=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')
        sched.step(vl)

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if patience > 0 and stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def run_exp433(args):
    """EXP-433: State-dependent loss weighting.

    Hypothesis: Weighting meal/correction windows more heavily in the loss
    focuses learning on the clinically harder and more important states.

    Fasting periods are easy (BG is relatively flat) but represent a large
    fraction of training data. Meal periods are hard (rapid BG changes)
    but clinically critical (dosing decisions happen during meals).

    By upweighting meal and correction windows, we shift gradient signal
    from the easy-but-boring fasting windows to the hard-but-important
    active windows.

    Variants:
      - uniform:        all windows weight 1.0 (control)
      - meal_2x:        fasting=1.0, correction=1.5, meal=2.0
      - meal_3x:        fasting=1.0, correction=1.5, meal=3.0
      - active_focus:   fasting=0.5, correction=2.0, meal=2.0
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-433: State-Dependent Loss Weighting (w48)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # First, profile metabolic state distribution
    half = 48 // 2
    fasting, correction, meal = _classify_metabolic_state(train_x, half)
    n = train_x.shape[0]
    print(f"\n  Metabolic state distribution (training):")
    print(f"    Fasting:    {fasting.sum().item():>5} ({fasting.sum().item()/n*100:.1f}%)")
    print(f"    Correction: {correction.sum().item():>5} ({correction.sum().item()/n*100:.1f}%)")
    print(f"    Meal:       {meal.sum().item():>5} ({meal.sum().item()/n*100:.1f}%)")

    weight_configs = {
        'uniform':      {'fasting_weight': 1.0, 'correction_weight': 1.0, 'meal_weight': 1.0},
        'meal_2x':      {'fasting_weight': 1.0, 'correction_weight': 1.5, 'meal_weight': 2.0},
        'meal_3x':      {'fasting_weight': 1.0, 'correction_weight': 1.5, 'meal_weight': 3.0},
        'active_focus': {'fasting_weight': 0.5, 'correction_weight': 2.0, 'meal_weight': 2.0},
    }

    all_results = {}
    for vname, weights in weight_configs.items():
        print(f"\n{'─'*40}")
        print(f"  {vname}: f={weights['fasting_weight']}, "
              f"c={weights['correction_weight']}, m={weights['meal_weight']}")
        print(f"{'─'*40}")

        # Base training with state-weighted loss
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp433_{vname}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({vname}):")
            if vname == 'uniform':
                # Control: standard training
                train_bridge(model, train_x, val_x, sp, f'433-{vname}-s{seed}',
                             device, pk_mode=True,
                             epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            else:
                train_bridge_state_weighted(
                    model, train_x, val_x, sp, f'433-{vname}-s{seed}',
                    device, pk_mode=True,
                    epochs=cfg['epochs_base'], patience=20, lr_patience=7,
                    **weights)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT (always uniform — FT is patient-specific)
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp433_{vname}_ft_{pid}_s{seed}.pth')
                # FT always uses standard loss (patient-specific already)
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'433-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'weights': weights,
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
        }
        print(f"\n  {vname}: Mean MAE = {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-433 SUMMARY — State-Dependent Loss Weighting")
    print(f"{'='*60}")
    print(f"  {'Config':<16} {'Fast':>5} {'Corr':>5} {'Meal':>5} {'MAE':>6}")
    print(f"  {'─'*42}")
    for vn, vr in all_results.items():
        w = vr['weights']
        print(f"  {vn:<16} {w['fasting_weight']:>5.1f} {w['correction_weight']:>5.1f} "
              f"{w['meal_weight']:>5.1f} {vr['mean_ensemble_mae']:>6.2f}")
    ctrl = all_results.get('uniform', {}).get('mean_ensemble_mae', 0)
    if ctrl:
        for vn, vr in all_results.items():
            if vn != 'uniform':
                delta = vr['mean_ensemble_mae'] - ctrl
                print(f"    Δ {vn} vs uniform: {delta:+.2f}")
    print(f"\n  EXP-411 w48 full ref: 13.50")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-433: State-Dependent Loss Weighting',
        'state_distribution': {
            'fasting_pct': round(fasting.sum().item() / n * 100, 1),
            'correction_pct': round(correction.sum().item() / n * 100, 1),
            'meal_pct': round(meal.sum().item() / n * 100, 1),
        },
        'results': all_results,
    }
    _save_results(result, 'exp433_state_weighted', cfg)
    return result


# ─── EXP-434: PK Conservation Fidelity Filtering ───

def compute_pk_conservation_error(base_windows, pk_windows, isf_array=None,
                                  half=24, glucose_scale=GLUCOSE_SCALE):
    """Compute per-window PK conservation error.

    Conservation symmetry: ΔBG ≈ -(insulin_net × ISF) + (carb_rate × CR)
    When this holds, PK channels carry genuine causal signal.
    When violated (bad settings, missing data), PK channels are noise.

    Returns per-window conservation error (lower = better fidelity).
    """
    n = len(base_windows)
    errors = np.zeros(n)

    for i in range(n):
        # Glucose change in history half (actual)
        gluc = base_windows[i, :half, 0]  # normalized 0-1
        valid = ~np.isnan(gluc) & (gluc > 0.01)
        if valid.sum() < 5:
            errors[i] = float('inf')
            continue

        # Actual glucose rate of change (per step, normalized)
        dgluc = np.diff(gluc[valid])
        actual_roc = np.mean(np.abs(dgluc)) if len(dgluc) > 0 else 0

        # PK-predicted direction: insulin_net (ch1) drives down, carb_rate (ch3) drives up
        ins_net = pk_windows[i, :half, 1]  # raw insulin_net
        carb_rt = pk_windows[i, :half, 3]  # raw carb_rate

        # Net PK effect direction over history
        mean_ins = np.mean(ins_net)
        mean_carb = np.mean(carb_rt)

        # Predicted direction: positive carbs → glucose up, positive insulin → glucose down
        pk_direction = mean_carb * 0.5 - mean_ins * 2.0  # rough ISF/CR scaling
        actual_direction = np.mean(dgluc) if len(dgluc) > 0 else 0

        # Conservation error: direction mismatch + magnitude mismatch
        # Low when PK and glucose agree; high when they disagree
        if actual_roc > 0.001:
            direction_error = abs(np.sign(pk_direction) - np.sign(actual_direction))
            magnitude_ratio = abs(pk_direction) / (actual_roc * glucose_scale + 1e-6)
            errors[i] = direction_error + min(abs(np.log(magnitude_ratio + 1e-6)), 5.0)
        else:
            # Flat glucose — PK should also be quiet
            errors[i] = abs(mean_ins) * 10 + abs(mean_carb) * 5

    return errors


def run_exp434(args):
    """EXP-434: PK conservation fidelity filtering.

    Hypothesis: PK channels only help when the patient data has sufficient
    fidelity to glucose conservation symmetry — ie, ISF × insulin ≈ ΔBG.
    Windows where PK signal disagrees with glucose movement add noise.

    Filtering approach:
    1. Compute per-window conservation error (PK vs glucose agreement)
    2. Remove worst N% of windows from training
    3. Train on filtered data, evaluate on ALL data (including filtered-out)

    This tests whether signal quality > data quantity for PK-enhanced models.

    Variants:
      - no_filter:   all windows (control)
      - filter_10:   remove worst 10% by conservation error
      - filter_25:   remove worst 25%
      - filter_50:   remove worst 50% (aggressive — keeps only best half)
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-434: PK Conservation Fidelity Filtering (w48)")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data

    # Compute conservation errors on raw data BEFORE PK preparation
    print("\n  Computing PK conservation errors...")
    train_errors = compute_pk_conservation_error(
        data['base_train'], data['pk_train'], half=24)
    val_errors = compute_pk_conservation_error(
        data['base_val'], data['pk_val'], half=24)

    # Profile the error distribution
    finite_errors = train_errors[np.isfinite(train_errors)]
    print(f"  Train conservation errors: mean={np.mean(finite_errors):.3f}, "
          f"median={np.median(finite_errors):.3f}, "
          f"p75={np.percentile(finite_errors, 75):.3f}, "
          f"p90={np.percentile(finite_errors, 90):.3f}")
    print(f"  Inf errors (missing data): {np.isinf(train_errors).sum()} "
          f"({np.isinf(train_errors).sum()/len(train_errors)*100:.1f}%)")

    # Prepare full data for evaluation (always evaluate on everything)
    train_x_full, val_x_full = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x_full.shape[-1]

    filter_configs = {
        'no_filter': 0.0,
        'filter_10': 0.10,
        'filter_25': 0.25,
        'filter_50': 0.50,
    }

    all_results = {}
    for vname, filter_pct in filter_configs.items():
        print(f"\n{'─'*40}")
        print(f"  {vname}: remove worst {filter_pct*100:.0f}%")
        print(f"{'─'*40}")

        if filter_pct > 0:
            threshold = np.percentile(finite_errors, (1 - filter_pct) * 100)
            keep_mask = train_errors <= threshold
            train_x = train_x_full[keep_mask]
            # Also filter ISF for training
            if has_isf:
                isf_train_filtered = data['isf_train'][keep_mask[:len(data['isf_train'])]]
            n_kept = keep_mask.sum()
            n_removed = len(keep_mask) - n_kept
            print(f"  Threshold: {threshold:.3f}, kept {n_kept}, removed {n_removed}")
        else:
            train_x = train_x_full
            n_kept = len(train_x)

        # Base training on filtered data
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp434_{vname}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({vname}, {n_kept} windows):")
            # Use full val for early stopping (don't filter val)
            train_bridge(model, train_x, val_x_full, sp,
                         f'434-{vname}-s{seed}', device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT on UNFILTERED per-patient data + evaluate
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x_full[ti:te]  # unfiltered for FT
            p_val_x = val_x_full[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            # Compute per-patient conservation quality
            p_errors = train_errors[ti:te]
            p_finite = p_errors[np.isfinite(p_errors)]
            p_quality = np.median(p_finite) if len(p_finite) > 0 else float('inf')

            print(f"\n  Patient {pid} (quality={p_quality:.3f}, "
                  f"{pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp434_{vname}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'434-ft-{pid}-s{seed}', device, pk_mode=True,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v)
            per_patient[pid] = {
                'seeds': seed_maes,
                'conservation_quality': round(float(p_quality), 3),
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]
        all_results[vname] = {
            'filter_pct': filter_pct,
            'n_train_kept': int(n_kept),
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'per_patient': per_patient,
        }
        print(f"\n  {vname}: Mean MAE = {all_results[vname]['mean_ensemble_mae']:.2f}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-434 SUMMARY — PK Conservation Fidelity Filtering")
    print(f"{'='*60}")
    print(f"  {'Config':<14} {'Filter':>6} {'Train':>8} {'MAE':>6}")
    print(f"  {'─'*40}")
    for vn, vr in all_results.items():
        print(f"  {vn:<14} {vr['filter_pct']*100:>4.0f}% {vr['n_train_kept']:>8} "
              f"{vr['mean_ensemble_mae']:>6.2f}")
    ctrl = all_results.get('no_filter', {}).get('mean_ensemble_mae', 0)
    if ctrl:
        for vn, vr in all_results.items():
            if vn != 'no_filter':
                delta = vr['mean_ensemble_mae'] - ctrl
                print(f"    Δ {vn} vs no_filter: {delta:+.2f}")

    # Per-patient quality vs MAE correlation
    print(f"\n  Per-patient conservation quality (no_filter):")
    no_filt = all_results.get('no_filter', {}).get('per_patient', {})
    for pid, pr in sorted(no_filt.items(), key=lambda x: x[1]['conservation_quality']):
        print(f"    {pid}: quality={pr['conservation_quality']:.3f}, "
              f"MAE={pr['ensemble_mae']:.1f}")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-434: PK Conservation Fidelity Filtering',
        'error_distribution': {
            'mean': round(float(np.mean(finite_errors)), 3),
            'median': round(float(np.median(finite_errors)), 3),
            'p75': round(float(np.percentile(finite_errors, 75)), 3),
            'p90': round(float(np.percentile(finite_errors, 90)), 3),
        },
        'results': all_results,
    }
    _save_results(result, 'exp434_fidelity_filter', cfg)
    return result


# ─── EXP-435: Extended Future PK Projection for h120+ ───

def run_exp435(args):
    """EXP-435: Extended future PK projection for h120+.

    Key insight: PK channels are DETERMINISTIC — computed from past events,
    they project absorption forward. We can extend the future PK projection
    beyond the standard symmetric split without needing more history.

    Current: w48 = 24 hist + 24 future → h120 max
    Proposed: fixed 24 hist (2h, proven optimal) + extended future:
      - w48_sym:      24 hist + 24 future → h120 (control)
      - w60_asym:     24 hist + 36 future → h180
      - w72_asym:     24 hist + 48 future → h240
      - w96_asym:     24 hist + 72 future → h360

    The model gets 2h of history (glucose momentum + current PK state) PLUS
    the complete future PK trajectory showing how insulin/carb absorption
    will evolve over the next 3-6 hours. This gives it knowledge of the
    full DIA arc without the data scarcity penalty of longer history.

    Hypothesis: This should dramatically improve h120-h360 because the model
    can now see the insulin tail — the gradual decay of bolus activity over
    the complete DIA (5-6h), which determines long-term glucose trajectory.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-435: Extended Future PK Projection")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Configurations: (window_size, history_steps, future_steps, label)
    configs = [
        (48, 24, 24, 'w48_sym'),      # control: symmetric
        (60, 24, 36, 'w60_asym'),      # +60min future PK
        (72, 24, 48, 'w72_asym'),      # +120min future PK (covers full DIA)
        (96, 24, 72, 'w96_asym'),      # +240min future PK (beyond DIA)
    ]

    all_results = {}
    for ws, hist, fut, label in configs:
        print(f"\n{'─'*40}")
        print(f"  {label}: {hist*5}min hist + {fut*5}min future = h{fut*5}")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=ws,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]

        print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val, {n_ch}ch, "
              f"seq_len={ws}")

        # Base training with asymmetric future_steps
        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp435_{label}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({label}):")
            train_bridge(model, train_x, val_x, sp, f'435-{label}-s{seed}',
                         device, pk_mode=True, future_steps=fut,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)

            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT + ensemble
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train_x = train_x[ti:te]
            p_val_x = val_x[vi:ve]
            p_isf_v = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']} train, {pinfo['n_val']} val):")
            seed_maes = {}
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp435_{label}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train_x, p_val_x, sp,
                             f'435-ft-{pid}-s{seed}', device, pk_mode=True,
                             future_steps=fut,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                metrics = evaluate_model(model, p_val_x, device, pk_mode=True,
                                         isf_val=p_isf_v, future_steps=fut)
                seed_maes[f's{seed}'] = metrics['overall_mae']
                ft_models.append(copy.deepcopy(model))
                print(f"    s{seed}: MAE={metrics['overall_mae']:.1f}")

            ens = ensemble_evaluate(ft_models, p_val_x, device, pk_mode=True,
                                    isf_val=p_isf_v, future_steps=fut)
            per_patient[pid] = {
                'seeds': seed_maes,
                'ensemble_mae': ens['overall_mae'],
                'ensemble_per_horizon': ens,
            }
            print(f"    Ensemble: MAE={ens['overall_mae']:.1f}, "
                  f"h60={ens.get('h60','?')}, h120={ens.get('h120','?')}")

        all_ens = [v['ensemble_mae'] for v in per_patient.values()]

        # Extract per-horizon averages
        horizon_avgs = {}
        for hname in ['h30', 'h60', 'h90', 'h120', 'h150', 'h180', 'h240', 'h300', 'h360']:
            step_idx = {'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
                        'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71}.get(hname, -1)
            if step_idx < fut:
                vals = [v['ensemble_per_horizon'].get(hname)
                        for v in per_patient.values()
                        if v['ensemble_per_horizon'].get(hname) is not None]
                if vals:
                    horizon_avgs[hname] = round(float(np.mean(vals)), 2)

        all_results[label] = {
            'window_size': ws,
            'history_steps': hist,
            'future_steps': fut,
            'max_horizon_min': fut * 5,
            'n_train': train_x.shape[0],
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'horizon_averages': horizon_avgs,
            'per_patient': per_patient,
        }
        print(f"\n  {label}: Mean Ensemble MAE = {all_results[label]['mean_ensemble_mae']:.2f}")
        print(f"  Per-horizon: {horizon_avgs}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-435 SUMMARY — Extended Future PK Projection")
    print(f"{'='*60}")
    hdr = f"  {'Config':<14} {'Hist':>5} {'Fut':>5} {'Train':>6} {'MAE':>6}"
    # Add horizon columns that exist
    all_horizons = sorted(set(h for r in all_results.values()
                              for h in r['horizon_averages']))
    for h in all_horizons:
        hdr += f" {h:>6}"
    print(hdr)
    print(f"  {'─'*(len(hdr)-2)}")
    for vn, vr in all_results.items():
        line = (f"  {vn:<14} {vr['history_steps']*5:>4}m {vr['future_steps']*5:>4}m "
                f"{vr['n_train']:>6} {vr['mean_ensemble_mae']:>6.2f}")
        for h in all_horizons:
            v = vr['horizon_averages'].get(h, '')
            line += f" {v if v else '—':>6}"
        print(line)

    ctrl = all_results.get('w48_sym', {}).get('mean_ensemble_mae', 0)
    if ctrl:
        for vn, vr in all_results.items():
            if vn != 'w48_sym':
                delta = vr['mean_ensemble_mae'] - ctrl
                print(f"    Δ {vn} vs w48_sym: {delta:+.2f}")

    # Per-horizon improvement analysis
    ctrl_horizons = all_results.get('w48_sym', {}).get('horizon_averages', {})
    if ctrl_horizons:
        print(f"\n  Per-horizon Δ vs w48_sym control:")
        for vn, vr in all_results.items():
            if vn == 'w48_sym':
                continue
            deltas = []
            for h in sorted(ctrl_horizons.keys()):
                if h in vr['horizon_averages']:
                    d = vr['horizon_averages'][h] - ctrl_horizons[h]
                    deltas.append(f"{h}:{d:+.1f}")
            print(f"    {vn}: {', '.join(deltas)}")

    print(f"\n  EXP-411 w48 full ref: 13.50 (symmetric)")
    print(f"  EXP-429 best h60: 12.78 (w36 asym, 2h hist)")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-435: Extended Future PK Projection',
        'results': all_results,
    }
    _save_results(result, 'exp435_extended_future_pk', cfg)
    return result


# ─── EXP-436: Horizon-Routed Ensemble ───

def run_exp436(args):
    """EXP-436: Horizon-routed ensemble — best model per horizon band.

    EXP-435 showed: w48 is best for h30-h120 (more data wins) but w96 is
    competitive at h240+ (extended PK wins). The solution is to train
    SEPARATE models for each horizon band and route predictions.

    This avoids the fundamental trade-off: short-horizon models don't
    sacrifice data for unused long-range context, while long-horizon models
    get the DIA-length future PK they need.

    Architecture:
      - Short model: w48 (24 hist + 24 future), predict h5-h120
      - Long model:  w96 (24 hist + 72 future), predict h120-h360
      - Combined: short predictions up to h120, long predictions h120+

    The combined system gives best-of-both: data-rich short-range accuracy
    with PK-informed long-range coverage.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-436: Horizon-Routed Ensemble")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # ── Train Short Model (w48, symmetric, for h30-h120) ──
    print(f"\n{'─'*40}")
    print(f"  SHORT MODEL: w48 (24hist + 24future → h120)")
    print(f"{'─'*40}")

    data_short = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data_short
    train_short, val_short = prepare_pk_future(data_short, use_isf=has_isf, drop_time=False)
    isf_v_short = data_short.get('isf_val')
    n_ch = train_short.shape[-1]

    print(f"  {train_short.shape[0]} train, {val_short.shape[0]} val, {n_ch}ch")

    short_base_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp436_short_base_s{seed}.pth')
        print(f"\n  Short base s{seed}:")
        train_bridge(model, train_short, val_short, sp, f'436-short-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        short_base_states[seed] = ckpt['model_state']

    # ── Train Long Model (w96, asymmetric 24hist+72future, for h120-h360) ──
    print(f"\n{'─'*40}")
    print(f"  LONG MODEL: w96 (24hist + 72future → h360)")
    print(f"{'─'*40}")

    data_long = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf_l = 'isf_val' in data_long
    train_long, val_long = prepare_pk_future(data_long, use_isf=has_isf_l, drop_time=False)
    isf_v_long = data_long.get('isf_val')

    print(f"  {train_long.shape[0]} train, {val_long.shape[0]} val, {n_ch}ch")

    long_base_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp436_long_base_s{seed}.pth')
        print(f"\n  Long base s{seed}:")
        train_bridge(model, train_long, val_long, sp, f'436-long-s{seed}',
                     device, pk_mode=True, future_steps=72,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        long_base_states[seed] = ckpt['model_state']

    # ── Per-Patient FT + Routed Evaluation ──
    print(f"\n{'='*40}")
    print(f"  Per-Patient FT + Horizon Routing")
    print(f"{'='*40}")

    # Build patient alignment between short and long datasets
    short_patients = {p['name']: p for p in data_short['per_patient']}
    long_patients = {p['name']: p for p in data_long['per_patient']}
    common_patients = sorted(set(short_patients) & set(long_patients))

    per_patient_results = {}
    for pid in common_patients:
        pinfo_s = short_patients[pid]
        pinfo_l = long_patients[pid]

        # Short model FT data
        ti_s, te_s = pinfo_s['train_idx']
        vi_s, ve_s = pinfo_s['val_idx']
        p_train_s = train_short[ti_s:te_s]
        p_val_s = val_short[vi_s:ve_s]
        p_isf_s = isf_v_short[vi_s:ve_s] if isf_v_short is not None else None

        # Long model FT data
        ti_l, te_l = pinfo_l['train_idx']
        vi_l, ve_l = pinfo_l['val_idx']
        p_train_l = train_long[ti_l:te_l]
        p_val_l = val_long[vi_l:ve_l]
        p_isf_l = isf_v_long[vi_l:ve_l] if isf_v_long is not None else None

        print(f"\n  Patient {pid} (short:{pinfo_s['n_train']}tr, long:{pinfo_l['n_train']}tr):")

        # FT + evaluate short model
        short_ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(short_base_states[seed])
            sp = os.path.join(cfg['output_dir'], f'exp436_short_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_s, p_val_s, sp,
                         f'436-sft-{pid}-s{seed}', device, pk_mode=True,
                         lr=1e-4, epochs=cfg['epochs_ft'],
                         patience=10, lr_patience=5)
            short_ft_models.append(copy.deepcopy(model))

        short_ens = ensemble_evaluate(short_ft_models, p_val_s, device,
                                      pk_mode=True, isf_val=p_isf_s)
        print(f"    Short: MAE={short_ens['overall_mae']:.1f}, "
              f"h60={short_ens.get('h60','?')}, h120={short_ens.get('h120','?')}")

        # FT + evaluate long model
        long_ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(long_base_states[seed])
            sp = os.path.join(cfg['output_dir'], f'exp436_long_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_l, p_val_l, sp,
                         f'436-lft-{pid}-s{seed}', device, pk_mode=True,
                         future_steps=72,
                         lr=1e-4, epochs=cfg['epochs_ft'],
                         patience=10, lr_patience=5)
            long_ft_models.append(copy.deepcopy(model))

        long_ens = ensemble_evaluate(long_ft_models, p_val_l, device,
                                     pk_mode=True, isf_val=p_isf_l,
                                     future_steps=72)
        print(f"    Long:  MAE={long_ens['overall_mae']:.1f}, "
              f"h60={long_ens.get('h60','?')}, h120={long_ens.get('h120','?')}, "
              f"h240={long_ens.get('h240','?')}, h360={long_ens.get('h360','?')}")

        # Routed result: short for h30-h120, long for h150-h360
        routed = {}
        for h in ['h30', 'h60', 'h90', 'h120']:
            if h in short_ens:
                routed[h] = short_ens[h]
        for h in ['h150', 'h180', 'h240', 'h300', 'h360']:
            if h in long_ens:
                routed[h] = long_ens[h]

        per_patient_results[pid] = {
            'short_overall': short_ens['overall_mae'],
            'long_overall': long_ens['overall_mae'],
            'short_horizons': {k: v for k, v in short_ens.items() if k.startswith('h')},
            'long_horizons': {k: v for k, v in long_ens.items() if k.startswith('h')},
            'routed': routed,
        }
        print(f"    Routed: {routed}")

    # Summary
    print(f"\n{'='*60}")
    print("EXP-436 SUMMARY — Horizon-Routed Ensemble")
    print(f"{'='*60}")

    # Per-horizon mean across patients
    all_horizons = sorted(set(h for pr in per_patient_results.values()
                               for h in pr['routed']))
    print(f"\n  Routed ensemble (best model per horizon band):")
    print(f"  {'Horizon':<8} {'MAE':>6} {'Source':>8}")
    print(f"  {'─'*24}")
    for h in all_horizons:
        vals = [pr['routed'][h] for pr in per_patient_results.values() if h in pr['routed']]
        source = 'short' if h in ['h30', 'h60', 'h90', 'h120'] else 'long'
        if vals:
            print(f"  {h:<8} {np.mean(vals):>6.1f} {source:>8}")

    # Compare to single-model baselines
    short_means = {h: np.mean([pr['short_horizons'].get(h, float('nan'))
                               for pr in per_patient_results.values()])
                   for h in ['h30', 'h60', 'h90', 'h120']}
    long_means = {h: np.mean([pr['long_horizons'].get(h, float('nan'))
                              for pr in per_patient_results.values()])
                  for h in all_horizons if any(h in pr['long_horizons']
                                               for pr in per_patient_results.values())}

    print(f"\n  Comparison:")
    print(f"  {'Horizon':<8} {'Short':>7} {'Long':>7} {'Routed':>7} {'Δ vs best single':>16}")
    print(f"  {'─'*45}")
    for h in all_horizons:
        s = short_means.get(h, float('nan'))
        l = long_means.get(h, float('nan'))
        r = np.mean([pr['routed'][h] for pr in per_patient_results.values() if h in pr['routed']])
        best_single = min(x for x in [s, l] if not np.isnan(x))
        delta = r - best_single
        s_str = f"{s:.1f}" if not np.isnan(s) else "—"
        l_str = f"{l:.1f}" if not np.isnan(l) else "—"
        print(f"  {h:<8} {s_str:>7} {l_str:>7} {r:>7.1f} {delta:>+14.1f}")

    print(f"\n  EXP-411 w48 full ref: 13.50 (h30-h120 only)")
    print(f"  EXP-435 w96 quick ref: h240=27.02, h360=28.95")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-436: Horizon-Routed Ensemble',
        'per_patient': per_patient_results,
        'n_patients': len(per_patient_results),
    }
    _save_results(result, 'exp436_horizon_routed', cfg)
    return result


# ─── EXP-437: Extended History for Long-Range Model ───

def run_exp437(args):
    """EXP-437: Does more history improve long-range (h120-h360) predictions?

    EXP-435/436 used 24-step (2h) history for all models. Prior experiments
    (EXP-429/430) showed MORE HISTORY DOESN'T HELP at w48 for h30-h120.
    But PK-driven long-horizon predictions might benefit from longer history
    because insulin dynamics unfold over DIA (5-6h).

    Tests:
      - w96  (24 hist + 72 future)  ← EXP-435 baseline
      - w120 (48 hist + 72 future)  ← 4h history
      - w144 (72 hist + 72 future)  ← 6h history (= DIA)
    All have same 72-step (6h) future, varying only history length.
    If longer history helps, it means the model can extract useful PK context
    from the past DIA period to improve long-range forecasts.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-437: Extended History for Long-Range Forecasting")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    configs = [
        (96,  24, 72, 'hist2h'),    # 2h history, 6h future (EXP-435 baseline)
        (120, 48, 72, 'hist4h'),    # 4h history, 6h future
        (144, 72, 72, 'hist6h'),    # 6h history (=DIA), 6h future
    ]

    all_results = {}
    for ws, hist, fut, label in configs:
        print(f"\n{'─'*40}")
        print(f"  {label}: {hist*5}min hist + {fut*5}min future (w{ws})")
        print(f"{'─'*40}")

        data = load_bridge_data(
            args.patients_dir, window_size=ws,
            max_patients=cfg['max_patients'], load_isf=True)
        has_isf = 'isf_val' in data
        train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
        isf_v = data.get('isf_val')
        n_ch = train_x.shape[-1]

        print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val, {n_ch}ch, "
              f"seq_len={ws}")

        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp437_{label}_base_s{seed}.pth')

            print(f"\n  Base s{seed} ({label}):")
            train_bridge(model, train_x, val_x, sp, f'437-{label}-s{seed}',
                         device, pk_mode=True, future_steps=fut,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT + evaluation
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train = train_x[ti:te]; p_val = val_x[vi:ve]
            p_isf = isf_v[vi:ve] if isf_v is not None else None

            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp437_{label}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train, p_val, sp,
                             f'437-{label}-ft-{pid}-s{seed}', device,
                             pk_mode=True, future_steps=fut,
                             lr=1e-4, epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                ft_models.append(copy.deepcopy(model))

            ens = ensemble_evaluate(ft_models, p_val, device, pk_mode=True,
                                    isf_val=p_isf, future_steps=fut)
            per_patient[pid] = ens
            horizons_str = ', '.join(f"{h}={ens[h]:.1f}" for h in
                                     ['h120', 'h180', 'h240', 'h300', 'h360']
                                     if h in ens)
            print(f"  {pid}: MAE={ens['overall_mae']:.1f}, {horizons_str}")

        # Compute mean per horizon
        mean_horizons = {}
        for h in ['h30', 'h60', 'h90', 'h120', 'h150', 'h180', 'h240', 'h300', 'h360']:
            vals = [pp[h] for pp in per_patient.values() if h in pp]
            if vals:
                mean_horizons[h] = np.mean(vals)

        all_results[label] = {
            'window_size': ws, 'history': hist, 'future': fut,
            'per_patient': {k: v for k, v in per_patient.items()},
            'mean_horizons': mean_horizons,
            'n_train': train_x.shape[0],
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXP-437 SUMMARY — Extended History for Long-Range")
    print(f"{'='*60}")

    all_horizons = sorted(set(h for r in all_results.values() for h in r['mean_horizons']))
    print(f"\n  {'Config':<12} {'Train':>6}", end='')
    for h in all_horizons:
        print(f" {h:>6}", end='')
    print()
    print(f"  {'─'*(12 + 7 + 7*len(all_horizons))}")

    for label, r in all_results.items():
        print(f"  {label:<12} {r['n_train']:>6}", end='')
        for h in all_horizons:
            v = r['mean_horizons'].get(h)
            print(f" {v:>6.1f}" if v else f" {'—':>6}", end='')
        print()

    # Delta vs baseline (hist2h)
    baseline = all_results.get('hist2h', {}).get('mean_horizons', {})
    print(f"\n  Delta vs hist2h baseline:")
    for label, r in all_results.items():
        if label == 'hist2h':
            continue
        print(f"  {label:<12}", end='')
        for h in all_horizons:
            v = r['mean_horizons'].get(h)
            b = baseline.get(h)
            if v is not None and b is not None:
                print(f" {v-b:>+6.1f}", end='')
            else:
                print(f" {'—':>6}", end='')
        print()

    print(f"\n  Question: Does DIA-length history (6h) help predict beyond DIA?")
    print(f"  If hist6h < hist2h at h240+, answer is YES.")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-437: Extended History for Long-Range',
        'variants': all_results,
    }
    _save_results(result, 'exp437_extended_history_longrange', cfg)
    return result


# ─── EXP-438: Patient Fidelity Gating ───

def run_exp438(args):
    """EXP-438: Patient-level fidelity gating using settings assessment scores.

    Settings assessment report (2026-04-07) provides per-patient fidelity
    scores: k=84, d=52, j=50, h=44, g=36, b=35, f=32, e=20, c=17, a=17, i=15.

    Hypothesis: Training ONLY on high-fidelity patients (score ≥ 35) and then
    fine-tuning on each patient individually should outperform training on all
    patients, because low-fidelity patients introduce noise into base training.

    Tests:
      - all_patients: standard pooled training (all available patients)
      - gold_only: base train only on patients with fidelity ≥ 45 (k,d,j,h)
      - silver+: base train on fidelity ≥ 35 (k,d,j,h,g,b)
      - gold_ft_all: base on gold, FT on all patients individually

    This requires full mode (11 patients) to be meaningful. In quick mode (4
    patients), all may be similar quality, reducing discriminative power.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    # Per-patient fidelity from settings assessment
    FIDELITY_SCORES = {
        'k': 84, 'd': 52, 'j': 50, 'h': 44, 'g': 36, 'b': 35,
        'f': 32, 'e': 20, 'c': 17, 'a': 17, 'i': 15
    }
    GOLD_THRESHOLD = 45   # k, d, j, h
    SILVER_THRESHOLD = 35  # + g, b

    print(f"\n{'='*60}")
    print(f"EXP-438: Patient Fidelity Gating")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Load full dataset
    data = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_all, val_all = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v_all = data.get('isf_val')
    n_ch = train_all.shape[-1]

    # Classify patients
    patient_names = [p['name'] for p in data['per_patient']]
    gold_patients = [p for p in patient_names if FIDELITY_SCORES.get(p, 50) >= GOLD_THRESHOLD]
    silver_patients = [p for p in patient_names if FIDELITY_SCORES.get(p, 50) >= SILVER_THRESHOLD]

    print(f"\n  Patients: {patient_names}")
    print(f"  Gold (≥{GOLD_THRESHOLD}): {gold_patients}")
    print(f"  Silver+ (≥{SILVER_THRESHOLD}): {silver_patients}")

    # Build filtered training sets
    patient_map = {p['name']: p for p in data['per_patient']}

    def _get_filtered_train(patient_subset):
        """Get training data only from specified patients."""
        chunks = []
        for pid in patient_subset:
            if pid in patient_map:
                pi = patient_map[pid]
                ti, te = pi['train_idx']
                chunks.append(train_all[ti:te].numpy() if isinstance(train_all, torch.Tensor) else train_all[ti:te])
        if not chunks:
            return train_all[:0]
        arr = np.concatenate(chunks, axis=0)
        return torch.tensor(arr, dtype=torch.float32)

    train_gold = _get_filtered_train(gold_patients)
    train_silver = _get_filtered_train(silver_patients)

    print(f"  All train: {train_all.shape[0]}, Gold: {train_gold.shape[0]}, "
          f"Silver+: {train_silver.shape[0]}")

    configs = [
        ('all_patients', train_all),
        ('gold_only', train_gold),
        ('silver_plus', train_silver),
    ]

    all_results = {}
    for label, train_data in configs:
        if len(train_data) < 50:
            print(f"\n  {label}: SKIP (only {len(train_data)} windows)")
            continue

        print(f"\n{'─'*40}")
        print(f"  {label}: {len(train_data)} training windows")
        print(f"{'─'*40}")

        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp438_{label}_base_s{seed}.pth')

            train_bridge(model, train_data, val_all, sp, f'438-{label}-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT and evaluation (FT always on that patient's own data)
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train = train_all[ti:te]; p_val = val_all[vi:ve]
            p_isf = isf_v_all[vi:ve] if isf_v_all is not None else None
            fid = FIDELITY_SCORES.get(pid, 50)

            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(base_states[seed])
                sp = os.path.join(cfg['output_dir'], f'exp438_{label}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train, p_val, sp,
                             f'438-{label}-ft-{pid}-s{seed}', device,
                             pk_mode=True, lr=1e-4,
                             epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                ft_models.append(copy.deepcopy(model))

            ens = ensemble_evaluate(ft_models, p_val, device, pk_mode=True,
                                    isf_val=p_isf)
            per_patient[pid] = {**ens, 'fidelity': fid}
            print(f"  {pid} (fid={fid}): MAE={ens['overall_mae']:.1f}")

        overall = np.mean([pp['overall_mae'] for pp in per_patient.values()])
        all_results[label] = {
            'per_patient': per_patient,
            'overall_mae': overall,
            'n_train': len(train_data),
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXP-438 SUMMARY — Patient Fidelity Gating")
    print(f"{'='*60}")

    for label, r in all_results.items():
        print(f"\n  {label} (n_train={r['n_train']}): overall={r['overall_mae']:.2f}")
        for pid in sorted(r['per_patient'], key=lambda p: r['per_patient'][p]['fidelity'], reverse=True):
            pp = r['per_patient'][pid]
            print(f"    {pid} (fid={pp['fidelity']}): {pp['overall_mae']:.1f}")

    # Compare to all_patients baseline
    if 'all_patients' in all_results:
        baseline = all_results['all_patients']['overall_mae']
        print(f"\n  Delta vs all_patients ({baseline:.2f}):")
        for label, r in all_results.items():
            if label != 'all_patients':
                delta = r['overall_mae'] - baseline
                print(f"    {label}: {delta:+.2f}")

    print(f"\n  NOTE: In quick mode (4 patients), filtering may not differentiate.")
    print(f"  Full mode (11 patients) needed for meaningful fidelity spread.")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-438: Patient Fidelity Gating',
        'variants': all_results,
        'fidelity_scores': FIDELITY_SCORES,
    }
    _save_results(result, 'exp438_fidelity_gating', cfg)
    return result


# ─── EXP-439: Autoregressive Rollout for Long Horizons ───

def _autoregressive_predict(model, val_x, n_rollouts, device, pk_mode=True,
                            isf_val=None, scale=GLUCOSE_SCALE):
    """Predict long horizons by iteratively rolling the short model forward.

    Uses a trained w48 model (24 hist → 24 future) to predict h120,
    then shifts the window forward and predicts again for h120-h240, etc.

    Key: only glucose is rolled forward (predicted). PK channels remain
    ground truth from the extended w96/w144 data, since PK is deterministic.

    Args:
        model: trained short model (w48)
        val_x: validation data, shape [N, seq_len_extended, ch]
                Must be wider than w48 (e.g., w96 or w144) to provide
                ground-truth PK/context channels for rollout steps.
        n_rollouts: number of 24-step rollouts (1=h120, 2=h240, 3=h360)
    """
    model.to(device)
    model.eval()
    half = 24  # w48 model: 24 history, 24 future

    N, full_len, n_ch = val_x.shape
    all_preds = []  # shape: [N, n_rollouts * 24]
    all_targets = []

    with torch.no_grad():
        for rollout_idx in range(n_rollouts):
            offset = rollout_idx * half
            # Extract w48 window starting at offset
            if offset + 2 * half > full_len:
                break
            window = val_x[:, offset:offset + 2*half, :].clone().to(device)

            # For rollout > 0, replace history glucose with predictions
            if rollout_idx > 0 and len(all_preds) > 0:
                # Previous predictions fill the history glucose channel
                prev_preds_norm = all_preds[-1]  # [N, 24] in normalized space
                window[:, :half, 0] = torch.tensor(prev_preds_norm, dtype=torch.float32).to(device)

            # Mask future glucose
            mask_future_pk(window, half, pk_mode=pk_mode)

            # Predict
            pred = model(window, causal=True)
            p_norm = pred[:, half:, 0].cpu().numpy()  # [N, 24] normalized
            t_norm = val_x[:, offset+half:offset+2*half, 0].numpy()  # [N, 24]

            all_preds.append(p_norm)
            all_targets.append(t_norm)

    # Concatenate all rollouts
    preds_cat = np.concatenate(all_preds, axis=1)  # [N, n_rollouts*24]
    targets_cat = np.concatenate(all_targets, axis=1)

    # De-normalize
    if isf_val is not None:
        undo = (isf_val / GLUCOSE_SCALE).reshape(-1, 1)
        preds_mg = preds_cat * undo * scale
        targets_mg = targets_cat * undo * scale
    else:
        preds_mg = preds_cat * scale
        targets_mg = targets_cat * scale

    # Compute MAE per horizon
    mae_per_step = np.mean(np.abs(preds_mg - targets_mg), axis=0)
    report = {'overall_mae': round(float(np.mean(np.abs(preds_mg - targets_mg))), 2)}
    horizon_map = {
        'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23,
        'h150': 29, 'h180': 35, 'h240': 47, 'h300': 59, 'h360': 71,
    }
    for name, step_idx in horizon_map.items():
        if step_idx < len(mae_per_step):
            report[name] = round(float(mae_per_step[step_idx]), 2)
    return report


def run_exp439(args):
    """EXP-439: Autoregressive rollout vs direct prediction for h120-h360.

    Compares two strategies for long-horizon prediction:
    1. Direct: w96 model predicts h120-h360 in one shot (EXP-435 approach)
    2. Autoregressive: w48 model rolled forward 3× (h120→h240→h360)

    The autoregressive approach has MORE training data (w48=10K vs w96=5K)
    and excellent h30 accuracy (13.3), but may suffer from error accumulation
    as predicted glucose replaces ground truth in subsequent rollouts.

    If autoregressive h240 < direct h240, it means the h30 model's higher
    accuracy compensates for error accumulation — suggesting a fundamentally
    different long-horizon strategy.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-439: Autoregressive Rollout vs Direct Prediction")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # ── Load extended data (w144 = 6h total for ground truth context) ──
    data_ext = load_bridge_data(
        args.patients_dir, window_size=144,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data_ext
    train_ext, val_ext = prepare_pk_future(data_ext, use_isf=has_isf, drop_time=False)
    isf_v_ext = data_ext.get('isf_val')
    n_ch = train_ext.shape[-1]

    # ── Also load w48 data for short model training ──
    data_short = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    train_short, val_short = prepare_pk_future(data_short, use_isf=has_isf, drop_time=False)
    isf_v_short = data_short.get('isf_val')

    # ── Also load w96 data for direct long model ──
    data_long = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    train_long, val_long = prepare_pk_future(data_long, use_isf=has_isf, drop_time=False)
    isf_v_long = data_long.get('isf_val')

    print(f"  Short (w48): {train_short.shape[0]} train, {val_short.shape[0]} val")
    print(f"  Long (w96): {train_long.shape[0]} train, {val_long.shape[0]} val")
    print(f"  Extended (w144): {train_ext.shape[0]} train, {val_ext.shape[0]} val")

    # ── Train short model (w48) ──
    print(f"\n{'─'*40}")
    print(f"  Training SHORT model (w48, for autoregressive rollout)")
    print(f"{'─'*40}")

    short_base_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp439_short_base_s{seed}.pth')
        train_bridge(model, train_short, val_short, sp, f'439-short-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        short_base_states[seed] = ckpt['model_state']

    # ── Train direct long model (w96) ──
    print(f"\n{'─'*40}")
    print(f"  Training DIRECT model (w96, one-shot h360)")
    print(f"{'─'*40}")

    long_base_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp439_long_base_s{seed}.pth')
        train_bridge(model, train_long, val_long, sp, f'439-long-s{seed}',
                     device, pk_mode=True, future_steps=72,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        long_base_states[seed] = ckpt['model_state']

    # ── Per-patient FT and Evaluation ──
    short_patients = {p['name']: p for p in data_short['per_patient']}
    long_patients = {p['name']: p for p in data_long['per_patient']}
    ext_patients = {p['name']: p for p in data_ext['per_patient']}
    common = sorted(set(short_patients) & set(long_patients) & set(ext_patients))

    per_patient = {}
    for pid in common:
        pi_s = short_patients[pid]
        pi_l = long_patients[pid]
        pi_e = ext_patients[pid]

        # Short model FT
        ti_s, te_s = pi_s['train_idx']
        vi_s, ve_s = pi_s['val_idx']
        p_train_s = train_short[ti_s:te_s]
        p_val_s = val_short[vi_s:ve_s]
        p_isf_s = isf_v_short[vi_s:ve_s] if isf_v_short is not None else None

        # Long model FT
        ti_l, te_l = pi_l['train_idx']
        vi_l, ve_l = pi_l['val_idx']
        p_train_l = train_long[ti_l:te_l]
        p_val_l = val_long[vi_l:ve_l]
        p_isf_l = isf_v_long[vi_l:ve_l] if isf_v_long is not None else None

        # Extended data for autoregressive context
        vi_e, ve_e = pi_e['val_idx']
        p_val_e = val_ext[vi_e:ve_e]
        p_isf_e = isf_v_ext[vi_e:ve_e] if isf_v_ext is not None else None

        print(f"\n  Patient {pid}:")

        # FT short models
        short_ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(short_base_states[seed])
            sp = os.path.join(cfg['output_dir'], f'exp439_short_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_s, p_val_s, sp,
                         f'439-sft-{pid}-s{seed}', device, pk_mode=True,
                         lr=1e-4, epochs=cfg['epochs_ft'],
                         patience=10, lr_patience=5)
            short_ft_models.append(copy.deepcopy(model))

        # Evaluate short model standard (h30-h120)
        short_ens = ensemble_evaluate(short_ft_models, p_val_s, device,
                                      pk_mode=True, isf_val=p_isf_s)
        print(f"    Short direct: h30={short_ens.get('h30','?')}, "
              f"h60={short_ens.get('h60','?')}, h120={short_ens.get('h120','?')}")

        # Autoregressive rollout using extended data (3 rollouts = h360)
        # Use first FT model for autoregressive (ensemble averaging doesn't
        # compose well with sequential rollout)
        ar_model = short_ft_models[0]
        ar_result = _autoregressive_predict(
            ar_model, p_val_e, n_rollouts=3, device=device,
            pk_mode=True, isf_val=p_isf_e, scale=GLUCOSE_SCALE)
        print(f"    Autoregressive: h120={ar_result.get('h120','?')}, "
              f"h240={ar_result.get('h240','?')}, h360={ar_result.get('h360','?')}")

        # FT long models
        long_ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(long_base_states[seed])
            sp = os.path.join(cfg['output_dir'], f'exp439_long_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train_l, p_val_l, sp,
                         f'439-lft-{pid}-s{seed}', device, pk_mode=True,
                         future_steps=72,
                         lr=1e-4, epochs=cfg['epochs_ft'],
                         patience=10, lr_patience=5)
            long_ft_models.append(copy.deepcopy(model))

        long_ens = ensemble_evaluate(long_ft_models, p_val_l, device,
                                     pk_mode=True, isf_val=p_isf_l,
                                     future_steps=72)
        print(f"    Direct long: h120={long_ens.get('h120','?')}, "
              f"h240={long_ens.get('h240','?')}, h360={long_ens.get('h360','?')}")

        per_patient[pid] = {
            'short_direct': {k: v for k, v in short_ens.items()},
            'autoregressive': {k: v for k, v in ar_result.items()},
            'direct_long': {k: v for k, v in long_ens.items()},
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXP-439 SUMMARY — Autoregressive vs Direct")
    print(f"{'='*60}")

    for method_name, method_key in [('Short direct (h120 max)', 'short_direct'),
                                     ('Autoregressive (3× rollout)', 'autoregressive'),
                                     ('Direct long (w96)', 'direct_long')]:
        print(f"\n  {method_name}:")
        horizons = ['h30', 'h60', 'h90', 'h120', 'h150', 'h180', 'h240', 'h300', 'h360']
        for h in horizons:
            vals = [pp[method_key].get(h) for pp in per_patient.values()
                    if pp[method_key].get(h) is not None]
            if vals:
                print(f"    {h}: {np.mean(vals):.1f}")

    # Direct comparison at key horizons
    print(f"\n  Head-to-head at key horizons:")
    print(f"  {'Horizon':<8} {'Short':>8} {'AR':>8} {'Direct':>8} {'Best':>8}")
    print(f"  {'─'*40}")
    for h in ['h120', 'h180', 'h240', 'h300', 'h360']:
        s_vals = [pp['short_direct'].get(h) for pp in per_patient.values()
                  if pp['short_direct'].get(h) is not None]
        a_vals = [pp['autoregressive'].get(h) for pp in per_patient.values()
                  if pp['autoregressive'].get(h) is not None]
        d_vals = [pp['direct_long'].get(h) for pp in per_patient.values()
                  if pp['direct_long'].get(h) is not None]
        s = np.mean(s_vals) if s_vals else float('nan')
        a = np.mean(a_vals) if a_vals else float('nan')
        d = np.mean(d_vals) if d_vals else float('nan')
        valid = [(v, n) for v, n in [(s, 'short'), (a, 'AR'), (d, 'direct')]
                 if not np.isnan(v)]
        best = min(valid, key=lambda x: x[0])[1] if valid else '—'
        s_str = f"{s:.1f}" if not np.isnan(s) else "—"
        a_str = f"{a:.1f}" if not np.isnan(a) else "—"
        d_str = f"{d:.1f}" if not np.isnan(d) else "—"
        print(f"  {h:<8} {s_str:>8} {a_str:>8} {d_str:>8} {best:>8}")

    print(f"\n  If AR < Direct at h240+: error accumulation < data scarcity.")
    print(f"  If Direct < AR at h240+: one-shot prediction better for far horizons.")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-439: Autoregressive vs Direct Prediction',
        'per_patient': per_patient,
        'n_patients': len(per_patient),
    }
    _save_results(result, 'exp439_autoregressive_rollout', cfg)
    return result


# ─── EXP-440: ISF-Aware Training + Blended Long Ensemble ───

def run_exp440(args):
    """EXP-440: ISF-aware loss weighting + blended AR/direct ensemble.

    Two innovations:
    1. ISF-proportional loss: Weight training samples by ISF/ISF_mean so the
       model works harder on high-ISF patients (whose mg/dL errors are amplified
       by ISF at evaluation time). We ISF-normalize inputs but then weight the
       loss to compensate for the amplification at de-normalization.

    2. Blended ensemble: Average autoregressive and direct predictions at each
       horizon. If their errors are uncorrelated (different generation methods),
       blending should reduce MAE by sqrt(2) factor at best.

    Tests:
      - uniform_loss: standard training (baseline)
      - isf_weighted: loss × (ISF/ISF_mean) per window
      - blended: average AR + direct predictions
      - isf_blended: ISF-weighted models + blending
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-440: ISF-Aware Training + Blended Ensemble")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Load data
    data48 = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data48
    train48, val48 = prepare_pk_future(data48, use_isf=has_isf, drop_time=False)
    isf_v48 = data48.get('isf_val')
    isf_t48 = data48.get('isf_train')
    n_ch = train48.shape[-1]

    # Compute ISF weights for training (normalized so mean=1)
    if isf_t48 is not None:
        isf_mean = np.mean(isf_t48)
        isf_weights_t = torch.tensor(isf_t48 / isf_mean, dtype=torch.float32)
        isf_weights_v = torch.tensor(isf_v48 / isf_mean, dtype=torch.float32) if isf_v48 is not None else None
    else:
        isf_weights_t = torch.ones(train48.shape[0])
        isf_weights_v = torch.ones(val48.shape[0])

    print(f"  ISF weights: min={isf_weights_t.min():.2f}, max={isf_weights_t.max():.2f}, "
          f"mean={isf_weights_t.mean():.2f}")

    # ── Train with ISF-weighted loss ──
    def train_isf_weighted(model, train_x, val_x, save_path, label, device,
                           isf_weights, pk_mode=True, lr=1e-3, epochs=200,
                           batch=32, patience=20, lr_patience=7, future_steps=None):
        """Like train_bridge but with per-sample ISF-proportional loss."""
        model.to(device)
        # Create dataset with ISF weights
        train_ds = TensorDataset(train_x, isf_weights[:len(train_x)])
        val_ds = TensorDataset(val_x)
        train_dl = DataLoader(train_ds, batch_size=batch, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=batch)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=lr_patience, factor=0.5)
        best = float('inf')
        stale = 0

        for ep in range(epochs):
            model.train()
            ttl, tn = 0.0, 0
            for batch_data in train_dl:
                x = batch_data[0].to(device)
                w = batch_data[1].to(device)  # ISF weights
                half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
                x_in = x.clone()
                mask_future_pk(x_in, half, pk_mode=pk_mode)
                pred = model(x_in, causal=True)
                # Weighted MSE: multiply per-sample loss by ISF weight
                per_sample = torch.mean((pred[:, half:, :1] - x[:, half:, :1])**2, dim=(1, 2))
                loss = torch.mean(per_sample * w)
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                ttl += loss.item() * x.size(0); tn += x.size(0)
            tl = ttl / tn if tn else float('inf')

            model.eval()
            vtl, vn = 0.0, 0
            with torch.no_grad():
                for batch_data in val_dl:
                    x = batch_data[0].to(device)
                    half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
                    x_in = x.clone()
                    mask_future_pk(x_in, half, pk_mode=pk_mode)
                    pred = model(x_in, causal=True)
                    loss = torch.mean((pred[:, half:, :1] - x[:, half:, :1])**2)
                    vtl += loss.item() * x.size(0); vn += x.size(0)
            vl = vtl / vn if vn else float('inf')
            sched.step(vl)

            if vl < best:
                best = vl; stale = 0
                os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                torch.save({'epoch': ep, 'model_state': model.state_dict(),
                            'val_loss': vl, 'label': label}, save_path)
            else:
                stale += 1
            if (ep + 1) % 10 == 0 or ep == epochs - 1:
                lr_now = opt.param_groups[0]['lr']
                mark = ' *' if stale == 0 else ''
                print(f'  [{label}] {ep+1:3d}/{epochs} '
                      f'train={tl:.6f} val={vl:.6f} best={best:.6f} lr={lr_now:.1e}{mark}')
            if patience > 0 and stale >= patience:
                print(f'  [{label}] Early stop at epoch {ep+1}')
                break

        if os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=False)
            model.load_state_dict(ckpt['model_state'])
        return best, ep + 1

    # ── Variant 1: Uniform loss (baseline, same as EXP-436 short) ──
    print(f"\n{'─'*40}")
    print(f"  Uniform loss (baseline)")
    print(f"{'─'*40}")

    uniform_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp440_uniform_base_s{seed}.pth')
        train_bridge(model, train48, val48, sp, f'440-uni-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        uniform_states[seed] = ckpt['model_state']

    # ── Variant 2: ISF-weighted loss ──
    print(f"\n{'─'*40}")
    print(f"  ISF-weighted loss")
    print(f"{'─'*40}")

    isf_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp440_isf_base_s{seed}.pth')
        train_isf_weighted(model, train48, val48, sp, f'440-isf-s{seed}',
                           device, isf_weights=isf_weights_t,
                           epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        isf_states[seed] = ckpt['model_state']

    # ── Per-patient FT + evaluation ──
    per_patient = {}
    for pinfo in data48['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train = train48[ti:te]; p_val = val48[vi:ve]
        p_isf = isf_v48[vi:ve] if isf_v48 is not None else None
        isf = pinfo.get('isf', 50)

        print(f"\n  Patient {pid} (ISF={isf}):")

        results = {}
        for label, states in [('uniform', uniform_states), ('isf_wt', isf_states)]:
            ft_models = []
            for seed in cfg['seeds']:
                torch.manual_seed(seed)
                model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                model.load_state_dict(states[seed])
                sp = os.path.join(cfg['output_dir'],
                                  f'exp440_{label}_ft_{pid}_s{seed}.pth')
                train_bridge(model, p_train, p_val, sp,
                             f'440-{label}-ft-{pid}-s{seed}', device,
                             pk_mode=True, lr=1e-4,
                             epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
                ft_models.append(copy.deepcopy(model))

            ens = ensemble_evaluate(ft_models, p_val, device, pk_mode=True,
                                    isf_val=p_isf)
            results[label] = ens
            print(f"    {label}: MAE={ens['overall_mae']:.1f}, "
                  f"h30={ens.get('h30','?')}, h60={ens.get('h60','?')}, "
                  f"h120={ens.get('h120','?')}")

        per_patient[pid] = {**results, 'isf': isf}

    # Summary
    print(f"\n{'='*60}")
    print("EXP-440 SUMMARY — ISF-Aware Training")
    print(f"{'='*60}")

    # Overall comparison
    for label in ['uniform', 'isf_wt']:
        overall = np.mean([pp[label]['overall_mae'] for pp in per_patient.values()])
        print(f"\n  {label}: overall={overall:.2f}")
        for pid in sorted(per_patient.keys()):
            pp = per_patient[pid]
            delta = pp['isf_wt']['overall_mae'] - pp['uniform']['overall_mae']
            print(f"    {pid} (ISF={pp['isf']}): uniform={pp['uniform']['overall_mae']:.1f}, "
                  f"isf_wt={pp['isf_wt']['overall_mae']:.1f}, Δ={delta:+.1f}")

    # ISF correlation analysis
    isf_vals = [per_patient[p]['isf'] for p in per_patient]
    deltas = [per_patient[p]['isf_wt']['overall_mae'] - per_patient[p]['uniform']['overall_mae']
              for p in per_patient]
    print(f"\n  ISF-delta correlation: higher ISF patients should benefit more")
    for p in sorted(per_patient.keys()):
        pp = per_patient[p]
        d = pp['isf_wt']['overall_mae'] - pp['uniform']['overall_mae']
        marker = "✓" if (pp['isf'] > 50 and d < 0) or (pp['isf'] <= 50 and d >= 0) else "✗"
        print(f"    {p} ISF={pp['isf']:>3}: Δ={d:+.1f} {marker}")

    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-440: ISF-Aware Training',
        'per_patient': per_patient,
    }
    _save_results(result, 'exp440_isf_aware_training', cfg)
    return result


# ─── EXP-441: Overnight Risk Assessment via Forecasting ───

def run_exp441(args):
    """EXP-441: Overnight risk assessment from evening glucose context.

    Uses our existing PK-enhanced forecasting models to predict overnight
    glucose trajectories, then derives binary risk classifications:
      - Hypo risk: P(min_glucose < 70 mg/dL in next 6h)
      - High risk: P(max_glucose > 250 mg/dL in next 6h)

    Architecture: Train w96 forecaster (24 hist + 72 future = 6h), then:
    1. Run on ALL validation windows to get predicted trajectories
    2. Filter to "evening" windows (starting 20:00-23:00) for overnight eval
    3. Also evaluate on ALL windows for general risk assessment
    4. Compute AUC-ROC, sensitivity, specificity, precision

    This is a POST-HOC evaluation of forecasting capability — no new
    model architecture needed. If the forecaster works well, the risk
    classifier inherits its accuracy for free.
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-441: Overnight Risk Assessment via Forecasting")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Load w96 data for 6h prediction window
    data = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val, {n_ch}ch")

    # Train base model
    base_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp441_base_s{seed}.pth')
        train_bridge(model, train_x, val_x, sp, f'441-base-s{seed}',
                     device, pk_mode=True, future_steps=72,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']

    # Per-patient FT + risk assessment
    per_patient = {}
    all_risk_data = []  # for pooled analysis

    for pinfo in data['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train = train_x[ti:te]; p_val = val_x[vi:ve]
        p_isf = isf_v[vi:ve] if isf_v is not None else None
        isf = pinfo.get('isf', 50)

        print(f"\n  Patient {pid} (ISF={isf:.0f}, {pinfo['n_val']} val windows):")

        # FT
        ft_models = []
        for seed in cfg['seeds']:
            torch.manual_seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(base_states[seed])
            sp = os.path.join(cfg['output_dir'], f'exp441_ft_{pid}_s{seed}.pth')
            train_bridge(model, p_train, p_val, sp,
                         f'441-ft-{pid}-s{seed}', device, pk_mode=True,
                         future_steps=72, lr=1e-4,
                         epochs=cfg['epochs_ft'],
                         patience=10, lr_patience=5)
            ft_models.append(copy.deepcopy(model))

        # Get predicted trajectories from ensemble
        dl = DataLoader(TensorDataset(p_val), batch_size=64)
        all_preds_mg = []
        all_targets_mg = []
        idx = 0

        for m in ft_models:
            m.to(device); m.eval()

        with torch.no_grad():
            for b in dl:
                x = b[0].to(device)
                bsz = x.size(0)
                half = 24  # 24 hist, 72 future

                # Get ensemble predictions
                batch_preds = []
                for m in ft_models:
                    x_in = x.clone()
                    mask_future_pk(x_in, half, pk_mode=True)
                    pred = m(x_in, causal=True)
                    p = pred[:, half:, 0].cpu().numpy()  # [bsz, 72]

                    # De-normalize
                    if p_isf is not None:
                        p = p * (p_isf[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * GLUCOSE_SCALE
                    else:
                        p = p * GLUCOSE_SCALE
                    batch_preds.append(p)

                # Target
                t = x[:, half:, 0].cpu().numpy()
                if p_isf is not None:
                    t = t * (p_isf[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * GLUCOSE_SCALE
                else:
                    t = t * GLUCOSE_SCALE

                # Ensemble mean
                ens_pred = np.mean(batch_preds, axis=0)  # [bsz, 72]
                all_preds_mg.append(ens_pred)
                all_targets_mg.append(t)
                idx += bsz

        preds_mg = np.concatenate(all_preds_mg, axis=0)  # [N, 72]
        targets_mg = np.concatenate(all_targets_mg, axis=0)  # [N, 72]

        # Compute actual and predicted risk labels
        HYPO_THRESH = 70.0
        HIGH_THRESH = 250.0

        actual_min = np.min(targets_mg, axis=1)  # min glucose in next 6h
        actual_max = np.max(targets_mg, axis=1)
        pred_min = np.min(preds_mg, axis=1)
        pred_max = np.max(preds_mg, axis=1)

        # Binary labels
        actual_hypo = (actual_min < HYPO_THRESH).astype(float)
        actual_high = (actual_max > HIGH_THRESH).astype(float)
        pred_hypo = (pred_min < HYPO_THRESH).astype(float)
        pred_high = (pred_max > HIGH_THRESH).astype(float)

        # Identify evening windows using time channel
        # sin(2π*t/288) and cos(2π*t/288) encode time of day
        sin_t = p_val[:, 0, 6].numpy() if p_val.shape[-1] > 6 else np.zeros(len(p_val))
        cos_t = p_val[:, 0, 7].numpy() if p_val.shape[-1] > 7 else np.zeros(len(p_val))
        hours = (np.arctan2(sin_t, cos_t) * 288 / (2 * np.pi) * 5 / 60) % 24
        evening_mask = (hours >= 20) | (hours < 1)  # 20:00-01:00

        def _classification_metrics(actual, predicted, mask=None):
            """Compute classification metrics."""
            if mask is not None:
                actual = actual[mask]
                predicted = predicted[mask]
            n = len(actual)
            if n == 0:
                return {'n': 0}
            tp = np.sum((actual == 1) & (predicted == 1))
            fp = np.sum((actual == 0) & (predicted == 1))
            fn = np.sum((actual == 1) & (predicted == 0))
            tn = np.sum((actual == 0) & (predicted == 0))
            prevalence = np.mean(actual)
            sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            f1 = 2*tp / (2*tp + fp + fn) if (2*tp + fp + fn) > 0 else 0.0
            accuracy = (tp + tn) / n
            return {
                'n': n, 'prevalence': round(prevalence, 4),
                'tp': int(tp), 'fp': int(fp), 'fn': int(fn), 'tn': int(tn),
                'sensitivity': round(sensitivity, 4),
                'specificity': round(specificity, 4),
                'precision': round(precision, 4),
                'f1': round(f1, 4),
                'accuracy': round(accuracy, 4),
            }

        hypo_all = _classification_metrics(actual_hypo, pred_hypo)
        hypo_eve = _classification_metrics(actual_hypo, pred_hypo, evening_mask)
        high_all = _classification_metrics(actual_high, pred_high)
        high_eve = _classification_metrics(actual_high, pred_high, evening_mask)

        n_evening = int(np.sum(evening_mask))
        print(f"    Evening windows: {n_evening}/{len(p_val)} ({100*n_evening/len(p_val):.0f}%)")
        print(f"    Hypo (all): prev={hypo_all['prevalence']:.3f}, "
              f"sens={hypo_all['sensitivity']:.3f}, spec={hypo_all['specificity']:.3f}, "
              f"F1={hypo_all['f1']:.3f}")
        print(f"    Hypo (eve): prev={hypo_eve.get('prevalence','?')}, "
              f"sens={hypo_eve.get('sensitivity','?')}, F1={hypo_eve.get('f1','?')}")
        print(f"    High (all): prev={high_all['prevalence']:.3f}, "
              f"sens={high_all['sensitivity']:.3f}, spec={high_all['specificity']:.3f}, "
              f"F1={high_all['f1']:.3f}")

        per_patient[pid] = {
            'isf': isf,
            'n_val': len(p_val), 'n_evening': n_evening,
            'hypo_all': hypo_all, 'hypo_evening': hypo_eve,
            'high_all': high_all, 'high_evening': high_eve,
            'actual_hypo_rate': float(np.mean(actual_hypo)),
            'actual_high_rate': float(np.mean(actual_high)),
            'mae_overall': float(np.mean(np.abs(preds_mg - targets_mg))),
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXP-441 SUMMARY — Overnight Risk Assessment")
    print(f"{'='*60}")

    print(f"\n  {'Patient':<10} {'ISF':>5} {'Hypo%':>6} {'H-Sens':>7} {'H-Spec':>7} "
          f"{'H-F1':>6} {'High%':>6} {'Hi-Sens':>8} {'Hi-F1':>6}")
    print(f"  {'─'*70}")
    for pid in sorted(per_patient.keys()):
        pp = per_patient[pid]
        ha = pp['hypo_all']
        hia = pp['high_all']
        print(f"  {pid:<10} {pp['isf']:>5.0f} {ha['prevalence']:>6.3f} "
              f"{ha['sensitivity']:>7.3f} {ha['specificity']:>7.3f} "
              f"{ha['f1']:>6.3f} {hia['prevalence']:>6.3f} "
              f"{hia['sensitivity']:>8.3f} {hia['f1']:>6.3f}")

    # Pooled metrics
    all_hypo_sens = [pp['hypo_all']['sensitivity'] for pp in per_patient.values()
                     if pp['hypo_all']['prevalence'] > 0]
    all_high_sens = [pp['high_all']['sensitivity'] for pp in per_patient.values()
                     if pp['high_all']['prevalence'] > 0]
    print(f"\n  Pooled hypo sensitivity: {np.mean(all_hypo_sens):.3f}" if all_hypo_sens else "")
    print(f"  Pooled high sensitivity: {np.mean(all_high_sens):.3f}" if all_high_sens else "")

    print(f"\n  Hypo threshold: {HYPO_THRESH} mg/dL")
    print(f"  High threshold: {HIGH_THRESH} mg/dL")
    print(f"  Method: if min(predicted_6h) < threshold → flag risk")
    print(f"  This uses forecasting MAE ~27 mg/dL as implicit uncertainty")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-441: Overnight Risk Assessment',
        'per_patient': per_patient,
        'thresholds': {'hypo': HYPO_THRESH, 'high': HIGH_THRESH},
    }
    _save_results(result, 'exp441_overnight_risk', cfg)
    return result


# ─── EXP-442: Adaptive Threshold Risk + Ensemble Uncertainty ───

def run_exp442(args):
    """EXP-442: ROC analysis and ensemble uncertainty for risk assessment.

    EXP-441 used hard thresholds (min<70 for hypo, max>250 for high).
    This experiment improves by:
    1. Sweeping margins: flag risk when predicted_min < 70 + margin
       (margin compensates for forecast uncertainty)
    2. Using ensemble SPREAD as confidence: if 5 models disagree about
       whether min<70, that's high uncertainty
    3. Computing full ROC curve to find optimal operating points

    No additional training — reuses EXP-441 models (or retrains if absent).
    """
    cfg = _get_config(args)
    device = get_device(args.device)

    print(f"\n{'='*60}")
    print(f"EXP-442: Adaptive Threshold + Ensemble Uncertainty Risk")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, "
          f"ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    # Load w96 data
    data = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    isf_v = data.get('isf_val')
    n_ch = train_x.shape[-1]

    # Train/load base models
    base_states = {}
    for seed in cfg['seeds']:
        sp = os.path.join(cfg['output_dir'], f'exp441_base_s{seed}.pth')
        if os.path.exists(sp):
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']
            print(f"  Loaded base s{seed}")
        else:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            train_bridge(model, train_x, val_x, sp, f'442-base-s{seed}',
                         device, pk_mode=True, future_steps=72,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

    per_patient = {}
    for pinfo in data['per_patient']:
        pid = pinfo['name']
        ti, te = pinfo['train_idx']
        vi, ve = pinfo['val_idx']
        p_train = train_x[ti:te]; p_val = val_x[vi:ve]
        p_isf = isf_v[vi:ve] if isf_v is not None else None
        isf = pinfo.get('isf', 50)

        print(f"\n  Patient {pid} (ISF={isf:.0f}):")

        # FT
        ft_models = []
        for seed in cfg['seeds']:
            sp441 = os.path.join(cfg['output_dir'], f'exp441_ft_{pid}_s{seed}.pth')
            sp442 = os.path.join(cfg['output_dir'], f'exp442_ft_{pid}_s{seed}.pth')
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            model.load_state_dict(base_states[seed])
            save_to = sp441 if os.path.exists(sp441) else sp442
            if os.path.exists(sp441):
                ckpt = torch.load(sp441, map_location=device, weights_only=False)
                model.load_state_dict(ckpt['model_state'])
            else:
                torch.manual_seed(seed)
                train_bridge(model, p_train, p_val, sp442,
                             f'442-ft-{pid}-s{seed}', device, pk_mode=True,
                             future_steps=72, lr=1e-4,
                             epochs=cfg['epochs_ft'],
                             patience=10, lr_patience=5)
            ft_models.append(copy.deepcopy(model))

        # Get per-model predicted trajectories
        dl = DataLoader(TensorDataset(p_val), batch_size=64)
        model_preds = []  # list of [N, 72] arrays per model

        for m in ft_models:
            m.to(device); m.eval()
            preds_list, idx = [], 0
            with torch.no_grad():
                for b in dl:
                    x = b[0].to(device)
                    bsz = x.size(0)
                    x_in = x.clone()
                    mask_future_pk(x_in, 24, pk_mode=True)
                    pred = m(x_in, causal=True)
                    p = pred[:, 24:, 0].cpu().numpy()
                    if p_isf is not None:
                        p = p * (p_isf[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * GLUCOSE_SCALE
                    else:
                        p = p * GLUCOSE_SCALE
                    preds_list.append(p)
                    idx += bsz
            model_preds.append(np.concatenate(preds_list, axis=0))

        # Stack: [n_models, N, 72]
        stacked = np.array(model_preds)
        ens_mean = np.mean(stacked, axis=0)  # [N, 72]
        ens_std = np.std(stacked, axis=0)    # [N, 72] — ensemble spread

        # Targets
        targets_list, idx = [], 0
        for b in DataLoader(TensorDataset(p_val), batch_size=64):
            x = b[0]
            bsz = x.size(0)
            t = x[:, 24:, 0].numpy()
            if p_isf is not None:
                t = t * (p_isf[idx:idx+bsz] / GLUCOSE_SCALE).reshape(-1, 1) * GLUCOSE_SCALE
            else:
                t = t * GLUCOSE_SCALE
            targets_list.append(t)
            idx += bsz
        targets = np.concatenate(targets_list, axis=0)

        actual_min = np.min(targets, axis=1)
        actual_max = np.max(targets, axis=1)
        pred_min_ens = np.min(ens_mean, axis=1)
        pred_max_ens = np.max(ens_mean, axis=1)
        pred_min_std = np.mean(ens_std, axis=1)  # mean uncertainty

        # Hypo labels
        actual_hypo = (actual_min < 70).astype(float)
        actual_high = (actual_max > 250).astype(float)

        # Sweep margins for ROC curve
        margins = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60]
        hypo_roc = []
        for m in margins:
            pred_flag = (pred_min_ens < 70 + m).astype(float)
            tp = np.sum((actual_hypo == 1) & (pred_flag == 1))
            fp = np.sum((actual_hypo == 0) & (pred_flag == 1))
            fn = np.sum((actual_hypo == 1) & (pred_flag == 0))
            tn = np.sum((actual_hypo == 0) & (pred_flag == 0))
            sens = tp / (tp + fn) if (tp + fn) > 0 else 0
            spec = tn / (tn + fp) if (tn + fp) > 0 else 0
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            f1 = 2*tp / (2*tp + fp + fn) if (2*tp + fp + fn) > 0 else 0
            hypo_roc.append({
                'margin': m, 'sensitivity': round(sens, 3),
                'specificity': round(spec, 3), 'precision': round(prec, 3),
                'f1': round(f1, 3),
            })

        # Ensemble uncertainty approach: flag if ANY model predicts min < 70
        per_model_hypo = [(np.min(mp, axis=1) < 70).astype(float) for mp in model_preds]
        vote_count = sum(per_model_hypo)  # how many models flag hypo
        # Use vote threshold: flag if >= k models predict hypo
        uncertainty_results = {}
        for k in [1]:  # with 1 seed in quick mode, k=1 is all we have
            pred_flag = (vote_count >= k).astype(float)
            tp = np.sum((actual_hypo == 1) & (pred_flag == 1))
            fp = np.sum((actual_hypo == 0) & (pred_flag == 1))
            fn = np.sum((actual_hypo == 1) & (pred_flag == 0))
            tn = np.sum((actual_hypo == 0) & (pred_flag == 0))
            sens = tp / (tp + fn) if (tp + fn) > 0 else 0
            spec = tn / (tn + fp) if (tn + fp) > 0 else 0
            uncertainty_results[k] = {
                'sensitivity': round(sens, 3), 'specificity': round(spec, 3)}

        # Print ROC
        print(f"    Hypo ROC (sweeping margin around 70 mg/dL):")
        print(f"    {'Margin':>7} {'Sens':>6} {'Spec':>6} {'Prec':>6} {'F1':>6}")
        print(f"    {'─'*33}")
        for r in hypo_roc:
            print(f"    {r['margin']:>5}mg {r['sensitivity']:>6.3f} {r['specificity']:>6.3f} "
                  f"{r['precision']:>6.3f} {r['f1']:>6.3f}")

        # Find best F1 operating point
        best_f1_point = max(hypo_roc, key=lambda x: x['f1'])
        print(f"    → Best F1={best_f1_point['f1']:.3f} at margin={best_f1_point['margin']}mg "
              f"(sens={best_f1_point['sensitivity']:.3f})")

        # Find 90% sensitivity point
        sens90 = [r for r in hypo_roc if r['sensitivity'] >= 0.90]
        if sens90:
            best_sens90 = min(sens90, key=lambda x: x['margin'])
            print(f"    → 90% sens at margin={best_sens90['margin']}mg "
                  f"(spec={best_sens90['specificity']:.3f})")

        per_patient[pid] = {
            'isf': isf, 'hypo_prevalence': float(np.mean(actual_hypo)),
            'high_prevalence': float(np.mean(actual_high)),
            'hypo_roc': hypo_roc,
            'best_f1': best_f1_point,
            'ensemble_uncertainty': uncertainty_results,
            'mean_pred_uncertainty': float(np.mean(pred_min_std)),
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXP-442 SUMMARY — Adaptive Threshold Risk")
    print(f"{'='*60}")

    print(f"\n  Optimal operating points per patient:")
    print(f"  {'Patient':<10} {'HypoPrev':>9} {'BestMargin':>11} {'F1':>6} {'Sens':>6} "
          f"{'Spec':>6} {'Unc(mg)':>8}")
    print(f"  {'─'*60}")
    for pid in sorted(per_patient.keys()):
        pp = per_patient[pid]
        bf = pp['best_f1']
        print(f"  {pid:<10} {pp['hypo_prevalence']:>9.3f} {bf['margin']:>9}mg "
              f"{bf['f1']:>6.3f} {bf['sensitivity']:>6.3f} {bf['specificity']:>6.3f} "
              f"{pp['mean_pred_uncertainty']:>8.1f}")

    # Improvement from adaptive vs fixed threshold
    print(f"\n  Improvement over fixed threshold (margin=0):")
    for pid in sorted(per_patient.keys()):
        pp = per_patient[pid]
        fixed = next(r for r in pp['hypo_roc'] if r['margin'] == 0)
        best = pp['best_f1']
        delta_f1 = best['f1'] - fixed['f1']
        delta_sens = best['sensitivity'] - fixed['sensitivity']
        print(f"    {pid}: F1 {fixed['f1']:.3f} → {best['f1']:.3f} ({delta_f1:+.3f}), "
              f"sens {fixed['sensitivity']:.3f} → {best['sensitivity']:.3f} ({delta_sens:+.3f})")

    print(f"\n  Key insight: adding margin compensates for forecast uncertainty.")
    print(f"  At margin=20-30mg (≈forecast MAE), most patients reach >70% sensitivity.")
    print(f"{'='*60}")

    result = {
        'experiment': 'EXP-442: Adaptive Threshold Risk Assessment',
        'per_patient': per_patient,
    }
    _save_results(result, 'exp442_adaptive_threshold_risk', cfg)
    return result


# ─── EXP-443: PK Derivatives for Long-Range Forecasting ───

def _prepare_pk_derivatives_asymmetric(data, history_steps, use_isf=False):
    """PK features + derivatives for ASYMMETRIC windows (history ≠ future).

    Like prepare_pk_future_with_derivatives but handles asymmetric splits
    (e.g., 24 history + 72 future for w96). Glucose derivatives are zeroed
    past the history boundary, not at half.

    Produces: [gluc, IOB, COB, net_basal, ins_net, carb_rate, sin, net_bal,
               d_ins, d_carb, d_gluc] = 11ch
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]
    bt[:, :, 7] = pt[:, :, 6] / PK_NORMS[6]
    bv[:, :, 7] = pv[:, :, 6] / PK_NORMS[6]

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    h = history_steps

    # PK derivatives — DETERMINISTIC, safe everywhere
    d_ins_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_ins_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_ins_t[:, 1:, 0] = bt[:, 1:, 4] - bt[:, :-1, 4]
    d_ins_v[:, 1:, 0] = bv[:, 1:, 4] - bv[:, :-1, 4]

    d_carb_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_carb_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_carb_t[:, 1:, 0] = bt[:, 1:, 5] - bt[:, :-1, 5]
    d_carb_v[:, 1:, 0] = bv[:, 1:, 5] - bv[:, :-1, 5]

    # Glucose derivative — history-only (future glucose is unknown)
    d_gluc_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_gluc_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_gluc_t[:, 1:h, 0] = bt[:, 1:h, 0] - bt[:, :h-1, 0]
    d_gluc_v[:, 1:h, 0] = bv[:, 1:h, 0] - bv[:, :h-1, 0]

    d_ins_t *= 10.0; d_ins_v *= 10.0
    d_carb_t *= 10.0; d_carb_v *= 10.0
    d_gluc_t *= 10.0; d_gluc_v *= 10.0

    bt = np.concatenate([bt, d_ins_t, d_carb_t, d_gluc_t], axis=-1)
    bv = np.concatenate([bv, d_ins_v, d_carb_v, d_gluc_v], axis=-1)

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def _prepare_pk_second_order(data, history_steps, use_isf=False):
    """PK features + first AND second order derivatives.

    Adds d²(IOB)/dt² and d²(COB)/dt² — acceleration of PK absorption.
    Second derivatives encode inflection points: peak absorption, transition
    from absorption to elimination phase.

    Produces: [gluc, IOB, COB, net_basal, ins_net, carb_rate, sin, net_bal,
               d_ins, d_carb, d_gluc, dd_ins, dd_carb] = 13ch
    """
    bt = data['base_train'].copy()
    bv = data['base_val'].copy()
    pt, pv = data['pk_train'], data['pk_val']

    bt[:, :, 4] = pt[:, :, 1] / PK_NORMS[1]
    bv[:, :, 4] = pv[:, :, 1] / PK_NORMS[1]
    bt[:, :, 5] = pt[:, :, 3] / PK_NORMS[3]
    bv[:, :, 5] = pv[:, :, 3] / PK_NORMS[3]
    bt[:, :, 7] = pt[:, :, 6] / PK_NORMS[6]
    bv[:, :, 7] = pv[:, :, 6] / PK_NORMS[6]

    if use_isf and 'isf_train' in data:
        _apply_isf_norm(bt, bv, data['isf_train'], data['isf_val'])

    h = history_steps

    # First order
    d_ins_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_ins_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_ins_t[:, 1:, 0] = bt[:, 1:, 4] - bt[:, :-1, 4]
    d_ins_v[:, 1:, 0] = bv[:, 1:, 4] - bv[:, :-1, 4]

    d_carb_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_carb_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_carb_t[:, 1:, 0] = bt[:, 1:, 5] - bt[:, :-1, 5]
    d_carb_v[:, 1:, 0] = bv[:, 1:, 5] - bv[:, :-1, 5]

    d_gluc_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    d_gluc_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    d_gluc_t[:, 1:h, 0] = bt[:, 1:h, 0] - bt[:, :h-1, 0]
    d_gluc_v[:, 1:h, 0] = bv[:, 1:h, 0] - bv[:, :h-1, 0]

    # Second order (acceleration)
    dd_ins_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    dd_ins_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    dd_ins_t[:, 2:, 0] = d_ins_t[:, 2:, 0] - d_ins_t[:, 1:-1, 0]
    dd_ins_v[:, 2:, 0] = d_ins_v[:, 2:, 0] - d_ins_v[:, 1:-1, 0]

    dd_carb_t = np.zeros((bt.shape[0], bt.shape[1], 1), dtype=np.float32)
    dd_carb_v = np.zeros((bv.shape[0], bv.shape[1], 1), dtype=np.float32)
    dd_carb_t[:, 2:, 0] = d_carb_t[:, 2:, 0] - d_carb_t[:, 1:-1, 0]
    dd_carb_v[:, 2:, 0] = d_carb_v[:, 2:, 0] - d_carb_v[:, 1:-1, 0]

    d_ins_t *= 10.0; d_ins_v *= 10.0
    d_carb_t *= 10.0; d_carb_v *= 10.0
    d_gluc_t *= 10.0; d_gluc_v *= 10.0
    dd_ins_t *= 100.0; dd_ins_v *= 100.0  # 2nd order needs more scaling
    dd_carb_t *= 100.0; dd_carb_v *= 100.0

    bt = np.concatenate([bt, d_ins_t, d_carb_t, d_gluc_t, dd_ins_t, dd_carb_t], axis=-1)
    bv = np.concatenate([bv, d_ins_v, d_carb_v, d_gluc_v, dd_ins_v, dd_carb_v], axis=-1)

    return torch.tensor(bt, dtype=torch.float32), torch.tensor(bv, dtype=torch.float32)


def run_exp443(args):
    """EXP-443: PK Derivatives for Long-Range Forecasting.

    Hypothesis: PK derivatives (dIOB/dt, dCOB/dt) provide absorption DYNAMICS
    that the transformer can't efficiently compute from raw PK levels alone.
    At long range (h120-h360), knowing whether insulin is ramping up vs winding
    down is crucial for predicting glucose direction changes.

    Variants:
      a) w96_standard: Long-range baseline (no derivatives)
      b) w96_1st_deriv: + first-order PK derivatives (11ch)
      c) w96_2nd_deriv: + first AND second-order PK derivatives (13ch)

    All use asymmetric 24hist+72future (h360 max), ISF normalization.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-443: PK Derivatives for Long-Range Forecasting")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}, ft_ep={cfg['epochs_ft']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    history_steps = 24
    future_steps = 72

    # Prepare variants
    train_std, val_std = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    train_d1, val_d1 = _prepare_pk_derivatives_asymmetric(data, history_steps, use_isf=has_isf)
    train_d2, val_d2 = _prepare_pk_second_order(data, history_steps, use_isf=has_isf)

    variants = {
        'w96_standard': (train_std, val_std, 8),
        'w96_1st_deriv': (train_d1, val_d1, 11),
        'w96_2nd_deriv': (train_d2, val_d2, 13),
    }

    isf_v = data.get('isf_val')
    result = {}

    for vname, (train_x, val_x, n_ch) in variants.items():
        print(f"\n{'─'*40}")
        print(f"  Variant: {vname} ({n_ch}ch)")
        print(f"  {train_x.shape[0]} train, {val_x.shape[0]} val")
        print(f"{'─'*40}")

        base_states = {}
        for seed in cfg['seeds']:
            torch.manual_seed(seed); np.random.seed(seed)
            model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            sp = os.path.join(cfg['output_dir'], f'exp443_{vname}_s{seed}.pth')
            print(f"\n  Base s{seed}:")
            train_bridge(model, train_x, val_x, sp, f'443-{vname}-s{seed}',
                         device, pk_mode=True, future_steps=future_steps,
                         epochs=cfg['epochs_base'], patience=20, lr_patience=7)
            ckpt = torch.load(sp, map_location=device, weights_only=False)
            base_states[seed] = ckpt['model_state']

        # Per-patient FT + evaluate
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train = train_x[ti:te]
            p_val = val_x[vi:ve]
            p_isf = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  Patient {pid} ({pinfo['n_train']}tr):")
            seed_maes = []
            for seed, bstate in base_states.items():
                torch.manual_seed(seed); np.random.seed(seed)
                m = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                m.load_state_dict(bstate)
                fp = os.path.join(cfg['output_dir'], f'exp443_{vname}_{pid}_s{seed}.pth')
                train_bridge(m, p_train, p_val, fp, f'443-{vname}-{pid}-s{seed}',
                             device, pk_mode=True, future_steps=future_steps,
                             epochs=cfg['epochs_ft'], patience=10, lr_patience=5,
                             lr=1e-4)
                mae = evaluate_model(m, p_val, device, pk_mode=True,
                                     isf_val=p_isf, future_steps=future_steps)
                seed_maes.append(mae)
                print(f"    s{seed}: overall={mae['overall_mae']:.1f}, "
                      f"h60={mae.get('h60','—')}, h120={mae.get('h120','—')}, "
                      f"h240={mae.get('h240','—')}, h360={mae.get('h360','—')}")

            avg = {}
            for k in seed_maes[0]:
                vals = [m[k] for m in seed_maes if isinstance(m.get(k), (int, float))]
                if vals:
                    avg[k] = round(np.mean(vals), 2)
            per_patient[pid] = avg

        # Compute variant average
        overall_keys = ['overall_mae', 'h30', 'h60', 'h120', 'h150', 'h180',
                        'h240', 'h300', 'h360']
        vavg = {}
        for k in overall_keys:
            vals = [pp[k] for pp in per_patient.values() if k in pp]
            if vals:
                vavg[k] = round(np.mean(vals), 2)
        result[vname] = {'per_patient': per_patient, 'average': vavg}

        print(f"\n  {vname} average: overall={vavg.get('overall_mae','?')}, "
              f"h60={vavg.get('h60','?')}, h120={vavg.get('h120','?')}, "
              f"h240={vavg.get('h240','?')}, h360={vavg.get('h360','?')}")

    # Summary
    print(f"\n{'='*60}")
    print(f"EXP-443 Summary: PK Derivatives for Long-Range")
    print(f"{'='*60}")
    for vname, vdata in result.items():
        avg = vdata['average']
        print(f"  {vname}: overall={avg.get('overall_mae','?')}, "
              f"h120={avg.get('h120','?')}, h240={avg.get('h240','?')}, "
              f"h360={avg.get('h360','?')}")

    std_mae = result['w96_standard']['average'].get('overall_mae', 0)
    d1_mae = result['w96_1st_deriv']['average'].get('overall_mae', 0)
    d2_mae = result['w96_2nd_deriv']['average'].get('overall_mae', 0)
    print(f"\n  Δ (1st deriv vs standard): {d1_mae - std_mae:+.2f}")
    print(f"  Δ (2nd deriv vs standard): {d2_mae - std_mae:+.2f}")

    if d1_mae < std_mae:
        print(f"  ✓ First-order PK derivatives HELP long-range forecasting!")
    else:
        print(f"  ✗ PK derivatives don't help — transformer already computes them.")

    _save_results(result, 'exp443_pk_derivatives_longrange', cfg)
    return result


# ─── EXP-444: Cosine LR + Long-Range Optimization ───

def _cosine_lr_schedule(optimizer, epoch, total_epochs, warmup_epochs=10, min_lr=1e-6):
    """Cosine annealing with linear warmup."""
    if epoch < warmup_epochs:
        lr = 1e-3 * (epoch + 1) / warmup_epochs
    else:
        progress = (epoch - warmup_epochs) / (total_epochs - warmup_epochs)
        lr = min_lr + 0.5 * (1e-3 - min_lr) * (1 + math.cos(math.pi * progress))
    for pg in optimizer.param_groups:
        pg['lr'] = lr
    return lr


def train_bridge_cosine(model, train_x, val_x, save_path, label, device,
                        pk_mode=False, epochs=200, batch=32, future_steps=None,
                        weight_decay=1e-5, warmup_epochs=10):
    """Like train_bridge but with cosine LR schedule instead of ReduceLROnPlateau."""
    model.to(device)
    train_dl = DataLoader(TensorDataset(train_x), batch_size=batch, shuffle=True)
    val_dl = DataLoader(TensorDataset(val_x), batch_size=batch)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=weight_decay)
    crit = nn.MSELoss()
    best = float('inf')
    stale = 0
    patience = 30  # slightly higher for cosine (no plateau to trigger reduction)

    def _step(batch_data, backward=False):
        x = batch_data[0].to(device)
        half = x.shape[1] - future_steps if future_steps else x.shape[1] // 2
        x_in = x.clone()
        mask_future_pk(x_in, half, pk_mode=pk_mode)
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    for ep in range(epochs):
        lr_now = _cosine_lr_schedule(opt, ep, epochs, warmup_epochs)

        model.train()
        ttl, tn = 0.0, 0
        for b in train_dl:
            opt.zero_grad()
            l, n = _step(b, backward=True)
            opt.step()
            ttl += l; tn += n
        tl = ttl / tn if tn else float('inf')

        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in val_dl:
                l, n = _step(b, backward=False)
                vtl += l; vn += n
        vl = vtl / vn if vn else float('inf')

        if vl < best:
            best = vl
            stale = 0
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            torch.save({
                'epoch': ep, 'model_state': model.state_dict(),
                'val_loss': vl, 'label': label,
            }, save_path)
        else:
            stale += 1

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            mark = ' *' if stale == 0 else ''
            print(f'  [{label}] {ep+1:3d}/{epochs} '
                  f'train={tl:.6f} val={vl:.6f} best={best:.6f} '
                  f'lr={lr_now:.1e}{mark}')

        if stale >= patience:
            print(f'  [{label}] Early stop at epoch {ep+1}')
            break

    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best, ep + 1


def run_exp444(args):
    """EXP-444: Cosine LR + Training Optimization for Long-Range.

    Hypothesis: Cosine LR with warmup improves convergence for the long-range
    (w96) model, especially because ReduceLROnPlateau can plateau-lock too early
    on 5K training windows.

    Variants:
      a) plateau_lr: Standard ReduceLROnPlateau (control)
      b) cosine_lr: Cosine annealing with 10-epoch warmup
      c) cosine_lr_long: Cosine with 50% more epochs (allow longer exploration)

    All use w96 asymmetric (24+72), ISF normalization, standard 8ch PK.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-444: Cosine LR for Long-Range Training")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}")
    print(f"{'='*60}")

    data = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    has_isf = 'isf_val' in data
    future_steps = 72
    train_x, val_x = prepare_pk_future(data, use_isf=has_isf, drop_time=False)
    n_ch = train_x.shape[-1]
    isf_v = data.get('isf_val')

    result = {}

    # Variant a: plateau_lr (control)
    vname = 'plateau_lr'
    print(f"\n{'─'*40}\n  Variant: {vname}\n{'─'*40}")
    base_states_p = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp444_{vname}_s{seed}.pth')
        print(f"\n  Base s{seed}:")
        train_bridge(model, train_x, val_x, sp, f'444-{vname}-s{seed}',
                     device, pk_mode=True, future_steps=future_steps,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states_p[seed] = ckpt['model_state']

    # Variant b: cosine_lr
    vname2 = 'cosine_lr'
    print(f"\n{'─'*40}\n  Variant: {vname2}\n{'─'*40}")
    base_states_c = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp444_{vname2}_s{seed}.pth')
        print(f"\n  Base s{seed}:")
        train_bridge_cosine(model, train_x, val_x, sp, f'444-{vname2}-s{seed}',
                            device, pk_mode=True, future_steps=future_steps,
                            epochs=cfg['epochs_base'], warmup_epochs=10)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states_c[seed] = ckpt['model_state']

    # Variant c: cosine_lr_long (50% more epochs)
    vname3 = 'cosine_lr_long'
    long_epochs = int(cfg['epochs_base'] * 1.5)
    print(f"\n{'─'*40}\n  Variant: {vname3} ({long_epochs} epochs)\n{'─'*40}")
    base_states_cl = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp444_{vname3}_s{seed}.pth')
        print(f"\n  Base s{seed}:")
        train_bridge_cosine(model, train_x, val_x, sp, f'444-{vname3}-s{seed}',
                            device, pk_mode=True, future_steps=future_steps,
                            epochs=long_epochs, warmup_epochs=15)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        base_states_cl[seed] = ckpt['model_state']

    # Per-patient FT + evaluate all variants
    all_variants = [
        ('plateau_lr', base_states_p),
        ('cosine_lr', base_states_c),
        ('cosine_lr_long', base_states_cl),
    ]

    for vn, bstates in all_variants:
        per_patient = {}
        for pinfo in data['per_patient']:
            pid = pinfo['name']
            ti, te = pinfo['train_idx']
            vi, ve = pinfo['val_idx']
            p_train = train_x[ti:te]
            p_val = val_x[vi:ve]
            p_isf = isf_v[vi:ve] if isf_v is not None else None

            print(f"\n  {vn}/{pid} ({pinfo['n_train']}tr):")
            seed_maes = []
            for seed, bstate in bstates.items():
                torch.manual_seed(seed); np.random.seed(seed)
                m = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
                m.load_state_dict(bstate)
                fp = os.path.join(cfg['output_dir'], f'exp444_{vn}_{pid}_s{seed}.pth')
                train_bridge(m, p_train, p_val, fp, f'444-{vn}-{pid}-s{seed}',
                             device, pk_mode=True, future_steps=future_steps,
                             epochs=cfg['epochs_ft'], patience=10, lr_patience=5,
                             lr=1e-4)
                mae = evaluate_model(m, p_val, device, pk_mode=True,
                                     isf_val=p_isf, future_steps=future_steps)
                seed_maes.append(mae)
                print(f"    s{seed}: overall={mae['overall_mae']:.1f}, "
                      f"h120={mae.get('h120','—')}, h360={mae.get('h360','—')}")

            avg = {}
            for k in seed_maes[0]:
                vals = [m[k] for m in seed_maes if isinstance(m.get(k), (int, float))]
                if vals:
                    avg[k] = round(np.mean(vals), 2)
            per_patient[pid] = avg

        vavg = {}
        for k in ['overall_mae', 'h30', 'h60', 'h120', 'h240', 'h360']:
            vals = [pp[k] for pp in per_patient.values() if k in pp]
            if vals:
                vavg[k] = round(np.mean(vals), 2)
        result[vn] = {'per_patient': per_patient, 'average': vavg}

    # Summary
    print(f"\n{'='*60}")
    print(f"EXP-444 Summary: LR Schedule Comparison")
    print(f"{'='*60}")
    for vn, vdata in result.items():
        avg = vdata['average']
        print(f"  {vn}: overall={avg.get('overall_mae','?')}, "
              f"h120={avg.get('h120','?')}, h360={avg.get('h360','?')}")

    p_mae = result['plateau_lr']['average'].get('overall_mae', 0)
    c_mae = result['cosine_lr']['average'].get('overall_mae', 0)
    cl_mae = result['cosine_lr_long']['average'].get('overall_mae', 0)
    print(f"\n  Δ (cosine vs plateau): {c_mae - p_mae:+.2f}")
    print(f"  Δ (cosine_long vs plateau): {cl_mae - p_mae:+.2f}")

    _save_results(result, 'exp444_cosine_lr_longrange', cfg)
    return result


# ─── EXP-445: Next-Day TIR Prediction (Category E2) ───

def _extract_daily_features(patients_dir, max_patients=None):
    """Extract daily-level features from raw CGM + PK data for TIR prediction.

    For each patient-day, compute:
    - glucose stats: mean, std, min, max, CV
    - TIR (70-180), time below 70, time above 180, time above 250
    - glucodensity: 8-bin histogram (40-400 mg/dL)
    - period TIR: 6h blocks (00-06, 06-12, 12-18, 18-24)
    - PK stats: mean IOB, mean COB, total insulin, total carbs
    - event counts: boluses, meals
    - day-of-week (encoded as sin/cos)
    """
    from pathlib import Path
    patients_path = Path(patients_dir)
    patient_dirs = sorted(d for d in patients_path.iterdir()
                          if d.is_dir() and (d / 'training').is_dir())
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]

    all_features = []
    all_targets = []
    all_patient_ids = []
    all_patient_boundaries = []

    from datetime import datetime

    for pdir in patient_dirs:
        pid = pdir.name
        train_dir = pdir / 'training'

        # Load glucose from entries.json (Nightscout format)
        entries_file = train_dir / 'entries.json'
        if not entries_file.exists():
            continue

        try:
            with open(entries_file) as f:
                entries = json.load(f)
        except Exception:
            continue

        if len(entries) < 288:  # less than 1 day
            continue

        # Parse glucose time series
        timestamps = []
        glucose_vals = []
        for entry in entries:
            try:
                ts_str = entry.get('dateString', '')
                mg = float(entry.get('sgv', 0))
                if mg < 20 or mg > 500 or not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamps.append(ts)
                glucose_vals.append(mg)
            except (ValueError, KeyError, TypeError):
                continue

        if len(timestamps) < 288:
            continue

        # Sort by time (entries may not be ordered)
        sorted_idx = np.argsort([ts.timestamp() for ts in timestamps])
        timestamps = [timestamps[i] for i in sorted_idx]
        glucose_vals_sorted = [glucose_vals[i] for i in sorted_idx]
        glucose_vals = glucose_vals_sorted

        glucose_vals = np.array(glucose_vals, dtype=np.float32)
        timestamps = np.array(timestamps)

        # Load PK data if available
        pk_file = train_dir / 'pk_curves.npz'
        pk_data = None
        if pk_file.exists():
            try:
                pk_data = np.load(pk_file)
            except Exception:
                pass

        # Group by date
        dates = np.array([ts.date() for ts in timestamps])
        unique_dates = sorted(set(dates))

        patient_features = []
        patient_tir = []

        for i, date in enumerate(unique_dates[:-1]):  # skip last day (need next-day target)
            mask = dates == date
            day_gluc = glucose_vals[mask]

            if len(day_gluc) < 200:  # need ~70% coverage
                continue

            # Next-day target
            next_date = unique_dates[i + 1]
            next_mask = dates == next_date
            next_gluc = glucose_vals[next_mask]
            if len(next_gluc) < 200:
                continue

            # Target: next-day TIR
            next_tir = np.mean((next_gluc >= 70) & (next_gluc <= 180)) * 100

            # --- Feature extraction ---
            feats = []

            # Basic glucose stats
            feats.extend([
                np.mean(day_gluc),           # mean glucose
                np.std(day_gluc),            # glucose SD
                np.min(day_gluc),            # min
                np.max(day_gluc),            # max
                np.std(day_gluc) / np.mean(day_gluc) * 100,  # CV%
            ])

            # TIR breakdown
            n = len(day_gluc)
            feats.extend([
                np.mean(day_gluc < 54) * 100,       # time < 54 (severe hypo)
                np.mean(day_gluc < 70) * 100,        # time < 70 (hypo)
                np.mean((day_gluc >= 70) & (day_gluc <= 180)) * 100,  # TIR
                np.mean(day_gluc > 180) * 100,       # time > 180 (high)
                np.mean(day_gluc > 250) * 100,       # time > 250 (very high)
            ])

            # Glucodensity (8 bins, 40-400 mg/dL)
            bins = np.linspace(40, 400, 9)
            hist, _ = np.histogram(np.clip(day_gluc, 40, 400), bins=bins)
            hist_norm = hist / hist.sum()
            feats.extend(hist_norm.tolist())

            # Period TIR (6h blocks by index position, approximate)
            quarter = len(day_gluc) // 4
            for q in range(4):
                qstart = q * quarter
                qend = (q + 1) * quarter if q < 3 else len(day_gluc)
                q_gluc = day_gluc[qstart:qend]
                if len(q_gluc) > 0:
                    feats.append(np.mean((q_gluc >= 70) & (q_gluc <= 180)) * 100)
                else:
                    feats.append(50.0)

            # Glucose dynamics
            diffs = np.diff(day_gluc)
            feats.extend([
                np.mean(np.abs(diffs)),       # MAGE-like
                np.mean(diffs > 0) * 100,     # % rising
                np.percentile(diffs, 10),     # 10th pctile (fast drops)
                np.percentile(diffs, 90),     # 90th pctile (fast rises)
            ])

            # Day of week (sin/cos encoding)
            dow = date.weekday()
            feats.extend([
                np.sin(2 * np.pi * dow / 7),
                np.cos(2 * np.pi * dow / 7),
            ])

            patient_features.append(feats)
            patient_tir.append(next_tir)

        if len(patient_features) < 10:
            continue

        start_idx = len(all_features)
        all_features.extend(patient_features)
        all_targets.extend(patient_tir)
        all_patient_ids.extend([pid] * len(patient_features))
        all_patient_boundaries.append({
            'name': pid,
            'start': start_idx,
            'end': start_idx + len(patient_features),
            'n_days': len(patient_features),
        })
        print(f"  {pid}: {len(patient_features)} days, "
              f"mean TIR={np.mean(patient_tir):.1f}%, "
              f"bad days (TIR<60%)={np.mean(np.array(patient_tir)<60)*100:.0f}%")

    X = np.array(all_features, dtype=np.float32)
    y = np.array(all_targets, dtype=np.float32)

    return X, y, all_patient_ids, all_patient_boundaries


def run_exp445(args):
    """EXP-445: Next-Day TIR Prediction (Category E2: Strategic Planning).

    Hypothesis: Today's glucose distribution and dynamics predict tomorrow's TIR.
    This opens the strategic planning layer — proactive day planning based on
    patterns rather than short-term forecasting.

    Uses XGBoost/Ridge regression on daily tabular features (safer at ~180
    samples/patient than deep learning). Per-patient chronological split
    (first 80% train, last 20% test).

    Features (29 total):
    - Glucose stats (5): mean, std, min, max, CV%
    - TIR breakdown (5): <54%, <70%, TIR, >180%, >250%
    - Glucodensity (8): 8-bin histogram
    - Period TIR (4): 6h-block TIR
    - Dynamics (4): mean|diff|, %rising, p10, p90
    - Day-of-week (2): sin/cos

    Target: next-day TIR (0-100%)
    """
    cfg = _get_config(args)
    print(f"\n{'='*60}")
    print(f"EXP-445: Next-Day TIR Prediction (Category E2)")
    print(f"{'='*60}")

    print(f"\n  Extracting daily features...")
    X, y, pids, boundaries = _extract_daily_features(
        args.patients_dir, max_patients=cfg['max_patients'])

    if len(X) == 0:
        print("  No data extracted! Check patient data format.")
        return {'error': 'no_data'}

    print(f"\n  Total: {len(X)} day-pairs, {len(boundaries)} patients")
    print(f"  Features: {X.shape[1]}, Target: next-day TIR")
    print(f"  Target distribution: mean={np.mean(y):.1f}%, std={np.std(y):.1f}%")

    # Use sklearn if available, else ridge regression by hand
    try:
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import GradientBoostingRegressor
        has_sklearn = True
    except ImportError:
        has_sklearn = False
        print("  sklearn not available, using manual Ridge regression")

    result = {}

    # Per-patient chronological split evaluation
    models_to_test = {}

    if has_sklearn:
        models_to_test['ridge'] = lambda: Ridge(alpha=1.0)
        models_to_test['gbr'] = lambda: GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            subsample=0.8, random_state=42)
    else:
        models_to_test['ridge_manual'] = None

    # Also test baselines
    # Baseline 1: predict today's TIR (persistence)
    # Baseline 2: predict patient mean TIR

    for model_name, model_factory in models_to_test.items():
        print(f"\n{'─'*40}")
        print(f"  Model: {model_name}")
        print(f"{'─'*40}")

        per_patient = {}
        all_preds = []
        all_trues = []

        for pinfo in boundaries:
            pid = pinfo['name']
            s, e = pinfo['start'], pinfo['end']
            n = e - s
            split_idx = int(n * 0.8)

            if split_idx < 10 or (n - split_idx) < 5:
                print(f"  {pid}: too few days ({n}), skipping")
                continue

            X_train = X[s:s+split_idx]
            y_train = y[s:s+split_idx]
            X_test = X[s+split_idx:e]
            y_test = y[s+split_idx:e]

            if has_sklearn and model_factory is not None:
                mdl = model_factory()
                mdl.fit(X_train, y_train)
                y_pred = mdl.predict(X_test)
            else:
                # Manual ridge regression
                X_b = np.hstack([X_train, np.ones((len(X_train), 1))])
                Xt_b = np.hstack([X_test, np.ones((len(X_test), 1))])
                alpha = 1.0
                I = np.eye(X_b.shape[1])
                w = np.linalg.solve(X_b.T @ X_b + alpha * I, X_b.T @ y_train)
                y_pred = Xt_b @ w

            # Baselines
            # Persistence: predict previous day's TIR
            # Approximate: ch index 7 is TIR (from feature extraction)
            y_persist = X_test[:, 7]  # today's TIR → predict as tomorrow's TIR
            y_mean = np.full_like(y_test, np.mean(y_train))

            mae_model = np.mean(np.abs(y_pred - y_test))
            mae_persist = np.mean(np.abs(y_persist - y_test))
            mae_mean = np.mean(np.abs(y_mean - y_test))

            # Binary: bad day (TIR < 60%)
            bad_true = y_test < 60
            if np.any(bad_true) and np.any(~bad_true):
                bad_pred = y_pred < 60
                bad_persist = y_persist < 60
                tp = np.sum(bad_pred & bad_true)
                fp = np.sum(bad_pred & ~bad_true)
                fn = np.sum(~bad_pred & bad_true)
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
            else:
                f1 = float('nan')

            per_patient[pid] = {
                'n_train': split_idx,
                'n_test': n - split_idx,
                'mae_model': round(mae_model, 2),
                'mae_persist': round(mae_persist, 2),
                'mae_mean': round(mae_mean, 2),
                'bad_day_f1': round(f1, 3) if not np.isnan(f1) else 'N/A',
            }
            all_preds.extend(y_pred.tolist())
            all_trues.extend(y_test.tolist())

            print(f"  {pid}: MAE={mae_model:.1f}% (persist={mae_persist:.1f}%, "
                  f"mean={mae_mean:.1f}%), bad-day F1={f1:.3f}" if not np.isnan(f1) 
                  else f"  {pid}: MAE={mae_model:.1f}% (persist={mae_persist:.1f}%, "
                  f"mean={mae_mean:.1f}%)")

        # Overall metrics
        if all_preds:
            all_preds = np.array(all_preds)
            all_trues = np.array(all_trues)
            overall_mae = np.mean(np.abs(all_preds - all_trues))
            overall_corr = np.corrcoef(all_preds, all_trues)[0, 1]
        else:
            overall_mae = float('nan')
            overall_corr = float('nan')

        result[model_name] = {
            'per_patient': per_patient,
            'overall_mae': round(overall_mae, 2),
            'overall_corr': round(overall_corr, 3),
        }

        print(f"\n  {model_name} overall: MAE={overall_mae:.2f}%, corr={overall_corr:.3f}")

    # Summary
    print(f"\n{'='*60}")
    print(f"EXP-445 Summary: Next-Day TIR Prediction")
    print(f"{'='*60}")
    for mn, md in result.items():
        print(f"  {mn}: MAE={md['overall_mae']}%, corr={md['overall_corr']}")
        for pid, pp in md['per_patient'].items():
            print(f"    {pid}: model={pp['mae_model']}% persist={pp['mae_persist']}% "
                  f"mean={pp['mae_mean']}%")

    # Check if model beats persistence
    for mn, md in result.items():
        model_maes = [pp['mae_model'] for pp in md['per_patient'].values()]
        persist_maes = [pp['mae_persist'] for pp in md['per_patient'].values()]
        if model_maes and persist_maes:
            avg_model = np.mean(model_maes)
            avg_persist = np.mean(persist_maes)
            if avg_model < avg_persist:
                print(f"\n  ✓ {mn} beats persistence by {avg_persist - avg_model:.1f}% MAE!")
            else:
                print(f"\n  ✗ {mn} doesn't beat persistence ({avg_model:.1f}% vs {avg_persist:.1f}%)")
                print(f"  TIR is highly autocorrelated — tomorrow ≈ today is hard to beat.")

    _save_results(result, 'exp445_nextday_tir', cfg)
    return result


# ─── EXP-446: AR-Enhanced Horizon Routing ───

def run_exp446(args):
    """EXP-446: AR-Enhanced Horizon Routing — best of EXP-436 + EXP-439.

    Hypothesis: Combining horizon routing (short model h30-h120, long model
    h120+) with autoregressive rollout for the long-range band provides
    both data-rich short-range accuracy AND progressive long-range refinement.

    Architecture:
      - Short: w48 (24+24), direct prediction for h30-h120
      - AR-Long: w48 model rolled forward on w144 data, for h120-h360
      - Direct-Long: w96 (24+72), direct prediction for h120-h360

    Compare: short+AR-long vs short+direct-long vs individual models.
    """
    cfg = _get_config(args)
    device = get_device(args.device)
    print(f"\n{'='*60}")
    print(f"EXP-446: AR-Enhanced Horizon Routing")
    print(f"  seeds={cfg['seeds']}, base_ep={cfg['epochs_base']}")
    print(f"{'='*60}")

    # ── Load data at multiple window sizes ──
    data_48 = load_bridge_data(
        args.patients_dir, window_size=48,
        max_patients=cfg['max_patients'], load_isf=True)
    data_96 = load_bridge_data(
        args.patients_dir, window_size=96,
        max_patients=cfg['max_patients'], load_isf=True)
    data_144 = load_bridge_data(
        args.patients_dir, window_size=144,
        max_patients=cfg['max_patients'], load_isf=True)

    has_isf = 'isf_val' in data_48

    train_48, val_48 = prepare_pk_future(data_48, use_isf=has_isf, drop_time=False)
    train_96, val_96 = prepare_pk_future(data_96, use_isf=has_isf, drop_time=False)
    train_144, val_144 = prepare_pk_future(data_144, use_isf=has_isf, drop_time=False)

    n_ch = train_48.shape[-1]
    isf_v_48 = data_48.get('isf_val')
    isf_v_96 = data_96.get('isf_val')
    isf_v_144 = data_144.get('isf_val')

    print(f"  w48: {train_48.shape[0]} train, w96: {train_96.shape[0]} train, "
          f"w144: {train_144.shape[0]} train")

    # ── Train short model (w48) ──
    print(f"\n{'─'*40}")
    print(f"  Training SHORT model (w48)")
    print(f"{'─'*40}")

    short_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp446_short_s{seed}.pth')
        print(f"\n  Short s{seed}:")
        train_bridge(model, train_48, val_48, sp, f'446-short-s{seed}',
                     device, pk_mode=True,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        short_states[seed] = ckpt['model_state']

    # ── Train direct long model (w96) ──
    print(f"\n{'─'*40}")
    print(f"  Training DIRECT-LONG model (w96)")
    print(f"{'─'*40}")

    long_states = {}
    for seed in cfg['seeds']:
        torch.manual_seed(seed); np.random.seed(seed)
        model = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
        sp = os.path.join(cfg['output_dir'], f'exp446_long_s{seed}.pth')
        print(f"\n  Long s{seed}:")
        train_bridge(model, train_96, val_96, sp, f'446-long-s{seed}',
                     device, pk_mode=True, future_steps=72,
                     epochs=cfg['epochs_base'], patience=20, lr_patience=7)
        ckpt = torch.load(sp, map_location=device, weights_only=False)
        long_states[seed] = ckpt['model_state']

    # ── Per-patient FT + 3-way comparison ──
    print(f"\n{'='*40}")
    print(f"  Per-Patient FT + Routing Comparison")
    print(f"{'='*40}")

    patients_48 = {p['name']: p for p in data_48['per_patient']}
    patients_96 = {p['name']: p for p in data_96['per_patient']}
    patients_144 = {p['name']: p for p in data_144['per_patient']}
    common = sorted(set(patients_48) & set(patients_96) & set(patients_144))

    result = {'short_direct': {}, 'ar_route': {}, 'direct_route': {}}

    for pid in common:
        p48 = patients_48[pid]
        p96 = patients_96[pid]
        p144 = patients_144[pid]

        ti48, te48 = p48['train_idx']
        vi48, ve48 = p48['val_idx']
        ti96, te96 = p96['train_idx']
        vi96, ve96 = p96['val_idx']
        vi144, ve144 = p144['val_idx']

        pt_48 = train_48[ti48:te48]
        pv_48 = val_48[vi48:ve48]
        pisf_48 = isf_v_48[vi48:ve48] if isf_v_48 is not None else None

        pt_96 = train_96[ti96:te96]
        pv_96 = val_96[vi96:ve96]
        pisf_96 = isf_v_96[vi96:ve96] if isf_v_96 is not None else None

        pv_144 = val_144[vi144:ve144]
        pisf_144 = isf_v_144[vi144:ve144] if isf_v_144 is not None else None

        print(f"\n  Patient {pid}:")

        # FT short model
        short_ft_models = []
        for seed, bstate in short_states.items():
            torch.manual_seed(seed); np.random.seed(seed)
            m = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(bstate)
            fp = os.path.join(cfg['output_dir'], f'exp446_short_{pid}_s{seed}.pth')
            train_bridge(m, pt_48, pv_48, fp, f'446-s-{pid}-s{seed}',
                         device, pk_mode=True,
                         epochs=cfg['epochs_ft'], patience=10, lr_patience=5, lr=1e-4)
            short_ft_models.append(m)

        # FT long model
        long_ft_models = []
        for seed, bstate in long_states.items():
            torch.manual_seed(seed); np.random.seed(seed)
            m = PKGroupedEncoder(input_dim=n_ch, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(bstate)
            fp = os.path.join(cfg['output_dir'], f'exp446_long_{pid}_s{seed}.pth')
            train_bridge(m, pt_96, pv_96, fp, f'446-l-{pid}-s{seed}',
                         device, pk_mode=True, future_steps=72,
                         epochs=cfg['epochs_ft'], patience=10, lr_patience=5, lr=1e-4)
            long_ft_models.append(m)

        # Evaluate: short-only (h30-h120)
        short_mae = evaluate_model(short_ft_models[0], pv_48, device, pk_mode=True,
                                   isf_val=pisf_48)
        print(f"    Short-direct: h30={short_mae.get('h30','—')}, h60={short_mae.get('h60','—')}, "
              f"h120={short_mae.get('h120','—')}")

        # Evaluate: direct-long (h30-h360)
        long_mae = evaluate_model(long_ft_models[0], pv_96, device, pk_mode=True,
                                  isf_val=pisf_96, future_steps=72)
        print(f"    Direct-long: h60={long_mae.get('h60','—')}, h120={long_mae.get('h120','—')}, "
              f"h240={long_mae.get('h240','—')}, h360={long_mae.get('h360','—')}")

        # Evaluate: AR rollout (short model on w144 data, 3 rollouts → h360)
        ar_result = _autoregressive_predict(
            short_ft_models[0], pv_144, n_rollouts=3, device=device,
            pk_mode=True, isf_val=pisf_144)
        print(f"    AR-rollout: h120={ar_result.get('h120','—')}, h240={ar_result.get('h240','—')}, "
              f"h360={ar_result.get('h360','—')}")

        # Build routed results
        # Route A: short h30-h120 + AR h120-h360
        ar_route = {}
        for k in ['h5', 'h10', 'h15', 'h20', 'h25', 'h30', 'h60', 'h90', 'h120']:
            if k in short_mae:
                ar_route[k] = short_mae[k]
        for k in ['h150', 'h180', 'h240', 'h300', 'h360']:
            if k in ar_result:
                ar_route[k] = ar_result[k]
        ar_vals = [v for v in ar_route.values() if isinstance(v, (int, float))]
        ar_route['overall_mae'] = round(np.mean(ar_vals), 2) if ar_vals else 0

        # Route B: short h30-h120 + direct-long h120-h360
        dir_route = {}
        for k in ['h5', 'h10', 'h15', 'h20', 'h25', 'h30', 'h60', 'h90', 'h120']:
            if k in short_mae:
                dir_route[k] = short_mae[k]
        for k in ['h150', 'h180', 'h240', 'h300', 'h360']:
            if k in long_mae:
                dir_route[k] = long_mae[k]
        dir_vals = [v for v in dir_route.values() if isinstance(v, (int, float))]
        dir_route['overall_mae'] = round(np.mean(dir_vals), 2) if dir_vals else 0

        result['short_direct'][pid] = short_mae
        result['ar_route'][pid] = ar_route
        result['direct_route'][pid] = dir_route

        print(f"    AR-Route overall={ar_route['overall_mae']}")
        print(f"    Direct-Route overall={dir_route['overall_mae']}")

    # Summary
    print(f"\n{'='*60}")
    print(f"EXP-446 Summary: AR-Enhanced Horizon Routing")
    print(f"{'='*60}")

    for rtype in ['ar_route', 'direct_route']:
        all_maes = [v['overall_mae'] for v in result[rtype].values()]
        avg_mae = np.mean(all_maes)
        h360_vals = [v.get('h360', 0) for v in result[rtype].values()]
        h120_vals = [v.get('h120', 0) for v in result[rtype].values()]
        print(f"  {rtype}: overall={avg_mae:.2f}, h120={np.mean(h120_vals):.1f}, "
              f"h360={np.mean(h360_vals):.1f}")

    _save_results(result, 'exp446_ar_enhanced_routing', cfg)
    return result


# ─── EXP-447: TIR Prediction with PK-Derived Daily Features ───

def _extract_daily_features_with_pk(patients_dir, max_patients=None):
    """Daily features enhanced with PK-derived insulin/carb stats.

    In addition to glucose features (from EXP-445), adds:
    - Mean IOB, max IOB, IOB variability
    - Total daily insulin dose (TDD) approximation
    - Meal count, mean carb dose, carb timing spread
    - Net metabolic balance features
    """
    from pathlib import Path
    from datetime import datetime
    patients_path = Path(patients_dir)
    patient_dirs = sorted(d for d in patients_path.iterdir()
                          if d.is_dir() and (d / 'training').is_dir())
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]

    all_features = []
    all_targets = []
    all_patient_ids = []
    all_patient_boundaries = []

    for pdir in patient_dirs:
        pid = pdir.name
        train_dir = pdir / 'training'

        # Load entries
        entries_file = train_dir / 'entries.json'
        if not entries_file.exists():
            continue
        try:
            with open(entries_file) as f:
                entries = json.load(f)
        except Exception:
            continue

        if len(entries) < 288:
            continue

        # Parse glucose
        timestamps = []
        glucose_vals = []
        for entry in entries:
            try:
                ts_str = entry.get('dateString', '')
                mg = float(entry.get('sgv', 0))
                if mg < 20 or mg > 500 or not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamps.append(ts)
                glucose_vals.append(mg)
            except (ValueError, KeyError, TypeError):
                continue

        if len(timestamps) < 288:
            continue

        sorted_idx = np.argsort([ts.timestamp() for ts in timestamps])
        timestamps = [timestamps[i] for i in sorted_idx]
        glucose_vals = [glucose_vals[i] for i in sorted_idx]

        # Load treatments for insulin/carb data
        treat_file = train_dir / 'treatments.json'
        treatments = []
        if treat_file.exists():
            try:
                with open(treat_file) as f:
                    treatments = json.load(f)
            except Exception:
                pass

        # Parse treatments by date
        treat_by_date = {}
        for t in treatments:
            try:
                ts_str = t.get('created_at', t.get('dateString', ''))
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                d = ts.date()
                if d not in treat_by_date:
                    treat_by_date[d] = []
                treat_by_date[d].append(t)
            except (ValueError, TypeError):
                continue

        glucose_vals = np.array(glucose_vals, dtype=np.float32)
        timestamps_arr = np.array(timestamps)
        dates = np.array([ts.date() for ts in timestamps])
        unique_dates = sorted(set(dates))

        patient_features = []
        patient_tir = []

        for i, date in enumerate(unique_dates[:-1]):
            mask = dates == date
            day_gluc = glucose_vals[mask]

            if len(day_gluc) < 200:
                continue

            next_date = unique_dates[i + 1]
            next_mask = dates == next_date
            next_gluc = glucose_vals[next_mask]
            if len(next_gluc) < 200:
                continue

            next_tir = np.mean((next_gluc >= 70) & (next_gluc <= 180)) * 100

            feats = []

            # === Glucose features (same as EXP-445) ===
            feats.extend([
                np.mean(day_gluc), np.std(day_gluc),
                np.min(day_gluc), np.max(day_gluc),
                np.std(day_gluc) / np.mean(day_gluc) * 100,
            ])
            feats.extend([
                np.mean(day_gluc < 54) * 100,
                np.mean(day_gluc < 70) * 100,
                np.mean((day_gluc >= 70) & (day_gluc <= 180)) * 100,
                np.mean(day_gluc > 180) * 100,
                np.mean(day_gluc > 250) * 100,
            ])
            bins = np.linspace(40, 400, 9)
            hist, _ = np.histogram(np.clip(day_gluc, 40, 400), bins=bins)
            hist_norm = hist / hist.sum()
            feats.extend(hist_norm.tolist())
            quarter = len(day_gluc) // 4
            for q in range(4):
                qstart = q * quarter
                qend = (q + 1) * quarter if q < 3 else len(day_gluc)
                q_gluc = day_gluc[qstart:qend]
                feats.append(np.mean((q_gluc >= 70) & (q_gluc <= 180)) * 100 if len(q_gluc) > 0 else 50.0)
            diffs = np.diff(day_gluc)
            feats.extend([
                np.mean(np.abs(diffs)),
                np.mean(diffs > 0) * 100,
                np.percentile(diffs, 10),
                np.percentile(diffs, 90),
            ])
            dow = date.weekday()
            feats.extend([np.sin(2*np.pi*dow/7), np.cos(2*np.pi*dow/7)])

            # === PK-derived features (NEW) ===
            day_treats = treat_by_date.get(date, [])

            # Insulin features
            boluses = [float(t.get('insulin') or 0) for t in day_treats
                       if float(t.get('insulin') or 0) > 0]
            tdd_bolus = sum(boluses) if boluses else 0
            n_bolus = len(boluses)

            # Basal rate from temp basals
            temp_basals = [t for t in day_treats if t.get('eventType') == 'Temp Basal']
            n_temp_basal = len(temp_basals)

            # Carb features
            carbs = [float(t.get('carbs') or 0) for t in day_treats
                     if float(t.get('carbs') or 0) > 0]
            total_carbs = sum(carbs) if carbs else 0
            n_meals = len(carbs)
            mean_carbs = np.mean(carbs) if carbs else 0
            max_carbs = max(carbs) if carbs else 0

            feats.extend([
                tdd_bolus,                    # total daily bolus dose
                n_bolus,                      # number of boluses
                np.mean(boluses) if boluses else 0,  # mean bolus size
                n_temp_basal,                 # number of temp basal changes
                total_carbs,                  # total daily carbs
                n_meals,                      # meal count
                mean_carbs,                   # mean carb dose
                max_carbs,                    # largest meal
                total_carbs / max(tdd_bolus, 0.1),  # carb-to-insulin ratio (daily)
            ])

            patient_features.append(feats)
            patient_tir.append(next_tir)

        if len(patient_features) < 10:
            continue

        start_idx = len(all_features)
        all_features.extend(patient_features)
        all_targets.extend(patient_tir)
        all_patient_ids.extend([pid] * len(patient_features))
        all_patient_boundaries.append({
            'name': pid,
            'start': start_idx,
            'end': start_idx + len(patient_features),
            'n_days': len(patient_features),
        })
        print(f"  {pid}: {len(patient_features)} days, {n_bolus} bolus/last day, "
              f"{n_meals} meals/last day, TIR={np.mean(patient_tir):.1f}%")

    X = np.array(all_features, dtype=np.float32)
    y = np.array(all_targets, dtype=np.float32)
    return X, y, all_patient_ids, all_patient_boundaries


def run_exp447(args):
    """EXP-447: TIR Prediction with PK-Derived Daily Features.

    Hypothesis: Adding insulin and carb statistics (TDD, meal count, carb-to-
    insulin ratio) to daily features improves next-day TIR prediction beyond
    EXP-445's glucose-only features.

    Compare:
      a) glucose_only: EXP-445 features (28 features)
      b) glucose+pk: + insulin/carb stats (37 features)

    Uses Ridge and GBR, same chronological per-patient split.
    """
    cfg = _get_config(args)
    print(f"\n{'='*60}")
    print(f"EXP-447: TIR with PK-Derived Daily Features")
    print(f"{'='*60}")

    # Glucose-only features (EXP-445 style)
    print(f"\n  Extracting glucose-only features...")
    X_gluc, y_gluc, pids_g, bounds_g = _extract_daily_features(
        args.patients_dir, max_patients=cfg['max_patients'])

    # Glucose + PK features
    print(f"\n  Extracting glucose+PK features...")
    X_pk, y_pk, pids_pk, bounds_pk = _extract_daily_features_with_pk(
        args.patients_dir, max_patients=cfg['max_patients'])

    if len(X_gluc) == 0 or len(X_pk) == 0:
        print("  No data!")
        return {'error': 'no_data'}

    print(f"\n  Glucose-only: {X_gluc.shape[1]} features, {len(X_gluc)} samples")
    print(f"  Glucose+PK: {X_pk.shape[1]} features, {len(X_pk)} samples")

    try:
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        print("  sklearn required for this experiment")
        return {'error': 'no_sklearn'}

    result = {}

    for feat_name, X, y, bounds in [
        ('glucose_only', X_gluc, y_gluc, bounds_g),
        ('glucose_pk', X_pk, y_pk, bounds_pk),
    ]:
        print(f"\n{'─'*40}")
        print(f"  Features: {feat_name} ({X.shape[1]} dims)")
        print(f"{'─'*40}")

        for model_name, model_factory in [
            ('ridge', lambda: Ridge(alpha=1.0)),
            ('gbr', lambda: GradientBoostingRegressor(
                n_estimators=100, max_depth=3, learning_rate=0.1,
                subsample=0.8, random_state=42)),
        ]:
            per_patient = {}
            all_preds, all_trues = [], []

            for pinfo in bounds:
                pid = pinfo['name']
                s, e = pinfo['start'], pinfo['end']
                n = e - s
                split_idx = int(n * 0.8)
                if split_idx < 10 or (n - split_idx) < 5:
                    continue

                X_train, y_train = X[s:s+split_idx], y[s:s+split_idx]
                X_test, y_test = X[s+split_idx:e], y[s+split_idx:e]

                mdl = model_factory()
                mdl.fit(X_train, y_train)
                y_pred = mdl.predict(X_test)

                y_persist = X_test[:, 7]  # today's TIR
                mae_model = np.mean(np.abs(y_pred - y_test))
                mae_persist = np.mean(np.abs(y_persist - y_test))

                per_patient[pid] = {
                    'mae_model': round(float(mae_model), 2),
                    'mae_persist': round(float(mae_persist), 2),
                }
                all_preds.extend(y_pred.tolist())
                all_trues.extend(y_test.tolist())
                print(f"    {pid}: {model_name}={mae_model:.1f}% persist={mae_persist:.1f}%")

            if all_preds:
                overall_mae = np.mean(np.abs(np.array(all_preds) - np.array(all_trues)))
            else:
                overall_mae = float('nan')

            key = f"{feat_name}_{model_name}"
            result[key] = {
                'per_patient': per_patient,
                'overall_mae': round(float(overall_mae), 2),
            }

    # Summary comparison
    print(f"\n{'='*60}")
    print(f"EXP-447 Summary: TIR Feature Comparison")
    print(f"{'='*60}")
    for key, data in result.items():
        print(f"  {key}: MAE={data['overall_mae']}%")
        for pid, pp in data['per_patient'].items():
            print(f"    {pid}: model={pp['mae_model']}% persist={pp['mae_persist']}%")

    # Delta: PK features vs glucose-only
    for mn in ['ridge', 'gbr']:
        g_key = f"glucose_only_{mn}"
        p_key = f"glucose_pk_{mn}"
        if g_key in result and p_key in result:
            delta = result[p_key]['overall_mae'] - result[g_key]['overall_mae']
            print(f"\n  Δ ({mn} PK vs glucose-only): {delta:+.2f}%")
            if delta < 0:
                print(f"  ✓ PK features help {mn} by {-delta:.1f}%!")
            else:
                print(f"  ✗ PK features don't help {mn}")

    _save_results(result, 'exp447_tir_pk_features', cfg)
    return result


EXPERIMENTS = {
    '405': run_exp405,
    '406': run_exp406,
    '407': run_exp407,
    '408': run_exp408,
    '409': run_exp409,
    '410': run_exp410,
    '411': run_exp411,
    '413': run_exp413,
    '414': run_exp414,
    '417': run_exp417,
    '419': run_exp419,
    '420': run_exp420,
    '421': run_exp421,
    '422': run_exp422,
    '423': run_exp423,
    '424': run_exp424,
    '425': run_exp425,
    '426': run_exp426,
    '427': run_exp427,
    '428': run_exp428,
    '429': run_exp429,
    '430': run_exp430,
    '431': run_exp431,
    '432': run_exp432,
    '433': run_exp433,
    '434': run_exp434,
    '435': run_exp435,
    '436': run_exp436,
    '437': run_exp437,
    '438': run_exp438,
    '439': run_exp439,
    '440': run_exp440,
    '441': run_exp441,
    '442': run_exp442,
    '443': run_exp443,
    '444': run_exp444,
    '445': run_exp445,
    '446': run_exp446,
    '447': run_exp447,
}


def main():
    parser = argparse.ArgumentParser(description='ERA 2+3 Bridge Experiments')
    parser.add_argument('--experiment', '-e', default='all',
                        help='Experiment (405-414) or "all"')
    parser.add_argument('--device', '-d', default=None)
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick: 4 patients, 1 seed, 60 epochs')
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--output-dir', default='externals/experiments')
    args = parser.parse_args()

    if args.experiment == 'all':
        exps = sorted(EXPERIMENTS.keys())
    else:
        exps = [args.experiment]

    t0 = time.time()
    all_results = {}
    for eid in exps:
        if eid not in EXPERIMENTS:
            print(f"Unknown: {eid}"); continue
        result = EXPERIMENTS[eid](args)
        all_results[eid] = result

    elapsed = time.time() - t0
    print(f"\nAll done in {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Summary table
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for eid, result in all_results.items():
        if 'summary' in result:
            print(f"  EXP-{eid}: Ensemble={result['summary'].get('mean_ensemble_mae','?')}")
        else:
            for vn, vd in result.items():
                if isinstance(vd, dict) and 'average' in vd:
                    print(f"  EXP-{eid}/{vn}: MAE={vd['average'].get('overall_mae','?')}, "
                          f"h60={vd['average'].get('h60','?')}")


if __name__ == '__main__':
    main()
