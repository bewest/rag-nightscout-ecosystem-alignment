'use strict';

/**
 * Layer 0: Validation
 *
 * Validates the test infrastructure itself:
 * - Vector schema compliance
 * - Adapter health (can load, can describe)
 * - Input assembly validation (adapter's translation is inspectable)
 */

const { loadVectors, summarizeVectors } = require('../lib/vector-loader');
const { loadAdapter, discoverAdapters } = require('../lib/adapter-protocol');
const { validateInput } = require('../lib/adapter-protocol');
const { vectorToAdapterInput } = require('../lib/adapter-protocol');

/**
 * Run Layer 0 validation.
 *
 * @param {object} opts - { vectorDir, adapterDirs, verbose }
 * @returns {object} Validation report
 */
async function runValidation(opts) {
  const results = {
    vectors: null,
    adapters: [],
    inputAssembly: [],
    pass: true,
  };

  // 1. Validate vectors
  if (opts.vectorDir) {
    const vectors = loadVectors(opts.vectorDir);
    const summary = summarizeVectors(vectors);

    const vectorIssues = [];
    for (const v of vectors) {
      const input = vectorToAdapterInput(v);
      const { valid, errors } = validateInput(input);
      if (!valid) {
        vectorIssues.push({
          vectorId: v.metadata?.id,
          errors: errors.map(e => `${e.instancePath} ${e.message}`),
        });
      }
    }

    results.vectors = {
      total: summary.total,
      categories: summary.categories,
      schemaValid: summary.total - vectorIssues.length,
      schemaInvalid: vectorIssues.length,
      issues: vectorIssues,
    };

    if (vectorIssues.length > 0) results.pass = false;
  }

  // 2. Validate adapters
  for (const adapterDir of (opts.adapterDirs || [])) {
    try {
      const adapter = loadAdapter(adapterDir);

      // Health check: can it describe itself?
      let describeResult = null;
      try {
        describeResult = await adapter.invoke(null, { mode: 'describe' });
      } catch (err) {
        describeResult = { error: err.message };
      }

      results.adapters.push({
        name: adapter.manifest.name,
        dir: adapterDir,
        manifestValid: true,
        describeResult,
        healthy: !describeResult?.error,
      });

      if (describeResult?.error) results.pass = false;
    } catch (err) {
      results.adapters.push({
        name: adapterDir,
        dir: adapterDir,
        manifestValid: false,
        error: err.message,
        healthy: false,
      });
      results.pass = false;
    }
  }

  // 3. Input assembly validation (spot-check a few vectors through each adapter)
  if (opts.vectorDir && results.adapters.some(a => a.healthy)) {
    const vectors = loadVectors(opts.vectorDir, { limit: 3 });

    for (const adapterInfo of results.adapters.filter(a => a.healthy)) {
      const adapter = loadAdapter(adapterInfo.dir);

      for (const vector of vectors) {
        const adapterInput = vectorToAdapterInput(vector);

        try {
          const validation = await adapter.invoke(adapterInput, { mode: 'validate-input' });
          results.inputAssembly.push({
            vectorId: vector.metadata?.id,
            adapter: adapterInfo.name,
            valid: validation.valid,
            warnings: validation.warnings || [],
            fieldMapping: validation.fieldMapping || null,
          });
        } catch (err) {
          results.inputAssembly.push({
            vectorId: vector.metadata?.id,
            adapter: adapterInfo.name,
            valid: false,
            error: err.message,
          });
        }
      }
    }
  }

  return results;
}

module.exports = { runValidation };
