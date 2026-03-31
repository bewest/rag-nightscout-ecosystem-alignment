from .encoder import FixtureEncoder, CGMDataset, load_fixtures_to_dataset, generate_training_vectors
from .sim_adapter import load_conformance_to_dataset, load_conformance_vectors
from .model import CGMTransformerAE
from .toolbox import CGMTransformerVAE, ConditionedTransformer, CGMDenoisingDiffusion, ContrastiveLoss

__all__ = [
    # Data pipeline
    'FixtureEncoder',
    'CGMDataset',
    'load_fixtures_to_dataset',
    'generate_training_vectors',
    'load_conformance_to_dataset',
    'load_conformance_vectors',
    # Model architectures
    'CGMTransformerAE',
    'CGMTransformerVAE',
    'ConditionedTransformer',
    'CGMDenoisingDiffusion',
    'ContrastiveLoss',
]
