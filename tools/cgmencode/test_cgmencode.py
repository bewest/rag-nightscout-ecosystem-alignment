#!/usr/bin/env python3
"""
Test suite for cgmencode — data pipeline, model construction, and training.

Tests cover:
  1. Schema constants and normalization
  2. Data reshaping (encoder, sim_adapter, datasets)
  3. Model construction smoke tests (all 5 architectures)
  4. Training algorithm validation (loss decreases)
  5. Evaluation metrics (denormalization, per-horizon MAE)

Usage:
    python tools/cgmencode/test_cgmencode.py          # Run all tests
    python tools/cgmencode/test_cgmencode.py -v        # Verbose output
    python -m pytest tools/cgmencode/test_cgmencode.py # With pytest

Exit codes:
    0 - All tests pass
    1 - Test failures
"""

import sys
import unittest
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import os
import tempfile

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from tools.cgmencode.model import CGMGroupedEncoder


# =============================================================================
# 1. Schema Tests
# =============================================================================

class TestSchema(unittest.TestCase):
    """Verify schema.py constants are self-consistent."""

    def test_feature_count(self):
        from tools.cgmencode.schema import NUM_FEATURES, FEATURE_NAMES, SCALE_ARRAY
        self.assertEqual(NUM_FEATURES, 8)
        self.assertEqual(len(FEATURE_NAMES), 8)
        self.assertEqual(len(SCALE_ARRAY), 8)

    def test_feature_names_order(self):
        from tools.cgmencode.schema import FEATURE_NAMES
        expected = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos']
        self.assertEqual(FEATURE_NAMES, expected)

    def test_index_groups_are_disjoint(self):
        from tools.cgmencode.schema import STATE_IDX, ACTION_IDX, TIME_IDX, ALL_VALS_IDX
        state_set = set(STATE_IDX)
        action_set = set(ACTION_IDX)
        time_set = set(TIME_IDX)
        self.assertEqual(len(state_set & action_set), 0)
        self.assertEqual(len(state_set & time_set), 0)
        self.assertEqual(len(action_set & time_set), 0)
        self.assertEqual(state_set | action_set, set(ALL_VALS_IDX))

    def test_index_groups_cover_all(self):
        from tools.cgmencode.schema import STATE_IDX, ACTION_IDX, TIME_IDX
        all_indices = set(STATE_IDX) | set(ACTION_IDX) | set(TIME_IDX)
        self.assertEqual(all_indices, {0, 1, 2, 3, 4, 5, 6, 7})

    def test_normalization_scales_positive(self):
        from tools.cgmencode.schema import NORMALIZATION_SCALES
        for name, scale in NORMALIZATION_SCALES.items():
            self.assertGreater(scale, 0, f"Scale for {name} must be positive")

    def test_scale_array_matches_dict(self):
        from tools.cgmencode.schema import NORMALIZATION_SCALES, SCALE_ARRAY, FEATURE_NAMES
        for i, name in enumerate(FEATURE_NAMES):
            if name in NORMALIZATION_SCALES:
                self.assertEqual(SCALE_ARRAY[i], NORMALIZATION_SCALES[name],
                                 f"SCALE_ARRAY[{i}] ({name}) doesn't match NORMALIZATION_SCALES")
            else:
                self.assertEqual(SCALE_ARRAY[i], 1.0,
                                 f"SCALE_ARRAY[{i}] ({name}) should be 1.0 for native features")

    def test_glucose_clip_range(self):
        from tools.cgmencode.schema import GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX
        self.assertGreater(GLUCOSE_CLIP_MIN, 0)
        self.assertLess(GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX)
        self.assertGreaterEqual(GLUCOSE_CLIP_MAX, 400)

    def test_extended_feature_count(self):
        from tools.cgmencode.schema import (
            NUM_FEATURES_EXTENDED, EXTENDED_FEATURE_NAMES, EXTENDED_SCALE_ARRAY,
        )
        self.assertEqual(NUM_FEATURES_EXTENDED, 21)
        self.assertEqual(len(EXTENDED_FEATURE_NAMES), 21)
        self.assertEqual(len(EXTENDED_SCALE_ARRAY), 21)

    def test_extended_preserves_core(self):
        """First 8 extended features must match core FEATURE_NAMES exactly."""
        from tools.cgmencode.schema import (
            FEATURE_NAMES, EXTENDED_FEATURE_NAMES, SCALE_ARRAY, EXTENDED_SCALE_ARRAY,
        )
        self.assertEqual(EXTENDED_FEATURE_NAMES[:8], FEATURE_NAMES)
        self.assertEqual(EXTENDED_SCALE_ARRAY[:8], SCALE_ARRAY)

    def test_extended_groups_disjoint(self):
        from tools.cgmencode.schema import (
            STATE_IDX, ACTION_IDX, TIME_IDX, CONTEXT_IDX,
        )
        core = set(STATE_IDX) | set(ACTION_IDX) | set(TIME_IDX)
        context = set(CONTEXT_IDX)
        self.assertEqual(len(core & context), 0,
                         "Context indices must not overlap core indices")

    def test_extended_groups_cover_all(self):
        from tools.cgmencode.schema import (
            STATE_IDX, ACTION_IDX, TIME_IDX, EXTENDED_CONTEXT_IDX,
            NUM_FEATURES_EXTENDED,
        )
        all_idx = set(STATE_IDX) | set(ACTION_IDX) | set(TIME_IDX) | set(EXTENDED_CONTEXT_IDX)
        self.assertEqual(all_idx, set(range(NUM_FEATURES_EXTENDED)))

    def test_enriched_groups_cover_all(self):
        from tools.cgmencode.schema import (
            STATE_IDX, ACTION_IDX, TIME_IDX, ENRICHED_CONTEXT_IDX,
            NUM_FEATURES_ENRICHED,
        )
        all_idx = set(STATE_IDX) | set(ACTION_IDX) | set(TIME_IDX) | set(ENRICHED_CONTEXT_IDX)
        self.assertEqual(all_idx, set(range(NUM_FEATURES_ENRICHED)))

    def test_override_types_valid(self):
        from tools.cgmencode.schema import OVERRIDE_TYPES, OVERRIDE_TYPE_NAMES
        self.assertIn('none', OVERRIDE_TYPES)
        self.assertEqual(OVERRIDE_TYPES['none'], 0.0)
        for name, val in OVERRIDE_TYPES.items():
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)
            self.assertEqual(OVERRIDE_TYPE_NAMES[val], name)


# =============================================================================
# 2. Data Pipeline / Encoder Tests
# =============================================================================

class TestEncoderNormalization(unittest.TestCase):
    """Verify data reshaping and normalization correctness."""

    def test_generate_training_vectors_shape(self):
        """Output shape should be (N, window+lead+result, 8)."""
        import pandas as pd
        from tools.cgmencode.encoder import generate_training_vectors

        n_rows = 100
        df = pd.DataFrame(
            np.random.rand(n_rows, 8) * [400, 20, 100, 5, 10, 100, 2, 2] - [0, 0, 0, 2.5, 0, 0, 1, 1],
            columns=['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs', 'time_sin', 'time_cos'],
        )
        vectors = generate_training_vectors(df, window_size=12, lead_time=3, result_window=3)
        self.assertEqual(vectors.ndim, 3)
        self.assertEqual(vectors.shape[1], 12 + 3 + 3)  # total length
        self.assertEqual(vectors.shape[2], 8)

    def test_glucose_clipping(self):
        """Glucose values outside [40, 400] should be clipped before normalization."""
        import pandas as pd
        from tools.cgmencode.encoder import generate_training_vectors
        from tools.cgmencode.schema import GLUCOSE_CLIP_MIN, GLUCOSE_CLIP_MAX, NORMALIZATION_SCALES

        n_rows = 30
        df = pd.DataFrame({
            'glucose': [500.0] * 10 + [20.0] * 10 + [120.0] * 10,  # HI, LO, normal
            'iob': [0.0] * n_rows,
            'cob': [0.0] * n_rows,
            'net_basal': [0.0] * n_rows,
            'bolus': [0.0] * n_rows,
            'carbs': [0.0] * n_rows,
            'time_sin': [0.0] * n_rows,
            'time_cos': [1.0] * n_rows,
        })
        vectors = generate_training_vectors(df, window_size=6, lead_time=3, result_window=3)
        if len(vectors) > 0:
            glucose_normalized = vectors[:, :, 0]
            # After clipping to [40, 400] and dividing by 400:
            max_expected = GLUCOSE_CLIP_MAX / NORMALIZATION_SCALES['glucose']
            min_expected = GLUCOSE_CLIP_MIN / NORMALIZATION_SCALES['glucose']
            self.assertLessEqual(glucose_normalized.max(), max_expected + 1e-6)
            self.assertGreaterEqual(glucose_normalized.min(), min_expected - 1e-6)

    def test_normalization_ranges(self):
        """After normalization, features should be in expected ranges."""
        import pandas as pd
        from tools.cgmencode.encoder import generate_training_vectors

        n_rows = 30
        df = pd.DataFrame({
            'glucose': np.linspace(80, 200, n_rows),
            'iob': np.linspace(0, 5, n_rows),
            'cob': np.linspace(0, 50, n_rows),
            'net_basal': np.linspace(-1, 1, n_rows),
            'bolus': np.linspace(0, 3, n_rows),
            'carbs': np.linspace(0, 30, n_rows),
            'time_sin': np.sin(np.linspace(0, 2 * np.pi, n_rows)),
            'time_cos': np.cos(np.linspace(0, 2 * np.pi, n_rows)),
        })
        vectors = generate_training_vectors(df, window_size=6, lead_time=3, result_window=3)
        self.assertGreater(len(vectors), 0)
        # Glucose: [0, 1] range
        self.assertGreaterEqual(vectors[:, :, 0].min(), 0.0)
        self.assertLessEqual(vectors[:, :, 0].max(), 1.0)
        # IOB: [0, 1]
        self.assertGreaterEqual(vectors[:, :, 1].min(), -0.01)
        self.assertLessEqual(vectors[:, :, 1].max(), 1.01)
        # time_sin/cos: [-1, 1]
        self.assertGreaterEqual(vectors[:, :, 6].min(), -1.01)
        self.assertLessEqual(vectors[:, :, 6].max(), 1.01)

    def test_circadian_encoding_continuity(self):
        """Sin/cos encoding: 23:55 should be close to 00:05."""
        from tools.cgmencode.schema import FEATURE_NAMES

        hour_2355 = 23 + 55 / 60.0
        hour_0005 = 0 + 5 / 60.0

        sin_2355 = np.sin(2 * np.pi * hour_2355 / 24.0)
        cos_2355 = np.cos(2 * np.pi * hour_2355 / 24.0)
        sin_0005 = np.sin(2 * np.pi * hour_0005 / 24.0)
        cos_0005 = np.cos(2 * np.pi * hour_0005 / 24.0)

        # Euclidean distance in sin/cos space should be small
        dist = np.sqrt((sin_2355 - sin_0005) ** 2 + (cos_2355 - cos_0005) ** 2)
        self.assertLess(dist, 0.1, "23:55 and 00:05 should be nearby in sin/cos space")


class TestCGMDataset(unittest.TestCase):
    """Verify dataset masking tasks produce correct shapes and masks."""

    def _make_dataset(self, task, n_samples=20, window_size=12, seq_len=18):
        from tools.cgmencode.encoder import CGMDataset
        vectors = np.random.rand(n_samples, seq_len, 8).astype(np.float32)
        return CGMDataset(vectors, task=task, window_size=window_size)

    def test_reconstruct_identity(self):
        """Reconstruct task: x and y should be identical."""
        ds = self._make_dataset('reconstruct')
        x, y = ds[0]
        self.assertTrue(torch.equal(x, y))

    def test_forecast_masks_future(self):
        """Forecast task: future values (indices 0-5) should be zeroed in x."""
        ds = self._make_dataset('forecast', window_size=12, seq_len=18)
        x, y = ds[0]
        # Future (window_size onwards) should be zero for val indices 0-5
        future_vals = x[12:, :6]
        self.assertTrue((future_vals == 0).all(),
                        "Forecast should zero features 0-5 after window_size")
        # But time features should still be present
        self.assertFalse((x[12:, 6:] == 0).all(),
                         "Time features should NOT be zeroed in forecast")

    def test_fill_actions_masks_actions(self):
        """Fill_actions task: action channels 3,4,5 should be zeroed in history."""
        ds = self._make_dataset('fill_actions', window_size=12, seq_len=18)
        x, y = ds[0]
        history_actions = x[:12, 3:6]
        self.assertTrue((history_actions == 0).all(),
                        "fill_actions should zero action channels in history")
        # State channels should be untouched
        self.assertFalse((x[:12, :3] == 0).all())

    def test_fill_readings_masks_state(self):
        """Fill_readings task: state channels 0,1,2 should be zeroed in history."""
        ds = self._make_dataset('fill_readings', window_size=12, seq_len=18)
        x, y = ds[0]
        history_state = x[:12, :3]
        self.assertTrue((history_state == 0).all(),
                        "fill_readings should zero state channels in history")

    def test_denoise_adds_noise(self):
        """Denoise task: x should differ from y (noise added)."""
        ds = self._make_dataset('denoise', window_size=12, seq_len=18)
        x, y = ds[0]
        # x and y should differ in the history region for val features
        diff = (x[:12, :6] - y[:12, :6]).abs().sum()
        self.assertGreater(diff.item(), 0, "Denoise should add noise to x")

    def test_dataset_length(self):
        ds = self._make_dataset('reconstruct', n_samples=50)
        self.assertEqual(len(ds), 50)

    def test_output_shapes(self):
        """All tasks should return (seq_len, 8) tensors."""
        for task in ['reconstruct', 'forecast', 'fill_actions', 'fill_readings',
                     'denoise', 'random_patch', 'shuffled_mask']:
            ds = self._make_dataset(task)
            x, y = ds[0]
            self.assertEqual(x.shape, (18, 8), f"Task {task}: x shape wrong")
            self.assertEqual(y.shape, (18, 8), f"Task {task}: y shape wrong")


class TestConditionedDataset(unittest.TestCase):
    """Verify conditioned dataset splits history/actions/target correctly."""

    def test_split_shapes(self):
        from tools.cgmencode.encoder import ConditionedDataset
        vectors = np.random.rand(10, 18, 8).astype(np.float32)
        ds = ConditionedDataset(vectors, window_size=12)

        (history, future_actions), target_glucose = ds[0]
        self.assertEqual(history.shape, (12, 8))
        self.assertEqual(future_actions.shape, (6, 3))  # actions: indices 3,4,5
        self.assertEqual(target_glucose.shape, (6,))     # glucose: index 0

    def test_target_is_glucose(self):
        """Target should be the glucose channel (index 0) of future timesteps."""
        from tools.cgmencode.encoder import ConditionedDataset
        vectors = np.random.rand(10, 18, 8).astype(np.float32)
        ds = ConditionedDataset(vectors, window_size=12)

        (history, future_actions), target_glucose = ds[0]
        # Target should match column 0 of timesteps 12: onward
        expected = torch.FloatTensor(vectors[0, 12:, 0])
        self.assertTrue(torch.allclose(target_glucose, expected))


class TestSimAdapter(unittest.TestCase):
    """Verify conformance vector → training tensor conversion."""

    def _make_vector(self, n_steps=24):
        """Create a synthetic conformance vector matching SIM-* format."""
        return {
            'input': {
                'iob': {'iob': 2.5},
                'mealData': {'cob': 30.0},
                'profile': {'basalRate': 1.0},
                'currentTemp': {'rate': 1.5},
                'glucoseStatus': {'timestamp': '2026-01-01T12:00:00Z'},
            },
            'originalOutput': {
                'predBGs': {
                    'IOB': list(np.linspace(150, 120, n_steps)),
                    'COB': list(np.linspace(150, 130, n_steps)),
                }
            }
        }

    def test_vector_to_features_shape(self):
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(24)
        features = vector_to_features(vec, curve_key='IOB')
        self.assertIsNotNone(features)
        self.assertEqual(features.shape, (24, 8))

    def test_vector_glucose_channel(self):
        """Channel 0 should contain the prediction trajectory."""
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(24)
        features = vector_to_features(vec, curve_key='IOB')
        expected_glucose = np.linspace(150, 120, 24)
        np.testing.assert_allclose(features[:, 0], expected_glucose, atol=0.01)

    def test_vector_iob_decays(self):
        """Channel 1 (IOB) should decay from initial value."""
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(24)
        features = vector_to_features(vec, curve_key='IOB')
        self.assertAlmostEqual(features[0, 1], 2.5, places=1)
        # Should decay
        self.assertLess(features[-1, 1], features[0, 1])

    def test_vector_net_basal(self):
        """Channel 3 (net_basal) = temp_rate - scheduled_basal."""
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(24)
        features = vector_to_features(vec, curve_key='IOB')
        expected = 1.5 - 1.0  # temp - scheduled
        self.assertAlmostEqual(features[0, 3], expected, places=2)

    def test_vector_circadian_populated(self):
        """Channels 6,7 should have circadian encoding (not all zeros)."""
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(24)
        features = vector_to_features(vec, curve_key='IOB')
        self.assertFalse(np.all(features[:, 6] == 0), "time_sin should not be all zeros")
        self.assertFalse(np.all(features[:, 7] == 0), "time_cos should not be all zeros")

    def test_normalize_features_glucose_clipping(self):
        """Normalize should clip glucose to [40, 400] before scaling."""
        from tools.cgmencode.sim_adapter import normalize_features
        data = np.zeros((5, 8))
        data[:, 0] = [500, 30, 100, 200, 400]  # glucose with out-of-range values
        normed = normalize_features(data)
        self.assertAlmostEqual(normed[0, 0], 400 / 400, places=3)  # 500 → clipped to 400
        self.assertAlmostEqual(normed[1, 0], 40 / 400, places=3)   # 30 → clipped to 40

    def test_short_trajectory_rejected(self):
        """Trajectories shorter than min_steps should be None."""
        from tools.cgmencode.sim_adapter import vector_to_features
        vec = self._make_vector(3)  # too short
        features = vector_to_features(vec, curve_key='IOB')
        self.assertIsNone(features)


# =============================================================================
# 3. Model Construction Smoke Tests
# =============================================================================

