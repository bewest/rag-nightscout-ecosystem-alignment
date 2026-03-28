'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Load TV-* conformance vectors from a directory.
 * Supports both flat directories and category subdirectories.
 *
 * @param {string} vectorDir - Path to vectors directory
 * @param {object} opts - { category, limit, ids }
 * @returns {object[]} Array of parsed vectors
 */
function loadVectors(vectorDir, opts = {}) {
  const absDir = path.resolve(vectorDir);

  if (!fs.existsSync(absDir)) {
    throw new Error(`Vector directory not found: ${absDir}`);
  }

  const files = collectJsonFiles(absDir);
  let vectors = [];

  for (const filePath of files) {
    try {
      const raw = fs.readFileSync(filePath, 'utf8');
      const vector = JSON.parse(raw);

      // Must have at minimum: input and metadata
      if (!vector.input || !vector.metadata) {
        continue;
      }

      vector._filePath = filePath;
      vectors.push(vector);
    } catch (err) {
      console.error(`Warning: skipping ${filePath}: ${err.message}`);
    }
  }

  // Apply filters
  if (opts.category) {
    vectors = vectors.filter(v => v.metadata.category === opts.category);
  }

  if (opts.ids && opts.ids.length > 0) {
    const idSet = new Set(opts.ids);
    vectors = vectors.filter(v => idSet.has(v.metadata.id));
  }

  // Sort by vector ID for deterministic ordering
  vectors.sort((a, b) => {
    const aId = a.metadata.id || '';
    const bId = b.metadata.id || '';
    return aId.localeCompare(bId, undefined, { numeric: true });
  });

  if (opts.limit && opts.limit > 0) {
    vectors = vectors.slice(0, opts.limit);
  }

  return vectors;
}

/**
 * Recursively collect .json files from a directory tree.
 */
function collectJsonFiles(dir) {
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectJsonFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.json')) {
      results.push(fullPath);
    }
  }

  return results;
}

/**
 * Load a single vector by file path.
 */
function loadVector(filePath) {
  const raw = fs.readFileSync(path.resolve(filePath), 'utf8');
  const vector = JSON.parse(raw);
  vector._filePath = filePath;
  return vector;
}

/**
 * Extract the expected output from a vector for comparison.
 * Returns normalized expected values.
 */
function extractExpected(vector) {
  const expected = vector.expected || {};
  const original = vector.originalOutput || {};

  return {
    rate: expected.rate ?? original.rate ?? null,
    duration: expected.duration ?? original.duration ?? null,
    eventualBG: expected.eventualBG ?? original.eventualBG ?? null,
    insulinReq: expected.insulinReq ?? original.insulinReq ?? null,
    iob: expected.iob ?? original.IOB ?? null,
    cob: expected.cob ?? original.COB ?? null,
    // Prediction trajectories from original output
    predictions: original.predBGs || null,
  };
}

/**
 * Get vector categories present in a loaded set.
 */
function getCategories(vectors) {
  const cats = new Set();
  for (const v of vectors) {
    if (v.metadata?.category) cats.add(v.metadata.category);
  }
  return [...cats].sort();
}

/**
 * Get summary statistics for a vector set.
 */
function summarizeVectors(vectors) {
  const categories = {};
  for (const v of vectors) {
    const cat = v.metadata?.category || 'unknown';
    categories[cat] = (categories[cat] || 0) + 1;
  }

  return {
    total: vectors.length,
    categories,
    ids: vectors.map(v => v.metadata?.id).filter(Boolean),
  };
}

module.exports = {
  loadVectors,
  loadVector,
  extractExpected,
  getCategories,
  summarizeVectors,
};
