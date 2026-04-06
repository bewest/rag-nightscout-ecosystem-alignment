#!/usr/bin/env python3
"""EXP-373: Multi-Task Transformer at 6h Scale

Combines two proven improvements:
1. Transformer + kitchen_sink_10ch: EXP-362 showed +1.4% override, +4.4% prolonged_high at 6h
2. Multi-task learning: EXP-325 showed +6% on weaker tasks via shared representations

Design: 6 configurations at 6h scale
  A) Single-task CNN + baseline_8ch         (control from EXP-362)
  B) Single-task Transformer + kitchen_sink (best from EXP-362)
  C) Multi-task CNN + baseline_8ch          (isolates multi-task benefit)
  D) Multi-task CNN + kitchen_sink_10ch     (isolates feature + MT)
  E) Multi-task Transformer + baseline_8ch  (isolates arch + MT)
  F) Multi-task Transformer + kitchen_sink  (FULL COMBINATION)

Multi-task head: Shared encoder → 3 separate heads (override, hypo, prolonged_high)
Loss = weighted sum (override_weight=1.0, hypo_weight=0.5, prolonged_high_weight=0.5)

Also tests EXP-374: Transformer at 2h to see if attention helps at shortest scale.

── NEXT EXPERIMENTS (after 373/374 complete) ──────────────────────────────

  exp_fda_classification_v2.py has EXP-405 and EXP-406 ready to run:

  EXP-405: Glucodensity + functional depth head injection
    Proven FDA features at CLASSIFIER HEAD (not input channels — those give
    zero gradient, EXP-338). Glucodensity 8-bin histogram + Modified Band
    Depth concatenated to pooled CNN features. Tested at 2h AND 12h.
    Key: glucodensity Δ=+0.54 Silhouette vs TIR (EXP-330), depth 112×
    hypo enrichment (EXP-335). Uses shared feature_helpers.py.

  EXP-406: Multi-rate EMA channels at 12h
    Replaces single glucose channel with 5ch: raw + EMA(0.7) + EMA(0.3)
    + EMA(0.1) + derivative. Captures multi-scale glucose dynamics.
    Expected benefit at 12h where single-scale features fail.
    Uses feature_helpers.py.

  These DON'T conflict with your transformer/multi-task direction:
    - Head injection is architecture-agnostic (works WITH your transformer)
    - EMA channels are input features (can combine with kitchen_sink)
    - If you prefer, try head injection ON your multi-task transformer
      for the best combo of all three approaches

  Run: python tools/cgmencode/exp_fda_classification_v2.py --experiment 405
       python tools/cgmencode/exp_fda_classification_v2.py --experiment 406

  All results include ECE (Expected Calibration Error) for clinical
  calibration assessment alongside F1 and AUC.

Usage:
    python tools/cgmencode/exp_multitask_transformer.py [--scales 2h 6h]
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse, math
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score
from scipy.interpolate import UnivariateSpline

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

SCALE_CONFIGS = {
    '2h':  {'window_size': 24,  'stride': 12, 'label': '1h history → 1h prediction'},
    '6h':  {'window_size': 72,  'stride': 36, 'label': '3h history → 3h prediction'},
}


# ── Data loading (reused from EXP-362) ───────────────────────────────────

def smooth_glucose_series(glucose, smoothing_factor=None):
    x = np.arange(len(glucose), dtype=float)
    valid = ~np.isnan(glucose) & (glucose > 0)
    if valid.sum() < 20:
        d1 = np.gradient(glucose)
        d2 = np.gradient(d1)
        return glucose.copy(), d1, d2
    if smoothing_factor is None:
        smoothing_factor = valid.sum() * 1.0
    try:
        spl = UnivariateSpline(x[valid], glucose[valid], s=smoothing_factor, k=4)
        smooth = spl(x)
        d1 = spl.derivative(1)(x)
        d2 = spl.derivative(2)(x)
        smooth = np.clip(smooth, 30, 500)
    except Exception:
        smooth = glucose.copy()
        d1 = np.gradient(glucose)
        d2 = np.gradient(d1)
    return smooth.astype(np.float32), d1.astype(np.float32), d2.astype(np.float32)


def find_patient_dirs(d):
    dirs = sorted(glob.glob(os.path.join(d, '*/training')))
    if not dirs:
        dirs = sorted(glob.glob(os.path.join(d, '*')))
    return [x for x in dirs if os.path.isdir(x)]


def load_patient_features(patients_dir):
    patient_dirs = find_patient_dirs(patients_dir)
    print(f"Loading {len(patient_dirs)} patients")
    patients = []
    for pdir in patient_dirs:
        pid = Path(pdir).parent.name
        try:
            df, base_8ch = build_nightscout_grid(pdir)
            pk_8ch = build_continuous_pk_features(df)
            raw_glucose = df['glucose'].values
            g_smooth, g_d1, g_d2 = smooth_glucose_series(raw_glucose)
            fda_3ch = np.column_stack([
                g_smooth / 400.0, g_d1 / 10.0, g_d2 / 5.0,
            ]).astype(np.float32)
            ml = min(len(base_8ch), len(pk_8ch), len(fda_3ch))
            base_8ch = base_8ch[:ml].astype(np.float32)
            pk_8ch = pk_8ch[:ml].astype(np.float32)
            fda_3ch = fda_3ch[:ml]
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(pk_8ch, copy=False)
            np.nan_to_num(fda_3ch, copy=False)
            patients.append((pid, base_8ch, pk_8ch, fda_3ch))
            print(f"  {pid}: {ml} timesteps")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")
    return patients


def window_and_split(patients, window_size, stride):
    all_bt, all_bv, all_pt, all_pv, all_ft, all_fv = [], [], [], [], [], []
    for pid, base, pk, fda in patients:
        ml = len(base)
        bw, pw, fw = [], [], []
        for i in range(0, ml - window_size + 1, stride):
            bw.append(base[i:i + window_size])
            pw.append(pk[i:i + window_size])
            fw.append(fda[i:i + window_size])
        if len(bw) < 10:
            continue
        bw = np.array(bw, dtype=np.float32)
        pw = np.array(pw, dtype=np.float32)
        fw = np.array(fw, dtype=np.float32)
        n = len(bw)
        s = int(n * 0.8)
        all_bt.append(bw[:s]); all_bv.append(bw[s:])
        all_pt.append(pw[:s]); all_pv.append(pw[s:])
        all_ft.append(fw[:s]); all_fv.append(fw[s:])
    bt = np.concatenate(all_bt); bv = np.concatenate(all_bv)
    pt = np.concatenate(all_pt); pv = np.concatenate(all_pv)
    ft = np.concatenate(all_ft); fv = np.concatenate(all_fv)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(bt))
    bt, pt, ft = bt[idx], pt[idx], ft[idx]
    return bt, bv, pt, pv, ft, fv


# ── Feature variants ─────────────────────────────────────────────────────

VARIANT_DEFS = {
    'baseline_8ch': {
        'desc': 'Standard 8ch (control)',
        'build': lambda b, p, f: b,
    },
    'kitchen_sink_10ch': {
        'desc': 'Raw + FDA deriv + PK state (10ch)',
        'build': lambda b, p, f: np.concatenate([
            b[:, :, 0:1],     # raw glucose
            f[:, :, 1:3],     # glucose_d1, glucose_d2
            b[:, :, 1:4],     # iob, cob, net_basal
            p[:, :, 6:7],     # pk net_balance
            p[:, :, 0:1],     # pk insulin_total
            p[:, :, 3:4],     # pk carb_rate
            p[:, :, 2:3],     # pk basal_ratio
        ], axis=2),
    },
    'no_time_6ch': {
        'desc': 'Baseline minus time_sin/cos (2h best for UAM)',
        'build': lambda b, p, f: b[:, :, :6],
    },
}


# ── Labels ────────────────────────────────────────────────────────────────

def build_override_labels(bw, half):
    fg = bw[:, half:, 0] * 400.0
    hi, lo = (fg > 180).any(axis=1), (fg < 70).any(axis=1)
    labels = np.zeros(len(bw), dtype=np.int64)
    labels[hi] = 1; labels[lo] = 2
    return labels

def build_hypo_labels(bw, half):
    return ((bw[:, half:, 0] * 400.0 < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(bw, half):
    fg = bw[:, half:, 0] * 400.0
    return ((fg > 180).mean(axis=1) > 0.5).astype(np.int64)

def build_uam_labels(bw, half):
    """UAM: rising glucose with no carbs in history (2h only)."""
    fg = bw[:, half:, 0] * 400.0
    rising = (np.diff(fg, axis=1) > 2.0).any(axis=1)
    hg = bw[:, :half, 0] * 400.0
    carbs_present = (bw[:, :half, 5] > 0).any(axis=1)  # ch5 = carbs
    return (rising & ~carbs_present).astype(np.int64)


# ── Architectures ─────────────────────────────────────────────────────────

class DeepCNN(nn.Module):
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        return self.fc(self.conv(x.permute(0, 2, 1)).squeeze(-1))


class ShallowCNN(nn.Module):
    """3-layer CNN for 2h scale (RF covers full 12-step window)."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3), nn.Linear(32, nc))

    def forward(self, x):
        return self.fc(self.conv(x.permute(0, 2, 1)).squeeze(-1))


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=200):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term[:d_model // 2])
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class TransformerClassifier(nn.Module):
    def __init__(self, in_ch, nc, d_model=64, nhead=4, nlayers=2, dropout=0.1):
        super().__init__()
        self.input_proj = nn.Linear(in_ch, d_model)
        self.pos_enc = PositionalEncoding(d_model, max_len=200)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=128,
            dropout=dropout, batch_first=True, activation='gelu',
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
        self.fc = nn.Sequential(nn.Linear(d_model, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, nc))

    def forward(self, x):
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)
        return self.fc(h)