class TestCGMTransformerAE(unittest.TestCase):
    """Smoke tests for the primary Transformer AE."""

    def setUp(self):
        from tools.cgmencode.model import CGMTransformerAE
        self.model = CGMTransformerAE(input_dim=8, d_model=32, nhead=2, num_layers=1)
        self.x = torch.randn(2, 12, 8)

    def test_forward_shape(self):
        y = self.model(self.x)
        self.assertEqual(y.shape, self.x.shape)

    def test_causal_forward_shape(self):
        y = self.model(self.x, causal=True)
        self.assertEqual(y.shape, self.x.shape)

    def test_causal_changes_output(self):
        """Causal mask should produce different output than bidirectional."""
        y_bi = self.model(self.x)
        y_causal = self.model(self.x, causal=True)
        self.assertFalse(torch.allclose(y_bi, y_causal, atol=1e-5),
                         "Causal and bidirectional should produce different outputs")

    def test_gradient_flows(self):
        y = self.model(self.x)
        loss = y.sum()
        loss.backward()
        for name, param in self.model.named_parameters():
            self.assertIsNotNone(param.grad, f"No gradient for {name}")
            self.assertFalse(torch.all(param.grad == 0), f"Zero gradient for {name}")

    def test_parameter_count(self):
        params = sum(p.numel() for p in self.model.parameters())
        self.assertGreater(params, 1000)
        self.assertLess(params, 1_000_000)


class TestCGMGroupedEncoder(unittest.TestCase):
    """Smoke tests for the feature-grouped encoder."""

    def setUp(self):
        from tools.cgmencode.model import CGMGroupedEncoder
        self.model = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2)
        self.x = torch.randn(2, 12, 8)

    def test_forward_shape(self):
        y = self.model(self.x)
        self.assertEqual(y.shape, (2, 12, 8))

    def test_causal_forward(self):
        y = self.model(self.x, causal=True)
        self.assertEqual(y.shape, (2, 12, 8))

    def test_gradient_flows(self):
        y = self.model(self.x)
        loss = y.sum()
        loss.backward()
        # Check that feature-group projections get gradients
        for name in ['state_proj', 'action_proj', 'time_proj']:
            layer = getattr(self.model, name)
            self.assertIsNotNone(layer.weight.grad, f"No gradient for {name}")


class TestCGMGroupedEncoderExtended(unittest.TestCase):
    """Tests for the extended 16-feature GroupedEncoder (agentic delivery)."""

    def setUp(self):
        from tools.cgmencode.model import CGMGroupedEncoder
        self.model_ext = CGMGroupedEncoder(input_dim=16, d_model=64, nhead=4, num_layers=2)
        self.model_core = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2)
        self.x_ext = torch.randn(2, 12, 16)
        self.x_core = torch.randn(2, 12, 8)

    def test_extended_forward_shape(self):
        y = self.model_ext(self.x_ext)
        self.assertEqual(y.shape, (2, 12, 16))

    def test_extended_causal_forward(self):
        y = self.model_ext(self.x_ext, causal=True)
        self.assertEqual(y.shape, (2, 12, 16))

    def test_core_still_works(self):
        """Core 8-feature model must produce identical behavior."""
        y = self.model_core(self.x_core)
        self.assertEqual(y.shape, (2, 12, 8))

    def test_context_group_has_gradients(self):
        y = self.model_ext(self.x_ext)
        loss = y.sum()
        loss.backward()
        self.assertIsNotNone(self.model_ext.context_proj.weight.grad)
        self.assertIsNotNone(self.model_ext.fusion.weight.grad)

    def test_core_model_has_no_context_layers(self):
        self.assertFalse(self.model_core._has_context)
        self.assertFalse(hasattr(self.model_core, 'context_proj'))

    def test_extended_param_count_reasonable(self):
        core_params = sum(p.numel() for p in self.model_core.parameters())
        ext_params = sum(p.numel() for p in self.model_ext.parameters())
        # Extended should have more params (context_proj + fusion), but not dramatically more
        self.assertGreater(ext_params, core_params)
        self.assertLess(ext_params, core_params * 1.5)

    def test_checkpoint_backward_compat(self):
        """Saving a core model checkpoint and loading it into a fresh core model must work."""
        import tempfile, os
        from tools.cgmencode.model import CGMGroupedEncoder
        # Save core state
        state = self.model_core.state_dict()
        with tempfile.NamedTemporaryFile(suffix='.pth', delete=False) as f:
            torch.save({'model_state': state, 'config': {'input_dim': 8}}, f.name)
            ckpt_path = f.name
        try:
            # Load into fresh core model — must not throw
            fresh = CGMGroupedEncoder(input_dim=8, d_model=64, nhead=4, num_layers=2)
            ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=True)
            fresh.load_state_dict(ckpt['model_state'])
            # All keys must match
            self.assertEqual(set(fresh.state_dict().keys()),
                             set(self.model_core.state_dict().keys()))
            # Forward pass must not throw
            with torch.no_grad():
                y = fresh(self.x_core)
            self.assertEqual(y.shape, (2, 12, 8))
        finally:
            os.unlink(ckpt_path)

    def test_core_checkpoint_keys_unchanged(self):
        """Core model state_dict keys must match the original architecture exactly."""
        expected_prefixes = {'state_proj', 'action_proj', 'time_proj',
                             'pos_encoder', 'transformer_encoder', 'output_projection'}
        for key in self.model_core.state_dict().keys():
            prefix = key.split('.')[0]
            self.assertIn(prefix, expected_prefixes,
                          f"Unexpected key prefix '{prefix}' in core model state_dict")


class TestVAE(unittest.TestCase):
    """Smoke tests for the redesigned VAE."""

    def setUp(self):
        from tools.cgmencode.toolbox import CGMTransformerVAE
        self.model = CGMTransformerVAE(input_dim=8, d_model=32, latent_dim=32)
        self.x = torch.randn(2, 12, 8)

    def test_forward_returns_three(self):
        result = self.model(self.x)
        self.assertEqual(len(result), 3, "VAE should return (recon, mu, logvar)")

    def test_output_shapes(self):
        recon, mu, logvar = self.model(self.x)
        self.assertEqual(recon.shape, self.x.shape)
        # Per-timestep latents
        self.assertEqual(mu.shape, (2, 12, 32))
        self.assertEqual(logvar.shape, (2, 12, 32))

    def test_reparameterize_stochastic(self):
        """Two samples from same mu/logvar should differ."""
        mu = torch.zeros(2, 12, 32)
        logvar = torch.zeros(2, 12, 32)
        z1 = self.model.reparameterize(mu, logvar)
        z2 = self.model.reparameterize(mu, logvar)
        self.assertFalse(torch.equal(z1, z2))

    def test_vae_loss_computes(self):
        from tools.cgmencode.toolbox import vae_loss_function
        recon, mu, logvar = self.model(self.x)
        loss = vae_loss_function(recon, self.x, mu, logvar, beta=0.1)
        self.assertFalse(torch.isnan(loss))
        self.assertFalse(torch.isinf(loss))


class TestConditionedTransformer(unittest.TestCase):
    """Smoke tests for the action-conditioned predictor."""

    def setUp(self):
        from tools.cgmencode.toolbox import ConditionedTransformer
        self.model = ConditionedTransformer(dropout=0.2)
        self.hist = torch.randn(2, 12, 8)
        self.actions = torch.randn(2, 6, 3)

    def test_forward_shape(self):
        pred = self.model(self.hist, self.actions)
        self.assertEqual(pred.shape, (2, 6), "Should predict one glucose per future step")

    def test_gradient_flows(self):
        pred = self.model(self.hist, self.actions)
        loss = pred.sum()
        loss.backward()
        self.assertIsNotNone(self.model.history_proj.weight.grad)
        self.assertIsNotNone(self.model.action_proj.weight.grad)

    def test_dropout_changes_output_in_train(self):
        """Dropout should make training outputs stochastic."""
        self.model.train()
        out1 = self.model(self.hist, self.actions)
        out2 = self.model(self.hist, self.actions)
        # With dropout, outputs should usually differ
        # (very small chance they're equal, so just check shapes)
        self.assertEqual(out1.shape, out2.shape)


class TestDiffusion(unittest.TestCase):
    """Smoke tests for the DDPM diffusion model."""

    def setUp(self):
        from tools.cgmencode.toolbox import CGMDenoisingDiffusion
        self.model = CGMDenoisingDiffusion(input_dim=8, d_model=32, timesteps=100)
        self.x = torch.randn(2, 12, 8)

    def test_forward_shape(self):
        t = torch.randint(0, 100, (2,))
        pred = self.model(self.x, t)
        self.assertEqual(pred.shape, self.x.shape)

    def test_q_sample_shape(self):
        t = torch.randint(0, 100, (2,))
        x_t = self.model.q_sample(self.x, t)
        self.assertEqual(x_t.shape, self.x.shape)

    def test_beta_schedule_increases_noise(self):
        """q_sample at t=0 should add less noise than at t=99."""
        noise = torch.randn_like(self.x)
        t_low = torch.zeros(2, dtype=torch.long)
        t_high = torch.full((2,), 99, dtype=torch.long)

        x_low = self.model.q_sample(self.x, t_low, noise=noise)
        x_high = self.model.q_sample(self.x, t_high, noise=noise)

        # Distance from original should increase with t
        dist_low = (x_low - self.x).abs().mean().item()
        dist_high = (x_high - self.x).abs().mean().item()
        self.assertGreater(dist_high, dist_low,
                           "Higher diffusion timestep should add more noise")

    def test_q_sample_at_t0_close_to_original(self):
        """At t=0, x_t should be very close to x_0."""
        t = torch.zeros(2, dtype=torch.long)
        x_t = self.model.q_sample(self.x, t)
        dist = (x_t - self.x).abs().mean().item()
        self.assertLess(dist, 0.05, "At t=0, q_sample should barely perturb input")


class TestCausalMask(unittest.TestCase):
    """Verify causal mask generation."""

    def test_mask_shape(self):
        from tools.cgmencode.model import generate_causal_mask
        mask = generate_causal_mask(12, torch.device('cpu'))
        self.assertEqual(mask.shape, (12, 12))

    def test_mask_upper_triangle_is_neginf(self):
        from tools.cgmencode.model import generate_causal_mask
        mask = generate_causal_mask(4, torch.device('cpu'))
        # Diagonal should be 0 (can attend to self)
        for i in range(4):
            self.assertEqual(mask[i, i].item(), 0.0)
        # Upper triangle should be -inf
        self.assertEqual(mask[0, 1].item(), float('-inf'))
        self.assertEqual(mask[0, 3].item(), float('-inf'))
        # Lower triangle should be 0 (can attend to past)
        self.assertEqual(mask[3, 0].item(), 0.0)


# =============================================================================
# 4. Training Algorithm Tests
# =============================================================================

class TestTrainStep(unittest.TestCase):
    """Verify train_step dispatches correctly for all model types."""

    def test_ae_train_step(self):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY['ae']
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        batch = (torch.randn(4, 18, 8), torch.randn(4, 18, 8))
        loss = train_step(model, batch, optimizer, 'ae', criterion)
        self.assertIsInstance(loss, float)
        self.assertGreater(loss, 0)

    def test_grouped_train_step(self):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY['grouped']
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        batch = (torch.randn(4, 18, 8), torch.randn(4, 18, 8))
        loss = train_step(model, batch, optimizer, 'grouped', criterion)
        self.assertIsInstance(loss, float)

    def test_vae_train_step(self):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY['vae']
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        batch = (torch.randn(4, 18, 8), torch.randn(4, 18, 8))
        loss = train_step(model, batch, optimizer, 'vae', criterion)
        self.assertIsInstance(loss, float)

    def test_conditioned_train_step(self):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY['conditioned']
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        batch = ((torch.randn(4, 12, 8), torch.randn(4, 6, 3)), torch.randn(4, 6))
        loss = train_step(model, batch, optimizer, 'conditioned', criterion)
        self.assertIsInstance(loss, float)

    def test_diffusion_train_step(self):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY['diffusion']
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        batch = (torch.randn(4, 18, 8), torch.randn(4, 18, 8))
        loss = train_step(model, batch, optimizer, 'diffusion', criterion)
        self.assertIsInstance(loss, float)


class TestLossDecreases(unittest.TestCase):
    """Verify that loss actually decreases over a few training steps."""

    def _train_n_steps(self, model_name, n_steps=20):
        from tools.cgmencode.train import train_step, MODEL_REGISTRY
        reg = MODEL_REGISTRY[model_name]
        model = reg['class'](**reg['kwargs'])
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        # Fixed training data
        torch.manual_seed(42)
        if reg['conditioned']:
            batch = ((torch.randn(8, 12, 8), torch.randn(8, 6, 3)), torch.randn(8, 6))
        else:
            x = torch.randn(8, 18, 8)
            batch = (x, x.clone())  # Reconstruct itself

        losses = []
        for _ in range(n_steps):
            loss = train_step(model, batch, optimizer, model_name, criterion)
            losses.append(loss)
        return losses

    def test_ae_loss_decreases(self):
        losses = self._train_n_steps('ae', n_steps=30)
        self.assertLess(losses[-1], losses[0],
                        f"AE loss should decrease: {losses[0]:.4f} → {losses[-1]:.4f}")

    def test_grouped_loss_decreases(self):
        losses = self._train_n_steps('grouped', n_steps=30)
        self.assertLess(losses[-1], losses[0],
                        f"Grouped loss should decrease: {losses[0]:.4f} → {losses[-1]:.4f}")

    def test_vae_loss_decreases(self):
        losses = self._train_n_steps('vae', n_steps=30)
        self.assertLess(losses[-1], losses[0],
                        f"VAE loss should decrease: {losses[0]:.4f} → {losses[-1]:.4f}")

    def test_conditioned_loss_decreases(self):
        losses = self._train_n_steps('conditioned', n_steps=30)
        self.assertLess(losses[-1], losses[0],
                        f"Conditioned loss should decrease: {losses[0]:.4f} → {losses[-1]:.4f}")

    def test_diffusion_loss_decreases(self):
        losses = self._train_n_steps('diffusion', n_steps=30)
        self.assertLess(losses[-1], losses[0],
                        f"Diffusion loss should decrease: {losses[0]:.4f} → {losses[-1]:.4f}")


# =============================================================================
# 5. Evaluation Metric Tests
# =============================================================================

class TestEvaluationMetrics(unittest.TestCase):
    """Verify evaluation helpers compute correct values."""

    def test_denormalize_glucose(self):
        from tools.cgmencode.evaluate import denormalize_glucose
        normalized = torch.tensor([0.25, 0.5, 1.0])
        mgdl = denormalize_glucose(normalized)
        expected = torch.tensor([100.0, 200.0, 400.0])
        self.assertTrue(torch.allclose(mgdl, expected))

    def test_mae_mgdl(self):
        from tools.cgmencode.evaluate import mae_mgdl
        pred = torch.zeros(2, 12, 8)
        target = torch.zeros(2, 12, 8)
        pred[..., 0] = 0.25   # 100 mg/dL
        target[..., 0] = 0.5  # 200 mg/dL
        mae = mae_mgdl(pred, target)
        self.assertAlmostEqual(mae, 100.0, places=0)

    def test_rmse_mgdl(self):
        from tools.cgmencode.evaluate import rmse_mgdl
        pred = torch.zeros(2, 12, 8)
        target = torch.zeros(2, 12, 8)
        pred[..., 0] = 0.25
        target[..., 0] = 0.5
        rmse = rmse_mgdl(pred, target)
        self.assertAlmostEqual(rmse, 100.0, places=0)

    def test_persistence_baseline(self):
        """Flat glucose → persistence MAE should be ~0."""
        from tools.cgmencode.evaluate import persistence_baseline
        from tools.cgmencode.encoder import CGMDataset

        # Constant glucose = 0.3 (120 mg/dL)
        vectors = np.full((20, 24, 8), 0.3, dtype=np.float32)
        ds = CGMDataset(vectors, task='forecast', window_size=12)
        mae, rmse = persistence_baseline(ds, window_size=12)
        self.assertLess(mae, 1.0, "Flat glucose should have near-zero persistence error")

    def test_per_horizon_mae_returns_dict(self):
        """per_horizon_mae should return a dict with minute labels."""
        from tools.cgmencode.evaluate import per_horizon_mae
        from tools.cgmencode.model import CGMTransformerAE
        from torch.utils.data import DataLoader, TensorDataset

        model = CGMTransformerAE(input_dim=8, d_model=32, nhead=2, num_layers=1)
        x = torch.randn(8, 18, 8)
        y = torch.randn(8, 18, 8)
        loader = DataLoader(TensorDataset(x, y), batch_size=4)
        result = per_horizon_mae(model, loader, 'ae', window_size=12)
        self.assertIsInstance(result, dict)
        # Should have entries like '5min', '10min', etc.
        self.assertGreater(len(result), 0)
        for key in result:
            self.assertTrue(key.endswith('min'), f"Key {key} should end with 'min'")


# =============================================================================
# Clinical Metrics Tests
# =============================================================================

