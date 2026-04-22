"""Tests for SimpsonFactsLoader."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from tools.cgmencode.production.simpson_facts_loader import (
    SimpsonAuditionFacts,
    SimpsonFactsLoader,
)


def _write_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    sim = tmp_path / "exp-2853_simpson_decomposition.parquet"
    stab = tmp_path / "exp-2856_per_patient_stability.parquet"
    boot = tmp_path / "exp-2859_bootstrap_simpson.parquet"
    pd.DataFrame({
        "patient_id": ["a", "b", "c"],
        "simpson_paradox": [False, True, True],
        "beta_fast_uph_per_mgdl": [0.001, 0.001, -0.001],
    }).to_parquet(sim, index=False)
    pd.DataFrame({
        "patient_id": ["a", "b"],
        "frac_agree_with_overall": [0.9, 0.25],
    }).to_parquet(stab, index=False)
    # Empty bootstrap by default; tests that need it can write more
    pd.DataFrame({"patient_id": [], "p_simpson": []}).to_parquet(boot, index=False)
    return sim, stab, boot


def test_loader_round_trip(tmp_path):
    sim, stab, boot = _write_artifacts(tmp_path)
    loader = SimpsonFactsLoader(
        simpson_path=sim, stability_path=stab, bootstrap_path=boot,
    )

    a = loader.get("a")
    assert a.simpson_paradox is False
    assert a.simpson_stability_frac == 0.9

    b = loader.get("b")
    assert b.simpson_paradox is True
    assert b.simpson_stability_frac == 0.25

    # In Simpson but no stability artifact for c
    c = loader.get("c")
    assert c.simpson_paradox is True
    assert c.simpson_stability_frac is None

    # Unknown patient: both None (caller falls back to phenotype proxy)
    z = loader.get("zzz")
    assert z == SimpsonAuditionFacts(None, None)


def test_loader_missing_files_returns_empty(tmp_path):
    loader = SimpsonFactsLoader(
        simpson_path=tmp_path / "nope1.parquet",
        stability_path=tmp_path / "nope2.parquet",
        bootstrap_path=tmp_path / "nope3.parquet",
    )
    assert loader.n_patients == 0
    assert loader.get("a") == SimpsonAuditionFacts(None, None)


def test_loader_integration_with_audition_inputs(tmp_path):
    """Loader output plugs directly into AuditionInputs and triggers
    correct severity per EXP-2856."""
    from tools.cgmencode.production.audition_matrix import (
        AuditionInputs,
        ControllerType,
        classify_triage_flags,
    )

    sim, stab, boot = _write_artifacts(tmp_path)
    loader = SimpsonFactsLoader(
        simpson_path=sim, stability_path=stab, bootstrap_path=boot,
    )

    # Patient b: Simpson=True, stability=0.25 → LOW severity
    facts_b = loader.get("b")
    inputs_b = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        simpson_paradox=facts_b.simpson_paradox,
        simpson_stability_frac=facts_b.simpson_stability_frac,
    )
    flags_b = classify_triage_flags(inputs_b)
    warn_b = [f for f in flags_b if f.name == "window_dependence_warning"]
    assert warn_b and warn_b[0].severity == "low"

    # Patient a: Simpson=False → no warning
    facts_a = loader.get("a")
    inputs_a = AuditionInputs(
        controller=ControllerType.LOOP,
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=0.6,
        simpson_paradox=facts_a.simpson_paradox,
        simpson_stability_frac=facts_a.simpson_stability_frac,
    )
    flags_a = classify_triage_flags(inputs_a)
    warn_a = [f for f in flags_a if f.name == "window_dependence_warning"]
    assert not warn_a
