# Reporting Needs Analysis: nightscout-reporter vs Built-in Reports

> **Sources**: nightscout-reporter (zreptil), cgm-remote-monitor report_plugins  
> **Generated**: 2026-01-29  
> **Focus**: Capability comparison, gaps, standardization opportunities

---

## Executive Summary

| Aspect | cgm-remote-monitor | nightscout-reporter |
|--------|-------------------|---------------------|
| **Platform** | Browser (JavaScript) | Browser (Dart/Angular) |
| **Output** | HTML in browser | PDF download |
| **Reports** | 11 plugins | 17 print forms |
| **Total Code** | ~4,738 lines | ~15,000+ lines |
| **API** | v1 (client-side) | v1 (client-side) |
| **Maintenance** | Active | Deprecated (→ Angular) |

**Key Finding**: Both compute statistics client-side. A server-side statistics API (see `statistics-api-proposal.md`) would reduce duplication and enable standardization.

---

## 1. cgm-remote-monitor Built-in Reports

Located in `lib/report_plugins/`:

| Report | Lines | Purpose |
|--------|-------|---------|
| `daytoday.js` | 1,114 | Day-by-day glucose graph with treatments |
| `loopalyzer.js` | 1,270 | Loop-specific IOB/COB analysis |
| `glucosedistribution.js` | 488 | Glucose distribution histogram |
| `treatments.js` | 365 | Treatment log with filtering |
| `weektoweek.js` | 326 | Week comparison view |
| `calibrations.js` | 276 | Calibration history |
| `hourlystats.js` | 218 | Hour-by-hour averages |
| `success.js` | 214 | Time-in-range success metrics |
| `percentile.js` | 197 | Percentile distribution |
| `dailystats.js` | 165 | Daily statistics summary |
| `profiles.js` | 105 | Profile visualization |

**Total**: ~4,738 lines across 11 reports

### Key Capabilities

- Real-time rendering in browser
- Integrated with Nightscout UI
- Treatment overlay on graphs
- Loop/OpenAPS specific analysis (loopalyzer)
- Configurable date ranges

### Limitations

- HTML only (no PDF export)
- Statistics computed per-request
- No standardized calculation library
- Each report implements own logic

---

## 2. nightscout-reporter (zreptil)

Located in `lib/src/forms/`:

| Report | Purpose |
|--------|---------|
| `print-daily-graphic.dart` | Daily glucose graph |
| `print-daily-hours.dart` | Hour-by-hour breakdown |
| `print-daily-statistics.dart` | Daily stats summary |
| `print-daily-analysis.dart` | In-depth daily analysis |
| `print-daily-log.dart` | Detailed event log |
| `print-daily-profile.dart` | Profile for day |
| `print-daily-gluc.dart` | Glucose-focused daily |
| `print-weekly-graphic.dart` | Week overview |
| `print-analysis.dart` | Statistical analysis |
| `print-percentile.dart` | Percentile chart |
| `print-gluc-distribution.dart` | Distribution histogram |
| `print-profile.dart` | Profile visualization |
| `print-basalrate.dart` | Basal rate chart |
| `print-cgp.dart` | CGP (Control Grid) |
| `print-user-data.dart` | User data summary |
| `print-test.dart` | Testing/debug |
| `print-template.dart` | Template base |

**Total**: 17 report types, ~15,000+ lines

### Key Capabilities

- PDF generation for printing/sharing
- Multi-language support
- Extensive customization options
- Ambulatory Glucose Profile (AGP) support
- Insulin profile visualization
- Treatment classification intelligence

### Advanced Features

From `mapping/nightscout-reporter/`:

1. **Uploader Detection** (`uploader-detection.md`)
   - Identifies data source from `enteredBy` field
   - Distinguishes OpenAPS, AAPS, Loop, xDrip+, etc.

2. **Treatment Classification** (`treatment-classification.md`)
   - Smart categorization of eventTypes
   - Edge case handling

3. **Calculations** (`calculations.md`)
   - COB/IOB computation
   - TIR (Time in Range)
   - Statistical aggregations

4. **Unit Conversion** (`unit-conversion.md`)
   - mg/dL ↔ mmol/L handling

---

## 3. Feature Comparison Matrix

