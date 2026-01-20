# Analysis Patterns for Nightscout Ecosystem

## CGM Protocol Analysis

When analyzing a CGM protocol (Dexcom G6/G7, Libre 2/3, etc.):

### Step 1: Identify Relevant Source Files

Search across external repos for protocol-specific code:

```bash
# Find Swift implementations
find externals -name "*.swift" | xargs grep -l "G7\|DexcomG7" 2>/dev/null

# Find Java/Kotlin implementations  
find externals -name "*.java" -o -name "*.kt" | xargs grep -l "G7\|DexcomG7" 2>/dev/null
```

### Step 2: Check Existing Documentation

```bash
# Search for existing analysis
python tools/query_workspace.py --search "G7" --json

# Check if faceted analysis exists
python tools/query_workspace.py --search "GAP-G7" --json
```

### Step 3: Analyze Source Code

Key files to examine for Dexcom protocols:
- `externals/DiaBLE/DiaBLE/DexcomG7.swift` - BLE traces, opcode definitions
- `externals/xDrip/libkeks/src/main/java/jamorham/keks/` - J-PAKE implementation
- `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Dexcom/` - iOS BLE handling

### Step 4: Update All 5 Facets

1. **Terminology Matrix** (`mapping/cross-project/terminology-matrix.md`)
   - Add any new terms discovered (opcodes, message types, etc.)
   - Map equivalent concepts across projects

2. **Gaps** (`traceability/gaps.md`)
   - Add `GAP-G7-NNN` entries for missing features
   - Document what's needed vs what exists

3. **Requirements** (`traceability/requirements.md`)
   - Extract formal `REQ-NNN` requirements
   - Include rationale and verification criteria

4. **Deep Dive** (`docs/10-domain/{protocol}-deep-dive.md`)
   - Technical specification with code references
   - Implementation comparison across projects

5. **Progress** (`progress.md`)
   - Add dated entry with deliverables table
   - List key findings and gaps identified

### Step 5: Validate

```bash
make verify
```

---

## Nightscout API Analysis

When analyzing Nightscout API collections:

### Required Context

- `specs/openapi/aid-entries-2025.yaml` - Entries schema
- `specs/openapi/aid-treatments-2025.yaml` - Treatments schema
- `specs/openapi/aid-devicestatus-2025.yaml` - DeviceStatus schema
- `mapping/nightscout/README.md` - Collection overview

### Cross-Reference Checklist

- [ ] Field names match terminology matrix
- [ ] eventTypes documented in treatments spec
- [ ] Controller support matrix (`x-aid-controllers`) updated
- [ ] Gap annotations (`x-aid-gap`) present where needed

### Source Code Locations

| Collection | Primary Source |
|------------|----------------|
| entries | `externals/cgm-remote-monitor/lib/api3/generic/entries/` |
| treatments | `externals/cgm-remote-monitor/lib/api3/generic/treatments/` |
| devicestatus | `externals/cgm-remote-monitor/lib/api3/generic/devicestatus/` |

---

## AID Algorithm Comparison

When comparing Loop vs oref0 vs Trio algorithms:

### Key Differences to Document

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| Prediction | Single combined curve | 4 separate curves (IOB, COB, UAM, ZT) |
| Carb Absorption | Dynamic adaptation | Linear decay + UAM backup |
| Sensitivity | Retrospective Correction | Autosens / Dynamic ISF |
| Micro-dosing | No SMB | SMB supported |

### Source Code Locations

| System | Algorithm Core |
|--------|----------------|
| Loop | `externals/LoopWorkspace/LoopAlgorithm/` |
| AAPS | `externals/AndroidAPS/app/src/main/kotlin/app/aaps/core/oref/` |
| Trio | `externals/Trio/FreeAPS/Sources/APS/OpenAPS/` |
| oref0 | `externals/oref0/lib/` |

---

## Treatment Sync Analysis

When analyzing how treatments sync between systems:

### Sync Flow Patterns

```
xDrip+ → AAPS → Nightscout → Loop (read-only)
                     ↓
                   Trio
```

### Identity Fields to Track

| System | Sync Identity Field |
|--------|---------------------|
| Nightscout | `identifier`, `_id` |
| Loop | `syncIdentifier` |
| AAPS | `interfaceIDs.nightscoutId` |
| Trio | `syncIdentifier` |
| xDrip+ | `uuid` |

### Deduplication Behavior

Document how each system handles:
- Duplicate detection
- Update vs insert decisions
- Conflict resolution

---

## Output Format Conventions

### Gap Entry Format

```markdown
### GAP-XXX-NNN: Brief Title

**Description**: What is missing or inconsistent.

**Affected Systems**: List of systems impacted.

**Impact**: Why this matters for interoperability.

**Remediation**: Suggested fix or workaround.
```

### Requirement Entry Format

```markdown
### REQ-NNN: Brief Title

**Statement**: The system MUST/SHOULD/MAY...

**Rationale**: Why this matters.

**Scenarios**: Link to test scenarios.

**Verification**: How to test this.
```

### Progress Entry Format

```markdown
### Component Name (YYYY-MM-DD)

Brief description of what was analyzed.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Doc Name | `path/to/file.md` | Summary |

**Key Findings**:
- Finding 1
- Finding 2

**Gaps Identified**: GAP-XXX-001, GAP-XXX-002

**Source Files Analyzed**:
- `externals/repo/path/file.ext`
```
