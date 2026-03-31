# CGMENCODE Schema

This document defines the schema for transforming T1Pal algorithm test fixtures into neural network training vectors.

## Feature Indices

The `encoder` produces a 3D NumPy array of shape `(Samples, TimeSteps, Features)`.

| Index | Feature | Type | Description |
|-------|---------|------|-------------|
| **0** | `glucose` | Input/State | Sensor Glucose Value (mg/dL). Primary target for forecasting. |
| **1** | `iob` | Input/State | Insulin on Board (Units). Represents active insulin in the body. |
| **2** | `cob` | Input/State | Carbs on Board (Grams). Represents unabsorbed carbohydrates. |
| **3** | `net_basal` | Action | Temp Basal Rate relative to scheduled basal (U/hr). |
| **4** | `bolus` | Action | Discrete insulin doses, including SMBs (Units). |
| **5** | `carbs` | Action | Discrete carbohydrate entries (Grams). |
| **6** | `time_sin` | Temporal | sin(2π · hour/24). Encodes circadian position on unit circle. |
| **7** | `time_cos` | Temporal | cos(2π · hour/24). Paired with `time_sin` so 23:55 ≈ 00:05. |

## Normalization Scales

| Feature | Raw Range | Normalized Range | Scale Factor |
|---------|-----------|-----------------|--------------|
| glucose | 40–400 mg/dL | [0, 1] | ÷ 400 |
| iob | 0–20 U | [0, 1] | ÷ 20 |
| cob | 0–100 g | [0, 1] | ÷ 100 |
| net_basal | −5 to +5 U/hr | [−1, 1] | ÷ 5 |
| bolus | 0–10 U | [0, 1] | ÷ 10 |
| carbs | 0–100 g | [0, 1] | ÷ 100 |
| time_sin | −1 to +1 | [−1, 1] | native |
| time_cos | −1 to +1 | [−1, 1] | native |

## Advanced Training Tasks

To build a robust encoder/decoder, we implement several "Self-Supervised" tasks:

1.  **`fill_actions`**: Mask indices `[3, 4, 5]` in the history.
    *   *Goal*: Learn the "policy" or "intent" of the controller given the physiological state.
2.  **`fill_readings`**: Mask indices `[0, 1, 2]` in the history.
    *   *Goal*: Infer state from actions and outcomes (system identification).
3.  **`forecast`**: Mask all features in the `result_window` (future).
    *   *Goal*: Predict physiological response to the current state and actions.
4.  **`denoise`**: Add Gaussian noise to all indices `[0-5]`.
    *   *Goal*: Learn to extract clean signals from noisy sensor data and jittery basal enactments.
5.  **`random_patch`**: Mask a random contiguous time-slice (e.g., 30-60 mins) across all features.
    *   *Goal*: Robustness to sensor dropouts or communication gaps (common in BLE insulin pumps).
6.  **`shuffled_mask`**: Mask random individual features at random timestamps.
    *   *Goal*: Learn local correlations between features (e.g., how a bolus at `t=0` affects `iob` at `t=1`).

## Alternative Architectures (Roadmap)

### 1. Variational Autoencoder (VAE) - Generative Mode
*   **Goal**: Sampling the latent space to generate synthetic training data.
*   **Structure**: `z ~ N(0, 1) -> Decoder -> [Synthetic Scenario]`.
*   **Usage**: Creating massive datasets for training lightweight "edge" NNs.

### 2. Action-Conditioned Predictor (Dosing Counselor)
*   **Goal**: Evaluating the impact of a potential action before it is taken.
*   **Structure**: `Encoder(History) + Proposed_Action -> Future_Glucose`.
*   **Usage**: Providing "What-if" simulations for dosing guidance.

### 3. Contrastive Learning
*   **Goal**: Learning robust, noise-invariant representations of patient physiology.
*   **Structure**: `Latent(Augmented_A) == Latent(Augmented_B)`.
*   **Usage**: Handling low-quality sensor data and signal dropouts.