# ── Multi-task models ─────────────────────────────────────────────────────

class MultiTaskCNN(nn.Module):
    """Shared CNN encoder with separate classification heads."""
    def __init__(self, in_ch, task_nc_dict):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        self.shared_fc = nn.Sequential(nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3))
        self.heads = nn.ModuleDict({
            name: nn.Linear(64, nc) for name, nc in task_nc_dict.items()
        })

    def forward(self, x):
        h = self.conv(x.permute(0, 2, 1)).squeeze(-1)
        h = self.shared_fc(h)
        return {name: head(h) for name, head in self.heads.items()}


class MultiTaskTransformer(nn.Module):
    """Shared Transformer encoder with separate classification heads."""
    def __init__(self, in_ch, task_nc_dict, d_model=64, nhead=4, nlayers=2, dropout=0.1):
        super().__init__()
        self.input_proj = nn.Linear(in_ch, d_model)
        self.pos_enc = PositionalEncoding(d_model, max_len=200)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=128,
            dropout=dropout, batch_first=True, activation='gelu',
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=nlayers)
        self.shared_fc = nn.Sequential(nn.Linear(d_model, 64), nn.ReLU(), nn.Dropout(0.3))
        self.heads = nn.ModuleDict({
            name: nn.Linear(64, nc) for name, nc in task_nc_dict.items()
        })

    def forward(self, x):
        h = self.input_proj(x)
        h = self.pos_enc(h)
        h = self.encoder(h)
        h = h.mean(dim=1)
        h = self.shared_fc(h)
        return {name: head(h) for name, head in self.heads.items()}


