"""Pattern-Triggered Override Pipeline.

Maps detected patterns directly to override recommendations WITHOUT requiring
intermediate glucose forecasting. Uses pattern embeddings + current state to
learn a policy that recommends override type and strength.

Optimization targets: TIR Delta, Hypo Safety Rate, Precision@1.

Usage:
    from tools.cgmencode.pattern_override import (
        PatternOverridePolicy, build_override_outcome_dataset,
        train_pattern_override_policy, PatternTriggeredRecommender,
        evaluate_pattern_overrides,
    )
"""
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .schema import OVERRIDE_TYPES


# ── Constants ───────────────────────────────────────────────────────────

N_OVERRIDE_TYPES = len(OVERRIDE_TYPES)  # eating_soon, exercise, sleep, sick, custom
OVERRIDE_STRENGTHS = [0.5, 0.75, 1.0, 1.25, 1.5]
N_STRENGTHS = len(OVERRIDE_STRENGTHS)

# TIR thresholds (mg/dL)
TIR_LOW = 70.0
TIR_HIGH = 180.0

# Safety thresholds
HYPO_RISK_THRESHOLD = 0.3  # P(hypo) above this blocks recommendation


# ── Policy Network ──────────────────────────────────────────────────────

class PatternOverridePolicy(nn.Module):
    """MLP policy that maps pattern embedding + glucose state to override
    recommendations.

    Inputs:
        - pattern_embedding: (B, embed_dim) from PatternEncoder
        - glucose_state: (B, state_dim) current glucose metrics
          (current_glucose, glucose_roc, iob, cob, time_sin, time_cos,
           recent_variability, hypo_risk)

    Outputs:
        - type_logits: (B, N_OVERRIDE_TYPES) override type probabilities
        - strength: (B, 1) predicted optimal strength multiplier
        - tir_delta: (B, 1) predicted TIR improvement
    """

    def __init__(self, embed_dim: int = 64, state_dim: int = 8,
                 hidden_dim: int = 128, n_override_types: int = N_OVERRIDE_TYPES):
        super().__init__()
        self.embed_dim = embed_dim
        self.state_dim = state_dim

        input_dim = embed_dim + state_dim

        self.shared = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
        )

        # Type head: which override?
        self.type_head = nn.Linear(hidden_dim, n_override_types)

        # Strength head: how strong? (sigmoid → [0, 2] range)
        self.strength_head = nn.Linear(hidden_dim, 1)

        # Value head: predicted TIR delta
        self.value_head = nn.Linear(hidden_dim, 1)

    def forward(self, embedding: torch.Tensor, state: torch.Tensor
                ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            embedding: (B, embed_dim) pattern embedding
            state: (B, state_dim) glucose state features

        Returns:
            type_logits: (B, N_OVERRIDE_TYPES)
            strength: (B, 1) in [0, 2] range
            tir_delta: (B, 1) predicted TIR improvement
        """
        x = torch.cat([embedding, state], dim=-1)
        h = self.shared(x)

        type_logits = self.type_head(h)
        strength = torch.sigmoid(self.strength_head(h)) * 2.0
        tir_delta = self.value_head(h)

        return type_logits, strength, tir_delta

    def recommend(self, embedding: torch.Tensor, state: torch.Tensor
                  ) -> Dict[str, float]:
        """Get a single recommendation (inference mode).

        Returns dict with override_type, strength, predicted_tir_delta, confidence.
        """
        self.eval()
        with torch.no_grad():
            type_logits, strength, tir_delta = self.forward(embedding, state)

        probs = F.softmax(type_logits, dim=-1)[0]
        type_idx = probs.argmax().item()
        override_types = list(OVERRIDE_TYPES.keys()) if isinstance(OVERRIDE_TYPES, dict) else OVERRIDE_TYPES

        return {
            'override_type': override_types[type_idx] if type_idx < len(override_types) else 'custom',
            'type_confidence': float(probs[type_idx]),
            'strength': float(strength[0, 0]),
            'predicted_tir_delta': float(tir_delta[0, 0]),
            'type_probabilities': {
                override_types[i] if i < len(override_types) else f'type_{i}': float(probs[i])
                for i in range(len(probs))
            },
        }


# ── Dataset Construction ────────────────────────────────────────────────

def _compute_tir(glucose_mgdl: np.ndarray) -> float:
    """Compute time-in-range (70-180 mg/dL) fraction."""
    valid = glucose_mgdl[~np.isnan(glucose_mgdl)]
    if len(valid) == 0:
        return 0.0
    in_range = np.sum((valid >= TIR_LOW) & (valid <= TIR_HIGH))
    return float(in_range / len(valid))


def extract_glucose_state(window: np.ndarray, glucose_scale: float = 400.0
                          ) -> np.ndarray:
    """Extract glucose state features from the most recent timestep of a window.

    Returns (8,) array: [glucose_norm, roc, iob, cob, time_sin, time_cos,
                         variability, hypo_risk_proxy]
    """
    if len(window.shape) == 1:
        window = window.reshape(1, -1)

    last = window[-1]
    glucose = last[0]
    iob = last[1]
    cob = last[2]
    time_sin = last[6] if window.shape[1] > 6 else 0.0
    time_cos = last[7] if window.shape[1] > 7 else 0.0

    # Rate of change from last 3 steps
    if len(window) >= 3:
        roc = (window[-1, 0] - window[-3, 0]) / 2.0
    elif len(window) >= 2:
        roc = window[-1, 0] - window[-2, 0]
    else:
        roc = 0.0

    # Variability: std of glucose in window
    variability = float(np.std(window[:, 0])) if len(window) > 1 else 0.0

    # Hypo risk proxy: how close to threshold
    glucose_mgdl = glucose * glucose_scale
    hypo_risk = max(0.0, (80.0 - glucose_mgdl) / 80.0)

    return np.array([glucose, roc, iob, cob, time_sin, time_cos,
                     variability, hypo_risk], dtype=np.float32)


def build_override_outcome_dataset(
    windows: np.ndarray,
    labels: List[List[str]],
    embeddings: np.ndarray,
    glucose_scale: float = 400.0,
    override_channel: int = 10,
    future_start: Optional[int] = None,
    include_counterfactual: bool = True,
    tir_improvement_threshold: float = 0.02,
) -> Dict[str, np.ndarray]:
    """Build training dataset for the override policy.

    For each window where an override was historically applied, records
    the outcome (TIR delta). Also mines "missed opportunities" where
    no override was applied but TIR degraded significantly.

    Args:
        windows: (N, T, F) normalized feature arrays
        labels: list of N label lists from classify_window()
        embeddings: (N, embed_dim) precomputed pattern embeddings
        glucose_scale: denormalization scale for glucose
        override_channel: channel index for override_active flag
        future_start: timestep where future begins (default: T//2)
        include_counterfactual: if True, adds "missed opportunity" samples
        tir_improvement_threshold: min TIR delta to count as beneficial

    Returns:
        dict with keys: embeddings, states, override_types, strengths,
        tir_deltas, is_counterfactual (boolean mask)
    """
    N, T, F = windows.shape
    if future_start is None:
        future_start = T // 2

    result_embeddings = []
    result_states = []
    result_types = []
    result_strengths = []
    result_tir_deltas = []
    result_counterfactual = []

    for i in range(N):
        history = windows[i, :future_start]
        future = windows[i, future_start:]

        state = extract_glucose_state(history, glucose_scale)

        # Check if override was active in this window
        has_override = False
        if F > override_channel:
            has_override = float(np.max(windows[i, :, override_channel])) > 0.5

        # Compute future TIR
        future_glucose = future[:, 0] * glucose_scale
        future_tir = _compute_tir(future_glucose)

        # History TIR as baseline
        history_glucose = history[:, 0] * glucose_scale
        history_tir = _compute_tir(history_glucose)

        tir_delta = future_tir - history_tir

        if has_override:
            # Real override sample
            override_type_val = 0
            if F > override_channel + 1:
                override_type_val = int(np.round(
                    float(np.max(windows[i, :, override_channel + 1])) * N_OVERRIDE_TYPES
                ))
                override_type_val = min(override_type_val, N_OVERRIDE_TYPES - 1)

            result_embeddings.append(embeddings[i])
            result_states.append(state)
            result_types.append(override_type_val)
            result_strengths.append(1.0)
            result_tir_deltas.append(tir_delta)
            result_counterfactual.append(False)

        elif include_counterfactual and tir_delta < -tir_improvement_threshold:
            # Missed opportunity: TIR degraded without override
            # Label as "should have used override" — type unknown, assign based on pattern
            primary = labels[i][0] if labels[i] else 'other'
            suggested_type = _suggest_override_for_pattern(primary)

            result_embeddings.append(embeddings[i])
            result_states.append(state)
            result_types.append(suggested_type)
            result_strengths.append(1.0)
            result_tir_deltas.append(tir_delta)
            result_counterfactual.append(True)

    if not result_embeddings:
        empty = np.zeros((0, embeddings.shape[1]))
        return {
            'embeddings': empty,
            'states': np.zeros((0, 8)),
            'override_types': np.zeros(0, dtype=np.int64),
            'strengths': np.zeros(0),
            'tir_deltas': np.zeros(0),
            'is_counterfactual': np.zeros(0, dtype=bool),
        }

    return {
        'embeddings': np.stack(result_embeddings),
        'states': np.stack(result_states),
        'override_types': np.array(result_types, dtype=np.int64),
        'strengths': np.array(result_strengths, dtype=np.float32),
        'tir_deltas': np.array(result_tir_deltas, dtype=np.float32),
        'is_counterfactual': np.array(result_counterfactual, dtype=bool),
    }


def _suggest_override_for_pattern(pattern_label: str) -> int:
    """Heuristic: map pattern type to suggested override type index."""
    mapping = {
        'meal_bolus': 0,       # eating_soon
        'meal_no_bolus': 0,    # eating_soon
        'exercise_candidate': 1,  # exercise
        'nocturnal': 2,        # sleep
        'dawn': 2,             # sleep (basal adjustment)
        'high_volatility': 4,  # custom
        'uam': 0,              # eating_soon (unknown meal)
    }
    return mapping.get(pattern_label, 4)  # default: custom


# ── Training ────────────────────────────────────────────────────────────

def train_pattern_override_policy(
    policy: PatternOverridePolicy,
    train_data: Dict[str, np.ndarray],
    val_data: Dict[str, np.ndarray],
    save_path: str,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    type_weight: float = 1.0,
    strength_weight: float = 0.5,
    value_weight: float = 1.0,
    patience: int = 10,
    device: str = 'cpu',
) -> Dict:
    """Train override policy on outcome data.

    Loss = type_weight * CE(type) + strength_weight * MSE(strength)
           + value_weight * MSE(tir_delta)

    Returns dict with best metrics and training info.
    """
    policy = policy.to(device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)

    ce_loss = nn.CrossEntropyLoss()
    mse_loss = nn.MSELoss()

    def _to_tensors(data):
        return {
            'embeddings': torch.from_numpy(data['embeddings']).float(),
            'states': torch.from_numpy(data['states']).float(),
            'override_types': torch.from_numpy(data['override_types']).long(),
            'strengths': torch.from_numpy(data['strengths']).float(),
            'tir_deltas': torch.from_numpy(data['tir_deltas']).float(),
        }

    train_t = _to_tensors(train_data)
    val_t = _to_tensors(val_data)
    n_train = len(train_t['embeddings'])
    n_val = len(val_t['embeddings'])

    if n_train == 0:
        return {'error': 'empty_training_data', 'epochs_run': 0}

    best_val_loss = float('inf')
    best_epoch = 0
    epochs_no_improve = 0

    for epoch in range(epochs):
        policy.train()
        perm = torch.randperm(n_train)
        total_loss = 0.0
        n_batches = 0

        for start in range(0, n_train, batch_size):
            idx = perm[start:start + batch_size]
            emb = train_t['embeddings'][idx].to(device)
            state = train_t['states'][idx].to(device)
            types = train_t['override_types'][idx].to(device)
            strengths = train_t['strengths'][idx].to(device)
            tir = train_t['tir_deltas'][idx].to(device)

            type_logits, pred_strength, pred_tir = policy(emb, state)

            loss = (type_weight * ce_loss(type_logits, types)
                    + strength_weight * mse_loss(pred_strength.squeeze(), strengths)
                    + value_weight * mse_loss(pred_tir.squeeze(), tir))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        # Validate
        if n_val > 0:
            policy.eval()
            with torch.no_grad():
                v_emb = val_t['embeddings'].to(device)
                v_state = val_t['states'].to(device)
                v_types = val_t['override_types'].to(device)
                v_strengths = val_t['strengths'].to(device)
                v_tir = val_t['tir_deltas'].to(device)

                vl, vs, vt = policy(v_emb, v_state)
                val_loss = float(
                    type_weight * ce_loss(vl, v_types)
                    + strength_weight * mse_loss(vs.squeeze(), v_strengths)
                    + value_weight * mse_loss(vt.squeeze(), v_tir)
                )

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_epoch = epoch
                epochs_no_improve = 0
                torch.save({
                    'model_state': policy.state_dict(),
                    'epoch': epoch,
                    'val_loss': val_loss,
                }, save_path)
            else:
                epochs_no_improve += 1
        else:
            # No val data — save every improvement on train
            avg_loss = total_loss / max(n_batches, 1)
            if avg_loss < best_val_loss:
                best_val_loss = avg_loss
                best_epoch = epoch
                torch.save({
                    'model_state': policy.state_dict(),
                    'epoch': epoch,
                    'train_loss': avg_loss,
                }, save_path)

        if epochs_no_improve >= patience:
            break

    return {
        'best_val_loss': best_val_loss,
        'best_epoch': best_epoch,
        'epochs_run': epoch + 1,
        'n_train': n_train,
        'n_val': n_val,
    }


# ── Full Pipeline: Pattern-Triggered Recommender ────────────────────────

class PatternTriggeredRecommender:
    """End-to-end pipeline: encode window → match pattern → recommend override.

    Combines PatternEncoder, PatternLibrary, and PatternOverridePolicy into
    a single interface with safety guards.
    """

    def __init__(self, encoder, pattern_library, policy: PatternOverridePolicy,
                 hypo_risk_threshold: float = HYPO_RISK_THRESHOLD,
                 min_confidence: float = 0.3,
                 device: str = 'cpu'):
        self.encoder = encoder
        self.library = pattern_library
        self.policy = policy
        self.hypo_risk_threshold = hypo_risk_threshold
        self.min_confidence = min_confidence
        self.device = device

    def recommend(self, window: np.ndarray, glucose_scale: float = 400.0,
                  top_k_similar: int = 5) -> Dict:
        """Generate override recommendation for a glucose window.

        Args:
            window: (T, F) normalized feature array
            glucose_scale: for denormalization
            top_k_similar: number of similar episodes to retrieve

        Returns:
            dict with: recommendation, safety_check, similar_episodes, explanation
        """
        self.encoder.eval()
        self.policy.eval()

        # Encode window
        with torch.no_grad():
            x = torch.from_numpy(window).float().unsqueeze(0).to(self.device)
            embedding = self.encoder.encode(x)
            emb_np = embedding.cpu().numpy()[0]

        # Extract glucose state
        state = extract_glucose_state(window, glucose_scale)
        state_t = torch.from_numpy(state).float().unsqueeze(0).to(self.device)

        # Safety check
        hypo_risk = state[-1]  # last element is hypo_risk_proxy
        safety_blocked = hypo_risk > self.hypo_risk_threshold

        # Get recommendation from policy
        with torch.no_grad():
            rec = self.policy.recommend(embedding, state_t)

        # Find similar episodes
        similar = self.library.match(emb_np, top_k=top_k_similar)

        # Build result
        result = {
            'recommendation': rec,
            'safety_check': {
                'blocked': safety_blocked,
                'hypo_risk': float(hypo_risk),
                'threshold': self.hypo_risk_threshold,
            },
            'similar_episodes': similar,
            'pattern_classification': self.library.classify(emb_np),
        }

        # Generate explanation
        result['explanation'] = self._explain(rec, similar, safety_blocked)

        return result

    def _explain(self, rec: Dict, similar: List[Dict],
                 safety_blocked: bool) -> str:
        """Generate human-readable explanation."""
        if safety_blocked:
            return ("Recommendation blocked: hypoglycemia risk is elevated. "
                    "No override recommended until glucose stabilizes.")

        override_type = rec['override_type']
        confidence = rec['type_confidence']
        tir_delta = rec['predicted_tir_delta']

        n_similar = len(similar)
        similar_labels = [s['label'] for s in similar[:3]]

        explanation = (
            f"Recommending '{override_type}' override "
            f"(confidence: {confidence:.0%}, predicted TIR change: "
            f"{tir_delta:+.1%}). "
            f"Based on {n_similar} similar episodes "
            f"(patterns: {', '.join(similar_labels)})."
        )

        return explanation


# ── Evaluation ──────────────────────────────────────────────────────────

def evaluate_pattern_overrides(
    recommender: PatternTriggeredRecommender,
    test_windows: np.ndarray,
    test_labels: List[List[str]],
    test_tir_deltas: np.ndarray,
    glucose_scale: float = 400.0,
) -> Dict:
    """Evaluate pattern-triggered override recommendations.

    Compares against actual outcomes to measure recommendation quality.

    Args:
        recommender: trained PatternTriggeredRecommender
        test_windows: (N, T, F) test glucose windows
        test_labels: list of N label lists
        test_tir_deltas: (N,) actual TIR deltas for these windows
        glucose_scale: denormalization scale

    Returns:
        dict with: mean_tir_delta, hypo_safety_rate, precision_at_1,
        recommendation_coverage, per_type_stats
    """
    n = len(test_windows)
    recommendations = []
    blocked_count = 0

    for i in range(n):
        rec = recommender.recommend(test_windows[i], glucose_scale=glucose_scale)
        rec['actual_tir_delta'] = float(test_tir_deltas[i])
        rec['actual_labels'] = test_labels[i]
        recommendations.append(rec)

        if rec['safety_check']['blocked']:
            blocked_count += 1

    # Active recommendations (not blocked)
    active = [r for r in recommendations if not r['safety_check']['blocked']]

    if not active:
        return {
            'mean_tir_delta': 0.0,
            'hypo_safety_rate': 1.0,
            'precision_at_1': 0.0,
            'recommendation_coverage': 0.0,
            'n_total': n,
            'n_blocked': blocked_count,
            'n_active': 0,
        }

    # TIR delta: mean predicted improvement for active recommendations
    predicted_deltas = [r['recommendation']['predicted_tir_delta'] for r in active]
    actual_deltas = [r['actual_tir_delta'] for r in active]

    # Precision@1: how often does the top recommendation have positive actual TIR delta?
    correct = sum(1 for a in actual_deltas if a > 0)
    precision = correct / len(active)

    # Hypo safety rate: fraction of recommendations where actual glucose didn't go hypo
    # (approximate: positive TIR delta implies no new hypo events)
    safe = sum(1 for a in actual_deltas if a >= -0.05)
    safety_rate = safe / len(active)

    # Per-type breakdown
    type_stats = {}
    for r in active:
        t = r['recommendation']['override_type']
        if t not in type_stats:
            type_stats[t] = {'count': 0, 'mean_predicted': 0.0, 'mean_actual': 0.0}
        type_stats[t]['count'] += 1
        type_stats[t]['mean_predicted'] += r['recommendation']['predicted_tir_delta']
        type_stats[t]['mean_actual'] += r['actual_tir_delta']

    for t in type_stats:
        c = type_stats[t]['count']
        type_stats[t]['mean_predicted'] /= c
        type_stats[t]['mean_actual'] /= c

    return {
        'mean_predicted_tir_delta': float(np.mean(predicted_deltas)),
        'mean_actual_tir_delta': float(np.mean(actual_deltas)),
        'hypo_safety_rate': safety_rate,
        'precision_at_1': precision,
        'recommendation_coverage': len(active) / n,
        'n_total': n,
        'n_blocked': blocked_count,
        'n_active': len(active),
        'per_type_stats': type_stats,
    }
