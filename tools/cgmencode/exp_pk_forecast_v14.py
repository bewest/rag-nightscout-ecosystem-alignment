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
import json, os, sys, time, argparse, copy
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
                     stride=None, load_isf=True):
    """Load data for bridge experiments.

    ERA 2 used window_size=24 (12 history + 12 future = 1h each at 5min).
    We use 48 (24 history = 2h, 24 future = 2h) to give PK more room.

    Returns dict with arrays and per-patient info for fine-tuning.
    """
    patient_dirs = find_patient_dirs(patients_dir)
    if max_patients:
        patient_dirs = patient_dirs[:max_patients]

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
                 patience=20, weight_decay=1e-5, lr_patience=7):
    """ERA 2-style masked-sequence forecast training with PK-aware masking."""
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
                   scale=GLUCOSE_SCALE):
    """Evaluate masked-sequence model. Returns MAE in mg/dL at each horizon."""
    model.to(device)
    model.eval()
    dl = DataLoader(TensorDataset(val_x), batch_size=64)
    all_preds, all_targets = [], []
    idx = 0

    with torch.no_grad():
        for b in dl:
            x = b[0].to(device)
            bsz = x.size(0)
            half = x.shape[1] // 2
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
    for name, step_idx in {'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23}.items():
        if step_idx < len(mae_per_step):
            report[name] = round(float(mae_per_step[step_idx]), 2)
    return report


def ensemble_evaluate(models, val_x, device, pk_mode=False, isf_val=None,
                      scale=GLUCOSE_SCALE):
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
                half = x.shape[1] // 2
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
        half = x.shape[1] // 2
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
    for name, step_idx in {'h30': 5, 'h60': 11, 'h90': 17, 'h120': 23}.items():
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


EXPERIMENTS = {
    '405': run_exp405,
    '406': run_exp406,
    '407': run_exp407,
    '408': run_exp408,
}


def main():
    parser = argparse.ArgumentParser(description='ERA 2+3 Bridge Experiments')
    parser.add_argument('--experiment', '-e', default='all',
                        help='Experiment (405-408) or "all"')
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
