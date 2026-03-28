'use strict';

/**
 * Layer 1: Equivalence Testing
 *
 * Tests that multiple implementations of the SAME algorithm produce
 * equivalent outputs given the same inputs.
 *
 * Key design: separates input assembly failures from algorithm differences.
 * When two adapters disagree, we can inspect each adapter's native input
 * (via validate-input mode) to determine if the disagreement is due to
 * different input translation or genuine algorithm divergence.
 */

const { loadVectors, extractExpected } = require('../lib/vector-loader');
const { loadAdapter, runVector, vectorToAdapterInput } = require('../lib/adapter-protocol');
const { compareOutputs, compareToExpected } = require('../lib/output-comparator');

/**
 * Run equivalence test: same vectors through multiple adapters of the same algorithm.
 *
 * @param {object} opts
 *   - vectorDir: path to vectors
 *   - adapterDirs: array of adapter directory paths
 *   - tolerances: override comparison tolerances
 *   - limit: max vectors to test
 *   - ids: specific vector IDs to test
 *   - verbose: include native inputs in results
 * @returns {object} Equivalence test results
 */
async function runEquivalence(opts) {
  const vectors = loadVectors(opts.vectorDir, {
    limit: opts.limit,
    ids: opts.ids,
  });

  const adapters = (opts.adapterDirs || []).map(dir => loadAdapter(dir));

  if (adapters.length === 0) {
    return { error: 'No adapters specified', pass: false };
  }

  const results = {
    mode: adapters.length === 1 ? 'single-adapter-vs-expected' : 'cross-adapter',
    adapters: adapters.map(a => a.manifest.name),
    vectorCount: vectors.length,
    vectorResults: [],
    pass: true,
  };

  for (const vector of vectors) {
    const vectorResult = {
      vectorId: vector.metadata?.id,
      category: vector.metadata?.category,
      adapterResults: {},
      crossComparisons: [],
      pass: true,
    };

    // Run each adapter
    for (const adapter of adapters) {
      const runResult = await runVector(adapter, vector, {
        mode: 'execute',
        verbose: opts.verbose,
      });

      // Also compare against expected values from the vector
      const expected = extractExpected(vector);
      let vsExpected = null;

      if (runResult.output && !runResult.error) {
        vsExpected = compareToExpected(runResult.output, expected, opts.tolerances);
      }

      vectorResult.adapterResults[adapter.manifest.name] = {
        output: runResult.output,
        error: runResult.error,
        elapsedMs: runResult.elapsedMs,
        vsExpected,
      };
    }

    // Cross-adapter comparison (if multiple adapters)
    if (adapters.length >= 2) {
      const adapterNames = Object.keys(vectorResult.adapterResults);

      for (let i = 0; i < adapterNames.length; i++) {
        for (let j = i + 1; j < adapterNames.length; j++) {
          const nameA = adapterNames[i];
          const nameB = adapterNames[j];
          const outA = vectorResult.adapterResults[nameA].output;
          const outB = vectorResult.adapterResults[nameB].output;

          if (outA && outB && !outA.error && !outB.error) {
            const comparison = compareOutputs(outA, outB, opts.tolerances);
            vectorResult.crossComparisons.push({
              adapterA: nameA,
              adapterB: nameB,
              comparison,
            });

            if (!comparison.pass) vectorResult.pass = false;
          } else {
            vectorResult.crossComparisons.push({
              adapterA: nameA,
              adapterB: nameB,
              comparison: null,
              error: 'One or both adapters failed to produce output',
            });
            vectorResult.pass = false;
          }
        }
      }
    } else {
      // Single adapter: pass/fail based on vs-expected
      const singleResult = Object.values(vectorResult.adapterResults)[0];
      if (singleResult.vsExpected && !singleResult.vsExpected.pass) {
        vectorResult.pass = false;
      }
      if (singleResult.error) {
        vectorResult.pass = false;
      }
    }

    if (!vectorResult.pass) results.pass = false;
    results.vectorResults.push(vectorResult);
  }

  // Aggregate statistics
  const passed = results.vectorResults.filter(r => r.pass).length;
  results.summary = {
    passed,
    failed: results.vectorResults.length - passed,
    passRate: vectors.length > 0 ? passed / vectors.length : 0,
  };

  return results;
}

/**
 * Diagnose an equivalence failure by inspecting input assembly.
 * When two adapters disagree, this shows whether the inputs were different.
 */
async function diagnoseFailure(vector, adapterDirs, opts = {}) {
  const adapters = adapterDirs.map(dir => loadAdapter(dir));
  const adapterInput = vectorToAdapterInput(vector);

  const nativeInputs = {};

  for (const adapter of adapters) {
    try {
      const validation = await adapter.invoke(adapterInput, { mode: 'validate-input' });
      nativeInputs[adapter.manifest.name] = {
        valid: validation.valid,
        nativeInput: validation.nativeInput,
        warnings: validation.warnings,
      };
    } catch (err) {
      nativeInputs[adapter.manifest.name] = { error: err.message };
    }
  }

  return {
    vectorId: vector.metadata?.id,
    adapterInput,
    nativeInputs,
  };
}

module.exports = { runEquivalence, diagnoseFailure };
