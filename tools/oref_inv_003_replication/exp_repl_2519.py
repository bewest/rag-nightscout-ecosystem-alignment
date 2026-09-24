#!/usr/bin/env python3
"""
EXP-2519: Does the 18-feature algorithm-neutral set hold up under patient-grouped CV?

EXP-2514 found the 18-feature PK-only set (glucose, rate of change,
acceleration, time of day, 13 PK channels) scored a higher 4h hypo AUC than
the 32-feature OREF set (0.8151 vs 0.8031). That comparison used
StratifiedKFold(shuffle=True) over rows, so rows from one patient, five
minutes apart, sit in both train and test folds. This experiment re-scores
the same three feature sets two ways:

  row      StratifiedKFold(shuffle=True), as EXP-2511..2514 did
  patient  StratifiedGroupKFold grouped by patient_id: no patient is in both
           a train and a test fold

on two cohorts:

  exp2514  the 19 patients EXP-2514 used (11 Loop, 8 ODC AAPS)
  current  every patient in the current training grid

On another data holder's corpus (a grid built by `ns2parquet convert-all`),
only the `current` cohort is scored, and the result names no patient.

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2519
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2519 --tiny
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2519 \
        --parquet-dir <their-parquet> --out <out>/tasks/exp_2519.json
"""

import argparse
import json
import time
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

from .data_bridge import OREF_FEATURES, load_patients_with_features
from .exp_repl_2511 import LGB_PARAMS
from .pk_bridge import (ALL_PK_FEATURES, add_pk_features_to_grid,
                        get_oref32_with_pk_replacements, get_pk_only_features)

PARQUET = "externals/ns-parquet/training"
OUT = "tools/oref_inv_003_replication/results/exp_2519_grouped_cv.json"


def _cv(X, y, groups, n_folds, grouped):
    if grouped:
        splitter = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=42)
        splits = splitter.split(X, y, groups)
    else:
        splitter = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
        splits = splitter.split(X, y)
    aucs = []
    for tr, te in splits:
        if len(np.unique(y[te])) < 2:
            continue
        model = lgb.LGBMClassifier(**LGB_PARAMS)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X.iloc[tr], y[tr])
        aucs.append(roc_auc_score(y[te], model.predict_proba(X.iloc[te])[:, 1]))
    return {"auc": float(np.mean(aucs)), "std": float(np.std(aucs)),
            "folds": [round(a, 4) for a in aucs]}


def build_frame(tiny, parquet_dir=PARQUET):
    df = load_patients_with_features(parquet_dir)
    grid = pd.read_parquet(Path(parquet_dir) / "grid.parquet")
    if tiny:
        keep = ["a", "b", "odc-86025410"]
        df = df[df["patient_id"].isin(keep)].copy()
        grid = grid[grid["patient_id"].isin(keep)]
    enriched = add_pk_features_to_grid(grid, verbose=False)
    for col in ALL_PK_FEATURES + ["glucose_roc", "glucose_accel"]:
        if col in enriched.columns and col not in df.columns:
            df[col] = enriched[col].values
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--tiny", action="store_true")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--parquet-dir", default=PARQUET)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    ours = Path(args.parquet_dir) == Path(PARQUET)

    t0 = time.time()
    df = build_frame(args.tiny, args.parquet_dir)
    oref = [f for f in OREF_FEATURES if f in df.columns]
    sets = {"oref32": oref,
            "oref32_pk_replaced": get_oref32_with_pk_replacements(oref),
            "pk_only_18": get_pk_only_features()}
    patients = sorted(df["patient_id"].unique())
    cohorts = {"current": patients}
    exp2514 = [p for p in patients if len(p) == 1 or p.startswith("odc-")]
    if ours and not args.tiny:
        cohorts["exp2514"] = exp2514

    folds = 2 if args.tiny else args.folds
    results = {"cohorts": {}, "feature_sets": {k: v for k, v in sets.items()}}
    for cname, pts in cohorts.items():
        sub = df[df["patient_id"].isin(pts)]
        crow = {"patients": len(pts), "loop_or_ns": sum(1 for p in pts if not p.startswith("odc-")),
                "odc": sum(1 for p in pts if p.startswith("odc-"))}
        for target in ("hypo_4h", "hyper_4h"):
            s = sub.dropna(subset=["cgm_mgdl", target])
            y = s[target].values.astype(int)
            groups = s["patient_id"].values
            crow[f"{target}_rows"] = int(len(s))
            crow[f"{target}_prevalence"] = round(float(y.mean()), 4)
            for sname, feats in sets.items():
                X = s[[f for f in feats if f in s.columns]].fillna(0)
                for mode in ("row", "patient"):
                    r = _cv(X, y, groups, folds, grouped=(mode == "patient"))
                    r["n_features"] = X.shape[1]
                    crow[f"{target}|{sname}|{mode}"] = r
                    print(f"  {cname:8s} {target:8s} {sname:20s} {mode:8s} "
                          f"AUC {r['auc']:.4f} ± {r['std']:.4f}  ({X.shape[1]} features)",
                          flush=True)
        results["cohorts"][cname] = crow

    results["elapsed_seconds"] = round(time.time() - t0)
    if not args.tiny:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=1) + "\n")
        print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