# ── Training routines ────────────────────────────────────────────────────

def compute_class_weights(y, nc):
    c = np.maximum(np.bincount(y, minlength=nc).astype(float), 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_single_task(tx, ty, vx, vy, nc, device, arch_cls, half,
                      epochs=60, bs=256, patience=12):
    in_ch = tx.shape[2]
    model = arch_cls(in_ch, nc).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

    th = torch.from_numpy(tx[:, :half].copy()).float()
    vh = torch.from_numpy(vx[:, :half].copy()).float()
    ds = TensorDataset(th, torch.from_numpy(ty).long())
    dl = DataLoader(ds, batch_size=bs, shuffle=True, pin_memory=(device.type == 'cuda'))

    best_m, best_p, best_pr, wait = -1, None, None, 0
    for ep in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(); crit(model(xb), yb).backward(); opt.step()
        model.eval()
        with torch.no_grad():
            logits = model(vh.to(device))
            preds = logits.argmax(1).cpu().numpy()
            probs = torch.softmax(logits, 1).cpu().numpy()
        if nc == 2:
            try: metric = roc_auc_score(vy, probs[:, 1])
            except: metric = 0.0
        else:
            metric = f1_score(vy, preds, average='macro', zero_division=0)
        sched.step(1 - metric)
        if metric > best_m:
            best_m, best_p, best_pr, wait = metric, preds.copy(), probs.copy(), 0
        else:
            wait += 1
            if wait >= patience: break
    return _compute_metrics(vy, best_p, best_pr, nc, ep + 1, in_ch, half, model)


def _compute_metrics(vy, preds, probs, nc, epochs, in_ch, half, model):
    nparams = sum(p.numel() for p in model.parameters())
    r = {'epochs': epochs, 'in_channels': in_ch, 'history_steps': half, 'param_count': nparams}
    if nc == 2:
        r['f1'] = float(f1_score(vy, preds, average='binary', zero_division=0))
        try: r['auc'] = float(roc_auc_score(vy, probs[:, 1]))
        except: r['auc'] = 0.0
        r['prevalence'] = float(vy.mean())
    else:
        r['f1_macro'] = float(f1_score(vy, preds, average='macro', zero_division=0))
        r['f1_per_class'] = [float(x) for x in f1_score(vy, preds, average=None, zero_division=0)]
    return r


TASK_WEIGHTS = {'override': 1.0, 'hypo': 0.5, 'prolonged_high': 0.5}
TASK_NC = {'override': 3, 'hypo': 2, 'prolonged_high': 2}

def train_multi_task(tx, labels_dict, vx, vlabels_dict, device, mt_model_cls,
                     half, epochs=80, bs=256, patience=15):
    """Train multi-task model on all 3 tasks jointly."""
    in_ch = tx.shape[2]
    model = mt_model_cls(in_ch, TASK_NC).to(device)

    criterions = {}
    for tname, nc in TASK_NC.items():
        w = compute_class_weights(labels_dict[tname], nc).to(device)
        criterions[tname] = nn.CrossEntropyLoss(weight=w)

    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)

    th = torch.from_numpy(tx[:, :half].copy()).float()
    vh = torch.from_numpy(vx[:, :half].copy()).float()

    ty_tensors = {k: torch.from_numpy(v).long() for k, v in labels_dict.items()}
    ds = TensorDataset(th, ty_tensors['override'], ty_tensors['hypo'],
                       ty_tensors['prolonged_high'])
    dl = DataLoader(ds, batch_size=bs, shuffle=True, pin_memory=(device.type == 'cuda'))

    best_score = -1
    best_results = {}
    wait = 0

    for ep in range(epochs):
        model.train()
        for batch in dl:
            xb = batch[0].to(device)
            yb = {'override': batch[1].to(device),
                  'hypo': batch[2].to(device),
                  'prolonged_high': batch[3].to(device)}
            opt.zero_grad()
            logits_dict = model(xb)
            loss = sum(TASK_WEIGHTS[t] * criterions[t](logits_dict[t], yb[t])
                       for t in TASK_NC)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(vh.to(device))

        task_metrics = {}
        for tname, nc in TASK_NC.items():
            vy = vlabels_dict[tname]
            logits = val_logits[tname]
            preds = logits.argmax(1).cpu().numpy()
            probs = torch.softmax(logits, 1).cpu().numpy()
            if nc == 2:
                try: m = roc_auc_score(vy, probs[:, 1])
                except: m = 0.0
            else:
                m = f1_score(vy, preds, average='macro', zero_division=0)
            task_metrics[tname] = {
                'metric': m, 'preds': preds.copy(), 'probs': probs.copy()
            }

        composite = sum(task_metrics[t]['metric'] * TASK_WEIGHTS[t]
                        for t in TASK_NC) / sum(TASK_WEIGHTS.values())
        sched.step(1 - composite)

        if composite > best_score:
            best_score = composite
            best_results = {}
            for tname, nc in TASK_NC.items():
                vy = vlabels_dict[tname]
                tm = task_metrics[tname]
                nparams = sum(p.numel() for p in model.parameters())
                r = {'epochs': ep + 1, 'in_channels': in_ch,
                     'history_steps': half, 'param_count': nparams}
                if nc == 2:
                    r['f1'] = float(f1_score(vy, tm['preds'], average='binary', zero_division=0))
                    try: r['auc'] = float(roc_auc_score(vy, tm['probs'][:, 1]))
                    except: r['auc'] = 0.0
                    r['prevalence'] = float(vy.mean())
                else:
                    r['f1_macro'] = float(f1_score(vy, tm['preds'], average='macro', zero_division=0))
                    r['f1_per_class'] = [float(x) for x in
                                         f1_score(vy, tm['preds'], average=None, zero_division=0)]
                best_results[tname] = r
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

    return best_results