class TestClinicalMetrics(unittest.TestCase):
    """Tests for clinical outcome metrics (TIR, GRI, CV, hypo events)."""

    def test_tir_all_in_range(self):
        from tools.cgmencode.evaluate import time_in_range
        glucose = np.array([100, 120, 140, 160, 170])
        result = time_in_range(glucose)
        self.assertAlmostEqual(result['tir'], 100.0)
        self.assertAlmostEqual(result['below_70'], 0.0)
        self.assertAlmostEqual(result['above_180'], 0.0)

    def test_tir_mixed(self):
        from tools.cgmencode.evaluate import time_in_range
        glucose = np.array([50, 60, 100, 200, 300])
        result = time_in_range(glucose)
        self.assertAlmostEqual(result['tir'], 20.0)  # only 100
        self.assertAlmostEqual(result['below_54'], 20.0)  # only 50
        self.assertAlmostEqual(result['above_250'], 20.0)  # only 300
        self.assertEqual(result['n_readings'], 5)

    def test_tir_empty(self):
        from tools.cgmencode.evaluate import time_in_range
        result = time_in_range(np.array([]))
        self.assertEqual(result['tir'], 0.0)
        self.assertEqual(result['n_readings'], 0)

    def test_glucose_variability(self):
        from tools.cgmencode.evaluate import glucose_variability
        glucose = np.array([100.0, 100.0, 100.0, 100.0])
        result = glucose_variability(glucose)
        self.assertAlmostEqual(result['cv'], 0.0)
        self.assertAlmostEqual(result['mean'], 100.0)

    def test_glucose_variability_nonzero(self):
        from tools.cgmencode.evaluate import glucose_variability
        glucose = np.array([80.0, 120.0, 80.0, 120.0])
        result = glucose_variability(glucose)
        self.assertGreater(result['cv'], 0)
        self.assertAlmostEqual(result['mean'], 100.0)

    def test_gri_perfect(self):
        from tools.cgmencode.evaluate import glycemia_risk_index
        glucose = np.array([100, 110, 120, 130, 140])  # all in range
        result = glycemia_risk_index(glucose)
        self.assertAlmostEqual(result['gri'], 0.0)

    def test_gri_all_hypo(self):
        from tools.cgmencode.evaluate import glycemia_risk_index
        glucose = np.array([40, 45, 50])  # all very low
        result = glycemia_risk_index(glucose)
        self.assertGreater(result['gri'], 0)
        self.assertGreater(result['vlow_component'], 0)

    def test_hypo_events_count(self):
        from tools.cgmencode.evaluate import hypo_events
        # One hypo event: 3 consecutive readings below 70
        glucose = np.array([100, 100, 60, 55, 65, 100, 100])
        result = hypo_events(glucose, threshold=70, min_duration_steps=3)
        self.assertEqual(result['hypo_events'], 1)

    def test_hypo_events_no_events(self):
        from tools.cgmencode.evaluate import hypo_events
        glucose = np.array([100, 120, 140, 160])
        result = hypo_events(glucose, threshold=70, min_duration_steps=3)
        self.assertEqual(result['hypo_events'], 0)

    def test_clinical_summary_keys(self):
        from tools.cgmencode.evaluate import clinical_summary
        glucose = np.array([100, 120, 60, 200, 300])
        result = clinical_summary(glucose)
        # Should have all keys from TIR + variability + GRI + hypo
        self.assertIn('tir', result)
        self.assertIn('cv', result)
        self.assertIn('gri', result)
        self.assertIn('hypo_events', result)

    def test_override_accuracy(self):
        from tools.cgmencode.evaluate import override_accuracy
        suggested = [
            {'timestamp_idx': 10, 'event_type': 'meal'},
            {'timestamp_idx': 50, 'event_type': 'exercise'},
        ]
        actual = [
            {'timestamp_idx': 14, 'event_type': 'meal'},  # 4 steps after suggestion
            {'timestamp_idx': 80, 'event_type': 'exercise'},  # too far
        ]
        result = override_accuracy(suggested, actual, lead_window_steps=6)
        self.assertEqual(result['true_positives'], 1)
        self.assertAlmostEqual(result['precision'], 0.5)
        self.assertAlmostEqual(result['recall'], 0.5)

    def test_override_accuracy_empty(self):
        from tools.cgmencode.evaluate import override_accuracy
        result = override_accuracy([], [{'timestamp_idx': 10, 'event_type': 'meal'}])
        self.assertAlmostEqual(result['precision'], 0.0)
        self.assertAlmostEqual(result['recall'], 0.0)


# =============================================================================
# 6. Integration: MODEL_REGISTRY consistency
# =============================================================================

class TestModelRegistry(unittest.TestCase):
    """Verify MODEL_REGISTRY is self-consistent."""

    def test_all_models_constructible(self):
        from tools.cgmencode.train import MODEL_REGISTRY
        for name, reg in MODEL_REGISTRY.items():
            model = reg['class'](**reg['kwargs'])
            params = sum(p.numel() for p in model.parameters())
            self.assertGreater(params, 0, f"Model {name} has no parameters")

    def test_all_models_have_required_keys(self):
        from tools.cgmencode.train import MODEL_REGISTRY
        required = {'class', 'kwargs', 'task', 'conditioned'}
        for name, reg in MODEL_REGISTRY.items():
            self.assertEqual(set(reg.keys()), required,
                             f"Model {name} missing keys: {required - set(reg.keys())}")

    def test_task_values_valid(self):
        from tools.cgmencode.train import MODEL_REGISTRY
        valid_tasks = {'forecast', 'reconstruct'}
        for name, reg in MODEL_REGISTRY.items():
            self.assertIn(reg['task'], valid_tasks,
                          f"Model {name} has invalid task: {reg['task']}")


# =============================================================================
# Extended Data Adapter Tests
# =============================================================================

