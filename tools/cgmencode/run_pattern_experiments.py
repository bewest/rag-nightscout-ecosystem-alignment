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
    from .real_data_adapter import build_nightscout_grid, downsample_grid

    SCALE_CONFIG = {
        'fast':    {'window': 24,  'interval_min': 5,  'stride': None},
        'episode': {'window': 144, 'interval_min': 5,  'stride': None},
        'daily':   {'window': 96,  'interval_min': 15, 'stride': 1},
        'weekly':  {'window': 168, 'interval_min': 60, 'stride': 1},
    }

    cfg = SCALE_CONFIG[scale]
    window = cfg['window']
    interval = cfg['interval_min']
    stride = cfg['stride'] or window // 2

    all_windows = []
    for i, path in enumerate(patient_paths):
        patient_id = os.path.basename(os.path.dirname(path))
        print(f"  Patient {patient_id} ({i+1}/{len(patient_paths)}): {path}")

        df, features = build_nightscout_grid(path, verbose=False)
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