# ── Main experiment ──────────────────────────────────────────────────────

CONFIGS_6H = [
    # (name, arch, features, multi_task)
    ('ST_cnn_base',       'cnn',         'baseline_8ch',      False),
    ('ST_cnn_kitchen',    'cnn',         'kitchen_sink_10ch', False),
    ('ST_tfm_base',       'transformer', 'baseline_8ch',      False),
    ('ST_tfm_kitchen',    'transformer', 'kitchen_sink_10ch', False),
    ('MT_cnn_base',       'cnn',         'baseline_8ch',      True),
    ('MT_cnn_kitchen',    'cnn',         'kitchen_sink_10ch', True),
    ('MT_tfm_base',       'transformer', 'baseline_8ch',      True),
    ('MT_tfm_kitchen',    'transformer', 'kitchen_sink_10ch', True),
]

CONFIGS_2H = [
    ('ST_shallow_base',    'shallow_cnn', 'baseline_8ch',      False),
    ('ST_shallow_notime',  'shallow_cnn', 'no_time_6ch',       False),
    ('ST_shallow_kitchen', 'shallow_cnn', 'kitchen_sink_10ch', False),
    ('ST_tfm_base',        'transformer', 'baseline_8ch',      False),
    ('ST_tfm_notime',      'transformer', 'no_time_6ch',       False),
    ('ST_tfm_kitchen',     'transformer', 'kitchen_sink_10ch', False),
]

