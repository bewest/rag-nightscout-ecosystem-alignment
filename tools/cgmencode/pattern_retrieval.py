"""Pattern Retrieval & Lead-Time Prediction Pipeline.

Provides episode-level segmentation (per-timestep labeling) and retrieval-based
lead-time prediction. Given a partial glucose window, finds similar completed
historical episodes and estimates time remaining until a clinically significant
event (hypo, spike, etc.).

Optimization targets: Segment F1, Lead Time MAE (minutes), Actionable Rate.

Usage:
    from tools.cgmencode.pattern_retrieval import (
        EpisodeSegmenter, build_episode_labels, EPISODE_LABELS,
        LeadTimePredictor, predict_lead_time, evaluate_lead_time,
    )
"""
import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ── Episode labels for per-timestep segmentation ────────────────────────

EPISODE_LABELS = [
    'stable',             # 0: glucose in range, low variability
    'rising',             # 1: glucose increasing > 1 mg/dL/min
    'falling',            # 2: glucose decreasing > 1 mg/dL/min
    'meal_response',      # 3: post-meal spike (carbs in recent history)
    'exercise_response',  # 4: exercise-induced drop (low IOB, rapid fall)
    'dawn_phenomenon',    # 5: early morning rise (03:00–08:00)
    'rebound',            # 6: rapid rise after hypo event
    'hypo_risk',          # 7: glucose < 80 or rapidly approaching 70
    'correction_response',# 8: glucose falling after correction bolus
    'sensitivity_shift',  # 9: autosens ratio > 1.1 (body more sensitive)
    'resistance_shift',   # 10: autosens ratio < 0.9 (body more resistant)
]
LABEL_TO_IDX = {label: i for i, label in enumerate(EPISODE_LABELS)}
N_EPISODE_LABELS = len(EPISODE_LABELS)

# Glucose thresholds (mg/dL, pre-normalization)
_HYPO_THRESHOLD = 80.0
_RISING_RATE = 1.0     # mg/dL per minute (5 mg/dL per 5-min step)
_FALLING_RATE = -1.0


# ── Episode label generation from heuristics ────────────────────────────

def build_episode_labels(glucose_mgdl: np.ndarray, iob: np.ndarray,
                         cob: np.ndarray, bolus: np.ndarray,
                         carbs: np.ndarray, time_hours: np.ndarray,
                         interval_min: float = 5.0,
                         autosens_ratio: Optional[np.ndarray] = None,
                         ) -> np.ndarray:
    """Generate per-timestep episode labels from raw signals.

    Applies a priority-based heuristic: more specific labels override generic ones.

    Args:
        glucose_mgdl: (T,) glucose in mg/dL
        iob: (T,) insulin on board
        cob: (T,) carbs on board
        bolus: (T,) bolus events (units)
        carbs: (T,) carb events (grams)
        time_hours: (T,) hour of day [0, 24)
        interval_min: grid interval in minutes
        autosens_ratio: (T,) optional autosens ratio [0.7-1.2].
            If provided, sensitivity_shift (>1.1) and resistance_shift (<0.9)
            labels are applied as low-priority background episodes.

    Returns:
        labels: (T,) integer labels indexing EPISODE_LABELS
    """
    T = len(glucose_mgdl)
    labels = np.zeros(T, dtype=np.int64)  # default: stable

    # Rate of change (mg/dL per minute)
    roc = np.zeros(T)
    roc[1:] = (glucose_mgdl[1:] - glucose_mgdl[:-1]) / interval_min

    # Recent carbs (30 min lookback = 6 steps at 5-min interval)
    lookback = int(30 / interval_min)
    recent_carbs = np.zeros(T)
    for t in range(T):
        start = max(0, t - lookback)
        recent_carbs[t] = np.sum(carbs[start:t + 1])

    # Recent bolus (30 min lookback)
    recent_bolus = np.zeros(T)
    for t in range(T):
        start = max(0, t - lookback)
        recent_bolus[t] = np.sum(bolus[start:t + 1])

    for t in range(T):
        g = glucose_mgdl[t]
        r = roc[t]
        h = time_hours[t] if not np.isnan(time_hours[t]) else 12.0

        # Priority ordering: most specific first

        # Hypo risk: glucose near or below threshold
        if g < _HYPO_THRESHOLD or (g < 90 and r < _FALLING_RATE):
            labels[t] = LABEL_TO_IDX['hypo_risk']
            continue

        # Rebound: rising from hypo (previous was hypo_risk AND rising)
        if t > 0 and labels[t - 1] == LABEL_TO_IDX['hypo_risk'] and r > _RISING_RATE:
            labels[t] = LABEL_TO_IDX['rebound']
            continue

        # Meal response: rising with recent carbs
        if recent_carbs[t] > 1.0 and r > 0.3:
            labels[t] = LABEL_TO_IDX['meal_response']
            continue

        # Correction response: falling after recent bolus, no carbs
        if recent_bolus[t] > 0.1 and recent_carbs[t] < 1.0 and r < -0.3:
            labels[t] = LABEL_TO_IDX['correction_response']
            continue

        # Dawn phenomenon: early morning rise, low IOB
        if 3 <= h <= 8 and r > 0.3 and iob[t] < 1.5:
            labels[t] = LABEL_TO_IDX['dawn_phenomenon']
            continue

        # Exercise response: rapid fall, low IOB, no recent carbs
        if r < _FALLING_RATE and iob[t] < 2.0 and recent_carbs[t] < 1.0:
            labels[t] = LABEL_TO_IDX['exercise_response']
            continue

        # Generic rising/falling
        if r > _RISING_RATE:
            labels[t] = LABEL_TO_IDX['rising']
        elif r < _FALLING_RATE:
            labels[t] = LABEL_TO_IDX['falling']
        # else: stays 'stable' (default)

    # Low-priority overlay: ISF drift labels (only override 'stable')
    if autosens_ratio is not None:
        _SENSITIVITY_THRESH = 1.1   # matches oref0/AAPS/Trio autosens bounds
        _RESISTANCE_THRESH = 0.9
        for t in range(T):
            if labels[t] != LABEL_TO_IDX['stable']:
                continue  # don't override specific episode labels
            ratio = autosens_ratio[t]
            if np.isnan(ratio):
                continue
            if ratio > _SENSITIVITY_THRESH:
                labels[t] = LABEL_TO_IDX['sensitivity_shift']
            elif ratio < _RESISTANCE_THRESH:
                labels[t] = LABEL_TO_IDX['resistance_shift']

    return labels


