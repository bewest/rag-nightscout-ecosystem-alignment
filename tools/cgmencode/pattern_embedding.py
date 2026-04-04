"""Pattern Embedding Pipeline — Contrastive learning for glucose episode similarity.

Learns to represent glucose windows as fixed-size embedding vectors such that
similar metabolic episodes (same event type, similar glucose dynamics) map to
nearby points in embedding space. This enables pattern library construction,
similarity search, and downstream pattern-triggered recommendations.

Optimization target: Retrieval Recall@K and Cluster Purity (NOT forecast MAE).

Usage:
    from tools.cgmencode.pattern_embedding import (
        PatternEncoder, TripletPatternLoss, build_triplets,
        train_pattern_encoder, build_pattern_library, PatternLibrary,
    )
"""
import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ── Pattern labels used for contrastive mining ──────────────────────────

PATTERN_LABELS = [
    'stable', 'meal_bolus', 'meal_no_bolus', 'correction',
    'dawn', 'uam', 'exercise_candidate', 'high_volatility',
    'nocturnal', 'sensitivity_shift', 'resistance_shift', 'other',
]
LABEL_TO_IDX = {label: i for i, label in enumerate(PATTERN_LABELS)}


# ── Model ───────────────────────────────────────────────────────────────

class PatternEncoder(nn.Module):
    """Transformer encoder that maps glucose windows to fixed-size embeddings.

    Architecture:
        Linear(input_dim → d_model) → PositionalEncoding → TransformerEncoder
        → AttentionPooling → Projection(d_model → embed_dim) → L2 normalize

    The input projection and transformer layers can be initialized from a
    pretrained CGMTransformerAE checkpoint for transfer learning.
    """

    def __init__(self, input_dim: int = 8, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 2, dim_feedforward: int = 128,
                 dropout: float = 0.1, embed_dim: int = 64):
        super().__init__()
        self.input_dim = input_dim
        self.d_model = d_model
        self.embed_dim = embed_dim

        self.input_projection = nn.Linear(input_dim, d_model)

        # Positional encoding (sinusoidal, same as CGMTransformerAE)
        self.register_buffer('pe', self._build_pe(d_model, max_len=512))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead,
            dim_feedforward=dim_feedforward, dropout=dropout,
            batch_first=True, norm_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers,
        )

        # Attention-weighted pooling over time → single vector
        self.pool_query = nn.Linear(d_model, 1, bias=False)

        # Projection head for contrastive learning
        self.projection = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, embed_dim),
        )

    @staticmethod
    def _build_pe(d_model: int, max_len: int = 512) -> torch.Tensor:
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        return pe.unsqueeze(0)  # (1, max_len, d_model)

    def _attention_pool(self, encoded: torch.Tensor) -> torch.Tensor:
        """Attention-weighted temporal pooling: (B, T, d_model) → (B, d_model)."""
        weights = torch.softmax(self.pool_query(encoded).squeeze(-1), dim=1)
        return (weights.unsqueeze(-1) * encoded).sum(dim=1)

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Encode a batch of windows to L2-normalized embeddings.

        Args:
            x: (B, T, input_dim) glucose windows

        Returns:
            embeddings: (B, embed_dim) L2-normalized
        """
        h = self.input_projection(x)
        h = h + self.pe[:, :h.size(1), :]
        h = self.transformer_encoder(h)
        pooled = self._attention_pool(h)
        projected = self.projection(pooled)
        return F.normalize(projected, p=2, dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Alias for encode()."""
        return self.encode(x)

    def load_from_forecast(self, forecast_state_dict: dict,
                           strict: bool = False) -> List[str]:
        """Initialize encoder weights from a pretrained CGMTransformerAE.

        Transfers input_projection and transformer_encoder weights.
        Projection head is left randomly initialized (new task).

        Returns list of keys that were NOT loaded (for logging).
        """
        transferable = {}
        for k, v in forecast_state_dict.items():
            if k.startswith('input_projection.') or k.startswith('transformer_encoder.'):
                transferable[k] = v
        missing, unexpected = self.load_state_dict(transferable, strict=False)
        return missing


# ── Loss ────────────────────────────────────────────────────────────────