TASKS_6H = {
    'override':       {'fn': build_override_labels,       'nc': 3, 'pm': 'f1_macro'},
    'hypo':           {'fn': build_hypo_labels,           'nc': 2, 'pm': 'auc'},
    'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1'},
}

TASKS_2H = {
    'uam':      {'fn': build_uam_labels,      'nc': 2, 'pm': 'f1'},
    'override': {'fn': build_override_labels,  'nc': 3, 'pm': 'f1_macro'},
    'hypo':     {'fn': build_hypo_labels,      'nc': 2, 'pm': 'auc'},
}

ARCH_MAP = {
    'cnn': DeepCNN,
    'shallow_cnn': ShallowCNN,
    'transformer': TransformerClassifier,
}
MT_ARCH_MAP = {
    'cnn': MultiTaskCNN,
    'transformer': MultiTaskTransformer,
}


def run_6h(patients, device, seeds):
    """EXP-373: Multi-task transformer at 6h."""
    print(f"\n{'#'*70}")
    print(f"# EXP-373: Multi-Task Transformer at 6h")
    print(f"{'#'*70}")

    cfg = SCALE_CONFIGS['6h']
    ws, half = cfg['window_size'], cfg['window_size'] // 2

    bt, bv, pt, pv, ft, fv = window_and_split(patients, ws, cfg['stride'])
    print(f"  {len(bt)} train, {len(bv)} val")

    # Build all labels
    train_labels = {}
    val_labels = {}
    for tname, tdef in TASKS_6H.items():
        train_labels[tname] = tdef['fn'](bt, half)
        val_labels[tname] = tdef['fn'](bv, half)
        if tdef['nc'] == 2:
            print(f"  {tname}: train_prev={train_labels[tname].mean():.3f}, val_prev={val_labels[tname].mean():.3f}")
        else:
            from collections import Counter
            print(f"  {tname}: dist={sorted(Counter(train_labels[tname]).items())}")

    all_results = {}
    for config_name, arch_type, feat_name, is_mt in CONFIGS_6H:
        fdef = VARIANT_DEFS[feat_name]
        tx = fdef['build'](bt, pt, ft)
        vx = fdef['build'](bv, pv, fv)

        print(f"\n{'='*60}")
        print(f"[6h] {config_name}: {arch_type} + {feat_name} ({'multi-task' if is_mt else 'single-task'})")
        print(f"{'='*60}")
        print(f"  {tx.shape[2]}ch, shape: {tx.shape}")

        config_results = {}
        for s in seeds:
            torch.manual_seed(s)
            np.random.seed(s)

            if is_mt:
                mt_cls = MT_ARCH_MAP[arch_type]
                seed_r = train_multi_task(tx, train_labels, vx, val_labels,
                                          device, mt_cls, half)
            else:
                seed_r = {}
                for tname, tdef in TASKS_6H.items():
                    arch_cls = ARCH_MAP[arch_type]
                    r = train_single_task(tx, train_labels[tname], vx, val_labels[tname],
                                          tdef['nc'], device, arch_cls, half)
                    seed_r[tname] = r

            for tname in TASKS_6H:
                if tname not in config_results:
                    config_results[tname] = []
                config_results[tname].append(seed_r[tname])

        # Average across seeds
        avg_results = {}
        for tname, tdef in TASKS_6H.items():
            pm = tdef['pm']
            seed_list = config_results[tname]
            avg = {}
            for k in seed_list[0]:
                if isinstance(seed_list[0][k], float):
                    avg[k] = float(np.mean([sr[k] for sr in seed_list]))
                elif isinstance(seed_list[0][k], list):
                    avg[k] = [float(np.mean([sr[k][i] for sr in seed_list]))
                              for i in range(len(seed_list[0][k]))]
                else:
                    avg[k] = seed_list[0][k]
            avg_results[tname] = avg
            val = avg.get(pm, avg.get('f1_macro', avg.get('auc', 0)))
            print(f"  {tname}: {pm}={val:.4f}")

        all_results[config_name] = avg_results

    # Summary
    print(f"\n{'='*70}")
    print(f"[6h] EXP-373 SUMMARY")
    print(f"{'='*70}")
    ctrl = all_results.get('ST_cnn_base', {})
    for tname, tdef in TASKS_6H.items():
        pm = tdef['pm']
        ctrl_val = ctrl.get(tname, {}).get(pm, 0)
        print(f"\n  {tname} ({pm}):")
        for config_name, _, _, _ in CONFIGS_6H:
            val = all_results.get(config_name, {}).get(tname, {}).get(pm, 0)
            delta = val - ctrl_val
            star = ' ★' if val >= ctrl_val and delta > 0 else ''
            mt_tag = ' [MT]' if 'MT_' in config_name else '     '
            print(f"    {config_name:25s}{mt_tag}: {val:.4f} (Δ={delta:+.4f}){star}")
        best_name = max(all_results.keys(), key=lambda k: all_results[k].get(tname, {}).get(pm, 0))
        best_val = all_results[best_name][tname][pm]
        print(f"    → BEST: {best_name} = {best_val:.4f} (Δ={best_val - ctrl_val:+.4f})")

    return all_results