def build_episode_labels_from_tensor(features: np.ndarray,
                                     glucose_scale: float = 400.0,
                                     interval_min: float = 5.0) -> np.ndarray:
    """Build episode labels from a normalized feature tensor.

    Convenience wrapper that extracts channels and denormalizes.

    Args:
        features: (T, F) normalized feature array (F ≥ 8)
        glucose_scale: normalization scale for channel 0
        interval_min: grid interval

    Returns:
        labels: (T,) integer episode labels
    """
    from .schema import (IDX_GLUCOSE, IDX_IOB, IDX_COB, IDX_BOLUS,
                         IDX_CARBS, IDX_TIME_SIN, IDX_TIME_COS)

    glucose_mgdl = features[:, IDX_GLUCOSE] * glucose_scale
    iob = features[:, IDX_IOB] * 20.0  # IOB normalization scale
    cob = features[:, IDX_COB] * 200.0  # COB normalization scale
    bolus = features[:, IDX_BOLUS] * 10.0
    carbs = features[:, IDX_CARBS] * 200.0

    # Recover hour from sin/cos encoding
    time_sin = features[:, IDX_TIME_SIN]
    time_cos = features[:, IDX_TIME_COS]
    time_hours = (np.arctan2(time_sin, time_cos) / (2 * np.pi) * 24.0) % 24.0

    return build_episode_labels(glucose_mgdl, iob, cob, bolus, carbs,
                                time_hours, interval_min)


# ── Episode Segmenter Model ────────────────────────────────────────────

