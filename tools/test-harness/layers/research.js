'use strict';

/**
 * Layer 3: R&D / Research Harness
 *
 * Supports:
 * - Agent effect injection (simulate EffectModifiers before algorithm runs)
 * - Algorithm mutation proposals (test parameter changes)
 * - Sandbox mode for experimenting with new algorithms
 *
 * This layer builds on Layer 2 (benchmarking) but adds the ability to
 * modify inputs before they reach adapters, simulating agents and overrides.
 */

const { loadVectors, extractExpected } = require('../lib/vector-loader');
const { loadAdapter, runVector, vectorToAdapterInput } = require('../lib/adapter-protocol');
const { compareToExpected } = require('../lib/output-comparator');

/**
 * Apply effect modifiers to an adapter input, simulating agent effects.
 *
 * Effect modifiers adjust profile parameters:
 * - isfMultiplier: scales sensitivity (ISF) — <1 = more sensitive
 * - crMultiplier: scales carb ratio — <1 = more responsive to carbs
 * - basalMultiplier: scales basal rate — <1 = less basal
 *
 * Safety bounds are enforced per EffectModifier spec.
 */
function applyEffectModifiers(adapterInput, modifiers) {
  if (!modifiers || modifiers.length === 0) return adapterInput;

  const modified = JSON.parse(JSON.stringify(adapterInput));
  const profile = modified.profile || {};

  for (const mod of modifiers) {
    if (mod.isfMultiplier != null) {
      const factor = clamp(mod.isfMultiplier, 0.5, 2.0);
      profile.sensitivity = (profile.sensitivity || 50) * factor;
    }
    if (mod.crMultiplier != null) {
      const factor = clamp(mod.crMultiplier, 0.7, 1.5);
      profile.carbRatio = (profile.carbRatio || 10) * factor;
    }
    if (mod.basalMultiplier != null) {
      const factor = clamp(mod.basalMultiplier, 0.5, 2.0);
      profile.basalRate = (profile.basalRate || 1.0) * factor;
    }
  }

  modified.profile = profile;
  modified.effectModifiers = modifiers;
  return modified;
}

/**
 * Simulate an agent effect by generating a modifier from a scenario description.
 */
const AGENT_PRESETS = {
  exercise: {
    source: 'ActivityModeAgent',
    isfMultiplier: 1.2,   // less sensitive during exercise
    crMultiplier: 1.0,
    basalMultiplier: 0.5, // reduce basal during exercise
    confidence: 0.8,
    reason: 'Exercise detected: HR > 120 bpm, reducing basal',
  },
  'post-exercise': {
    source: 'ActivityModeAgent',
    isfMultiplier: 0.7,   // more sensitive post-exercise
    crMultiplier: 1.0,
    basalMultiplier: 0.8,
    confidence: 0.7,
    reason: 'Post-exercise sensitivity increase',
  },
  'breakfast-boost': {
    source: 'BreakfastBoostAgent',
    isfMultiplier: 1.3,   // less sensitive at breakfast (dawn phenomenon)
    crMultiplier: 0.85,   // more aggressive carb coverage
    basalMultiplier: 1.2,
    confidence: 0.6,
    reason: 'Morning meal pattern detected',
  },
  illness: {
    source: 'IllnessAgent',
    isfMultiplier: 1.5,   // significantly less sensitive when ill
    crMultiplier: 1.0,
    basalMultiplier: 1.3,
    confidence: 0.5,
    reason: 'Illness pattern detected: elevated basal glucose',
  },
};

/**
 * Run R&D experiment: test algorithm behavior with agent effects.
 *
 * @param {object} opts
 *   - vectorDir: path to vectors
 *   - adapterDirs: adapter paths
 *   - agents: array of agent preset names or custom modifiers
 *   - limit, ids: vector selection
 * @returns {object} Research results with baseline vs modified comparison
 */
async function runResearch(opts) {
  const vectors = loadVectors(opts.vectorDir, {
    limit: opts.limit,
    ids: opts.ids,
  });

  const adapters = (opts.adapterDirs || []).map(dir => loadAdapter(dir));

  // Resolve agent presets
  const modifiers = (opts.agents || []).map(agent => {
    if (typeof agent === 'string') {
      const preset = AGENT_PRESETS[agent];
      if (!preset) throw new Error(`Unknown agent preset: ${agent}. Available: ${Object.keys(AGENT_PRESETS).join(', ')}`);
      return preset;
    }
    return agent;
  });

  const results = {
    experiment: {
      agents: modifiers.map(m => ({ source: m.source, reason: m.reason })),
      adapterCount: adapters.length,
      vectorCount: vectors.length,
    },
    vectorResults: [],
  };

  for (const vector of vectors) {
    const vectorResult = {
      vectorId: vector.metadata?.id,
      baseline: {},
      modified: {},
      deltas: {},
    };

    for (const adapter of adapters) {
      const name = adapter.manifest.name;

      // Baseline: run without modifiers
      const baselineResult = await runVector(adapter, vector);
      vectorResult.baseline[name] = {
        decision: baselineResult.output?.decision || null,
        predictions: baselineResult.output?.predictions || null,
        error: baselineResult.error,
      };

      // Modified: apply agent effects and re-run
      const baseInput = vectorToAdapterInput(vector);
      const modifiedInput = applyEffectModifiers(baseInput, modifiers);
      const modifiedResult = await adapter.invoke(modifiedInput);

      vectorResult.modified[name] = {
        decision: modifiedResult?.decision || null,
        predictions: modifiedResult?.predictions || null,
        error: modifiedResult?.error,
      };

      // Compute deltas
      const baseRate = baselineResult.output?.decision?.rate;
      const modRate = modifiedResult?.decision?.rate;
      const baseEB = baselineResult.output?.predictions?.eventualBG;
      const modEB = modifiedResult?.predictions?.eventualBG;

      vectorResult.deltas[name] = {
        rateChange: (baseRate != null && modRate != null) ? round(modRate - baseRate, 3) : null,
        eventualBGChange: (baseEB != null && modEB != null) ? round(modEB - baseEB, 1) : null,
      };
    }

    results.vectorResults.push(vectorResult);
  }

  // Aggregate impact statistics
  for (const adapter of adapters) {
    const name = adapter.manifest.name;
    const rateChanges = results.vectorResults
      .map(vr => vr.deltas[name]?.rateChange)
      .filter(d => d != null);
    const bgChanges = results.vectorResults
      .map(vr => vr.deltas[name]?.eventualBGChange)
      .filter(d => d != null);

    results[`impact_${name}`] = {
      avgRateChange: rateChanges.length > 0
        ? round(rateChanges.reduce((a, b) => a + b, 0) / rateChanges.length, 3)
        : null,
      avgBGChange: bgChanges.length > 0
        ? round(bgChanges.reduce((a, b) => a + b, 0) / bgChanges.length, 1)
        : null,
      vectorsAffected: rateChanges.filter(d => Math.abs(d) > 0.01).length,
      totalVectors: rateChanges.length,
    };
  }

  return results;
}

function clamp(val, min, max) {
  return Math.min(max, Math.max(min, val));
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

module.exports = {
  runResearch,
  applyEffectModifiers,
  AGENT_PRESETS,
};
