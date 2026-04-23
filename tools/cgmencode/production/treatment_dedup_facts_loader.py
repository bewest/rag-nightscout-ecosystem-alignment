"""Treatment deduplication strategy FactsLoader.

Load per-patient deduplication logic from EXP-2892 (treatment sync reconciliation)
to expose dedup window, tie-breaker priority, and sync identity strategy for
production treatment collection without re-computing dedup analysis.

This demonstrates the "multifactored reconciliation" pattern from BabelBetes Flair:
multiple orthogonal sources (xDrip+, AAPS, Nightscout, Loop) merged with ordered
factors (time → sync ID → event type → confidence).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_DEDUP_STRATEGY_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2892_treatment_dedup_strategy.parquet"
)

# Default dedup strategy: conservative, works across all AID systems
DEFAULT_DEDUP_WINDOW_SEC = 60  # ±1 minute for matching timestamp
DEFAULT_TIE_BREAKER_PRIORITY = ["AAPS", "xDripPlus", "Loop", "Nightscout"]


@dataclass(frozen=True)
class TreatmentDedupFacts:
    """Per-patient treatment deduplication strategy facts.
    
    These facts encapsulate patient-specific dedup logic learned from EXP-2892
    traffic analysis, allowing audition code to apply personalized reconciliation
    without re-running the analysis.
    """
    # Time-based deduplication
    dedup_window_sec: int = DEFAULT_DEDUP_WINDOW_SEC
    
    # Tie-breaking order (which system "wins" in conflicts)
    # E.g., if AAPS and xDrip+ both report bolus within ±60s, AAPS version is canonical
    tie_breaker_priority: list[str] = None  # dataclass field default to mutable...
    
    # Sync identity strategy
    use_sync_id: bool = True  # Prefer syncIdentifier if present
    sync_id_field: str = "interfaceIDs.nightscoutId"  # Where to find cross-system link
    
    # Event type handling (some types less reliable across systems)
    # E.g., bolus very reliable, temp basal adjustment less so
    event_type_confidence: dict[str, float] = None
    
    # Control: probability that this patient's dedup strategy is reliable (0-1)
    confidence: Optional[float] = None
    
    def __post_init__(self) -> None:
        """Validate dedup facts."""
        if self.tie_breaker_priority is None:
            object.__setattr__(self, 'tie_breaker_priority', DEFAULT_TIE_BREAKER_PRIORITY)
        if self.event_type_confidence is None:
            object.__setattr__(self, 'event_type_confidence', {
                'bolus': 0.95,
                'meal': 0.85,
                'tempbasal': 0.70,
                'suspend': 0.90,
                'resume': 0.90,
            })


class TreatmentDedupFactsLoader:
    """Lookup of EXP-2892 per-patient treatment dedup strategy.
    
    Returns per-patient dedup facts (window, priority, sync fields) from
    EXP-2892 traffic analysis. For patients not in EXP-2892, uses conservative
    defaults that work across all AID systems.
    
    Example:
        loader = TreatmentDedupFactsLoader()
        strategy = loader.lookup("ns-8b3c1b50793c")
        
        # Apply dedup to incoming treatments
        deduped = deduplicate_treatments(
            treatments,
            window_sec=strategy.dedup_window_sec,
            priority=strategy.tie_breaker_priority,
        )
    """
    
    def __init__(
        self,
        strategy_path: Path = DEFAULT_DEDUP_STRATEGY_PARQUET,
    ) -> None:
        self._strategy_path = Path(strategy_path)
        self._index: Optional[dict[str, TreatmentDedupFacts]] = None
    
    def _load(self) -> dict[str, TreatmentDedupFacts]:
        """Load EXP-2892 dedup strategy parquet.
        
        Expected schema:
            patient_id (str): Nightscout patient ID
            dedup_window_sec (int): ±N seconds for timestamp matching
            tie_breaker_priority (str): JSON list of system names in priority order
            use_sync_id (bool): Whether to prefer sync identity over time
            sync_id_field (str): Which field holds sync identifier
            event_type_confidence (str): JSON dict of eventType → confidence
            confidence (float): 0-1 reliability of this strategy
        """
        idx: dict[str, TreatmentDedupFacts] = {}
        
        if not self._strategy_path.exists():
            return idx
        
        df = pd.read_parquet(self._strategy_path)
        if "patient_id" not in df.columns:
            return idx
        
        for _, r in df.iterrows():
            pid = str(r["patient_id"])
            
            # Parse JSON fields if present
            import json
            
            tie_breaker = DEFAULT_TIE_BREAKER_PRIORITY
            if "tie_breaker_priority" in df.columns and pd.notna(r.get("tie_breaker_priority")):
                try:
                    tie_breaker = json.loads(r["tie_breaker_priority"])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            event_confidence = None
            if "event_type_confidence" in df.columns and pd.notna(r.get("event_type_confidence")):
                try:
                    event_confidence = json.loads(r["event_type_confidence"])
                except (json.JSONDecodeError, TypeError):
                    pass
            
            idx[pid] = TreatmentDedupFacts(
                dedup_window_sec=(
                    int(r["dedup_window_sec"])
                    if "dedup_window_sec" in df.columns and pd.notna(r.get("dedup_window_sec"))
                    else DEFAULT_DEDUP_WINDOW_SEC
                ),
                tie_breaker_priority=tie_breaker,
                use_sync_id=(
                    bool(r["use_sync_id"])
                    if "use_sync_id" in df.columns and pd.notna(r.get("use_sync_id"))
                    else True
                ),
                sync_id_field=(
                    str(r["sync_id_field"])
                    if "sync_id_field" in df.columns and pd.notna(r.get("sync_id_field"))
                    else "interfaceIDs.nightscoutId"
                ),
                event_type_confidence=event_confidence,
                confidence=(
                    float(r["confidence"])
                    if "confidence" in df.columns and pd.notna(r.get("confidence"))
                    else None
                ),
            )
        
        return idx
    
    def lookup(self, patient_id: str) -> TreatmentDedupFacts:
        """Lookup dedup strategy for patient_id.
        
        Returns patient-specific strategy if found in EXP-2892, else
        conservative defaults that work for any patient.
        """
        if self._index is None:
            self._index = self._load()
        
        return self._index.get(
            str(patient_id),
            TreatmentDedupFacts(),  # All-default conservative strategy
        )
    
    def known_patients(self) -> list[str]:
        """List patients with EXP-2892 dedup analysis."""
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())
    
    def n_patients_analyzed(self) -> int:
        """Count of patients in EXP-2892."""
        if self._index is None:
            self._index = self._load()
        return len(self._index)


def _smoke() -> None:  # pragma: no cover
    """Smoke test: verify loader initialization."""
    loader = TreatmentDedupFactsLoader()
    n = loader.n_patients_analyzed()
    print(f"Loaded dedup strategies for {n} patients from EXP-2892")
    
    pids = loader.known_patients()
    if pids:
        sample_pid = pids[0]
        strategy = loader.lookup(sample_pid)
        print(f"\nSample patient {sample_pid}:")
        print(f"  dedup_window_sec: {strategy.dedup_window_sec}")
        print(f"  tie_breaker_priority: {strategy.tie_breaker_priority}")
        print(f"  use_sync_id: {strategy.use_sync_id}")
        print(f"  confidence: {strategy.confidence}")
    
    # Show defaults
    print(f"\nDefault strategy (for unknown patient):")
    default = loader.lookup("unknown-patient-xyz")
    print(f"  dedup_window_sec: {default.dedup_window_sec}")
    print(f"  tie_breaker_priority: {default.tie_breaker_priority}")


if __name__ == "__main__":
    _smoke()