class TripletPatternLoss(nn.Module):
    """Triplet margin loss for pattern embeddings.

    Given (anchor, positive, negative) embeddings, optimizes:
        loss = max(0, d(a,p) - d(a,n) + margin)

    where d is Euclidean distance in the L2-normalized embedding space.
    """

    def __init__(self, margin: float = 1.0):
        super().__init__()
        self.margin = margin

    def forward(self, anchor: torch.Tensor, positive: torch.Tensor,
                negative: torch.Tensor) -> torch.Tensor:
        """Compute triplet loss.

        Args:
            anchor:   (B, embed_dim) L2-normalized
            positive: (B, embed_dim) L2-normalized
            negative: (B, embed_dim) L2-normalized

        Returns:
            Scalar loss
        """
        d_pos = (anchor - positive).pow(2).sum(dim=-1)
        d_neg = (anchor - negative).pow(2).sum(dim=-1)
        losses = F.relu(d_pos - d_neg + self.margin)
        return losses.mean()


# ── Triplet Mining ──────────────────────────────────────────────────────

def _primary_label(labels: List[str]) -> str:
    """Extract the primary (first non-'other') label from classify_window output."""
    for lbl in labels:
        if lbl in LABEL_TO_IDX and lbl != 'other':
            return lbl
    return 'other'


def build_triplets(windows: np.ndarray, labels: List[List[str]],
                   patient_ids: Optional[np.ndarray] = None,
                   strategy: str = 'random',
                   n_triplets: int = 10000,
                   rng: Optional[np.random.RandomState] = None,
                   ) -> List[Tuple[int, int, int]]:
    """Mine triplets from labeled windows for contrastive training.

    Positive pairs: same primary label (optionally same patient).
    Negative pairs: different primary label.

    Args:
        windows: (N, T, F) feature array (used only for shape/indexing)
        labels: list of N label lists from classify_window()
        patient_ids: optional (N,) array of patient identifiers
        strategy: 'random' | 'semi-hard' | 'hard'
            - 'random': uniform random positive/negative selection
            - 'semi-hard': negatives within margin (requires embeddings, falls back to random)
            - 'hard': hardest negatives (requires embeddings, falls back to random)
        n_triplets: number of triplets to generate
        rng: random state for reproducibility

    Returns:
        list of (anchor_idx, positive_idx, negative_idx) tuples
    """
    if rng is None:
        rng = np.random.RandomState(42)

    n = len(labels)
    primary = [_primary_label(lbl) for lbl in labels]

    # Group indices by primary label
    label_groups: Dict[str, List[int]] = defaultdict(list)
    for i, lbl in enumerate(primary):
        label_groups[lbl].append(i)

    # Need at least 2 labels with ≥1 sample each
    active_labels = [l for l, idxs in label_groups.items() if len(idxs) >= 2]
    if len(active_labels) < 2:
        # Not enough diversity — create pairs from available
        active_labels = [l for l, idxs in label_groups.items() if len(idxs) >= 1]

    all_negatable = [l for l in label_groups if l not in set()]  # all labels

    triplets = []
    for _ in range(n_triplets):
        # Pick anchor label with at least 2 members
        anchor_label = rng.choice(active_labels)
        anchor_members = label_groups[anchor_label]

        if len(anchor_members) < 2:
            continue

        # Pick anchor and positive from same label
        a_idx, p_idx = rng.choice(anchor_members, size=2, replace=False)

        # Pick negative from different label
        neg_labels = [l for l in all_negatable if l != anchor_label and len(label_groups[l]) > 0]
        if not neg_labels:
            continue
        neg_label = rng.choice(neg_labels)
        n_idx = rng.choice(label_groups[neg_label])

        triplets.append((int(a_idx), int(p_idx), int(n_idx)))

    return triplets


# ── Training ────────────────────────────────────────────────────────────

