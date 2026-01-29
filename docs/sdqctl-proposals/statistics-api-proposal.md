# Statistics API Proposal for Nightscout

> **Version**: 1.0  
> **Date**: 2026-01-29  
> **Status**: Draft  
> **Related**: PR#8366 (2025 reports), nightscout-reporter integration

## Executive Summary

This proposal defines a server-side Statistics API for Nightscout that provides pre-computed glucose aggregations, reducing client-side computation burden and enabling efficient AI/LLM integration via MCP (Model Context Protocol) patterns.

### Problem Statement

Current state:
1. **Client-side computation**: Reports calculate statistics in browser (nightscout-reporter, cgm-remote-monitor reports)
2. **Redundant API calls**: Each report fetches raw entries and recomputes aggregations
3. **No aggregate endpoints**: API v3 provides CRUD operations but no statistical summaries
4. **LLM inefficiency**: AI tools must fetch thousands of entries to compute simple statistics

### Proposed Solution

Add `/api/v3/stats` endpoint family providing pre-computed aggregations:
- Daily/weekly/monthly summaries
- Time-in-range calculations
- Percentile distributions
- Estimated A1C values
- Glycemic variability metrics

---

## Requirements

### REQ-STATS-001: Daily Aggregation Endpoint

**Statement**: The system MUST provide a `/api/v3/stats/daily` endpoint returning per-day glucose statistics.

**Rationale**: Eliminates client-side computation for daily reports.

**Response Schema**:
```json
{
  "date": "2026-01-29",
  "entries": {
    "count": 288,
    "gaps": 3,
    "coverage": 0.98
  },
  "glucose": {
    "mean": 142.5,
    "median": 138.0,
    "min": 72,
    "max": 245,
    "stdDev": 32.4,
    "cv": 22.7
  },
  "percentiles": {
    "p10": 98,
    "p25": 115,
    "p50": 138,
    "p75": 165,
    "p90": 192
  },
  "ranges": {
    "veryLow": { "count": 2, "percent": 0.7, "threshold": 54 },
    "low": { "count": 8, "percent": 2.8, "threshold": 70 },
    "inRange": { "count": 215, "percent": 74.7, "low": 70, "high": 180 },
    "high": { "count": 55, "percent": 19.1, "threshold": 180 },
    "veryHigh": { "count": 8, "percent": 2.8, "threshold": 250 }
  },
  "estimates": {
    "a1c_dcct": 6.6,
    "a1c_ifcc": 49,
    "gmi": 6.8
  }
}
```

---

### REQ-STATS-002: Period Summary Endpoint

**Statement**: The system MUST provide a `/api/v3/stats/summary` endpoint returning aggregated statistics for a date range.

**Query Parameters**:
- `from`: Start date (ISO8601)
- `to`: End date (ISO8601)
- `period`: Aggregation period (`day`, `week`, `month`)

**Response Schema**:
```json
{
  "period": {
    "from": "2026-01-01",
    "to": "2026-01-29",
    "days": 29
  },
  "glucose": {
    "mean": 145.2,
    "median": 140.0,
    "stdDev": 35.1,
    "cv": 24.2,
    "gvi": 1.32,
    "pgs": 85.4
  },
  "ranges": {
    "veryLow": 0.5,
    "low": 2.1,
    "inRange": 72.3,
    "high": 21.8,
    "veryHigh": 3.3
  },
  "estimates": {
    "a1c_dcct": 6.7,
    "a1c_ifcc": 50,
    "gmi": 6.9
  },
  "variability": {
    "meanDailyChange": 142.5,
    "meanHourlyChange": 5.9,
    "fluctuationRate5": 45.2,
    "fluctuationRate10": 12.3
  }
}
```

---

### REQ-STATS-003: Hourly Distribution Endpoint

**Statement**: The system SHOULD provide a `/api/v3/stats/hourly` endpoint returning hourly glucose distributions.

**Rationale**: Enables percentile charts without fetching all entries.

**Response Schema**:
```json
{
  "period": { "from": "2026-01-01", "to": "2026-01-29" },
  "hours": [
    {
      "hour": 0,
      "count": 812,
      "mean": 138.5,
      "percentiles": { "p10": 95, "p25": 112, "p50": 135, "p75": 158, "p90": 185 }
    },
    {
      "hour": 1,
      "count": 798,
      "mean": 132.1,
      "percentiles": { "p10": 92, "p25": 108, "p50": 128, "p75": 152, "p90": 178 }
    }
    // ... hours 2-23
  ]
}
```