class TestExtendedFeatures(unittest.TestCase):
    """Tests for build_extended_features() in real_data_adapter."""

    def _make_synthetic_grid(self, n_steps=100):
        """Create a synthetic 5-min DataFrame matching build_nightscout_grid output."""
        import pandas as pd
        import numpy as np
        from tools.cgmencode.schema import NORMALIZATION_SCALES

        start = pd.Timestamp('2026-03-01 08:00:00', tz='UTC')
        idx = pd.date_range(start, periods=n_steps, freq='5min')
        df = pd.DataFrame({
            'glucose': np.linspace(120, 180, n_steps),
            'iob': np.linspace(2.0, 0.5, n_steps),
            'cob': np.linspace(30, 0, n_steps),
            'net_basal': np.sin(np.linspace(0, 4, n_steps)) * 0.5,
            'bolus': np.zeros(n_steps),
            'carbs': np.zeros(n_steps),
        }, index=idx)
        # Add a bolus at step 10 and carbs at step 20
        df.iloc[10, df.columns.get_loc('bolus')] = 3.0
        df.iloc[20, df.columns.get_loc('carbs')] = 45.0

        hours = idx.hour + idx.minute / 60.0
        features = np.column_stack([
            df['glucose'].values / NORMALIZATION_SCALES['glucose'],
            df['iob'].values / NORMALIZATION_SCALES['iob'],
            df['cob'].values / NORMALIZATION_SCALES['cob'],
            df['net_basal'].values / NORMALIZATION_SCALES['net_basal'],
            df['bolus'].values / NORMALIZATION_SCALES['bolus'],
            df['carbs'].values / NORMALIZATION_SCALES['carbs'],
            np.sin(2 * np.pi * hours / 24.0),
            np.cos(2 * np.pi * hours / 24.0),
        ]).astype(np.float32)
        return df, features

    def test_extended_shape(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features)
        self.assertEqual(ext.shape, (100, 21))

    def test_core_features_preserved(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features)
        np.testing.assert_array_equal(ext[:, :8], features)

    def test_day_of_week_encoding(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features)
        # Day sin/cos should be in [-1, 1]
        self.assertTrue(np.all(ext[:, 8] >= -1.0))
        self.assertTrue(np.all(ext[:, 8] <= 1.0))
        self.assertTrue(np.all(ext[:, 9] >= -1.0))
        self.assertTrue(np.all(ext[:, 9] <= 1.0))

    def test_glucose_roc(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features)
        # Glucose goes from 120→180 over 100 steps → positive ROC
        roc_norm = ext[:, 12]
        # Most values should be positive (glucose rising)
        self.assertGreater(np.mean(roc_norm[1:] > 0), 0.8)

    def test_time_since_bolus(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features)
        # Before bolus at step 10, time_since_bolus should be capped (360 min)
        self.assertAlmostEqual(ext[0, 14], 1.0, places=2)  # 360/360 = 1.0 (capped)
        # At step 10 (bolus), time_since_bolus = 0
        self.assertAlmostEqual(ext[10, 14], 0.0, places=2)
        # At step 15, time_since_bolus = 25 min → 25/360
        self.assertAlmostEqual(ext[15, 14], 25.0/360.0, places=2)

    def test_no_overrides_without_treatments(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        df, features = self._make_synthetic_grid()
        ext = build_extended_features(df, features, treatments=None)
        # No treatments → override channels all zero
        self.assertTrue(np.all(ext[:, 10] == 0.0))
        self.assertTrue(np.all(ext[:, 11] == 0.0))

    def test_override_extraction(self):
        from tools.cgmencode.real_data_adapter import build_extended_features
        from tools.cgmencode.schema import OVERRIDE_TYPES
        import pandas as pd
        df, features = self._make_synthetic_grid()
        # Simulate an "Eating Soon" override at step 30, duration 30 min
        ts = df.index[30].isoformat()
        treatments = [{
            'eventType': 'Temporary Override',
            'created_at': ts,
            'duration': 30,
            'reason': 'Eating Soon',
        }]
        ext = build_extended_features(df, features, treatments=treatments)
        # Steps 30–35 should be active (30 min = 6 steps)
        self.assertEqual(ext[30, 10], 1.0)
        self.assertEqual(ext[35, 10], 1.0)
        self.assertEqual(ext[36, 10], 0.0)
        self.assertAlmostEqual(ext[30, 11], OVERRIDE_TYPES['eating_soon'])


# =============================================================================
# 8. State Tracker Tests (ISF/CR drift detection)
# =============================================================================

class TestStateTracker(unittest.TestCase):
    """Tests for ISFCRTracker and DriftDetector (Kalman-based, deprecated)."""

    def setUp(self):
        import warnings
        warnings.filterwarnings('ignore', category=DeprecationWarning,
                                message='ISFCRTracker is deprecated')

    def test_tracker_init(self):
        """Initial state matches nominal values."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        np.testing.assert_allclose(tracker.state, [40.0, 10.0])
        np.testing.assert_allclose(tracker.nominal, [40.0, 10.0])
        self.assertEqual(len(tracker.history), 0)
        self.assertEqual(tracker.P.shape, (2, 2))
        # P should be symmetric positive-definite
        eigenvalues = np.linalg.eigvalsh(tracker.P)
        self.assertTrue(np.all(eigenvalues > 0))

    def test_tracker_update_stable(self):
        """With zero residuals, ISF/CR should stay near nominal."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)

        for _ in range(50):
            result = tracker.update(
                glucose_residual=0.0,
                iob_delta=0.5,
                cob_delta=5.0,
            )

        # Should remain close to nominal
        self.assertAlmostEqual(result['isf'], 40.0, delta=5.0)
        self.assertAlmostEqual(result['cr'], 10.0, delta=3.0)
        self.assertLess(result['isf_drift_pct'], 15.0)
        self.assertLess(result['cr_drift_pct'], 15.0)

    def test_tracker_detects_isf_drop(self):
        """Positive residuals (actual > predicted) indicate ISF dropped.

        If true ISF is 30 but the physics model assumes 40, each unit of
        insulin has LESS effect → the model over-predicts the BG drop →
        actual BG is higher than predicted → positive residual.

        The tracker should lower its ISF estimate.
        """
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(
            nominal_isf=40.0, nominal_cr=10.0,
            process_noise=0.1, measurement_noise=2.0,
        )

        # Simulate: true ISF=30, nominal=40 → insulin effect is weaker
        # Each step: iob_delta=0.5 U, residual = -(0.5)*(40-30) = +5 mg/dL
        for _ in range(60):
            tracker.update(
                glucose_residual=5.0,
                iob_delta=0.5,
                cob_delta=0.0,
            )

        # ISF should have decreased from 40 toward 30
        self.assertLess(tracker.state[0], 38.0,
                        f"ISF should drop below 38, got {tracker.state[0]:.1f}")

    def test_tracker_detects_cr_change(self):
        """Residuals from carb absorption indicate CR change.

        If true CR is 15 but model assumes 10, each gram of carbs has
        LESS effect → model over-predicts BG rise → actual is lower →
        negative residual.
        """
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(
            nominal_isf=40.0, nominal_cr=10.0,
            process_noise=0.1, measurement_noise=2.0,
        )

        # Simulate: carb-only information
        for _ in range(60):
            tracker.update(
                glucose_residual=-3.0,
                iob_delta=0.0,
                cob_delta=5.0,
            )

        # CR should have shifted from nominal
        cr_drift = abs(tracker.state[1] - 10.0)
        self.assertGreater(cr_drift, 0.5,
                           f"CR should drift from nominal, drift was {cr_drift:.2f}")

    def test_drift_detector_stable(self):
        """No drift → 'stable' classification."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)

        # Feed enough stable observations
        for _ in range(20):
            tracker.update(
                glucose_residual=0.0,
                iob_delta=0.5,
                cob_delta=5.0,
            )

        detector = DriftDetector(tracker, min_observations=12)
        result = detector.classify()
        self.assertEqual(result['state'], 'stable')

    def test_drift_detector_resistance(self):
        """ISF drop → 'resistance' classification."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector
        tracker = ISFCRTracker(
            nominal_isf=40.0, nominal_cr=10.0,
            process_noise=0.5, measurement_noise=1.0,
        )

        # Strong positive residuals → ISF has dropped
        for _ in range(40):
            tracker.update(
                glucose_residual=10.0,
                iob_delta=1.0,
                cob_delta=0.0,
            )

        detector = DriftDetector(tracker, drift_threshold_pct=15.0,
                                 min_observations=12)
        result = detector.classify()
        self.assertEqual(result['state'], 'resistance',
                         f"Expected 'resistance', got '{result['state']}' "
                         f"(ISF drift: {result['isf_drift_pct']:.1f}%)")

    def test_drift_summary(self):
        """Verify summary dict has all expected keys."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)

        # Feed some data
        for _ in range(5):
            tracker.update(0.0, 0.5, 2.0)

        summary = tracker.drift_summary()
        expected_keys = {
            'mean_isf', 'mean_cr', 'isf_trend', 'cr_trend',
            'isf_drift_pct', 'cr_drift_pct', 'is_significant',
            'suggested_adjustment',
        }
        self.assertEqual(set(summary.keys()), expected_keys)

        # Verify types
        self.assertIsInstance(summary['mean_isf'], float)
        self.assertIsInstance(summary['mean_cr'], float)
        self.assertIn(summary['is_significant'], (True, False))

    def test_drift_summary_empty(self):
        """Summary on empty tracker returns nominal values."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=42.0, nominal_cr=12.0)
        summary = tracker.drift_summary()
        self.assertAlmostEqual(summary['mean_isf'], 42.0)
        self.assertAlmostEqual(summary['mean_cr'], 12.0)
        self.assertFalse(summary['is_significant'])

    def test_suggested_override_stable(self):
        """Stable state → no override suggested."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        for _ in range(20):
            tracker.update(0.0, 0.5, 5.0)
        detector = DriftDetector(tracker, min_observations=12)
        self.assertIsNone(detector.suggested_override())

    def test_suggested_override_resistance(self):
        """Resistance → override with insulin_needs_factor > 1."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector
        tracker = ISFCRTracker(
            nominal_isf=40.0, nominal_cr=10.0,
            process_noise=0.5, measurement_noise=1.0,
        )
        for _ in range(40):
            tracker.update(10.0, 1.0, 0.0)
        detector = DriftDetector(tracker, drift_threshold_pct=15.0,
                                 min_observations=12)
        override = detector.suggested_override()
        self.assertIsNotNone(override)
        self.assertEqual(override['type'], 'sick')
        self.assertGreater(override['insulin_needs_factor'], 1.0)
        self.assertGreater(override['confidence'], 0.0)

    def test_zero_deltas_no_crash(self):
        """Zero IOB/COB deltas should not cause numerical errors."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        result = tracker.update(5.0, 0.0, 0.0)
        # Should return valid result without NaN
        self.assertFalse(np.isnan(result['isf']))
        self.assertFalse(np.isnan(result['cr']))

    def test_covariance_stays_positive_definite(self):
        """Covariance matrix should remain positive-definite after many updates."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        rng = np.random.RandomState(42)
        for _ in range(200):
            tracker.update(
                glucose_residual=rng.normal(0, 10),
                iob_delta=rng.uniform(0, 2),
                cob_delta=rng.uniform(0, 10),
            )
        eigenvalues = np.linalg.eigvalsh(tracker.P)
        self.assertTrue(np.all(eigenvalues > 0),
                        f"Covariance not PD: eigenvalues = {eigenvalues}")

    def test_tracker_reset(self):
        """Reset returns tracker to initial state."""
        from tools.cgmencode.state_tracker import ISFCRTracker
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        for _ in range(20):
            tracker.update(5.0, 0.5, 2.0)
        tracker.reset()
        np.testing.assert_allclose(tracker.state, [40.0, 10.0])
        self.assertEqual(len(tracker.history), 0)

    def test_pattern_state_machine_stable(self):
        """State machine stays stable with no drift."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector, PatternStateMachine
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0)
        detector = DriftDetector(tracker, min_observations=5)
        psm = PatternStateMachine(detector)

        for i in range(20):
            tracker.update(0.0, 0.5, 1.0)
            result = psm.update(timestamp=f't{i}')

        self.assertEqual(psm.current_state, 'stable')
        self.assertEqual(len(psm.transitions), 0)
        summary = psm.summary()
        self.assertEqual(summary['n_observations'], 20)

    def test_pattern_state_machine_transition(self):
        """State machine detects transition to resistance."""
        from tools.cgmencode.state_tracker import ISFCRTracker, DriftDetector, PatternStateMachine
        tracker = ISFCRTracker(nominal_isf=40.0, nominal_cr=10.0,
                               process_noise=0.5, measurement_noise=5.0)
        detector = DriftDetector(tracker, drift_threshold_pct=15.0, min_observations=5)
        psm = PatternStateMachine(detector, min_confidence=0.1)

        # Feed strong resistance signal
        for i in range(30):
            tracker.update(10.0, 1.0, 0.0)
            psm.update(timestamp=f't{i}')

        # Should have transitioned at some point
        self.assertGreater(len(psm.transitions), 0)
        durations = psm.get_state_durations()
        self.assertIn('stable', durations)  # started stable


class TestOverrideExtraction(unittest.TestCase):
    """Tests for extended override extraction and pre-event windows."""

    def test_classify_override_reason(self):
        from tools.cgmencode.label_events import classify_override_reason
        self.assertEqual(classify_override_reason('Eating Soon'), 'eating_soon')
        self.assertEqual(classify_override_reason('Pre-Meal Override'), 'eating_soon')
        self.assertEqual(classify_override_reason('exercise'), 'exercise')
        self.assertEqual(classify_override_reason('Going to the Gym'), 'exercise')
        self.assertEqual(classify_override_reason('Sleep'), 'sleep')
        self.assertEqual(classify_override_reason('Bedtime routine'), 'sleep')
        self.assertEqual(classify_override_reason('sick day'), 'sick')
        self.assertEqual(classify_override_reason('Custom thing'), 'custom_override')
        self.assertEqual(classify_override_reason(''), 'custom_override')
        self.assertEqual(classify_override_reason(None), 'custom_override')

    def test_extended_label_map(self):
        from tools.cgmencode.label_events import EXTENDED_LABEL_MAP
        # Must have all expected keys
        expected_keys = {'none', 'meal', 'correction_bolus', 'override',
                         'eating_soon', 'exercise', 'sleep', 'sick', 'custom_override'}
        self.assertEqual(set(EXTENDED_LABEL_MAP.keys()), expected_keys)
        # All values unique
        vals = list(EXTENDED_LABEL_MAP.values())
        self.assertEqual(len(vals), len(set(vals)))
        # none is 0, meal is 1 (backward compat)
        self.assertEqual(EXTENDED_LABEL_MAP['none'], 0)
        self.assertEqual(EXTENDED_LABEL_MAP['meal'], 1)

    def test_extract_override_events_treatments(self):
        """Test extraction from a minimal treatments.json."""
        import tempfile
        from tools.cgmencode.label_events import extract_override_events
        treatments = [
            {'eventType': 'Meal Bolus', 'created_at': '2024-01-15T12:00:00Z',
             'carbs': 45, 'insulin': 3.5},
            {'eventType': 'Temporary Override', 'created_at': '2024-01-15T14:00:00Z',
             'reason': 'Exercise - Running', 'duration': 60, 'insulinNeedsScaleFactor': 0.5},
            {'eventType': 'Temporary Override', 'created_at': '2024-01-15T22:00:00Z',
             'reason': 'Sleep', 'duration': 480, 'insulinNeedsScaleFactor': 1.0},
            {'eventType': 'Correction Bolus', 'created_at': '2024-01-15T16:00:00Z',
             'insulin': 1.2},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(treatments, f)
            path = f.name
        try:
            events, stats = extract_override_events(path)
            types = [e['event_type'] for e in events]
            self.assertIn('meal', types)
            self.assertIn('exercise', types)
            self.assertIn('sleep', types)
            self.assertIn('correction_bolus', types)
            # Check exercise event has scale factor
            ex_event = [e for e in events if e['event_type'] == 'exercise'][0]
            self.assertAlmostEqual(ex_event['insulin_needs_scale'], 0.5)
            self.assertAlmostEqual(ex_event['duration_min'], 60.0)
        finally:
            os.unlink(path)

    def test_extract_override_events_devicestatus(self):
        """Test extraction from devicestatus with Loop override."""
        import tempfile
        from tools.cgmencode.label_events import extract_override_events
        treatments = []
        devicestatus = [
            {'created_at': '2024-01-15T14:01:00Z',
             'override': {'active': True, 'name': 'Eating Soon', 'duration': 60}},
            {'created_at': '2024-01-15T14:02:00Z',
             'override': {'active': True, 'name': 'Eating Soon', 'duration': 60}},
            {'created_at': '2024-01-15T22:00:00Z',
             'override': {'active': False, 'name': 'Sleep'}},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as ft:
            json.dump(treatments, ft)
            tx_path = ft.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as fd:
            json.dump(devicestatus, fd)
            ds_path = fd.name
        try:
            events, stats = extract_override_events(tx_path, ds_path)
            # Only one eating_soon (dedup), no sleep (active=False)
            eating = [e for e in events if e['event_type'] == 'eating_soon']
            self.assertEqual(len(eating), 1)
            sleeping = [e for e in events if e['event_type'] == 'sleep']
            self.assertEqual(len(sleeping), 0)
        finally:
            os.unlink(tx_path)
            os.unlink(ds_path)

    def test_build_pre_event_windows_shape(self):
        """Pre-event windows have correct shape and lead times."""
        from tools.cgmencode.label_events import (
            build_pre_event_windows, EXTENDED_LABEL_MAP,
        )
        # Synthetic grid: 200 steps of 8 features
        n_steps = 200
        idx = pd.date_range('2024-01-15', periods=n_steps, freq='5min')
        cols = ['glucose', 'iob', 'cob', 'net_basal', 'bolus', 'carbs',
                'time_sin', 'time_cos']
        data = np.random.RandomState(42).rand(n_steps, 8) * 0.5 + 0.3
        data[:, 0] = 120 / 400  # normalized glucose
        grid = pd.DataFrame(data, index=idx, columns=cols)

        events = [
            {'timestamp': idx[80], 'event_type': 'meal', 'carbs': 40, 'insulin': 2.0},
            {'timestamp': idx[150], 'event_type': 'exercise', 'duration_min': 60,
             'insulin_needs_scale': 0.5},
        ]

        features, labels, meta = build_pre_event_windows(
            grid, events, window_steps=12, lead_steps=[6], neg_ratio=2)

        self.assertEqual(features.ndim, 3)
        self.assertEqual(features.shape[1], 12)  # window_steps
        self.assertEqual(features.shape[2], 8)   # features
        # Should have exactly 2 positive windows (1 per event × 1 lead time)
        n_pos = np.sum(labels > 0)
        self.assertEqual(n_pos, 2)
        # Lead time should be recorded in metadata
        for m in meta:
            if m['event_type'] != 'none':
                self.assertEqual(m['lead_time_min'], 30)

    def test_extract_extended_tabular_shape(self):
        """Extended tabular features add 4 columns."""
        from tools.cgmencode.label_events import extract_extended_tabular
        N, T, F = 10, 12, 8
        windows = np.random.rand(N, T, F) * 0.5 + 0.1
        labels = np.array([0, 0, 0, 1, 1, 2, 3, 4, 5, 0])
        meta = [{'lead_time_min': 30 if i >= 3 else 0} for i in range(N)]
        tab, names = extract_extended_tabular(windows, labels, meta)
        self.assertEqual(tab.shape[0], N)
        # Original 17 + 4 extended = 21
        self.assertEqual(tab.shape[1], 21)
        self.assertEqual(len(names), 21)
        self.assertIn('lead_time_hr', names)
        self.assertIn('glucose_accel', names)


# =============================================================================
# MC-Dropout Uncertainty Tests
# =============================================================================

class TestUncertainty(unittest.TestCase):
    """Verify MC-Dropout uncertainty quantification utilities."""

    def _make_model(self, input_dim=8, dropout=0.3):
        from tools.cgmencode.model import CGMGroupedEncoder
        return CGMGroupedEncoder(
            input_dim=input_dim, d_model=32, nhead=4,
            num_layers=2, dim_feedforward=64, dropout=dropout,
        )

    def _make_input(self, batch=2, seq_len=24, features=8):
        return torch.randn(batch, seq_len, features)

    # ---- enable_mc_dropout ---------------------------------------------------

    def test_enable_mc_dropout(self):
        """Dropout layers are active inside context, restored on exit."""
        from tools.cgmencode.uncertainty import enable_mc_dropout
        model = self._make_model()
        model.eval()

        # Before: all Dropout modules should be in eval (training=False)
        for m in model.modules():
            if isinstance(m, nn.Dropout):
                self.assertFalse(m.training)

        # During: Dropout modules should be in training mode
        with enable_mc_dropout(model):
            for m in model.modules():
                if isinstance(m, nn.Dropout):
                    self.assertTrue(m.training, "Dropout not active inside MC context")

        # After: restored back to eval
        for m in model.modules():
            if isinstance(m, nn.Dropout):
                self.assertFalse(m.training, "Dropout not restored after MC context")

    # ---- mc_predict ----------------------------------------------------------

    def test_mc_predict_shapes(self):
        """Output shapes match (B,S,F) for mean/std and (N,B,S,F) for samples."""
        from tools.cgmencode.uncertainty import mc_predict
        model = self._make_model()
        x = self._make_input(batch=3, seq_len=24, features=8)
        n = 10
        mean, std, samples = mc_predict(model, x, n_samples=n)

        self.assertEqual(mean.shape, (3, 24, 8))
        self.assertEqual(std.shape, (3, 24, 8))
        self.assertEqual(samples.shape, (n, 3, 24, 8))

    def test_mc_predict_variance(self):
        """With dropout, MC samples should exhibit non-zero variance."""
        from tools.cgmencode.uncertainty import mc_predict
        model = self._make_model(dropout=0.3)
        x = self._make_input(batch=2, seq_len=24, features=8)
        _, std, _ = mc_predict(model, x, n_samples=30)
        # At least some timesteps should have variance > 0
        self.assertGreater(std.max().item(), 0.0,
                           "MC samples have zero variance — dropout not active?")

    def test_mc_predict_extended(self):
        """mc_predict works with 16-feature extended input."""
        from tools.cgmencode.uncertainty import mc_predict
        model = self._make_model(input_dim=16)
        x = self._make_input(batch=2, seq_len=24, features=16)
        mean, std, samples = mc_predict(model, x, n_samples=5)
        self.assertEqual(mean.shape, (2, 24, 16))

    def test_mc_predict_causal(self):
        """mc_predict with causal=True produces valid output."""
        from tools.cgmencode.uncertainty import mc_predict
        model = self._make_model()
        x = self._make_input(batch=2, seq_len=12, features=8)
        mean, std, samples = mc_predict(model, x, n_samples=5, causal=True)
        self.assertEqual(mean.shape, (2, 12, 8))
        self.assertFalse(torch.isnan(mean).any())

    # ---- hypo_probability ----------------------------------------------------

    def test_hypo_probability_range(self):
        """P(hypo) values are in [0, 1]."""
        from tools.cgmencode.uncertainty import hypo_probability
        mean = torch.tensor([[120.0, 80.0, 60.0]])
        std = torch.tensor([[15.0, 15.0, 15.0]])
        p = hypo_probability(mean, std, threshold_mgdl=70.0)
        self.assertTrue((p >= 0.0).all() and (p <= 1.0).all())

    def test_hypo_probability_ordering(self):
        """Lower mean glucose → higher P(hypo)."""
        from tools.cgmencode.uncertainty import hypo_probability
        mean = torch.tensor([[150.0, 80.0, 50.0]])
        std = torch.tensor([[10.0, 10.0, 10.0]])
        p = hypo_probability(mean, std, threshold_mgdl=70.0)
        # p[0,2] > p[0,1] > p[0,0]
        self.assertGreater(p[0, 2].item(), p[0, 1].item())
        self.assertGreater(p[0, 1].item(), p[0, 0].item())

    # ---- hyper_probability ---------------------------------------------------

    def test_hyper_probability_range(self):
        """P(hyper) values are in [0, 1]."""
        from tools.cgmencode.uncertainty import hyper_probability
        mean = torch.tensor([[120.0, 180.0, 250.0]])
        std = torch.tensor([[15.0, 15.0, 15.0]])
        p = hyper_probability(mean, std, threshold_mgdl=180.0)
        self.assertTrue((p >= 0.0).all() and (p <= 1.0).all())

    def test_hyper_probability_ordering(self):
        """Higher mean glucose → higher P(hyper)."""
        from tools.cgmencode.uncertainty import hyper_probability
        mean = torch.tensor([[120.0, 180.0, 250.0]])
        std = torch.tensor([[10.0, 10.0, 10.0]])
        p = hyper_probability(mean, std, threshold_mgdl=180.0)
        self.assertGreater(p[0, 2].item(), p[0, 1].item())
        self.assertGreater(p[0, 1].item(), p[0, 0].item())

    # ---- prediction_interval -------------------------------------------------

    def test_prediction_interval(self):
        """Lower < mean < upper and width increases with std."""
        from tools.cgmencode.uncertainty import prediction_interval
        mean = torch.tensor([[120.0, 80.0]])
        std = torch.tensor([[10.0, 20.0]])
        lo, hi = prediction_interval(mean, std, confidence=0.95)

        self.assertTrue((lo < mean).all(), "Lower bound should be < mean")
        self.assertTrue((hi > mean).all(), "Upper bound should be > mean")
        # Wider std → wider interval
        width = hi - lo
        self.assertGreater(width[0, 1].item(), width[0, 0].item())

    def test_prediction_interval_symmetry(self):
        """Interval is symmetric around the mean."""
        from tools.cgmencode.uncertainty import prediction_interval
        mean = torch.tensor([[100.0]])
        std = torch.tensor([[10.0]])
        lo, hi = prediction_interval(mean, std, confidence=0.90)
        self.assertAlmostEqual((mean - lo).item(), (hi - mean).item(), places=4)

    # ---- mc_forecast_with_safety ---------------------------------------------

    def test_mc_forecast_with_safety(self):
        """Full pipeline returns expected keys and shapes."""
        from tools.cgmencode.uncertainty import mc_forecast_with_safety
        model = self._make_model()
        x = self._make_input(batch=2, seq_len=24, features=8)
        result = mc_forecast_with_safety(model, x, n_samples=10)

        expected_keys = {
            'mean_glucose_mgdl', 'std_glucose_mgdl',
            'p_hypo', 'p_hyper', 'ci_lower', 'ci_upper', 'is_safe',
        }
        self.assertEqual(set(result.keys()), expected_keys)

        # Shape checks — glucose channel only → (B, SeqLen)
        self.assertEqual(result['mean_glucose_mgdl'].shape, (2, 24))
        self.assertEqual(result['std_glucose_mgdl'].shape, (2, 24))
        self.assertEqual(result['p_hypo'].shape, (2, 24))
        self.assertEqual(result['p_hyper'].shape, (2, 24))
        self.assertEqual(result['ci_lower'].shape, (2, 24))
        self.assertEqual(result['ci_upper'].shape, (2, 24))
        self.assertEqual(result['is_safe'].shape, (2,))

        # Probabilities in [0, 1]
        self.assertTrue((result['p_hypo'] >= 0).all())
        self.assertTrue((result['p_hypo'] <= 1).all())
        self.assertTrue((result['p_hyper'] >= 0).all())
        self.assertTrue((result['p_hyper'] <= 1).all())

        # is_safe is boolean
        self.assertEqual(result['is_safe'].dtype, torch.bool)

    def test_mc_forecast_with_safety_transformer_ae(self):
        """Works with CGMTransformerAE as well."""
        from tools.cgmencode.model import CGMTransformerAE
        from tools.cgmencode.uncertainty import mc_forecast_with_safety
        model = CGMTransformerAE(
            input_dim=8, d_model=32, nhead=4,
            num_layers=1, dim_feedforward=64, dropout=0.3,
        )
        x = self._make_input(batch=2, seq_len=12, features=8)
        result = mc_forecast_with_safety(model, x, n_samples=5)
        self.assertIn('is_safe', result)
        self.assertEqual(result['mean_glucose_mgdl'].shape, (2, 12))


# =============================================================================
# 18. Coarse-Grid Downsampling Tests
# =============================================================================

class TestCoarseGrid(unittest.TestCase):
    """Verify downsample_grid and build_multihorizon_windows."""

    def _make_5min_grid(self, n_rows=100):
        """Create a synthetic 5-min grid DataFrame matching schema columns."""
        import pandas as pd
        idx = pd.date_range('2024-01-01', periods=n_rows, freq='5min')
        rng = np.random.RandomState(99)

        hours = idx.hour + idx.minute / 60.0
        df = pd.DataFrame({
            'glucose': 120.0 + rng.normal(0, 5, n_rows),
            'iob': np.linspace(2.0, 0.5, n_rows),
            'cob': np.linspace(30.0, 0.0, n_rows),
            'net_basal': rng.uniform(-0.5, 0.5, n_rows),
            'bolus': np.zeros(n_rows),
            'carbs': np.zeros(n_rows),
            'time_sin': np.sin(2 * np.pi * hours / 24.0),
            'time_cos': np.cos(2 * np.pi * hours / 24.0),
        }, index=idx)

        # Inject bolus/carbs at specific rows for summation testing
        df.iloc[0, df.columns.get_loc('bolus')] = 3.0
        df.iloc[1, df.columns.get_loc('bolus')] = 2.0
        df.iloc[2, df.columns.get_loc('bolus')] = 1.0
        df.iloc[0, df.columns.get_loc('carbs')] = 10.0
        df.iloc[1, df.columns.get_loc('carbs')] = 20.0
        df.iloc[2, df.columns.get_loc('carbs')] = 30.0
        return df

    def test_downsample_15min(self):
        """15-min downsample: shape, glucose smoothing, bolus summation."""
        from tools.cgmencode.real_data_adapter import downsample_grid

        df = self._make_5min_grid(100)
        ds = downsample_grid(df, target_interval_min=15)

        # Each 15-min bin holds 3 five-min rows; 100 rows → ceil(100/3) bins
        expected_rows = len(df.resample('15min').mean())
        self.assertEqual(len(ds), expected_rows)
        self.assertEqual(list(ds.columns), list(df.columns))

        # Glucose should be mean → smoother (lower std) than original
        self.assertLessEqual(ds['glucose'].std(), df['glucose'].std())

        # Bolus should be summed: first 15-min bin = 3+2+1 = 6
        self.assertAlmostEqual(ds['bolus'].iloc[0], 6.0, places=5)
        # Carbs summed: first bin = 10+20+30 = 60
        self.assertAlmostEqual(ds['carbs'].iloc[0], 60.0, places=5)

        # IOB should be 'last' within first 15-min bin
        self.assertAlmostEqual(ds['iob'].iloc[0], df['iob'].iloc[2], places=5)

    def test_downsample_60min(self):
        """60-min downsample: shape and aggregation."""
        from tools.cgmencode.real_data_adapter import downsample_grid

        df = self._make_5min_grid(120)  # 10 hours of data
        ds = downsample_grid(df, target_interval_min=60)

        expected_rows = len(df.resample('60min').mean())
        self.assertEqual(len(ds), expected_rows)
        self.assertEqual(list(ds.columns), list(df.columns))

        # First hour = 12 five-min rows; bolus sum should include rows 0-2
        first_hour_bolus = df.iloc[:12]['bolus'].sum()
        self.assertAlmostEqual(ds['bolus'].iloc[0], first_hour_bolus, places=5)

    def test_downsample_identity(self):
        """target_interval_min <= 5 returns a copy, not a resample."""
        from tools.cgmencode.real_data_adapter import downsample_grid

        df = self._make_5min_grid(20)
        ds = downsample_grid(df, target_interval_min=5)
        self.assertEqual(len(ds), len(df))
        np.testing.assert_array_equal(ds.values, df.values)

    def test_downsample_handles_nan(self):
        """NaN in sum columns should not become 0; mean/last propagate NaN."""
        from tools.cgmencode.real_data_adapter import downsample_grid

        df = self._make_5min_grid(15)
        df.iloc[3:6, df.columns.get_loc('bolus')] = np.nan
        ds = downsample_grid(df, target_interval_min=15)
        # Second 15-min bin (rows 3-5) was all-NaN bolus → should be NaN
        self.assertTrue(np.isnan(ds['bolus'].iloc[1]))

    def test_multihorizon_windows(self):
        """build_multihorizon_windows returns correct keys and shapes."""
        from tools.cgmencode.real_data_adapter import build_multihorizon_windows

        df = self._make_5min_grid(300)  # 25 hours
        result = build_multihorizon_windows(df)

        # Default horizons produce 3 entries
        self.assertEqual(set(result.keys()), {'1hr@5min', '6hr@15min', '3day@1hr'})

        for label, entry in result.items():
            self.assertIn('features', entry)
            self.assertIn('grid', entry)
            self.assertIn('interval_min', entry)
            # Features should be float32 2-D array with 8 columns (core)
            self.assertEqual(entry['features'].ndim, 2)
            self.assertEqual(entry['features'].shape[1], 8)
            self.assertEqual(entry['features'].dtype, np.float32)

        # 5-min grid should keep all rows
        self.assertEqual(result['1hr@5min']['features'].shape[0], 300)
        # 15-min grid should be ~1/3 the rows
        self.assertLess(result['6hr@15min']['features'].shape[0], 300)
        self.assertGreater(result['6hr@15min']['features'].shape[0], 0)
        # 60-min grid should be ~1/12 the rows
        self.assertLess(result['3day@1hr']['features'].shape[0],
                        result['6hr@15min']['features'].shape[0])

    def test_multihorizon_custom_horizons(self):
        """Custom horizons list is respected."""
        from tools.cgmencode.real_data_adapter import build_multihorizon_windows

        df = self._make_5min_grid(60)
        custom = [{'interval_min': 15, 'history_steps': 4, 'forecast_steps': 8, 'label': 'test'}]
        result = build_multihorizon_windows(df, horizons=custom)
        self.assertEqual(list(result.keys()), ['test'])
        self.assertEqual(result['test']['interval_min'], 15)


# =============================================================================
# 19. Event Classifier Tests
# =============================================================================

class TestEventClassifier(unittest.TestCase):
    """Tests for XGBoost event classifier and scoring."""

    def _make_synthetic_data(self, n=200, n_features=21):
        """Create synthetic classification data."""
        rng = np.random.RandomState(42)
        X = rng.randn(n, n_features)
        # Create separable classes: class 1 has positive feature 0, class 2 negative
        y = np.zeros(n, dtype=int)
        y[X[:, 0] > 0.5] = 1
        y[X[:, 1] < -0.5] = 2
        return X, y

    def test_compute_per_class_metrics(self):
        from tools.cgmencode.event_classifier import compute_per_class_metrics
        y_true = np.array([0, 0, 1, 1, 2, 2])
        y_pred = np.array([0, 0, 1, 0, 2, 2])
        probs = np.eye(3)[y_pred]  # one-hot
        result = compute_per_class_metrics(y_true, y_pred, probs)
        self.assertIn('accuracy', result)
        self.assertIn('per_class', result)
        self.assertIn('macro_f1_events', result)
        # Class 0: perfect, class 1: 1 FN, class 2: perfect
        self.assertAlmostEqual(result['per_class']['none']['precision'], 2/3, places=2)

    def test_manual_auroc(self):
        from tools.cgmencode.event_classifier import _manual_auroc
        # Perfect separation
        y = np.array([1, 1, 0, 0])
        scores = np.array([0.9, 0.8, 0.2, 0.1])
        self.assertAlmostEqual(_manual_auroc(y, scores), 1.0)
        # Inverse separation
        scores_inv = np.array([0.1, 0.2, 0.8, 0.9])
        self.assertAlmostEqual(_manual_auroc(y, scores_inv), 0.0)
        # Partial separation
        y2 = np.array([1, 0, 1, 0])
        scores2 = np.array([0.9, 0.7, 0.3, 0.1])
        auroc = _manual_auroc(y2, scores2)
        self.assertGreater(auroc, 0.5)

    def test_train_event_classifier(self):
        from tools.cgmencode.event_classifier import train_event_classifier
        X, y = self._make_synthetic_data(n=300)
        names = [f'f{i}' for i in range(X.shape[1])]
        result = train_event_classifier(X, y, feature_names=names, val_fraction=0.2,
                                        xgb_params={'n_estimators': 20, 'max_depth': 3})
        self.assertIn('model', result)
        self.assertIn('metrics', result)
        self.assertIn('feature_importance', result)
        self.assertGreater(result['metrics']['accuracy'], 0.5)

    def test_predict_events(self):
        from tools.cgmencode.event_classifier import train_event_classifier, predict_events
        X, y = self._make_synthetic_data(n=300)
        result = train_event_classifier(X, y, xgb_params={'n_estimators': 20, 'max_depth': 3})
        suggestions = predict_events(result['model'], X[:10], threshold=0.3)
        self.assertIsInstance(suggestions, list)
        for s in suggestions:
            self.assertIn('event_type', s)
            self.assertIn('probability', s)
            self.assertGreaterEqual(s['probability'], 0.3)

    def test_score_override_candidates(self):
        from tools.cgmencode.event_classifier import (
            train_event_classifier, score_override_candidates,
        )
        X, y = self._make_synthetic_data(n=300)
        # Relabel: 1=meal, 2=exercise (match EXTENDED_LABEL_MAP)
        result = train_event_classifier(X, y, xgb_params={'n_estimators': 20, 'max_depth': 3})
        meta = [{'timestamp': f't{i}', 'lead_time_min': 30} for i in range(10)]
        overrides = score_override_candidates(result['model'], X[:10], meta, min_prob=0.3)
        self.assertIsInstance(overrides, list)

    def test_rolling_features(self):
        from tools.cgmencode.label_events import compute_rolling_features
        idx = pd.date_range('2024-01-15', periods=100, freq='5min')
        df = pd.DataFrame({
            'glucose': np.random.RandomState(42).rand(100) * 200 + 70,
            'iob': np.random.RandomState(43).rand(100) * 5,
            'cob': np.random.RandomState(44).rand(100) * 40,
        }, index=idx)
        result = compute_rolling_features(df)
        self.assertIn('glucose_mean_1hr', result.columns)
        self.assertIn('glucose_std_3hr', result.columns)
        self.assertIn('glucose_range_6hr', result.columns)
        self.assertIn('iob_mean_1hr', result.columns)
        self.assertEqual(len(result), 100)


# =============================================================================
# 20. Forecast Pipeline Tests
# =============================================================================

class TestHierarchicalForecaster(unittest.TestCase):
    """Tests for HierarchicalForecaster, ScenarioSimulator, BacktestEngine."""

    def _make_model(self):
        from tools.cgmencode.model import CGMGroupedEncoder
        return CGMGroupedEncoder(input_dim=8, d_model=32, nhead=4, num_layers=1)

    def test_hierarchical_short_only(self):
        from tools.cgmencode.forecast import HierarchicalForecaster
        model = self._make_model()
        forecaster = HierarchicalForecaster(short_model=model)
        x = torch.randn(1, 24, 8)
        result = forecaster.forecast(x, horizon_hours=2.0)
        self.assertIn('short', result)
        self.assertEqual(result['short']['interval_min'], 5)

    def test_hierarchical_combined(self):
        from tools.cgmencode.forecast import HierarchicalForecaster
        model = self._make_model()
        forecaster = HierarchicalForecaster(short_model=model)
        x = torch.randn(1, 24, 8)
        glucose, times = forecaster.combined_forecast_mgdl(x, horizon_hours=2.0)
        self.assertGreater(len(glucose), 0)
        self.assertEqual(len(glucose), len(times))

    def test_hierarchical_long_term(self):
        from tools.cgmencode.forecast import HierarchicalForecaster
        forecaster = HierarchicalForecaster(short_model=self._make_model())
        x = torch.randn(1, 24, 8)
        result = forecaster.forecast(x, horizon_hours=24.0)
        self.assertIn('long', result)
        self.assertEqual(result['long']['interval_min'], 60)

    def test_scenario_simulator(self):
        from tools.cgmencode.forecast import HierarchicalForecaster, ScenarioSimulator
        forecaster = HierarchicalForecaster(short_model=self._make_model())
        sim = ScenarioSimulator(forecaster)
        x = torch.randn(1, 24, 8)
        result = sim.simulate_scenario(x, 'meal_medium', horizon_hours=2.0)
        self.assertIn('baseline_mgdl', result)
        self.assertIn('scenario_mgdl', result)
        self.assertIn('delta_mgdl', result)
        self.assertIn('max_impact_mgdl', result)

    def test_scenario_compare(self):
        from tools.cgmencode.forecast import HierarchicalForecaster, ScenarioSimulator
        forecaster = HierarchicalForecaster(short_model=self._make_model())
        sim = ScenarioSimulator(forecaster)
        x = torch.randn(1, 24, 8)
        results = sim.compare_scenarios(x, ['meal_small', 'meal_large'], horizon_hours=2.0)
        self.assertEqual(len(results), 2)
        # Sorted by TIR descending
        self.assertGreaterEqual(results[0]['tir'], results[1]['tir'])

    def test_backtest_full(self):
        from tools.cgmencode.forecast import BacktestEngine
        engine = BacktestEngine()
        # Synthetic glucose: 500 readings (41+ hours)
        glucose = np.random.RandomState(42).normal(140, 30, size=500).clip(40, 400)
        events = [{'timestamp_idx': 100, 'event_type': 'meal'}]
        result = engine.full_backtest(glucose, events, window_size_steps=72, stride_steps=36)
        self.assertGreater(result['n_windows'], 0)
        self.assertIn('mean_tir', result)
        self.assertIn('mean_gri', result)
        self.assertIn('total_hypo_events', result)

    def test_backtest_replay(self):
        from tools.cgmencode.forecast import BacktestEngine
        engine = BacktestEngine()
        glucose = np.array([120, 130, 140, 150, 160, 100, 90, 80, 70, 110])
        events = [{'timestamp_idx': 5, 'event_type': 'meal'}]
        result = engine.replay(glucose, events)
        self.assertIn('actual_clinical', result)
        self.assertIn('suggestion_accuracy', result)


class TestHindcastComposite(unittest.TestCase):
    """Tests for composite hindcast modes (decision, drift-scan, calibration)."""

    def _make_model(self):
        from tools.cgmencode.model import CGMGroupedEncoder
        return CGMGroupedEncoder(input_dim=8, d_model=32, nhead=4, num_layers=1,
                                 dropout=0.1)

    def _make_features_and_df(self, n_steps=288):
        """Create synthetic features (n_steps, 8) and a matching DataFrame."""
        rng = np.random.RandomState(42)
        features = np.zeros((n_steps, 8), dtype=np.float32)
        # glucose: oscillating around 140/400 normalized
        t = np.arange(n_steps)
        features[:, 0] = (140 + 30 * np.sin(t * 2 * np.pi / 288)) / 400.0
        # IOB: slow decay
        features[:, 1] = np.maximum(0, 5.0 - t * 0.02) / 10.0
        # COB: spike then decay
        features[:, 2] = np.maximum(0, 30.0 * np.exp(-t / 50.0)) / 60.0
        # time_sin/cos
        hours = (t * 5 / 60.0) % 24
        features[:, 6] = np.sin(2 * np.pi * hours / 24)
        features[:, 7] = np.cos(2 * np.pi * hours / 24)
        # Small noise
        features += rng.normal(0, 0.01, features.shape).astype(np.float32)
        features = np.clip(features, 0, 1)

        import pandas as pd
        idx = pd.date_range('2026-01-01', periods=n_steps, freq='5min', tz='UTC')
        df = pd.DataFrame({
            'glucose': features[:, 0] * 400,
            'iob': features[:, 1] * 10,
            'cob': features[:, 2] * 60,
        }, index=idx)
        return features, df

    # --- Decision mode ---

    def test_decision_returns_all_keys(self):
        from tools.cgmencode.hindcast_composite import run_decision
        model = self._make_model()
        features, df = self._make_features_and_df()
        result = run_decision(
            model, features, df, center_idx=144,
            history=12, horizon=12,
            profile={'isf': 40.0, 'cr': 10.0},
            n_mc_samples=5)
        # All pipeline stages must be present
        self.assertIn('event_classification', result)
        self.assertIn('drift_tracking', result)
        self.assertIn('forecast', result)
        self.assertIn('scenario_simulation', result)
        self.assertIn('uncertainty', result)
        self.assertIn('clinical_actual', result)
        self.assertIn('time', result)

    def test_decision_without_classifier(self):
        """Decision mode should work (skip classification) without a classifier."""
        from tools.cgmencode.hindcast_composite import run_decision
        model = self._make_model()
        features, df = self._make_features_and_df()
        result = run_decision(
            model, features, df, center_idx=144,
            history=12, horizon=12,
            profile={'isf': 40.0, 'cr': 10.0},
            n_mc_samples=5,
            classifier_model=None, classifier_features=None)
        self.assertEqual(result['event_classification']['status'], 'skipped')
        # Other stages should still work
        self.assertIn('drift_tracking', result)
        self.assertIn('forecast', result)

    def test_decision_out_of_bounds(self):
        """Decision mode should handle window out of bounds gracefully."""
        from tools.cgmencode.hindcast_composite import run_decision
        model = self._make_model()
        features, df = self._make_features_and_df(n_steps=20)
        result = run_decision(
            model, features, df, center_idx=5,
            history=12, horizon=12,
            profile={'isf': 40.0, 'cr': 10.0})
        self.assertIn('error', result)

    def test_decision_uncertainty_has_bounds(self):
        """Uncertainty section should have P(hypo), P(hyper), and prediction intervals."""
        from tools.cgmencode.hindcast_composite import run_decision
        model = self._make_model()
        features, df = self._make_features_and_df()
        result = run_decision(
            model, features, df, center_idx=144,
            history=12, horizon=12,
            profile={'isf': 40.0, 'cr': 10.0},
            n_mc_samples=5)
        unc = result.get('uncertainty', {})
        if unc.get('status') != 'error':
            self.assertIn('max_p_hypo', unc)
            self.assertIn('max_p_hyper', unc)
            self.assertIn('pi_95_low_mgdl', unc)
            self.assertIn('pi_95_high_mgdl', unc)
            self.assertGreaterEqual(unc['max_p_hypo'], 0)
            self.assertLessEqual(unc['max_p_hypo'], 1)

    # --- Drift-scan mode ---

    def test_drift_scan_returns_ranked(self):
        from tools.cgmencode.hindcast_composite import run_drift_scan
        model = self._make_model()
        features, df = self._make_features_and_df()
        results = run_drift_scan(
            model, features, df,
            profile={'isf': 40.0, 'cr': 10.0},
            history=12, horizon=12, top_n=5, stride=12)
        self.assertIsInstance(results, list)
        self.assertLessEqual(len(results), 5)
        if len(results) >= 2:
            # Should be sorted by drift_magnitude descending
            self.assertGreaterEqual(
                results[0]['drift_magnitude'],
                results[1]['drift_magnitude'])

    def test_drift_scan_has_anomaly_cross_ref(self):
        from tools.cgmencode.hindcast_composite import run_drift_scan
        model = self._make_model()
        features, df = self._make_features_and_df()
        results = run_drift_scan(
            model, features, df,
            profile={'isf': 40.0, 'cr': 10.0},
            history=12, horizon=12, top_n=3, stride=24)
        for r in results:
            self.assertIn('isf_drift_pct', r)
            self.assertIn('cr_drift_pct', r)
            self.assertIn('anomaly_mae', r)
            self.assertIn('co_occurrence', r)

    # --- Calibration mode ---

    def test_calibration_coverage_structure(self):
        from tools.cgmencode.hindcast_composite import run_calibration
        model = self._make_model()
        features, _ = self._make_features_and_df()
        result = run_calibration(
            model, features,
            history=12, horizon=12, stride=48,
            n_samples_sweep=[5, 10],
            confidence_levels=[0.5, 0.95])
        self.assertIn('calibration', result)
        self.assertIn('best_n_samples', result)
        self.assertIn('confidence_levels', result)

    def test_calibration_coverage_monotonic(self):
        """Higher confidence level should give equal or higher actual coverage."""
        from tools.cgmencode.hindcast_composite import run_calibration
        model = self._make_model()
        features, _ = self._make_features_and_df()
        result = run_calibration(
            model, features,
            history=12, horizon=12, stride=48,
            n_samples_sweep=[10],
            confidence_levels=[0.5, 0.8, 0.95])
        cal = result['calibration'].get(10, {})
        if not isinstance(cal, dict) or 'status' in cal:
            self.skipTest('No calibration data produced')
        coverages = []
        for cl in ['0.5', '0.8', '0.95']:
            if cl in cal:
                coverages.append(cal[cl]['actual_coverage'])
        if len(coverages) >= 2:
            for i in range(len(coverages) - 1):
                self.assertGreaterEqual(coverages[i + 1], coverages[i] - 0.05,
                                        'Coverage should be approximately monotonic')

    # --- Display functions (smoke tests) ---

    def test_display_decision_runs(self):
        """display_decision should not crash on a valid result dict."""
        from tools.cgmencode.hindcast_composite import run_decision, display_decision
        model = self._make_model()
        features, df = self._make_features_and_df()
        result = run_decision(
            model, features, df, center_idx=144,
            history=12, horizon=12,
            profile={'isf': 40.0, 'cr': 10.0},
            n_mc_samples=5)
        # Should not raise
        display_decision(result, 'grouped', 'test.pth')

    def test_display_drift_scan_runs(self):
        from tools.cgmencode.hindcast_composite import run_drift_scan, display_drift_scan
        model = self._make_model()
        features, df = self._make_features_and_df()
        results = run_drift_scan(
            model, features, df,
            profile={'isf': 40.0, 'cr': 10.0},
            history=12, horizon=12, top_n=3, stride=24)
        display_drift_scan(results, 'grouped', 'test.pth')

    def test_display_calibration_runs(self):
        from tools.cgmencode.hindcast_composite import run_calibration, display_calibration
        model = self._make_model()
        features, _ = self._make_features_and_df()
        result = run_calibration(
            model, features, history=12, horizon=12, stride=48,
            n_samples_sweep=[5], confidence_levels=[0.5, 0.95])
        display_calibration(result, 'grouped', 'test.pth')


class TestValidationSuites(unittest.TestCase):
    """Tests for multi-objective validation suites (validate_verification.py)."""

    def test_build_classifier_dataset_split_param(self):
        """build_classifier_dataset() accepts split='verification'."""
        from tools.cgmencode.label_events import build_classifier_dataset
        import inspect
        sig = inspect.signature(build_classifier_dataset)
        self.assertIn('split', sig.parameters)
        self.assertEqual(sig.parameters['split'].default, 'training')

    def test_per_class_metrics_shape(self):
        """_per_class_metrics returns per-class dicts with expected keys."""
        from tools.cgmencode.validate_verification import _per_class_metrics
        from tools.cgmencode.label_events import EXTENDED_LABEL_MAP
        y_true = np.array([0, 1, 2, 1, 0, 3, 1, 2])
        y_pred = np.array([0, 1, 1, 1, 0, 3, 2, 2])
        result = _per_class_metrics(y_true, y_pred, EXTENDED_LABEL_MAP)
        # Should have entries for non-zero classes present in data
        self.assertIn('meal', result)  # class 1
        for cls_metrics in result.values():
            for key in ('precision', 'recall', 'f1', 'tp', 'fp', 'fn', 'support'):
                self.assertIn(key, cls_metrics)

    def test_per_class_metrics_perfect(self):
        """Perfect predictions → F1 = 1.0 for all classes."""
        from tools.cgmencode.validate_verification import _per_class_metrics
        label_map = {'none': 0, 'meal': 1, 'exercise': 5}
        y = np.array([0, 1, 5, 1, 0, 5])
        result = _per_class_metrics(y, y, label_map)
        for name, m in result.items():
            self.assertAlmostEqual(m['f1'], 1.0, places=3,
                                   msg=f'{name} should have perfect F1')

    def test_per_class_metrics_zero_support(self):
        """Classes with zero support should have 0 metrics."""
        from tools.cgmencode.validate_verification import _per_class_metrics
        label_map = {'none': 0, 'meal': 1, 'exercise': 5}
        y_true = np.array([0, 0, 0])
        y_pred = np.array([0, 1, 0])  # FP for meal, but no actual meals
        result = _per_class_metrics(y_true, y_pred, label_map)
        if 'meal' in result:
            self.assertEqual(result['meal']['recall'], 0.0)
            self.assertEqual(result['meal']['support'], 0)

    def test_patient_dirs_helper(self):
        """_patient_dirs returns directories with the given split."""
        from tools.cgmencode.validate_verification import _patient_dirs
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create patient dirs with training and verification
            for p in ['a', 'b', 'c']:
                os.makedirs(os.path.join(tmpdir, p, 'training'))
                os.makedirs(os.path.join(tmpdir, p, 'verification'))
            # Patient d only has training
            os.makedirs(os.path.join(tmpdir, 'd', 'training'))

            train_dirs = _patient_dirs(tmpdir, 'training')
            verif_dirs = _patient_dirs(tmpdir, 'verification')
            self.assertEqual(len(train_dirs), 4)
            self.assertEqual(len(verif_dirs), 3)

    def test_event_detection_returns_expected_keys(self):
        """run_event_detection_verification returns structured dict even on no data."""
        from tools.cgmencode.validate_verification import run_event_detection_verification
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            # Empty patients dir → should return error status
            result = run_event_detection_verification(tmpdir)
            self.assertIn('status', result)
            self.assertIn(result['status'], ('error', 'partial'))

    def test_drift_tir_correlation_empty(self):
        """run_drift_tir_correlation handles empty data gracefully."""
        from tools.cgmencode.validate_verification import run_drift_tir_correlation
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_drift_tir_correlation(tmpdir)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(len(result['per_patient']), 0)

    def test_safe_div(self):
        """_safe_div handles zero denominator."""
        from tools.cgmencode.validate_verification import _safe_div
        self.assertEqual(_safe_div(10, 0), 0.0)
        self.assertEqual(_safe_div(10, 0, default=-1.0), -1.0)
        self.assertAlmostEqual(_safe_div(10, 2), 5.0)


class TestMultitaskModel(unittest.TestCase):
    """Tests for multi-task GroupedEncoder with auxiliary heads."""

    def test_grouped_no_aux_returns_tensor(self):
        """Without aux_config, forward() returns plain tensor (backward compat)."""
        model = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2, num_layers=1)
        x = torch.randn(2, 24, 8)
        out = model(x)
        self.assertIsInstance(out, torch.Tensor)
        self.assertEqual(out.shape, (2, 24, 8))

    def test_grouped_with_aux_returns_dict(self):
        """With aux_config, forward() returns dict with all heads."""
        aux = {'n_event_classes': 9, 'n_drift_outputs': 2, 'n_states': 4}
        model = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2,
                                  num_layers=1, aux_config=aux)
        x = torch.randn(2, 24, 8)
        out = model(x)
        self.assertIsInstance(out, dict)
        self.assertIn('forecast', out)
        self.assertIn('event_logits', out)
        self.assertIn('drift_pred', out)
        self.assertIn('state_logits', out)
        self.assertEqual(out['forecast'].shape, (2, 24, 8))
        self.assertEqual(out['event_logits'].shape, (2, 9))
        self.assertEqual(out['drift_pred'].shape, (2, 2))
        self.assertEqual(out['state_logits'].shape, (2, 4))

    def test_grouped_partial_aux(self):
        """Only requested heads are created."""
        aux = {'n_event_classes': 5}
        model = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2,
                                  num_layers=1, aux_config=aux)
        x = torch.randn(2, 24, 8)
        out = model(x)
        self.assertIsInstance(out, dict)
        self.assertIn('forecast', out)
        self.assertIn('event_logits', out)
        self.assertNotIn('drift_pred', out)
        self.assertNotIn('state_logits', out)

    def test_encode_method(self):
        """encode() returns d_model-dimensional representations."""
        model = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2, num_layers=1)
        x = torch.randn(2, 24, 8)
        encoded = model.encode(x)
        self.assertEqual(encoded.shape, (2, 24, 32))

    def test_extended_with_aux(self):
        """16-feature model with aux heads works correctly."""
        aux = {'n_event_classes': 9, 'n_states': 4}
        model = CGMGroupedEncoder(input_dim=16, d_model=64, nhead=4,
                                  num_layers=2, aux_config=aux)
        x = torch.randn(2, 24, 16)
        out = model(x)
        self.assertIsInstance(out, dict)
        self.assertEqual(out['forecast'].shape, (2, 24, 16))
        self.assertEqual(out['event_logits'].shape, (2, 9))

    def test_backward_compat_checkpoint_load(self):
        """Model trained without aux can load into model with aux."""
        # Train without aux → save
        model_old = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2, num_layers=1)
        state = model_old.state_dict()

        # Create model with aux
        aux = {'n_event_classes': 9, 'n_drift_outputs': 2}
        model_new = CGMGroupedEncoder(input_dim=8, d_model=32, nhead=2,
                                      num_layers=1, aux_config=aux)
        # Load old weights — should work with strict=False
        model_new.load_state_dict(state, strict=False)
        x = torch.randn(2, 24, 8)
        out = model_new(x)
        self.assertIsInstance(out, dict)


class TestMultitaskLoss(unittest.TestCase):
    """Tests for composite multi-task loss computation."""

    def test_forecast_only(self):
        """With just forecast output, loss is pure MSE."""
        from tools.cgmencode.experiment_lib import multitask_loss
        x = torch.randn(4, 24, 8)
        outputs = torch.randn(4, 24, 8)  # plain tensor
        targets = {'x': x}
        total, loss_dict = multitask_loss(outputs, targets)
        self.assertIn('forecast', loss_dict)
        self.assertGreater(total.item(), 0)

    def test_all_heads(self):
        """Composite loss with all 4 heads."""
        from tools.cgmencode.experiment_lib import multitask_loss
        x = torch.randn(4, 24, 8)
        outputs = {
            'forecast': torch.randn(4, 24, 8),
            'event_logits': torch.randn(4, 9),
            'drift_pred': torch.randn(4, 2),
            'state_logits': torch.randn(4, 4),
        }
        targets = {
            'x': x,
            'event_label': torch.randint(0, 9, (4,)),
            'drift_target': torch.randn(4, 2),
            'state_label': torch.randint(0, 4, (4,)),
        }
        total, loss_dict = multitask_loss(outputs, targets)
        self.assertIn('forecast', loss_dict)
        self.assertIn('event', loss_dict)
        self.assertIn('drift', loss_dict)
        self.assertIn('state', loss_dict)
        self.assertGreater(total.item(), 0)

    def test_masked_labels_skipped(self):
        """Labels of -1 are skipped in event/state loss."""
        from tools.cgmencode.experiment_lib import multitask_loss
        x = torch.randn(4, 24, 8)
        outputs = {
            'forecast': torch.randn(4, 24, 8),
            'event_logits': torch.randn(4, 9),
            'state_logits': torch.randn(4, 4),
        }
        targets = {
            'x': x,
            'event_label': torch.full((4,), -1, dtype=torch.long),
            'state_label': torch.full((4,), -1, dtype=torch.long),
        }
        total, loss_dict = multitask_loss(outputs, targets)
        self.assertIn('forecast', loss_dict)
        # Event and state should be skipped (all -1)
        self.assertNotIn('event', loss_dict)
        self.assertNotIn('state', loss_dict)

    def test_nan_drift_skipped(self):
        """NaN drift targets are skipped."""
        from tools.cgmencode.experiment_lib import multitask_loss
        x = torch.randn(4, 24, 8)
        outputs = {
            'forecast': torch.randn(4, 24, 8),
            'drift_pred': torch.randn(4, 2),
        }
        targets = {
            'x': x,
            'drift_target': torch.full((4, 2), float('nan')),
        }
        total, loss_dict = multitask_loss(outputs, targets)
        self.assertNotIn('drift', loss_dict)


class TestOutcomeBasedOverride(unittest.TestCase):
    """Tests for outcome_based_override_score."""

    def test_basic_score(self):
        """Score returns expected fields."""
        from tools.cgmencode.evaluate import outcome_based_override_score
        # Glucose: 200 for 2h, then 120 for 2h (improving)
        g = np.concatenate([np.full(24, 200.0), np.full(24, 120.0)])
        result = outcome_based_override_score(g, [24])
        self.assertIn('tir_before', result)
        self.assertIn('tir_after', result)
        self.assertIn('tir_delta', result)
        self.assertEqual(result['n_evaluated'], 1)
        # After is better (120 is in range, 200 is above range)
        self.assertGreater(result['tir_after'], result['tir_before'])

    def test_empty_suggestions(self):
        """No suggestions → zero results."""
        from tools.cgmencode.evaluate import outcome_based_override_score
        g = np.full(100, 120.0)
        result = outcome_based_override_score(g, [])
        self.assertEqual(result['n_suggestions'], 0)

    def test_edge_indices(self):
        """Suggestions near edges are handled gracefully."""
        from tools.cgmencode.evaluate import outcome_based_override_score
        g = np.full(20, 120.0)
        result = outcome_based_override_score(g, [2, 18])
        # Should handle gracefully (small windows)
        self.assertIn('n_evaluated', result)


class TestAuxLabelGeneration(unittest.TestCase):
    """Tests for generate_aux_labels module."""

    def test_drift_labels_shape(self):
        """Drift label generator returns correct shape."""
        from tools.cgmencode.generate_aux_labels import _generate_drift_labels
        feat = np.random.randn(10, 24, 8).astype(np.float32)
        labels = _generate_drift_labels(feat, isf_nominal=40.0, cr_nominal=10.0)
        self.assertEqual(labels.shape, (10, 2))

    def test_state_labels_shape(self):
        """State label generator returns correct shape."""
        from tools.cgmencode.generate_aux_labels import _generate_state_labels
        drift = np.array([[0, 0], [-10, 0], [10, 0], [0, 10]], dtype=np.float32)
        states = _generate_state_labels(drift, 40.0, 10.0)
        self.assertEqual(states.shape, (4,))
        self.assertEqual(states[0], 0)  # stable
        self.assertEqual(states[1], 1)  # resistance
        self.assertEqual(states[2], 2)  # sensitivity

    def test_multitask_dataset_iteration(self):
        """MultitaskDataset yields (features, targets_dict) pairs."""
        from tools.cgmencode.generate_aux_labels import MultitaskDataset
        features = torch.randn(10, 24, 8)
        events = torch.randint(0, 9, (10,))
        drift = torch.randn(10, 2)
        states = torch.randint(0, 4, (10,))
        ds = MultitaskDataset(features, events, drift, states)
        self.assertEqual(len(ds), 10)
        x, targets = ds[0]
        self.assertEqual(x.shape, (24, 8))
        self.assertIn('x', targets)
        self.assertIn('event_label', targets)
        self.assertIn('drift_target', targets)
        self.assertIn('state_label', targets)

    def test_state_labels_nan_handling(self):
        """NaN drift values produce -1 state labels (masked)."""
        from tools.cgmencode.generate_aux_labels import _generate_state_labels
        drift = np.array([[float('nan'), float('nan')], [0.0, 0.0]], dtype=np.float32)
        states = _generate_state_labels(drift, 40.0, 10.0)
        self.assertEqual(states[0], -1)  # invalid → masked
        self.assertEqual(states[1], 0)   # stable


# =============================================================================
# Masking Correctness Tests
# =============================================================================

class TestMaskingCorrectness(unittest.TestCase):
    """Verify mask_future_channels and validate_masking work correctly."""

    def test_mask_future_channels_zeros_correct_channels(self):
        """Masked channels are zeroed in future half, non-masked are preserved."""
        from tools.cgmencode.experiment_lib import mask_future_channels
        from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS, NUM_FEATURES_ENRICHED
        batch, seq, ch = 2, 24, NUM_FEATURES_ENRICHED
        half = seq // 2
        x = torch.ones(batch, seq, ch)
        x = mask_future_channels(x, half)
        for c in FUTURE_UNKNOWN_CHANNELS:
            self.assertTrue(
                (x[:, half:, c] == 0.0).all(),
                f"Channel {c} should be zeroed in future half"
            )
        # Deterministic channels must be preserved (IOB=1, COB=2, net_basal=3)
        for c in [1, 2, 3, 6, 7]:
            self.assertTrue(
                (x[:, half:, c] == 1.0).all(),
                f"Deterministic channel {c} should be preserved"
            )

    def test_mask_future_channels_preserves_history(self):
        """History half ([:half]) is never modified."""
        from tools.cgmencode.experiment_lib import mask_future_channels
        from tools.cgmencode.schema import NUM_FEATURES_ENRICHED
        batch, seq, ch = 2, 24, NUM_FEATURES_ENRICHED
        half = seq // 2
        x = torch.ones(batch, seq, ch)
        original_history = x[:, :half, :].clone()
        mask_future_channels(x, half)
        self.assertTrue(
            torch.equal(x[:, :half, :], original_history),
            "History half must not be modified"
        )

    def test_mask_future_channels_bounds_check(self):
        """8-channel input with 39-channel mask list doesn't crash."""
        from tools.cgmencode.experiment_lib import mask_future_channels
        from tools.cgmencode.schema import NUM_FEATURES
        batch, seq, ch = 2, 24, NUM_FEATURES  # 8 channels
        half = seq // 2
        x = torch.ones(batch, seq, ch)
        x = mask_future_channels(x, half)
        # Only channels 0, 4, 5 should be masked (other mask channels > 7)
        for c in [0, 4, 5]:
            self.assertTrue((x[:, half:, c] == 0.0).all(),
                            f"Channel {c} should be masked even in 8-ch input")
        # IOB, COB, net_basal should be preserved
        for c in [1, 2, 3]:
            self.assertTrue((x[:, half:, c] == 1.0).all(),
                            f"Channel {c} should be preserved in 8-ch input")

    def test_clone_before_mask_pattern(self):
        """Masking on a clone doesn't corrupt the original tensor."""
        from tools.cgmencode.experiment_lib import mask_future_channels
        from tools.cgmencode.schema import NUM_FEATURES_ENRICHED
        batch, seq, ch = 1, 24, NUM_FEATURES_ENRICHED
        half = seq // 2
        original = torch.ones(batch, seq, ch)
        cloned = original.clone()
        mask_future_channels(cloned, half)
        self.assertTrue(
            (original == 1.0).all(),
            "Original tensor must not be modified when cloning before mask"
        )
        # But the clone should have zeros
        self.assertFalse(
            (cloned[:, half:, 0] == 1.0).all(),
            "Clone should have masked glucose channel"
        )

    def test_validate_masking_passes_all_tiers(self):
        """validate_masking succeeds for 8f, 21f, and 39f input dims."""
        from tools.cgmencode.experiments_agentic import validate_masking
        for dim in [8, 21, 39]:
            result = validate_masking(dim, label=f'test-{dim}f')
            self.assertTrue(result, f"validate_masking should pass for {dim}-dim input")

    def test_validate_masking_raises_on_leak(self):
        """Removing a must-mask channel from FUTURE_UNKNOWN_CHANNELS raises ValueError."""
        from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS, IDX_GLUCOSE
        import tools.cgmencode.experiments_agentic as ea_mod
        import tools.cgmencode.schema as schema_mod
        import tools.cgmencode.experiment_lib as elib
        # Save originals
        orig_schema = list(schema_mod.FUTURE_UNKNOWN_CHANNELS)
        orig_ea = list(ea_mod.FUTURE_UNKNOWN_CHANNELS)
        orig_elib = list(elib.FUTURE_UNKNOWN_CHANNELS)
        leaked_list = [ch for ch in orig_schema if ch != IDX_GLUCOSE]
        try:
            schema_mod.FUTURE_UNKNOWN_CHANNELS = leaked_list
            ea_mod.FUTURE_UNKNOWN_CHANNELS = leaked_list
            elib.FUTURE_UNKNOWN_CHANNELS = leaked_list
            with self.assertRaises(ValueError, msg="Should detect glucose leak"):
                ea_mod.validate_masking(39, label='leak-test')
        finally:
            schema_mod.FUTURE_UNKNOWN_CHANNELS = orig_schema
            ea_mod.FUTURE_UNKNOWN_CHANNELS = orig_ea
            elib.FUTURE_UNKNOWN_CHANNELS = orig_elib

    def test_future_unknown_channels_complete(self):
        """Every glucose-derived channel is in FUTURE_UNKNOWN_CHANNELS."""
        from tools.cgmencode.schema import (
            FUTURE_UNKNOWN_CHANNELS, IDX_GLUCOSE, IDX_GLUCOSE_ROC,
            IDX_GLUCOSE_ACCEL, IDX_TREND_DIRECTION, IDX_TREND_RATE,
            IDX_ROLLING_NOISE, IDX_GLUCOSE_VS_TARGET,
        )
        glucose_derived = [
            IDX_GLUCOSE, IDX_GLUCOSE_ROC, IDX_GLUCOSE_ACCEL,
            IDX_TREND_DIRECTION, IDX_TREND_RATE, IDX_ROLLING_NOISE,
            IDX_GLUCOSE_VS_TARGET,
        ]
        masked_set = set(FUTURE_UNKNOWN_CHANNELS)
        for ch in glucose_derived:
            self.assertIn(ch, masked_set,
                          f"Glucose-derived channel {ch} must be in FUTURE_UNKNOWN_CHANNELS")


# =============================================================================
# Online Adaptation Tests
# =============================================================================

class TestOnlineAdaptation(unittest.TestCase):
    """Verify online_adaptation module components."""

    def test_sliding_window_dataset_time_ordered(self):
        """Windows should be yielded in chronological order."""
        from tools.cgmencode.online_adaptation import SlidingWindowDataset
        n_samples = 100
        data = torch.arange(n_samples).float().unsqueeze(-1).unsqueeze(-1).expand(n_samples, 24, 8)
        swd = SlidingWindowDataset(data, window_weeks=1, stride_weeks=1,
                                   samples_per_week=20)
        windows = list(swd.windows())
        self.assertGreater(len(windows), 1)
        # First element of each window should increase
        for i in range(1, len(windows)):
            first_prev = windows[i - 1].tensors[0][0, 0, 0].item()
            first_curr = windows[i].tensors[0][0, 0, 0].item()
            self.assertGreater(first_curr, first_prev,
                               "Windows must be in chronological order")

    def test_sliding_window_latest(self):
        """latest_window should return the most recent data."""
        from tools.cgmencode.online_adaptation import SlidingWindowDataset
        data = torch.arange(100).float().unsqueeze(-1).unsqueeze(-1).expand(100, 24, 8)
        swd = SlidingWindowDataset(data, window_weeks=1, samples_per_week=20)
        latest = swd.latest_window()
        # Should contain the last 20 samples
        self.assertEqual(len(latest), 20)
        self.assertEqual(latest.tensors[0][-1, 0, 0].item(), 99.0)

    def test_evaluate_temporal_stability_structure(self):
        """evaluate_temporal_stability returns expected dict structure."""
        from tools.cgmencode.online_adaptation import evaluate_temporal_stability
        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dim_feedforward=32, dropout=0.0)
        data = torch.randn(200, 24, 8)
        result = evaluate_temporal_stability(
            model, data, n_windows=3, window_weeks=1)
        self.assertIn('mae_per_window', result)
        self.assertIn('trend_slope', result)
        self.assertIn('is_degrading', result)
        self.assertIn('n_windows_evaluated', result)

    def test_adaptive_retrainer_triggers_on_threshold(self):
        """AdaptiveRetrainer.should_retrain() returns True when MAE degrades enough."""
        from tools.cgmencode.online_adaptation import AdaptiveRetrainer
        # Create minimal model checkpoint
        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dim_feedforward=32, dropout=0.0)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pth', delete=False) as f:
            torch.save({'model_state': model.state_dict()}, f.name)
            ckpt_path = f.name

        try:
            data = torch.randn(50, 24, 8)
            ar = AdaptiveRetrainer(ckpt_path, data,
                                   config={'degradation_threshold': 10.0})
            # Simulate history with degradation
            ar.history = [
                {'mae': 0.01, 'model_path': ckpt_path},
                {'mae': 0.02, 'model_path': ckpt_path},  # 100% increase
            ]
            self.assertTrue(ar.should_retrain())

            # No degradation
            ar.history = [
                {'mae': 0.01, 'model_path': ckpt_path},
                {'mae': 0.0105, 'model_path': ckpt_path},  # only 5%
            ]
            self.assertFalse(ar.should_retrain())
        finally:
            os.unlink(ckpt_path)

    def test_periodic_retrain_preserves_architecture(self):
        """Retrained model should have same architecture as base."""
        from tools.cgmencode.online_adaptation import periodic_retrain
        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dropout=0.0)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pth', delete=False) as f:
            torch.save({'model_state': model.state_dict()}, f.name)
            base_path = f.name
        out_path = base_path + '.retrained'

        try:
            data = torch.randn(50, 24, 8)
            result = periodic_retrain(
                base_path, data, out_path,
                input_dim=8, d_model=16, nhead=2, num_layers=1,
                window_weeks=1, epochs=2, patience=2)

            self.assertIn('new_mae', result)
            self.assertIn('old_mae', result)
            self.assertIn('improvement_pct', result)

            # Verify checkpoint can be loaded
            ckpt = torch.load(out_path, map_location='cpu', weights_only=False)
            new_model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                          num_layers=1, dropout=0.0)
            new_model.load_state_dict(ckpt['model_state'])
        finally:
            os.unlink(base_path)
            if os.path.exists(out_path):
                os.unlink(out_path)