def run_2h(patients, device, seeds):
    """EXP-374: Transformer at 2h scale."""
    print(f"\n{'#'*70}")
    print(f"# EXP-374: Transformer at 2h Scale")
    print(f"{'#'*70}")

    cfg = SCALE_CONFIGS['2h']
    ws, half = cfg['window_size'], cfg['window_size'] // 2

    bt, bv, pt, pv, ft, fv = window_and_split(patients, ws, cfg['stride'])
    print(f"  {len(bt)} train, {len(bv)} val")

    train_labels = {}
    val_labels = {}
    for tname, tdef in TASKS_2H.items():
        train_labels[tname] = tdef['fn'](bt, half)
        val_labels[tname] = tdef['fn'](bv, half)
        if tdef['nc'] == 2:
            print(f"  {tname}: train_prev={train_labels[tname].mean():.3f}, val_prev={val_labels[tname].mean():.3f}")
        else:
            from collections import Counter
            print(f"  {tname}: dist={sorted(Counter(train_labels[tname]).items())}")

    all_results = {}
    for config_name, arch_type, feat_name, is_mt in CONFIGS_2H:
        fdef = VARIANT_DEFS[feat_name]
        tx = fdef['build'](bt, pt, ft)
        vx = fdef['build'](bv, pv, fv)

        print(f"\n{'='*60}")
        print(f"[2h] {config_name}: {arch_type} + {feat_name}")
        print(f"{'='*60}")
        print(f"  {tx.shape[2]}ch, shape: {tx.shape}")

        config_results = {}
        for s in seeds:
            torch.manual_seed(s)
            np.random.seed(s)
            seed_r = {}
            for tname, tdef in TASKS_2H.items():
                arch_cls = ARCH_MAP[arch_type]
                r = train_single_task(tx, train_labels[tname], vx, val_labels[tname],
                                      tdef['nc'], device, arch_cls, half)
                seed_r[tname] = r
            for tname in TASKS_2H:
                if tname not in config_results:
                    config_results[tname] = []
                config_results[tname].append(seed_r[tname])

        avg_results = {}
        for tname, tdef in TASKS_2H.items():
            pm = tdef['pm']
            seed_list = config_results[tname]
            avg = {}
            for k in seed_list[0]:
                if isinstance(seed_list[0][k], float):
                    avg[k] = float(np.mean([sr[k] for sr in seed_list]))
                elif isinstance(seed_list[0][k], list):
                    avg[k] = [float(np.mean([sr[k][i] for sr in seed_list]))
                              for i in range(len(seed_list[0][k]))]
                else:
                    avg[k] = seed_list[0][k]
            avg_results[tname] = avg
            val = avg.get(pm, avg.get('f1_macro', avg.get('auc', 0)))
            print(f"  {tname}: {pm}={val:.4f}")

        all_results[config_name] = avg_results

    # Summary
    print(f"\n{'='*70}")
    print(f"[2h] EXP-374 SUMMARY")
    print(f"{'='*70}")
    ctrl = all_results.get('ST_shallow_base', {})
    for tname, tdef in TASKS_2H.items():
        pm = tdef['pm']
        ctrl_val = ctrl.get(tname, {}).get(pm, 0)
        print(f"\n  {tname} ({pm}):")
        for config_name, _, _, _ in CONFIGS_2H:
            val = all_results.get(config_name, {}).get(tname, {}).get(pm, 0)
            delta = val - ctrl_val
            star = ' ★' if delta > 0 else ''
            print(f"    {config_name:25s}: {val:.4f} (Δ={delta:+.4f}){star}")
        best_name = max(all_results.keys(), key=lambda k: all_results[k].get(tname, {}).get(pm, 0))
        best_val = all_results[best_name][tname][pm]
        print(f"    → BEST: {best_name} = {best_val:.4f} (Δ={best_val - ctrl_val:+.4f})")

    return all_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--scales', nargs='+', default=['6h', '2h'])
    parser.add_argument('--seeds', nargs='+', type=int, default=[42, 123, 456])
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"EXP-373/374: Multi-Task Transformer + 2h Transformer")
    print(f"Device: {device}, Seeds: {args.seeds}, Scales: {args.scales}")

    t0 = time.time()
    patients = load_patient_features(args.patients_dir)

    output = {
        'experiment': 'EXP-373/374',
        'device': str(device),
        'seeds': args.seeds,
        'scales': args.scales,
    }

    if '6h' in args.scales:
        r6 = run_6h(patients, device, args.seeds)
        output['6h'] = r6

    if '2h' in args.scales:
        r2 = run_2h(patients, device, args.seeds)
        output['2h'] = r2

    elapsed = time.time() - t0
    output['total_seconds'] = elapsed
    print(f"\nTotal: {elapsed:.0f}s")

    # Cross-scale summary
    print(f"\n{'#'*70}")
    print(f"# CROSS-EXPERIMENT SUMMARY")
    print(f"{'#'*70}")

    if '6h' in args.scales:
        print("\n  EXP-373 (6h Multi-Task):")
        r6 = output['6h']
        for tname in ['override', 'hypo', 'prolonged_high']:
            pm = TASKS_6H[tname]['pm']
            st_val = r6.get('ST_tfm_kitchen', {}).get(tname, {}).get(pm, 0)
            mt_val = r6.get('MT_tfm_kitchen', {}).get(tname, {}).get(pm, 0)
            delta = mt_val - st_val
            print(f"    {tname}: ST={st_val:.4f}, MT={mt_val:.4f} (MT Δ={delta:+.4f})")

    if '2h' in args.scales:
        print("\n  EXP-374 (2h Transformer):")
        r2 = output['2h']
        for tname in ['uam', 'override', 'hypo']:
            pm = TASKS_2H[tname]['pm']
            cnn_val = r2.get('ST_shallow_base', {}).get(tname, {}).get(pm, 0)
            tfm_val = r2.get('ST_tfm_base', {}).get(tname, {}).get(pm, 0)
            delta = tfm_val - cnn_val
            print(f"    {tname}: CNN={cnn_val:.4f}, Transformer={tfm_val:.4f} (Δ={delta:+.4f})")

    out_path = 'externals/experiments/exp373_multitask_transformer.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Saved: {out_path}")


if __name__ == '__main__':
    main()
