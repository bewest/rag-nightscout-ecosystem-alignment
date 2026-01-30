# Selective Repo Loading Proposal

> **Created**: 2026-01-30  
> **Purpose**: Reduce token usage by loading only task-relevant repos  
> **Status**: Proposal  
> **Companion**: [REFCAT Caching Proposal](refcat-caching-proposal.md)

---

## Executive Summary

The workspace contains **22 external repositories** but most tasks only need 2-4 repos. By implementing selective loading based on task keywords, we can reduce token usage by an estimated **40-60%**.

### Current Problem

| Metric | Value | Issue |
|--------|-------|-------|
| External repos | 22 | All loaded each cycle |
| Tokens/cycle | 3.4M | Heavy exploration |
| Top 8 repos | 80% of refs | 14 repos rarely used |
| Cost/cycle | $10.27 | Could be $4-6 |

### Proposed Solution

Implement **task-aware repo selection** that:
1. Parses task description for keywords
2. Maps keywords to relevant repos
3. Loads only matched repos
4. Falls back to core set for unknown tasks

### Expected Benefits

| Benefit | Estimate |
|---------|----------|
| Token reduction | 40-60% |
| Cost savings | $4-6/cycle |
| Faster exploration | 50% fewer files |
| Combined with REFCAT | 60-80% total reduction |

---

## Current State Analysis

### Repository Reference Frequency

From iterate-effectiveness-report.md:

| Tier | Repository | References | % of Total |
|------|------------|------------|------------|
| 1 | LoopWorkspace | 60 | 25% |
| 1 | AndroidAPS | 45 | 19% |
| 1 | DiaBLE | 40 | 17% |
| 2 | cgm-remote-monitor | 28 | 12% |
| 2 | Trio | 20 | 8% |
| 2 | oref0 | 20 | 8% |
| 3 | tconnectsync | 12 | 5% |
| 3 | xdrip-js | 11 | 5% |
| 4 | Others (14 repos) | <10 each | <1% each |

**Finding**: Top 8 repos account for **99%** of references.

### Repository Categories

| Category | Repos | Use Cases |
|----------|-------|-----------|
| **Algorithm** | LoopWorkspace, AndroidAPS, Trio, oref0 | Algorithm conformance, prediction |
| **CGM** | DiaBLE, xDrip, xdripswift, xdrip-js | CGM protocols, BLE |
| **API** | cgm-remote-monitor, nocturne | Nightscout API, collections |
| **Connectors** | nightscout-connect, share2nightscout-bridge, tconnectsync | Data bridges |
| **Caregivers** | LoopFollow, LoopCaregiver, nightguard | Remote monitoring |
| **Utilities** | nightscout-reporter, nightscout-roles-gateway | Reporting, auth |

---

## Task→Repo Mapping

### Keyword-Based Selection

| Task Keywords | Repos to Load |
|---------------|---------------|
| `algorithm`, `oref`, `prediction`, `dosing` | LoopWorkspace, AndroidAPS, Trio, oref0 |
| `cgm`, `libre`, `dexcom`, `ble`, `sensor` | DiaBLE, xDrip, xdripswift, xdrip-js |
| `api`, `nightscout`, `entries`, `treatments` | cgm-remote-monitor, nocturne |
| `connector`, `bridge`, `sync` | nightscout-connect, tconnectsync |
| `loop`, `ios`, `swift` | LoopWorkspace, Trio, LoopFollow, LoopCaregiver |
| `aaps`, `android`, `kotlin` | AndroidAPS |
| `tandem`, `tconnect` | tconnectsync |
| `profile`, `override`, `target` | LoopWorkspace, AndroidAPS, Trio, oref0 |

### Core Set (Always Loaded)

These repos are referenced across most task types:

```
cgm-remote-monitor    # Central API reference
oref0                 # Algorithm baseline
```

### Default Set (Unknown Tasks)

For tasks without clear keyword matches:

```
cgm-remote-monitor
LoopWorkspace
AndroidAPS
oref0
```

---

## Implementation Architecture

### Configuration File

```yaml
# .sdqctl/repo-selection.yaml

core_repos:
  - cgm-remote-monitor
  - oref0

default_repos:
  - cgm-remote-monitor
  - LoopWorkspace
  - AndroidAPS
  - oref0

task_mappings:
  algorithm:
    keywords: [algorithm, oref, prediction, dosing, bolus, basal, smb]
    repos: [LoopWorkspace, AndroidAPS, Trio, oref0]
  
  cgm:
    keywords: [cgm, libre, dexcom, ble, sensor, glucose, sgv]
    repos: [DiaBLE, xDrip, xdripswift, xdrip-js]
  
  api:
    keywords: [api, nightscout, entries, treatments, devicestatus]
    repos: [cgm-remote-monitor, nocturne]
  
  connector:
    keywords: [connector, bridge, sync, upload]
    repos: [nightscout-connect, tconnectsync, share2nightscout-bridge]
  
  ios:
    keywords: [loop, ios, swift, apple]
    repos: [LoopWorkspace, Trio, LoopFollow, LoopCaregiver]
  
  android:
    keywords: [aaps, android, kotlin]
    repos: [AndroidAPS, xDrip]
```