---

### REQ-STATS-004: Treatment Aggregation Endpoint

**Statement**: The system SHOULD provide a `/api/v3/stats/treatments` endpoint returning insulin and carb summaries.

**Response Schema**:
```json
{
  "period": { "from": "2026-01-01", "to": "2026-01-29", "days": 29 },
  "insulin": {
    "totalDaily": 42.5,
    "basal": 22.1,
    "bolus": 20.4,
    "smb": 3.2,
    "correction": 5.1,
    "carbBolus": 12.1
  },
  "carbs": {
    "totalDaily": 185,
    "avgPerMeal": 45.2,
    "mealsPerDay": 4.1
  },
  "ratios": {
    "bolusToBasal": 0.92,
    "carbToBolus": 15.2,
    "tdd": 42.5
  }
}
```

---

### REQ-STATS-005: MCP Resource Provider

**Statement**: The Statistics API SHOULD be exposed as MCP (Model Context Protocol) resources for AI/LLM consumption.

**Rationale**: Enables efficient integration with AI assistants and health analysis tools.

**MCP Resource Definitions**:
```json
{
  "resources": [
    {
      "uri": "nightscout://stats/daily/{date}",
      "name": "Daily glucose statistics",
      "mimeType": "application/json"
    },
    {
      "uri": "nightscout://stats/summary?days={n}",
      "name": "Period summary statistics",
      "mimeType": "application/json"
    },
    {
      "uri": "nightscout://stats/current",
      "name": "Current glucose and recent statistics",
      "mimeType": "application/json"
    }
  ]
}
```

---

## API Specification

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v3/stats/daily` | Daily statistics array |
| GET | `/api/v3/stats/daily/{date}` | Single day statistics |
| GET | `/api/v3/stats/summary` | Period summary |
| GET | `/api/v3/stats/hourly` | Hourly distribution |
| GET | `/api/v3/stats/treatments` | Treatment aggregations |
| GET | `/api/v3/stats/current` | Real-time current statistics |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from` | ISO8601 | 14 days ago | Start date |
| `to` | ISO8601 | now | End date |
| `units` | `mg/dL`, `mmol/L` | profile | Glucose units |
| `targetLow` | number | profile | Low threshold |
| `targetHigh` | number | profile | High threshold |

### Authentication

Uses existing Nightscout authentication:
- API Secret header: `api-secret: <sha1-hash>`
- JWT token: `Authorization: Bearer <token>`
- Requires `readable` permission minimum

---