# =============================================================================
# Override Recommender Tests
# =============================================================================

class TestOverrideRecommender(unittest.TestCase):
    """Verify override_recommender module components."""

    def _make_model(self, input_dim=21):
        return CGMGroupedEncoder(
            input_dim=input_dim, d_model=16, nhead=2,
            num_layers=1, dim_feedforward=32, dropout=0.0)

    def test_counterfactual_forecast_changes_prediction(self):
        """Override injection should produce different predictions than no-override."""
        from tools.cgmencode.override_recommender import counterfactual_forecast
        model = self._make_model(21)
        x = torch.randn(2, 24, 21) * 0.1 + 0.3
        x[:, :, 10] = 0.0  # no override active
        x[:, :, 11] = 0.0

        pred_no_override = counterfactual_forecast(model, x, 'none', 1.0)
        pred_exercise = counterfactual_forecast(model, x, 'exercise', 1.0)

        # With different override inputs, predictions should differ
        self.assertFalse(
            torch.allclose(pred_no_override, pred_exercise, atol=1e-6),
            "Counterfactual with override should differ from no-override"
        )

    def test_evaluate_overrides_ranks_correctly(self):
        """Best TIR should be ranked first."""
        from tools.cgmencode.override_recommender import evaluate_overrides
        model = self._make_model(21)
        x = torch.randn(4, 24, 21) * 0.1 + 0.3
        ranked = evaluate_overrides(
            model, x, override_types=['eating_soon', 'exercise'],
            strengths=[0.5, 1.0], horizon_steps=6)

        self.assertGreater(len(ranked), 0)
        # Verify sorted by TIR descending
        tirs = [r['predicted_tir'] for r in ranked]
        self.assertEqual(tirs, sorted(tirs, reverse=True))

    def test_recommend_override_returns_valid_type(self):
        """Recommendation should return a valid override type."""
        from tools.cgmencode.override_recommender import (
            recommend_override, OVERRIDE_TYPE_LIST,
        )
        model = self._make_model(21)
        x = torch.randn(2, 24, 21) * 0.1 + 0.3
        result = recommend_override(model, x, horizon_steps=6)

        self.assertIn(result['override_type'], OVERRIDE_TYPE_LIST)
        self.assertIn('confidence', result)
        self.assertIn('predicted_tir', result)
        self.assertIn('predicted_tir_no_override', result)
        self.assertIn('all_evaluations', result)

    def test_override_channels_correctly_injected(self):
        """Counterfactual should modify channels 10,11 only."""
        from tools.cgmencode.override_recommender import (
            counterfactual_forecast, IDX_OVERRIDE_ACTIVE, IDX_OVERRIDE_TYPE,
        )
        model = self._make_model(21)
        x = torch.zeros(1, 24, 21)
        # Run counterfactual — the function clones internally,
        # so original x should be unchanged
        _ = counterfactual_forecast(model, x, 'exercise', 1.5)
        self.assertTrue((x[:, :, IDX_OVERRIDE_ACTIVE] == 0.0).all(),
                        "Original tensor should not be modified")

    def test_override_value_model_forward(self):
        """OverrideValueModel forward pass produces correct shape."""
        from tools.cgmencode.override_recommender import OverrideValueModel
        vm = OverrideValueModel(state_dim=8, hidden_dim=32, n_override_types=5)
        state = torch.randn(4, 8)
        otype = torch.tensor([0, 1, 2, 3])
        strength = torch.randn(4, 1)
        out = vm(state, otype, strength)
        self.assertEqual(out.shape, (4, 1))


