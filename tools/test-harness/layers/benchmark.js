'use strict';

/**
 * Layer 2: Algorithm Benchmarking
 *
 * Compares DIFFERENT algorithms given the same inputs.
 * Unlike equivalence testing (same algorithm, different implementations),
 * benchmarking expects different outputs and measures divergence patterns.
 */

const { loadVectors, extractExpected } = require('../lib/vector-loader');
const { loadAdapter, runVector } = require('../lib/adapter-protocol');
const { compareOutputs, DIVERGENCE_LEVELS } = require('../lib/output-comparator');

/**
 * Run benchmark: same vectors through different algorithm adapters.
 *
 * @param {object} opts
 *   - vectorDir: path to vectors
 *   - adapterDirs: array of adapter directory paths (different algorithms)
 *   - limit: max vectors
 *   - ids: specific vector IDs
 * @returns {object} Benchmark results with divergence analysis
 */
async function runBenchmark(opts) {
  const vectors = loadVectors(opts.vectorDir, {
    limit: opts.limit,
    ids: opts.ids,
  });

  const adapters = (opts.adapterDirs || []).map(dir => loadAdapter(dir));

  if (adapters.length < 2) {
    return { error: 'Benchmarking requires at least 2 adapters', pass: false };
  }

  const results = {
    adapters: adapters.map(a => ({
      name: a.manifest.name,
      algorithm: a.manifest.algorithm,
    })),
    vectorCount: vectors.length,
    vectorResults: [],
    divergenceMatrix: {},
  };

  // Initialize divergence matrix
  for (const a of adapters) {
    results.divergenceMatrix[a.manifest.name] = {};
    for (const b of adapters) {
      if (a.manifest.name !== b.manifest.name) {
        results.divergenceMatrix[a.manifest.name][b.manifest.name] = {
          none: 0, minor: 0, moderate: 0, significant: 0, opposite: 0,
        };
      }
    }
  }

  for (const vector of vectors) {
    const vectorResult = {
      vectorId: vector.metadata?.id,
      category: vector.metadata?.category,
      outputs: {},
      pairComparisons: [],
    };

    // Run all adapters
    for (const adapter of adapters) {
      const runResult = await runVector(adapter, vector);
      vectorResult.outputs[adapter.manifest.name] = {
        decision: runResult.output?.decision || null,
        predictions: runResult.output?.predictions || null,
        state: runResult.output?.state || null,
        elapsedMs: runResult.elapsedMs,
        error: runResult.error,
      };
    }

    // Pairwise comparison
    for (let i = 0; i < adapters.length; i++) {
      for (let j = i + 1; j < adapters.length; j++) {
        const nameA = adapters[i].manifest.name;
        const nameB = adapters[j].manifest.name;
        const outA = vectorResult.outputs[nameA];
        const outB = vectorResult.outputs[nameB];

        if (outA && outB && !outA.error && !outB.error) {
          // Wrap in adapter output format for compareOutputs
          const wrappedA = { decision: outA.decision, predictions: outA.predictions, state: outA.state };
          const wrappedB = { decision: outB.decision, predictions: outB.predictions, state: outB.state };

          const comparison = compareOutputs(wrappedA, wrappedB, {
            // Looser tolerances for cross-algorithm comparison
            rate: 0.5,
            eventualBG: 20.0,
            insulinReq: 0.2,
          });

          vectorResult.pairComparisons.push({
            adapterA: nameA,
            adapterB: nameB,
            divergence: comparison.summary.worstDivergence,
            fields: comparison.fields,
          });

          // Update divergence matrix
          const div = comparison.summary.worstDivergence;
          if (results.divergenceMatrix[nameA]?.[nameB]) {
            results.divergenceMatrix[nameA][nameB][div] =
              (results.divergenceMatrix[nameA][nameB][div] || 0) + 1;
          }
        }
      }
    }

    results.vectorResults.push(vectorResult);
  }

  // Compute summary statistics per adapter
  results.adapterSummaries = {};
  for (const adapter of adapters) {
    const name = adapter.manifest.name;
    const outputs = results.vectorResults
      .map(vr => vr.outputs[name])
      .filter(o => o && !o.error);

    const rates = outputs.map(o => o.decision?.rate).filter(r => r != null);
    const eventualBGs = outputs.map(o => o.predictions?.eventualBG).filter(e => e != null);

    results.adapterSummaries[name] = {
      successCount: outputs.length,
      errorCount: results.vectorResults.length - outputs.length,
      rateStats: computeStats(rates),
      eventualBGStats: computeStats(eventualBGs),
    };
  }

  return results;
}

function computeStats(values) {
  if (values.length === 0) return null;

  values.sort((a, b) => a - b);
  const sum = values.reduce((a, b) => a + b, 0);

  return {
    count: values.length,
    min: values[0],
    max: values[values.length - 1],
    mean: round(sum / values.length, 3),
    median: values[Math.floor(values.length / 2)],
  };
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

module.exports = { runBenchmark };
