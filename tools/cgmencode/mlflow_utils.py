"""Shared MLflow helpers for cgmencode experiments.

These helpers keep MLflow optional at import time so the rest of the
codebase can still run in environments where the dependency has not yet
been installed. When MLflow is available, runs default to a local
SQLite-backed tracking store plus a git-ignored artifact root under
``externals/mlflow/`` unless ``MLFLOW_TRACKING_URI`` is set.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACKING_DB = ROOT / 'externals' / 'mlflow' / 'mlflow.db'
DEFAULT_ARTIFACT_DIR = ROOT / 'externals' / 'mlflow' / 'artifacts'
DEFAULT_EXPERIMENT_NAME = 'cgmencode'
DISABLE_ENV = 'CGMENCODE_DISABLE_MLFLOW'
EXPERIMENT_ENV = 'CGMENCODE_MLFLOW_EXPERIMENT'


def _import_mlflow():
    try:
        import mlflow  # type: ignore
    except ImportError:
        return None
    return mlflow


def is_enabled() -> bool:
    disabled = os.getenv(DISABLE_ENV, '').strip().lower()
    if disabled in {'1', 'true', 'yes', 'on'}:
        return False
    return _import_mlflow() is not None


def get_tracking_uri() -> str:
    tracking_uri = os.getenv('MLFLOW_TRACKING_URI')
    if tracking_uri:
        return tracking_uri
    DEFAULT_TRACKING_DB.parent.mkdir(parents=True, exist_ok=True)
    return f'sqlite:///{DEFAULT_TRACKING_DB.resolve()}'


def get_artifact_root() -> str:
    DEFAULT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_ARTIFACT_DIR.resolve().as_uri()


def _ensure_experiment(mlflow, experiment_name: str) -> None:
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is not None:
        return
    artifact_location = f'{get_artifact_root().rstrip("/")}/{experiment_name}'
    client = mlflow.tracking.MlflowClient()
    client.create_experiment(experiment_name, artifact_location=artifact_location)


def configure_tracking(experiment_name: str | None = None):
    mlflow = _import_mlflow()
    if mlflow is None or not is_enabled():
        return None
    tracking_uri = get_tracking_uri()
    mlflow.set_tracking_uri(tracking_uri)
    resolved_experiment = experiment_name or os.getenv(EXPERIMENT_ENV, DEFAULT_EXPERIMENT_NAME)
    if tracking_uri.startswith('sqlite:'):
        _ensure_experiment(mlflow, resolved_experiment)
    mlflow.set_experiment(resolved_experiment)
    return mlflow


def has_active_run() -> bool:
    mlflow = _import_mlflow()
    if mlflow is None or not is_enabled():
        return False
    return mlflow.active_run() is not None


def _git_value(*args: str) -> str | None:
    try:
        proc = subprocess.run(
            ['git', *args],
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = proc.stdout.strip()
    return value or None


def _workspace_lock_hash() -> str | None:
    lockfile = ROOT / 'workspace.lock.json'
    if not lockfile.exists():
        return None
    digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
    return digest[:16]


def default_tags(extra: dict[str, Any] | None = None) -> dict[str, str]:
    tags: dict[str, str] = {
        'project': 'cgmencode',
        'workspace_root': str(ROOT),
    }
    commit = _git_value('rev-parse', 'HEAD')
    branch = _git_value('rev-parse', '--abbrev-ref', 'HEAD')
    if commit:
        tags['git_commit'] = commit
    if branch:
        tags['git_branch'] = branch
    lock_hash = _workspace_lock_hash()
    if lock_hash:
        tags['workspace_lock_sha256'] = lock_hash
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            tags[key] = str(value)
    return tags


def _flatten_scalars(
    data: Any,
    prefix: str = '',
    *,
    include_strings: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            child = f'{prefix}.{key}' if prefix else str(key)
            result.update(_flatten_scalars(value, child, include_strings=include_strings))
        return result
    if isinstance(data, (list, tuple)):
        if include_strings:
            result[prefix] = json.dumps(data, default=str, sort_keys=True)
        return result
    if isinstance(data, bool):
        result[prefix] = int(data)
        return result
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        result[prefix] = data
        return result
    if include_strings and isinstance(data, (str, Path)):
        result[prefix] = str(data)
    return result


def _sanitize_key(key: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9_.:/ -]', '_', key).strip()
    return sanitized or 'value'


def log_params(params: dict[str, Any], prefix: str | None = None) -> None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return
    flat = _flatten_scalars(params, prefix or '', include_strings=True)
    if flat:
        mlflow.log_params({_sanitize_key(k): str(v) for k, v in flat.items() if k})


def log_metrics(metrics: dict[str, Any], prefix: str | None = None, step: int | None = None) -> None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return
    flat = _flatten_scalars(metrics, prefix or '', include_strings=False)
    if not flat:
        return
    if step is None:
        mlflow.log_metrics({_sanitize_key(k): float(v) for k, v in flat.items() if k})
        return
    for key, value in flat.items():
        if key:
            mlflow.log_metric(_sanitize_key(key), float(value), step=step)


def log_text(text: str, artifact_file: str) -> None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return
    mlflow.log_text(text, artifact_file)


def log_dict(data: dict[str, Any], artifact_file: str) -> None:
    log_text(json.dumps(data, indent=2, default=str, sort_keys=True), artifact_file)


def log_artifact(path: str | os.PathLike[str], artifact_path: str | None = None) -> None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return
    artifact = Path(path)
    if artifact.exists():
        mlflow.log_artifact(str(artifact), artifact_path=artifact_path)


def log_artifacts(path: str | os.PathLike[str], artifact_path: str | None = None) -> None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return
    artifact_dir = Path(path)
    if artifact_dir.exists():
        mlflow.log_artifacts(str(artifact_dir), artifact_path=artifact_path)


@contextlib.contextmanager
def start_run(
    run_name: str | None = None,
    *,
    nested: bool = False,
    experiment_name: str | None = None,
    tags: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
):
    mlflow = configure_tracking(experiment_name=experiment_name)
    if mlflow is None:
        yield None
        return

    with mlflow.start_run(run_name=run_name, nested=nested):
        merged_tags = default_tags(tags)
        if merged_tags:
            mlflow.set_tags(merged_tags)
        if params:
            log_params(params)
        yield mlflow.active_run()