class EpisodeSegmenter(nn.Module):
    """Per-timestep episode classification using a Transformer encoder.

    Architecture:
        Linear(input_dim → d_model) → PositionalEncoding → TransformerEncoder
        → Linear(d_model → n_labels) per timestep

    Output is (B, T, n_labels) logits for per-timestep classification.
    """

    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 2, dim_feedforward: int = 128,
                 dropout: float = 0.1, n_labels: int = N_EPISODE_LABELS):
        super().__init__()
        self.input_dim = input_dim
        self.n_labels = n_labels

        self.input_projection = nn.Linear(input_dim, d_model)

        self.register_buffer('pe', self._build_pe(d_model, max_len=512))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead,
            dim_feedforward=dim_feedforward, dropout=dropout,
            batch_first=True, norm_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers,
        )

        self.classifier = nn.Linear(d_model, n_labels)

    @staticmethod
    def _build_pe(d_model: int, max_len: int = 512) -> torch.Tensor:
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return pe.unsqueeze(0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Predict per-timestep episode labels.

        Args:
            x: (B, T, input_dim)

        Returns:
            logits: (B, T, n_labels)
        """
        h = self.input_projection(x)
        h = h + self.pe[:, :h.size(1), :]
        h = self.transformer_encoder(h)
        return self.classifier(h)

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """Return predicted label indices (argmax)."""
        logits = self.forward(x)
        return logits.argmax(dim=-1)


def train_episode_segmenter(
    model: EpisodeSegmenter,
    train_windows: np.ndarray,
    train_labels: np.ndarray,
    val_windows: np.ndarray,
    val_labels: np.ndarray,
    save_path: str,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    patience: int = 10,
    device: str = 'cpu',
    class_weights: Optional[np.ndarray] = None,
) -> Dict:
    """Train per-timestep episode segmenter.

    Args:
        train_windows: (N, T, F) feature arrays
        train_labels: (N, T) integer labels
        val_windows, val_labels: validation set
        save_path: checkpoint path
        class_weights: optional (n_labels,) weights for imbalanced labels

    Returns:
        dict with best_segment_f1, best_epoch, epochs_run
    """
    model = model.to(device)

    if class_weights is not None:
        weight = torch.from_numpy(class_weights).float().to(device)
    else:
        weight = None

    criterion = nn.CrossEntropyLoss(weight=weight, ignore_index=-1)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    train_x = torch.from_numpy(train_windows).float()
    train_y = torch.from_numpy(train_labels).long()
    val_x = torch.from_numpy(val_windows).float()
    val_y = torch.from_numpy(val_labels).long()

    best_f1 = 0.0
    best_epoch = 0
    epochs_no_improve = 0

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0

        # Shuffle
        perm = torch.randperm(len(train_x))
        for start in range(0, len(train_x), batch_size):
            idx = perm[start:start + batch_size]
            x_batch = train_x[idx].to(device)
            y_batch = train_y[idx].to(device)

            logits = model(x_batch)  # (B, T, n_labels)
            loss = criterion(logits.reshape(-1, model.n_labels), y_batch.reshape(-1))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        # Validate
        model.eval()
        with torch.no_grad():
            val_logits = []
            for start in range(0, len(val_x), batch_size):
                vx = val_x[start:start + batch_size].to(device)
                vl = model(vx)
                val_logits.append(vl.cpu())
            val_logits = torch.cat(val_logits, dim=0)
            val_preds = val_logits.argmax(dim=-1).numpy()

        f1 = _segment_f1(val_y.numpy(), val_preds)

        if f1 > best_f1:
            best_f1 = f1
            best_epoch = epoch
            epochs_no_improve = 0
            torch.save({
                'model_state': model.state_dict(),
                'epoch': epoch,
                'segment_f1': f1,
            }, save_path)
        else:
            epochs_no_improve += 1

        if epochs_no_improve >= patience:
            break

    return {
        'best_segment_f1': best_f1,
        'best_epoch': best_epoch,
        'epochs_run': epoch + 1,
    }


def _segment_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute macro-averaged F1 across episode labels (excluding 'stable')."""
    # Flatten: (N, T) → (N*T,)
    yt = y_true.flatten()
    yp = y_pred.flatten()

    # Compute per-class F1, skip stable (class 0) and average
    f1_scores = []
    for c in range(1, N_EPISODE_LABELS):
        tp = np.sum((yp == c) & (yt == c))
        fp = np.sum((yp == c) & (yt != c))
        fn = np.sum((yp != c) & (yt == c))
        if tp + fp + fn == 0:
            continue
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall > 0:
            f1_scores.append(2 * precision * recall / (precision + recall))

    return float(np.mean(f1_scores)) if f1_scores else 0.0


# ── Lead-Time Prediction ───────────────────────────────────────────────

class LeadTimePredictor:
    """Retrieval-based lead-time prediction.

    Given a current partial window, finds similar completed historical episodes
    and estimates time remaining until a clinically significant event based on
    how long those similar episodes took to reach the event.

    Requires:
        - A trained PatternEncoder for embedding similarity
        - A PatternLibrary with indexed historical episodes
        - Episode metadata including event timestamps and durations
    """

    def __init__(self, encoder, pattern_library, device: str = 'cpu'):
        """
        Args:
            encoder: trained PatternEncoder
            pattern_library: built PatternLibrary with metadata containing
                             'episode_duration_min' and 'event_type' keys
            device: torch device for encoding
        """
        self.encoder = encoder
        self.library = pattern_library
        self.device = device

    def predict(self, window: np.ndarray, top_k: int = 5,
                min_similarity: float = 0.3) -> Dict:
        """Predict lead time for a partial window.

        Args:
            window: (T, F) current glucose window (may be partial episode)
            top_k: number of similar episodes to average
            min_similarity: minimum cosine similarity to consider

        Returns:
            dict with:
                predicted_lead_time_min: float
                confidence: float (mean similarity of matches)
                matched_pattern_type: str
                similar_episodes: list of match dicts
        """
        self.encoder.eval()
        with torch.no_grad():
            x = torch.from_numpy(window).float().unsqueeze(0).to(self.device)
            embedding = self.encoder.encode(x).cpu().numpy()[0]

        matches = self.library.match(embedding, top_k=top_k)

        # Filter by minimum similarity
        matches = [m for m in matches if m['similarity'] >= min_similarity]

        if not matches:
            return {
                'predicted_lead_time_min': float('nan'),
                'confidence': 0.0,
                'matched_pattern_type': 'unknown',
                'similar_episodes': [],
            }

        # Extract durations from metadata
        durations = []
        weights = []
        for m in matches:
            meta = m.get('metadata', {})
            dur = meta.get('episode_duration_min', None)
            if dur is not None:
                durations.append(dur)
                weights.append(m['similarity'])

        if not durations:
            # No duration metadata — fall back to pattern type
            pattern_type, conf = self.library.classify(embedding)
            return {
                'predicted_lead_time_min': float('nan'),
                'confidence': float(conf),
                'matched_pattern_type': pattern_type,
                'similar_episodes': matches,
            }

        # Weighted average of durations
        weights = np.array(weights)
        durations = np.array(durations)
        weights = weights / weights.sum()
        predicted = float(np.dot(weights, durations))

        # Confidence: mean similarity of matches with duration
        confidence = float(np.mean([m['similarity'] for m in matches]))

        # Majority vote for pattern type
        types = [m.get('metadata', {}).get('event_type', m['label'])
                 for m in matches]
        type_counts = Counter(types)
        matched_type = type_counts.most_common(1)[0][0]

        return {
            'predicted_lead_time_min': predicted,
            'confidence': confidence,
            'matched_pattern_type': matched_type,
            'similar_episodes': matches,
        }


def predict_lead_time(encoder, pattern_library, current_window: np.ndarray,
                      device: str = 'cpu', top_k: int = 5,
                      min_similarity: float = 0.3) -> Dict:
    """Convenience function wrapping LeadTimePredictor."""
    predictor = LeadTimePredictor(encoder, pattern_library, device=device)
    return predictor.predict(current_window, top_k=top_k,
                             min_similarity=min_similarity)


def evaluate_lead_time(predictor: LeadTimePredictor,
                       test_windows: np.ndarray,
                       test_metadata: List[Dict],
                       horizons: List[int] = None) -> Dict:
    """Evaluate lead-time prediction quality.

    For each test window, predicts lead time and compares to actual.

    Args:
        predictor: trained LeadTimePredictor
        test_windows: (N, T, F) completed episode windows
        test_metadata: list of N dicts with 'episode_duration_min' and 'event_type'
        horizons: evaluation horizons in minutes (default [15, 30, 60, 120])

    Returns:
        dict with per-horizon metrics: lead_time_mae, actionable_rate, coverage
    """
    if horizons is None:
        horizons = [15, 30, 60, 120]

    results = {}
    predictions = []

    for i in range(len(test_windows)):
        pred = predictor.predict(test_windows[i])
        actual_dur = test_metadata[i].get('episode_duration_min', float('nan'))
        predictions.append({
            'predicted': pred['predicted_lead_time_min'],
            'actual': actual_dur,
            'confidence': pred['confidence'],
            'pattern_type': pred['matched_pattern_type'],
        })

    # Per-horizon metrics
    for h in horizons:
        valid = [p for p in predictions
                 if not np.isnan(p['predicted']) and not np.isnan(p['actual'])]

        if not valid:
            results[f'{h}min'] = {
                'lead_time_mae_min': float('nan'),
                'actionable_rate': 0.0,
                'coverage': 0.0,
            }
            continue

        errors = [abs(p['predicted'] - p['actual']) for p in valid]
        actionable = sum(1 for p in valid if p['predicted'] >= h) / len(valid)
        coverage = len(valid) / len(predictions) if predictions else 0.0

        results[f'{h}min'] = {
            'lead_time_mae_min': float(np.mean(errors)),
            'actionable_rate': actionable,
            'coverage': coverage,
        }

    results['n_predictions'] = len(predictions)
    results['n_valid'] = len([p for p in predictions
                              if not np.isnan(p['predicted'])])

    return results
