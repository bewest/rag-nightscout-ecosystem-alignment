"""Multifactored phenotype FactsLoader: integrate stack × brake × counter-reg axes.

Load EXP-2886 (phenotype synthesis), EXP-2878 (HAAF detection), and
EXP-2881 (evening drivers) to expose per-patient phenotype facts for audition
without re-computing orthogonal axes.

This loader demonstrates the "multifactored" pattern: keep orthogonal signals
(|ρ|<0.32) separate rather than compositing into hidden_leverage-like constructs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_PHENOTYPE_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2886_phenotype_synthesis.parquet"
)
DEFAULT_HAAF_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2878_haaf_detection.parquet"
)
DEFAULT_EVENING_DRIVERS_PARQUET = (
    _REPO / "externals" / "experiments" / "exp-2881_evening_drivers.parquet"
)


@dataclass(frozen=True)
class PhenotypeFacts:
    """Orthogonal phenotype axes from EXP-2886 + validated HAAF/evening signals.
    
    All fields are Optional to support patients with incomplete phenotyping.
    Audition code should handle None gracefully (fallback to naive defaults).
    """
    # EXP-2886: primary phenotype axes (pairwise |ρ|<0.32)
    stack_score: Optional[float] = None  # Bolus stacking tendency (U, cumulative over 4h)
    brake_ratio: Optional[float] = None  # Basal suspension aggressiveness (frac, 0-1)
    counter_reg_intercept: Optional[float] = None  # Recovery rate at hypo (mg/dL/min)
    
    # EXP-2878: HAAF fragility marker (β_nadir slope sensitivity to hypo depth)
    beta_nadir: Optional[float] = None  # Dose-response sensitivity (unitless)
    p_haaf: Optional[float] = None  # Bootstrap p-value for HAAF detection
    
    # EXP-2881: evening stacking risk (primary driver of evening hypo)
    evening_bolus_excess_4h: Optional[float] = None  # Excess bolus in evening vs daily mean (U)
    evening_iob_at_descent: Optional[float] = None  # IOB when evening hypo descent starts (U)
    
    # Lineage classifier
    controller_lineage: Optional[str] = None  # Loop|oref0|Trio (from parent experiments)


class PhenotypeFactsLoader:
    """Lookup of EXP-2886/2878/2881 orthogonal phenotype facts by patient_id.
    
    Loads three independent research parquets (phenotype, HAAF, evening drivers)
    and merges them into a single frozen dataclass per patient. Supports lazy
    evaluation with caching.
    
    Returns PhenotypeFacts with all-None fields for unknown patients, allowing
    graceful fallback in audition code.
    
    Example:
        loader = PhenotypeFactsLoader()
        facts = loader.lookup("patient_123")
        if facts.brake_ratio is not None:
            # Use HAAF-validated brake as fragility signal
            fragile = facts.brake_ratio < 0.10 and facts.p_haaf < 0.05
    """
    
    def __init__(
        self,
        phenotype_path: Path = DEFAULT_PHENOTYPE_PARQUET,
        haaf_path: Path = DEFAULT_HAAF_PARQUET,
        evening_drivers_path: Path = DEFAULT_EVENING_DRIVERS_PARQUET,
    ) -> None:
        self._phenotype_path = Path(phenotype_path)
        self._haaf_path = Path(haaf_path)
        self._evening_drivers_path = Path(evening_drivers_path)
        self._index: Optional[dict[str, PhenotypeFacts]] = None
    
    def _load(self) -> dict[str, PhenotypeFacts]:
        """Load and merge three independent research artifacts.
        
        Each artifact is independently optional. Patients may have:
        - Full phenotype (all 3 artifacts)
        - Partial phenotype (1-2 artifacts)
        - No phenotype (fallback to None dataclass)
        
        This follows the graceful degradation principle from FactsLoader.
        """
        idx: dict[str, PhenotypeFacts] = {}
        
        # EXP-2886: Phenotype synthesis (stack, brake, counter-reg)
        phenotype_by_pid: dict[str, dict] = {}
        if self._phenotype_path.exists():
            df = pd.read_parquet(self._phenotype_path)
            if "patient_id" in df.columns:
                for _, r in df.iterrows():
                    pid = str(r["patient_id"])
                    phenotype_by_pid[pid] = {
                        'stack_score': (
                            float(r["stack_score"])
                            if "stack_score" in df.columns and pd.notna(r.get("stack_score"))
                            else None
                        ),
                        'brake_ratio': (
                            float(r["brake_ratio"])
                            if "brake_ratio" in df.columns and pd.notna(r.get("brake_ratio"))
                            else None
                        ),
                        'counter_reg_intercept': (
                            float(r["counter_reg_intercept"])
                            if "counter_reg_intercept" in df.columns and pd.notna(r.get("counter_reg_intercept"))
                            else None
                        ),
                        'controller_lineage': (
                            str(r["controller_lineage"])
                            if "controller_lineage" in df.columns and pd.notna(r.get("controller_lineage"))
                            else None
                        ),
                    }
        
        # EXP-2878: HAAF detection (β_nadir sensitivity, p_haaf)
        haaf_by_pid: dict[str, dict] = {}
        if self._haaf_path.exists():
            df = pd.read_parquet(self._haaf_path)
            if "patient_id" in df.columns:
                for _, r in df.iterrows():
                    pid = str(r["patient_id"])
                    haaf_by_pid[pid] = {
                        'beta_nadir': (
                            float(r["beta_nadir"])
                            if "beta_nadir" in df.columns and pd.notna(r.get("beta_nadir"))
                            else None
                        ),
                        'p_haaf': (
                            float(r["p_haaf"])
                            if "p_haaf" in df.columns and pd.notna(r.get("p_haaf"))
                            else None
                        ),
                    }
        
        # EXP-2881: Evening stacking drivers
        evening_by_pid: dict[str, dict] = {}
        if self._evening_drivers_path.exists():
            df = pd.read_parquet(self._evening_drivers_path)
            if "patient_id" in df.columns:
                for _, r in df.iterrows():
                    pid = str(r["patient_id"])
                    evening_by_pid[pid] = {
                        'evening_bolus_excess_4h': (
                            float(r["evening_bolus_excess_4h"])
                            if "evening_bolus_excess_4h" in df.columns and pd.notna(r.get("evening_bolus_excess_4h"))
                            else None
                        ),
                        'evening_iob_at_descent': (
                            float(r["evening_iob_at_descent"])
                            if "evening_iob_at_descent" in df.columns and pd.notna(r.get("evening_iob_at_descent"))
                            else None
                        ),
                    }
        
        # Merge all patients seen in any artifact
        all_pids = set(phenotype_by_pid) | set(haaf_by_pid) | set(evening_by_pid)
        for pid in all_pids:
            pheno = phenotype_by_pid.get(pid, {})
            haaf = haaf_by_pid.get(pid, {})
            evening = evening_by_pid.get(pid, {})
            
            idx[pid] = PhenotypeFacts(
                stack_score=pheno.get('stack_score'),
                brake_ratio=pheno.get('brake_ratio'),
                counter_reg_intercept=pheno.get('counter_reg_intercept'),
                beta_nadir=haaf.get('beta_nadir'),
                p_haaf=haaf.get('p_haaf'),
                evening_bolus_excess_4h=evening.get('evening_bolus_excess_4h'),
                evening_iob_at_descent=evening.get('evening_iob_at_descent'),
                controller_lineage=pheno.get('controller_lineage'),
            )
        
        return idx
    
    def lookup(self, patient_id: str) -> PhenotypeFacts:
        """Lookup phenotype facts for patient_id.
        
        Returns PhenotypeFacts with all-None for unknown patients.
        Callers should check individual fields:
            facts = loader.lookup(pid)
            if facts.brake_ratio is not None:
                # Use brake signal
        """
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            str(patient_id),
            PhenotypeFacts(),  # All-None dataclass
        )
    
    def known_patients(self) -> list[str]:
        """List all patients with at least one phenotype fact."""
        if self._index is None:
            self._index = self._load()
        return sorted(self._index.keys())
    
    def n_patients(self) -> int:
        """Count of patients with phenotype facts."""
        if self._index is None:
            self._index = self._load()
        return len(self._index)

    def compute_for(
        self,
        patient_id: str,
        grid_df,
        *,
        detected_controller: Optional[str] = None,
        cache: bool = True,
    ) -> PhenotypeFacts:
        """Minimal per-patient phenotype from grid only.

        Cohort-level fields (HAAF, evening drivers) require population
        comparisons and stay None; the lineage + observable-rate fields
        (controller_lineage, brake_ratio, stack_score) are computed inline.
        """
        from tools.cgmencode.production._per_patient_compute import (
            compute_phenotype_minimal,
        )
        row = compute_phenotype_minimal(
            grid_df, detected_controller=detected_controller
        )
        facts = PhenotypeFacts(
            stack_score=row.get("stack_score"),
            brake_ratio=row.get("brake_ratio"),
            counter_reg_intercept=row.get("counter_reg_intercept"),
            beta_nadir=row.get("beta_nadir"),
            p_haaf=row.get("p_haaf"),
            evening_bolus_excess_4h=row.get("evening_bolus_excess_4h"),
            evening_iob_at_descent=row.get("evening_iob_at_descent"),
            controller_lineage=row.get("controller_lineage"),
        )
        if cache:
            if self._index is None:
                self._index = self._load()
            self._index[str(patient_id)] = facts
        return facts
    
    def coverage_by_axis(self) -> dict[str, int]:
        """Count non-None for each orthogonal axis.
        
        Returns dict like:
            {
                'stack_score': 25,
                'brake_ratio': 25,
                'counter_reg_intercept': 25,
                'beta_nadir': 24,  # One patient missing HAAF
                'p_haaf': 24,
                'evening_bolus_excess_4h': 20,  # Some patients missing evening data
                ...
            }
        """
        if self._index is None:
            self._index = self._load()
        
        coverage = {
            'stack_score': 0,
            'brake_ratio': 0,
            'counter_reg_intercept': 0,
            'beta_nadir': 0,
            'p_haaf': 0,
            'evening_bolus_excess_4h': 0,
            'evening_iob_at_descent': 0,
            'controller_lineage': 0,
        }
        
        for facts in self._index.values():
            if facts.stack_score is not None:
                coverage['stack_score'] += 1
            if facts.brake_ratio is not None:
                coverage['brake_ratio'] += 1
            if facts.counter_reg_intercept is not None:
                coverage['counter_reg_intercept'] += 1
            if facts.beta_nadir is not None:
                coverage['beta_nadir'] += 1
            if facts.p_haaf is not None:
                coverage['p_haaf'] += 1
            if facts.evening_bolus_excess_4h is not None:
                coverage['evening_bolus_excess_4h'] += 1
            if facts.evening_iob_at_descent is not None:
                coverage['evening_iob_at_descent'] += 1
            if facts.controller_lineage is not None:
                coverage['controller_lineage'] += 1
        
        return coverage


def _smoke() -> None:  # pragma: no cover
    """Smoke test: verify loader initialization and lookup."""
    loader = PhenotypeFactsLoader()
    n = loader.n_patients()
    print(f"Loaded phenotype facts for {n} patients")
    
    coverage = loader.coverage_by_axis()
    print("Coverage by axis:")
    for axis, count in coverage.items():
        pct = 100.0 * count / n if n > 0 else 0
        print(f"  {axis:30s}: {count:3d} ({pct:5.1f}%)")
    
    # Sample lookup
    pids = loader.known_patients()
    if pids:
        sample_pid = pids[0]
        facts = loader.lookup(sample_pid)
        print(f"\nSample patient {sample_pid}:")
        print(f"  stack_score={facts.stack_score}")
        print(f"  brake_ratio={facts.brake_ratio}")
        print(f"  counter_reg_intercept={facts.counter_reg_intercept}")
        print(f"  beta_nadir={facts.beta_nadir} (p={facts.p_haaf})")
        print(f"  evening_bolus_excess_4h={facts.evening_bolus_excess_4h}")
        print(f"  controller_lineage={facts.controller_lineage}")


if __name__ == "__main__":
    _smoke()
