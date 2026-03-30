'use strict';

/**
 * Mock round_basal matching AAPS's Rhino behavior.
 *
 * AAPS (DetermineBasalAdapterSMBJS.kt:117) mocks round_basal as identity:
 *   "var round_basal = function round_basal(basal, profile) { return basal; };"
 *
 * This is a significant difference from upstream oref0 which rounds to pump
 * precision (typically 0.05 U/hr, or 0.025 for x23/x54 pumps at <1 U/hr).
 */
module.exports = function round_basal(basal, profile) {
  return basal;
};