| Feature | cgm-remote-monitor | nightscout-reporter |
|---------|-------------------|---------------------|
| **Daily Graph** | ✅ daytoday | ✅ print-daily-graphic |
| **Glucose Distribution** | ✅ glucosedistribution | ✅ print-gluc-distribution |
| **Percentile Chart** | ✅ percentile | ✅ print-percentile |
| **Time in Range** | ✅ success | ✅ print-analysis |
| **Hourly Stats** | ✅ hourlystats | ✅ print-daily-hours |
| **Weekly View** | ✅ weektoweek | ✅ print-weekly-graphic |
| **Profile View** | ✅ profiles | ✅ print-profile |
| **Treatment Log** | ✅ treatments | ✅ print-daily-log |
| **Calibrations** | ✅ calibrations | ❌ Not separate |
| **Loop Analysis** | ✅ loopalyzer | ⚠️ Via uploader detection |
| **PDF Export** | ❌ | ✅ |
| **AGP (Ambulatory Glucose Profile)** | ❌ | ✅ print-cgp |
| **Basal Rate Chart** | ❌ | ✅ print-basalrate |
| **Multi-language** | ⚠️ Via translations | ✅ Built-in |
| **Insulin Profiles** | ❌ | ✅ |

---

## 4. Calculation Comparison

### Time in Range (TIR)

**cgm-remote-monitor** (`success.js`):
```javascript
// Counts entries in target range
var inRange = entries.filter(e => e.sgv >= low && e.sgv <= high).length;
var tir = (inRange / entries.length) * 100;
```

**nightscout-reporter** (`calculations.md`):
```dart
// More sophisticated with configurable ranges
double tirLow = entries.where((e) => e.gluc < lowLimit).length / total * 100;
double tirTarget = entries.where((e) => e.gluc >= lowLimit && e.gluc <= highLimit).length / total * 100;
double tirHigh = entries.where((e) => e.gluc > highLimit).length / total * 100;
```

### Estimated A1C

**cgm-remote-monitor**: Not directly computed
**nightscout-reporter**: `hba1c = (avgGluc + 46.7) / 28.7` (DCCT formula)

---

## 5. Gaps Identified

### GAP-REPORT-001: No Server-Side Statistics API

**Description**: Both cgm-remote-monitor and nightscout-reporter compute statistics client-side, duplicating logic and preventing standardization.

**Impact**:
- Inconsistent calculations between clients
- High client-side computation load
- No standard statistics endpoint

**Remediation**: Implement `statistics-api-proposal.md` server-side endpoints.

### GAP-REPORT-002: No PDF Export in cgm-remote-monitor

**Description**: Built-in reports render HTML only. Users wanting PDF must use nightscout-reporter or browser print-to-PDF.

**Impact**:
- Suboptimal for clinical sharing
- Requires separate tool for print

**Remediation**: Add PDF export capability or integrate with nightscout-reporter.

### GAP-REPORT-003: Loop Analysis Fragmented

**Description**: Loop/OpenAPS analysis exists in `loopalyzer.js` for cgm-remote-monitor, but nightscout-reporter uses uploader detection heuristics instead of dedicated analysis.

**Impact**:
- Inconsistent loop analysis across tools
- Different metrics computed

**Remediation**: Standardize loop analysis metrics.

---

## 6. Standardization Opportunities

### Server-Side Statistics (from statistics-api-proposal.md)

Proposed endpoints that would unify reporting:

| Endpoint | Purpose |
|----------|---------|
| `/api/v3/statistics/tir` | Time in Range |
| `/api/v3/statistics/daily` | Daily aggregates |
| `/api/v3/statistics/a1c` | Estimated A1C |
| `/api/v3/statistics/agp` | Ambulatory Glucose Profile |

### Shared Calculation Library

Both tools could use a shared library for:
- TIR calculation
- A1C estimation
- COB/IOB algorithms
- Glucose variability metrics (CV, SD, GV)

---

## 7. Recommendations

| Priority | Action | Effort |
|----------|--------|--------|
| P1 | Implement server-side statistics API | High |
| P2 | Document calculation algorithms in specs/ | Medium |
| P3 | Add PDF export to cgm-remote-monitor | Medium |
| P4 | Create shared calculation library | High |

---

## 8. Code References

| System | Path | Purpose |
|--------|------|---------|
| cgm-remote-monitor | `lib/report_plugins/` | 11 built-in reports |
| nightscout-reporter | `lib/src/forms/` | 17 print forms |
| nightscout-reporter | `lib/src/json_data.dart` | Data models (2,869 lines) |
| Statistics proposal | `docs/sdqctl-proposals/statistics-api-proposal.md` | Server-side API design |

---

## Cross-References

- [nightscout-reporter mapping](../../mapping/nightscout-reporter/) - 2,559 lines of documentation
- [Statistics API Proposal](statistics-api-proposal.md) - Server-side statistics design
- [cgm-remote-monitor Plugin Deep Dive](../10-domain/cgm-remote-monitor-plugin-deep-dive.md) - Plugin architecture
