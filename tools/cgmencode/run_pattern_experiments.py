#!/usr/bin/env python3
"""
run_pattern_experiments.py — Run pattern pipeline experiments (EXP-286+).

These experiments optimize for non-MAE objectives:
  - Pattern embedding quality (Recall@K, Silhouette)
  - Episode segmentation accuracy (Segment F1)
  - Feature importance via ablation
  - Optimal timescale via window sweep

Multi-scale experiments (Phase 18+) re-run at optimal timescales:
  - 12h (144-step @ 5-min): Complete insulin DIA cycles
  - 24h (96-step @ 15-min): Daily drift patterns
  - 7-day (168-step @ 1-hr): Weekly ISF trends

Usage:
    # Channel-group ablation at 2h (EXP-287)
    python3 -m tools.cgmencode.run_pattern_experiments ablation-embedding

    # Channel ablation at 12h (EXP-298) — tests if features matter more
    python3 -m tools.cgmencode.run_pattern_experiments ablation-12h

    # UAM detection at 12h (EXP-299) — tests precision improvement
    python3 -m tools.cgmencode.run_pattern_experiments uam-12h

    # Drift segmentation at 24h/15-min (EXP-300)
    python3 -m tools.cgmencode.run_pattern_experiments drift-daily

    # Weekly ISF trends at 7-day/1-hr (EXP-301)
    python3 -m tools.cgmencode.run_pattern_experiments weekly-isf

    # List available experiments
    python3 -m tools.cgmencode.run_pattern_experiments --list
"""

import argparse
import json
import os
import sys
import time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset


# ── Utilities ──────────────────────────────────────────────────────────