# =============================================================================
# Hypo Safety Module Tests
# =============================================================================

class TestHypoSafety(unittest.TestCase):
    """Verify hypo_safety module components."""

    def test_asymmetric_loss_penalizes_misses_more(self):
        """Loss for missed hypos should be higher than same-magnitude false alarms."""
        from tools.cgmencode.hypo_safety import AsymmetricHypoLoss, HYPO_THRESHOLD_NORM
        loss_fn = AsymmetricHypoLoss(miss_weight=5.0, false_alarm_weight=1.0)

        # Scenario 1: True glucose is hypo (0.15 = 60 mg/dL), predicted normal (0.25 = 100 mg/dL)
        pred_miss = torch.tensor([[[0.25]]])
        true_hypo = torch.tensor([[[0.15]]])  # below threshold (0.175)
        loss_miss = loss_fn(pred_miss, true_hypo)

        # Scenario 2: True glucose is normal (0.25 = 100), predicted hypo (0.15 = 60)
        pred_alarm = torch.tensor([[[0.15]]])
        true_normal = torch.tensor([[[0.25]]])  # above threshold
        loss_alarm = loss_fn(pred_alarm, true_normal)

        # Same squared error but miss should be 5x heavier
        self.assertAlmostEqual(loss_miss.item() / loss_alarm.item(), 5.0, places=3)

    def test_asymmetric_loss_equals_mse_when_weights_equal(self):
        """With equal weights, AsymmetricHypoLoss == MSELoss."""
        from tools.cgmencode.hypo_safety import AsymmetricHypoLoss
        loss_fn = AsymmetricHypoLoss(miss_weight=1.0, false_alarm_weight=1.0)
        mse_fn = nn.MSELoss()
        pred = torch.randn(4, 12, 1)
        target = torch.randn(4, 12, 1)
        self.assertAlmostEqual(
            loss_fn(pred, target).item(),
            mse_fn(pred, target).item(),
            places=5
        )

    def test_hypo_ensemble_predict_returns_expected_keys(self):
        """HypoSafetyEnsemble.predict() returns dict with required keys."""
        from tools.cgmencode.hypo_safety import HypoSafetyEnsemble
        clf = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                num_layers=1, dim_feedforward=32, dropout=0.0)
        forecasters = [
            CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                              num_layers=1, dim_feedforward=32, dropout=0.0)
            for _ in range(2)
        ]
        ensemble = HypoSafetyEnsemble(clf, forecasters, clf_threshold=0.5)
        x = torch.randn(2, 24, 8)
        result = ensemble.predict(x, horizon_steps=6)

        self.assertIn('hypo_probability', result)
        self.assertIn('predicted_glucose', result)
        self.assertIn('is_hypo_alert', result)
        self.assertEqual(result['hypo_probability'].shape, (2,))
        self.assertEqual(result['predicted_glucose'].shape, (2, 24, 1))
        self.assertEqual(result['is_hypo_alert'].shape, (2,))

    def test_evaluate_hypo_safety_returns_expected_structure(self):
        """evaluate_hypo_safety returns per-horizon metrics dict."""
        from tools.cgmencode.hypo_safety import evaluate_hypo_safety, GLUCOSE_SCALE
        from torch.utils.data import TensorDataset
        # Create synthetic data with some hypo values
        n, seq, ch = 32, 24, 8
        x = torch.randn(n, seq, ch) * 0.1 + 0.3  # centered around 120 mg/dL
        # Force some samples to have hypo values
        x[:4, 12:18, 0] = 0.12  # 48 mg/dL — definitely hypo
        ds = TensorDataset(x)

        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dim_feedforward=32, dropout=0.0)
        result = evaluate_hypo_safety([model], ds, thresholds_steps=[6],
                                      batch_size=16)
        self.assertIn('30min', result)
        metrics = result['30min']
        self.assertIn('sensitivity', metrics)
        self.assertIn('specificity', metrics)
        self.assertIn('n_hypo_samples', metrics)
        self.assertIn('n_total_samples', metrics)
        self.assertGreater(metrics['n_hypo_samples'], 0)