def train_pattern_encoder(
    model: PatternEncoder,
    train_windows: np.ndarray,
    train_labels: List[List[str]],
    val_windows: np.ndarray,
    val_labels: List[List[str]],
    save_path: str,
    epochs: int = 50,
    batch_size: int = 128,
    lr: float = 1e-3,
    margin: float = 1.0,
    n_triplets: int = 10000,
    patience: int = 10,
    device: str = 'cpu',
    train_patient_ids: Optional[np.ndarray] = None,
    val_patient_ids: Optional[np.ndarray] = None,
) -> Dict:
    """Train pattern encoder with triplet loss.

    Returns dict with best_recall, best_purity, epochs_run.
    """
    model = model.to(device)
    criterion = TripletPatternLoss(margin=margin)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=patience // 2, factor=0.5,
    )

    best_recall = 0.0
    best_epoch = 0
    epochs_no_improve = 0

    train_t = torch.from_numpy(train_windows).float()
    val_t = torch.from_numpy(val_windows).float()

    for epoch in range(epochs):
        model.train()

        # Mine fresh triplets each epoch
        triplets = build_triplets(
            train_windows, train_labels,
            patient_ids=train_patient_ids,
            n_triplets=n_triplets,
            rng=np.random.RandomState(epoch),
        )

        if len(triplets) == 0:
            break

        # Batch training
        total_loss = 0.0
        n_batches = 0

        for start in range(0, len(triplets), batch_size):
            batch = triplets[start:start + batch_size]
            a_idx = [t[0] for t in batch]
            p_idx = [t[1] for t in batch]
            n_idx = [t[2] for t in batch]

            a_emb = model.encode(train_t[a_idx].to(device))
            p_emb = model.encode(train_t[p_idx].to(device))
            n_emb = model.encode(train_t[n_idx].to(device))

            loss = criterion(a_emb, p_emb, n_emb)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)

        # Validate with retrieval recall
        model.eval()
        with torch.no_grad():
            val_emb = model.encode(val_t.to(device)).cpu().numpy()
        recall = retrieval_recall_at_k(val_emb, val_labels, k=5)

        scheduler.step(-recall)

        if recall > best_recall:
            best_recall = recall
            best_epoch = epoch
            epochs_no_improve = 0
            torch.save({
                'model_state': model.state_dict(),
                'epoch': epoch,
                'recall_at_5': recall,
                'train_loss': avg_loss,
            }, save_path)
        else:
            epochs_no_improve += 1

        if epochs_no_improve >= patience:
            break

    return {
        'best_recall_at_5': best_recall,
        'best_epoch': best_epoch,
        'epochs_run': epoch + 1,
        'final_train_loss': avg_loss if n_batches > 0 else float('nan'),
    }


# ── Evaluation Metrics ──────────────────────────────────────────────────

def retrieval_recall_at_k(embeddings: np.ndarray, labels: List[List[str]],
                          k: int = 5) -> float:
    """Compute retrieval recall@k: fraction of queries where at least one
    of the top-k nearest neighbors shares the primary label.

    Args:
        embeddings: (N, embed_dim) L2-normalized
        labels: list of N label lists from classify_window()
        k: number of neighbors to check

    Returns:
        Recall@k in [0, 1]
    """
    primary = [_primary_label(lbl) for lbl in labels]
    n = len(embeddings)
    if n <= k + 1:
        return 0.0

    # Cosine similarity (embeddings are L2-normalized, so dot product = cosine)
    sims = embeddings @ embeddings.T
    hits = 0
    for i in range(n):
        # Exclude self
        sims[i, i] = -float('inf')
        top_k = np.argsort(sims[i])[-k:]
        if any(primary[j] == primary[i] for j in top_k):
            hits += 1

    return hits / n


def cluster_purity(embeddings: np.ndarray, labels: List[List[str]],
                   n_clusters: int = 10) -> float:
    """Compute cluster purity: assign each embedding to nearest cluster,
    measure fraction sharing the dominant label per cluster.

    Uses k-means clustering. Falls back to label-count purity if
    sklearn is unavailable.
    """
    primary = np.array([_primary_label(lbl) for lbl in labels])

    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=min(n_clusters, len(embeddings)),
                    random_state=42, n_init=3)
        assignments = km.fit_predict(embeddings)
    except ImportError:
        # Fallback: random assignment
        assignments = np.random.randint(0, n_clusters, size=len(embeddings))

    total_pure = 0
    for c in range(assignments.max() + 1):
        mask = assignments == c
        if mask.sum() == 0:
            continue
        cluster_labels = primary[mask]
        # Count most common label
        unique, counts = np.unique(cluster_labels, return_counts=True)
        total_pure += counts.max()

    return total_pure / len(embeddings)


def silhouette_score_safe(embeddings: np.ndarray, labels: List[List[str]]) -> float:
    """Compute silhouette score using primary labels as ground-truth clusters.

    Returns -1.0 if computation fails (e.g., < 2 unique labels).
    """
    primary = [_primary_label(lbl) for lbl in labels]
    unique_labels = set(primary)
    if len(unique_labels) < 2 or len(embeddings) < 3:
        return -1.0

    try:
        from sklearn.metrics import silhouette_score
        return float(silhouette_score(embeddings, primary, metric='cosine'))
    except (ImportError, ValueError):
        return -1.0


# ── Pattern Library ─────────────────────────────────────────────────────

