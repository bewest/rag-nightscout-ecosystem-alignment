'use strict';

const DEFAULT_TOLERANCES = {
  rate: 0.05,            // U/hr
  duration: 1,           // minutes
  eventualBG: 10.0,      // mg/dL
  minPredBG: 10.0,       // mg/dL
  insulinReq: 0.05,      // U
  iob: 0.01,             // U
  cob: 1.0,              // g
  predictionMAE: 2.0,    // mg/dL
};

const DIVERGENCE_LEVELS = {
  NONE: 'none',           // Exact or within float precision
  MINOR: 'minor',         // Within tight tolerance
  MODERATE: 'moderate',   // Within loose tolerance
  SIGNIFICANT: 'significant', // Outside tolerance
  OPPOSITE: 'opposite',   // Direction reversal
};

/**
 * Compare two adapter outputs using tolerance-based comparison.
 *
 * @param {object} outputA - First adapter output (adapter-output schema)
 * @param {object} outputB - Second adapter output (or expected values)
 * @param {object} tolerances - Override default tolerances
 * @returns {object} Comparison result
 */
function compareOutputs(outputA, outputB, tolerances = {}) {
  const tol = { ...DEFAULT_TOLERANCES, ...tolerances };
  const fields = [];

  // Extract comparable values from both sides
  const a = extractComparables(outputA);
  const b = extractComparables(outputB);

  // Compare each numeric field
  for (const [field, tolValue] of Object.entries(tol)) {
    if (field === 'predictionMAE') continue; // handled separately

    const valA = a[field];
    const valB = b[field];

    if (valA == null && valB == null) continue;
    if (valA == null || valB == null) {
      fields.push({
        field,
        valueA: valA,
        valueB: valB,
        diff: null,
        absDiff: null,
        tolerance: tolValue,
        pass: false,
        divergence: DIVERGENCE_LEVELS.SIGNIFICANT,
        reason: `Missing in ${valA == null ? 'A' : 'B'}`,
      });
      continue;
    }

    const diff = valA - valB;
    const absDiff = Math.abs(diff);
    const pass = absDiff <= tolValue;
    const divergence = classifyDivergence(field, valA, valB, absDiff, tolValue);

    fields.push({
      field,
      valueA: valA,
      valueB: valB,
      diff: round(diff, 4),
      absDiff: round(absDiff, 4),
      tolerance: tolValue,
      pass,
      divergence,
    });
  }

  // Compare prediction trajectories (if present)
  const predComparison = comparePredictions(
    a.predictions,
    b.predictions,
    tol.predictionMAE
  );

  const allPassed = fields.every(f => f.pass) &&
    (predComparison ? predComparison.pass : true);

  return {
    pass: allPassed,
    fields,
    predictions: predComparison,
    summary: {
      totalFields: fields.length,
      passed: fields.filter(f => f.pass).length,
      failed: fields.filter(f => !f.pass).length,
      worstDivergence: worstDivergence(fields),
    },
  };
}

/**
 * Compare an adapter output against expected values from a vector.
 */
function compareToExpected(adapterOutput, expected, tolerances = {}) {
  // Wrap expected values in the same shape as adapter output
  const pseudoOutput = {
    decision: {
      rate: expected.rate,
      duration: expected.duration,
    },
    predictions: {
      eventualBG: expected.eventualBG,
      iob: expected.predictions?.IOB || expected.predictions?.iob || [],
      zt: expected.predictions?.ZT || expected.predictions?.zt || [],
      cob: expected.predictions?.COB || expected.predictions?.cob || [],
      uam: expected.predictions?.UAM || expected.predictions?.uam || [],
    },
    state: {
      iob: expected.iob,
      cob: expected.cob,
      insulinReq: expected.insulinReq,
    },
  };

  return compareOutputs(adapterOutput, pseudoOutput, tolerances);
}

/**
 * Extract comparable numeric values from any output shape.
 * Handles both adapter-output format and raw expected values.
 */