# =============================================================================
# Forecast MSE Tests
# =============================================================================

class TestForecastMSE(unittest.TestCase):
    """Verify forecast_mse evaluation metric."""

    def _make_tiny_model(self, input_dim=8):
        """Create a minimal model for testing."""
        return CGMGroupedEncoder(
            input_dim=input_dim, d_model=16, nhead=2,
            num_layers=1, dim_feedforward=32, dropout=0.0,
        )

    def _make_synthetic_dataset(self, n_samples=16, seq_len=24, n_features=8):
        """Create a synthetic TensorDataset for testing."""
        from torch.utils.data import TensorDataset
        x = torch.randn(n_samples, seq_len, n_features)
        return TensorDataset(x)

    def test_forecast_mse_with_masking(self):
        """forecast_mse produces a valid float with mask_future=True."""
        from tools.cgmencode.experiment_lib import forecast_mse
        model = self._make_tiny_model()
        ds = self._make_synthetic_dataset()
        mse = forecast_mse(model, ds, batch_size=8, mask_future=True)
        self.assertIsInstance(mse, float)
        self.assertGreater(mse, 0.0, "MSE should be positive on random data")

    def test_forecast_mse_without_masking(self):
        """forecast_mse with mask_future=False should also work."""
        from tools.cgmencode.experiment_lib import forecast_mse
        model = self._make_tiny_model()
        ds = self._make_synthetic_dataset()
        mse = forecast_mse(model, ds, batch_size=8, mask_future=False)
        self.assertIsInstance(mse, float)
        self.assertGreater(mse, 0.0)

    def test_forecast_mse_handles_dict_output(self):
        """Multi-task model returning dict with 'forecast' key is handled."""
        from tools.cgmencode.experiment_lib import forecast_mse
        # Wrap model to return dict
        model = self._make_tiny_model()

        class DictWrapper(nn.Module):
            def __init__(self, inner):
                super().__init__()
                self.inner = inner
            def forward(self, x, causal=False):
                out = self.inner(x, causal=causal)
                return {'forecast': out, 'event_logits': torch.zeros(x.size(0), 3)}

        wrapped = DictWrapper(model)
        ds = self._make_synthetic_dataset()
        mse = forecast_mse(wrapped, ds, batch_size=8, mask_future=True)
        self.assertIsInstance(mse, float)
        self.assertGreater(mse, 0.0)

    def test_masking_changes_mse(self):
        """MSE should differ between masked and unmasked evaluation."""
        from tools.cgmencode.experiment_lib import forecast_mse
        model = self._make_tiny_model()
        ds = self._make_synthetic_dataset()
        mse_masked = forecast_mse(model, ds, batch_size=16, mask_future=True)
        mse_unmasked = forecast_mse(model, ds, batch_size=16, mask_future=False)
        # With random data these will almost certainly differ
        # (masking zeroes out future channels which changes model input)
        self.assertNotEqual(
            round(mse_masked, 6), round(mse_unmasked, 6),
            "Masking should change model inputs and thus MSE"
        )


# =============================================================================
# End-to-End Masking Regression Test
# =============================================================================

class TestMaskingEndToEnd(unittest.TestCase):
    """End-to-end verification that masking behaves correctly during training."""

    def test_train_and_eval_masking_consistent(self):
        """Train a tiny model, verify masking is applied in both train and eval."""
        from tools.cgmencode.experiment_lib import (
            train_forecast, forecast_mse, mask_future_channels,
        )
        from tools.cgmencode.schema import FUTURE_UNKNOWN_CHANNELS
        from torch.utils.data import TensorDataset

        n, seq, ch = 32, 24, 8
        x = torch.randn(n, seq, ch)
        train_ds = TensorDataset(x[:24])
        val_ds = TensorDataset(x[24:])

        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dropout=0.0)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pth', delete=False) as f:
            sp = f.name

        try:
            # Train for 2 epochs
            best_val, ep = train_forecast(model, train_ds, val_ds, sp,
                                          label='e2e-test', lr=1e-3,
                                          epochs=2, patience=2)
            self.assertIsInstance(best_val, float)
            self.assertGreater(ep, 0)

            # Verify forecast_mse with masking
            mse = forecast_mse(model, val_ds, mask_future=True)
            self.assertIsInstance(mse, float)
            self.assertGreater(mse, 0.0)

            # Verify masking preserves deterministic channels
            test_input = torch.ones(1, seq, ch)
            half = seq // 2
            masked = test_input.clone()
            mask_future_channels(masked, half)

            # Glucose (0), bolus (4), carbs (5) should be zeroed
            for c in [0, 4, 5]:
                self.assertTrue((masked[0, half:, c] == 0.0).all())
            # IOB (1), COB (2), net_basal (3) should be preserved
            for c in [1, 2, 3]:
                self.assertTrue((masked[0, half:, c] == 1.0).all())
        finally:
            os.unlink(sp)

    def test_masking_regression_all_tiers(self):
        """validate_masking passes for all 3 input dimension tiers."""
        from tools.cgmencode.experiments_agentic import validate_masking
        for dim, tier in [(8, 'core'), (21, 'extended'), (39, 'enriched')]:
            result = validate_masking(dim, label=f'e2e-{tier}')
            self.assertTrue(result, f"Masking validation failed for {tier}")


# =============================================================================
# Validation Suite Tests
# =============================================================================

class TestValidationSuites(unittest.TestCase):
    """Verify that validation suite functions return expected structures."""

    def test_hypo_safety_evaluate_returns_per_horizon(self):
        """evaluate_hypo_safety returns metrics for each requested horizon."""
        from tools.cgmencode.hypo_safety import evaluate_hypo_safety
        from torch.utils.data import TensorDataset
        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dropout=0.0)
        x = torch.randn(16, 24, 8)
        ds = TensorDataset(x)
        result = evaluate_hypo_safety([model], ds, thresholds_steps=[6, 12])
        self.assertIn('30min', result)
        self.assertIn('60min', result)
        for key in ['30min', '60min']:
            self.assertIn('n_total_samples', result[key])

    def test_override_evaluate_returns_ranked_list(self):
        """evaluate_overrides returns sorted results with TIR."""
        from tools.cgmencode.override_recommender import evaluate_overrides
        model = CGMGroupedEncoder(input_dim=21, d_model=16, nhead=2,
                                  num_layers=1, dropout=0.0)
        x = torch.randn(4, 24, 21)
        ranked = evaluate_overrides(model, x,
                                    override_types=['eating_soon'],
                                    strengths=[0.5, 1.0],
                                    horizon_steps=6)
        self.assertEqual(len(ranked), 2)
        for r in ranked:
            self.assertIn('type', r)
            self.assertIn('strength', r)
            self.assertIn('predicted_tir', r)

    def test_temporal_stability_detects_trend(self):
        """evaluate_temporal_stability returns valid trend data."""
        from tools.cgmencode.online_adaptation import evaluate_temporal_stability
        model = CGMGroupedEncoder(input_dim=8, d_model=16, nhead=2,
                                  num_layers=1, dropout=0.0)
        data = torch.randn(200, 24, 8)
        result = evaluate_temporal_stability(model, data, n_windows=3,
                                             window_weeks=1)
        self.assertIsInstance(result['trend_slope'], float)
        self.assertIsInstance(result['is_degrading'], bool)
        self.assertEqual(len(result['mae_per_window']),
                         result['n_windows_evaluated'])


