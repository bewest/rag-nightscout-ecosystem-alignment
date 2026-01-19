# Coverage Analysis Report

Generated: 2026-01-19T19:25:53.740272+00:00

## Summary

### Requirements Coverage

| Level | Count | Description |
|-------|-------|-------------|
| Full | 0 | Has mapping AND assertion |
| Partial | 10 | Has mapping OR assertion |
| Documented | 8 | Referenced but no mapping/assertion |
| None | 8 | No references found |
| **Total** | 26 | |

### Gaps Coverage

| Metric | Count |
|--------|-------|
| Total Gaps | 73 |
| Addressed in Spec | 20 |
| With Assertions | 7 |
| Orphaned | 4 |

## Uncovered Requirements

These requirements have no references in mappings, specs, or assertions:

- **REQ-010**: UTC Timestamps
- **REQ-020**: Event Immutability
- **REQ-030**: Sync Identity Preservation
- **REQ-031**: Self-Entry Exclusion
- **REQ-032**: Incremental Sync Support
- **REQ-033**: Server Deduplication
- **REQ-034**: Cross-Controller Coexistence
- **REQ-035**: Conflict Detection

## Orphaned Gaps

These gaps are defined but have no references elsewhere:

- **GAP-LIBRE-002**: Libre 2 Gen2 Session-Based Authentication
- **GAP-LIBRE-003**: Transmitter Bridge Firmware Variance
- **GAP-LIBRE-004**: Calibration Algorithm Not Synced
- **GAP-LIBRE-005**: Sensor Serial Number Not in Nightscout Entries

## Requirements Detail

| ID | Title | Mappings | Assertions | Level |
|----|-------|----------|------------|-------|
| REQ-001 | Override Identity | 1 | 0 | ⚠️ partial |
| REQ-002 | Override Supersession Tracking | 1 | 0 | ⚠️ partial |
| REQ-003 | Override Status Transitions | 1 | 0 | ⚠️ partial |
| REQ-010 | UTC Timestamps | 0 | 0 | ❌ none |
| REQ-020 | Event Immutability | 0 | 0 | ❌ none |
| REQ-030 | Sync Identity Preservation | 0 | 0 | ❌ none |
| REQ-031 | Self-Entry Exclusion | 0 | 0 | ❌ none |
| REQ-032 | Incremental Sync Support | 0 | 0 | ❌ none |
| REQ-033 | Server Deduplication | 0 | 0 | ❌ none |
| REQ-034 | Cross-Controller Coexistence | 0 | 0 | ❌ none |
| REQ-035 | Conflict Detection | 0 | 0 | ❌ none |
| REQ-040 | Bolus Amount Preservation | 0 | 1 | ⚠️ partial |
| REQ-041 | Carb Amount Preservation | 0 | 1 | ⚠️ partial |
| REQ-042 | Treatment Timestamp Accuracy | 0 | 1 | ⚠️ partial |
| REQ-043 | Automatic Bolus Flag | 0 | 1 | ⚠️ partial |
| REQ-044 | Duration Unit Normalization | 0 | 1 | ⚠️ partial |
| REQ-045 | Treatment Sync Identity Round-Trip | 0 | 1 | ⚠️ partial |
| REQ-046 | Absorption Time Unit Conversion | 0 | 1 | ⚠️ partial |
| REQ-050 | Source Device Attribution | 0 | 0 | 📄 documented |
| REQ-051 | UTC Timestamp for CGM Entries | 0 | 0 | 📄 documented |
| REQ-052 | Follower Source Indication | 0 | 0 | 📄 documented |
| REQ-053 | Calibration Provenance (Proposed) | 0 | 0 | 📄 documented |
| REQ-054 | Duplicate Prevention via UUID | 0 | 0 | 📄 documented |
| REQ-055 | Raw Sensor Value Preservation | 0 | 0 | 📄 documented |
| REQ-056 | Sensor Age Tracking | 0 | 0 | 📄 documented |
| REQ-057 | Bridge Device Identification | 0 | 0 | 📄 documented |
