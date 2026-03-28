'use strict';

const COLORS = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  dim: '\x1b[2m',
  bold: '\x1b[1m',
};

const DIVERGENCE_SYMBOLS = {
  none: `${COLORS.green}✓${COLORS.reset}`,
  minor: `${COLORS.green}~${COLORS.reset}`,
  moderate: `${COLORS.yellow}△${COLORS.reset}`,
  significant: `${COLORS.red}✗${COLORS.reset}`,
  opposite: `${COLORS.red}⇄${COLORS.reset}`,
};

/**
 * Format a single vector comparison result as a one-line summary.
 */
function formatVectorLine(result) {
  const id = (result.vectorId || '???').padEnd(8);
  const pass = result.comparison?.pass;
  const icon = pass ? `${COLORS.green}PASS${COLORS.reset}` : `${COLORS.red}FAIL${COLORS.reset}`;
  const divergence = result.comparison?.summary?.worstDivergence || 'unknown';
  const divIcon = DIVERGENCE_SYMBOLS[divergence] || '?';

  const details = (result.comparison?.fields || [])
    .filter(f => !f.pass)
    .map(f => `${f.field}:${f.valueA}→${f.valueB}(Δ${f.absDiff})`)
    .join(' ');

  return `  ${divIcon} ${id} ${icon} ${details}`;
}

/**
 * Format a full equivalence/benchmark report.
 */
function formatReport(results, opts = {}) {
  const lines = [];
  const title = opts.title || 'Test Harness Report';

  lines.push('');
  lines.push(`${COLORS.bold}${title}${COLORS.reset}`);
  lines.push(`${'─'.repeat(60)}`);

  // Adapter info
  const adapters = [...new Set(results.map(r => r.adapter))];
  lines.push(`Adapters: ${adapters.join(', ')}`);
  lines.push(`Vectors:  ${results.length}`);
  lines.push('');

  // Per-vector results
  const passed = results.filter(r => r.comparison?.pass);
  const failed = results.filter(r => !r.comparison?.pass);

  if (failed.length > 0) {
    lines.push(`${COLORS.red}Failed (${failed.length}):${COLORS.reset}`);
    for (const r of failed) {
      lines.push(formatVectorLine(r));
    }
    lines.push('');
  }

  if (passed.length > 0 && opts.verbose) {
    lines.push(`${COLORS.green}Passed (${passed.length}):${COLORS.reset}`);
    for (const r of passed) {
      lines.push(formatVectorLine(r));
    }
    lines.push('');
  }

  // Summary
  lines.push(`${'─'.repeat(60)}`);
  const rate = results.length > 0
    ? ((passed.length / results.length) * 100).toFixed(1)
    : '0.0';
  const icon = passed.length === results.length
    ? COLORS.green
    : COLORS.red;

  lines.push(`${icon}${passed.length}/${results.length} passed (${rate}%)${COLORS.reset}`);

  // Divergence distribution
  const divCounts = {};
  for (const r of results) {
    const div = r.comparison?.summary?.worstDivergence || 'error';
    divCounts[div] = (divCounts[div] || 0) + 1;
  }
  const divLine = Object.entries(divCounts)
    .map(([k, v]) => `${DIVERGENCE_SYMBOLS[k] || k}${k}:${v}`)
    .join('  ');
  lines.push(`Divergence: ${divLine}`);

  // Timing
  const times = results.map(r => r.elapsedMs).filter(Boolean);
  if (times.length > 0) {
    const avg = (times.reduce((a, b) => a + b, 0) / times.length).toFixed(0);
    const max = Math.max(...times);
    lines.push(`${COLORS.dim}Timing: avg ${avg}ms, max ${max}ms${COLORS.reset}`);
  }

  lines.push('');
  return lines.join('\n');
}

/**
 * Format results as JSON for machine consumption.
 */
function formatJSON(results, opts = {}) {
  const passed = results.filter(r => r.comparison?.pass).length;

  return JSON.stringify({
    title: opts.title || 'Test Harness Report',
    adapters: [...new Set(results.map(r => r.adapter))],
    totalVectors: results.length,
    passed,
    failed: results.length - passed,
    passRate: results.length > 0 ? passed / results.length : 0,
    results: results.map(r => ({
      vectorId: r.vectorId,
      adapter: r.adapter,
      pass: r.comparison?.pass ?? false,
      divergence: r.comparison?.summary?.worstDivergence || 'error',
      failedFields: (r.comparison?.fields || []).filter(f => !f.pass).map(f => ({
        field: f.field,
        expected: f.valueB,
        actual: f.valueA,
        diff: f.absDiff,
        tolerance: f.tolerance,
      })),
      elapsedMs: r.elapsedMs,
      error: r.error,
    })),
  }, null, 2);
}

/**
 * Format an equivalence matrix (multiple adapters × multiple vectors).
 */
function formatEquivalenceMatrix(matrixResults) {
  const lines = [];
  const adapters = Object.keys(matrixResults);

  if (adapters.length < 2) {
    return 'Need at least 2 adapters for equivalence comparison.\n';
  }

  lines.push('');
  lines.push(`${COLORS.bold}Equivalence Matrix${COLORS.reset}`);
  lines.push(`${'─'.repeat(60)}`);

  // Header
  const header = 'Vector'.padEnd(10) + adapters.map(a => a.padEnd(16)).join('');
  lines.push(header);

  // Get all vector IDs
  const vectorIds = [...new Set(
    Object.values(matrixResults).flatMap(results =>
      results.map(r => r.vectorId)
    )
  )].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

  for (const vid of vectorIds) {
    let row = vid.padEnd(10);
    for (const adapter of adapters) {
      const result = matrixResults[adapter]?.find(r => r.vectorId === vid);
      if (!result) {
        row += `${COLORS.dim}skip${COLORS.reset}`.padEnd(16);
      } else if (result.error) {
        row += `${COLORS.red}err${COLORS.reset} `.padEnd(16);
      } else {
        const rate = result.output?.decision?.rate;
        const display = rate != null ? rate.toFixed(2) : 'null';
        row += display.padEnd(16);
      }
    }
    lines.push(row);
  }

  lines.push('');
  return lines.join('\n');
}

module.exports = {
  formatReport,
  formatJSON,
  formatVectorLine,
  formatEquivalenceMatrix,
};
