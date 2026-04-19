"""
experiment_base.py — Shared base class for observational AID experiments.

Eliminates copy-paste across 300+ experiments by providing:
  - Standard data loading (grid + devicestatus + controller map + qualified patients)
  - Declarative filter specification via ExperimentFilters
  - BGI subtraction as default preprocessing (EXP-2698: +0.418 R²)
  - Event categorization (correction/meal/UAM/basal/mixed)
  - Natural Experiment Detector integration
  - Automatic validation checks
  - Standard result saving and visualization

Usage:
    class MyExperiment(ObservationalExperiment):
        EXP_ID = "EXP-2699"
        TITLE = "My ISF Analysis"

        # Declare what this experiment needs
        FILTERS = ExperimentFilters.correction()
        DECONFOUNDING = ["bgi_subtraction", "categorize"]

        def analyze(self, events: pd.DataFrame) -> dict:
            corrections = events[events["category"] == "correction"]
            # ... your analysis here ...
            return {"my_result": 42}

    exp = MyExperiment()
    exp.run()  # loads data, filters, deconfounds, validates, analyzes, saves

Design principles:
  - Subclasses override analyze() with experiment-specific logic
  - Base class handles all boilerplate (load, filter, deconfound, validate, save)
  - Flexible: subclasses can override any step
  - Composable: mix exclusion-based and subtraction-based deconfounding
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .deconfounding import (
    BGISubtraction,
    ChannelDecomposition,
    EventCategorizer,
    ExperimentFilters,
    IsolationFilter,
    ValidationChecks,
)

warnings.filterwarnings("ignore")


# ── Standard paths ───────────────────────────────────────────────────

GRID_PATH = Path("externals/ns-parquet/training/grid.parquet")
DS_PATH = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST_PATH = Path("externals/experiments/autoprepare-qualified.json")
EXPERIMENTS_DIR = Path("externals/experiments")
VIS_DIR = Path("visualizations")


# ── Base Class ───────────────────────────────────────────────────────

class ObservationalExperiment:
    """Base class for observational AID experiments.

    Provides standard data loading, filtering, deconfounding, validation,
    and result saving. Subclasses override analyze() with their specific logic.

    Class attributes (override in subclass):
        EXP_ID: str          — Experiment identifier (e.g., "EXP-2699")
        TITLE: str           — Human-readable title
        FILTERS: ExperimentFilters — Declarative filter specification
        DECONFOUNDING: list   — Ordered list of strategies to apply:
            "bgi_subtraction"     — Subtract expected insulin effect (oref0-style)
            "channel_decomposition" — Estimate per-channel effects
            "categorize"          — Classify events into categories
            "isolation"           — Apply exclusion-based isolation filters
        CONTROLLER_STRATIFY: bool — Whether to run per-controller analysis
    """

    EXP_ID: str = "EXP-0000"
    TITLE: str = "Unnamed Experiment"
    FILTERS: ExperimentFilters = ExperimentFilters.permissive()
    DECONFOUNDING: List[str] = ["bgi_subtraction", "categorize"]
    CONTROLLER_STRATIFY: bool = True

    def __init__(
        self,
        grid_path: Optional[Path] = None,
        ds_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        self.grid_path = grid_path or GRID_PATH
        self.ds_path = ds_path or DS_PATH
        self.manifest_path = manifest_path or MANIFEST_PATH
        self.output_dir = output_dir or VIS_DIR / self.EXP_ID.lower().replace("-", "_")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.grid: Optional[pd.DataFrame] = None
        self.ctrl_map: Optional[Dict[str, str]] = None
        self.qualified: Optional[List[str]] = None
        self.events: Optional[pd.DataFrame] = None
        self.validation: Optional[Dict] = None
        self.results: Optional[Dict] = None

    # ── Standard Pipeline ────────────────────────────────────────────

    def run(self) -> Dict:
        """Execute the full experiment pipeline.

        Steps:
            1. load_data()       — Load grid, devicestatus, qualified patients
            2. extract_events()  — Apply filters + deconfounding to get events
            3. validate()        — Run automatic validation checks
            4. analyze()         — Subclass-specific analysis (override this)
            5. save_results()    — Persist JSON results
        """
        print(f"\n{'='*60}")
        print(f"{self.EXP_ID}: {self.TITLE}")
        print(f"{'='*60}\n")

        print("Step 1: Loading data...")
        self.load_data()
        print(f"  Grid: {len(self.grid):,} rows, {self.grid['patient_id'].nunique()} patients")

        print("Step 2: Extracting events...")
        self.events = self.extract_events()
        print(f"  Events: {len(self.events):,}")

        print("Step 3: Validating...")
        self.validation = self.validate()
        overall = self.validation.get("overall", "UNKNOWN")
        print(f"  Validation: {overall}")

        if overall == "REVIEW":
            for key, val in self.validation.items():
                if isinstance(val, dict) and val.get("status") not in ("PASS", "SKIP", None):
                    print(f"    ⚠ {key}: {val.get('status')} — {val.get('recommendation', '')}")

        print("Step 4: Analyzing...")
        self.results = self.analyze(self.events)

        print("Step 5: Saving results...")
        self.save_results()

        print(f"\n✓ {self.EXP_ID} complete. Results: {self._results_path()}")
        return self.results

    # ── Data Loading ─────────────────────────────────────────────────

    def load_data(self):
        """Load grid, devicestatus, controller map, and qualified patients.

        This is the 8-line block that was copy-pasted across every experiment.
        Now it's done once, correctly.
        """
        self.grid = pd.read_parquet(self.grid_path)
        ds = pd.read_parquet(self.ds_path)
        self.ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
        self.grid["controller"] = self.grid["patient_id"].map(self.ctrl_map)

        manifest = json.loads(self.manifest_path.read_text())
        self.qualified = manifest["qualified_patients"]
        self.grid = self.grid[self.grid["patient_id"].isin(self.qualified)].copy()

        # Ensure time is datetime
        if not pd.api.types.is_datetime64_any_dtype(self.grid["time"]):
            self.grid["time"] = pd.to_datetime(self.grid["time"], utc=True)
        self.grid = self.grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # ── Event Extraction ─────────────────────────────────────────────

    def extract_events(self) -> pd.DataFrame:
        """Apply deconfounding pipeline to extract events.

        Applies strategies in order from self.DECONFOUNDING.
        Subclasses can override for custom extraction logic.
        """
        events = self.grid

        for strategy in self.DECONFOUNDING:
            if strategy == "bgi_subtraction":
                bgi = BGISubtraction(
                    horizon_steps=int(self.FILTERS.horizon_hours * 12)
                )
                events = bgi.compute_deviations(events)
                print(f"    BGI subtraction: {len(events):,} events")

            elif strategy == "channel_decomposition":
                cd = ChannelDecomposition()
                events = cd.decompose(events)
                print(f"    Channel decomposition: added residual columns")

            elif strategy == "categorize":
                ec = EventCategorizer()
                events = ec.categorize(events)
                cat_counts = events["category"].value_counts().to_dict()
                print(f"    Categorized: {cat_counts}")

            elif strategy == "isolation":
                iso = IsolationFilter(self.FILTERS)
                events = iso.apply(events)
                print(f"    Isolation filter: {len(events):,} events remaining")

        # Apply BG floor filter (always, unless 0)
        if self.FILTERS.bg_floor > 0 and "bg0" in events.columns:
            events = events[events["bg0"] >= self.FILTERS.bg_floor].copy()
            print(f"    BG floor ≥{self.FILTERS.bg_floor}: {len(events):,} events")

        return events

    # ── Validation ───────────────────────────────────────────────────

    def validate(self) -> Dict:
        """Run automatic validation checks on extracted events.

        Returns validation report dict. Subclasses can override to add
        experiment-specific checks.
        """
        if self.events is None or len(self.events) == 0:
            return {"overall": "FAIL", "reason": "No events extracted"}

        return ValidationChecks.run_all(self.events, self.FILTERS)

    # ── Analysis (OVERRIDE THIS) ─────────────────────────────────────

    def analyze(self, events: pd.DataFrame) -> Dict:
        """Subclass-specific analysis logic.

        Override this method with your experiment's analysis.
        The events DataFrame has already been filtered, deconfounded,
        categorized, and validated.

        Args:
            events: DataFrame with standard columns (bg0, deviation,
                    category, bolus_2h, smb_2h, etc.)

        Returns:
            Dict of results to persist as JSON.
        """
        return {
            "experiment": self.EXP_ID,
            "title": self.TITLE,
            "n_events": len(events),
            "note": "Override analyze() in your subclass",
        }

    # ── Result Saving ────────────────────────────────────────────────

    def _results_path(self) -> Path:
        slug = self.EXP_ID.lower().replace("-", "_").replace(" ", "_")
        return EXPERIMENTS_DIR / f"{slug}_results.json"

    def save_results(self):
        """Save results JSON and validation report."""
        output = {
            "experiment": self.EXP_ID,
            "title": self.TITLE,
            "n_events": len(self.events) if self.events is not None else 0,
            "filters": asdict(self.FILTERS),
            "deconfounding": self.DECONFOUNDING,
            "validation": self.validation,
            **(self.results or {}),
        }

        path = self._results_path()
        path.write_text(json.dumps(output, indent=2, default=str))

    # ── Convenience Methods ──────────────────────────────────────────

    def corrections(self) -> pd.DataFrame:
        """Get correction events only."""
        if self.events is None:
            raise RuntimeError("Call run() or extract_events() first")
        if "category" not in self.events.columns:
            raise RuntimeError("Events not categorized. Add 'categorize' to DECONFOUNDING.")
        return self.events[self.events["category"] == "correction"].copy()

    def meals(self) -> pd.DataFrame:
        """Get meal events only."""
        if self.events is None:
            raise RuntimeError("Call run() or extract_events() first")
        return self.events[self.events["category"] == "meal"].copy()

    def by_controller(self) -> Dict[str, pd.DataFrame]:
        """Split events by controller type."""
        if self.events is None:
            raise RuntimeError("Call run() or extract_events() first")
        return {
            ctrl: group
            for ctrl, group in self.events.groupby("controller")
        }

    def by_patient(self) -> Dict[str, pd.DataFrame]:
        """Split events by patient_id."""
        if self.events is None:
            raise RuntimeError("Call run() or extract_events() first")
        return {
            pid: group
            for pid, group in self.events.groupby("patient_id")
        }

    def summary(self) -> str:
        """Print summary of extracted events and validation."""
        lines = [
            f"{self.EXP_ID}: {self.TITLE}",
            f"  Events: {len(self.events):,}" if self.events is not None else "  Events: not loaded",
        ]
        if self.events is not None and "category" in self.events.columns:
            counts = self.events["category"].value_counts()
            for cat, n in counts.items():
                lines.append(f"    {cat}: {n:,}")
        if self.validation:
            lines.append(f"  Validation: {self.validation.get('overall', 'N/A')}")
        return "\n".join(lines)