class PatternLibrary:
    """Indexed collection of pattern prototypes for fast similarity search.

    Stores prototype embeddings (cluster centroids) labeled with pattern types.
    Supports nearest-neighbor retrieval for new windows.
    """

    def __init__(self):
        self.prototypes: Dict[str, np.ndarray] = {}
        self._all_embeddings: Optional[np.ndarray] = None
        self._all_labels: Optional[List[str]] = None
        self._all_metadata: Optional[List[dict]] = None

    def build(self, embeddings: np.ndarray, labels: List[List[str]],
              metadata: Optional[List[dict]] = None,
              n_prototypes_per_label: int = 3) -> 'PatternLibrary':
        """Build library from embeddings and labels.

        Args:
            embeddings: (N, embed_dim) L2-normalized
            labels: list of N label lists
            metadata: optional list of N dicts with timestamps, patient_id, etc.
            n_prototypes_per_label: number of centroids per label

        Returns:
            self (for chaining)
        """
        primary = [_primary_label(lbl) for lbl in labels]

        self._all_embeddings = embeddings.copy()
        self._all_labels = primary
        self._all_metadata = metadata

        # Compute prototypes per label
        label_groups: Dict[str, List[int]] = defaultdict(list)
        for i, lbl in enumerate(primary):
            label_groups[lbl].append(i)

        self.prototypes = {}
        for lbl, idxs in label_groups.items():
            group_emb = embeddings[idxs]
            if len(idxs) <= n_prototypes_per_label:
                # Use all as prototypes
                self.prototypes[lbl] = group_emb.mean(axis=0)
            else:
                try:
                    from sklearn.cluster import KMeans
                    km = KMeans(n_clusters=n_prototypes_per_label,
                                random_state=42, n_init=3)
                    km.fit(group_emb)
                    # Store centroid closest to overall mean as prototype
                    self.prototypes[lbl] = km.cluster_centers_.mean(axis=0)
                except ImportError:
                    self.prototypes[lbl] = group_emb.mean(axis=0)

            # L2 normalize prototype
            norm = np.linalg.norm(self.prototypes[lbl])
            if norm > 0:
                self.prototypes[lbl] /= norm

        return self

    def match(self, embedding: np.ndarray, top_k: int = 5
              ) -> List[Dict]:
        """Find most similar stored episodes to a query embedding.

        Args:
            embedding: (embed_dim,) L2-normalized query
            top_k: number of results

        Returns:
            list of dicts with keys: label, distance, index, metadata
        """
        if self._all_embeddings is None or len(self._all_embeddings) == 0:
            return []

        # Cosine similarity (already L2-normalized)
        sims = self._all_embeddings @ embedding
        top_idx = np.argsort(sims)[-top_k:][::-1]

        results = []
        for idx in top_idx:
            result = {
                'label': self._all_labels[idx],
                'similarity': float(sims[idx]),
                'index': int(idx),
            }
            if self._all_metadata is not None:
                result['metadata'] = self._all_metadata[idx]
            results.append(result)

        return results

    def classify(self, embedding: np.ndarray) -> Tuple[str, float]:
        """Classify a query by nearest prototype.

        Returns (label, similarity_score).
        """
        if not self.prototypes:
            return ('other', 0.0)

        best_label = 'other'
        best_sim = -float('inf')
        for lbl, proto in self.prototypes.items():
            sim = float(embedding @ proto)
            if sim > best_sim:
                best_sim = sim
                best_label = lbl

        return (best_label, best_sim)


def build_pattern_library(encoder: PatternEncoder,
                          windows: np.ndarray,
                          labels: List[List[str]],
                          metadata: Optional[List[dict]] = None,
                          device: str = 'cpu',
                          batch_size: int = 256,
                          n_prototypes_per_label: int = 3,
                          ) -> PatternLibrary:
    """Encode all windows and build a searchable pattern library.

    Args:
        encoder: trained PatternEncoder
        windows: (N, T, F) feature array
        labels: list of N label lists from classify_window()
        metadata: optional list of dicts (timestamps, patient_id, etc.)
        device: torch device
        batch_size: encoding batch size
        n_prototypes_per_label: centroids per label group

    Returns:
        PatternLibrary with indexed embeddings and prototypes
    """
    encoder.eval()
    all_emb = []

    t = torch.from_numpy(windows).float()
    with torch.no_grad():
        for start in range(0, len(t), batch_size):
            batch = t[start:start + batch_size].to(device)
            emb = encoder.encode(batch).cpu().numpy()
            all_emb.append(emb)

    embeddings = np.concatenate(all_emb, axis=0)

    library = PatternLibrary()
    library.build(embeddings, labels, metadata=metadata,
                  n_prototypes_per_label=n_prototypes_per_label)
    return library