function extractComparables(output) {
  if (!output) return {};

  // Adapter output format
  if (output.decision || output.state) {
    return {
      rate: output.decision?.rate ?? null,
      duration: output.decision?.duration ?? null,
      eventualBG: output.predictions?.eventualBG ?? null,
      minPredBG: output.predictions?.minPredBG ?? null,
      insulinReq: output.state?.insulinReq ?? null,
      iob: output.state?.iob ?? null,
      cob: output.state?.cob ?? null,
      predictions: {
        iob: output.predictions?.iob || [],
        zt: output.predictions?.zt || [],
        cob: output.predictions?.cob || [],
        uam: output.predictions?.uam || [],
      },
    };
  }

  // Raw expected format (from vector)
  return {
    rate: output.rate ?? null,
    duration: output.duration ?? null,
    eventualBG: output.eventualBG ?? null,
    minPredBG: output.minPredBG ?? null,
    insulinReq: output.insulinReq ?? null,
    iob: output.iob ?? null,
    cob: output.cob ?? null,
    predictions: output.predictions || {},
  };
}

/**
 * Classify divergence level between two values.
 */
function classifyDivergence(field, valA, valB, absDiff, tolerance) {
  // Direction reversal for rate changes
  if (field === 'rate') {
    if ((valA > 0 && valB <= 0) || (valA <= 0 && valB > 0)) {
      return DIVERGENCE_LEVELS.OPPOSITE;
    }
  }

  if (absDiff <= tolerance * 0.1) return DIVERGENCE_LEVELS.NONE;
  if (absDiff <= tolerance) return DIVERGENCE_LEVELS.MINOR;
  if (absDiff <= tolerance * 5) return DIVERGENCE_LEVELS.MODERATE;
  return DIVERGENCE_LEVELS.SIGNIFICANT;
}

/**
 * Compare prediction trajectory arrays using Mean Absolute Error.
 */
function comparePredictions(predsA, predsB, maeTolerance) {
  if (!predsA || !predsB) return null;

  const results = {};
  let overallMAE = 0;
  let trajectoryCount = 0;

  for (const key of ['iob', 'zt', 'cob', 'uam']) {
    const a = predsA[key] || [];
    const b = predsB[key] || [];

    if (a.length === 0 && b.length === 0) continue;
    if (a.length === 0 || b.length === 0) {
      results[key] = { mae: null, length: { a: a.length, b: b.length }, pass: false };
      continue;
    }

    const minLen = Math.min(a.length, b.length);
    let totalError = 0;

    for (let i = 0; i < minLen; i++) {
      totalError += Math.abs(a[i] - b[i]);
    }

    const mae = round(totalError / minLen, 2);
    results[key] = {
      mae,
      length: { a: a.length, b: b.length },
      pass: mae <= maeTolerance,
    };

    overallMAE += mae;
    trajectoryCount++;
  }

  const avgMAE = trajectoryCount > 0 ? round(overallMAE / trajectoryCount, 2) : null;

  return {
    trajectories: results,
    avgMAE,
    pass: Object.values(results).every(r => r.pass !== false),
  };
}

/**
 * Find the worst divergence level in a set of field comparisons.
 */
function worstDivergence(fields) {
  const order = [
    DIVERGENCE_LEVELS.NONE,
    DIVERGENCE_LEVELS.MINOR,
    DIVERGENCE_LEVELS.MODERATE,
    DIVERGENCE_LEVELS.SIGNIFICANT,
    DIVERGENCE_LEVELS.OPPOSITE,
  ];

  let worst = 0;
  for (const f of fields) {
    const idx = order.indexOf(f.divergence);
    if (idx > worst) worst = idx;
  }

  return order[worst] || DIVERGENCE_LEVELS.NONE;
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

module.exports = {
  compareOutputs,
  compareToExpected,
  extractComparables,
  comparePredictions,
  DEFAULT_TOLERANCES,
  DIVERGENCE_LEVELS,
};