### Selection Algorithm

```python
def select_repos(task_description: str, config: dict) -> list[str]:
    """Select repos based on task keywords."""
    
    # Start with core repos
    selected = set(config['core_repos'])
    
    # Check each task mapping
    task_lower = task_description.lower()
    matched = False
    
    for category, mapping in config['task_mappings'].items():
        for keyword in mapping['keywords']:
            if keyword in task_lower:
                selected.update(mapping['repos'])
                matched = True
    
    # Fall back to default if no matches
    if not matched:
        selected.update(config['default_repos'])
    
    return sorted(selected)
```

### Integration Points

| Component | Change |
|-----------|--------|
| `make bootstrap` | Accept `--repos` flag |
| `workspace.lock.json` | Track which repos loaded |
| `.sdqctl/` | Store selection config |
| Workflow preamble | Add `REPOS:` directive |

---

## Workflow Integration

### New Directive

```yaml
# In .conv workflow files
REPOS: algorithm, api   # Load algorithm + api repo sets
REPOS: auto             # Auto-detect from task description
REPOS: all              # Load all repos (current behavior)
```

### Example Usage

```yaml
# workflows/algorithm-conformance.conv
REPOS: algorithm

SYSTEM:
  You are analyzing algorithm implementations...
```

```yaml
# workflows/cgm-analysis.conv  
REPOS: cgm

SYSTEM:
  You are analyzing CGM protocols...
```

---

## Token Savings Estimate

### Per-Task Analysis

| Task Type | Current Repos | Selective Repos | Reduction |
|-----------|---------------|-----------------|-----------|
| Algorithm conformance | 22 | 4 | 82% |
| CGM protocol analysis | 22 | 4 | 82% |
| API documentation | 22 | 2 | 91% |
| Connector analysis | 22 | 3 | 86% |
| General/unknown | 22 | 4 | 82% |

### Overall Estimate

| Scenario | Token Reduction | Cost Savings |
|----------|-----------------|--------------|
| Conservative | 40% | $4.10/cycle |
| Optimistic | 60% | $6.16/cycle |

### Combined with REFCAT

| Optimization | Individual | Combined |
|--------------|------------|----------|
| REFCAT caching | 20-40% | - |
| Selective loading | 40-60% | - |
| **Both** | - | **60-80%** |

**Potential**: Reduce $10.27/cycle → $2-4/cycle

---

## Implementation Phases

### Phase 1: Configuration (1 hour)

1. Create `.sdqctl/repo-selection.yaml`
2. Define task→repo mappings
3. Document configuration format

### Phase 2: Selection Logic (2 hours)

1. Implement `select_repos()` function
2. Add keyword matching
3. Handle edge cases

### Phase 3: Bootstrap Integration (2 hours)

1. Modify `make bootstrap` for selective loading
2. Update `workspace.lock.json` schema
3. Add `--repos` flag

### Phase 4: Workflow Directive (2 hours)

1. Add `REPOS:` directive parsing
2. Integrate with sdqctl
3. Add auto-detection mode

### Phase 5: Testing & Documentation (1 hour)

1. Test all task types
2. Verify token reduction
3. Update documentation

**Total Effort**: ~8 hours

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Missing repo for task | Medium | High | Fall back to default set |
| Keyword ambiguity | Low | Medium | Multiple keyword matching |
| Config complexity | Low | Low | Clear YAML format |
| Breaking existing workflows | Medium | Medium | `REPOS: all` default |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Token reduction | >40% | Compare iterate runs |
| Task coverage | 100% | All task types work |
| False negatives | <5% | Missing repo complaints |
| Load time | <30s | Selective bootstrap |

---

## Files to Create

| File | Purpose |
|------|---------|
| `.sdqctl/repo-selection.yaml` | Configuration |
| `tools/select_repos.py` | Selection logic |
| `Makefile` | Updated bootstrap target |

---

## Cross-References

- [REFCAT Caching Proposal](refcat-caching-proposal.md) - Companion optimization
- [iterate-effectiveness-report.md](iterate-effectiveness-report.md) - Token analysis
- [tooling.md](backlogs/tooling.md) - Backlog item #10