## Implementation Design

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API v3 Layer                         │
│  /api/v3/stats/*                                        │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│              Stats Service (lib/server/stats.js)        │
│  - Aggregation logic                                    │
│  - Caching layer                                        │
│  - Formula implementations                              │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│              MongoDB Aggregation Pipeline               │
│  - $match (date range)                                  │
│  - $group (by day/hour)                                 │
│  - $project (statistics)                                │
└─────────────────────────────────────────────────────────┘
```

### MongoDB Aggregation Pipeline

```javascript
// Daily aggregation pipeline
[
  { $match: { 
    type: 'sgv',
    date: { $gte: fromDate, $lte: toDate }
  }},
  { $group: {
    _id: { $dateToString: { format: "%Y-%m-%d", date: "$dateString" } },
    count: { $sum: 1 },
    mean: { $avg: "$sgv" },
    min: { $min: "$sgv" },
    max: { $max: "$sgv" },
    stdDev: { $stdDevPop: "$sgv" },
    values: { $push: "$sgv" }  // For percentile calculation
  }},
  { $project: {
    date: "$_id",
    count: 1,
    mean: { $round: ["$mean", 1] },
    min: 1,
    max: 1,
    stdDev: { $round: ["$stdDev", 1] },
    cv: { $round: [{ $multiply: [{ $divide: ["$stdDev", "$mean"] }, 100] }, 1] }
  }}
]
```

### Caching Strategy

| Endpoint | Cache Duration | Invalidation |
|----------|----------------|--------------|
| `/stats/daily/{date}` | 24 hours | New entries for that date |
| `/stats/summary` | 5 minutes | Any new entries |
| `/stats/hourly` | 15 minutes | Any new entries |
| `/stats/current` | 30 seconds | Real-time |

---

## Formulas Reference

### A1C Estimation

**DCCT Formula** (Nathan et al. 2008):
```
A1C (%) = (mean_glucose_mg_dl + 46.7) / 28.7
```

**IFCC Formula**:
```
A1C (mmol/mol) = (A1C_DCCT - 2.15) × 10.929
```

**GMI (Glucose Management Indicator)**:
```
GMI (%) = 3.31 + (0.02392 × mean_glucose_mg_dl)
```

### Glycemic Variability

**GVI (Glycemic Variability Index)**:
```
GVI = (Σ √(ΔTime² + ΔGlucose²)) / (Σ ΔTime)
```
Where ideal GVI = 1.0 (straight line)

**PGS (Patient Glycemic Status)**:
```
PGS = GVI × MeanGlucose × (1 - TIR_multiplier)
```
Where TIR_multiplier weights time-in-range

**Coefficient of Variation (CV)**:
```
CV (%) = (StdDev / Mean) × 100
```
Target: CV < 36% (ADA recommendation)

### Time-in-Range

| Range | Threshold (mg/dL) | Target (ADA) |
|-------|-------------------|--------------|
| Very Low | < 54 | < 1% |
| Low | 54-70 | < 4% |
| In Range | 70-180 | > 70% |
| High | 180-250 | < 25% |
| Very High | > 250 | < 5% |

---

## Migration Path

### Phase 1: Core Statistics (Effort: Medium)

1. Add `lib/server/stats.js` service
2. Implement MongoDB aggregation pipelines
3. Create `/api/v3/stats/daily` endpoint
4. Create `/api/v3/stats/summary` endpoint
5. Add to swagger.yaml

### Phase 2: Extended Statistics (Effort: Medium)

1. Implement hourly distribution
2. Add treatment aggregations
3. Implement caching layer
4. Add real-time `/stats/current`

### Phase 3: MCP Integration (Effort: Small)

1. Create MCP resource definitions
2. Implement MCP server adapter
3. Document AI integration patterns

---

## Compatibility

### Existing Report Plugins

Report plugins can migrate to server-side stats:

| Plugin | Current | Migrated |
|--------|---------|----------|
| dailystats | Client-side calculation | Fetch `/stats/daily` |
| glucosedistribution | Client-side ranges | Fetch `/stats/summary` |
| hourlystats | Client-side hourly | Fetch `/stats/hourly` |
| percentile | Client-side percentiles | Fetch `/stats/hourly` |

### nightscout-reporter

Replace client-side aggregations:
```dart
// Before
final entries = await api.getEntries(from, to);
final stats = calculateStats(entries);  // Heavy computation

// After
final stats = await api.getStats(from, to);  // Pre-computed
```

### Third-Party Tools

| Tool | Benefit |
|------|---------|
| Nightscout-reporter | 90% reduction in data transfer |
| Sugarmate | Direct stats access |
| Tidepool | Interop opportunity |
| AI Assistants | MCP-based health insights |

---

## Gap Analysis

### Gaps Addressed

| Gap ID | Description | Resolution |
|--------|-------------|------------|
| GAP-STATS-001 | No aggregate endpoints | `/stats/*` endpoints |
| GAP-STATS-002 | Client-side computation burden | Server-side aggregation |
| GAP-STATS-003 | No MCP integration | MCP resource provider |

### New Requirements

| Req ID | Description |
|--------|-------------|
| REQ-STATS-001 | Daily aggregation endpoint |
| REQ-STATS-002 | Period summary endpoint |
| REQ-STATS-003 | Hourly distribution endpoint |
| REQ-STATS-004 | Treatment aggregation endpoint |
| REQ-STATS-005 | MCP resource provider |

---

## Security Considerations

1. **Authentication**: All stats endpoints require authentication
2. **Rate Limiting**: Apply standard API rate limits
3. **Data Scope**: Stats only for authenticated user's data
4. **Caching**: Cache invalidation on permission changes
5. **Audit**: Log stats access for compliance

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Report load time | 50% reduction |
| API data transfer | 80% reduction for reports |
| Client CPU usage | 70% reduction |
| MCP response time | < 500ms for 30-day stats |

---

## References

- [cgm-remote-monitor lib/report_plugins/](../../externals/cgm-remote-monitor-official/lib/report_plugins/)
- [nightscout-reporter](../../externals/nightscout-reporter/)
- [PR#8366 - 2025 Reports](https://github.com/nightscout/cgm-remote-monitor/pull/8366)
- [Model Context Protocol Spec](https://modelcontextprotocol.io/)
- [ADA Time-in-Range Recommendations](https://diabetesjournals.org/care/article/42/8/1593/36211/)
- [Nathan et al. 2008 - A1C Formula](https://pubmed.ncbi.nlm.nih.gov/18540046/)