# ── Feature Ablation Framework ──────────────────────────────────────────

# Channel groups matching schema.py definitions
CHANNEL_GROUPS = {
    'base_8f':     list(range(0, 8)),     # glucose, IOB, COB, basal, bolus, carbs, time
    'dynamics':    list(range(8, 12)),     # weekday, override, glucose dynamics
    'temporal':    list(range(12, 16)),    # ROC, accel, time-since-bolus/carb
    'cgm_quality': list(range(16, 21)),   # CAGE, SAGE, warmup, noise, calibration
    'aid_context': list(range(21, 32)),   # Loop predictions, enacted actions
    'profile':     list(range(32, 35)),   # scheduled ISF, CR, glucose_vs_target
    'pump_state':  list(range(35, 39)),   # pump reservoir, battery, suspension
}


def ablation_sweep(encoder_factory, train_fn, eval_fn,
                   train_ds, val_ds, input_dim: int = 39,
                   groups: Optional[Dict[str, List[int]]] = None,
                   device: str = 'cpu') -> Dict[str, Dict]:
    """Run channel-group ablation: mask each group, measure metric delta.

    Args:
        encoder_factory: callable(input_dim) → PatternEncoder
        train_fn: callable(encoder, train_ds, val_ds, masked_channels) → trained encoder
        eval_fn: callable(encoder, val_ds) → dict of metrics
        train_ds: training dataset
        val_ds: validation dataset
        input_dim: total number of channels
        groups: channel group definitions (defaults to CHANNEL_GROUPS)
        device: torch device string

    Returns:
        dict mapping group_name → {
            'baseline_metrics': {...}, 'ablated_metrics': {...},
            'delta': {...}, 'channels_masked': [...]
        }
    """
    if groups is None:
        groups = CHANNEL_GROUPS

    # Train and evaluate baseline (no masking)
    baseline_encoder = encoder_factory(input_dim)
    baseline_encoder = train_fn(baseline_encoder, train_ds, val_ds, [])
    baseline_metrics = eval_fn(baseline_encoder, val_ds)

    results = {}
    for group_name, channels in groups.items():
        # Only ablate channels that exist in the input
        valid_channels = [c for c in channels if c < input_dim]
        if not valid_channels:
            continue

        ablated_encoder = encoder_factory(input_dim)
        ablated_encoder = train_fn(ablated_encoder, train_ds, val_ds, valid_channels)
        ablated_metrics = eval_fn(ablated_encoder, val_ds)

        delta = {}
        for k in baseline_metrics:
            if isinstance(baseline_metrics[k], (int, float)):
                delta[k] = ablated_metrics.get(k, 0) - baseline_metrics[k]

        results[group_name] = {
            'baseline_metrics': baseline_metrics,
            'ablated_metrics': ablated_metrics,
            'delta': delta,
            'channels_masked': valid_channels,
        }

    return results


def window_sweep(encoder_factory, train_fn, eval_fn,
                 data_loader_fn, window_sizes: Optional[List[int]] = None,
                 input_dim: int = 8,
                 device: str = 'cpu') -> Dict[int, Dict]:
    """Sweep window lengths: train + evaluate at each size.

    Args:
        encoder_factory: callable(input_dim) → PatternEncoder
        train_fn: callable(encoder, train_ds, val_ds) → trained encoder
        eval_fn: callable(encoder, val_ds) → dict of metrics
        data_loader_fn: callable(window_size) → (train_ds, val_ds)
        window_sizes: list of window sizes to test (steps)
        input_dim: number of channels
        device: torch device string

    Returns:
        dict mapping window_size → metrics dict
    """
    if window_sizes is None:
        window_sizes = [12, 24, 48, 96, 144]  # 1h, 2h, 4h, 8h, 12h

    results = {}
    for ws in window_sizes:
        train_ds, val_ds = data_loader_fn(ws)
        if train_ds is None or len(train_ds) < 10:
            results[ws] = {'error': 'insufficient data', 'n_train': 0}
            continue

        encoder = encoder_factory(input_dim)
        encoder = train_fn(encoder, train_ds, val_ds)
        metrics = eval_fn(encoder, val_ds)
        metrics['window_size'] = ws
        metrics['n_train'] = len(train_ds)
        results[ws] = metrics

    return results
