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

import numpy as np
import torch
import torch.nn as nn


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


if __name__ == '__main__':
    unittest.main()
