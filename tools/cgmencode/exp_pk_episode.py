#!/usr/bin/env python3
"""EXP-350: PK Channel + Symmetry Test at Episode Scale (12h)

At 2h (EXP-349), PK channels HURT because 1h history is too short for
5-6h DIA curves. At 12h, the full absorption envelope is visible.
Hypothesis: PK channels help at 12h scale, time features become important.

Causality: Model receives ONLY history half (6h) — sufficient to capture
full insulin DIA. Future bolus/carbs/temp basals never seen by model.

Tests the same 5 variants as EXP-349 but at episode scale (144 steps, 12h).
Labels are adapted for the longer timescale.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import json, os, sys, time, glob, argparse
from pathlib import Path
from sklearn.metrics import f1_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

WINDOW_SIZE = 144   # 12h at 5-min
STRIDE = 72         # 50% overlap
HALF = WINDOW_SIZE // 2  # 6h history

VARIANT_DEFS = {
    'baseline_8ch': lambda b, p: b,
    'pk_replace_8ch': lambda b, p: np.concatenate([
        b[:, :, 0:1], p[:, :, 0:1], p[:, :, 6:7], p[:, :, 2:3],
        p[:, :, 3:4], p[:, :, 4:5], b[:, :, 6:8],
    ], axis=2),
    'no_time_6ch': lambda b, p: b[:, :, :6],
    'pk_no_time_6ch': lambda b, p: np.concatenate([
        b[:, :, 0:1], p[:, :, 0:1], p[:, :, 6:7], p[:, :, 2:3],
        p[:, :, 3:4], p[:, :, 4:5],
    ], axis=2),
    'augmented_16ch': lambda b, p: np.concatenate([b, p], axis=2),
}
VARIANT_ORDER = list(VARIANT_DEFS.keys())


def find_patient_dirs(d):
    dirs = sorted(glob.glob(os.path.join(d, '*/training')))
    if not dirs:
        dirs = sorted(glob.glob(os.path.join(d, '*')))
    return [x for x in dirs if os.path.isdir(x)]


def load_all_data(patients_dir):
    patient_dirs = find_patient_dirs(patients_dir)
    print(f"Loading {len(patient_dirs)} patients (12h windows)")
    bt, bv, pt, pv = [], [], [], []

    for pdir in patient_dirs:
        pid = Path(pdir).parent.name
        try:
            df, base_8ch = build_nightscout_grid(pdir)
            pk_8ch = build_continuous_pk_features(df)
            ml = min(len(base_8ch), len(pk_8ch))
            base_8ch = base_8ch[:ml].astype(np.float32)
            pk_8ch = pk_8ch[:ml].astype(np.float32)
            np.nan_to_num(base_8ch, copy=False)
            np.nan_to_num(pk_8ch, copy=False)

            bw, pw = [], []
            for i in range(0, ml - WINDOW_SIZE + 1, STRIDE):
                bw.append(base_8ch[i:i + WINDOW_SIZE])
                pw.append(pk_8ch[i:i + WINDOW_SIZE])
            if len(bw) < 10:
                print(f"  {pid}: too few ({len(bw)}), skip")
                continue
            bw, pw = np.array(bw, dtype=np.float32), np.array(pw, dtype=np.float32)
            n = len(bw)
            s = int(n * 0.8)
            bt.append(bw[:s]); bv.append(bw[s:])
            pt.append(pw[:s]); pv.append(pw[s:])
            print(f"  {pid}: {n} windows ({s} train, {n-s} val)")
        except Exception as e:
            print(f"  {pid}: FAILED - {e}")

    bt, bv = np.concatenate(bt), np.concatenate(bv)
    pt, pv = np.concatenate(pt), np.concatenate(pv)
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(bt))
    bt, pt = bt[idx], pt[idx]
    print(f"Total: {len(bt)} train, {len(bv)} val")
    return bt, bv, pt, pv


# Labels for 12h scale — different from 2h
def build_override_labels(bw):
    """Override in future 6h."""
    fg = bw[:, HALF:, 0] * 400.0
    h = (fg > 180).any(axis=1)
    lo = (fg < 70).any(axis=1)
    labels = np.zeros(len(bw), dtype=np.int64)
    labels[h] = 1
    labels[lo] = 2
    return labels

def build_hypo_labels(bw):
    """Any hypo in future 6h."""
    fg = bw[:, HALF:, 0] * 400.0
    return ((fg < 70).any(axis=1)).astype(np.int64)

def build_prolonged_high_labels(bw):
    """Prolonged high: >180 for >50% of future 6h (sustained hyperglycemia)."""
    fg = bw[:, HALF:, 0] * 400.0
    frac_high = (fg > 180).mean(axis=1)
    return (frac_high > 0.5).astype(np.int64)


TASKS = {
    'override': {'fn': build_override_labels, 'nc': 3, 'pm': 'f1_macro', 'ref': 'EXP-314'},
    'hypo': {'fn': build_hypo_labels, 'nc': 2, 'pm': 'auc', 'ref': 'EXP-322'},
    'prolonged_high': {'fn': build_prolonged_high_labels, 'nc': 2, 'pm': 'f1', 'ref': 'NEW'},
}


class FlexCNN(nn.Module):
    """Deeper CNN for 72-step (6h) history input."""
    def __init__(self, in_ch, nc):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(32),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.MaxPool1d(2),  # 72 → 36
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm1d(128),
            nn.AdaptiveAvgPool1d(1),
        )
        self.fc = nn.Sequential(
            nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(64, nc),
        )

    def forward(self, x):
        x = x.permute(0, 2, 1)
        return self.fc(self.conv(x).squeeze(-1))


def compute_class_weights(y, nc):
    c = np.bincount(y, minlength=nc).astype(float)
    c = np.maximum(c, 1.0)
    return torch.FloatTensor(len(y) / (nc * c))


def train_and_eval(tx, ty, vx, vy, nc, device, epochs=50, bs=256, patience=10):
    in_ch = tx.shape[2]
    model = FlexCNN(in_ch, nc).to(device)
    w = compute_class_weights(ty, nc).to(device)
    crit = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

    # History-only: no future leakage
    th = torch.from_numpy(tx[:, :HALF].copy()).float()
    vh = torch.from_numpy(vx[:, :HALF].copy()).float()
    tl = torch.from_numpy(ty).long()
    ds = TensorDataset(th, tl)
    dl = DataLoader(ds, batch_size=bs, shuffle=True, pin_memory=(device.type == 'cuda'))

    best_m, best_p, best_pr, wait = -1, None, None, 0
    for ep in range(epochs):
        model.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            crit(model(xb), yb).backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            logits = model(vh.to(device))
            preds = logits.argmax(1).cpu().numpy()
            probs = torch.softmax(logits, 1).cpu().numpy()
        if nc == 2:
            try: auc = roc_auc_score(vy, probs[:, 1])
            except: auc = 0.0
            metric = auc
        else:
            metric = f1_score(vy, preds, average='macro', zero_division=0)
        if metric > best_m:
            best_m = metric
            best_p, best_pr = preds.copy(), probs.copy()
            wait = 0
        else:
            wait += 1
            if wait >= patience: break

    r = {'epochs': ep + 1, 'in_channels': in_ch}
    if nc == 2:
        r['f1'] = float(f1_score(vy, best_p, average='binary', zero_division=0))
        try: r['auc'] = float(roc_auc_score(vy, best_pr[:, 1]))
        except: r['auc'] = 0.0
        r['prevalence'] = float(vy.mean())
    else:
        r['f1_macro'] = float(f1_score(vy, best_p, average='macro', zero_division=0))
        r['f1_per_class'] = [float(x) for x in f1_score(vy, best_p, average=None, zero_division=0)]
    return r


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--patients-dir', default='externals/ns-data/patients')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--output', default='externals/experiments/exp350_pk_episode.json')
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 123, 456])
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"EXP-350: PK Channel Test at Episode Scale (12h)")
    print(f"Device: {device}, Seeds: {args.seeds}")
    t0 = time.time()

    bt, bv, pt, pv = load_all_data(args.patients_dir)

    labels = {}
    for tn, tc in TASKS.items():
        ty, vy = tc['fn'](bt), tc['fn'](bv)
        if tc['nc'] == 2:
            info = f"pos={ty.mean():.3f}"
        else:
            info = f"dist={np.bincount(ty, minlength=tc['nc']).tolist()}"
        print(f"  {tn}: {info}")
        labels[tn] = (ty, vy)

    results = {
        'experiment': 'EXP-350',
        'title': 'PK Channel + Symmetry at Episode Scale (12h)',
        'scale': '12h (144 steps @ 5min)',
        'history': '6h (72 steps)',
        'n_train': int(len(bt)), 'n_val': int(len(bv)),
        'device': str(device), 'seeds': args.seeds,
        'variants': {}, 'comparison': {},
    }

    for vn in VARIANT_ORDER:
        print(f"\n{'='*60}\nVariant: {vn}\n{'='*60}")
        tx = VARIANT_DEFS[vn](bt, pt)
        vx = VARIANT_DEFS[vn](bv, pv)
        nch = tx.shape[2]
        print(f"  {nch}ch, shape: {tx.shape}")
        results['variants'][vn] = {'n_channels': nch, 'tasks': {}}

        for tn, tc in TASKS.items():
            ty, vy = labels[tn]
            seed_r = []
            for s in args.seeds:
                torch.manual_seed(s); np.random.seed(s)
                if torch.cuda.is_available(): torch.cuda.manual_seed(s)
                seed_r.append(train_and_eval(tx, ty, vx, vy, tc['nc'], device))
            agg = {}
            for k in seed_r[0]:
                vals = [sr[k] for sr in seed_r]
                if isinstance(vals[0], (int, float)):
                    agg[k] = float(np.mean(vals))
                    if len(vals) > 1: agg[f'{k}_std'] = float(np.std(vals))
                elif isinstance(vals[0], list):
                    agg[k] = [float(np.mean(x)) for x in zip(*vals)]
            pm = tc['pm']
            print(f"  {tn}: {pm}={agg.get(pm, 0):.4f}")
            results['variants'][vn]['tasks'][tn] = agg

    # Summary
    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for tn, tc in TASKS.items():
        pm = tc['pm']
        print(f"\n{tn} ({pm}):")
        bl = results['variants']['baseline_8ch']['tasks'][tn].get(pm, 0)
        best_v, best_val = None, -1
        for vn in VARIANT_ORDER:
            v = results['variants'][vn]['tasks'][tn].get(pm, 0)
            d = v - bl
            print(f"  {vn:25s}: {v:.4f} (Δ={d:+.4f})")
            if v > best_val: best_val, best_v = v, vn
        results['comparison'][tn] = {
            'metric': pm, 'baseline': float(bl),
            'best_variant': best_v, 'best_value': float(best_val),
            'delta': float(best_val - bl),
        }

    # Symmetry analysis
    print(f"\nSYMMETRY (time removal at 12h):")
    for tn, tc in TASKS.items():
        pm = tc['pm']
        wt = results['variants']['baseline_8ch']['tasks'][tn].get(pm, 0)
        nt = results['variants']['no_time_6ch']['tasks'][tn].get(pm, 0)
        pk_wt = results['variants']['pk_replace_8ch']['tasks'][tn].get(pm, 0)
        pk_nt = results['variants']['pk_no_time_6ch']['tasks'][tn].get(pm, 0)
        print(f"  {tn}: base Δ={nt-wt:+.4f}, pk Δ={pk_nt-pk_wt:+.4f}  "
              f"{'✓' if nt-wt >= 0 and pk_nt-pk_wt >= 0 else '✗'}")

    elapsed = time.time() - t0
    results['elapsed_seconds'] = float(elapsed)
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    print(f"\nTotal: {elapsed:.0f}s")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved: {args.output}")


if __name__ == '__main__':
    main()