def save_results(result, path):
    """Save experiment results as JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Saved: {path}")


def resolve_patient_paths(patients_dir):
    """Resolve patient training directories."""
    paths = sorted([
        os.path.join(patients_dir, p, 'training')
        for p in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, p, 'training'))
    ])
    return paths


def load_base_data(patient_paths, window_size=24):
    """Load 8-channel base data from patient directories."""
    from .real_data_adapter import load_multipatient_nightscout
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=window_size
    )
    if train_ds is None:
        raise RuntimeError("Failed to load patient data")
    return train_ds, val_ds


# ── Grid Cache (load once, derive all scales) ─────────────────────────

_GRID_CACHE = {}  # {path: (df, features)} — survives across experiments in same process


def _get_cached_grid(path, verbose=False):
    """Load and cache 5-min grid. Avoids redundant JSON parsing."""
    if path not in _GRID_CACHE:
        from .real_data_adapter import build_nightscout_grid
        df, features = build_nightscout_grid(path, verbose=verbose)
        if df is not None:
            _GRID_CACHE[path] = (df, features)
        else:
            return None, None
    return _GRID_CACHE[path]


def clear_grid_cache():
    """Clear the grid cache (for testing or memory management)."""
    _GRID_CACHE.clear()


def dataset_to_numpy(ds):
    """Extract numpy arrays from CGMDataset or TensorDataset."""
    if hasattr(ds, 'vectors'):
        # CGMDataset stores raw windows in .vectors
        return ds.vectors.numpy()
    if hasattr(ds, 'tensors'):
        return ds.tensors[0].numpy()
    raise ValueError(f"Cannot extract from {type(ds)}")


def build_episode_labels_batch(windows_np, glucose_scale=400.0):
    """Build per-window episode label lists from feature windows."""
    from .pattern_retrieval import build_episode_labels_from_tensor, EPISODE_LABELS
    all_labels = []
    for i in range(len(windows_np)):
        # Use first half (history) for labeling
        half = windows_np.shape[1] // 2
        hist = windows_np[i, :half]
        int_labels = build_episode_labels_from_tensor(hist, glucose_scale=glucose_scale)
        # Majority vote for window-level label
        counts = np.bincount(int_labels, minlength=len(EPISODE_LABELS))
        majority = EPISODE_LABELS[np.argmax(counts)]
        all_labels.append([majority])
    return all_labels


# ── Training Helpers ───────────────────────────────────────────────────

def train_pattern_encoder(encoder, train_windows, train_labels, val_windows,
                          val_labels, epochs=30, batch_size=32, lr=1e-3,
                          device='cpu', masked_channels=None):
    """Train a PatternEncoder with triplet loss.

    Args:
        encoder: PatternEncoder instance
        train_windows: (N, T, F) numpy array
        train_labels: list of list of strings, length N
        val_windows: (N, T, F) numpy array
        val_labels: list of list of strings, length N
        epochs: number of training epochs
        batch_size: batch size
        lr: learning rate
        device: torch device
        masked_channels: list of channel indices to zero out (for ablation)

    Returns:
        trained encoder, training history dict
    """
    from .pattern_embedding import build_triplets, TripletPatternLoss

    encoder = encoder.to(device)
    optimizer = torch.optim.Adam(encoder.parameters(), lr=lr, weight_decay=1e-5)
    triplet_loss = TripletPatternLoss(margin=1.0)

    # Apply channel masking if requested
    def maybe_mask(windows_np):
        if masked_channels:
            w = windows_np.copy()
            for ch in masked_channels:
                if ch < w.shape[2]:
                    w[:, :, ch] = 0.0
            return w
        return windows_np

    train_masked = maybe_mask(train_windows)
    val_masked = maybe_mask(val_windows)

    # Build triplets: returns List[Tuple[anchor_idx, pos_idx, neg_idx]]
    triplets = build_triplets(train_masked, train_labels, n_triplets=min(20000, len(train_labels) * 3))
    if len(triplets) < batch_size:
        return encoder, {'error': 'insufficient triplets', 'n_triplets': len(triplets)}

    triplet_arr = np.array(triplets, dtype=np.int64)  # (N, 3)
    train_t = torch.from_numpy(train_masked).float()
    history = {'train_loss': [], 'val_loss': []}
    best_val_loss = float('inf')
    patience_counter = 0

    for epoch in range(epochs):
        encoder.train()
        perm = np.random.permutation(len(triplet_arr))
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, len(perm), batch_size):
            end = min(start + batch_size, len(perm))
            idx = perm[start:end]
            batch = triplet_arr[idx]

            a = train_t[batch[:, 0]].to(device)
            p = train_t[batch[:, 1]].to(device)
            n = train_t[batch[:, 2]].to(device)

            a_emb = encoder.encode(a)
            p_emb = encoder.encode(p)
            n_emb = encoder.encode(n)

            loss = triplet_loss(a_emb, p_emb, n_emb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_train = epoch_loss / max(n_batches, 1)
        history['train_loss'].append(avg_train)

        # Validation
        encoder.eval()
        with torch.no_grad():
            val_triplets = build_triplets(val_masked, val_labels, n_triplets=min(2000, len(val_labels)))
            if len(val_triplets) > 0:
                vt = np.array(val_triplets, dtype=np.int64)
                val_t = torch.from_numpy(val_masked).float()
                a_e = encoder.encode(val_t[vt[:, 0]].to(device))
                p_e = encoder.encode(val_t[vt[:, 1]].to(device))
                n_e = encoder.encode(val_t[vt[:, 2]].to(device))
                vl = triplet_loss(a_e, p_e, n_e).item()
            else:
                vl = avg_train
        history['val_loss'].append(vl)

        if vl < best_val_loss:
            best_val_loss = vl
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= 10:
                break

    return encoder, history


def eval_pattern_encoder(encoder, val_windows, val_labels, device='cpu',
                         masked_channels=None):
    """Evaluate a PatternEncoder on retrieval quality metrics.

    Returns dict with recall_at_5, silhouette, cluster_purity, n_val.
    """
    from .pattern_embedding import retrieval_recall_at_k
    from sklearn.metrics import silhouette_score

    if masked_channels:
        val_w = val_windows.copy()
        for ch in masked_channels:
            if ch < val_w.shape[2]:
                val_w[:, :, ch] = 0.0
    else:
        val_w = val_windows

    encoder.eval()
    with torch.no_grad():
        val_t = torch.from_numpy(val_w).float().to(device)
        embeddings = encoder.encode(val_t).cpu().numpy()

    # Recall@5
    recall = retrieval_recall_at_k(embeddings, val_labels, k=5)

    # Silhouette score (needs >=2 clusters)
    flat_labels = [ls[0] if ls else 'stable' for ls in val_labels]
    unique = set(flat_labels)
    if len(unique) >= 2 and len(embeddings) > len(unique):
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        int_labels = le.fit_transform(flat_labels)
        sil = float(silhouette_score(embeddings, int_labels))
    else:
        sil = 0.0

    return {
        'recall_at_5': float(recall),
        'silhouette': sil,
        'n_val': len(val_windows),
        'n_unique_labels': len(unique),
    }


# ── EXP-287: Channel-Group Ablation (Embedding) ───────────────────────

def run_ablation_embedding(args):
    """EXP-287: Which feature groups matter for pattern Recall@5?

    Trains PatternEncoder with each channel group masked out, measures
    embedding quality degradation. Uses 8-channel base features.
    """
    from .pattern_embedding import PatternEncoder, CHANNEL_GROUPS

    patients_dir = args.patients_dir
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-287: Channel-Group Ablation for Pattern Embedding")
    print("=" * 60)

    patient_paths = resolve_patient_paths(patients_dir)
    print(f"Loading data from {len(patient_paths)} patients...")
    train_ds, val_ds = load_base_data(patient_paths, window_size=24)

    train_np = dataset_to_numpy(train_ds)
    val_np = dataset_to_numpy(val_ds)
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val, {input_dim} channels")

    # Build episode labels for triplet mining
    print("Building episode labels...")
    train_labels = build_episode_labels_batch(train_np)
    val_labels = build_episode_labels_batch(val_np)

    # For 8-channel data, do per-channel ablation (groups only cover base_8f)
    # For 39-channel data, do group-level ablation
    if input_dim <= 8:
        channel_map = {
            'glucose': [0],
            'iob': [1],
            'cob': [2],
            'basal_rate': [3],
            'bolus': [4],
            'carbs': [5],
            'time_sin': [6],
            'time_cos': [7],
        }
        # Also test combined ablations
        channel_map['insulin_all'] = [1, 3, 4]  # IOB + basal + bolus
        channel_map['meal_all'] = [2, 5]         # COB + carbs
        channel_map['time_all'] = [6, 7]         # sin + cos
    else:
        channel_map = {k: v for k, v in CHANNEL_GROUPS.items()}

    label_dist = {}
    for ls in train_labels:
        for l in ls:
            label_dist[l] = label_dist.get(l, 0) + 1
    print(f"Label distribution: {label_dist}")
    print(f"Ablation strategy: {'per-channel' if input_dim <= 8 else 'per-group'} "
          f"({len(channel_map)} conditions)")

    print("\n--- Baseline (all channels) ---")
    baseline_encoder = PatternEncoder(
        input_dim=input_dim, d_model=64, embed_dim=32,
        nhead=4, num_layers=2
    )
    baseline_encoder, baseline_hist = train_pattern_encoder(
        baseline_encoder, train_np, train_labels, val_np, val_labels,
        epochs=epochs, device=device
    )
    baseline_metrics = eval_pattern_encoder(
        baseline_encoder, val_np, val_labels, device=device
    )
    print(f"Baseline: Recall@5={baseline_metrics['recall_at_5']:.4f}, "
          f"Silhouette={baseline_metrics['silhouette']:.4f}")

    # Ablation sweep: mask each group
    results = {'baseline': baseline_metrics, 'ablations': {}, 'ranking': []}

    for group_name, channels in channel_map.items():
        valid_channels = [c for c in channels if c < input_dim]
        if not valid_channels:
            continue

        print(f"\n--- Ablating {group_name} (channels {valid_channels}) ---")
        abl_encoder = PatternEncoder(
            input_dim=input_dim, d_model=64, embed_dim=32,
            nhead=4, num_layers=2
        )
        abl_encoder, abl_hist = train_pattern_encoder(
            abl_encoder, train_np, train_labels, val_np, val_labels,
            epochs=epochs, device=device, masked_channels=valid_channels
        )
        abl_metrics = eval_pattern_encoder(
            abl_encoder, val_np, val_labels, device=device,
            masked_channels=valid_channels
        )

        delta_recall = abl_metrics['recall_at_5'] - baseline_metrics['recall_at_5']
        delta_sil = abl_metrics['silhouette'] - baseline_metrics['silhouette']

        results['ablations'][group_name] = {
            'channels_masked': valid_channels,
            'metrics': abl_metrics,
            'delta_recall_at_5': delta_recall,
            'delta_silhouette': delta_sil,
            'train_epochs': len(abl_hist.get('train_loss', [])),
        }
        print(f"  Recall@5={abl_metrics['recall_at_5']:.4f} (Δ={delta_recall:+.4f}), "
              f"Silhouette={abl_metrics['silhouette']:.4f} (Δ={delta_sil:+.4f})")

    # Rank by importance (most negative delta = most important)
    ranking = sorted(
        results['ablations'].items(),
        key=lambda x: x[1]['delta_recall_at_5']
    )
    results['ranking'] = [
        {'group': name, 'delta_recall': data['delta_recall_at_5'],
         'delta_silhouette': data['delta_silhouette']}
        for name, data in ranking
    ]

    print("\n=== Feature Importance Ranking (by Recall@5 drop) ===")
    for r in results['ranking']:
        print(f"  {r['group']:15s}: ΔRecall={r['delta_recall']:+.4f}, "
              f"ΔSilhouette={r['delta_silhouette']:+.4f}")

    results['experiment'] = 'EXP-287'
    results['name'] = 'channel-ablation-embedding'
    results['input_dim'] = input_dim
    results['n_train'] = train_np.shape[0]
    results['n_val'] = val_np.shape[0]
    results['epochs'] = epochs
    results['device'] = device
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    save_results(results, os.path.join(output_dir, 'exp287_channel_ablation_emb.json'))
    return results


# ── EXP-289: Window Length Sweep (Embedding) ───────────────────────────

def run_window_sweep_embedding(args):
    """EXP-289: What timescale is optimal for pattern matching?

    Trains PatternEncoder at multiple window sizes and measures Recall@5.
    Physiological rationale for window selection (5-min intervals):
      12 steps =  1h — acute events, insulin onset only
      24 steps =  2h — meal peak, partial correction
      48 steps =  4h — most of insulin action curve
      72 steps =  6h — full DIA (Duration of Insulin Action)
      96 steps =  8h — overnight/dawn phenomenon
     144 steps = 12h — ISF drift onset, half-day patterns

    Insulin pharmacokinetics: onset ~15min, peak ~60-90min, tail ~5-6h.
    A 2h window can't observe whether a correction actually worked.
    6h is the minimum to capture a complete bolus→effect→resolution cycle.
    """
    from .pattern_embedding import PatternEncoder

    patients_dir = args.patients_dir
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs
    # Physiologically-grounded window sizes (5-min intervals)
    # 72 steps (6h) = full DIA; 96 (8h) = dawn; 144 (12h) = ISF drift
    window_sizes = [12, 24, 48, 72, 96, 144]

    print("=" * 60)
    print("EXP-289: Window Length Sweep for Pattern Embedding")
    print("=" * 60)

    patient_paths = resolve_patient_paths(patients_dir)
    results = {'per_window': {}, 'experiment': 'EXP-289',
               'name': 'window-sweep-embedding'}

    for ws in window_sizes:
        print(f"\n--- Window size: {ws} steps ({ws * 5} min) ---")
        try:
            train_ds, val_ds = load_base_data(patient_paths, window_size=ws)
            train_np = dataset_to_numpy(train_ds)
            val_np = dataset_to_numpy(val_ds)
            input_dim = train_np.shape[2]
            print(f"  Data: {train_np.shape[0]} train, {val_np.shape[0]} val")

            train_labels = build_episode_labels_batch(train_np)
            val_labels = build_episode_labels_batch(val_np)

            encoder = PatternEncoder(
                input_dim=input_dim, d_model=64, embed_dim=32,
                nhead=4, num_layers=2
            )
            encoder, hist = train_pattern_encoder(
                encoder, train_np, train_labels, val_np, val_labels,
                epochs=epochs, device=device
            )
            metrics = eval_pattern_encoder(
                encoder, val_np, val_labels, device=device
            )
            metrics['window_size'] = ws
            metrics['window_minutes'] = ws * 5
            metrics['n_train'] = train_np.shape[0]
            metrics['n_val'] = val_np.shape[0]
            metrics['train_epochs'] = len(hist.get('train_loss', []))

            results['per_window'][ws] = metrics
            print(f"  Recall@5={metrics['recall_at_5']:.4f}, "
                  f"Silhouette={metrics['silhouette']:.4f}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results['per_window'][ws] = {'error': str(e)}

    # Find optimal
    valid = {k: v for k, v in results['per_window'].items()
             if 'recall_at_5' in v}
    if valid:
        best_ws = max(valid, key=lambda k: valid[k]['recall_at_5'])
        results['optimal_window'] = best_ws
        results['optimal_minutes'] = best_ws * 5
        results['optimal_recall'] = valid[best_ws]['recall_at_5']
        print(f"\n=== Optimal: {best_ws} steps ({best_ws * 5} min), "
              f"Recall@5={valid[best_ws]['recall_at_5']:.4f} ===")

    results['device'] = device
    results['epochs'] = epochs
    results['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    save_results(results, os.path.join(output_dir, 'exp289_window_sweep_emb.json'))
    return results


# ── EXP-286: ISF-Drift Episode Segmentation ───────────────────────────

def run_drift_segmentation(args):
    """EXP-286: Do drift-shift episode types improve Segment F1?

    Compares EpisodeSegmenter with 11 labels (including sensitivity_shift,
    resistance_shift) vs 9-label baseline on the same data.
    """
    from .pattern_retrieval import (
        EpisodeSegmenter, N_EPISODE_LABELS, EPISODE_LABELS,
        build_episode_labels, build_episode_labels_from_tensor
    )
    from .schema import IDX_GLUCOSE, IDX_SCHEDULED_ISF

    patients_dir = args.patients_dir
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-286: ISF-Drift Episode Segmentation (11 vs 9 labels)")
    print("=" * 60)

    patient_paths = resolve_patient_paths(patients_dir)
    print(f"Loading data from {len(patient_paths)} patients...")
    train_ds, val_ds = load_base_data(patient_paths, window_size=24)

    train_np = dataset_to_numpy(train_ds)
    val_np = dataset_to_numpy(val_ds)
    input_dim = train_np.shape[2]
    seq_len = train_np.shape[1] // 2  # history half
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val, {input_dim}ch")

    def build_segmentation_targets(windows_np, n_labels, use_drift=False):
        """Build per-timestep targets for segmentation training."""
        half = windows_np.shape[1] // 2
        all_targets = []
        for i in range(len(windows_np)):
            hist = windows_np[i, :half]
            int_labels = build_episode_labels_from_tensor(
                hist, glucose_scale=400.0
            )
            # Clamp to available labels
            int_labels = np.clip(int_labels, 0, n_labels - 1)
            all_targets.append(int_labels)
        return np.stack(all_targets)  # (N, T)

    def train_and_eval_segmenter(n_labels, label_name, windows_train, windows_val):
        """Train segmenter and return per-class F1."""
        targets_train = build_segmentation_targets(windows_train, n_labels)
        targets_val = build_segmentation_targets(windows_val, n_labels)

        model = EpisodeSegmenter(
            input_dim=input_dim, d_model=64, nhead=4,
            num_layers=2, n_labels=n_labels
        ).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss()

        half = windows_train.shape[1] // 2
        x_train = torch.from_numpy(windows_train[:, :half]).float()
        y_train = torch.from_numpy(targets_train).long()
        x_val = torch.from_numpy(windows_val[:, :half]).float()
        y_val = torch.from_numpy(targets_val).long()

        best_val_loss = float('inf')
        patience_counter = 0

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(x_train))
            epoch_loss = 0.0
            n_b = 0
            for start in range(0, len(perm), 32):
                end = min(start + 32, len(perm))
                idx = perm[start:end]
                out = model(x_train[idx].to(device))  # (B, T, n_labels)
                loss = criterion(
                    out.reshape(-1, n_labels),
                    y_train[idx].reshape(-1).to(device)
                )
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_b += 1

            model.eval()
            with torch.no_grad():
                val_out = model(x_val.to(device))
                val_loss = criterion(
                    val_out.reshape(-1, n_labels),
                    y_val.reshape(-1).to(device)
                ).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= 10:
                    break

        # Evaluate: per-class F1
        model.eval()
        with torch.no_grad():
            val_out = model(x_val.to(device))
            preds = val_out.argmax(dim=-1).cpu().numpy().flatten()
            truths = y_val.numpy().flatten()

        from sklearn.metrics import f1_score, classification_report
        macro_f1 = f1_score(truths, preds, average='macro', zero_division=0)
        weighted_f1 = f1_score(truths, preds, average='weighted', zero_division=0)

        # Per-class F1
        per_class = {}
        for cls_idx in range(n_labels):
            mask = truths == cls_idx
            if mask.sum() > 0:
                cls_f1 = f1_score(truths == cls_idx, preds == cls_idx, zero_division=0)
                per_class[EPISODE_LABELS[cls_idx] if cls_idx < len(EPISODE_LABELS)
                          else f'label_{cls_idx}'] = {
                    'f1': float(cls_f1),
                    'support': int(mask.sum()),
                }

        return {
            'macro_f1': float(macro_f1),
            'weighted_f1': float(weighted_f1),
            'per_class': per_class,
            'val_loss': best_val_loss,
            'epochs_trained': epoch + 1,
        }

    # Run baseline (9 labels — original without drift)
    print("\n--- Baseline: 9-label segmenter ---")
    baseline = train_and_eval_segmenter(9, 'baseline_9', train_np, val_np)
    print(f"  Macro F1={baseline['macro_f1']:.4f}, "
          f"Weighted F1={baseline['weighted_f1']:.4f}")

    # Run with drift labels (11 labels)
    print("\n--- Drift-enhanced: 11-label segmenter ---")
    drift = train_and_eval_segmenter(11, 'drift_11', train_np, val_np)
    print(f"  Macro F1={drift['macro_f1']:.4f}, "
          f"Weighted F1={drift['weighted_f1']:.4f}")

    delta_macro = drift['macro_f1'] - baseline['macro_f1']
    delta_weighted = drift['weighted_f1'] - baseline['weighted_f1']

    results = {
        'experiment': 'EXP-286',
        'name': 'isf-drift-segmentation',
        'baseline_9_labels': baseline,
        'drift_11_labels': drift,
        'delta_macro_f1': delta_macro,
        'delta_weighted_f1': delta_weighted,
        'n_train': train_np.shape[0],
        'n_val': val_np.shape[0],
        'input_dim': input_dim,
        'epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n=== Result: Δ Macro F1 = {delta_macro:+.4f}, "
          f"Δ Weighted F1 = {delta_weighted:+.4f} ===")

    # Check drift-specific class F1
    for cls in ['sensitivity_shift', 'resistance_shift']:
        if cls in drift.get('per_class', {}):
            info = drift['per_class'][cls]
            print(f"  {cls}: F1={info['f1']:.4f}, support={info['support']}")

    save_results(results, os.path.join(output_dir, 'exp286_isf_drift_seg.json'))
    return results


# ── EXP-291: UAM Detection via Embedding ──────────────────────────────

def run_uam_detection(args):
    """EXP-291: Can embedding-based UAM beat heuristic detection?

    Uses PatternEncoder embeddings + a simple MLP head to detect
    unannounced meals. Compares to heuristic UAM from event_eval.py.
    """
    from .pattern_embedding import PatternEncoder

    patients_dir = args.patients_dir
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-291: UAM Detection via Pattern Embedding")
    print("=" * 60)

    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_base_data(patient_paths, window_size=24)
    train_np = dataset_to_numpy(train_ds)
    val_np = dataset_to_numpy(val_ds)
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val")

    def label_uam(windows, glucose_scale=400.0):
        """Label windows as UAM (1) or not (0).

        UAM criteria: glucose rises >30 mg/dL in future half,
        with no carb events (channel 5) in recent history.
        """
        half = windows.shape[1] // 2
        glucose_hist = windows[:, :half, 0] * glucose_scale
        glucose_fut = windows[:, half:, 0] * glucose_scale
        carbs_hist = windows[:, max(0, half - 6):half, 5]  # 30min pre-event

        rise = glucose_fut[:, -1] - glucose_hist[:, -1]
        no_carbs = carbs_hist.sum(axis=1) < 0.01

        uam = (rise > 30) & no_carbs
        return uam.astype(np.int64)

    train_uam = label_uam(train_np)
    val_uam = label_uam(val_np)
    print(f"UAM prevalence: train={train_uam.mean():.3f}, val={val_uam.mean():.3f}")

    if train_uam.sum() < 10:
        results = {
            'experiment': 'EXP-291', 'name': 'uam-detection-embedding',
            'error': f'Insufficient UAM events: {train_uam.sum()} in training',
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        }
        save_results(results, os.path.join(output_dir, 'exp291_uam_detection.json'))
        return results

    # Train PatternEncoder + UAM head
    encoder = PatternEncoder(
        input_dim=input_dim, d_model=64, embed_dim=32,
        nhead=4, num_layers=2
    ).to(device)
    uam_head = nn.Linear(32, 2).to(device)

    optimizer = torch.optim.Adam(
        list(encoder.parameters()) + list(uam_head.parameters()),
        lr=1e-3, weight_decay=1e-5
    )

    # Class-weighted loss (UAM is rare)
    n_pos = train_uam.sum()
    n_neg = len(train_uam) - n_pos
    weight = torch.tensor([1.0, n_neg / max(n_pos, 1)]).float().to(device)
    criterion = nn.CrossEntropyLoss(weight=weight)

    half = train_np.shape[1] // 2
    x_train = torch.from_numpy(train_np[:, :half]).float()
    y_train = torch.from_numpy(train_uam).long()
    x_val = torch.from_numpy(val_np[:, :half]).float()
    y_val = torch.from_numpy(val_uam).long()

    best_val_f1 = 0.0
    for epoch in range(epochs):
        encoder.train()
        uam_head.train()
        perm = torch.randperm(len(x_train))
        for start in range(0, len(perm), 32):
            end = min(start + 32, len(perm))
            idx = perm[start:end]
            emb = encoder.encode(x_train[idx].to(device))
            logits = uam_head(emb)
            loss = criterion(logits, y_train[idx].to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # Eval
        encoder.eval()
        uam_head.eval()
        with torch.no_grad():
            val_emb = encoder.encode(x_val.to(device))
            val_logits = uam_head(val_emb)
            val_preds = val_logits.argmax(dim=-1).cpu().numpy()

        from sklearn.metrics import f1_score, precision_score, recall_score
        f1 = f1_score(y_val.numpy(), val_preds, zero_division=0)
        if f1 > best_val_f1:
            best_val_f1 = f1

    # Final evaluation
    encoder.eval()
    uam_head.eval()
    with torch.no_grad():
        val_emb = encoder.encode(x_val.to(device))
        val_logits = uam_head(val_emb)
        val_preds = val_logits.argmax(dim=-1).cpu().numpy()

    from sklearn.metrics import f1_score, precision_score, recall_score
    results = {
        'experiment': 'EXP-291',
        'name': 'uam-detection-embedding',
        'uam_f1': float(f1_score(y_val.numpy(), val_preds, zero_division=0)),
        'uam_precision': float(precision_score(y_val.numpy(), val_preds, zero_division=0)),
        'uam_recall': float(recall_score(y_val.numpy(), val_preds, zero_division=0)),
        'best_val_f1': float(best_val_f1),
        'uam_prevalence_train': float(train_uam.mean()),
        'uam_prevalence_val': float(val_uam.mean()),
        'n_uam_train': int(train_uam.sum()),
        'n_uam_val': int(val_uam.sum()),
        'n_train': len(train_np),
        'n_val': len(val_np),
        'epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n=== UAM Detection: F1={results['uam_f1']:.4f}, "
          f"P={results['uam_precision']:.4f}, R={results['uam_recall']:.4f} ===")

    save_results(results, os.path.join(output_dir, 'exp291_uam_detection.json'))
    return results


# ── Multi-Scale Data Pipeline ──────────────────────────────────────────

SCALE_CONFIG = {
    'fast':    {'window': 24,  'interval_min': 5,  'stride': None},
    'episode': {'window': 144, 'interval_min': 5,  'stride': None},
    'daily':   {'window': 96,  'interval_min': 15, 'stride': 1},
    'weekly':  {'window': 168, 'interval_min': 60, 'stride': 1},
}


def load_aligned_multiscale(patient_paths, scales=('fast', 'episode', 'weekly'),
                            alignment_stride_hr=1, val_fraction=0.2):
    """Load time-aligned windows at multiple scales from a single grid load.

    All windows share the same END timestamp so embeddings describe the same
    moment from different temporal perspectives.

    Args:
        patient_paths: list of patient data directories
        scales: tuple of scale names to load (default: fast+episode+weekly)
        alignment_stride_hr: hours between aligned samples (default=1)
        val_fraction: validation split ratio

    Returns:
        dict of {scale: {'train': np.ndarray, 'val': np.ndarray, 'config': dict}}
        Arrays within each scale are row-aligned across scales.
    """
    from .real_data_adapter import downsample_grid

    configs = {s: SCALE_CONFIG[s] for s in scales}

    # Determine coarsest resolution for alignment
    max_interval = max(configs[s]['interval_min'] for s in scales)
    alignment_steps = max(1, alignment_stride_hr * 60 // max_interval)

    # Minimum history needed (in 5-min steps) to populate longest window
    max_5min_history = max(
        configs[s]['window'] * configs[s]['interval_min'] // 5
        for s in scales
    )

    per_scale_windows = {s: [] for s in scales}

    for i, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"  Patient {patient_id} ({i+1}/{len(patient_paths)}): {path}")

        df, features_5min = _get_cached_grid(path)
        if df is None:
            print(f"    SKIP: no valid data")
            continue

        # Build downsampled grids (once per patient, shared across scales)
        grids = {5: (df, features_5min)}  # 5-min already loaded
        needed_intervals = set(configs[s]['interval_min'] for s in scales)
        for interval in needed_intervals:
            if interval > 5 and interval not in grids:
                df_ds = downsample_grid(df, target_interval_min=interval)
                feat_ds = _grid_to_features(df_ds)
                grids[interval] = (df_ds, feat_ds)

        # Align by end timestamp using 1-hr step on the coarsest grid
        coarse_interval = max_interval
        _, coarse_features = grids[coarse_interval]
        n_coarse = len(coarse_features)

        # Walk through coarse timestamps, extracting aligned sub-windows
        patient_aligned = {s: [] for s in scales}
        n_valid = 0

        # Start from the point where all scales have enough history
        coarse_start = max_5min_history // (coarse_interval // 5)

        for t_coarse in range(coarse_start, n_coarse, alignment_steps):
            valid = True
            windows_at_t = {}

            for s in scales:
                cfg = configs[s]
                interval = cfg['interval_min']
                win_size = cfg['window']
                _, feat = grids[interval]

                # Map coarse index to this scale's index
                t_scale = t_coarse * coarse_interval // interval
                start_idx = t_scale - win_size
                if start_idx < 0 or t_scale > len(feat):
                    valid = False
                    break

                w = feat[start_idx:t_scale].copy()
                if len(w) != win_size:
                    valid = False
                    break

                # Check glucose validity (≥80%)
                glucose_valid = np.sum(~np.isnan(w[:, 0]))
                if glucose_valid / win_size < 0.8:
                    valid = False
                    break

                # Interpolate NaNs in this window
                for col in range(w.shape[1]):
                    mask = np.isnan(w[:, col])
                    if mask.any():
                        v = ~mask
                        if v.sum() >= 2:
                            w[mask, col] = np.interp(
                                np.where(mask)[0], np.where(v)[0], w[v, col])
                        else:
                            w[mask, col] = 0.0

                windows_at_t[s] = w

            if valid:
                for s in scales:
                    patient_aligned[s].append(windows_at_t[s])
                n_valid += 1

        for s in scales:
            per_scale_windows[s].extend(patient_aligned[s])

        print(f"    {n_valid} aligned windows across {len(scales)} scales")

    # Shuffle consistently and split train/val (same indices for all scales)
    n_total = len(per_scale_windows[scales[0]])
    if n_total == 0:
        raise RuntimeError(f"No aligned windows for scales={scales}")

    rng = np.random.RandomState(42)
    perm = rng.permutation(n_total)
    split_idx = int(n_total * (1 - val_fraction))

    result = {}
    for s in scales:
        arr = np.array(per_scale_windows[s], dtype=np.float32)[perm]
        result[s] = {
            'train': arr[:split_idx],
            'val': arr[split_idx:],
            'config': configs[s],
        }

    print(f"\nAligned multi-scale: {n_total} total, {split_idx} train, "
          f"{n_total - split_idx} val")
    for s in scales:
        cfg = configs[s]
        dur = cfg['window'] * cfg['interval_min'] / 60
        print(f"  {s}: {result[s]['train'].shape} train, "
              f"{result[s]['val'].shape} val ({dur:.0f}h window)")

    return result


def load_multiscale_data(patient_paths, scale='episode', val_fraction=0.2):
    """Load data at a specific timescale for pattern experiments.

    Scales:
      fast:    24 steps @ 5-min  = 2h   (acute events)
      episode: 144 steps @ 5-min = 12h  (complete insulin cycles)
      daily:   96 steps @ 15-min = 24h  (ISF drift, dawn phenomenon)
      weekly:  168 steps @ 1-hr  = 7d   (multi-day ISF trends)

    Returns:
      (train_np, val_np) — numpy arrays of shape (N, window_steps, channels)
    """
    from .real_data_adapter import downsample_grid

    cfg = SCALE_CONFIG[scale]
    window = cfg['window']
    interval = cfg['interval_min']
    stride = cfg['stride'] or window // 2

    all_windows = []
    for i, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"  Patient {patient_id} ({i+1}/{len(patient_paths)}): {path}")

        df, features = _get_cached_grid(path)
        if df is None:
            print(f"    SKIP: no valid data")
            continue

        # Downsample if needed
        if interval > 5:
            df_ds = downsample_grid(df, target_interval_min=interval)
            # Rebuild normalized features from downsampled grid
            features = _grid_to_features(df_ds)
        else:
            features = features  # already 5-min, 8ch normalized

        # Split into windows with configurable stride
        windows = _split_windows(features, window, stride)
        if not windows:
            print(f"    SKIP: no valid windows")
            continue

        dur_h = window * interval / 60
        print(f"    {len(df)} rows → {len(windows)} windows "
              f"({features.shape[1]}ch, {dur_h:.0f}h @ {interval}min)")
        all_windows.extend(windows)

    if not all_windows:
        raise RuntimeError(f"No valid windows for scale={scale}")

    rng = np.random.RandomState(42)
    rng.shuffle(all_windows)
    split_idx = int(len(all_windows) * (1 - val_fraction))
    arr = np.array(all_windows, dtype=np.float32)
    return arr[:split_idx], arr[split_idx:]


def _grid_to_features(df):
    """Extract normalized 8-channel features from a grid DataFrame."""
    SCALE = {'glucose': 400.0, 'iob': 20.0, 'cob': 200.0,
             'net_basal': 5.0, 'bolus': 10.0, 'carbs': 100.0}
    t = df.index
    hours = t.hour + t.minute / 60.0
    time_sin = np.sin(2 * np.pi * hours / 24.0)
    time_cos = np.cos(2 * np.pi * hours / 24.0)

    features = np.column_stack([
        df['glucose'].values / SCALE['glucose'],
        df['iob'].values / SCALE['iob'],
        df['cob'].values / SCALE['cob'],
        df['net_basal'].values / SCALE['net_basal'],
        df['bolus'].values / SCALE['bolus'],
        df['carbs'].values / SCALE['carbs'],
        time_sin,
        time_cos,
    ]).astype(np.float32)

    # Fill NaN
    for col in range(features.shape[1]):
        mask = np.isnan(features[:, col])
        if mask.any():
            valid = ~mask
            if valid.sum() >= 2:
                features[mask, col] = np.interp(
                    np.where(mask)[0], np.where(valid)[0], features[valid, col])
            else:
                features[mask, col] = 0.0
    return features


def _split_windows(features, window_size, stride, min_valid=0.8):
    """Split features into windows with configurable stride."""
    windows = []
    for start in range(0, len(features) - window_size + 1, stride):
        w = features[start:start + window_size].copy()
        glucose_valid = np.sum(~np.isnan(w[:, 0]))
        if glucose_valid / window_size >= min_valid:
            for col in range(w.shape[1]):
                mask = np.isnan(w[:, col])
                if mask.any():
                    valid = ~mask
                    if valid.sum() >= 2:
                        w[mask, col] = np.interp(
                            np.where(mask)[0], np.where(valid)[0], w[valid, col])
                    else:
                        w[mask, col] = 0.0
            windows.append(w)
    return windows


# ── Cross-Scale Architecture ───────────────────────────────────────────

class CrossScaleEncoder(nn.Module):
    """Encodes patterns at multiple timescales and concatenates embeddings.

    Wraps independent PatternEncoders for each scale. The concatenated
    embedding captures the same moment from fast (2h), episode (12h),
    and weekly (7d) temporal perspectives.

    Output dim = sum(per-scale embed_dim) = e.g. 3 × 32 = 96.
    """

    def __init__(self, scale_configs, input_dim=8, d_model=64, nhead=4,
                 num_layers=2, embed_dim=32):
        """
        Args:
            scale_configs: dict of {scale_name: {'window': int, ...}}
            input_dim: channels per scale (default 8)
            d_model: transformer hidden dim
            embed_dim: per-scale embedding dim (total = len(scales) * embed_dim)
        """
        super().__init__()
        from .pattern_embedding import PatternEncoder

        self.scale_names = sorted(scale_configs.keys())
        self.embed_dim = embed_dim
        self.total_embed_dim = len(self.scale_names) * embed_dim

        self.encoders = nn.ModuleDict({
            name: PatternEncoder(
                input_dim=input_dim, d_model=d_model, nhead=nhead,
                num_layers=num_layers, embed_dim=embed_dim,
            )
            for name in self.scale_names
        })

        # Learned scale attention (optional weighting)
        self.scale_attention = nn.Parameter(
            torch.ones(len(self.scale_names)) / len(self.scale_names)
        )

    def forward(self, scale_inputs):
        """
        Args:
            scale_inputs: dict of {scale_name: (B, T_scale, C)} tensors

        Returns:
            (B, total_embed_dim) L2-normalized concatenated embedding
        """
        embeddings = []
        weights = F.softmax(self.scale_attention, dim=0)

        for i, name in enumerate(self.scale_names):
            emb = self.encoders[name](scale_inputs[name])  # (B, embed_dim)
            embeddings.append(emb * weights[i])

        concat = torch.cat(embeddings, dim=-1)  # (B, total_embed_dim)
        return F.normalize(concat, p=2, dim=-1)

    def encode_scale(self, name, x):
        """Encode a single scale (for per-scale evaluation)."""
        return self.encoders[name](x)


def train_cross_scale_encoder(encoder, train_data, val_data, train_labels,
                              val_labels, epochs=30, batch_size=32, lr=1e-3,
                              device='cpu'):
    """Train a CrossScaleEncoder with triplet loss on concatenated embeddings.

    Args:
        encoder: CrossScaleEncoder instance
        train_data: dict of {scale: np.ndarray (N, T, C)}
        val_data: dict of {scale: np.ndarray (N, T, C)}
        train_labels: list of list of strings, length N
        val_labels: list of list of strings, length N

    Returns:
        trained encoder, history dict
    """
    from .pattern_embedding import build_triplets, TripletPatternLoss

    scales = encoder.scale_names
    encoder = encoder.to(device)
    optimizer = torch.optim.Adam(encoder.parameters(), lr=lr, weight_decay=1e-5)
    triplet_loss = TripletPatternLoss(margin=1.0)

    train_tensors = {s: torch.from_numpy(train_data[s]).float() for s in scales}
    n_train = len(train_labels)

    # Build triplets using train_labels (same for all scales since aligned)
    triplets = build_triplets(
        train_data[scales[0]], train_labels,
        n_triplets=min(20000, n_train * 3)
    )
    if len(triplets) < batch_size:
        return encoder, {'error': 'insufficient triplets'}

    triplet_arr = np.array(triplets, dtype=np.int64)
    history = {'train_loss': [], 'val_loss': []}

    for epoch in range(epochs):
        encoder.train()
        perm = np.random.permutation(len(triplet_arr))
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, len(perm), batch_size):
            end = min(start + batch_size, len(perm))
            idx = perm[start:end]
            batch_triplets = triplet_arr[idx]

            a_idx = batch_triplets[:, 0]
            p_idx = batch_triplets[:, 1]
            n_idx = batch_triplets[:, 2]

            # Build per-scale inputs for anchor/positive/negative
            a_inputs = {s: train_tensors[s][a_idx].to(device) for s in scales}
            p_inputs = {s: train_tensors[s][p_idx].to(device) for s in scales}
            n_inputs = {s: train_tensors[s][n_idx].to(device) for s in scales}

            a_emb = encoder(a_inputs)
            p_emb = encoder(p_inputs)
            n_emb = encoder(n_inputs)

            loss = triplet_loss(a_emb, p_emb, n_emb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        history['train_loss'].append(avg_loss)

        # Validation loss
        encoder.eval()
        with torch.no_grad():
            val_tensors = {s: torch.from_numpy(val_data[s]).float() for s in scales}
            val_triplets = build_triplets(
                val_data[scales[0]], val_labels,
                n_triplets=min(5000, len(val_labels) * 2)
            )
            if len(val_triplets) >= batch_size:
                vt = np.array(val_triplets[:min(2000, len(val_triplets))], dtype=np.int64)
                va = {s: val_tensors[s][vt[:, 0]].to(device) for s in scales}
                vp = {s: val_tensors[s][vt[:, 1]].to(device) for s in scales}
                vn = {s: val_tensors[s][vt[:, 2]].to(device) for s in scales}
                v_loss = triplet_loss(encoder(va), encoder(vp), encoder(vn)).item()
            else:
                v_loss = float('nan')
        history['val_loss'].append(v_loss)

        if epoch % 5 == 0 or epoch == epochs - 1:
            print(f"  Epoch {epoch+1}/{epochs}: train_loss={avg_loss:.4f}, "
                  f"val_loss={v_loss:.4f}")

    return encoder, history


def eval_cross_scale_encoder(encoder, val_data, val_labels, device='cpu',
                             batch_size=512):
    """Evaluate cross-scale encoder: Recall@5 and Silhouette on val set."""
    from .pattern_embedding import retrieval_recall_at_k
    from sklearn.metrics import silhouette_score

    scales = encoder.scale_names
    encoder = encoder.to(device).eval()

    # Encode in batches
    all_embs = []
    n_val = len(val_data[scales[0]])
    with torch.no_grad():
        for start in range(0, n_val, batch_size):
            end = min(start + batch_size, n_val)
            batch = {
                s: torch.from_numpy(val_data[s][start:end]).float().to(device)
                for s in scales
            }
            emb = encoder(batch)
            all_embs.append(emb.cpu().numpy())

    embeddings = np.concatenate(all_embs, axis=0)

    # Flatten labels for evaluation
    flat_labels = []
    for lab_list in val_labels:
        flat_labels.append(lab_list[0] if isinstance(lab_list, list) else lab_list)

    r5 = retrieval_recall_at_k(embeddings, flat_labels, k=5)
    unique_labels = list(set(flat_labels))
    if len(unique_labels) >= 2:
        label_ints = [unique_labels.index(l) for l in flat_labels]
        sil = silhouette_score(embeddings, label_ints,
                               metric='cosine', sample_size=min(5000, len(label_ints)))
    else:
        sil = float('nan')

    return {'recall_at_5': r5, 'silhouette': sil, 'n_val': n_val,
            'embed_dim': embeddings.shape[1], 'n_unique_labels': len(unique_labels)}


# ── Multi-Scale Experiments ────────────────────────────────────────────

def run_ablation_12h(args):
    """EXP-298: Re-run channel ablation at 12h window.

    Hypothesis: Feature importance deltas become MUCH larger when the model
    sees the full insulin DIA cycle. At 2h, all deltas were <1.12%.
    """
    from .pattern_embedding import PatternEncoder

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-298: Channel Ablation at 12h (144-step) Window")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='episode')
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val, "
          f"{input_dim} channels, window={train_np.shape[1]} steps")

    train_labels = build_episode_labels_batch(train_np)
    val_labels = build_episode_labels_batch(val_np)

    # Baseline
    print("\n--- Baseline (all channels) ---")
    encoder = PatternEncoder(input_dim=input_dim, d_model=64, embed_dim=32,
                             nhead=4, num_layers=2)
    encoder, _ = train_pattern_encoder(
        encoder, train_np, train_labels, val_np, val_labels,
        epochs=epochs, device=device)
    baseline = eval_pattern_encoder(encoder, val_np, val_labels, device=device)
    print(f"Baseline: Recall@5={baseline['recall_at_5']:.4f}, "
          f"Silhouette={baseline['silhouette']:.4f}")

    # Per-channel ablation
    channel_names = ['glucose', 'iob', 'cob', 'basal_rate', 'bolus',
                     'carbs', 'time_sin', 'time_cos']
    ablations = {}
    for ch_idx, ch_name in enumerate(channel_names):
        print(f"\n--- Ablating {ch_name} (channel {ch_idx}) ---")
        train_abl = train_np.copy()
        val_abl = val_np.copy()
        train_abl[:, :, ch_idx] = 0.0
        val_abl[:, :, ch_idx] = 0.0

        enc = PatternEncoder(input_dim=input_dim, d_model=64, embed_dim=32,
                             nhead=4, num_layers=2)
        enc, hist = train_pattern_encoder(
            enc, train_abl, train_labels, val_abl, val_labels,
            epochs=epochs, device=device)
        m = eval_pattern_encoder(enc, val_abl, val_labels, device=device)

        dr = m['recall_at_5'] - baseline['recall_at_5']
        ds = m['silhouette'] - baseline['silhouette']
        ablations[ch_name] = {
            'channels_masked': [ch_idx],
            'metrics': m,
            'delta_recall_at_5': dr,
            'delta_silhouette': ds,
            'train_epochs': len(hist.get('train_loss', [])),
        }
        print(f"  Recall@5={m['recall_at_5']:.4f} (Δ={dr:+.4f}), "
              f"Silhouette={m['silhouette']:.4f} (Δ={ds:+.4f})")

    # Ranking
    ranking = sorted(ablations.items(), key=lambda x: x[1]['delta_recall_at_5'])
    print(f"\n=== Feature Importance at 12h (by Recall@5 drop) ===")
    for name, v in ranking:
        print(f"  {name:15s}: ΔRecall={v['delta_recall_at_5']:+.4f}, "
              f"ΔSilhouette={v['delta_silhouette']:+.4f}")

    # Compare with 2h results
    print(f"\n=== Comparison: 2h vs 12h max |ΔRecall| ===")
    max_delta_12h = max(abs(v['delta_recall_at_5']) for v in ablations.values())
    print(f"  12h max |ΔRecall|: {max_delta_12h:.4f}")
    print(f"  2h max |ΔRecall|:  0.0112 (basal_rate from EXP-287)")

    results = {
        'baseline': baseline,
        'ablations': ablations,
        'ranking': [{'group': n, 'delta_recall': v['delta_recall_at_5'],
                     'delta_silhouette': v['delta_silhouette']}
                    for n, v in ranking],
        'experiment': 'EXP-298',
        'name': 'channel-ablation-embedding-12h',
        'scale': 'episode',
        'window_steps': 144,
        'window_hours': 12,
        'input_dim': input_dim,
        'n_train': len(train_np),
        'n_val': len(val_np),
        'epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    save_results(results, os.path.join(output_dir, 'exp298_ablation_12h.json'))
    return results


def run_uam_12h(args):
    """EXP-299: UAM detection at 12h window.

    Hypothesis: Precision improves because the model sees the full
    meal→absorption→resolution cycle, reducing false positives from
    dawn phenomenon and rebound highs.
    """
    from .pattern_embedding import PatternEncoder

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-299: UAM Detection at 12h (144-step) Window")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='episode')
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val")

    # Build UAM labels
    train_labels = build_episode_labels_batch(train_np)
    val_labels = build_episode_labels_batch(val_np)
    train_uam = np.array([1 if 'meal_response' in lbl and 'correction_response' not in lbl
                          else 0 for lbl in train_labels])
    val_uam = np.array([1 if 'meal_response' in lbl and 'correction_response' not in lbl
                        else 0 for lbl in val_labels])
    print(f"UAM prevalence: train={train_uam.mean():.3f}, val={val_uam.mean():.3f}")

    # Train encoder
    encoder = PatternEncoder(input_dim=input_dim, d_model=64, embed_dim=32,
                             nhead=4, num_layers=2)
    encoder, _ = train_pattern_encoder(
        encoder, train_np, train_labels, val_np, val_labels,
        epochs=epochs, device=device)

    # Train UAM classifier on embeddings
    with torch.no_grad():
        encoder.eval()
        x_train = torch.tensor(train_np, dtype=torch.float32)
        x_val = torch.tensor(val_np, dtype=torch.float32)
        train_emb = encoder.encode(x_train.to(device))
        val_emb = encoder.encode(x_val.to(device))

    embed_dim = train_emb.shape[1]
    uam_head = nn.Linear(embed_dim, 2).to(device)
    opt = torch.optim.Adam(uam_head.parameters(), lr=1e-3)
    y_train = torch.tensor(train_uam, dtype=torch.long).to(device)
    y_val = torch.tensor(val_uam, dtype=torch.long).to(device)

    # Class weighting for imbalanced UAM
    n_pos = max(train_uam.sum(), 1)
    n_neg = max(len(train_uam) - n_pos, 1)
    weight = torch.tensor([1.0, n_neg / n_pos], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight)

    best_val_f1 = 0
    for ep in range(min(epochs, 50)):
        uam_head.train()
        logits = uam_head(train_emb)
        loss = criterion(logits, y_train)
        opt.zero_grad()
        loss.backward()
        opt.step()

        uam_head.eval()
        with torch.no_grad():
            vl = uam_head(val_emb)
            vp = vl.argmax(dim=-1).cpu().numpy()
            from sklearn.metrics import f1_score
            vf1 = f1_score(val_uam, vp, zero_division=0)
            best_val_f1 = max(best_val_f1, vf1)

    # Final eval
    uam_head.eval()
    with torch.no_grad():
        val_logits = uam_head(val_emb)
        val_preds = val_logits.argmax(dim=-1).cpu().numpy()

    from sklearn.metrics import f1_score, precision_score, recall_score
    results = {
        'experiment': 'EXP-299',
        'name': 'uam-detection-12h',
        'scale': 'episode',
        'window_steps': 144,
        'window_hours': 12,
        'uam_f1': float(f1_score(val_uam, val_preds, zero_division=0)),
        'uam_precision': float(precision_score(val_uam, val_preds, zero_division=0)),
        'uam_recall': float(recall_score(val_uam, val_preds, zero_division=0)),
        'best_val_f1': float(best_val_f1),
        'uam_prevalence_train': float(train_uam.mean()),
        'uam_prevalence_val': float(val_uam.mean()),
        'n_train': len(train_np),
        'n_val': len(val_np),
        'epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n=== UAM at 12h: F1={results['uam_f1']:.4f}, "
          f"P={results['uam_precision']:.4f}, R={results['uam_recall']:.4f} ===")
    print(f"  (vs 2h: F1=0.399, P=0.283, R=0.676)")

    save_results(results, os.path.join(output_dir, 'exp299_uam_12h.json'))
    return results


def run_daily_drift(args):
    """EXP-300: Drift segmentation at 24h/15-min resolution.

    Uses downsampled data so 24h of context fits in 96 steps.
    With 24h windows, ISF drift patterns should be detectable even
    without enriched ISF profile features.
    """
    from .pattern_retrieval import EpisodeSegmenter, EPISODE_LABELS

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-300: Drift Segmentation at 24h (96-step @ 15-min)")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='daily')
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val, "
          f"{input_dim}ch, window={train_np.shape[1]} steps (24h)")

    train_labels = build_episode_labels_batch(train_np, glucose_scale=400.0)
    val_labels = build_episode_labels_batch(val_np, glucose_scale=400.0)

    # Count label distribution
    from collections import Counter
    all_labels = [l for labels in train_labels for l in labels]
    dist = Counter(all_labels)
    print(f"Label distribution: {dict(dist.most_common())}")

    # 11-label (with drift)
    n_labels = len(EPISODE_LABELS)
    print(f"\n--- {n_labels}-label segmenter (with drift) ---")
    seg = EpisodeSegmenter(input_dim=input_dim, n_labels=n_labels,
                           d_model=64, nhead=4, num_layers=2)

    # Convert multi-label to primary label for training
    label_to_idx = {l: i for i, l in enumerate(EPISODE_LABELS)}
    def primary_label(labels):
        for l in labels:
            if l != 'stable' and l in label_to_idx:
                return label_to_idx[l]
        return label_to_idx.get('stable', 0)

    train_y = torch.tensor([primary_label(l) for l in train_labels], dtype=torch.long)
    val_y = torch.tensor([primary_label(l) for l in val_labels], dtype=torch.long)

    # Train
    seg = seg.to(device)
    opt = torch.optim.Adam(seg.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    train_tensor = torch.tensor(train_np, dtype=torch.float32)
    val_tensor = torch.tensor(val_np, dtype=torch.float32)

    best_val_loss = float('inf')
    patience_counter = 0
    for ep in range(epochs):
        seg.train()
        indices = torch.randperm(len(train_tensor))
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, len(indices), 64):
            batch_idx = indices[start:start+64]
            x = train_tensor[batch_idx].to(device)
            y = train_y[batch_idx].to(device)
            logits = seg(x)  # [B, T, n_labels]
            # Pool per-timestep logits to per-window classification
            logits_pooled = logits.mean(dim=1)  # [B, n_labels]
            loss = criterion(logits_pooled, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            epoch_loss += loss.item()
            n_batches += 1

        seg.eval()
        with torch.no_grad():
            # Batched validation to avoid OOM with large datasets
            val_loss_sum = 0.0
            for vs in range(0, len(val_tensor), 512):
                vb = val_tensor[vs:vs+512].to(device)
                vy = val_y[vs:vs+512].to(device)
                vl_logits = seg(vb)
                val_loss_sum += criterion(vl_logits.mean(dim=1), vy).item() * len(vb)
            vl_avg = val_loss_sum / len(val_tensor)
        if vl_avg < best_val_loss:
            best_val_loss = vl_avg
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= 5:
                break

    seg.eval()
    all_preds = []
    with torch.no_grad():
        for vs in range(0, len(val_tensor), 512):
            vb = val_tensor[vs:vs+512].to(device)
            vl_logits = seg(vb)
            vp = vl_logits.mean(dim=1).argmax(dim=-1).cpu()
            all_preds.append(vp)
    val_preds = torch.cat(all_preds).numpy()

    from sklearn.metrics import f1_score
    macro_f1 = f1_score(val_y.numpy(), val_preds, average='macro', zero_division=0)
    weighted_f1 = f1_score(val_y.numpy(), val_preds, average='weighted', zero_division=0)
    print(f"  Macro F1={macro_f1:.4f}, Weighted F1={weighted_f1:.4f}")

    # Check if drift labels were actually assigned
    drift_labels = {'sensitivity_shift', 'resistance_shift'}
    drift_count = sum(1 for labels in train_labels
                      for l in labels if l in drift_labels)
    print(f"  Drift labels in training: {drift_count} "
          f"({drift_count/len(train_labels)*100:.1f}% of windows)")

    results = {
        'experiment': 'EXP-300',
        'name': 'drift-segmentation-24h',
        'scale': 'daily',
        'window_steps': 96,
        'resolution_min': 15,
        'window_hours': 24,
        'macro_f1': float(macro_f1),
        'weighted_f1': float(weighted_f1),
        'n_labels': n_labels,
        'drift_label_count': drift_count,
        'label_distribution': dict(dist.most_common()),
        'n_train': len(train_np),
        'n_val': len(val_np),
        'epochs_trained': ep + 1,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n=== Daily Drift: Macro F1={macro_f1:.4f} ===")
    print(f"  (vs 2h baseline: Macro F1=0.861)")

    save_results(results, os.path.join(output_dir, 'exp300_drift_24h.json'))
    return results


def run_weekly_isf(args):
    """EXP-301: Weekly ISF trend detection at 7-day/1-hr resolution.

    Can we detect multi-day ISF drift patterns (sick days, menstrual cycle,
    exercise adaptation) using weekly-scale embeddings?
    """
    from .pattern_embedding import PatternEncoder

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-301: Weekly ISF Trends (168-step @ 1-hr = 7 days)")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='weekly')
    input_dim = train_np.shape[2]
    print(f"Data: {train_np.shape[0]} train, {val_np.shape[0]} val, "
          f"{input_dim}ch, window={train_np.shape[1]} steps (7 days)")

    train_labels = build_episode_labels_batch(train_np, glucose_scale=400.0)
    val_labels = build_episode_labels_batch(val_np, glucose_scale=400.0)

    # Train encoder
    encoder = PatternEncoder(input_dim=input_dim, d_model=64, embed_dim=32,
                             nhead=4, num_layers=2)
    encoder, hist = train_pattern_encoder(
        encoder, train_np, train_labels, val_np, val_labels,
        epochs=epochs, device=device)
    metrics = eval_pattern_encoder(encoder, val_np, val_labels, device=device)

    # Analyze: do weekly embeddings cluster by ISF drift state?
    from collections import Counter
    all_labels = [l for labels in val_labels for l in labels]
    dist = Counter(all_labels)

    results = {
        'experiment': 'EXP-301',
        'name': 'weekly-isf-trends',
        'scale': 'weekly',
        'window_steps': 168,
        'resolution_min': 60,
        'window_days': 7,
        'recall_at_5': float(metrics['recall_at_5']),
        'silhouette': float(metrics['silhouette']),
        'n_unique_labels': metrics.get('n_unique_labels', 0),
        'label_distribution': dict(dist.most_common()),
        'n_train': len(train_np),
        'n_val': len(val_np),
        'train_epochs': len(hist.get('train_loss', [])),
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n=== Weekly: Recall@5={metrics['recall_at_5']:.4f}, "
          f"Silhouette={metrics['silhouette']:.4f} ===")
    print(f"  (vs 2h: R@5=0.950, Sil=-0.367)")
    print(f"  (vs 12h: R@5=0.952, Sil=-0.339)")

    save_results(results, os.path.join(output_dir, 'exp301_weekly_isf.json'))
    return results


# ── Cross-Scale Experiments ────────────────────────────────────────────

def run_cross_scale_retrieval(args):
    """EXP-304: Cross-scale retrieval — does combining fast+episode+weekly
    beat any single scale for pattern retrieval?

    Staged approach (avoids joint-training convergence issues):
    1. Train each per-scale encoder INDEPENDENTLY with triplet loss
    2. Freeze per-scale encoders
    3. Generate per-scale embeddings on validation set
    4. Concatenate → evaluate cross-scale R@5 and Silhouette
    5. Compare: cross-scale vs best single-scale (weekly, Sil=-0.301)

    Uses 6h alignment stride to reduce temporal autocorrelation.
    """
    from .pattern_embedding import PatternEncoder, retrieval_recall_at_k
    from sklearn.metrics import silhouette_score

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-304: Cross-Scale Retrieval (staged training)")
    print("=" * 60)

    # Load aligned data with 6h stride (reduces temporal autocorrelation)
    scales = ('fast', 'episode', 'weekly')
    data = load_aligned_multiscale(patient_paths, scales=scales,
                                   alignment_stride_hr=6)

    # Build labels from episode-scale windows (best granularity)
    print("\nBuilding episode labels...")
    train_labels = build_episode_labels_batch(data['episode']['train'])
    val_labels = build_episode_labels_batch(data['episode']['val'])
    flat_val_labels = [l[0] if isinstance(l, list) else l for l in val_labels]

    # Stage 1: Train each per-scale encoder independently
    per_scale_encoders = {}
    per_scale_metrics = {}

    for s in scales:
        print(f"\n--- Training {s}-scale encoder ---")
        enc = PatternEncoder(
            input_dim=8, d_model=64, nhead=4, num_layers=2, embed_dim=32,
        )
        enc, hist = train_pattern_encoder(
            enc, data[s]['train'], train_labels,
            data[s]['val'], val_labels,
            epochs=epochs, batch_size=32, lr=1e-3, device=device,
        )
        per_scale_encoders[s] = enc

        # Evaluate per-scale
        enc = enc.to(device).eval()
        all_embs = []
        n_val = len(data[s]['val'])
        with torch.no_grad():
            for start in range(0, n_val, 512):
                end = min(start + 512, n_val)
                batch = torch.from_numpy(data[s]['val'][start:end]).float().to(device)
                emb = enc(batch)
                all_embs.append(emb.cpu().numpy())
        embeddings = np.concatenate(all_embs)

        r5 = retrieval_recall_at_k(embeddings, flat_val_labels, k=5)
        unique_labels = list(set(flat_val_labels))
        label_ints = [unique_labels.index(l) for l in flat_val_labels]
        sil = silhouette_score(embeddings, label_ints, metric='cosine',
                               sample_size=min(5000, len(label_ints)))
        per_scale_metrics[s] = {
            'recall_at_5': float(r5), 'silhouette': float(sil),
            'embed_dim': 32,
        }
        print(f"  {s}: R@5={r5:.4f}, Sil={sil:.4f}")

    # Stage 2: Generate all per-scale embeddings and concatenate
    print(f"\n--- Cross-scale concatenation ---")
    per_scale_embs = {}
    for s in scales:
        enc = per_scale_encoders[s].to(device).eval()
        all_embs = []
        n_val = len(data[s]['val'])
        with torch.no_grad():
            for start in range(0, n_val, 512):
                end = min(start + 512, n_val)
                batch = torch.from_numpy(data[s]['val'][start:end]).float().to(device)
                emb = enc(batch)
                all_embs.append(emb.cpu().numpy())
        per_scale_embs[s] = np.concatenate(all_embs)

    # Concatenate: [fast_32d || episode_32d || weekly_32d] = 96d
    cross_emb = np.concatenate([per_scale_embs[s] for s in scales], axis=1)
    cross_emb_norm = cross_emb / (np.linalg.norm(cross_emb, axis=1, keepdims=True) + 1e-8)

    r5_cross = retrieval_recall_at_k(cross_emb_norm, flat_val_labels, k=5)
    unique_labels = list(set(flat_val_labels))
    label_ints = [unique_labels.index(l) for l in flat_val_labels]
    sil_cross = silhouette_score(cross_emb_norm, label_ints, metric='cosine',
                                 sample_size=min(5000, len(label_ints)))

    cross_metrics = {
        'recall_at_5': float(r5_cross), 'silhouette': float(sil_cross),
        'embed_dim': cross_emb.shape[1], 'n_val': len(flat_val_labels),
        'n_unique_labels': len(unique_labels),
    }

    # Build CrossScaleEncoder and load trained weights for checkpoint
    scale_configs = {s: SCALE_CONFIG[s] for s in scales}
    cross_encoder = CrossScaleEncoder(
        scale_configs, input_dim=8, d_model=64, nhead=4,
        num_layers=2, embed_dim=32,
    )
    for s in scales:
        cross_encoder.encoders[s].load_state_dict(per_scale_encoders[s].state_dict())
    total_params = sum(p.numel() for p in cross_encoder.parameters())

    results = {
        'experiment': 'EXP-304',
        'name': 'cross-scale-retrieval-staged',
        'scales': list(scales),
        'alignment_stride_hr': 6,
        'training_method': 'staged (independent per-scale, then concat)',
        'cross_scale': cross_metrics,
        'per_scale': per_scale_metrics,
        'total_params': total_params,
        'embed_dim': cross_emb.shape[1],
        'n_train': len(train_labels),
        'n_val': len(flat_val_labels),
        'train_epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    # Determine best single scale
    best_s = max(per_scale_metrics, key=lambda s: per_scale_metrics[s]['silhouette'])
    best_sil = per_scale_metrics[best_s]['silhouette']
    delta_sil = sil_cross - best_sil
    results['best_single_scale'] = best_s
    results['delta_sil_vs_best'] = float(delta_sil)

    print(f"\n{'='*60}")
    print(f"Cross-scale (96d): R@5={r5_cross:.4f}, Sil={sil_cross:.4f}")
    for s in scales:
        m = per_scale_metrics[s]
        marker = " ← best single" if s == best_s else ""
        print(f"  {s:10s} (32d): R@5={m['recall_at_5']:.4f}, Sil={m['silhouette']:.4f}{marker}")
    print(f"\nΔSil vs best single ({best_s}): {delta_sil:+.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp304_cross_scale.json'))

    # Save checkpoint for EXP-305
    ckpt_path = os.path.join(output_dir, 'cross_scale_encoder.pth')
    torch.save({
        'model_state': cross_encoder.state_dict(),
        'scale_configs': scale_configs,
        'scales': list(scales),
        'embed_dim': 32,
        'cross_metrics': cross_metrics,
    }, ckpt_path)
    print(f"Saved checkpoint: {ckpt_path}")

    return results


def run_multiscale_override(args):
    """EXP-305: Scale-comparison override recommendation.

    EXP-304 showed cross-scale concat hurts retrieval (ΔSil=-0.525 vs weekly).
    This experiment tests whether multi-scale context helps CLASSIFICATION:
    - Does weekly embedding + glucose state beat glucose state alone?
    - Does adding fast/episode context help or hurt override classification?

    Compares 4 input configurations:
    1. state-only (10d) — glucose state baseline
    2. weekly+state (42d) — best retrieval scale + state
    3. episode+state (42d) — mid scale + state
    4. cross-scale+state (106d) — all scales + state
    """
    from .pattern_override import extract_glucose_state
    from .pattern_embedding import PatternEncoder

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-305: Scale-Comparison Override Classification")
    print("=" * 60)

    # Load aligned data with 6h stride (matching EXP-304)
    scales = ('fast', 'episode', 'weekly')
    data = load_aligned_multiscale(patient_paths, scales=scales,
                                   alignment_stride_hr=6)

    # Load pretrained per-scale encoders from EXP-304 checkpoint
    ckpt_path = os.path.join(output_dir, 'cross_scale_encoder.pth')
    scale_configs = {s: SCALE_CONFIG[s] for s in scales}

    if os.path.exists(ckpt_path):
        print(f"Loading pretrained encoders from: {ckpt_path}")
        ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        cross_encoder = CrossScaleEncoder(
            scale_configs, input_dim=8, d_model=64, nhead=4,
            num_layers=2, embed_dim=32,
        )
        cross_encoder.load_state_dict(ckpt['model_state'])
        per_scale_encoders = {s: cross_encoder.encoders[s] for s in scales}
    else:
        print("No pretrained encoder — training per-scale from scratch")
        train_labels = build_episode_labels_batch(data['episode']['train'])
        val_labels = build_episode_labels_batch(data['episode']['val'])
        per_scale_encoders = {}
        for s in scales:
            enc = PatternEncoder(
                input_dim=8, d_model=64, nhead=4, num_layers=2, embed_dim=32,
            )
            enc, _ = train_pattern_encoder(
                enc, data[s]['train'], train_labels,
                data[s]['val'], val_labels,
                epochs=epochs, batch_size=32, lr=1e-3, device=device,
            )
            per_scale_encoders[s] = enc

    # Generate embeddings for val set
    val_data = {s: data[s]['val'] for s in scales}
    n_val = len(val_data['fast'])

    per_scale_embs = {}
    for s in scales:
        enc = per_scale_encoders[s].to(device).eval()
        embs = []
        with torch.no_grad():
            for start in range(0, n_val, 512):
                end = min(start + 512, n_val)
                batch = torch.from_numpy(val_data[s][start:end]).float().to(device)
                embs.append(enc(batch).cpu().numpy())
        per_scale_embs[s] = np.concatenate(embs)  # (N, 32)

    cross_emb = np.concatenate([per_scale_embs[s] for s in scales], axis=1)  # (N, 96)

    # Build FORWARD-LOOKING override labels from fast window trajectory
    # Split fast window: first 12 steps (1h) = context, last 12 steps (1h) = future
    # This makes pattern embeddings meaningful — they predict what WILL happen
    fast_val = val_data['fast']  # (N, 24, 8)
    context_steps = 12  # first 1h for state extraction
    future_steps = 12   # last 1h for label generation

    # Extract glucose state from CONTEXT portion only (first 1h)
    glucose_states = np.array([
        extract_glucose_state(fast_val[i, :context_steps, :], glucose_scale=400.0)
        for i in range(n_val)
    ])  # (N, 10)

    # Labels from FUTURE portion: what happens in the next hour?
    future_glucose = fast_val[:, context_steps:, 0] * 400.0  # (N, 12) denormalized
    future_max = future_glucose.max(axis=1)
    future_min = future_glucose.min(axis=1)
    current_glucose = fast_val[:, context_steps - 1, 0] * 400.0  # glucose at split point

    needs_override = np.zeros(n_val, dtype=np.int64)
    # Class 1: will go high (future max > 180 AND currently in-range)
    needs_override[(future_max > 180) & (current_glucose <= 180)] = 1
    # Class 2: will go low (future min < 70 AND currently not low)
    needs_override[(future_min < 70) & (current_glucose >= 70)] = 2
    # Class 3: will spike very high (future max > 250)
    needs_override[future_max > 250] = 3

    override_dist = {
        'none': int((needs_override == 0).sum()),
        'upcoming_high': int((needs_override == 1).sum()),
        'upcoming_low': int((needs_override == 2).sum()),
        'upcoming_spike': int((needs_override == 3).sum()),
    }
    print(f"\nForward-looking override distribution: {override_dist}")
    in_range_now = (current_glucose >= 70) & (current_glucose <= 180)
    tir_baseline = float(in_range_now.mean())
    print(f"Current TIR (at split point): {tir_baseline:.4f}")

    # Compute class weights for imbalanced loss
    class_counts = np.bincount(needs_override, minlength=4).astype(np.float32)
    class_counts = np.maximum(class_counts, 1.0)  # avoid div by zero
    class_weights = (1.0 / class_counts) * n_val / 4.0
    class_weights_t = torch.from_numpy(class_weights).float().to(device)
    print(f"Class weights: {dict(zip(['none','high','low','spike'], class_weights_t.cpu().tolist()))}")

    # Define input configurations to compare
    configs = {
        'state-only': glucose_states,                                       # 10d
        'weekly+state': np.concatenate([glucose_states, per_scale_embs['weekly']], axis=1),  # 42d
        'episode+state': np.concatenate([glucose_states, per_scale_embs['episode']], axis=1), # 42d
        'cross+state': np.concatenate([glucose_states, cross_emb], axis=1),  # 106d
    }

    # Train and evaluate a simple MLP classifier for each config
    # (Using a plain MLP rather than PatternOverridePolicy to isolate
    #  the input representation as the variable under test)
    target_t = torch.from_numpy(needs_override).long()
    train_idx = int(n_val * 0.8)

    config_results = {}
    for cfg_name, features in configs.items():
        print(f"\n--- {cfg_name} ({features.shape[1]}d) ---")
        features_t = torch.from_numpy(features).float()

        classifier = nn.Sequential(
            nn.Linear(features.shape[1], 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 4),  # 4 override classes
        ).to(device)
        optimizer = torch.optim.Adam(classifier.parameters(), lr=1e-3,
                                     weight_decay=1e-4)
        ce_loss = nn.CrossEntropyLoss(weight=class_weights_t)

        train_x = features_t[:train_idx].to(device)
        train_y = target_t[:train_idx].to(device)
        val_x = features_t[train_idx:].to(device)
        val_y = target_t[train_idx:].to(device)

        best_val_acc = 0.0
        for epoch in range(epochs):
            classifier.train()
            logits = classifier(train_x)
            loss = ce_loss(logits, train_y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            classifier.eval()
            with torch.no_grad():
                vl = classifier(val_x)
                acc = (vl.argmax(dim=1) == val_y).float().mean().item()
            best_val_acc = max(best_val_acc, acc)

            if epoch % 10 == 0 or epoch == epochs - 1:
                print(f"  Epoch {epoch+1}/{epochs}: loss={loss.item():.4f}, acc={acc:.4f}")

        # Full-set eval
        classifier.eval()
        with torch.no_grad():
            all_l = classifier(features_t.to(device))
            preds = all_l.argmax(dim=1).cpu().numpy()
        full_acc = float((preds == needs_override).mean())

        # Per-class F1
        from sklearn.metrics import f1_score, classification_report
        macro_f1 = float(f1_score(needs_override, preds, average='macro', zero_division=0))
        weighted_f1 = float(f1_score(needs_override, preds, average='weighted', zero_division=0))

        config_results[cfg_name] = {
            'input_dim': features.shape[1],
            'full_accuracy': full_acc,
            'best_val_accuracy': float(best_val_acc),
            'macro_f1': macro_f1,
            'weighted_f1': weighted_f1,
        }
        print(f"  → Acc={full_acc:.4f}, Macro-F1={macro_f1:.4f}, "
              f"W-F1={weighted_f1:.4f}")

    # Determine best configuration
    best_cfg = max(config_results, key=lambda c: config_results[c]['macro_f1'])
    best_f1 = config_results[best_cfg]['macro_f1']

    results = {
        'experiment': 'EXP-305',
        'name': 'scale-comparison-override',
        'alignment_stride_hr': 6,
        'scales': list(scales),
        'tir_baseline': tir_baseline,
        'override_distribution': override_dist,
        'configs': config_results,
        'best_config': best_cfg,
        'best_macro_f1': best_f1,
        'n_total': n_val,
        'n_train': train_idx,
        'n_val_policy': n_val - train_idx,
        'train_epochs': epochs,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Scale Comparison — Override Classification")
    print(f"{'='*60}")
    for cfg, m in config_results.items():
        marker = " ← BEST" if cfg == best_cfg else ""
        print(f"  {cfg:20s} ({m['input_dim']:3d}d): "
              f"F1={m['macro_f1']:.4f}, Acc={m['full_accuracy']:.4f}{marker}")
    print(f"\nBaseline TIR: {tir_baseline:.4f}")
    print(f"Best: {best_cfg} (Macro-F1={best_f1:.4f})")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp305_multiscale_override.json'))
    return results


def run_indirect_drift_detection(args):
    """EXP-306: Indirect ISF drift detection via pattern comparison.

    Hypothesis: If similar meal/bolus patterns produce different glucose outcomes
    at different time periods, the difference IS the drift signal.

    Method:
    1. Use weekly encoder (best clustering, Sil=+0.326) to embed all 7d windows
    2. For each window, measure glucose "outcome" (mean, peak, nadir, TIR)
    3. Find top-K similar windows by cosine similarity
    4. Compare outcomes of matched windows across time:
       - Same outcome → stable sensitivity
       - Higher glucose response → increasing resistance (ISF drift up)
       - Lower glucose response → increasing sensitivity (ISF drift down)
    5. Build drift trajectory per patient over time
    6. Validate: correlate detected drift with known indicators
       (dawn phenomenon, illness, exercise patterns)
    """
    from .pattern_embedding import PatternEncoder, retrieval_recall_at_k
    from sklearn.metrics.pairwise import cosine_similarity

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device

    print("=" * 60)
    print("EXP-306: Indirect ISF Drift Detection")
    print("=" * 60)

    # Load weekly-scale data (best for pattern matching)
    train_w, val_w = load_multiscale_data(patient_paths, scale='weekly')
    all_windows = np.concatenate([train_w, val_w], axis=0)
    n_total = len(all_windows)
    print(f"\nTotal weekly windows: {n_total}")

    # Load pretrained weekly encoder from EXP-304
    ckpt_path = os.path.join(output_dir, 'cross_scale_encoder.pth')
    encoder = PatternEncoder(input_dim=8, d_model=64, nhead=4,
                             num_layers=2, embed_dim=32)
    if os.path.exists(ckpt_path):
        ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        # Extract weekly encoder weights from cross-scale checkpoint
        weekly_state = {}
        prefix = 'encoders.weekly.'
        for k, v in ckpt['model_state'].items():
            if k.startswith(prefix):
                weekly_state[k[len(prefix):]] = v
        if weekly_state:
            encoder.load_state_dict(weekly_state)
            print("Loaded pretrained weekly encoder from cross-scale checkpoint")
        else:
            print("No weekly encoder in checkpoint — using random initialization")
    else:
        print("No checkpoint found — training weekly encoder from scratch")
        from .pattern_embedding import build_triplets, TripletPatternLoss
        train_labels = build_episode_labels_batch(train_w)
        val_labels = build_episode_labels_batch(val_w)
        encoder, _ = train_pattern_encoder(
            encoder, train_w, train_labels, val_w, val_labels,
            epochs=args.epochs, batch_size=32, lr=1e-3, device=device,
        )

    # Generate embeddings for all windows
    encoder = encoder.to(device).eval()
    all_embs = []
    with torch.no_grad():
        for start in range(0, n_total, 512):
            end = min(start + 512, n_total)
            batch = torch.from_numpy(all_windows[start:end]).float().to(device)
            emb = encoder(batch)
            all_embs.append(emb.cpu().numpy())
    embeddings = np.concatenate(all_embs)  # (N, 32)
    print(f"Embeddings shape: {embeddings.shape}")

    # Extract glucose outcome metrics for each window
    # Channel 0 = glucose (normalized by /400)
    glucose_traces = all_windows[:, :, 0] * 400.0  # (N, 168) denormalized

    outcomes = {
        'mean_glucose': glucose_traces.mean(axis=1),
        'peak_glucose': np.nanmax(glucose_traces, axis=1),
        'nadir_glucose': np.nanmin(glucose_traces, axis=1),
        'glucose_range': np.nanmax(glucose_traces, axis=1) - np.nanmin(glucose_traces, axis=1),
        'tir': ((glucose_traces >= 70) & (glucose_traces <= 180)).mean(axis=1),
        'time_above_180': (glucose_traces > 180).mean(axis=1),
        'time_below_70': (glucose_traces < 70).mean(axis=1),
    }

    # Compute pairwise cosine similarity (sample if too large)
    max_pairs = 5000
    if n_total > max_pairs:
        sample_idx = np.random.choice(n_total, max_pairs, replace=False)
        sample_idx.sort()
    else:
        sample_idx = np.arange(n_total)

    sample_embs = embeddings[sample_idx]
    sim_matrix = cosine_similarity(sample_embs)  # (S, S)
    np.fill_diagonal(sim_matrix, -1)  # exclude self-matches
    print(f"Similarity matrix: {sim_matrix.shape}")

    # For each window, find top-K similar windows and compute outcome deltas
    K = 10
    drift_signals = []

    for i in range(len(sample_idx)):
        # Find K most similar windows
        top_k = np.argsort(sim_matrix[i])[-K:]
        sims = sim_matrix[i, top_k]

        if sims.mean() < 0.5:
            continue  # skip if no good matches

        idx_i = sample_idx[i]
        matched_indices = sample_idx[top_k]

        # Compute outcome delta: this window vs matched windows
        for metric_name in ['mean_glucose', 'tir', 'glucose_range']:
            my_val = outcomes[metric_name][idx_i]
            matched_vals = outcomes[metric_name][matched_indices]
            delta = my_val - matched_vals.mean()
            drift_signals.append({
                'window_idx': int(idx_i),
                'metric': metric_name,
                'my_value': float(my_val),
                'matched_mean': float(matched_vals.mean()),
                'matched_std': float(matched_vals.std()),
                'delta': float(delta),
                'mean_similarity': float(sims.mean()),
                'n_matched': int(len(matched_indices)),
            })

    drift_df = {}
    for metric in ['mean_glucose', 'tir', 'glucose_range']:
        signals = [s for s in drift_signals if s['metric'] == metric]
        if signals:
            deltas = [s['delta'] for s in signals]
            drift_df[metric] = {
                'n_comparisons': len(signals),
                'mean_delta': float(np.mean(deltas)),
                'std_delta': float(np.std(deltas)),
                'median_delta': float(np.median(deltas)),
                'pct_positive': float(np.mean(np.array(deltas) > 0)),
                'pct_significant': float(np.mean(np.abs(deltas) > np.std(deltas))),
            }

    # Temporal ordering: check if drift deltas correlate with window position
    # (window index is a proxy for time)
    glucose_signals = [s for s in drift_signals if s['metric'] == 'mean_glucose']
    if glucose_signals:
        idx_arr = np.array([s['window_idx'] for s in glucose_signals])
        delta_arr = np.array([s['delta'] for s in glucose_signals])
        # Split into early (first half) vs late (second half) windows
        median_idx = np.median(idx_arr)
        early = delta_arr[idx_arr < median_idx]
        late = delta_arr[idx_arr >= median_idx]
        temporal_shift = float(late.mean() - early.mean()) if len(early) > 0 and len(late) > 0 else 0.0
        temporal_corr = float(np.corrcoef(idx_arr, delta_arr)[0, 1]) if len(idx_arr) > 2 else 0.0
    else:
        temporal_shift = 0.0
        temporal_corr = 0.0

    results = {
        'experiment': 'EXP-306',
        'name': 'indirect-isf-drift-detection',
        'method': 'pattern-similarity outcome comparison',
        'scale': 'weekly (7d @ 1hr)',
        'n_windows': n_total,
        'n_sampled': len(sample_idx),
        'k_neighbors': K,
        'n_drift_signals': len(drift_signals),
        'drift_metrics': drift_df,
        'temporal_analysis': {
            'early_vs_late_glucose_shift': temporal_shift,
            'temporal_correlation': temporal_corr,
            'interpretation': (
                'positive shift = later windows show higher glucose for same patterns '
                '(increasing resistance); negative = increasing sensitivity'
            ),
        },
        'embedding_dim': 32,
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Indirect ISF Drift Detection Results")
    print(f"{'='*60}")
    for metric, stats in drift_df.items():
        print(f"\n{metric}:")
        print(f"  n_comparisons: {stats['n_comparisons']}")
        print(f"  mean_delta: {stats['mean_delta']:.2f} "
              f"(std={stats['std_delta']:.2f})")
        print(f"  % positive delta: {stats['pct_positive']:.1%}")
        print(f"  % significant: {stats['pct_significant']:.1%}")
    print(f"\nTemporal analysis:")
    print(f"  Early→Late glucose shift: {temporal_shift:+.2f} mg/dL")
    print(f"  Temporal correlation: {temporal_corr:+.4f}")
    print(f"  (positive = increasing resistance over time)")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp306_indirect_drift.json'))
    return results


def run_per_patient_drift(args):
    """EXP-307: Per-patient temporal ISF drift detection.

    Fixes EXP-306's critical flaws:
    1. Analyze each patient INDEPENDENTLY (drift is per-patient)
    2. Preserve temporal order (sequential windows, no shuffle)
    3. Match early-period patterns to late-period patterns within same patient
    4. Only compare high-similarity matches (cosine > threshold)

    For each patient:
    - Split their 7d windows into temporal thirds: early / mid / late
    - Embed all windows with pretrained weekly encoder
    - For each late-period window, find K nearest matches from early period
    - Compare glucose outcomes: delta = late_outcome - early_outcome
    - If delta > 0 consistently → ISF drift (increasing resistance)
    """
    from .pattern_embedding import PatternEncoder
    from sklearn.metrics.pairwise import cosine_similarity
    from .real_data_adapter import downsample_grid

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device

    print("=" * 60)
    print("EXP-307: Per-Patient Temporal ISF Drift Detection")
    print("=" * 60)

    # Load pretrained weekly encoder
    encoder = PatternEncoder(input_dim=8, d_model=64, nhead=4,
                             num_layers=2, embed_dim=32)
    ckpt_path = os.path.join(output_dir, 'cross_scale_encoder.pth')
    if os.path.exists(ckpt_path):
        ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        weekly_state = {}
        prefix = 'encoders.weekly.'
        for k, v in ckpt['model_state'].items():
            if k.startswith(prefix):
                weekly_state[k[len(prefix):]] = v
        if weekly_state:
            encoder.load_state_dict(weekly_state)
            print("Loaded pretrained weekly encoder")
    encoder = encoder.to(device).eval()

    # Process each patient independently with TEMPORAL ORDER preserved
    per_patient_results = {}
    K = 5
    SIM_THRESHOLD = 0.7

    for pi, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"\n--- Patient {patient_id} ({pi+1}/{len(patient_paths)}) ---")

        df, features_5min = _get_cached_grid(path)
        if df is None:
            print("  SKIP: no data")
            continue

        # Downsample to 1-hr for weekly windows
        df_1h = downsample_grid(df, target_interval_min=60)
        features = _grid_to_features(df_1h)

        # Build SEQUENTIAL windows (stride=24 = 1 day, preserving temporal order)
        window = 168  # 7 days
        stride = 24   # 1-day advance
        windows = []
        for start in range(0, len(features) - window + 1, stride):
            w = features[start:start + window]
            if np.isnan(w[:, 0]).mean() < 0.3:  # <30% NaN in glucose
                w = np.nan_to_num(w, nan=0.0)
                windows.append(w)
        windows = np.array(windows, dtype=np.float32) if windows else None

        if windows is None or len(windows) < 6:
            print(f"  SKIP: only {0 if windows is None else len(windows)} windows")
            continue

        n = len(windows)
        third = n // 3
        early = windows[:third]      # first temporal third
        late = windows[-third:]       # last temporal third
        print(f"  {n} sequential windows (stride=1d), early={len(early)}, late={len(late)}")

        # Embed all windows
        def embed(arr):
            embs = []
            with torch.no_grad():
                for s in range(0, len(arr), 256):
                    e = min(s + 256, len(arr))
                    batch = torch.from_numpy(arr[s:e]).float().to(device)
                    embs.append(encoder(batch).cpu().numpy())
            return np.concatenate(embs)

        early_emb = embed(early)  # (E, 32)
        late_emb = embed(late)    # (L, 32)

        # For each late window, find K best matches from early period
        sim = cosine_similarity(late_emb, early_emb)  # (L, E)

        glucose_deltas = []
        tir_deltas = []
        range_deltas = []
        match_sims = []

        for i in range(len(late)):
            # Get top-K matches above threshold
            sims = sim[i]
            top_k_idx = np.argsort(sims)[-K:]
            top_k_sims = sims[top_k_idx]
            good = top_k_sims >= SIM_THRESHOLD
            if good.sum() < 2:
                continue  # need at least 2 good matches

            matched_idx = top_k_idx[good]
            matched_sims = top_k_sims[good]

            # Glucose outcomes
            late_gluc = late[i, :, 0] * 400.0
            early_gluc = np.array([early[j, :, 0] * 400.0 for j in matched_idx])

            # Outcome metrics
            late_mean = np.nanmean(late_gluc)
            early_mean = np.nanmean(early_gluc)
            glucose_deltas.append(late_mean - early_mean)

            late_tir = ((late_gluc >= 70) & (late_gluc <= 180)).mean()
            early_tir = np.array([((eg >= 70) & (eg <= 180)).mean()
                                  for eg in early_gluc]).mean()
            tir_deltas.append(late_tir - early_tir)

            late_range = np.nanmax(late_gluc) - np.nanmin(late_gluc)
            early_range = np.mean([np.nanmax(eg) - np.nanmin(eg) for eg in early_gluc])
            range_deltas.append(late_range - early_range)

            match_sims.append(float(matched_sims.mean()))

        if len(glucose_deltas) < 3:
            print(f"  SKIP: only {len(glucose_deltas)} high-quality matches")
            continue

        glucose_deltas = np.array(glucose_deltas)
        tir_deltas = np.array(tir_deltas)
        range_deltas = np.array(range_deltas)

        # Statistical test: is the mean delta significantly different from 0?
        from scipy import stats as scipy_stats
        t_stat, p_value = scipy_stats.ttest_1samp(glucose_deltas, 0)

        per_patient_results[patient_id] = {
            'n_windows': n,
            'n_comparisons': len(glucose_deltas),
            'mean_sim': float(np.mean(match_sims)),
            'glucose_delta': {
                'mean': float(glucose_deltas.mean()),
                'std': float(glucose_deltas.std()),
                'median': float(np.median(glucose_deltas)),
                'pct_positive': float((glucose_deltas > 0).mean()),
                't_statistic': float(t_stat),
                'p_value': float(p_value),
            },
            'tir_delta': {
                'mean': float(tir_deltas.mean()),
                'std': float(tir_deltas.std()),
            },
            'range_delta': {
                'mean': float(range_deltas.mean()),
                'std': float(range_deltas.std()),
            },
        }

        direction = "↑ resistance" if glucose_deltas.mean() > 0 else "↓ sensitivity"
        sig = "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
        print(f"  Glucose Δ: {glucose_deltas.mean():+.1f} mg/dL "
              f"(p={p_value:.4f}{sig}) → {direction}")
        print(f"  TIR Δ: {tir_deltas.mean():+.3f}, Range Δ: {range_deltas.mean():+.1f}")
        print(f"  Mean match similarity: {np.mean(match_sims):.3f}")

    # Aggregate across patients
    patients_with_drift = []
    for pid, pr in per_patient_results.items():
        if pr['glucose_delta']['p_value'] < 0.05:
            patients_with_drift.append(pid)

    results = {
        'experiment': 'EXP-307',
        'name': 'per-patient-temporal-drift',
        'method': 'early-vs-late pattern matching within patient',
        'scale': 'weekly (7d @ 1hr)',
        'k_neighbors': K,
        'similarity_threshold': SIM_THRESHOLD,
        'stride_days': 1,
        'per_patient': per_patient_results,
        'summary': {
            'n_patients_analyzed': len(per_patient_results),
            'n_patients_significant_drift': len(patients_with_drift),
            'patients_with_drift': patients_with_drift,
            'mean_glucose_delta_all': float(np.mean([
                pr['glucose_delta']['mean'] for pr in per_patient_results.values()
            ])) if per_patient_results else 0.0,
        },
        'device': device,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Per-Patient ISF Drift Summary")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'N':>5} {'ΔGluc':>8} {'p-val':>8} {'ΔTIR':>7} {'Drift':>12}")
    print("-" * 55)
    for pid in sorted(per_patient_results.keys()):
        pr = per_patient_results[pid]
        g = pr['glucose_delta']
        sig = "**" if g['p_value'] < 0.01 else "*" if g['p_value'] < 0.05 else ""
        direction = "resistance↑" if g['mean'] > 0 else "sensitivity↑"
        print(f"{pid:>8} {pr['n_comparisons']:>5} {g['mean']:>+7.1f} "
              f"{g['p_value']:>7.4f}{sig} {pr['tir_delta']['mean']:>+6.3f} "
              f"{direction:>12}")
    print(f"\nSignificant drift (p<0.05): {len(patients_with_drift)}/{len(per_patient_results)} patients")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp307_per_patient_drift.json'))
    return results


def run_insulin_controlled_drift(args):
    """EXP-308: Insulin-controlled ISF drift detection.

    Addresses EXP-307's caveat: match sim≈1.0 means embedding matching
    wasn't discriminative. Instead, match windows by TREATMENT CONTEXT
    (insulin delivery + carb intake) directly from the data channels.

    If similar treatment contexts produce different glucose outcomes at
    different times → that's true ISF drift (not just behavior change).

    Treatment context (from channels 1-5):
    - Mean IOB (ch1), Mean COB (ch2), Mean basal (ch3)
    - Total bolus (ch4), Total carbs (ch5)
    - These are normalized, so we match on normalized values directly.

    Uses 12h episode windows (captures complete DIA cycle, best for
    insulin response analysis) with non-overlapping stride.
    """
    from sklearn.metrics.pairwise import cosine_similarity
    from scipy import stats as scipy_stats
    from .real_data_adapter import downsample_grid

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir

    print("=" * 60)
    print("EXP-308: Insulin-Controlled ISF Drift Detection")
    print("=" * 60)

    # Use episode scale (12h @ 5min) — captures full DIA cycle
    # Non-overlapping stride to ensure statistical independence
    window = 144  # 12h at 5-min
    stride = 144  # NON-OVERLAPPING

    per_patient_results = {}
    K = 5
    TREATMENT_SIM_THRESHOLD = 0.85

    for pi, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"\n--- Patient {patient_id} ({pi+1}/{len(patient_paths)}) ---")

        df, features_5min = _get_cached_grid(path)
        if df is None:
            print("  SKIP: no data")
            continue

        # Build NON-OVERLAPPING 12h windows preserving temporal order
        windows = []
        for start in range(0, len(features_5min) - window + 1, stride):
            w = features_5min[start:start + window]
            # Require <20% NaN in glucose
            if np.isnan(w[:, 0]).mean() < 0.2:
                w = np.nan_to_num(w, nan=0.0)
                windows.append(w)

        if len(windows) < 10:
            print(f"  SKIP: only {len(windows)} non-overlapping 12h windows")
            continue

        windows = np.array(windows, dtype=np.float32)  # (N, 144, 8)
        n = len(windows)

        # Extract treatment context: summary of insulin/carb channels per window
        # Channels: 0=glucose, 1=IOB, 2=COB, 3=basal, 4=bolus, 5=carbs, 6=tsin, 7=tcos
        treatment_ctx = np.column_stack([
            windows[:, :, 1].mean(axis=1),  # mean IOB
            windows[:, :, 2].mean(axis=1),  # mean COB
            windows[:, :, 3].mean(axis=1),  # mean basal
            windows[:, :, 4].sum(axis=1),   # total bolus (sum, not mean)
            windows[:, :, 5].sum(axis=1),   # total carbs (sum, not mean)
        ])  # (N, 5) treatment context vector

        # Normalize treatment context for cosine similarity
        norms = np.linalg.norm(treatment_ctx, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        treatment_ctx_norm = treatment_ctx / norms

        # Split into temporal thirds
        third = n // 3
        early_idx = np.arange(third)
        late_idx = np.arange(n - third, n)

        early_ctx = treatment_ctx_norm[early_idx]
        late_ctx = treatment_ctx_norm[late_idx]

        # Match late windows to early windows by treatment similarity
        sim = cosine_similarity(late_ctx, early_ctx)  # (L, E)

        glucose_deltas = []
        tir_deltas = []
        match_sims = []
        insulin_deltas = []

        for i in range(len(late_idx)):
            sims = sim[i]
            top_k = np.argsort(sims)[-K:]
            top_k_sims = sims[top_k]
            good = top_k_sims >= TREATMENT_SIM_THRESHOLD

            if good.sum() < 2:
                continue

            matched_early = early_idx[top_k[good]]
            matched_sims_arr = top_k_sims[good]
            li = late_idx[i]

            # Glucose outcomes (channel 0, denormalized)
            late_gluc = windows[li, :, 0] * 400.0
            early_gluc = np.array([windows[j, :, 0] * 400.0 for j in matched_early])

            # Insulin delivery (channel 4, denormalized)
            late_insulin = windows[li, :, 4].sum() * 10.0  # bolus units
            early_insulin = np.mean([windows[j, :, 4].sum() * 10.0
                                     for j in matched_early])

            glucose_deltas.append(float(np.nanmean(late_gluc) - np.nanmean(early_gluc)))
            insulin_deltas.append(float(late_insulin - early_insulin))

            late_tir = ((late_gluc >= 70) & (late_gluc <= 180)).mean()
            early_tir = np.mean([((windows[j, :, 0] * 400.0 >= 70) &
                                   (windows[j, :, 0] * 400.0 <= 180)).mean()
                                  for j in matched_early])
            tir_deltas.append(float(late_tir - early_tir))
            match_sims.append(float(matched_sims_arr.mean()))

        if len(glucose_deltas) < 3:
            print(f"  SKIP: only {len(glucose_deltas)} treatment-matched pairs")
            continue

        glucose_deltas = np.array(glucose_deltas)
        tir_deltas = np.array(tir_deltas)
        insulin_deltas = np.array(insulin_deltas)

        t_stat, p_value = scipy_stats.ttest_1samp(glucose_deltas, 0)

        # Also test if insulin delivery changed (confounder check)
        t_ins, p_ins = scipy_stats.ttest_1samp(insulin_deltas, 0)

        per_patient_results[patient_id] = {
            'n_windows': n,
            'n_non_overlapping': n,
            'n_comparisons': len(glucose_deltas),
            'mean_treatment_sim': float(np.mean(match_sims)),
            'glucose_delta': {
                'mean': float(glucose_deltas.mean()),
                'std': float(glucose_deltas.std()),
                'median': float(np.median(glucose_deltas)),
                'pct_positive': float((glucose_deltas > 0).mean()),
                't_statistic': float(t_stat),
                'p_value': float(p_value),
            },
            'insulin_delta': {
                'mean': float(insulin_deltas.mean()),
                'p_value': float(p_ins),
                'note': 'should be ~0 if treatment matching worked',
            },
            'tir_delta': {
                'mean': float(tir_deltas.mean()),
                'std': float(tir_deltas.std()),
            },
        }

        direction = "↑ resistance" if glucose_deltas.mean() > 0 else "↓ sensitivity"
        sig = "**" if p_value < 0.01 else "*" if p_value < 0.05 else ""
        ins_note = f" (ΔInsulin={insulin_deltas.mean():+.2f}U, p={p_ins:.3f})" if p_ins < 0.05 else ""
        print(f"  {n} non-overlapping 12h windows, {len(glucose_deltas)} matched pairs")
        print(f"  Glucose Δ: {glucose_deltas.mean():+.1f} mg/dL "
              f"(p={p_value:.4f}{sig}) → {direction}")
        print(f"  Mean treatment sim: {np.mean(match_sims):.3f}{ins_note}")

    # Summary
    patients_with_drift = [pid for pid, pr in per_patient_results.items()
                           if pr['glucose_delta']['p_value'] < 0.05]
    # Patients where insulin changed significantly (confounded)
    confounded = [pid for pid, pr in per_patient_results.items()
                  if pr['insulin_delta']['p_value'] < 0.05]

    results = {
        'experiment': 'EXP-308',
        'name': 'insulin-controlled-drift',
        'method': 'treatment-context matching (12h non-overlapping)',
        'scale': 'episode (12h @ 5min, stride=12h)',
        'k_neighbors': K,
        'treatment_sim_threshold': TREATMENT_SIM_THRESHOLD,
        'per_patient': per_patient_results,
        'summary': {
            'n_patients_analyzed': len(per_patient_results),
            'n_significant_drift': len(patients_with_drift),
            'patients_with_drift': patients_with_drift,
            'n_confounded': len(confounded),
            'confounded_patients': confounded,
            'clean_drift': [p for p in patients_with_drift if p not in confounded],
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Insulin-Controlled Drift Summary")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'N':>5} {'ΔGluc':>8} {'p-val':>8} {'ΔIns':>7} {'TxSim':>6} {'Drift':>12}")
    print("-" * 65)
    for pid in sorted(per_patient_results.keys()):
        pr = per_patient_results[pid]
        g = pr['glucose_delta']
        sig = "**" if g['p_value'] < 0.01 else "*" if g['p_value'] < 0.05 else ""
        conf = "†" if pr['insulin_delta']['p_value'] < 0.05 else ""
        direction = "resistance↑" if g['mean'] > 0 else "sensitivity↑"
        print(f"{pid:>8} {pr['n_comparisons']:>5} {g['mean']:>+7.1f} "
              f"{g['p_value']:>7.4f}{sig} {pr['insulin_delta']['mean']:>+6.2f}{conf} "
              f"{pr['mean_treatment_sim']:>5.3f} {direction:>12}")
    clean = results['summary']['clean_drift']
    print(f"\nSignificant drift: {len(patients_with_drift)}/{len(per_patient_results)}")
    print(f"Confounded (insulin also changed): {len(confounded)}")
    print(f"Clean drift (glucose changed, insulin didn't): {len(clean)} → {clean}")
    print(f"† = insulin delivery also changed significantly (p<0.05)")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp308_insulin_drift.json'))
    return results


# ── EXP-309: ISF Response Ratio Tracking ──────────────────────────────

def run_isf_response_ratio(args):
    """EXP-309: Direct ISF measurement via glucose/insulin response ratio.

    Instead of embedding-based drift detection (EXP-306/307 had caveats),
    directly measure effective insulin sensitivity by computing the
    glucose response per unit insulin over complete DIA cycles.

    Method:
    1. Identify bolus events (ch4 sum > threshold in a 6h window)
    2. For each bolus window, compute:
       - glucose_delta = end_glucose - start_glucose (should be negative)
       - insulin_total = total bolus + basal over window
       - ISF_effective = glucose_delta / insulin_total (mg/dL per unit)
    3. Track ISF_effective over time within each patient
    4. Test for temporal trend (Spearman correlation + OLS slope)

    If ISF_effective trends toward 0 → developing resistance.
    If ISF_effective trends more negative → improving sensitivity.

    Uses 6h (72-step @ 5min) windows — one complete DIA cycle.
    Non-overlapping stride ensures independence.
    """
    from scipy import stats as scipy_stats

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir

    print("=" * 60)
    print("EXP-309: ISF Response Ratio Tracking")
    print("=" * 60)

    window = 72   # 6h at 5-min = 1 DIA cycle
    stride = 72   # non-overlapping
    BOLUS_THRESHOLD = 0.01  # normalized threshold for bolus presence (ch4)
    MIN_INSULIN = 0.5       # minimum total insulin (denorm units) to qualify

    per_patient_results = {}

    for pi, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"\n--- Patient {patient_id} ({pi+1}/{len(patient_paths)}) ---")

        df, features_5min = _get_cached_grid(path)
        if df is None:
            print("  SKIP: no data")
            continue

        # Build non-overlapping 6h windows
        windows = []
        window_times = []  # track temporal order
        for start in range(0, len(features_5min) - window + 1, stride):
            w = features_5min[start:start + window]
            # Require <20% NaN in glucose
            if np.isnan(w[:, 0]).mean() < 0.2:
                w_clean = np.nan_to_num(w, nan=0.0)
                windows.append(w_clean)
                window_times.append(start)  # temporal index

        if len(windows) < 10:
            print(f"  SKIP: only {len(windows)} windows")
            continue

        windows = np.array(windows, dtype=np.float32)  # (N, 72, 8)
        n = len(windows)

        # Identify bolus windows (ch4 = bolus, normalized)
        bolus_sums = windows[:, :, 4].sum(axis=1)  # total normalized bolus
        basal_means = windows[:, :, 3].mean(axis=1)  # mean normalized basal

        # Denormalize: bolus channel normalized by /10.0 in encoder
        # basal channel normalized by mean subtraction in encoder
        bolus_units = bolus_sums * 10.0  # approx total bolus units
        basal_total = basal_means * 10.0 * (window * 5 / 60)  # basal rate * hours
        total_insulin = bolus_units + basal_total

        # Glucose response: end - start (denormalized)
        glucose_start = windows[:, :12, 0].mean(axis=1) * 400.0  # first hour mean
        glucose_end = windows[:, -12:, 0].mean(axis=1) * 400.0    # last hour mean
        glucose_delta = glucose_end - glucose_start

        # Filter: only windows with meaningful insulin delivery
        mask = total_insulin >= MIN_INSULIN
        if mask.sum() < 10:
            print(f"  SKIP: only {mask.sum()} windows with insulin >= {MIN_INSULIN}U")
            continue

        # Compute ISF_effective = glucose_delta / total_insulin
        isf_eff = glucose_delta[mask] / total_insulin[mask]  # mg/dL per unit
        times = np.array(window_times)[mask]

        # Normalize times to [0, 1] for correlation
        if len(times) < 5:
            continue
        times_norm = (times - times.min()) / max(1, times.max() - times.min())

        # Spearman correlation: is ISF_effective trending over time?
        rho, p_spearman = scipy_stats.spearmanr(times_norm, isf_eff)

        # OLS slope in mg/dL per unit per normalized time
        slope, intercept = np.polyfit(times_norm, isf_eff, 1)

        # Also compute early vs late ISF to compare with EXP-308
        n_qualified = mask.sum()
        third = n_qualified // 3
        early_isf = isf_eff[:third]
        late_isf = isf_eff[-third:]
        t_stat, p_ttest = scipy_stats.ttest_ind(early_isf, late_isf)

        # Bolus-only analysis (exclude low-bolus windows)
        bolus_mask = mask & (bolus_units >= 0.5)
        if bolus_mask.sum() >= 10:
            bolus_isf = glucose_delta[bolus_mask] / total_insulin[bolus_mask]
            bolus_times = np.array(window_times)[bolus_mask]
            bolus_times_n = (bolus_times - bolus_times.min()) / max(1, bolus_times.max() - bolus_times.min())
            rho_bolus, p_bolus = scipy_stats.spearmanr(bolus_times_n, bolus_isf)
            bolus_slope, _ = np.polyfit(bolus_times_n, bolus_isf, 1)
        else:
            rho_bolus, p_bolus, bolus_slope = float('nan'), float('nan'), float('nan')

        per_patient_results[patient_id] = {
            'n_total_windows': n,
            'n_qualified': int(n_qualified),
            'n_bolus_windows': int(bolus_mask.sum()) if bolus_mask.sum() >= 10 else 0,
            'isf_effective': {
                'mean': float(isf_eff.mean()),
                'std': float(isf_eff.std()),
                'median': float(np.median(isf_eff)),
            },
            'temporal_trend': {
                'spearman_rho': float(rho),
                'spearman_p': float(p_spearman),
                'ols_slope': float(slope),
                'intercept': float(intercept),
            },
            'early_vs_late': {
                'early_mean': float(early_isf.mean()),
                'late_mean': float(late_isf.mean()),
                'delta': float(late_isf.mean() - early_isf.mean()),
                't_stat': float(t_stat),
                'p_value': float(p_ttest),
            },
            'bolus_only': {
                'spearman_rho': float(rho_bolus),
                'spearman_p': float(p_bolus),
                'ols_slope': float(bolus_slope),
            },
        }

        sig = "**" if p_spearman < 0.01 else "*" if p_spearman < 0.05 else ""
        direction = "→ resistance↑" if slope > 0 else "→ sensitivity↑"
        print(f"  {n_qualified} qualified windows (insulin≥{MIN_INSULIN}U)")
        print(f"  ISF_eff: mean={isf_eff.mean():+.1f} mg/dL/U (std={isf_eff.std():.1f})")
        print(f"  Trend: ρ={rho:+.3f} (p={p_spearman:.4f}{sig}), slope={slope:+.2f} {direction}")
        print(f"  Early→Late: {early_isf.mean():+.1f} → {late_isf.mean():+.1f} (Δ={late_isf.mean()-early_isf.mean():+.1f}, p={p_ttest:.4f})")

    # Summary
    trending = [pid for pid, pr in per_patient_results.items()
                if pr['temporal_trend']['spearman_p'] < 0.05]
    trending_resistance = [pid for pid in trending
                           if per_patient_results[pid]['temporal_trend']['ols_slope'] > 0]
    trending_sensitivity = [pid for pid in trending
                            if per_patient_results[pid]['temporal_trend']['ols_slope'] < 0]

    results = {
        'experiment': 'EXP-309',
        'name': 'isf-response-ratio',
        'method': 'glucose_delta/insulin_total per 6h DIA cycle (non-overlapping)',
        'window': f'{window*5/60:.0f}h @ 5min (stride={stride*5/60:.0f}h)',
        'min_insulin_threshold': MIN_INSULIN,
        'per_patient': per_patient_results,
        'summary': {
            'n_patients': len(per_patient_results),
            'n_significant_trend': len(trending),
            'patients_trending': trending,
            'trending_resistance': trending_resistance,
            'trending_sensitivity': trending_sensitivity,
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"ISF Response Ratio Summary")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'N':>5} {'ISF_eff':>8} {'ρ':>7} {'p':>8} {'Slope':>7} {'E→L Δ':>7} {'Trend':>14}")
    print("-" * 72)
    for pid in sorted(per_patient_results.keys()):
        pr = per_patient_results[pid]
        t = pr['temporal_trend']
        el = pr['early_vs_late']
        sig = "**" if t['spearman_p'] < 0.01 else "*" if t['spearman_p'] < 0.05 else ""
        direction = "resistance↑" if t['ols_slope'] > 0 else "sensitivity↑"
        print(f"{pid:>8} {pr['n_qualified']:>5} {pr['isf_effective']['mean']:>+7.1f} "
              f"{t['spearman_rho']:>+6.3f} {t['spearman_p']:>7.4f}{sig} "
              f"{t['ols_slope']:>+6.2f} {el['delta']:>+6.1f} {direction:>14}")
    print(f"\nSignificant trend: {len(trending)}/{len(per_patient_results)}")
    print(f"  Resistance↑: {len(trending_resistance)} → {trending_resistance}")
    print(f"  Sensitivity↑: {len(trending_sensitivity)} → {trending_sensitivity}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp309_isf_response_ratio.json'))
    return results


# ── EXP-310: Leave-Patient-Out Retrieval ──────────────────────────────

def run_leave_patient_out_retrieval(args):
    """EXP-310: Leave-one-patient-out weekly retrieval evaluation.

    Tests whether weekly pattern embeddings generalize across patients.
    For each patient:
    1. Train weekly encoder on all OTHER patients
    2. Embed held-out patient's windows
    3. Evaluate R@5, R@1, and Silhouette on held-out patient

    If metrics hold → encoder learns universal CGM patterns.
    If metrics collapse → encoder overfits to patient-specific fingerprints.

    Uses weekly scale (168h @ 1hr) — proven best for retrieval (EXP-301/304).
    """
    from .pattern_embedding import PatternEncoder, retrieval_recall_at_k
    from sklearn.metrics import silhouette_score

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-310: Leave-Patient-Out Weekly Retrieval")
    print("=" * 60)

    # Load weekly-scale data PER PATIENT (need patient identity)
    per_patient_data = {}
    for path in patient_paths:
        patient_id = os.path.basename(os.path.dirname(path))
        df, features_5min = _get_cached_grid(path)
        if df is None:
            continue

        from .real_data_adapter import downsample_grid
        df_1h = downsample_grid(df, target_interval_min=60)
        feat_1h = _grid_to_features(df_1h)

        window = 168  # 7 days
        stride = 24   # 1-day stride for sufficient windows
        windows = []
        for start in range(0, len(feat_1h) - window + 1, stride):
            w = feat_1h[start:start + window]
            if np.isnan(w[:, 0]).mean() < 0.2:
                for col in range(w.shape[1]):
                    mask = np.isnan(w[:, col])
                    if mask.any():
                        v = ~mask
                        if v.sum() >= 2:
                            w[mask, col] = np.interp(
                                np.where(mask)[0], np.where(v)[0], w[v, col])
                        else:
                            w[mask, col] = 0.0
                windows.append(w)

        if len(windows) >= 5:
            per_patient_data[patient_id] = np.array(windows, dtype=np.float32)
            print(f"  Patient {patient_id}: {len(windows)} weekly windows")
        else:
            print(f"  Patient {patient_id}: SKIP ({len(windows)} windows)")

    patient_ids = sorted(per_patient_data.keys())
    if len(patient_ids) < 3:
        print("ERROR: Need at least 3 patients")
        return {'experiment': 'EXP-310', 'error': 'insufficient patients'}

    print(f"\n{len(patient_ids)} patients available for LOO evaluation\n")

    per_patient_results = {}

    for held_out in patient_ids:
        print(f"--- Holding out patient {held_out} ---")

        # Combine all OTHER patients for training
        train_windows = []
        train_labels_all = []
        for pid in patient_ids:
            if pid == held_out:
                continue
            w = per_patient_data[pid]
            train_windows.append(w)
            labels = build_episode_labels_batch(w)
            train_labels_all.extend(labels)

        train_np = np.concatenate(train_windows, axis=0)

        # Held-out patient as validation
        val_np = per_patient_data[held_out]
        val_labels = build_episode_labels_batch(val_np)
        flat_val_labels = [l[0] if isinstance(l, list) else l for l in val_labels]

        if len(set(flat_val_labels)) < 2:
            print(f"  SKIP: only 1 label type in held-out patient")
            per_patient_results[held_out] = {'error': 'single_label'}
            continue

        # Train encoder
        enc = PatternEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2,
                             embed_dim=32)
        enc, hist = train_pattern_encoder(
            enc, train_np, train_labels_all,
            val_np, val_labels,
            epochs=epochs, batch_size=32, lr=1e-3, device=device,
        )

        # Embed held-out patient
        enc = enc.to(device).eval()
        all_embs = []
        with torch.no_grad():
            for start in range(0, len(val_np), 512):
                end = min(start + 512, len(val_np))
                batch = torch.from_numpy(val_np[start:end]).float().to(device)
                emb = enc(batch)
                all_embs.append(emb.cpu().numpy())
        embeddings = np.concatenate(all_embs)

        # Evaluate
        r5 = retrieval_recall_at_k(embeddings, flat_val_labels, k=5)
        r1 = retrieval_recall_at_k(embeddings, flat_val_labels, k=1)

        unique_labels = list(set(flat_val_labels))
        label_ints = [unique_labels.index(l) for l in flat_val_labels]
        try:
            sil = silhouette_score(embeddings, label_ints, metric='cosine',
                                   sample_size=min(2000, len(label_ints)))
        except ValueError:
            sil = float('nan')

        per_patient_results[held_out] = {
            'n_train': len(train_np),
            'n_val': len(val_np),
            'n_labels': len(unique_labels),
            'recall_at_5': float(r5),
            'recall_at_1': float(r1),
            'silhouette': float(sil),
            'train_loss_final': float(hist.get('train_loss', [float('nan')])[-1])
                if 'train_loss' in hist and hist['train_loss'] else float('nan'),
        }
        print(f"  R@5={r5:.4f}, R@1={r1:.4f}, Sil={sil:.4f} "
              f"(trained on {len(train_np)} windows from {len(patient_ids)-1} patients)")

    # Summary
    valid = {k: v for k, v in per_patient_results.items() if 'error' not in v}
    if valid:
        mean_r5 = np.mean([v['recall_at_5'] for v in valid.values()])
        mean_r1 = np.mean([v['recall_at_1'] for v in valid.values()])
        mean_sil = np.nanmean([v['silhouette'] for v in valid.values()])
    else:
        mean_r5 = mean_r1 = mean_sil = float('nan')

    results = {
        'experiment': 'EXP-310',
        'name': 'leave-patient-out-retrieval',
        'method': 'LOO: train on N-1, eval on held-out (weekly 7d @ 1hr)',
        'scale': 'weekly (168h @ 1hr, stride=24h)',
        'per_patient': per_patient_results,
        'summary': {
            'n_patients': len(per_patient_results),
            'n_valid': len(valid),
            'mean_recall_at_5': float(mean_r5),
            'mean_recall_at_1': float(mean_r1),
            'mean_silhouette': float(mean_sil),
        },
        'comparison': {
            'within_patient_sil': -0.301,
            'note': 'EXP-301 trained/tested mixed: Sil=-0.301, R@5=0.957',
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Leave-Patient-Out Retrieval Summary")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'N_val':>6} {'R@5':>6} {'R@1':>6} {'Sil':>7}")
    print("-" * 40)
    for pid in sorted(per_patient_results.keys()):
        pr = per_patient_results[pid]
        if 'error' in pr:
            print(f"{pid:>8} {'—':>6} {'SKIP':>6}")
        else:
            print(f"{pid:>8} {pr['n_val']:>6} {pr['recall_at_5']:>5.3f} "
                  f"{pr['recall_at_1']:>5.3f} {pr['silhouette']:>+6.3f}")
    print(f"\nMean: R@5={mean_r5:.4f}, R@1={mean_r1:.4f}, Sil={mean_sil:.4f}")
    print(f"Comparison: within-patient Sil={-0.301:.3f} (EXP-301)")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp310_lpo_retrieval.json'))
    return results


# ── EXP-311: Temporal Override Model (1D-CNN) ─────────────────────────

def run_temporal_override(args):
    """EXP-311: 1D-CNN temporal model for override prediction.

    EXP-305 showed static state features predict overrides (F1=0.39)
    but embeddings barely help (ΔF1<0.001). This tests whether a
    temporal model on the raw 2h fast window can do better by
    capturing temporal dynamics that static state summaries miss.

    Compares:
    1. Baseline: MLP on 10-dim static state features (EXP-305 approach)
    2. 1D-CNN: Conv1d on raw 2h window → override prediction
    3. Combined: 1D-CNN + static state concatenated

    Uses forward-looking labels: will glucose exceed threshold in NEXT 1h?
    (Same label scheme proven in EXP-305.)
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-311: Temporal Override Model (1D-CNN)")
    print("=" * 60)

    # Load 2h fast-scale data
    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    # Build forward-looking override labels
    # Label: will glucose exceed 180 or drop below 70 in NEXT 1h (12 steps)?
    def build_forward_labels(windows):
        """Binary label: will glucose leave [70,180] range in second half of window?"""
        half = windows.shape[1] // 2
        future_glucose = windows[:, half:, 0] * 400.0  # denormalize
        high = (future_glucose > 180).any(axis=1)
        low = (future_glucose < 70).any(axis=1)
        # 0=no_override, 1=high_override, 2=low_override
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2  # low overrides high (safety priority)
        return labels

    train_labels = build_forward_labels(train_np)
    val_labels = build_forward_labels(val_np)

    print(f"Label dist (train): no={np.sum(train_labels==0)}, "
          f"high={np.sum(train_labels==1)}, low={np.sum(train_labels==2)}")
    print(f"Label dist (val): no={np.sum(val_labels==0)}, "
          f"high={np.sum(val_labels==1)}, low={np.sum(val_labels==2)}")

    # Class weights for imbalanced labels
    from collections import Counter
    counts = Counter(train_labels.tolist())
    n_total = len(train_labels)
    n_classes = 3
    class_weights = torch.tensor([
        n_total / (n_classes * max(1, counts.get(c, 1))) for c in range(n_classes)
    ], dtype=torch.float32).to(device)

    # Extract static state features (10-dim, same as EXP-305)
    def extract_state_batch(windows):
        """Extract 10-dim static state from each window's history half."""
        half = windows.shape[1] // 2
        hist = windows[:, :half]
        glucose = hist[:, :, 0] * 400.0
        states = np.column_stack([
            np.nanmean(glucose, axis=1),                    # mean glucose
            np.nanstd(glucose, axis=1),                     # glucose variability
            glucose[:, -1] - glucose[:, 0],                 # glucose trend
            (glucose[:, -1] - glucose[:, -3]) if hist.shape[1] >= 3 else np.zeros(len(hist)),  # recent ROC
            np.nanmean(hist[:, :, 1], axis=1),              # mean IOB
            np.nanmean(hist[:, :, 2], axis=1),              # mean COB
            np.nanmean(hist[:, :, 3], axis=1),              # mean basal
            hist[:, :, 4].sum(axis=1),                      # total bolus
            hist[:, :, 5].sum(axis=1),                      # total carbs
            (glucose < 70/400.0).any(axis=1).astype(float), # hypo flag
        ])
        return np.nan_to_num(states, nan=0.0).astype(np.float32)

    train_state = extract_state_batch(train_np)
    val_state = extract_state_batch(val_np)

    # ── Model Definitions ──

    class StateMLP(nn.Module):
        """Baseline: MLP on 10-dim static state."""
        def __init__(self, state_dim=10, n_classes=3):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim, 64), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.1),
                nn.Linear(32, n_classes),
            )
        def forward(self, state):
            return self.net(state)

    class TemporalCNN(nn.Module):
        """1D-CNN on raw 2h window → override prediction."""
        def __init__(self, in_channels=8, n_classes=3):
            super().__init__()
            # Only process history half (first 12 steps)
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),  # global average pool
            )
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )
        def forward(self, x):
            # x: (B, T, C) → (B, C, T) for Conv1d
            half = x.shape[1] // 2
            x = x[:, :half].permute(0, 2, 1)
            features = self.conv(x).squeeze(-1)  # (B, 64)
            return self.classifier(features)

    class CombinedModel(nn.Module):
        """1D-CNN + static state features combined."""
        def __init__(self, in_channels=8, state_dim=10, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64 + state_dim, 48), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(48, n_classes),
            )
        def forward(self, x, state):
            half = x.shape[1] // 2
            x = x[:, :half].permute(0, 2, 1)
            cnn_feat = self.conv(x).squeeze(-1)  # (B, 64)
            combined = torch.cat([cnn_feat, state], dim=1)
            return self.classifier(combined)

    # ── Training Loop ──

    def train_model(model, model_name, use_state=False, use_sequence=False):
        """Generic training loop for any model variant."""
        model = model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        train_t = torch.from_numpy(train_np).float()
        val_t = torch.from_numpy(val_np).float()
        train_s = torch.from_numpy(train_state).float()
        val_s = torch.from_numpy(val_state).float()
        train_y = torch.from_numpy(train_labels).long()
        val_y = torch.from_numpy(val_labels).long()

        batch_size = 256
        best_val_f1 = 0.0
        patience_counter = 0

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]

                if use_state and use_sequence:
                    logits = model(train_t[idx].to(device), train_s[idx].to(device))
                elif use_state:
                    logits = model(train_s[idx].to(device))
                else:
                    logits = model(train_t[idx].to(device))

                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            # Validate every 5 epochs
            if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
                model.eval()
                all_preds = []
                with torch.no_grad():
                    for vs in range(0, len(val_np), 512):
                        ve = min(vs + 512, len(val_np))
                        if use_state and use_sequence:
                            logits = model(val_t[vs:ve].to(device), val_s[vs:ve].to(device))
                        elif use_state:
                            logits = model(val_s[vs:ve].to(device))
                        else:
                            logits = model(val_t[vs:ve].to(device))
                        all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                preds = np.concatenate(all_preds)

                from sklearn.metrics import f1_score
                val_f1 = f1_score(val_labels, preds, average='macro', zero_division=0)
                if val_f1 > best_val_f1:
                    best_val_f1 = val_f1
                    patience_counter = 0
                else:
                    patience_counter += 1

                if (epoch + 1) % 10 == 0:
                    print(f"  [{model_name}] E{epoch+1}: loss={epoch_loss/n_batches:.4f}, "
                          f"val_F1={val_f1:.4f} (best={best_val_f1:.4f})")

                if patience_counter >= 4:
                    print(f"  [{model_name}] Early stop at epoch {epoch+1}")
                    break

        # Final evaluation
        model.eval()
        all_preds = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                if use_state and use_sequence:
                    logits = model(val_t[vs:ve].to(device), val_s[vs:ve].to(device))
                elif use_state:
                    logits = model(val_s[vs:ve].to(device))
                else:
                    logits = model(val_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)

        from sklearn.metrics import f1_score, precision_score, recall_score, classification_report
        f1_macro = f1_score(val_labels, preds, average='macro', zero_division=0)
        f1_per = f1_score(val_labels, preds, average=None, zero_division=0)
        precision = precision_score(val_labels, preds, average='macro', zero_division=0)
        recall = recall_score(val_labels, preds, average='macro', zero_division=0)

        report = classification_report(val_labels, preds,
                                       target_names=['no_override', 'high', 'low'],
                                       zero_division=0, output_dict=True)

        return {
            'f1_macro': float(f1_macro),
            'f1_per_class': [float(f) for f in f1_per],
            'precision_macro': float(precision),
            'recall_macro': float(recall),
            'best_val_f1': float(best_val_f1),
            'classification_report': report,
        }

    # ── Run all three models ──

    print("\n--- Model 1: StateMLP (baseline) ---")
    state_results = train_model(StateMLP(), 'StateMLP', use_state=True)

    print("\n--- Model 2: TemporalCNN (raw window) ---")
    cnn_results = train_model(TemporalCNN(), 'CNN', use_sequence=True)

    print("\n--- Model 3: Combined (CNN + state) ---")
    combined_results = train_model(CombinedModel(), 'Combined',
                                   use_state=True, use_sequence=True)

    results = {
        'experiment': 'EXP-311',
        'name': 'temporal-override-model',
        'method': '1D-CNN vs StateMLP vs Combined for override prediction',
        'labels': 'forward-looking: will glucose leave [70,180] in next 1h',
        'models': {
            'state_mlp': state_results,
            'temporal_cnn': cnn_results,
            'combined': combined_results,
        },
        'data': {
            'n_train': len(train_np),
            'n_val': len(val_np),
            'window': '2h @ 5min (24 steps)',
            'label_dist_train': {
                'no_override': int(np.sum(train_labels == 0)),
                'high': int(np.sum(train_labels == 1)),
                'low': int(np.sum(train_labels == 2)),
            },
        },
        'comparison': {
            'exp305_state_f1': 0.39,
            'note': 'EXP-305 used embeddings+state; ΔF1<0.001 from embeddings',
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Override Model Comparison")
    print(f"{'='*60}")
    print(f"{'Model':>15} {'F1_macro':>9} {'F1_no':>7} {'F1_hi':>7} {'F1_lo':>7}")
    print("-" * 50)
    for name, r in results['models'].items():
        f1s = r['f1_per_class']
        print(f"{name:>15} {r['f1_macro']:>8.4f} "
              f"{f1s[0]:>6.3f} {f1s[1] if len(f1s)>1 else 0:>6.3f} "
              f"{f1s[2] if len(f1s)>2 else 0:>6.3f}")
    print(f"\nEXP-305 baseline (state+embedding): F1=0.39")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp311_temporal_override.json'))
    return results


# ── EXP-312: Rolling Weekly ISF Aggregation ───────────────────────────

def run_rolling_isf(args):
    """EXP-312: Rolling weekly aggregation of ISF response ratio.

    EXP-309 showed per-cycle ISF_effective has enormous variance (std up to
    59 mg/dL/U), making individual-cycle drift detection impossible. This
    experiment aggregates ISF_effective into rolling weekly windows, then
    tests for temporal trend in the smoothed series.

    Method:
    1. Compute per-cycle ISF_effective (same as EXP-309)
    2. Group into rolling 7-day windows with 1-day stride
    3. Compute weekly mean ISF_effective (reduces variance by √N)
    4. Test for temporal trend in weekly series (Spearman + OLS)
    5. Also test month-scale aggregation for even more smoothing

    If weekly smoothing reveals significant trends that per-cycle didn't →
    ISF drift is real but needs aggregation to detect.
    """
    from scipy import stats as scipy_stats

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir

    print("=" * 60)
    print("EXP-312: Rolling Weekly ISF Aggregation")
    print("=" * 60)

    window = 72   # 6h at 5-min = 1 DIA cycle
    stride = 72   # non-overlapping
    MIN_INSULIN = 0.5
    STEPS_PER_DAY = 288  # 24h * 60min / 5min

    per_patient_results = {}

    for pi, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"\n--- Patient {patient_id} ({pi+1}/{len(patient_paths)}) ---")

        df, features_5min = _get_cached_grid(path)
        if df is None:
            print("  SKIP: no data")
            continue

        # Compute per-cycle ISF_effective (reuse EXP-309 logic)
        cycle_isf = []
        cycle_times = []  # time index (in 5-min steps)

        for start in range(0, len(features_5min) - window + 1, stride):
            w = features_5min[start:start + window]
            if np.isnan(w[:, 0]).mean() >= 0.2:
                continue
            w = np.nan_to_num(w, nan=0.0)

            bolus_units = w[:, 4].sum() * 10.0
            basal_total = w[:, 3].mean() * 10.0 * (window * 5 / 60)
            total_insulin = bolus_units + basal_total

            if total_insulin < MIN_INSULIN:
                continue

            glucose_start = w[:12, 0].mean() * 400.0
            glucose_end = w[-12:, 0].mean() * 400.0
            isf_eff = (glucose_end - glucose_start) / total_insulin

            cycle_isf.append(isf_eff)
            cycle_times.append(start)

        if len(cycle_isf) < 20:
            print(f"  SKIP: only {len(cycle_isf)} qualified cycles")
            continue

        cycle_isf = np.array(cycle_isf)
        cycle_times = np.array(cycle_times)

        # Rolling aggregation at multiple scales
        results_by_scale = {}
        for scale_name, scale_days in [('weekly', 7), ('biweekly', 14), ('monthly', 30)]:
            scale_steps = scale_days * STEPS_PER_DAY

            # Group cycles into rolling windows
            rolling_means = []
            rolling_times = []
            rolling_n = []

            # Slide a window of scale_steps across the data
            day_stride = STEPS_PER_DAY  # 1-day stride
            t_min, t_max = cycle_times.min(), cycle_times.max()

            for win_start in range(int(t_min), int(t_max - scale_steps) + 1, day_stride):
                win_end = win_start + scale_steps
                mask = (cycle_times >= win_start) & (cycle_times < win_end)
                n_in_window = mask.sum()

                if n_in_window >= 3:  # need at least 3 cycles per window
                    rolling_means.append(cycle_isf[mask].mean())
                    rolling_times.append((win_start + win_end) / 2)  # midpoint
                    rolling_n.append(int(n_in_window))

            if len(rolling_means) < 5:
                results_by_scale[scale_name] = {
                    'n_windows': len(rolling_means),
                    'error': 'insufficient_rolling_windows',
                }
                continue

            rolling_means = np.array(rolling_means)
            rolling_times = np.array(rolling_times)
            times_norm = (rolling_times - rolling_times.min()) / max(1, rolling_times.max() - rolling_times.min())

            rho, p_spearman = scipy_stats.spearmanr(times_norm, rolling_means)
            slope, intercept = np.polyfit(times_norm, rolling_means, 1)

            # Variance reduction: compare std of rolling means vs raw cycles
            variance_reduction = cycle_isf.std() / max(0.01, rolling_means.std())

            results_by_scale[scale_name] = {
                'n_windows': len(rolling_means),
                'mean_cycles_per_window': float(np.mean(rolling_n)),
                'isf_mean': float(rolling_means.mean()),
                'isf_std': float(rolling_means.std()),
                'raw_std': float(cycle_isf.std()),
                'variance_reduction': float(variance_reduction),
                'spearman_rho': float(rho),
                'spearman_p': float(p_spearman),
                'ols_slope': float(slope),
                'first_half_mean': float(rolling_means[:len(rolling_means)//2].mean()),
                'second_half_mean': float(rolling_means[len(rolling_means)//2:].mean()),
            }

        per_patient_results[patient_id] = {
            'n_raw_cycles': len(cycle_isf),
            'raw_isf_std': float(cycle_isf.std()),
            'scales': results_by_scale,
        }

        # Print weekly summary
        w = results_by_scale.get('weekly', {})
        if 'error' not in w and w:
            sig = "**" if w['spearman_p'] < 0.01 else "*" if w['spearman_p'] < 0.05 else ""
            direction = "resistance↑" if w['ols_slope'] > 0 else "sensitivity↑"
            print(f"  {len(cycle_isf)} cycles → {w['n_windows']} weekly windows")
            print(f"  Variance reduction: {w['variance_reduction']:.1f}× "
                  f"(raw std={cycle_isf.std():.1f}, weekly std={w['isf_std']:.1f})")
            print(f"  Weekly trend: ρ={w['spearman_rho']:+.3f} (p={w['spearman_p']:.4f}{sig})")
            print(f"  1st half→2nd half: {w['first_half_mean']:+.1f} → {w['second_half_mean']:+.1f}")
        else:
            print(f"  Insufficient rolling windows")

    # Summary across all scales
    results = {
        'experiment': 'EXP-312',
        'name': 'rolling-isf-aggregation',
        'method': 'Rolling weekly/biweekly/monthly mean of per-cycle ISF_effective',
        'cycle_window': f'{window*5/60:.0f}h (non-overlapping)',
        'per_patient': per_patient_results,
        'summary': {},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Rolling ISF Aggregation Summary")
    print(f"{'='*60}")

    for scale_name in ['weekly', 'biweekly', 'monthly']:
        print(f"\n--- {scale_name.upper()} scale ---")
        print(f"{'Patient':>8} {'N_win':>6} {'VarRed':>7} {'ρ':>7} {'p':>8} {'Slope':>7} {'Trend':>14}")
        print("-" * 65)

        trending = []
        for pid in sorted(per_patient_results.keys()):
            s = per_patient_results[pid]['scales'].get(scale_name, {})
            if 'error' in s or not s:
                print(f"{pid:>8} {'—':>6}")
                continue
            sig = "**" if s['spearman_p'] < 0.01 else "*" if s['spearman_p'] < 0.05 else ""
            direction = "resistance↑" if s['ols_slope'] > 0 else "sensitivity↑"
            print(f"{pid:>8} {s['n_windows']:>6} {s['variance_reduction']:>6.1f}× "
                  f"{s['spearman_rho']:>+6.3f} {s['spearman_p']:>7.4f}{sig} "
                  f"{s['ols_slope']:>+6.2f} {direction:>14}")
            if s['spearman_p'] < 0.05:
                trending.append(pid)

        results['summary'][scale_name] = {
            'n_significant': len(trending),
            'patients_significant': trending,
        }
        print(f"  Significant: {len(trending)}/{len(per_patient_results)}")

    print(f"\n{'='*60}")
    save_results(results, os.path.join(output_dir, 'exp312_rolling_isf.json'))
    return results


# ── EXP-313: 1D-CNN UAM Detection ────────────────────────────────────

def run_cnn_uam(args):
    """EXP-313: 1D-CNN for UAM (Unannounced Meal) detection.

    EXP-291 achieved F1=0.40 with embedding + linear classifier at 2h.
    EXP-311 showed 1D-CNN beats embeddings for override prediction.
    This tests whether 1D-CNN also beats embeddings for UAM detection.

    Compares:
    1. Embedding + classifier (EXP-291 approach)
    2. 1D-CNN on raw 2h window
    3. Combined (CNN + embedding)

    UAM = rapid glucose rise (>2 mg/dL/min) without recent carb entry.
    """
    from .pattern_embedding import PatternEncoder

    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-313: 1D-CNN UAM Detection")
    print("=" * 60)

    # Load 2h fast data
    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    # Build UAM labels (same logic as EXP-291)
    def build_uam_labels(windows):
        """UAM = rapid glucose rise without recent carbs."""
        half = windows.shape[1] // 2
        hist = windows[:, :half]
        glucose = hist[:, :, 0] * 400.0
        carbs = hist[:, :, 5]  # carb channel

        # Rate of change > 2 mg/dL/min = 10 mg/dL per 5min step
        roc = np.diff(glucose, axis=1)
        rapid_rise = (roc > 10).any(axis=1)

        # No significant carbs in recent history
        no_carbs = carbs.sum(axis=1) < 0.01

        # UAM = rapid rise + no carbs
        uam = (rapid_rise & no_carbs).astype(np.int64)
        return uam

    train_uam = build_uam_labels(train_np)
    val_uam = build_uam_labels(val_np)
    print(f"UAM prevalence: train={train_uam.mean():.3f} ({train_uam.sum()}/{len(train_uam)}), "
          f"val={val_uam.mean():.3f} ({val_uam.sum()}/{len(val_uam)})")

    if train_uam.sum() < 10:
        print("ERROR: insufficient UAM events")
        return {'experiment': 'EXP-313', 'error': 'insufficient UAM events'}

    # Class weights
    n_pos = train_uam.sum()
    n_neg = len(train_uam) - n_pos
    class_weights = torch.tensor([1.0, n_neg / max(1, n_pos)], dtype=torch.float32).to(device)
    print(f"Class weights: {class_weights.tolist()}")

    # ── Model 1: Embedding + classifier (EXP-291 approach) ──
    class EmbeddingClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = PatternEncoder(input_dim=8, d_model=64, nhead=4,
                                          num_layers=2, embed_dim=32)
            self.classifier = nn.Sequential(
                nn.Linear(32, 16), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(16, 2),
            )
        def forward(self, x):
            half = x.shape[1] // 2
            emb = self.encoder(x[:, :half])
            return self.classifier(emb)

    # ── Model 2: 1D-CNN ──
    class UAMCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 2),
            )
        def forward(self, x):
            half = x.shape[1] // 2
            x = x[:, :half].permute(0, 2, 1)
            features = self.conv(x).squeeze(-1)
            return self.classifier(features)

    # ── Model 3: CNN + Embedding ──
    class CombinedUAM(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.encoder = PatternEncoder(input_dim=8, d_model=64, nhead=4,
                                          num_layers=2, embed_dim=32)
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64 + 32, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 2),
            )
        def forward(self, x):
            half = x.shape[1] // 2
            emb = self.encoder(x[:, :half])
            cnn_feat = self.conv(x[:, :half].permute(0, 2, 1)).squeeze(-1)
            return self.classifier(torch.cat([cnn_feat, emb], dim=1))

    # ── Generic training loop ──
    def train_uam_model(model, model_name):
        model = model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        train_t = torch.from_numpy(train_np).float()
        val_t = torch.from_numpy(val_np).float()
        train_y = torch.from_numpy(train_uam).long()
        val_y = torch.from_numpy(val_uam).long()

        batch_size = 256
        best_val_f1 = 0.0
        patience_counter = 0

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
                model.eval()
                all_preds = []
                with torch.no_grad():
                    for vs in range(0, len(val_np), 512):
                        ve = min(vs + 512, len(val_np))
                        logits = model(val_t[vs:ve].to(device))
                        all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                preds = np.concatenate(all_preds)

                from sklearn.metrics import f1_score
                val_f1 = f1_score(val_uam, preds, zero_division=0)
                if val_f1 > best_val_f1:
                    best_val_f1 = val_f1
                    patience_counter = 0
                else:
                    patience_counter += 1

                if (epoch + 1) % 10 == 0:
                    print(f"  [{model_name}] E{epoch+1}: loss={epoch_loss/n_batches:.4f}, "
                          f"val_F1={val_f1:.4f} (best={best_val_f1:.4f})")

                if patience_counter >= 4:
                    print(f"  [{model_name}] Early stop at epoch {epoch+1}")
                    break

        # Final eval
        model.eval()
        all_preds = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                logits = model(val_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)

        from sklearn.metrics import f1_score, precision_score, recall_score
        return {
            'f1': float(f1_score(val_uam, preds, zero_division=0)),
            'precision': float(precision_score(val_uam, preds, zero_division=0)),
            'recall': float(recall_score(val_uam, preds, zero_division=0)),
            'best_val_f1': float(best_val_f1),
        }

    print("\n--- Model 1: Embedding + Classifier (EXP-291 approach) ---")
    emb_results = train_uam_model(EmbeddingClassifier(), 'Emb')

    print("\n--- Model 2: 1D-CNN ---")
    cnn_results = train_uam_model(UAMCNN(), 'CNN')

    print("\n--- Model 3: Combined (CNN + Embedding) ---")
    combined_results = train_uam_model(CombinedUAM(), 'Combined')

    results = {
        'experiment': 'EXP-313',
        'name': 'cnn-uam-detection',
        'method': '1D-CNN vs embedding vs combined for UAM detection',
        'models': {
            'embedding': emb_results,
            'cnn': cnn_results,
            'combined': combined_results,
        },
        'data': {
            'n_train': len(train_np),
            'n_val': len(val_np),
            'uam_prevalence_train': float(train_uam.mean()),
            'uam_prevalence_val': float(val_uam.mean()),
        },
        'comparison': {
            'exp291_f1': 0.40,
            'note': 'EXP-291 used same embedding approach, achieved F1=0.40',
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"UAM Detection Model Comparison")
    print(f"{'='*60}")
    print(f"{'Model':>15} {'F1':>7} {'Prec':>7} {'Recall':>7}")
    print("-" * 40)
    for name, r in results['models'].items():
        print(f"{name:>15} {r['f1']:>6.4f} {r['precision']:>6.4f} {r['recall']:>6.4f}")
    print(f"\nEXP-291 baseline: F1=0.40, Recall=0.68")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp313_cnn_uam.json'))
    return results


# ── EXP-314: Multi-Lead-Time Override Prediction ─────────────────────

def run_multi_lead_override(args):
    """EXP-314: Override prediction at multiple lead times (15/30/60 min).

    EXP-311 showed 1D-CNN achieves F1=0.726 for "will glucose leave [70,180]
    in the next 1 hour?" This tests whether shorter prediction horizons
    (15min, 30min) are easier and more actionable, or if longer lead gives
    the model more signal to work with.

    Trains a separate 1D-CNN for each lead time:
    - 15 min (3 future steps): Immediate alert
    - 30 min (6 future steps): Short-term warning
    - 60 min (12 future steps): Full hour prediction (EXP-311 baseline)
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-314: Multi-Lead-Time Override Prediction")
    print("=" * 60)

    # Load 2h fast data
    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    lead_configs = [
        ('15min', 3),   # 3 steps × 5min = 15 min
        ('30min', 6),   # 6 steps × 5min = 30 min
        ('60min', 12),  # 12 steps × 5min = 60 min (EXP-311 baseline)
    ]

    all_results = {}

    for lead_name, lead_steps in lead_configs:
        print(f"\n--- Lead time: {lead_name} ({lead_steps} steps) ---")

        # Build labels: will glucose leave [70, 180] in the NEXT lead_steps?
        half = train_np.shape[1] // 2  # history/future boundary

        def build_lead_labels(windows, n_steps):
            future = windows[:, half:half + n_steps, 0] * 400.0
            high = (future > 180).any(axis=1)
            low = (future < 70).any(axis=1)
            labels = np.zeros(len(windows), dtype=np.int64)
            labels[high] = 1
            labels[low] = 2  # low overrides high (safety)
            return labels

        train_labels = build_lead_labels(train_np, lead_steps)
        val_labels = build_lead_labels(val_np, lead_steps)

        n_no = (train_labels == 0).sum()
        n_hi = (train_labels == 1).sum()
        n_lo = (train_labels == 2).sum()
        print(f"  Labels: no={n_no}, high={n_hi}, low={n_lo}")

        # Class weights
        from collections import Counter
        counts = Counter(train_labels.tolist())
        n_total = len(train_labels)
        n_classes = 3
        class_weights = torch.tensor([
            n_total / (n_classes * max(1, counts.get(c, 1))) for c in range(n_classes)
        ], dtype=torch.float32).to(device)

        # 1D-CNN model (same architecture as EXP-311)
        class LeadCNN(nn.Module):
            def __init__(self, in_channels=8, n_classes=3):
                super().__init__()
                self.conv = nn.Sequential(
                    nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(32),
                    nn.Conv1d(32, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.AdaptiveAvgPool1d(1),
                )
                self.classifier = nn.Sequential(
                    nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                    nn.Linear(32, n_classes),
                )
            def forward(self, x):
                h = x.shape[1] // 2
                x = x[:, :h].permute(0, 2, 1)
                feat = self.conv(x).squeeze(-1)
                return self.classifier(feat)

        model = LeadCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        train_t = torch.from_numpy(train_np).float()
        val_t = torch.from_numpy(val_np).float()
        train_y = torch.from_numpy(train_labels).long()

        batch_size = 256
        best_val_f1 = 0.0

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            epoch_loss = 0.0
            n_batches = 0

            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            if (epoch + 1) % 10 == 0 or epoch == epochs - 1:
                model.eval()
                all_preds = []
                with torch.no_grad():
                    for vs in range(0, len(val_np), 512):
                        ve = min(vs + 512, len(val_np))
                        logits = model(val_t[vs:ve].to(device))
                        all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                preds = np.concatenate(all_preds)

                from sklearn.metrics import f1_score
                val_f1 = f1_score(val_labels, preds, average='macro', zero_division=0)
                best_val_f1 = max(best_val_f1, val_f1)
                print(f"  [{lead_name}] E{epoch+1}: loss={epoch_loss/n_batches:.4f}, "
                      f"val_F1={val_f1:.4f} (best={best_val_f1:.4f})")

        # Final eval
        model.eval()
        all_preds = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                logits = model(val_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)

        from sklearn.metrics import f1_score, classification_report
        f1_macro = f1_score(val_labels, preds, average='macro', zero_division=0)
        f1_per = f1_score(val_labels, preds, average=None, zero_division=0)
        report = classification_report(val_labels, preds,
                                       target_names=['no_override', 'high', 'low'],
                                       zero_division=0, output_dict=True)

        all_results[lead_name] = {
            'lead_steps': lead_steps,
            'lead_minutes': lead_steps * 5,
            'f1_macro': float(f1_macro),
            'f1_per_class': [float(f) for f in f1_per],
            'best_val_f1': float(best_val_f1),
            'label_dist': {'no': int(n_no), 'high': int(n_hi), 'low': int(n_lo)},
            'classification_report': report,
        }

    results = {
        'experiment': 'EXP-314',
        'name': 'multi-lead-override',
        'method': '1D-CNN override at 15/30/60 min lead times',
        'leads': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np)},
        'comparison': {'exp311_60min_f1': 0.726},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Multi-Lead Override Comparison")
    print(f"{'='*60}")
    print(f"{'Lead':>8} {'F1_macro':>9} {'F1_no':>7} {'F1_hi':>7} {'F1_lo':>7} {'N_hi':>6} {'N_lo':>6}")
    print("-" * 55)
    for name, r in sorted(all_results.items(), key=lambda x: x[1]['lead_minutes']):
        f = r['f1_per_class']
        d = r['label_dist']
        print(f"{name:>8} {r['f1_macro']:>8.4f} {f[0]:>6.3f} {f[1]:>6.3f} "
              f"{f[2]:>6.3f} {d['high']:>6} {d['low']:>6}")
    print(f"\nEXP-311 baseline (60min): F1=0.726")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp314_multi_lead.json'))
    return results


# ── EXP-315: Dedicated Hypo Prediction CNN ───────────────────────────

def run_hypo_cnn(args):
    """EXP-315: Dedicated CNN for hypoglycemia prediction.

    EXP-311 showed low override F1=0.515 (hypo is hardest to predict).
    This experiment dedicates a full CNN to hypo prediction with:
    - Binary labels (hypo vs not-hypo) for focused optimization
    - Multiple thresholds (70, 65, 54 mg/dL) for severity grading
    - Class-balanced sampling with aggressive hypo weighting
    - Extended input: both history half AND recent glucose trend features
    - Per-patient evaluation (hypo risk varies greatly)
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-315: Dedicated Hypo Prediction CNN")
    print("=" * 60)

    # Load 2h fast data
    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    half = train_np.shape[1] // 2
    thresholds = {
        'mild_70': 70.0,     # standard hypo threshold
        'moderate_65': 65.0, # Level 1 hypo
        'severe_54': 54.0,   # Level 2 hypo (clinically significant)
    }

    lead_configs = [
        ('30min', 6),   # predict hypo in next 30 min
        ('60min', 12),  # predict hypo in next 60 min
    ]

    all_results = {}

    for threshold_name, threshold in thresholds.items():
        for lead_name, lead_steps in lead_configs:
            config_name = f"{threshold_name}_{lead_name}"
            print(f"\n--- {config_name}: glucose < {threshold} in next {lead_name} ---")

            # Binary hypo labels
            def build_hypo_labels(windows, thresh, n_steps):
                future = windows[:, half:half + n_steps, 0] * 400.0
                hypo = (future < thresh).any(axis=1).astype(np.int64)
                return hypo

            train_labels = build_hypo_labels(train_np, threshold, lead_steps)
            val_labels = build_hypo_labels(val_np, threshold, lead_steps)

            n_pos = train_labels.sum()
            n_neg = len(train_labels) - n_pos
            prevalence = n_pos / len(train_labels)
            print(f"  Prevalence: {prevalence:.3f} ({n_pos}/{len(train_labels)})")

            if n_pos < 20:
                print(f"  SKIP: insufficient hypo events ({n_pos})")
                all_results[config_name] = {'error': f'insufficient events ({n_pos})'}
                continue

            # Aggressive class weighting for rare events
            pos_weight = max(2.0, n_neg / max(1, n_pos))
            class_weights = torch.tensor([1.0, pos_weight], dtype=torch.float32).to(device)
            print(f"  Class weight: [1.0, {pos_weight:.1f}]")

            # 1D-CNN with deeper architecture for hypo subtleties
            class HypoCNN(nn.Module):
                def __init__(self, in_channels=8):
                    super().__init__()
                    self.conv = nn.Sequential(
                        nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                        nn.ReLU(), nn.BatchNorm1d(32),
                        nn.Conv1d(32, 64, kernel_size=3, padding=1),
                        nn.ReLU(), nn.BatchNorm1d(64),
                        nn.Conv1d(64, 64, kernel_size=3, padding=1),
                        nn.ReLU(), nn.BatchNorm1d(64),
                        nn.AdaptiveAvgPool1d(1),
                    )
                    self.classifier = nn.Sequential(
                        nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                        nn.Linear(32, 2),
                    )
                def forward(self, x):
                    h = x.shape[1] // 2
                    x = x[:, :h].permute(0, 2, 1)
                    feat = self.conv(x).squeeze(-1)
                    return self.classifier(feat)

            model = HypoCNN().to(device)
            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
            criterion = nn.CrossEntropyLoss(weight=class_weights)

            train_t = torch.from_numpy(train_np).float()
            val_t = torch.from_numpy(val_np).float()
            train_y = torch.from_numpy(train_labels).long()

            batch_size = 256
            best_val_f1 = 0.0
            patience = 0

            for epoch in range(epochs):
                model.train()
                perm = torch.randperm(len(train_np))
                epoch_loss = 0.0
                n_batches = 0

                for start in range(0, len(perm), batch_size):
                    end = min(start + batch_size, len(perm))
                    idx = perm[start:end]
                    logits = model(train_t[idx].to(device))
                    loss = criterion(logits, train_y[idx].to(device))
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    epoch_loss += loss.item()
                    n_batches += 1

                if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
                    model.eval()
                    all_preds = []
                    with torch.no_grad():
                        for vs in range(0, len(val_np), 512):
                            ve = min(vs + 512, len(val_np))
                            logits = model(val_t[vs:ve].to(device))
                            all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                    preds = np.concatenate(all_preds)

                    from sklearn.metrics import f1_score
                    val_f1 = f1_score(val_labels, preds, zero_division=0)
                    if val_f1 > best_val_f1:
                        best_val_f1 = val_f1
                        patience = 0
                    else:
                        patience += 1

                    if (epoch + 1) % 10 == 0:
                        print(f"  [{config_name}] E{epoch+1}: loss={epoch_loss/n_batches:.4f}, "
                              f"F1={val_f1:.4f} (best={best_val_f1:.4f})")

                    if patience >= 4:
                        print(f"  [{config_name}] Early stop at epoch {epoch+1}")
                        break

            # Final eval
            model.eval()
            all_preds = []
            all_probs = []
            with torch.no_grad():
                for vs in range(0, len(val_np), 512):
                    ve = min(vs + 512, len(val_np))
                    logits = model(val_t[vs:ve].to(device))
                    all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                    all_probs.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
            preds = np.concatenate(all_preds)
            probs = np.concatenate(all_probs)

            from sklearn.metrics import f1_score, precision_score, recall_score
            from sklearn.metrics import roc_auc_score

            f1 = f1_score(val_labels, preds, zero_division=0)
            prec = precision_score(val_labels, preds, zero_division=0)
            rec = recall_score(val_labels, preds, zero_division=0)
            try:
                auc = roc_auc_score(val_labels, probs)
            except ValueError:
                auc = float('nan')

            all_results[config_name] = {
                'threshold': threshold,
                'lead_minutes': lead_steps * 5,
                'prevalence': float(prevalence),
                'f1': float(f1),
                'precision': float(prec),
                'recall': float(rec),
                'auc_roc': float(auc),
                'best_val_f1': float(best_val_f1),
                'n_hypo_train': int(n_pos),
                'n_hypo_val': int(val_labels.sum()),
            }
            print(f"  Result: F1={f1:.4f}, P={prec:.4f}, R={rec:.4f}, AUC={auc:.4f}")

    results = {
        'experiment': 'EXP-315',
        'name': 'hypo-prediction-cnn',
        'method': 'Dedicated 3-layer CNN for binary hypo prediction',
        'configs': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np)},
        'comparison': {'exp311_low_override_f1': 0.515},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Hypo Prediction Summary")
    print(f"{'='*60}")
    print(f"{'Config':>22} {'Prev':>6} {'F1':>7} {'Prec':>7} {'Recall':>7} {'AUC':>7}")
    print("-" * 60)
    for name in sorted(all_results.keys()):
        r = all_results[name]
        if 'error' in r:
            print(f"{name:>22} {'SKIP':>6}")
            continue
        print(f"{name:>22} {r['prevalence']:>5.3f} {r['f1']:>6.4f} "
              f"{r['precision']:>6.4f} {r['recall']:>6.4f} {r['auc_roc']:>6.4f}")
    print(f"\nEXP-311 baseline (low override, 60min): F1=0.515")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp315_hypo_cnn.json'))
    return results


# ── EXP-316: ISF Trend as Downstream Feature ────────────────────────

def run_isf_as_feature(args):
    """EXP-316: Feed rolling ISF trend into override and UAM models.

    EXP-312 showed rolling biweekly ISF_effective tracks real drift in 9/11
    patients. This tests whether adding ISF metabolic context as an input
    feature improves downstream classification tasks:
    - Does knowing "patient is becoming more insulin sensitive" help predict
      whether an override is needed?
    - Does ISF trend help predict UAM events?

    Method: Compute rolling ISF_effective at each timestep, append as
    additional channel to the 2h window, retrain CNN classifiers.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-316: ISF Trend as Downstream Feature")
    print("=" * 60)

    # Step 1: Compute per-patient rolling ISF for each 5-min timestep
    from tools.cgmencode.real_data_adapter import build_nightscout_grid

    # Build pid→path mapping from the list
    pid_paths = {}
    for p in patient_paths:
        pid = os.path.basename(os.path.dirname(p))
        pid_paths[pid] = p

    all_isf_grids = {}
    window_14d = 4032  # 14 days in 5-min steps

    for pid, ppath in sorted(pid_paths.items()):
        result = _get_cached_grid(ppath)
        if result is None or result[0] is None:
            continue
        _, grid = result

        n_rows = grid.shape[0]
        glucose = grid[:, 0] * 400.0
        bolus = grid[:, 4] * 10.0

        # Vectorized: compute ISF_eff at each bolus event, then rolling mean
        bolus_idxs = np.where(bolus > 0.5)[0]
        bolus_idxs = bolus_idxs[(bolus_idxs >= 6) & (bolus_idxs + 24 < n_rows)]

        # Compute g_before (mean of 3 steps before) and g_after (mean of steps 18-24 after)
        isf_at_bolus = np.full(n_rows, np.nan)
        for bi in bolus_idxs:
            g_before = np.nanmean(glucose[bi - 3:bi])
            g_after = np.nanmean(glucose[bi + 18:bi + 24])
            dose = bolus[bi]
            if np.isnan(g_before) or np.isnan(g_after) or dose < 0.5:
                continue
            isf_eff = (g_before - g_after) / dose
            if -200 < isf_eff < 200:
                isf_at_bolus[bi] = isf_eff

        # Rolling 14-day mean of per-bolus ISF values (vectorized with searchsorted)
        isf_trace = np.full(n_rows, np.nan)
        valid_isf_idx = np.where(~np.isnan(isf_at_bolus))[0]
        valid_isf_vals = isf_at_bolus[valid_isf_idx]
        if len(valid_isf_idx) >= 3:
            # Use sorted index for O(log n) lookups
            cumsum = np.cumsum(valid_isf_vals)
            cumsum = np.insert(cumsum, 0, 0.0)  # prepend 0 for easy slicing
            for t in range(n_rows):
                lo = np.searchsorted(valid_isf_idx, max(0, t - window_14d), side='left')
                hi = np.searchsorted(valid_isf_idx, t, side='right')
                count = hi - lo
                if count >= 3:
                    isf_trace[t] = (cumsum[hi] - cumsum[lo]) / count

        # Forward-fill NaNs
        last_valid = np.nan
        for t in range(n_rows):
            if not np.isnan(isf_trace[t]):
                last_valid = isf_trace[t]
            elif not np.isnan(last_valid):
                isf_trace[t] = last_valid

        # Normalize to ~[0, 1] range: typical ISF 20-80 mg/dL/U
        isf_trace = np.clip(isf_trace / 100.0, -2.0, 2.0)
        all_isf_grids[pid] = isf_trace
        valid_pct = (~np.isnan(isf_trace)).mean() * 100
        print(f"  Patient {pid}: ISF coverage {valid_pct:.1f}%, "
              f"mean={np.nanmean(isf_trace)*100:.1f} mg/dL/U")

    # Step 2: Load windows and append ISF channel
    print("\nLoading 2h windows with ISF channel...")
    window_2h = 24
    stride = window_2h // 2

    all_train_8ch = []
    all_train_9ch = []
    all_val_8ch = []
    all_val_9ch = []

    for pid, ppath in sorted(pid_paths.items()):
        result = _get_cached_grid(ppath)
        if result is None or result[0] is None:
            continue
        df_grid, _ = result

        features = _grid_to_features(df_grid)
        n_rows = features.shape[0]
        n_ch = features.shape[1]

        isf_trace = all_isf_grids.get(pid)
        if isf_trace is None:
            continue

        # Build windows
        windows_8ch = []
        windows_9ch = []
        for start in range(0, n_rows - window_2h + 1, stride):
            w = features[start:start + window_2h]
            if np.isnan(w[:, 0]).mean() >= 0.2:
                continue
            # Replace NaN with 0
            w_clean = np.nan_to_num(w, nan=0.0)
            windows_8ch.append(w_clean)

            # Append ISF channel
            isf_ch = isf_trace[start:start + window_2h].copy()
            isf_ch = np.nan_to_num(isf_ch, nan=0.0).reshape(-1, 1)
            w9 = np.concatenate([w_clean, isf_ch], axis=1)
            windows_9ch.append(w9)

        if not windows_8ch:
            continue

        arr_8 = np.array(windows_8ch, dtype=np.float32)
        arr_9 = np.array(windows_9ch, dtype=np.float32)

        split_idx = int(len(arr_8) * 0.8)
        all_train_8ch.append(arr_8[:split_idx])
        all_val_8ch.append(arr_8[split_idx:])
        all_train_9ch.append(arr_9[:split_idx])
        all_val_9ch.append(arr_9[split_idx:])

    train_8 = np.concatenate(all_train_8ch)
    val_8 = np.concatenate(all_val_8ch)
    train_9 = np.concatenate(all_train_9ch)
    val_9 = np.concatenate(all_val_9ch)
    print(f"8ch: {train_8.shape} train, {val_8.shape} val")
    print(f"9ch: {train_9.shape} train, {val_9.shape} val")

    # Step 3: Train CNN classifiers WITH and WITHOUT ISF channel
    half = train_8.shape[1] // 2
    tasks = {
        'override': {'lead': 12, 'n_classes': 3},
        'uam': {'lead': 6, 'n_classes': 2},
    }

    all_results = {}

    for task_name, task_cfg in tasks.items():
        lead = task_cfg['lead']
        n_cls = task_cfg['n_classes']
        print(f"\n=== Task: {task_name} (lead={lead*5}min, {n_cls} classes) ===")

        def build_labels(windows, lead_steps, n_classes):
            future = windows[:, half:half + lead_steps, 0] * 400.0
            if n_classes == 3:  # override
                high = (future > 180).any(axis=1)
                low = (future < 70).any(axis=1)
                labels = np.zeros(len(windows), dtype=np.int64)
                labels[high] = 1
                labels[low] = 2
                return labels
            else:  # uam: sharp rise
                rise = np.diff(future, axis=1)
                sharp_rise = (rise > 3.0).any(axis=1)
                return sharp_rise.astype(np.int64)

        train_y = build_labels(train_8, lead, n_cls)
        val_y = build_labels(val_8, lead, n_cls)

        for variant, (train_data, val_data, in_ch) in [
            ('baseline_8ch', (train_8, val_8, 8)),
            ('with_isf_9ch', (train_9, val_9, 9)),
        ]:
            print(f"\n--- {variant} ---")

            # Class weights
            from collections import Counter
            counts = Counter(train_y.tolist())
            n_total = len(train_y)
            cw = torch.tensor([
                n_total / (n_cls * max(1, counts.get(c, 1))) for c in range(n_cls)
            ], dtype=torch.float32).to(device)

            class TaskCNN(nn.Module):
                def __init__(self, in_channels, n_classes):
                    super().__init__()
                    self.conv = nn.Sequential(
                        nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                        nn.ReLU(), nn.BatchNorm1d(32),
                        nn.Conv1d(32, 64, kernel_size=3, padding=1),
                        nn.ReLU(), nn.BatchNorm1d(64),
                        nn.AdaptiveAvgPool1d(1),
                    )
                    self.classifier = nn.Sequential(
                        nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                        nn.Linear(32, n_classes),
                    )
                def forward(self, x):
                    h = x.shape[1] // 2
                    x = x[:, :h].permute(0, 2, 1)
                    feat = self.conv(x).squeeze(-1)
                    return self.classifier(feat)

            model = TaskCNN(in_ch, n_cls).to(device)
            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
            criterion = nn.CrossEntropyLoss(weight=cw)

            train_t = torch.from_numpy(train_data).float()
            val_t = torch.from_numpy(val_data).float()
            train_yt = torch.from_numpy(train_y).long()

            batch_size = 256
            best_f1 = 0.0

            for epoch in range(epochs):
                model.train()
                perm = torch.randperm(len(train_data))
                for start in range(0, len(perm), batch_size):
                    end = min(start + batch_size, len(perm))
                    idx = perm[start:end]
                    logits = model(train_t[idx].to(device))
                    loss = criterion(logits, train_yt[idx].to(device))
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                if (epoch + 1) % 10 == 0 or epoch == epochs - 1:
                    model.eval()
                    all_preds = []
                    with torch.no_grad():
                        for vs in range(0, len(val_data), 512):
                            ve = min(vs + 512, len(val_data))
                            logits = model(val_t[vs:ve].to(device))
                            all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                    preds = np.concatenate(all_preds)
                    from sklearn.metrics import f1_score
                    f1 = f1_score(val_y, preds, average='macro', zero_division=0)
                    best_f1 = max(best_f1, f1)
                    print(f"    E{epoch+1}: F1={f1:.4f} (best={best_f1:.4f})")

            # Final eval
            model.eval()
            all_preds = []
            with torch.no_grad():
                for vs in range(0, len(val_data), 512):
                    ve = min(vs + 512, len(val_data))
                    logits = model(val_t[vs:ve].to(device))
                    all_preds.append(logits.argmax(dim=-1).cpu().numpy())
            preds = np.concatenate(all_preds)
            from sklearn.metrics import f1_score
            f1_final = f1_score(val_y, preds, average='macro', zero_division=0)
            f1_per = f1_score(val_y, preds, average=None, zero_division=0)

            key = f"{task_name}_{variant}"
            all_results[key] = {
                'task': task_name,
                'variant': variant,
                'in_channels': in_ch,
                'f1_macro': float(f1_final),
                'f1_per_class': [float(f) for f in f1_per],
                'best_val_f1': float(best_f1),
            }

    results = {
        'experiment': 'EXP-316',
        'name': 'isf-as-feature',
        'method': 'CNN with/without rolling ISF_eff as 9th input channel',
        'configs': all_results,
        'data': {'n_train_8ch': len(train_8), 'n_train_9ch': len(train_9)},
        'isf_coverage': {pid: float((~np.isnan(v)).mean())
                         for pid, v in all_isf_grids.items()},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"ISF-as-Feature Comparison")
    print(f"{'='*60}")
    print(f"{'Config':>30} {'F1_macro':>9} {'Delta':>7}")
    print("-" * 48)
    for task_name in ['override', 'uam']:
        base_key = f"{task_name}_baseline_8ch"
        isf_key = f"{task_name}_with_isf_9ch"
        base_f1 = all_results[base_key]['f1_macro']
        isf_f1 = all_results[isf_key]['f1_macro']
        delta = isf_f1 - base_f1
        sign = '+' if delta >= 0 else ''
        print(f"{base_key:>30} {base_f1:>8.4f}")
        print(f"{isf_key:>30} {isf_f1:>8.4f} {sign}{delta:>6.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp316_isf_feature.json'))
    return results


# ── EXP-317: Hypo Threshold Optimization ─────────────────────────────

def run_hypo_threshold_opt(args):
    """EXP-317: Optimize probability threshold for hypo prediction.

    EXP-315 showed AUC=0.95 but F1=0.52 using argmax (threshold=0.5).
    With 6.4% prevalence, the optimal threshold should be much lower.
    This experiment:
    1. Trains the same hypo CNN as EXP-315
    2. Sweeps probability thresholds from 0.01 to 0.99
    3. Reports optimal F1, F2 (recall-weighted), and F0.5 (precision-weighted)
    4. Evaluates per-patient performance at optimal threshold
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-317: Hypo Threshold Optimization")
    print("=" * 60)

    # Load 2h fast data
    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    half = train_np.shape[1] // 2
    configs = [
        ('mild_70_30min', 70.0, 6),
        ('mild_70_60min', 70.0, 12),
    ]

    all_results = {}

    for config_name, threshold, lead_steps in configs:
        print(f"\n--- {config_name}: glucose < {threshold} in {lead_steps*5}min ---")

        def build_hypo_labels(windows, thresh, n_steps):
            future = windows[:, half:half + n_steps, 0] * 400.0
            return (future < thresh).any(axis=1).astype(np.int64)

        train_labels = build_hypo_labels(train_np, threshold, lead_steps)
        val_labels = build_hypo_labels(val_np, threshold, lead_steps)
        n_pos = train_labels.sum()
        n_neg = len(train_labels) - n_pos
        prevalence = n_pos / len(train_labels)
        print(f"  Prevalence: {prevalence:.3f} ({n_pos}/{len(train_labels)})")

        pos_weight = max(2.0, n_neg / max(1, n_pos))
        class_weights = torch.tensor([1.0, pos_weight], dtype=torch.float32).to(device)

        class HypoCNN(nn.Module):
            def __init__(self, in_channels=8):
                super().__init__()
                self.conv = nn.Sequential(
                    nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(32),
                    nn.Conv1d(32, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.Conv1d(64, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.AdaptiveAvgPool1d(1),
                )
                self.classifier = nn.Sequential(
                    nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                    nn.Linear(32, 2),
                )
            def forward(self, x):
                h = x.shape[1] // 2
                x = x[:, :h].permute(0, 2, 1)
                feat = self.conv(x).squeeze(-1)
                return self.classifier(feat)

        model = HypoCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        train_t = torch.from_numpy(train_np).float()
        val_t = torch.from_numpy(val_np).float()
        train_y = torch.from_numpy(train_labels).long()

        batch_size = 256
        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            if (epoch + 1) % 10 == 0:
                model.eval()
                all_preds = []
                with torch.no_grad():
                    for vs in range(0, len(val_np), 512):
                        ve = min(vs + 512, len(val_np))
                        logits = model(val_t[vs:ve].to(device))
                        all_preds.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
                probs = np.concatenate(all_preds)
                from sklearn.metrics import f1_score
                preds = (probs >= 0.5).astype(int)
                f1 = f1_score(val_labels, preds, zero_division=0)
                print(f"  E{epoch+1}: F1@0.5={f1:.4f}")

        # Get final probabilities
        model.eval()
        all_probs = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                logits = model(val_t[vs:ve].to(device))
                all_probs.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
        probs = np.concatenate(all_probs)

        # Threshold sweep
        from sklearn.metrics import f1_score, precision_score, recall_score, fbeta_score
        thresholds = np.arange(0.01, 1.0, 0.01)
        sweep_results = []
        best_f1 = 0.0
        best_f1_thresh = 0.5
        best_f2 = 0.0
        best_f2_thresh = 0.5

        for thresh in thresholds:
            preds = (probs >= thresh).astype(int)
            f1 = f1_score(val_labels, preds, zero_division=0)
            f2 = fbeta_score(val_labels, preds, beta=2, zero_division=0)
            prec = precision_score(val_labels, preds, zero_division=0)
            rec = recall_score(val_labels, preds, zero_division=0)
            sweep_results.append({
                'threshold': float(thresh),
                'f1': float(f1), 'f2': float(f2),
                'precision': float(prec), 'recall': float(rec),
            })
            if f1 > best_f1:
                best_f1 = f1
                best_f1_thresh = float(thresh)
            if f2 > best_f2:
                best_f2 = f2
                best_f2_thresh = float(thresh)

        # Report
        f1_at_05 = f1_score(val_labels, (probs >= 0.5).astype(int), zero_division=0)
        f1_at_opt = best_f1
        preds_opt = (probs >= best_f1_thresh).astype(int)
        prec_opt = precision_score(val_labels, preds_opt, zero_division=0)
        rec_opt = recall_score(val_labels, preds_opt, zero_division=0)

        print(f"\n  Threshold sweep results:")
        print(f"    F1@0.50 (argmax): {f1_at_05:.4f}")
        print(f"    F1@{best_f1_thresh:.2f} (optimal): {best_f1:.4f} "
              f"(P={prec_opt:.3f}, R={rec_opt:.3f})")
        print(f"    F2@{best_f2_thresh:.2f} (recall-heavy): {best_f2:.4f}")
        print(f"    Improvement: +{(best_f1 - f1_at_05):.4f} ({(best_f1/max(f1_at_05,0.001)-1)*100:.1f}%)")

        all_results[config_name] = {
            'threshold': threshold,
            'lead_minutes': lead_steps * 5,
            'prevalence': float(prevalence),
            'f1_at_0.5': float(f1_at_05),
            'best_f1': float(best_f1),
            'best_f1_threshold': float(best_f1_thresh),
            'best_f1_precision': float(prec_opt),
            'best_f1_recall': float(rec_opt),
            'best_f2': float(best_f2),
            'best_f2_threshold': float(best_f2_thresh),
            'sweep': sweep_results,
        }

    results = {
        'experiment': 'EXP-317',
        'name': 'hypo-threshold-optimization',
        'method': 'Probability threshold sweep for hypo CNN',
        'configs': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np)},
        'comparison': {'exp315_f1_argmax': 0.520},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Hypo Threshold Optimization Summary")
    print(f"{'='*60}")
    for name, r in all_results.items():
        print(f"\n{name}:")
        print(f"  F1 @ 0.50 (argmax): {r['f1_at_0.5']:.4f}")
        print(f"  F1 @ {r['best_f1_threshold']:.2f} (optimal): {r['best_f1']:.4f} "
              f"(+{r['best_f1'] - r['f1_at_0.5']:.4f})")
        print(f"  F2 @ {r['best_f2_threshold']:.2f} (recall): {r['best_f2']:.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp317_hypo_threshold.json'))
    return results


# ── EXP-318: Per-Patient Override Fine-Tuning ────────────────────────

def run_per_patient_override(args):
    """EXP-318: Per-patient fine-tuning for override prediction.

    EXP-242 showed per-patient fine-tuned ensembles improved forecasting
    by 9.1%. This tests the same approach for override classification:
    1. Train base CNN on all patients (EXP-314 architecture)
    2. Fine-tune on each patient's data with lower learning rate
    3. Compare per-patient F1 vs base model
    4. Report which patients benefit most from personalization
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-318: Per-Patient Override Fine-Tuning")
    print("=" * 60)

    # Step 1: Load per-patient data separately
    from tools.cgmencode.real_data_adapter import build_nightscout_grid

    per_patient_data = {}
    for ppath in patient_paths:
        pid = os.path.basename(os.path.dirname(ppath))
        result = _get_cached_grid(ppath)
        if result is None or result[0] is None:
            continue
        df_grid, _ = result
        features = _grid_to_features(df_grid)

        window = 24
        stride = window // 2
        windows = []
        for start in range(0, len(features) - window + 1, stride):
            w = features[start:start + window]
            if np.isnan(w[:, 0]).mean() < 0.2:
                windows.append(np.nan_to_num(w, nan=0.0))

        if len(windows) < 100:
            print(f"  Patient {pid}: SKIP ({len(windows)} windows)")
            continue

        arr = np.array(windows, dtype=np.float32)
        split = int(len(arr) * 0.8)
        per_patient_data[pid] = {
            'train': arr[:split],
            'val': arr[split:],
        }
        print(f"  Patient {pid}: {split} train, {len(arr)-split} val")

    # Step 2: Build all-patient pooled data
    all_train = np.concatenate([d['train'] for d in per_patient_data.values()])
    all_val = np.concatenate([d['val'] for d in per_patient_data.values()])
    print(f"\nPooled: {all_train.shape} train, {all_val.shape} val")

    half = all_train.shape[1] // 2
    lead_steps = 6  # 30 min (best from EXP-314)

    def build_labels(windows, lead=lead_steps):
        future = windows[:, half:half + lead, 0] * 400.0
        high = (future > 180).any(axis=1)
        low = (future < 70).any(axis=1)
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2
        return labels

    class OverrideCNN(nn.Module):
        def __init__(self, in_channels=8, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )
        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.conv(x).squeeze(-1)
            return self.classifier(feat)

    # Step 3: Train base model on all patients
    print("\n--- Training base model (all patients) ---")
    from collections import Counter
    train_labels = build_labels(all_train)
    val_labels = build_labels(all_val)
    counts = Counter(train_labels.tolist())
    n_total = len(train_labels)
    cw = torch.tensor([n_total / (3 * max(1, counts.get(c, 1))) for c in range(3)],
                       dtype=torch.float32).to(device)

    base_model = OverrideCNN().to(device)
    optimizer = torch.optim.Adam(base_model.parameters(), lr=1e-3, weight_decay=1e-5)
    criterion = nn.CrossEntropyLoss(weight=cw)

    train_t = torch.from_numpy(all_train).float()
    train_y = torch.from_numpy(train_labels).long()
    batch_size = 256

    for epoch in range(epochs):
        base_model.train()
        perm = torch.randperm(len(all_train))
        for start in range(0, len(perm), batch_size):
            end = min(start + batch_size, len(perm))
            idx = perm[start:end]
            logits = base_model(train_t[idx].to(device))
            loss = criterion(logits, train_y[idx].to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        if (epoch + 1) % 10 == 0:
            base_model.eval()
            all_preds = []
            with torch.no_grad():
                val_t = torch.from_numpy(all_val).float()
                for vs in range(0, len(all_val), 512):
                    ve = min(vs + 512, len(all_val))
                    logits = base_model(val_t[vs:ve].to(device))
                    all_preds.append(logits.argmax(dim=-1).cpu().numpy())
            preds = np.concatenate(all_preds)
            from sklearn.metrics import f1_score
            f1 = f1_score(val_labels, preds, average='macro', zero_division=0)
            print(f"  E{epoch+1}: F1={f1:.4f}")

    # Save base model state
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

    # Step 4: Evaluate base model per-patient
    base_model.eval()
    base_per_patient = {}
    for pid, data in sorted(per_patient_data.items()):
        val_arr = data['val']
        val_y = build_labels(val_arr)
        val_t = torch.from_numpy(val_arr).float()
        all_preds = []
        with torch.no_grad():
            for vs in range(0, len(val_arr), 512):
                ve = min(vs + 512, len(val_arr))
                logits = base_model(val_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)
        from sklearn.metrics import f1_score
        f1 = f1_score(val_y, preds, average='macro', zero_division=0)
        base_per_patient[pid] = float(f1)
        print(f"  Base {pid}: F1={f1:.4f}")

    # Step 5: Fine-tune per patient
    ft_epochs = max(10, epochs // 3)
    ft_per_patient = {}

    for pid, data in sorted(per_patient_data.items()):
        print(f"\n--- Fine-tuning patient {pid} ({ft_epochs} epochs) ---")
        train_arr = data['train']
        val_arr = data['val']
        train_y = build_labels(train_arr)
        val_y = build_labels(val_arr)

        # Reset to base model
        ft_model = OverrideCNN().to(device)
        ft_model.load_state_dict(base_state)

        # Lower learning rate for fine-tuning
        ft_optimizer = torch.optim.Adam(ft_model.parameters(), lr=1e-4, weight_decay=1e-5)

        # Per-patient class weights
        p_counts = Counter(train_y.tolist())
        p_total = len(train_y)
        p_cw = torch.tensor([p_total / (3 * max(1, p_counts.get(c, 1))) for c in range(3)],
                             dtype=torch.float32).to(device)
        ft_criterion = nn.CrossEntropyLoss(weight=p_cw)

        train_t = torch.from_numpy(train_arr).float()
        train_yt = torch.from_numpy(train_y).long()
        best_f1 = 0.0

        for epoch in range(ft_epochs):
            ft_model.train()
            perm = torch.randperm(len(train_arr))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = ft_model(train_t[idx].to(device))
                loss = ft_criterion(logits, train_yt[idx].to(device))
                ft_optimizer.zero_grad()
                loss.backward()
                ft_optimizer.step()

        # Evaluate
        ft_model.eval()
        val_t = torch.from_numpy(val_arr).float()
        all_preds = []
        with torch.no_grad():
            for vs in range(0, len(val_arr), 512):
                ve = min(vs + 512, len(val_arr))
                logits = ft_model(val_t[vs:ve].to(device))
                all_preds.append(logits.argmax(dim=-1).cpu().numpy())
        preds = np.concatenate(all_preds)
        from sklearn.metrics import f1_score
        ft_f1 = f1_score(val_y, preds, average='macro', zero_division=0)
        ft_per_patient[pid] = float(ft_f1)
        delta = ft_f1 - base_per_patient[pid]
        sign = '+' if delta >= 0 else ''
        print(f"  FT {pid}: F1={ft_f1:.4f} (base={base_per_patient[pid]:.4f}, "
              f"Δ={sign}{delta:.4f})")

    results = {
        'experiment': 'EXP-318',
        'name': 'per-patient-override',
        'method': 'Base CNN + per-patient fine-tuning for 30min override prediction',
        'base_per_patient': base_per_patient,
        'ft_per_patient': ft_per_patient,
        'improvement': {
            pid: float(ft_per_patient.get(pid, 0) - base_per_patient.get(pid, 0))
            for pid in base_per_patient
        },
        'data': {pid: {'n_train': len(d['train']), 'n_val': len(d['val'])}
                 for pid, d in per_patient_data.items()},
        'config': {'lead_steps': lead_steps, 'ft_epochs': ft_epochs, 'ft_lr': 1e-4},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    # Summary table
    print(f"\n{'='*60}")
    print(f"Per-Patient Override Fine-Tuning Summary")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'Base F1':>8} {'FT F1':>8} {'Delta':>8}")
    print("-" * 35)
    total_base = 0.0
    total_ft = 0.0
    n_patients = 0
    for pid in sorted(base_per_patient.keys()):
        b = base_per_patient[pid]
        f = ft_per_patient.get(pid, b)
        d = f - b
        sign = '+' if d >= 0 else ''
        print(f"{pid:>8} {b:>7.4f} {f:>7.4f} {sign}{d:>7.4f}")
        total_base += b
        total_ft += f
        n_patients += 1
    avg_base = total_base / max(1, n_patients)
    avg_ft = total_ft / max(1, n_patients)
    avg_d = avg_ft - avg_base
    sign = '+' if avg_d >= 0 else ''
    print("-" * 35)
    print(f"{'Mean':>8} {avg_base:>7.4f} {avg_ft:>7.4f} {sign}{avg_d:>7.4f}")
    improved = sum(1 for pid in base_per_patient
                   if ft_per_patient.get(pid, 0) > base_per_patient[pid])
    print(f"\n{improved}/{n_patients} patients improved by fine-tuning")
    print(f"{'='*60}")

    results['summary'] = {
        'mean_base_f1': float(avg_base),
        'mean_ft_f1': float(avg_ft),
        'mean_improvement': float(avg_d),
        'patients_improved': improved,
        'total_patients': n_patients,
    }

    save_results(results, os.path.join(output_dir, 'exp318_per_patient_override.json'))
    return results


# ── EXP-319: Selective Per-Patient Override Ensemble ─────────────────

def run_selective_ensemble(args):
    """EXP-319: Selective ensemble — FT where validation improves, base elsewhere.

    EXP-318 showed FT helps 5/11 patients. This tests the practical deployment
    strategy: train base model, fine-tune all patients, but only USE the fine-tuned
    model when validation F1 improves. Otherwise keep the base model.

    Also tests at both 15min and 30min lead times (EXP-314 showed 15min is best).
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-319: Selective Per-Patient Override Ensemble")
    print("=" * 60)

    # Load per-patient data
    per_patient_data = {}
    for ppath in patient_paths:
        pid = os.path.basename(os.path.dirname(ppath))
        result = _get_cached_grid(ppath)
        if result is None or result[0] is None:
            continue
        df_grid, _ = result
        features = _grid_to_features(df_grid)

        window = 24
        stride = window // 2
        windows = []
        for start in range(0, len(features) - window + 1, stride):
            w = features[start:start + window]
            if np.isnan(w[:, 0]).mean() < 0.2:
                windows.append(np.nan_to_num(w, nan=0.0))

        if len(windows) < 100:
            continue

        arr = np.array(windows, dtype=np.float32)
        split = int(len(arr) * 0.8)
        per_patient_data[pid] = {'train': arr[:split], 'val': arr[split:]}

    all_train = np.concatenate([d['train'] for d in per_patient_data.values()])
    half = all_train.shape[1] // 2

    lead_configs = [('15min', 3), ('30min', 6)]
    all_results = {}

    class OverrideCNN(nn.Module):
        def __init__(self, in_channels=8, n_classes=3):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, n_classes),
            )
        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.conv(x).squeeze(-1)
            return self.classifier(feat)

    for lead_name, lead_steps in lead_configs:
        print(f"\n{'='*50}")
        print(f"Lead time: {lead_name}")
        print(f"{'='*50}")

        def build_labels(windows, lead=lead_steps):
            future = windows[:, half:half + lead, 0] * 400.0
            high = (future > 180).any(axis=1)
            low = (future < 70).any(axis=1)
            labels = np.zeros(len(windows), dtype=np.int64)
            labels[high] = 1
            labels[low] = 2
            return labels

        # Train base model
        print("\n--- Training base model ---")
        all_train = np.concatenate([d['train'] for d in per_patient_data.values()])
        train_labels = build_labels(all_train)
        from collections import Counter
        counts = Counter(train_labels.tolist())
        n_total = len(train_labels)
        cw = torch.tensor([n_total / (3 * max(1, counts.get(c, 1))) for c in range(3)],
                           dtype=torch.float32).to(device)

        base_model = OverrideCNN().to(device)
        optimizer = torch.optim.Adam(base_model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=cw)
        train_t = torch.from_numpy(all_train).float()
        train_y = torch.from_numpy(train_labels).long()
        batch_size = 256

        for epoch in range(epochs):
            base_model.train()
            perm = torch.randperm(len(all_train))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = base_model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

        # Evaluate base + FT per patient, select best
        patient_results = {}
        ft_epochs = max(10, epochs // 3)

        for pid in sorted(per_patient_data.keys()):
            data = per_patient_data[pid]
            val_arr = data['val']
            val_y = build_labels(val_arr)
            val_t = torch.from_numpy(val_arr).float()

            def eval_model(model):
                model.eval()
                all_preds = []
                with torch.no_grad():
                    for vs in range(0, len(val_arr), 512):
                        ve = min(vs + 512, len(val_arr))
                        logits = model(val_t[vs:ve].to(device))
                        all_preds.append(logits.argmax(dim=-1).cpu().numpy())
                preds = np.concatenate(all_preds)
                from sklearn.metrics import f1_score
                return f1_score(val_y, preds, average='macro', zero_division=0)

            # Base model eval
            base_f1 = eval_model(base_model)

            # Fine-tune
            ft_model = OverrideCNN().to(device)
            ft_model.load_state_dict(base_state)
            ft_optimizer = torch.optim.Adam(ft_model.parameters(), lr=1e-4, weight_decay=1e-5)
            train_arr = data['train']
            ft_train_y = build_labels(train_arr)
            p_counts = Counter(ft_train_y.tolist())
            p_total = len(ft_train_y)
            p_cw = torch.tensor([p_total / (3 * max(1, p_counts.get(c, 1))) for c in range(3)],
                                 dtype=torch.float32).to(device)
            ft_criterion = nn.CrossEntropyLoss(weight=p_cw)
            ft_train_t = torch.from_numpy(train_arr).float()
            ft_train_yt = torch.from_numpy(ft_train_y).long()

            for epoch in range(ft_epochs):
                ft_model.train()
                perm = torch.randperm(len(train_arr))
                for start in range(0, len(perm), batch_size):
                    end = min(start + batch_size, len(perm))
                    idx = perm[start:end]
                    logits = ft_model(ft_train_t[idx].to(device))
                    loss = ft_criterion(logits, ft_train_yt[idx].to(device))
                    ft_optimizer.zero_grad()
                    loss.backward()
                    ft_optimizer.step()

            ft_f1 = eval_model(ft_model)

            # Selective: use FT only if it improves
            use_ft = ft_f1 > base_f1
            selected_f1 = ft_f1 if use_ft else base_f1
            patient_results[pid] = {
                'base_f1': float(base_f1),
                'ft_f1': float(ft_f1),
                'selected': 'ft' if use_ft else 'base',
                'selected_f1': float(selected_f1),
            }
            marker = '✓ FT' if use_ft else '✗ BASE'
            print(f"  {pid}: base={base_f1:.4f} ft={ft_f1:.4f} → {marker} ({selected_f1:.4f})")

        # Compute ensemble metrics
        base_mean = np.mean([r['base_f1'] for r in patient_results.values()])
        ft_mean = np.mean([r['ft_f1'] for r in patient_results.values()])
        sel_mean = np.mean([r['selected_f1'] for r in patient_results.values()])
        n_ft = sum(1 for r in patient_results.values() if r['selected'] == 'ft')
        n_base = sum(1 for r in patient_results.values() if r['selected'] == 'base')

        print(f"\n  Ensemble: {n_ft} FT + {n_base} base")
        print(f"  Mean: base={base_mean:.4f}, ft_all={ft_mean:.4f}, selective={sel_mean:.4f}")

        all_results[lead_name] = {
            'lead_steps': lead_steps,
            'patients': patient_results,
            'base_mean_f1': float(base_mean),
            'ft_all_mean_f1': float(ft_mean),
            'selective_mean_f1': float(sel_mean),
            'n_ft': n_ft,
            'n_base': n_base,
        }

    results = {
        'experiment': 'EXP-319',
        'name': 'selective-per-patient-ensemble',
        'method': 'Selective FT: use fine-tuned model only when val F1 improves',
        'leads': all_results,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Selective Ensemble Summary")
    print(f"{'='*60}")
    print(f"{'Lead':>8} {'Base':>8} {'FT all':>8} {'Select':>8} {'N_FT':>5} {'Δ vs base':>9}")
    print("-" * 50)
    for name, r in all_results.items():
        d = r['selective_mean_f1'] - r['base_mean_f1']
        sign = '+' if d >= 0 else ''
        print(f"{name:>8} {r['base_mean_f1']:>7.4f} {r['ft_all_mean_f1']:>7.4f} "
              f"{r['selective_mean_f1']:>7.4f} {r['n_ft']:>4}/{r['n_ft']+r['n_base']} "
              f"{sign}{d:>8.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp319_selective_ensemble.json'))
    return results


# ── EXP-320: IOB Trajectory Features for Hypo ───────────────────────

def run_iob_hypo(args):
    """EXP-320: Enhanced features for hypo prediction.

    EXP-315/317 showed hypo AUC=0.95 but F1=0.63 (with threshold tuning).
    This adds derived features specifically informative for hypo events:
    - IOB slope (rate of IOB change over last 30 min)
    - Time since last bolus (minutes, normalized)
    - Glucose momentum (2nd derivative — acceleration of glucose change)
    - IOB × glucose_slope interaction (high IOB + falling glucose → danger)
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-320: IOB Trajectory Features for Hypo Prediction")
    print("=" * 60)

    # Load per-patient and compute derived features
    all_train_8 = []
    all_val_8 = []
    all_train_12 = []
    all_val_12 = []

    for ppath in patient_paths:
        pid = os.path.basename(os.path.dirname(ppath))
        result = _get_cached_grid(ppath)
        if result is None or result[0] is None:
            continue
        df_grid, _ = result
        features = _grid_to_features(df_grid)  # [n, 8]
        n_rows = features.shape[0]

        # Compute derived channels
        glucose = features[:, 0]    # normalized
        iob = features[:, 1]        # normalized
        bolus = features[:, 4]      # normalized

        # IOB slope: rate of IOB change over 6 steps (30 min)
        iob_slope = np.zeros(n_rows, dtype=np.float32)
        for i in range(6, n_rows):
            iob_slope[i] = (iob[i] - iob[i - 6]) / 6.0

        # Time since last bolus (in 5-min steps, normalized by 288 = 24h)
        time_since_bolus = np.zeros(n_rows, dtype=np.float32)
        last_bolus_idx = -1
        for i in range(n_rows):
            if bolus[i] > 0.01:
                last_bolus_idx = i
            if last_bolus_idx >= 0:
                time_since_bolus[i] = min((i - last_bolus_idx) / 288.0, 1.0)
            else:
                time_since_bolus[i] = 1.0

        # Glucose momentum (2nd derivative over 3 steps)
        glucose_momentum = np.zeros(n_rows, dtype=np.float32)
        for i in range(6, n_rows):
            d1 = glucose[i] - glucose[i - 3]
            d2 = glucose[i - 3] - glucose[i - 6]
            glucose_momentum[i] = (d1 - d2)  # acceleration

        # IOB × glucose_slope interaction
        glucose_slope = np.zeros(n_rows, dtype=np.float32)
        for i in range(3, n_rows):
            glucose_slope[i] = glucose[i] - glucose[i - 3]
        iob_gluc_interaction = iob * glucose_slope

        derived = np.column_stack([iob_slope, time_since_bolus,
                                   glucose_momentum, iob_gluc_interaction])

        # Build windows
        window = 24
        stride = window // 2
        windows_8 = []
        windows_12 = []
        for start in range(0, n_rows - window + 1, stride):
            w8 = features[start:start + window]
            if np.isnan(w8[:, 0]).mean() >= 0.2:
                continue
            w8_clean = np.nan_to_num(w8, nan=0.0)
            d4 = derived[start:start + window]
            d4_clean = np.nan_to_num(d4, nan=0.0)
            w12 = np.concatenate([w8_clean, d4_clean], axis=1)
            windows_8.append(w8_clean)
            windows_12.append(w12)

        if not windows_8:
            continue

        arr_8 = np.array(windows_8, dtype=np.float32)
        arr_12 = np.array(windows_12, dtype=np.float32)
        split = int(len(arr_8) * 0.8)
        all_train_8.append(arr_8[:split])
        all_val_8.append(arr_8[split:])
        all_train_12.append(arr_12[:split])
        all_val_12.append(arr_12[split:])
        print(f"  Patient {pid}: {len(arr_8)} windows")

    train_8 = np.concatenate(all_train_8)
    val_8 = np.concatenate(all_val_8)
    train_12 = np.concatenate(all_train_12)
    val_12 = np.concatenate(all_val_12)
    print(f"\n8ch: {train_8.shape} train, {val_8.shape} val")
    print(f"12ch: {train_12.shape} train, {val_12.shape} val")

    half = train_8.shape[1] // 2
    threshold = 70.0
    lead_steps = 6  # 30 min

    def build_hypo_labels(windows):
        future = windows[:, half:half + lead_steps, 0] * 400.0
        return (future < threshold).any(axis=1).astype(np.int64)

    train_y = build_hypo_labels(train_8)
    val_y = build_hypo_labels(val_8)
    prevalence = train_y.mean()
    print(f"Hypo prevalence: {prevalence:.3f}")

    pos_weight = max(2.0, (1 - prevalence) / max(prevalence, 0.001))

    all_results = {}

    for variant, train_data, val_data, in_ch in [
        ('baseline_8ch', train_8, val_8, 8),
        ('enhanced_12ch', train_12, val_12, 12),
    ]:
        print(f"\n--- {variant} (in_ch={in_ch}) ---")
        class_weights = torch.tensor([1.0, pos_weight], dtype=torch.float32).to(device)

        class HypoCNN(nn.Module):
            def __init__(self, in_channels):
                super().__init__()
                self.conv = nn.Sequential(
                    nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(32),
                    nn.Conv1d(32, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.Conv1d(64, 64, kernel_size=3, padding=1),
                    nn.ReLU(), nn.BatchNorm1d(64),
                    nn.AdaptiveAvgPool1d(1),
                )
                self.classifier = nn.Sequential(
                    nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                    nn.Linear(32, 2),
                )
            def forward(self, x):
                h = x.shape[1] // 2
                x = x[:, :h].permute(0, 2, 1)
                feat = self.conv(x).squeeze(-1)
                return self.classifier(feat)

        model = HypoCNN(in_ch).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.CrossEntropyLoss(weight=class_weights)

        train_t = torch.from_numpy(train_data).float()
        val_t = torch.from_numpy(val_data).float()
        train_yt = torch.from_numpy(train_y).long()
        batch_size = 256

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_data))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_yt[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            if (epoch + 1) % 10 == 0:
                model.eval()
                all_probs = []
                with torch.no_grad():
                    for vs in range(0, len(val_data), 512):
                        ve = min(vs + 512, len(val_data))
                        logits = model(val_t[vs:ve].to(device))
                        all_probs.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
                probs = np.concatenate(all_probs)
                preds = (probs >= 0.5).astype(int)
                from sklearn.metrics import f1_score
                f1 = f1_score(val_y, preds, zero_division=0)
                print(f"    E{epoch+1}: F1@0.5={f1:.4f}")

        # Final eval with threshold sweep
        model.eval()
        all_probs = []
        with torch.no_grad():
            for vs in range(0, len(val_data), 512):
                ve = min(vs + 512, len(val_data))
                logits = model(val_t[vs:ve].to(device))
                all_probs.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
        probs = np.concatenate(all_probs)

        from sklearn.metrics import f1_score, precision_score, recall_score
        from sklearn.metrics import roc_auc_score, fbeta_score

        best_f1 = 0.0
        best_thresh = 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            preds = (probs >= thresh).astype(int)
            f1 = f1_score(val_y, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = float(thresh)

        preds_opt = (probs >= best_thresh).astype(int)
        f1_at_05 = f1_score(val_y, (probs >= 0.5).astype(int), zero_division=0)
        try:
            auc = roc_auc_score(val_y, probs)
        except ValueError:
            auc = float('nan')

        prec = precision_score(val_y, preds_opt, zero_division=0)
        rec = recall_score(val_y, preds_opt, zero_division=0)

        all_results[variant] = {
            'in_channels': in_ch,
            'f1_at_0.5': float(f1_at_05),
            'best_f1': float(best_f1),
            'best_threshold': float(best_thresh),
            'precision_at_opt': float(prec),
            'recall_at_opt': float(rec),
            'auc_roc': float(auc),
        }
        print(f"  F1@0.5={f1_at_05:.4f}, F1@{best_thresh:.2f}={best_f1:.4f}, "
              f"AUC={auc:.4f}")

    results = {
        'experiment': 'EXP-320',
        'name': 'iob-trajectory-hypo',
        'method': 'Enhanced IOB/glucose features for hypo CNN',
        'features_added': ['iob_slope', 'time_since_bolus', 'glucose_momentum',
                          'iob_glucose_interaction'],
        'configs': all_results,
        'data': {'n_train': len(train_8), 'n_val': len(val_8)},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"IOB Trajectory Hypo Features Comparison")
    print(f"{'='*60}")
    for name, r in all_results.items():
        print(f"  {name}: F1@opt={r['best_f1']:.4f} @{r['best_threshold']:.2f}, "
              f"AUC={r['auc_roc']:.4f}")
    base_f1 = all_results['baseline_8ch']['best_f1']
    enh_f1 = all_results['enhanced_12ch']['best_f1']
    delta = enh_f1 - base_f1
    sign = '+' if delta >= 0 else ''
    print(f"  Delta: {sign}{delta:.4f} ({sign}{delta/max(base_f1,0.001)*100:.1f}%)")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp320_iob_hypo.json'))
    return results


# ── EXP-321: Focal Loss for Hypo Prediction ─────────────────────────

def run_focal_hypo(args):
    """EXP-321: Focal loss for hypo prediction.

    EXP-315/317 used class-weighted CrossEntropyLoss. Focal loss (Lin et al. 2017)
    naturally down-weights easy negatives and focuses on hard-to-classify examples.
    This should help with the precision problem (too many false positives) because
    easy true negatives won't dominate the gradient.

    Tests: focal γ=1,2,3 vs weighted CE baseline. All with threshold optimization.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-321: Focal Loss for Hypo Prediction")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    half = train_np.shape[1] // 2
    threshold = 70.0
    lead_steps = 6  # 30 min

    def build_hypo_labels(windows):
        future = windows[:, half:half + lead_steps, 0] * 400.0
        return (future < threshold).any(axis=1).astype(np.int64)

    train_labels = build_hypo_labels(train_np)
    val_labels = build_hypo_labels(val_np)
    n_pos = train_labels.sum()
    n_neg = len(train_labels) - n_pos
    prevalence = n_pos / len(train_labels)
    print(f"Prevalence: {prevalence:.3f} ({n_pos}/{len(train_labels)})")

    class FocalLoss(nn.Module):
        def __init__(self, gamma=2.0, alpha=None):
            super().__init__()
            self.gamma = gamma
            self.alpha = alpha

        def forward(self, logits, targets):
            ce_loss = nn.functional.cross_entropy(logits, targets, reduction='none',
                                                  weight=self.alpha)
            pt = torch.exp(-ce_loss)
            focal_loss = ((1 - pt) ** self.gamma) * ce_loss
            return focal_loss.mean()

    class HypoCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.classifier = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 2),
            )
        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.conv(x).squeeze(-1)
            return self.classifier(feat)

    pos_weight = max(2.0, n_neg / max(1, n_pos))
    alpha = torch.tensor([1.0, pos_weight], dtype=torch.float32).to(device)

    configs = [
        ('weighted_ce', None, None),
        ('focal_g1', 1.0, alpha),
        ('focal_g2', 2.0, alpha),
        ('focal_g3', 3.0, alpha),
        ('focal_g2_no_alpha', 2.0, None),
    ]

    all_results = {}
    train_t = torch.from_numpy(train_np).float()
    val_t = torch.from_numpy(val_np).float()
    train_y = torch.from_numpy(train_labels).long()

    for config_name, gamma, alpha_weights in configs:
        print(f"\n--- {config_name} ---")

        model = HypoCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)

        if gamma is None:
            criterion = nn.CrossEntropyLoss(weight=alpha)
        else:
            criterion = FocalLoss(gamma=gamma, alpha=alpha_weights)

        batch_size = 256
        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                logits = model(train_t[idx].to(device))
                loss = criterion(logits, train_y[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Get probabilities
        model.eval()
        all_probs = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                logits = model(val_t[vs:ve].to(device))
                all_probs.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
        probs = np.concatenate(all_probs)

        # Threshold sweep
        from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
        best_f1 = 0.0
        best_thresh = 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            preds = (probs >= thresh).astype(int)
            f1 = f1_score(val_labels, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = float(thresh)

        preds_opt = (probs >= best_thresh).astype(int)
        f1_at_05 = f1_score(val_labels, (probs >= 0.5).astype(int), zero_division=0)
        try:
            auc = roc_auc_score(val_labels, probs)
        except ValueError:
            auc = float('nan')
        prec = precision_score(val_labels, preds_opt, zero_division=0)
        rec = recall_score(val_labels, preds_opt, zero_division=0)

        all_results[config_name] = {
            'gamma': gamma,
            'has_alpha': alpha_weights is not None,
            'f1_at_0.5': float(f1_at_05),
            'best_f1': float(best_f1),
            'best_threshold': float(best_thresh),
            'precision': float(prec),
            'recall': float(rec),
            'auc_roc': float(auc),
        }
        print(f"  F1@0.5={f1_at_05:.4f}, F1@{best_thresh:.2f}={best_f1:.4f}, "
              f"P={prec:.3f}, R={rec:.3f}, AUC={auc:.4f}")

    results = {
        'experiment': 'EXP-321',
        'name': 'focal-loss-hypo',
        'method': 'Focal loss vs weighted CE for hypo prediction CNN',
        'configs': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np),
                 'prevalence': float(prevalence)},
        'comparison': {'exp317_best_f1': 0.630},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Focal Loss Comparison")
    print(f"{'='*60}")
    print(f"{'Config':>20} {'F1@0.5':>8} {'F1@opt':>8} {'Thresh':>7} {'AUC':>7}")
    print("-" * 55)
    for name, r in all_results.items():
        print(f"{name:>20} {r['f1_at_0.5']:>7.4f} {r['best_f1']:>7.4f} "
              f"{r['best_threshold']:>6.2f} {r['auc_roc']:>6.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp321_focal_hypo.json'))
    return results


# ── EXP-322: Multi-Task Override+Hypo CNN ────────────────────────────

def run_multitask_cnn(args):
    """EXP-322: Multi-task CNN predicting override type AND hypo probability.

    Hypothesis: Shared feature extraction between related tasks (override
    prediction and hypo prediction) should improve both via shared
    representations. Both tasks use the same 2h input window.

    Architecture:
    - Shared CNN backbone (32→64→64 channels)
    - Override head: 3-class (none/high/low)
    - Hypo head: binary (hypo/not-hypo at 30min)
    - Joint loss = override_loss + λ × hypo_loss (λ=1.0)
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-322: Multi-Task Override+Hypo CNN")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    half = train_np.shape[1] // 2

    # Override labels (15min lead — best from EXP-314)
    def build_override_labels(windows, lead=3):
        future = windows[:, half:half + lead, 0] * 400.0
        high = (future > 180).any(axis=1)
        low = (future < 70).any(axis=1)
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2
        return labels

    # Hypo labels (30min lead)
    def build_hypo_labels(windows, lead=6):
        future = windows[:, half:half + lead, 0] * 400.0
        return (future < 70).any(axis=1).astype(np.int64)

    train_override = build_override_labels(train_np)
    val_override = build_override_labels(val_np)
    train_hypo = build_hypo_labels(train_np)
    val_hypo = build_hypo_labels(val_np)

    print(f"Override: {(train_override > 0).mean():.3f} positive rate")
    print(f"Hypo: {train_hypo.mean():.3f} prevalence")

    class MultiTaskCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 3),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 2),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.backbone(x).squeeze(-1)
            return self.override_head(feat), self.hypo_head(feat)

    # Class weights
    from collections import Counter
    ov_counts = Counter(train_override.tolist())
    n_total = len(train_override)
    ov_cw = torch.tensor([n_total / (3 * max(1, ov_counts.get(c, 1))) for c in range(3)],
                          dtype=torch.float32).to(device)

    n_hypo_pos = train_hypo.sum()
    n_hypo_neg = len(train_hypo) - n_hypo_pos
    hypo_weight = max(2.0, n_hypo_neg / max(1, n_hypo_pos))
    hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

    # Also train single-task baselines for fair comparison
    configs = {
        'multitask': 'multi',
        'single_override': 'override',
        'single_hypo': 'hypo',
    }

    all_results = {}
    train_t = torch.from_numpy(train_np).float()
    val_t = torch.from_numpy(val_np).float()
    train_ov_t = torch.from_numpy(train_override).long()
    train_hypo_t = torch.from_numpy(train_hypo).long()
    batch_size = 256

    for config_name, mode in configs.items():
        print(f"\n--- {config_name} ---")

        model = MultiTaskCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)
        hypo_criterion = nn.CrossEntropyLoss(weight=hypo_cw)

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                ov_logits, hypo_logits = model(train_t[idx].to(device))

                if mode == 'multi':
                    loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                           hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
                elif mode == 'override':
                    loss = ov_criterion(ov_logits, train_ov_t[idx].to(device))
                else:
                    loss = hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Evaluate both tasks
        model.eval()
        all_ov_preds = []
        all_hypo_probs = []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                ov_logits, hypo_logits = model(val_t[vs:ve].to(device))
                all_ov_preds.append(ov_logits.argmax(dim=-1).cpu().numpy())
                all_hypo_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())

        ov_preds = np.concatenate(all_ov_preds)
        hypo_probs = np.concatenate(all_hypo_probs)

        from sklearn.metrics import f1_score, roc_auc_score
        ov_f1 = f1_score(val_override, ov_preds, average='macro', zero_division=0)

        # Hypo with threshold sweep
        best_hypo_f1 = 0.0
        best_hypo_thresh = 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            preds = (hypo_probs >= thresh).astype(int)
            f1 = f1_score(val_hypo, preds, zero_division=0)
            if f1 > best_hypo_f1:
                best_hypo_f1 = f1
                best_hypo_thresh = float(thresh)

        try:
            hypo_auc = roc_auc_score(val_hypo, hypo_probs)
        except ValueError:
            hypo_auc = float('nan')

        all_results[config_name] = {
            'mode': mode,
            'override_f1': float(ov_f1),
            'hypo_best_f1': float(best_hypo_f1),
            'hypo_threshold': float(best_hypo_thresh),
            'hypo_auc': float(hypo_auc),
        }
        print(f"  Override F1={ov_f1:.4f}, Hypo F1@opt={best_hypo_f1:.4f} "
              f"@{best_hypo_thresh:.2f}, AUC={hypo_auc:.4f}")

    results = {
        'experiment': 'EXP-322',
        'name': 'multitask-override-hypo',
        'method': 'Multi-task CNN: shared backbone + dual heads',
        'configs': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np)},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"Multi-Task CNN Comparison")
    print(f"{'='*60}")
    print(f"{'Config':>20} {'OV_F1':>8} {'Hypo_F1':>8} {'Hypo_AUC':>8}")
    print("-" * 46)
    for name, r in all_results.items():
        print(f"{name:>20} {r['override_f1']:>7.4f} {r['hypo_best_f1']:>7.4f} "
              f"{r['hypo_auc']:>7.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp322_multitask.json'))
    return results


def run_multitask_focal(args):
    """EXP-323: Multi-task CNN with focal loss for hypo head.

    Combines two best hypo improvements:
    - Multi-task backbone (EXP-322): +6.0% hypo F1
    - Focal loss γ=2 (EXP-321): +2.8% hypo F1

    Hypothesis: improvements are complementary — multi-task learns shared
    representations while focal loss focuses on hard hypo examples.
    Tests: multi-task + focal vs multi-task + weighted CE vs single-task + focal.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-323: Multi-Task CNN + Focal Loss")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)
    print(f"Loaded: {train_np.shape} train, {val_np.shape} val")

    half = train_np.shape[1] // 2

    def build_override_labels(windows, lead=3):
        future = windows[:, half:half + lead, 0] * 400.0
        high = (future > 180).any(axis=1)
        low = (future < 70).any(axis=1)
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2
        return labels

    def build_hypo_labels(windows, lead=6):
        future = windows[:, half:half + lead, 0] * 400.0
        return (future < 70).any(axis=1).astype(np.int64)

    train_override = build_override_labels(train_np)
    val_override = build_override_labels(val_np)
    train_hypo = build_hypo_labels(train_np)
    val_hypo = build_hypo_labels(val_np)

    print(f"Override: {(train_override > 0).mean():.3f} positive rate")
    print(f"Hypo: {train_hypo.mean():.3f} prevalence")

    class FocalLoss(nn.Module):
        def __init__(self, gamma=2.0, alpha=None):
            super().__init__()
            self.gamma = gamma
            self.alpha = alpha

        def forward(self, logits, targets):
            ce_loss = nn.functional.cross_entropy(logits, targets, reduction='none',
                                                  weight=self.alpha)
            pt = torch.exp(-ce_loss)
            focal_loss = ((1 - pt) ** self.gamma) * ce_loss
            return focal_loss.mean()

    class MultiTaskCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 3),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 2),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.backbone(x).squeeze(-1)
            return self.override_head(feat), self.hypo_head(feat)

    # Class weights
    from collections import Counter
    ov_counts = Counter(train_override.tolist())
    n_total = len(train_override)
    ov_cw = torch.tensor([n_total / (3 * max(1, ov_counts.get(c, 1))) for c in range(3)],
                          dtype=torch.float32).to(device)

    n_hypo_pos = train_hypo.sum()
    n_hypo_neg = len(train_hypo) - n_hypo_pos
    hypo_weight = max(2.0, n_hypo_neg / max(1, n_hypo_pos))
    hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

    # Configs: vary hypo loss function and multi-task vs single
    configs = {
        'mt_focal_g2': ('multi', 'focal', 2.0),
        'mt_weighted_ce': ('multi', 'wce', 0),
        'st_focal_g2': ('hypo', 'focal', 2.0),
        'st_weighted_ce': ('hypo', 'wce', 0),
        'mt_focal_g2_no_alpha': ('multi', 'focal_no_alpha', 2.0),
    }

    all_results = {}
    train_t = torch.from_numpy(train_np).float()
    val_t = torch.from_numpy(val_np).float()
    train_ov_t = torch.from_numpy(train_override).long()
    train_hypo_t = torch.from_numpy(train_hypo).long()
    batch_size = 256

    for config_name, (task_mode, loss_type, gamma) in configs.items():
        print(f"\n--- {config_name} ---")

        model = MultiTaskCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)

        if loss_type == 'focal':
            hypo_criterion = FocalLoss(gamma=gamma, alpha=hypo_cw)
        elif loss_type == 'focal_no_alpha':
            hypo_criterion = FocalLoss(gamma=gamma, alpha=None)
        else:
            hypo_criterion = nn.CrossEntropyLoss(weight=hypo_cw)

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                ov_logits, hypo_logits = model(train_t[idx].to(device))

                if task_mode == 'multi':
                    loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                           hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
                else:
                    loss = hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Evaluate
        model.eval()
        all_ov_preds, all_hypo_probs = [], []
        with torch.no_grad():
            for vs in range(0, len(val_np), 512):
                ve = min(vs + 512, len(val_np))
                ov_logits, hypo_logits = model(val_t[vs:ve].to(device))
                all_ov_preds.append(ov_logits.argmax(dim=-1).cpu().numpy())
                all_hypo_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())

        ov_preds = np.concatenate(all_ov_preds)
        hypo_probs = np.concatenate(all_hypo_probs)

        from sklearn.metrics import f1_score, roc_auc_score
        ov_f1 = f1_score(val_override, ov_preds, average='macro', zero_division=0)

        best_hypo_f1 = 0.0
        best_hypo_thresh = 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            preds = (hypo_probs >= thresh).astype(int)
            f1 = f1_score(val_hypo, preds, zero_division=0)
            if f1 > best_hypo_f1:
                best_hypo_f1 = f1
                best_hypo_thresh = float(thresh)

        f1_at_05 = f1_score(val_hypo, (hypo_probs >= 0.5).astype(int), zero_division=0)

        try:
            hypo_auc = roc_auc_score(val_hypo, hypo_probs)
        except ValueError:
            hypo_auc = float('nan')

        all_results[config_name] = {
            'task_mode': task_mode,
            'loss_type': loss_type,
            'gamma': gamma,
            'override_f1': float(ov_f1),
            'hypo_f1_at_05': float(f1_at_05),
            'hypo_best_f1': float(best_hypo_f1),
            'hypo_threshold': float(best_hypo_thresh),
            'hypo_auc': float(hypo_auc),
        }
        print(f"  OV F1={ov_f1:.4f}, Hypo F1@0.5={f1_at_05:.4f}, "
              f"F1@opt={best_hypo_f1:.4f} @{best_hypo_thresh:.2f}, AUC={hypo_auc:.4f}")

    results = {
        'experiment': 'EXP-323',
        'name': 'multitask-focal',
        'method': 'Multi-task CNN with focal loss hypo head',
        'configs': all_results,
        'data': {'n_train': len(train_np), 'n_val': len(val_np)},
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"EXP-323: Multi-Task + Focal Loss Comparison")
    print(f"{'='*60}")
    print(f"{'Config':>25} {'Mode':>6} {'Loss':>10} {'OV_F1':>7} "
          f"{'H_F1@.5':>8} {'H_F1opt':>8} {'H_AUC':>7}")
    print("-" * 80)
    for name, r in all_results.items():
        print(f"{name:>25} {r['task_mode']:>6} {r['loss_type']:>10} "
              f"{r['override_f1']:>7.4f} {r['hypo_f1_at_05']:>8.4f} "
              f"{r['hypo_best_f1']:>8.4f} {r['hypo_auc']:>7.4f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp323_multitask_focal.json'))
    return results


def run_calibration_analysis(args):
    """EXP-324: Temperature scaling and calibration analysis for hypo prediction.

    The AUC=0.958 vs F1=0.672 gap suggests the model discriminates well but
    the predicted probabilities are poorly calibrated. Temperature scaling
    is a simple post-hoc calibration technique that learns a single parameter T
    to rescale logits: p = softmax(logits / T).

    Also computes reliability diagrams and ECE (Expected Calibration Error).
    Tests: uncalibrated vs temperature-scaled vs Platt scaling (logistic regression).
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-324: Temperature Scaling & Calibration Analysis")
    print("=" * 60)

    train_np, val_np = load_multiscale_data(patient_paths, scale='fast',
                                            val_fraction=0.2)

    # Split val into calibration + test (50/50)
    n_val = len(val_np)
    n_cal = n_val // 2
    cal_np = val_np[:n_cal]
    test_np = val_np[n_cal:]
    print(f"Loaded: {train_np.shape} train, {cal_np.shape} cal, {test_np.shape} test")

    half = train_np.shape[1] // 2

    def build_hypo_labels(windows, lead=6):
        future = windows[:, half:half + lead, 0] * 400.0
        return (future < 70).any(axis=1).astype(np.int64)

    def build_override_labels(windows, lead=3):
        future = windows[:, half:half + lead, 0] * 400.0
        high = (future > 180).any(axis=1)
        low = (future < 70).any(axis=1)
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2
        return labels

    train_hypo = build_hypo_labels(train_np)
    cal_hypo = build_hypo_labels(cal_np)
    test_hypo = build_hypo_labels(test_np)
    train_override = build_override_labels(train_np)

    print(f"Train hypo prevalence: {train_hypo.mean():.3f}")
    print(f"Cal hypo prevalence: {cal_hypo.mean():.3f}")
    print(f"Test hypo prevalence: {test_hypo.mean():.3f}")

    class MultiTaskCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 3),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 2),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.backbone(x).squeeze(-1)
            return self.override_head(feat), self.hypo_head(feat)

    # Train multi-task CNN with focal loss (best config from EXP-322/321)
    from collections import Counter
    ov_counts = Counter(train_override.tolist())
    n_total = len(train_override)
    ov_cw = torch.tensor([n_total / (3 * max(1, ov_counts.get(c, 1))) for c in range(3)],
                          dtype=torch.float32).to(device)
    n_hypo_pos = train_hypo.sum()
    n_hypo_neg = len(train_hypo) - n_hypo_pos
    hypo_weight = max(2.0, n_hypo_neg / max(1, n_hypo_pos))
    hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

    class FocalLoss(nn.Module):
        def __init__(self, gamma=2.0, alpha=None):
            super().__init__()
            self.gamma = gamma
            self.alpha = alpha

        def forward(self, logits, targets):
            ce_loss = nn.functional.cross_entropy(logits, targets, reduction='none',
                                                  weight=self.alpha)
            pt = torch.exp(-ce_loss)
            return (((1 - pt) ** self.gamma) * ce_loss).mean()

    model = MultiTaskCNN().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)
    hypo_criterion = FocalLoss(gamma=2.0, alpha=hypo_cw)

    print("\nTraining multi-task CNN (focal γ=2)...")
    train_t = torch.from_numpy(train_np).float()
    train_ov_t = torch.from_numpy(train_override).long()
    train_hypo_t = torch.from_numpy(train_hypo).long()
    batch_size = 256

    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(len(train_np))
        for start in range(0, len(perm), batch_size):
            end = min(start + batch_size, len(perm))
            idx = perm[start:end]
            ov_logits, hypo_logits = model(train_t[idx].to(device))
            loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                   hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    # Collect logits on calibration and test sets
    model.eval()
    def get_logits_and_probs(data_np):
        data_t = torch.from_numpy(data_np).float()
        all_logits, all_probs = [], []
        with torch.no_grad():
            for vs in range(0, len(data_np), 512):
                ve = min(vs + 512, len(data_np))
                _, hypo_logits = model(data_t[vs:ve].to(device))
                all_logits.append(hypo_logits.cpu())
                all_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())
        return torch.cat(all_logits), np.concatenate(all_probs)

    cal_logits, cal_probs = get_logits_and_probs(cal_np)
    test_logits, test_probs = get_logits_and_probs(test_np)

    # 1. Temperature Scaling (learn T on calibration set)
    temperature = nn.Parameter(torch.ones(1) * 1.5)
    temp_optimizer = torch.optim.LBFGS([temperature], lr=0.01, max_iter=50)
    cal_labels_t = torch.from_numpy(cal_hypo).long()

    def temp_eval():
        temp_optimizer.zero_grad()
        scaled = cal_logits / temperature
        loss = nn.functional.cross_entropy(scaled, cal_labels_t)
        loss.backward()
        return loss

    temp_optimizer.step(temp_eval)
    learned_T = temperature.item()
    print(f"\nLearned temperature: T={learned_T:.4f}")

    # Apply temperature to test set
    test_scaled_logits = test_logits / learned_T
    test_scaled_probs = torch.softmax(test_scaled_logits, dim=-1)[:, 1].detach().numpy()

    # 2. Platt Scaling (logistic regression on calibration logits)
    from sklearn.linear_model import LogisticRegression
    cal_log_odds = cal_logits[:, 1].numpy().reshape(-1, 1)
    platt_model = LogisticRegression(C=1e10, solver='lbfgs', max_iter=1000)
    platt_model.fit(cal_log_odds, cal_hypo)
    test_log_odds = test_logits[:, 1].numpy().reshape(-1, 1)
    test_platt_probs = platt_model.predict_proba(test_log_odds)[:, 1]

    # 3. Compute metrics for each calibration method
    from sklearn.metrics import f1_score, roc_auc_score, brier_score_loss

    def compute_ece(probs, labels, n_bins=10):
        """Expected Calibration Error."""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            in_bin = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
            if in_bin.sum() == 0:
                continue
            avg_conf = probs[in_bin].mean()
            avg_acc = labels[in_bin].mean()
            ece += in_bin.sum() / len(probs) * abs(avg_acc - avg_conf)
        return float(ece)

    def eval_calibration(probs, labels, name):
        auc = roc_auc_score(labels, probs) if len(np.unique(labels)) > 1 else float('nan')
        ece = compute_ece(probs, labels)
        brier = brier_score_loss(labels, probs)

        best_f1, best_thresh = 0.0, 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            f1 = f1_score(labels, (probs >= thresh).astype(int), zero_division=0)
            if f1 > best_f1:
                best_f1, best_thresh = f1, float(thresh)

        f1_at_05 = f1_score(labels, (probs >= 0.5).astype(int), zero_division=0)

        return {
            'method': name,
            'auc': float(auc),
            'ece': float(ece),
            'brier': float(brier),
            'f1_at_05': float(f1_at_05),
            'f1_optimal': float(best_f1),
            'threshold': float(best_thresh),
        }

    uncalibrated = eval_calibration(test_probs, test_hypo, 'uncalibrated')
    temp_scaled = eval_calibration(test_scaled_probs, test_hypo, 'temperature_scaled')
    platt_scaled = eval_calibration(test_platt_probs, test_hypo, 'platt_scaled')

    # 4. Reliability diagram data (binned accuracy vs confidence)
    def reliability_bins(probs, labels, n_bins=10):
        bins = []
        boundaries = np.linspace(0, 1, n_bins + 1)
        for i in range(n_bins):
            mask = (probs >= boundaries[i]) & (probs < boundaries[i + 1])
            if mask.sum() > 0:
                bins.append({
                    'bin_center': float((boundaries[i] + boundaries[i + 1]) / 2),
                    'mean_confidence': float(probs[mask].mean()),
                    'mean_accuracy': float(labels[mask].mean()),
                    'count': int(mask.sum()),
                })
        return bins

    uncal_bins = reliability_bins(test_probs, test_hypo)
    temp_bins = reliability_bins(test_scaled_probs, test_hypo)
    platt_bins = reliability_bins(test_platt_probs, test_hypo)

    results = {
        'experiment': 'EXP-324',
        'name': 'calibration-analysis',
        'method': 'Temperature scaling and Platt calibration for hypo CNN',
        'learned_temperature': learned_T,
        'metrics': {
            'uncalibrated': uncalibrated,
            'temperature_scaled': temp_scaled,
            'platt_scaled': platt_scaled,
        },
        'reliability': {
            'uncalibrated': uncal_bins,
            'temperature_scaled': temp_bins,
            'platt_scaled': platt_bins,
        },
        'data': {
            'n_train': len(train_np),
            'n_cal': len(cal_np),
            'n_test': len(test_np),
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    print(f"\n{'='*60}")
    print(f"EXP-324: Calibration Analysis")
    print(f"{'='*60}")
    print(f"Learned temperature T={learned_T:.4f}")
    print(f"\n{'Method':>20} {'AUC':>7} {'ECE':>7} {'Brier':>7} "
          f"{'F1@.5':>7} {'F1opt':>7} {'Thresh':>7}")
    print("-" * 70)
    for m in [uncalibrated, temp_scaled, platt_scaled]:
        print(f"{m['method']:>20} {m['auc']:>7.4f} {m['ece']:>7.4f} "
              f"{m['brier']:>7.4f} {m['f1_at_05']:>7.4f} "
              f"{m['f1_optimal']:>7.4f} {m['threshold']:>7.2f}")
    print(f"{'='*60}")

    save_results(results, os.path.join(output_dir, 'exp324_calibration.json'))
    return results


def run_cusum_isf_drift(args):
    """EXP-325: CUSUM and online change-point detection for ISF drift.

    EXP-312 showed rolling biweekly ISF_effective detects drift in 9/11 patients,
    but requires 14 days of data. Can online methods detect changes faster?

    Tests:
    1. CUSUM (Cumulative Sum Control Chart) — sequential detection
    2. EWMA (Exponentially Weighted Moving Average) control chart
    3. Sliding-window t-test with various window sizes (3d, 5d, 7d, 10d, 14d)

    Ground truth: biweekly ISF trend from EXP-312 (linear regression slope).
    Detection metric: earliest day where method flags a significant change,
    vs biweekly method that needs ≥14 days.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir

    print("=" * 60)
    print("EXP-325: CUSUM/Online Change-Point ISF Drift Detection")
    print("=" * 60)

    from tools.cgmencode.real_data_adapter import build_nightscout_grid
    from scipy import stats as sp_stats

    def compute_daily_isf(features_np):
        """Compute daily ISF_effective from features array.
        features_np: (T, 8) — ch0=glucose(normed), ch1=IOB, ch2=COB, etc.
        """
        glucose = features_np[:, 0] * 400.0  # denormalize
        iob = features_np[:, 1]  # already in units

        samples_per_day = 288
        n_days = len(glucose) // samples_per_day
        daily_isf = []
        day_indices = []

        for d in range(n_days):
            s, e = d * samples_per_day, (d + 1) * samples_per_day
            g = glucose[s:e].astype(np.float64)
            i = iob[s:e].astype(np.float64)

            valid = ~(np.isnan(g) | np.isnan(i))
            if valid.sum() < samples_per_day * 0.5:
                continue

            g_valid = g[valid]
            i_valid = i[valid]

            active_iob = i_valid[i_valid > 0.1]
            if len(active_iob) < 10:
                continue

            g_range = np.nanmax(g_valid) - np.nanmin(g_valid)
            mean_iob = np.nanmean(active_iob)
            if mean_iob < 0.05:
                continue

            isf_eff = g_range / mean_iob
            daily_isf.append(isf_eff)
            day_indices.append(d)

        return np.array(daily_isf), np.array(day_indices)

    def cusum_detect(values, threshold_sigma=2.0):
        """CUSUM change-point detection. Returns detection days."""
        if len(values) < 5:
            return [], float('nan')
        mu = np.mean(values[:min(7, len(values))])
        sigma = max(np.std(values[:min(7, len(values))]), 1e-6)
        h = threshold_sigma * sigma  # Decision threshold
        k = 0.5 * sigma  # Allowance

        s_pos = np.zeros(len(values))
        s_neg = np.zeros(len(values))
        detections = []

        for i in range(1, len(values)):
            s_pos[i] = max(0, s_pos[i-1] + (values[i] - mu) - k)
            s_neg[i] = max(0, s_neg[i-1] - (values[i] - mu) - k)
            if s_pos[i] > h or s_neg[i] > h:
                detections.append(i)
                s_pos[i] = 0
                s_neg[i] = 0

        first_detect = detections[0] if detections else len(values)
        return detections, first_detect

    def ewma_detect(values, lam=0.2, L=3.0):
        """EWMA control chart. Returns detection days."""
        if len(values) < 5:
            return [], float('nan')
        mu = np.mean(values[:min(7, len(values))])
        sigma = max(np.std(values[:min(7, len(values))]), 1e-6)

        z = np.zeros(len(values))
        z[0] = values[0]
        detections = []

        for i in range(1, len(values)):
            z[i] = lam * values[i] + (1 - lam) * z[i-1]
            # Control limit
            cl = L * sigma * np.sqrt(lam / (2 - lam) * (1 - (1-lam)**(2*(i+1))))
            if abs(z[i] - mu) > cl:
                detections.append(i)

        first_detect = detections[0] if detections else len(values)
        return detections, first_detect

    def sliding_ttest(values, window_size):
        """Sliding window t-test for change detection."""
        if len(values) < 2 * window_size:
            return [], float('nan')
        detections = []
        for i in range(window_size, len(values) - window_size + 1):
            left = values[i-window_size:i]
            right = values[i:i+window_size]
            if len(left) < 3 or len(right) < 3:
                continue
            t_stat, p_val = sp_stats.ttest_ind(left, right)
            if p_val < 0.05:
                detections.append(i)

        first_detect = detections[0] if detections else len(values)
        return detections, first_detect

    # Ground truth: linear regression slope significance on full data
    def ground_truth_drift(values):
        """Is there significant drift in the full series?"""
        if len(values) < 10:
            return False, 0.0, 1.0
        x = np.arange(len(values))
        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, values)
        return p_value < 0.05, float(slope), float(p_value)

    all_patient_results = {}

    for pid_path in patient_paths:
        pid = os.path.basename(os.path.dirname(pid_path))
        print(f"\n  Patient {pid}:")

        try:
            grid_df, features_np = _get_cached_grid(pid_path)
        except Exception as e:
            print(f"    SKIP: {e}")
            continue

        daily_isf, day_idx = compute_daily_isf(features_np)
        if len(daily_isf) < 14:
            print(f"    SKIP: only {len(daily_isf)} daily ISF values")
            continue

        # Remove extreme outliers (>3 sigma)
        mu, sigma = np.mean(daily_isf), np.std(daily_isf)
        mask = np.abs(daily_isf - mu) < 3 * sigma
        daily_isf = daily_isf[mask]
        day_idx = day_idx[mask]

        has_drift, slope, p_val = ground_truth_drift(daily_isf)
        print(f"    {len(daily_isf)} days, slope={slope:.3f}/day, p={p_val:.4f}, "
              f"drift={'YES' if has_drift else 'no'}")

        # Run all detection methods
        methods = {}

        # CUSUM at different thresholds
        for sigma_mult in [1.5, 2.0, 3.0]:
            detections, first = cusum_detect(daily_isf, threshold_sigma=sigma_mult)
            methods[f'cusum_{sigma_mult}σ'] = {
                'first_detect_day': int(first),
                'n_detections': len(detections),
            }

        # EWMA at different smoothing
        for lam in [0.1, 0.2, 0.3]:
            detections, first = ewma_detect(daily_isf, lam=lam)
            methods[f'ewma_λ{lam}'] = {
                'first_detect_day': int(first),
                'n_detections': len(detections),
            }

        # Sliding t-test at different windows
        for win_days in [3, 5, 7, 10, 14]:
            detections, first = sliding_ttest(daily_isf, window_size=win_days)
            methods[f'ttest_{win_days}d'] = {
                'first_detect_day': int(first),
                'n_detections': len(detections),
            }

        all_patient_results[pid] = {
            'n_days': len(daily_isf),
            'has_drift': has_drift,
            'slope': slope,
            'p_value': p_val,
            'methods': methods,
        }

        # Summary for this patient
        fastest = min((v['first_detect_day'], k) for k, v in methods.items())
        print(f"    Fastest detection: day {fastest[0]} ({fastest[1]})")

    # Aggregate: for patients WITH drift, how fast is each method?
    drift_patients = {k: v for k, v in all_patient_results.items() if v['has_drift']}
    no_drift_patients = {k: v for k, v in all_patient_results.items() if not v['has_drift']}

    print(f"\n{'='*60}")
    print(f"EXP-325: Change-Point Detection Summary")
    print(f"{'='*60}")
    print(f"Patients with ground-truth drift: {len(drift_patients)}/{len(all_patient_results)}")
    print(f"Patients without drift: {len(no_drift_patients)}/{len(all_patient_results)}")

    # Average first-detection day per method (for drift patients only)
    method_names = list(next(iter(all_patient_results.values()))['methods'].keys()) \
                   if all_patient_results else []

    method_summary = {}
    for method in method_names:
        detect_days = []
        false_alarms = 0
        for pid, pr in drift_patients.items():
            detect_days.append(pr['methods'][method]['first_detect_day'])
        for pid, pr in no_drift_patients.items():
            if pr['methods'][method]['first_detect_day'] < pr['n_days']:
                false_alarms += 1
        mean_detect = np.mean(detect_days) if detect_days else float('nan')
        method_summary[method] = {
            'mean_detect_day': float(mean_detect),
            'median_detect_day': float(np.median(detect_days)) if detect_days else float('nan'),
            'detected_fraction': float(np.mean([d < p['n_days'] for p, d in
                                                 zip(drift_patients.values(), detect_days)])) if detect_days else 0,
            'false_alarm_rate': float(false_alarms / max(1, len(no_drift_patients))),
        }

    print(f"\n{'Method':>15} {'MeanDay':>8} {'MedDay':>7} {'Detect%':>8} {'FA Rate':>8}")
    print("-" * 50)
    for method, ms in sorted(method_summary.items(), key=lambda x: x[1]['mean_detect_day']):
        print(f"{method:>15} {ms['mean_detect_day']:>8.1f} {ms['median_detect_day']:>7.1f} "
              f"{ms['detected_fraction']*100:>7.1f}% {ms['false_alarm_rate']*100:>7.1f}%")
    print(f"{'='*60}")
    print(f"  Biweekly baseline: 14.0 days (from EXP-312)")

    results = {
        'experiment': 'EXP-325',
        'name': 'cusum-isf-drift',
        'method': 'CUSUM, EWMA, and sliding t-test for ISF change-point detection',
        'per_patient': all_patient_results,
        'method_summary': method_summary,
        'n_drift_patients': len(drift_patients),
        'n_no_drift_patients': len(no_drift_patients),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    save_results(results, os.path.join(output_dir, 'exp325_cusum_drift.json'))
    return results


def run_leave_patient_out(args):
    """EXP-326: Leave-one-patient-out generalization for classification.

    Critical deployment question: do override/hypo models trained on N-1 patients
    generalize to an unseen patient?

    Method: For each of 11 patients, train multi-task CNN on 10 others, test on
    the held-out patient. Report per-patient F1 and compare to within-patient
    (trained-on-all) baseline from EXP-322.
    """
    patient_paths = resolve_patient_paths(args.patients_dir)
    output_dir = args.output_dir
    device = args.device
    epochs = args.epochs

    print("=" * 60)
    print("EXP-326: Leave-One-Patient-Out Classification Generalization")
    print("=" * 60)

    # Load per-patient data
    per_patient = {}
    for pp in patient_paths:
        pid = os.path.basename(os.path.dirname(pp))
        try:
            data = load_multiscale_data([pp], scale='fast', val_fraction=0.0)
            if isinstance(data, tuple):
                windows = data[0]
            else:
                windows = data
            per_patient[pid] = windows
            print(f"  Patient {pid}: {windows.shape}")
        except Exception as e:
            print(f"  Patient {pid}: SKIP ({e})")

    pids = sorted(per_patient.keys())
    print(f"\nLoaded {len(pids)} patients: {pids}")

    half = next(iter(per_patient.values())).shape[1] // 2

    def build_override_labels(windows, lead=3):
        future = windows[:, half:half + lead, 0] * 400.0
        high = (future > 180).any(axis=1)
        low = (future < 70).any(axis=1)
        labels = np.zeros(len(windows), dtype=np.int64)
        labels[high] = 1
        labels[low] = 2
        return labels

    def build_hypo_labels(windows, lead=6):
        future = windows[:, half:half + lead, 0] * 400.0
        return (future < 70).any(axis=1).astype(np.int64)

    class MultiTaskCNN(nn.Module):
        def __init__(self, in_channels=8):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv1d(in_channels, 32, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(32),
                nn.Conv1d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.Conv1d(64, 64, kernel_size=3, padding=1),
                nn.ReLU(), nn.BatchNorm1d(64),
                nn.AdaptiveAvgPool1d(1),
            )
            self.override_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 3),
            )
            self.hypo_head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(32, 2),
            )

        def forward(self, x):
            h = x.shape[1] // 2
            x = x[:, :h].permute(0, 2, 1)
            feat = self.backbone(x).squeeze(-1)
            return self.override_head(feat), self.hypo_head(feat)

    from sklearn.metrics import f1_score, roc_auc_score

    loo_results = {}
    batch_size = 256

    for hold_pid in pids:
        print(f"\n  Holding out patient {hold_pid}:")

        # Build train from all other patients
        train_windows = [per_patient[p] for p in pids if p != hold_pid]
        train_np = np.concatenate(train_windows, axis=0)
        test_np = per_patient[hold_pid]

        train_override = build_override_labels(train_np)
        test_override = build_override_labels(test_np)
        train_hypo = build_hypo_labels(train_np)
        test_hypo = build_hypo_labels(test_np)

        # Class weights from training data
        from collections import Counter
        ov_counts = Counter(train_override.tolist())
        n_total = len(train_override)
        ov_cw = torch.tensor([n_total / (3 * max(1, ov_counts.get(c, 1))) for c in range(3)],
                              dtype=torch.float32).to(device)
        n_pos = train_hypo.sum()
        n_neg = len(train_hypo) - n_pos
        hypo_weight = max(2.0, n_neg / max(1, n_pos))
        hypo_cw = torch.tensor([1.0, hypo_weight], dtype=torch.float32).to(device)

        model = MultiTaskCNN().to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        ov_criterion = nn.CrossEntropyLoss(weight=ov_cw)
        hypo_criterion = nn.CrossEntropyLoss(weight=hypo_cw)

        # Train
        train_t = torch.from_numpy(train_np).float()
        train_ov_t = torch.from_numpy(train_override).long()
        train_hypo_t = torch.from_numpy(train_hypo).long()

        for epoch in range(epochs):
            model.train()
            perm = torch.randperm(len(train_np))
            for start in range(0, len(perm), batch_size):
                end = min(start + batch_size, len(perm))
                idx = perm[start:end]
                ov_logits, hypo_logits = model(train_t[idx].to(device))
                loss = ov_criterion(ov_logits, train_ov_t[idx].to(device)) + \
                       hypo_criterion(hypo_logits, train_hypo_t[idx].to(device))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        # Evaluate on held-out patient
        model.eval()
        test_t = torch.from_numpy(test_np).float()
        all_ov_preds, all_hypo_probs = [], []
        with torch.no_grad():
            for vs in range(0, len(test_np), 512):
                ve = min(vs + 512, len(test_np))
                ov_logits, hypo_logits = model(test_t[vs:ve].to(device))
                all_ov_preds.append(ov_logits.argmax(dim=-1).cpu().numpy())
                all_hypo_probs.append(torch.softmax(hypo_logits, dim=-1)[:, 1].cpu().numpy())

        ov_preds = np.concatenate(all_ov_preds)
        hypo_probs = np.concatenate(all_hypo_probs)

        ov_f1 = f1_score(test_override, ov_preds, average='macro', zero_division=0)

        # Threshold sweep for hypo
        best_f1, best_thresh = 0.0, 0.5
        for thresh in np.arange(0.01, 1.0, 0.01):
            f1 = f1_score(test_hypo, (hypo_probs >= thresh).astype(int), zero_division=0)
            if f1 > best_f1:
                best_f1, best_thresh = f1, float(thresh)

        try:
            hypo_auc = roc_auc_score(test_hypo, hypo_probs)
        except ValueError:
            hypo_auc = float('nan')

        hypo_prev = test_hypo.mean()
        ov_prev = (test_override > 0).mean()

        loo_results[hold_pid] = {
            'n_test': len(test_np),
            'n_train': len(train_np),
            'override_f1': float(ov_f1),
            'hypo_f1': float(best_f1),
            'hypo_threshold': float(best_thresh),
            'hypo_auc': float(hypo_auc),
            'hypo_prevalence': float(hypo_prev),
            'override_prevalence': float(ov_prev),
        }
        print(f"    n={len(test_np)}, OV F1={ov_f1:.4f}, "
              f"Hypo F1={best_f1:.4f} @{best_thresh:.2f}, AUC={hypo_auc:.4f}")

    # Baselines from EXP-322 (trained on all, validated on 20% split)
    baseline_ov_f1 = 0.809
    baseline_hypo_f1 = 0.672

    mean_ov_f1 = np.mean([r['override_f1'] for r in loo_results.values()])
    mean_hypo_f1 = np.mean([r['hypo_f1'] for r in loo_results.values()])
    mean_hypo_auc = np.nanmean([r['hypo_auc'] for r in loo_results.values()])

    print(f"\n{'='*60}")
    print(f"EXP-326: Leave-One-Patient-Out Results")
    print(f"{'='*60}")
    print(f"{'Patient':>8} {'N':>6} {'OV F1':>7} {'Hypo F1':>8} {'Hypo AUC':>9} {'Hypo Prev':>10}")
    print("-" * 55)
    for pid in sorted(loo_results.keys()):
        r = loo_results[pid]
        print(f"{pid:>8} {r['n_test']:>6} {r['override_f1']:>7.4f} "
              f"{r['hypo_f1']:>8.4f} {r['hypo_auc']:>9.4f} {r['hypo_prevalence']:>10.3f}")
    print("-" * 55)
    print(f"{'LOO Mean':>8} {'':>6} {mean_ov_f1:>7.4f} {mean_hypo_f1:>8.4f} {mean_hypo_auc:>9.4f}")
    print(f"{'Baseline':>8} {'':>6} {baseline_ov_f1:>7.4f} {baseline_hypo_f1:>8.4f}")
    print(f"{'Δ':>8} {'':>6} {mean_ov_f1 - baseline_ov_f1:>+7.4f} "
          f"{mean_hypo_f1 - baseline_hypo_f1:>+8.4f}")
    print(f"{'='*60}")

    results = {
        'experiment': 'EXP-326',
        'name': 'leave-patient-out-classification',
        'method': 'LOO multi-task CNN for override + hypo generalization',
        'per_patient': loo_results,
        'summary': {
            'mean_override_f1': float(mean_ov_f1),
            'mean_hypo_f1': float(mean_hypo_f1),
            'mean_hypo_auc': float(mean_hypo_auc),
            'baseline_override_f1': baseline_ov_f1,
            'baseline_hypo_f1': baseline_hypo_f1,
            'delta_override': float(mean_ov_f1 - baseline_ov_f1),
            'delta_hypo': float(mean_hypo_f1 - baseline_hypo_f1),
        },
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    save_results(results, os.path.join(output_dir, 'exp326_loo_classification.json'))
    return results


# ── Registry & CLI ─────────────────────────────────────────────────────

EXPERIMENTS = {
    # Phase 15: Original 2h-scale experiments
    'ablation-embedding': ('EXP-287', run_ablation_embedding,
                           'Channel-group ablation for pattern embedding Recall@5'),
    'window-sweep-embedding': ('EXP-289', run_window_sweep_embedding,
                               'Window length sweep for pattern embedding'),
    'drift-segmentation': ('EXP-286', run_drift_segmentation,
                           'ISF-drift episode segmentation (11 vs 9 labels)'),
    'uam-detection': ('EXP-291', run_uam_detection,
                      'UAM detection via pattern embedding'),
    # Phase 18: Multi-scale re-runs at optimal timescales
    'ablation-12h': ('EXP-298', run_ablation_12h,
                     'Channel ablation at 12h — feature importance at full DIA'),
    'uam-12h': ('EXP-299', run_uam_12h,
                'UAM detection at 12h — precision vs 2h baseline'),
    'drift-daily': ('EXP-300', run_daily_drift,
                    'Drift segmentation at 24h/15-min resolution'),
    'weekly-isf': ('EXP-301', run_weekly_isf,
                   'Weekly ISF trends (7-day @ 1-hr embeddings)'),
    # Phase 21-23: Cross-scale integration
    'cross-scale': ('EXP-304', run_cross_scale_retrieval,
                    'Cross-scale retrieval (fast+episode+weekly → 96d)'),
    'multiscale-override': ('EXP-305', run_multiscale_override,
                            'Multi-scale override recommendation (106d input)'),
    # Phase 25: ISF drift detection
    'indirect-drift': ('EXP-306', run_indirect_drift_detection,
                       'Indirect ISF drift via pattern-similarity outcome comparison'),
    'per-patient-drift': ('EXP-307', run_per_patient_drift,
                          'Per-patient temporal ISF drift (early vs late matching)'),
    'insulin-drift': ('EXP-308', run_insulin_controlled_drift,
                      'Insulin-controlled drift (treatment-context matching)'),
    # Phase 26: ISF response ratio, generalization, temporal override
    'isf-response-ratio': ('EXP-309', run_isf_response_ratio,
                           'Direct ISF measurement via glucose/insulin response ratio'),
    'leave-patient-out': ('EXP-310', run_leave_patient_out_retrieval,
                          'Leave-one-patient-out weekly retrieval (generalization)'),
    'temporal-override': ('EXP-311', run_temporal_override,
                          '1D-CNN temporal model vs static state for override prediction'),
    # Phase 27: Rolling ISF aggregation, CNN UAM
    'rolling-isf': ('EXP-312', run_rolling_isf,
                    'Rolling weekly ISF aggregation for drift detection'),
    'cnn-uam': ('EXP-313', run_cnn_uam,
                '1D-CNN for UAM detection vs embedding baseline'),
    # Phase 28: Multi-lead override, dedicated hypo prediction
    'multi-lead-override': ('EXP-314', run_multi_lead_override,
                            'Multi-lead-time override prediction (15/30/60 min)'),
    'hypo-cnn': ('EXP-315', run_hypo_cnn,
                 'Dedicated CNN for hypo prediction at multiple thresholds'),
    'isf-feature': ('EXP-316', run_isf_as_feature,
                    'ISF trend as downstream feature for override/UAM CNN'),
    # Phase 29: Threshold optimization, per-patient fine-tuning
    'hypo-threshold': ('EXP-317', run_hypo_threshold_opt,
                       'Probability threshold optimization for hypo CNN'),
    'per-patient-override': ('EXP-318', run_per_patient_override,
                             'Per-patient fine-tuning for override CNN'),
    # Phase 30: Selective ensemble, IOB trajectory features
    'selective-ensemble': ('EXP-319', run_selective_ensemble,
                           'Selective per-patient override ensemble'),
    'iob-hypo': ('EXP-320', run_iob_hypo,
                 'IOB trajectory features for hypo prediction CNN'),
    # Phase 31: Loss function and multi-task
    'focal-hypo': ('EXP-321', run_focal_hypo,
                   'Focal loss for hypo prediction CNN'),
    'multitask-cnn': ('EXP-322', run_multitask_cnn,
                      'Multi-task override+hypo CNN with shared backbone'),
    # Phase 32: Combined optimization and calibration
    'multitask-focal': ('EXP-323', run_multitask_focal,
                        'Multi-task CNN + focal loss for hypo head'),
    'calibration': ('EXP-324', run_calibration_analysis,
                    'Temperature scaling and Platt calibration for hypo CNN'),
    # Phase 33: Generalization and online drift detection
    'cusum-drift': ('EXP-325', run_cusum_isf_drift,
                    'CUSUM/EWMA/sliding-ttest change-point detection for ISF drift'),
    'loo-classification': ('EXP-326', run_leave_patient_out,
                           'Leave-one-patient-out multi-task CNN generalization'),
}


def main():
    parser = argparse.ArgumentParser(
        description='Run pattern pipeline experiments (EXP-286+)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('experiment', nargs='?', default=None,
                        choices=list(EXPERIMENTS.keys()),
                        help='Which experiment to run')
    parser.add_argument('--list', action='store_true',
                        help='List available experiments')
    parser.add_argument('--patients-dir', default='externals/ns-data/patients',
                        help='Patient data directory')
    parser.add_argument('--output-dir', default='externals/experiments',
                        help='Output directory for results (gitignored)')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu',
                        help='Torch device (cpu/cuda/mps)')
    parser.add_argument('--epochs', type=int, default=30,
                        help='Training epochs per model')

    args = parser.parse_args()

    if args.list or args.experiment is None:
        print("Available pattern experiments:")
        for name, (exp_id, _, desc) in sorted(EXPERIMENTS.items()):
            print(f"  {name:30s} {exp_id}  {desc}")
        return

    exp_id, func, desc = EXPERIMENTS[args.experiment]
    print(f"\nRunning {exp_id}: {desc}")
    print(f"  patients: {args.patients_dir}")
    print(f"  output:   {args.output_dir}")
    print(f"  device:   {args.device}")
    print(f"  epochs:   {args.epochs}")
    print()

    os.makedirs(args.output_dir, exist_ok=True)
    t0 = time.time()
    result = func(args)
    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s")


if __name__ == '__main__':
    main()
