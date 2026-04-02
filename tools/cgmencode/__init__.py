from .schema import (
    NORMALIZATION_SCALES, SCALE_ARRAY, FEATURE_NAMES, NUM_FEATURES,
    STATE_IDX, ACTION_IDX, TIME_IDX, ALL_VALS_IDX,
    GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX,
    # Extended schema (agentic delivery)
    NUM_FEATURES_EXTENDED, EXTENDED_FEATURE_NAMES, EXTENDED_SCALE_ARRAY,
    CONTEXT_IDX, WEEKDAY_IDX, OVERRIDE_IDX, DYNAMICS_IDX, TEMPORAL_IDX,
    OVERRIDE_TYPES, OVERRIDE_TYPE_NAMES, TIME_SINCE_CAP_MIN,
)
from .encoder import FixtureEncoder, CGMDataset, load_fixtures_to_dataset, generate_training_vectors
from .sim_adapter import load_conformance_to_dataset, load_conformance_vectors
from .model import CGMTransformerAE, CGMGroupedEncoder, train_one_epoch, eval_loss
from .toolbox import CGMTransformerVAE, ConditionedTransformer, CGMDenoisingDiffusion, ContrastiveLoss
from .uncertainty import mc_predict, hypo_probability, hyper_probability, prediction_interval
from .state_tracker import ISFCRTracker, DriftDetector
from .label_events import (
    extract_override_events, classify_override_reason,
    build_pre_event_windows, extract_extended_tabular,
    build_classifier_dataset, compute_rolling_features,
    EXTENDED_LABEL_MAP, OVERRIDE_REASON_MAP,
)
from .event_classifier import (
    train_event_classifier, predict_events, score_override_candidates,
    compute_per_class_metrics,
)
from .state_tracker import PatternStateMachine
from .forecast import HierarchicalForecaster, ScenarioSimulator, BacktestEngine
from .hindcast_composite import (
    run_decision, run_drift_scan, run_calibration,
    display_decision, display_drift_scan, display_calibration,
)

__all__ = [
    # Schema (core)
    'NORMALIZATION_SCALES', 'SCALE_ARRAY', 'FEATURE_NAMES', 'NUM_FEATURES',
    'STATE_IDX', 'ACTION_IDX', 'TIME_IDX', 'ALL_VALS_IDX',
    'GLUCOSE_CLIP_MIN', 'GLUCOSE_CLIP_MAX',
    # Schema (extended — agentic delivery)
    'NUM_FEATURES_EXTENDED', 'EXTENDED_FEATURE_NAMES', 'EXTENDED_SCALE_ARRAY',
    'CONTEXT_IDX', 'WEEKDAY_IDX', 'OVERRIDE_IDX', 'DYNAMICS_IDX', 'TEMPORAL_IDX',
    'OVERRIDE_TYPES', 'OVERRIDE_TYPE_NAMES', 'TIME_SINCE_CAP_MIN',
    # Data pipeline
    'FixtureEncoder',
    'CGMDataset',
    'load_fixtures_to_dataset',
    'generate_training_vectors',
    'load_conformance_to_dataset',
    'load_conformance_vectors',
    # Model architectures
    'CGMTransformerAE',
    'CGMGroupedEncoder',
    'train_one_epoch',
    'eval_loss',
    'CGMTransformerVAE',
    'ConditionedTransformer',
    'CGMDenoisingDiffusion',
    'ContrastiveLoss',
    # Uncertainty quantification
    'mc_predict',
    'hypo_probability',
    'hyper_probability',
    'prediction_interval',
    # State tracking
    'ISFCRTracker',
    'DriftDetector',
    'PatternStateMachine',
    # Event label pipeline (agentic delivery)
    'extract_override_events',
    'classify_override_reason',
    'build_pre_event_windows',
    'extract_extended_tabular',
    'build_classifier_dataset',
    'compute_rolling_features',
    'EXTENDED_LABEL_MAP',
    'OVERRIDE_REASON_MAP',
    # Event classifier
    'train_event_classifier',
    'predict_events',
    'score_override_candidates',
    'compute_per_class_metrics',
    # Forecast pipeline
    'HierarchicalForecaster',
    'ScenarioSimulator',
    'BacktestEngine',
    # Composite hindcast modes
    'run_decision',
    'run_drift_scan',
    'run_calibration',
    'display_decision',
    'display_drift_scan',
    'display_calibration',
]
