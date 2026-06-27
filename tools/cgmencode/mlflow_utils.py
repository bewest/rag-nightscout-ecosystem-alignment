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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACKING_DB = ROOT / 'externals' / 'mlflow' / 'mlflow.db'
DEFAULT_ARTIFACT_DIR = ROOT / 'externals' / 'mlflow' / 'artifacts'
DEFAULT_EXPERIMENT_NAME = 'cgmencode'
DISABLE_ENV = 'CGMENCODE_DISABLE_MLFLOW'
EXPERIMENT_ENV = 'CGMENCODE_MLFLOW_EXPERIMENT'
RUN_CONTEXT_SCHEMA_VERSION = '1.0'
STRUCTURED_ARTIFACT_SCHEMA_VERSION = '1.0'


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


def _sanitize_filename_component(value: str) -> str:
    sanitized = re.sub(r'[^A-Za-z0-9_.-]+', '_', value.strip())
    return sanitized.strip('._') or 'artifact'


def resolve_patient_ids(
    patient_paths: list[str] | tuple[str, ...] | None = None,
    *,
    patients_dir: str | os.PathLike[str] | None = None,
) -> list[str]:
    ids: set[str] = set()
    for raw_path in patient_paths or ():
        path = Path(raw_path)
        if path.name == 'training' and path.parent.name:
            ids.add(path.parent.name)
        elif path.name:
            ids.add(path.name)
    if patients_dir:
        base = Path(patients_dir)
        if base.exists():
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                training = child / 'training'
                if training.is_dir():
                    ids.add(child.name)
    return sorted(ids)


def cohort_fingerprint(patient_ids: list[str] | tuple[str, ...]) -> str:
    digest = hashlib.sha256(
        json.dumps(sorted(patient_ids), separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    return digest[:16]


def build_run_context(
    *,
    task_type: str,
    result_type: str,
    artifact_role: str,
    patient_paths: list[str] | tuple[str, ...] | None = None,
    patients_dir: str | os.PathLike[str] | None = None,
    data_source: str = 'nightscout',
    split_strategy: str | None = None,
    split_details: dict[str, Any] | None = None,
    horizon_minutes: int | None = None,
    model_family: str | None = None,
    experiment_family: str | None = None,
    extra_tags: dict[str, Any] | None = None,
    extra_params: dict[str, Any] | None = None,
    extra_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patient_ids = resolve_patient_ids(patient_paths, patients_dir=patients_dir)
    manifest: dict[str, Any] = {
        'schema_version': RUN_CONTEXT_SCHEMA_VERSION,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'task_type': task_type,
        'result_type': result_type,
        'artifact_role': artifact_role,
        'data_source': data_source,
        'patient_ids': patient_ids,
        'n_patients': len(patient_ids),
        'cohort_hash': cohort_fingerprint(patient_ids) if patient_ids else None,
        'split_strategy': split_strategy,
        'split_details': split_details or {},
        'horizon_minutes': horizon_minutes,
        'model_family': model_family,
        'experiment_family': experiment_family,
    }
    if extra_manifest:
        manifest.update(extra_manifest)

    tags: dict[str, str] = {
        'task_type': task_type,
        'result_type': result_type,
        'artifact_role': artifact_role,
        'data_source': data_source,
    }
    if model_family:
        tags['model_family'] = model_family
    if experiment_family:
        tags['experiment_family'] = experiment_family
    if extra_tags:
        for key, value in extra_tags.items():
            if value is None:
                continue
            tags[str(key)] = str(value)

    params: dict[str, Any] = {
        'task_type': task_type,
        'result_type': result_type,
        'artifact_role': artifact_role,
        'data_source': data_source,
        'n_patients': len(patient_ids),
        'cohort_hash': manifest['cohort_hash'],
    }
    if split_strategy:
        params['split_strategy'] = split_strategy
    if horizon_minutes is not None:
        params['horizon_minutes'] = horizon_minutes
    if model_family:
        params['model_family'] = model_family
    if experiment_family:
        params['experiment_family'] = experiment_family
    if extra_params:
        params.update(extra_params)

    return {
        'tags': tags,
        'params': params,
        'manifest': manifest,
    }


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


def log_run_context(context: dict[str, Any], artifact_file: str = 'metadata/run_context.json') -> None:
    if not has_active_run():
        return
    manifest = context.get('manifest', context)
    if isinstance(manifest, dict):
        log_dict(manifest, artifact_file)


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


def log_model_artifact(
    name: str,
    payload: dict[str, Any],
    *,
    artifact_type: str = 'structured-model',
    artifact_path: str = 'models',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_name = _sanitize_filename_component(name)
    artifact_file = f'{artifact_path.rstrip("/")}/{artifact_name}.json'
    envelope = {
        'schema_version': STRUCTURED_ARTIFACT_SCHEMA_VERSION,
        'artifact_type': artifact_type,
        'name': artifact_name,
        'metadata': metadata or {},
        'payload': payload,
    }
    if has_active_run():
        log_dict(envelope, artifact_file)
    return envelope


def log_parameter_artifact(
    name: str,
    payload: dict[str, Any],
    *,
    parameter_type: str,
    artifact_path: str = 'parameters',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_metadata = dict(metadata or {})
    merged_metadata['parameter_type'] = parameter_type
    return log_model_artifact(
        name,
        payload,
        artifact_type='parameter-artifact',
        artifact_path=artifact_path,
        metadata=merged_metadata,
    )


def log_pyfunc_model(
    artifact_path: str,
    *,
    python_model: Any,
    artifacts: dict[str, str] | None = None,
    code_paths: list[str] | None = None,
    input_example: Any = None,
) -> str | None:
    mlflow = _import_mlflow()
    if mlflow is None or not has_active_run():
        return None
    safe_name = _sanitize_filename_component(artifact_path.replace('/', '_'))
    mlflow.pyfunc.log_model(
        name=safe_name,
        python_model=python_model,
        artifacts=artifacts or {},
        code_paths=code_paths,
        input_example=input_example,
    )
    run = mlflow.active_run()
    if run is None:
        return None
    return f"runs:/{run.info.run_id}/{safe_name}"


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