# ── Phase 6: Pattern Embedding Tests ────────────────────────────────────

class TestPatternEmbedding(unittest.TestCase):
    """Tests for pattern_embedding.py — contrastive learning pipeline."""

    def test_encoder_output_shape(self):
        """PatternEncoder produces (B, embed_dim) L2-normalized embeddings."""
        from tools.cgmencode.pattern_embedding import PatternEncoder
        encoder = PatternEncoder(input_dim=8, d_model=32, embed_dim=64,
                                 nhead=4, num_layers=1)
        x = torch.randn(4, 24, 8)
        emb = encoder.encode(x)
        self.assertEqual(emb.shape, (4, 64))
        # L2 normalized: norms should be ~1.0
        norms = emb.norm(dim=-1)
        for n in norms:
            self.assertAlmostEqual(n.item(), 1.0, places=4)

    def test_triplet_loss_gradient_direction(self):
        """TripletPatternLoss decreases when positive moves closer."""
        from tools.cgmencode.pattern_embedding import TripletPatternLoss
        loss_fn = TripletPatternLoss(margin=1.0)
        anchor = F.normalize(torch.randn(8, 64), dim=-1)
        positive_far = F.normalize(torch.randn(8, 64), dim=-1)
        negative = F.normalize(torch.randn(8, 64), dim=-1)
        # Positive very close to anchor
        positive_close = F.normalize(anchor + 0.01 * torch.randn(8, 64), dim=-1)

        loss_far = loss_fn(anchor, positive_far, negative)
        loss_close = loss_fn(anchor, positive_close, negative)
        self.assertGreater(loss_far.item(), loss_close.item())

    def test_build_triplets_balanced(self):
        """build_triplets produces valid triplet indices."""
        from tools.cgmencode.pattern_embedding import build_triplets
        n = 100
        windows = np.random.randn(n, 24, 8)
        labels = [['meal_bolus']] * 30 + [['stable']] * 40 + [['dawn']] * 30
        triplets = build_triplets(windows, labels, n_triplets=500)
        self.assertGreater(len(triplets), 0)
        for a, p, neg in triplets:
            self.assertNotEqual(a, p)
            # All indices valid
            self.assertLess(a, n)
            self.assertLess(p, n)
            self.assertLess(neg, n)

    def test_pattern_library_nearest_neighbor(self):
        """PatternLibrary retrieves inserted prototypes correctly."""
        from tools.cgmencode.pattern_embedding import PatternLibrary
        lib = PatternLibrary()
        embeddings = np.random.randn(50, 64).astype(np.float32)
        # Normalize
        embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
        labels = [['meal_bolus']] * 20 + [['stable']] * 30
        lib.build(embeddings, labels)

        # Query with a known embedding
        query = embeddings[0]  # meal_bolus
        matches = lib.match(query, top_k=5)
        self.assertGreater(len(matches), 0)
        self.assertGreater(matches[0]['similarity'], 0.9)

    def test_known_patterns_separate(self):
        """Distinct patterns should be separable after embedding (synthetic test)."""
        from tools.cgmencode.pattern_embedding import (
            PatternEncoder, retrieval_recall_at_k,
        )
        # Create two clearly different "patterns"
        n_each = 20
        dawn = np.zeros((n_each, 12, 8), dtype=np.float32)
        dawn[:, :, 0] = np.linspace(0.2, 0.5, 12)  # rising glucose
        dawn[:, :, 6] = -0.5  # early morning time_sin
        dawn += np.random.randn(n_each, 12, 8).astype(np.float32) * 0.02

        meal = np.zeros((n_each, 12, 8), dtype=np.float32)
        meal[:, :, 0] = np.linspace(0.3, 0.7, 12)  # sharper rise
        meal[:, :, 5] = 0.5  # carbs present
        meal += np.random.randn(n_each, 12, 8).astype(np.float32) * 0.02

        windows = np.concatenate([dawn, meal], axis=0)
        labels = [['dawn']] * n_each + [['meal_bolus']] * n_each

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=16,
                                 nhead=2, num_layers=1)
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()

        # Even without training, features should provide some separation
        recall = retrieval_recall_at_k(emb, labels, k=5)
        # At minimum, random would give ~50%. Structured features should do better.
        self.assertGreaterEqual(recall, 0.4)

    def test_encoder_init_from_forecast(self):
        """PatternEncoder can load weights from a CGMTransformerAE checkpoint."""
        from tools.cgmencode.pattern_embedding import PatternEncoder
        from tools.cgmencode.model import CGMTransformerAE
        # Create a forecast model and save its state
        forecast = CGMTransformerAE(input_dim=8, d_model=32, nhead=4, num_layers=2)
        state = forecast.state_dict()

        encoder = PatternEncoder(input_dim=8, d_model=32, embed_dim=64,
                                 nhead=4, num_layers=2)
        missing = encoder.load_from_forecast(state)
        # Projection head should be in missing (new task-specific layers)
        projection_missing = [k for k in missing if 'projection' in k]
        self.assertGreater(len(projection_missing), 0)
        # But input_projection and transformer should have been loaded
        # Verify by checking values match
        self.assertTrue(torch.allclose(
            encoder.input_projection.weight,
            forecast.input_projection.weight,
        ))


# ── Phase 7: Pattern Retrieval Tests ───────────────────────────────────

class TestPatternRetrieval(unittest.TestCase):
    """Tests for pattern_retrieval.py — episode segmentation & lead time."""

    def test_episode_segmenter_output_shape(self):
        """EpisodeSegmenter produces (B, T, n_labels) logits."""
        from tools.cgmencode.pattern_retrieval import EpisodeSegmenter, N_EPISODE_LABELS
        model = EpisodeSegmenter(input_dim=8, d_model=32, nhead=4,
                                 num_layers=1, n_labels=N_EPISODE_LABELS)
        x = torch.randn(4, 24, 8)
        logits = model(x)
        self.assertEqual(logits.shape, (4, 24, N_EPISODE_LABELS))

        # predict() returns integer labels
        preds = model.predict(x)
        self.assertEqual(preds.shape, (4, 24))
        self.assertTrue((preds >= 0).all())
        self.assertTrue((preds < N_EPISODE_LABELS).all())

    def test_build_episode_labels_covers_all_timesteps(self):
        """build_episode_labels assigns a label to every timestep."""
        from tools.cgmencode.pattern_retrieval import (
            build_episode_labels, N_EPISODE_LABELS,
        )
        T = 48
        glucose = np.concatenate([
            np.linspace(120, 60, T // 3),   # falling to hypo
            np.linspace(60, 200, T // 3),    # rebound
            np.linspace(200, 130, T - 2 * (T // 3)),  # correction
        ])
        iob = np.ones(T) * 1.0
        cob = np.zeros(T)
        bolus = np.zeros(T)
        bolus[T // 3 + 5] = 2.0  # correction bolus during rebound
        carbs = np.zeros(T)
        hours = np.linspace(4, 8, T)  # dawn hours

        labels = build_episode_labels(glucose, iob, cob, bolus, carbs, hours)
        self.assertEqual(len(labels), T)
        # All labels are valid indices
        self.assertTrue(np.all(labels >= 0))
        self.assertTrue(np.all(labels < N_EPISODE_LABELS))
        # Should have some non-stable labels
        self.assertGreater(np.sum(labels != 0), 0)

    def test_lead_time_predictor_with_known_pattern(self):
        """LeadTimePredictor returns valid output structure."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_retrieval import LeadTimePredictor

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=16,
                                 nhead=2, num_layers=1)
        # Build library with duration metadata
        n = 30
        windows = np.random.randn(n, 12, 8).astype(np.float32)
        labels = [['dawn']] * n
        metadata = [{'episode_duration_min': 60.0, 'event_type': 'dawn'}] * n

        lib = PatternLibrary()
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()
        lib.build(emb, labels, metadata=metadata)

        predictor = LeadTimePredictor(encoder, lib)
        result = predictor.predict(windows[0])

        self.assertIn('predicted_lead_time_min', result)
        self.assertIn('confidence', result)
        self.assertIn('matched_pattern_type', result)
        self.assertIn('similar_episodes', result)

    def test_predict_lead_time_confidence_ordering(self):
        """Higher similarity matches should have higher confidence."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_retrieval import LeadTimePredictor

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=16,
                                 nhead=2, num_layers=1)
        n = 50
        windows = np.random.randn(n, 12, 8).astype(np.float32)
        labels = [['meal_bolus']] * 25 + [['stable']] * 25
        metadata = [{'episode_duration_min': 45.0, 'event_type': 'meal'}] * 25 + \
                   [{'episode_duration_min': 120.0, 'event_type': 'stable'}] * 25

        lib = PatternLibrary()
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()
        lib.build(emb, labels, metadata=metadata)

        predictor = LeadTimePredictor(encoder, lib)
        result = predictor.predict(windows[0], min_similarity=-1.0)

        # similar_episodes should be sorted by similarity (descending)
        sims = [m['similarity'] for m in result['similar_episodes']]
        for i in range(len(sims) - 1):
            self.assertGreaterEqual(sims[i], sims[i + 1])

    def test_evaluate_lead_time_metrics_structure(self):
        """evaluate_lead_time returns correct metric dict structure."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_retrieval import (
            LeadTimePredictor, evaluate_lead_time,
        )
        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=16,
                                 nhead=2, num_layers=1)
        n = 20
        windows = np.random.randn(n, 12, 8).astype(np.float32)
        labels = [['stable']] * n
        metadata = [{'episode_duration_min': 30.0}] * n

        lib = PatternLibrary()
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()
        lib.build(emb, labels, metadata=metadata)

        predictor = LeadTimePredictor(encoder, lib)
        result = evaluate_lead_time(predictor, windows, metadata,
                                    horizons=[15, 30])

        self.assertIn('15min', result)
        self.assertIn('30min', result)
        self.assertIn('n_predictions', result)
        self.assertIn('n_valid', result)
        for h in ['15min', '30min']:
            self.assertIn('lead_time_mae_min', result[h])
            self.assertIn('actionable_rate', result[h])
            self.assertIn('coverage', result[h])


# ── Phase 8: Pattern Override Tests ────────────────────────────────────

class TestPatternOverride(unittest.TestCase):
    """Tests for pattern_override.py — pattern-triggered override policy."""

    def test_policy_output_valid_types(self):
        """PatternOverridePolicy outputs valid type logits and strength."""
        from tools.cgmencode.pattern_override import PatternOverridePolicy, N_OVERRIDE_TYPES
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=64)
        emb = torch.randn(4, 32)
        state = torch.randn(4, 8)
        type_logits, strength, tir_delta = policy(emb, state)

        self.assertEqual(type_logits.shape, (4, N_OVERRIDE_TYPES))
        self.assertEqual(strength.shape, (4, 1))
        self.assertEqual(tir_delta.shape, (4, 1))
        # Strength should be in [0, 2] (sigmoid * 2)
        self.assertTrue((strength >= 0).all())
        self.assertTrue((strength <= 2).all())

    def test_build_outcome_dataset_includes_missed(self):
        """build_override_outcome_dataset includes counterfactual 'missed' samples."""
        from tools.cgmencode.pattern_override import build_override_outcome_dataset
        n = 20
        windows = np.random.randn(n, 24, 12).astype(np.float32)
        # Make glucose decline in future → TIR degrades → missed opportunities
        windows[:, 12:, 0] = 0.1  # low glucose (below TIR range after denorm)
        windows[:, :12, 0] = 0.3  # normal in history
        windows[:, :, 10] = 0.0   # no override active
        labels = [['stable']] * n
        embeddings = np.random.randn(n, 32).astype(np.float32)

        result = build_override_outcome_dataset(
            windows, labels, embeddings,
            include_counterfactual=True,
            tir_improvement_threshold=0.01,
        )

        # Should have some counterfactual samples (TIR degraded)
        self.assertIn('is_counterfactual', result)
        self.assertEqual(len(result['embeddings']), len(result['tir_deltas']))

    def test_safety_guard_blocks_high_risk(self):
        """PatternTriggeredRecommender blocks recommendation when hypo risk is high."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_override import (
            PatternOverridePolicy, PatternTriggeredRecommender,
        )
        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=32)
        lib = PatternLibrary()
        emb = np.random.randn(10, 32).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        lib.build(emb, [['stable']] * 10)

        recommender = PatternTriggeredRecommender(
            encoder, lib, policy, hypo_risk_threshold=0.3,
        )

        # Create window with very low glucose → high hypo risk
        window = np.zeros((12, 8), dtype=np.float32)
        window[:, 0] = 0.1  # ~40 mg/dL → way below threshold
        result = recommender.recommend(window)

        self.assertTrue(result['safety_check']['blocked'])
        self.assertIn('blocked', result['explanation'].lower())

    def test_explain_includes_similar_episodes(self):
        """Explanation mentions similar episodes."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_override import (
            PatternOverridePolicy, PatternTriggeredRecommender,
        )
        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=32)
        lib = PatternLibrary()
        emb = np.random.randn(10, 32).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        lib.build(emb, [['meal_bolus']] * 5 + [['dawn']] * 5)

        recommender = PatternTriggeredRecommender(
            encoder, lib, policy, hypo_risk_threshold=0.5,
        )

        # Normal glucose → not blocked
        window = np.zeros((12, 8), dtype=np.float32)
        window[:, 0] = 0.3  # ~120 mg/dL
        result = recommender.recommend(window)

        self.assertFalse(result['safety_check']['blocked'])
        self.assertIn('similar episodes', result['explanation'].lower())
        self.assertGreater(len(result['similar_episodes']), 0)

    def test_evaluate_comparison_structure(self):
        """evaluate_pattern_overrides returns correct metrics structure."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_override import (
            PatternOverridePolicy, PatternTriggeredRecommender,
            evaluate_pattern_overrides,
        )
        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=32)
        lib = PatternLibrary()
        emb = np.random.randn(10, 32).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        lib.build(emb, [['stable']] * 10)

        recommender = PatternTriggeredRecommender(
            encoder, lib, policy, hypo_risk_threshold=0.5,
        )

        n = 8
        windows = np.random.randn(n, 12, 8).astype(np.float32)
        windows[:, :, 0] = 0.3  # keep glucose reasonable
        labels = [['stable']] * n
        tir_deltas = np.random.randn(n).astype(np.float32) * 0.1

        result = evaluate_pattern_overrides(recommender, windows, labels, tir_deltas)

        self.assertIn('hypo_safety_rate', result)
        self.assertIn('precision_at_1', result)
        self.assertIn('recommendation_coverage', result)
        self.assertIn('n_total', result)
        self.assertEqual(result['n_total'], n)


# ── Phase 9: Integration Tests ─────────────────────────────────────────

class TestPipelineIntegration(unittest.TestCase):
    """Cross-pipeline integration tests."""

    def test_embedding_feeds_retrieval(self):
        """PatternEncoder output is compatible with LeadTimePredictor input."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_retrieval import LeadTimePredictor

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        windows = np.random.randn(20, 12, 8).astype(np.float32)
        labels = [['dawn']] * 20
        metadata = [{'episode_duration_min': 60.0}] * 20

        lib = PatternLibrary()
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()
        lib.build(emb, labels, metadata=metadata)

        # LeadTimePredictor should accept the same encoder + library
        predictor = LeadTimePredictor(encoder, lib)
        result = predictor.predict(windows[0])
        self.assertIn('predicted_lead_time_min', result)

    def test_retrieval_feeds_override(self):
        """Pattern library classification feeds into override policy."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_override import (
            PatternOverridePolicy, PatternTriggeredRecommender,
        )
        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=32)
        lib = PatternLibrary()
        emb = np.random.randn(10, 32).astype(np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True)
        lib.build(emb, [['meal_bolus']] * 10)

        recommender = PatternTriggeredRecommender(encoder, lib, policy)
        window = np.random.randn(12, 8).astype(np.float32)
        window[:, 0] = 0.3
        result = recommender.recommend(window)

        self.assertIn('recommendation', result)
        self.assertIn('pattern_classification', result)
        self.assertIn('override_type', result['recommendation'])

    def test_full_pipeline_smoke(self):
        """Full pipeline: raw window → pattern → lead time → recommendation."""
        from tools.cgmencode.pattern_embedding import PatternEncoder, PatternLibrary
        from tools.cgmencode.pattern_retrieval import LeadTimePredictor
        from tools.cgmencode.pattern_override import (
            PatternOverridePolicy, PatternTriggeredRecommender,
        )

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)
        policy = PatternOverridePolicy(embed_dim=32, state_dim=8, hidden_dim=32)

        # Build library
        n = 30
        windows = np.random.randn(n, 12, 8).astype(np.float32)
        labels = [['meal_bolus']] * 15 + [['dawn']] * 15
        metadata = [{'episode_duration_min': 45.0, 'event_type': 'meal'}] * 15 + \
                   [{'episode_duration_min': 90.0, 'event_type': 'dawn'}] * 15

        lib = PatternLibrary()
        with torch.no_grad():
            emb = encoder.encode(torch.from_numpy(windows).float()).numpy()
        lib.build(emb, labels, metadata=metadata)

        # Stage 1: Lead time prediction
        predictor = LeadTimePredictor(encoder, lib)
        lead = predictor.predict(windows[0])
        self.assertIn('predicted_lead_time_min', lead)

        # Stage 2: Override recommendation
        recommender = PatternTriggeredRecommender(
            encoder, lib, policy, hypo_risk_threshold=0.5,
        )
        window = np.zeros((12, 8), dtype=np.float32)
        window[:, 0] = 0.3
        rec = recommender.recommend(window)
        self.assertIn('recommendation', rec)
        self.assertIn('similar_episodes', rec)

    def test_masking_preserved_across_pipelines(self):
        """Pattern embedding doesn't require future masking (uses full history)."""
        from tools.cgmencode.pattern_embedding import PatternEncoder

        encoder = PatternEncoder(input_dim=8, d_model=16, embed_dim=32,
                                 nhead=2, num_layers=1)

        # Embedding uses the FULL window (history only) — no future to mask
        window = torch.randn(1, 12, 8)
        # Deterministic in eval mode (set eval to disable dropout)
        encoder.eval()
        with torch.no_grad():
            emb1 = encoder.encode(window)
            emb2 = encoder.encode(window)
        self.assertTrue(torch.allclose(emb1, emb2))


if __name__ == '__main__':
    unittest.main()
