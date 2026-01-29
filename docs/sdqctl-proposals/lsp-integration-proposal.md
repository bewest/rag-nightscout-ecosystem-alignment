# LSP Integration Proposal

> **Purpose**: Enable semantic code analysis for cross-project verification  
> **Priority**: P2  
> **Effort**: High  
> **Last Updated**: 2026-01-29

## Executive Summary

This proposal defines how to integrate Language Server Protocol (LSP) tools into the alignment workspace to enable semantic code verification beyond regex-based file existence checks.

### Current State

| Tool | Capability | Limitation |
|------|-----------|------------|
| `verify_refs.py` | File existence validation | Cannot verify line numbers, symbols |
| Regex patterns | Text matching | No semantic understanding |
| Manual inspection | Full understanding | Does not scale |

### Proposed State

| Tool | Capability | Languages |
|------|-----------|-----------|
| `lsp_query.py` | Go-to-definition, find-references | Swift, Kotlin, JS/TS |
| Enhanced `verify_refs.py` | Line number + symbol validation | All via LSP |
| Diagnostic collection | Type errors, unused imports | Per-language |

---

## Problem Statement

### Current Gaps

1. **Line number drift**: References like `crm:lib/api.js#L45` become stale after refactoring
2. **Symbol verification**: Cannot confirm `BgReading.calculated_value` actually exists
3. **Placeholder paths**: `aaps:plugins/.../smsCommunicator/` with `...` unresolvable
4. **Type understanding**: Cannot track data flow through transformations

### Validation Report (2026-01-29)

| Metric | Count | Issue |
|--------|-------|-------|
| Total refs | 386 | - |
| Valid | 355 (92%) | File exists |
| Broken | 31 (8%) | Unknown alias, missing path |
| **Line-verified** | **0** | Not implemented |
| **Symbol-verified** | **0** | Not implemented |

---

## Language Coverage Matrix

### Repository Analysis

| Repository | Primary Language | Files | LSP Server | Platform |
|------------|-----------------|-------|------------|----------|
| **LoopWorkspace** | Swift | ~3,000 | sourcekit-lsp | macOS only |
| **Trio** | Swift | ~3,000 | sourcekit-lsp | macOS only |
| **xdripswift** | Swift | ~1,500 | sourcekit-lsp | macOS only |
| **DiaBLE** | Swift | ~1,000 | sourcekit-lsp | macOS only |
| **AndroidAPS** | Kotlin | ~3,000 | kotlin-language-server | Any |
| **xDrip** | Java | ~500 | Eclipse JDT LS | Any |
| **cgm-remote-monitor** | JavaScript | ~500 | tsserver / typescript-language-server | Any |
| **oref0** | JavaScript | ~50 | tsserver | Any |
| **openaps** | Python | ~50 | pylsp / pyright | Any |

### Platform Constraints

| Language | LSP Server | Linux | macOS | Notes |
|----------|------------|-------|-------|-------|
| Swift | sourcekit-lsp | ⚠️ Limited | ✅ | No iOS frameworks on Linux |
| Kotlin | kotlin-language-server | ✅ | ✅ | Needs Gradle wrapper |
| Java | Eclipse JDT LS | ✅ | ✅ | Mature, stable |
| JavaScript | tsserver | ✅ | ✅ | Part of TypeScript |
| TypeScript | typescript-language-server | ✅ | ✅ | Wrapper around tsserver |
| Python | pylsp / pyright | ✅ | ✅ | pyright is faster |

**Critical Constraint**: Swift LSP requires macOS for full iOS project support. Linux Swift has no UIKit, CoreData, HealthKit - cannot index Loop/Trio properly.

---

## Scope Options

### Option A: Minimal (Line Validation Only)

**Goal**: Validate `#L45` line anchors exist  
**Approach**: No LSP - just count lines with `wc -l` or read file  
**Effort**: Low (1-2 hours)  
**Value**: Catches line drift, no semantic understanding

```python
# Pseudo-code for line validation
def validate_line_anchor(file_path, line_num):
    with open(file_path) as f:
        lines = f.readlines()
    return line_num <= len(lines)
```

### Option B: Moderate (Symbol Existence)

**Goal**: Verify symbols like `BgReading.calculated_value` exist  
**Approach**: LSP textDocument/definition queries  
**Effort**: Medium (1-2 days)  
**Value**: Catches renamed/deleted symbols

```python
# Pseudo-code for symbol verification
def verify_symbol(file_path, line, column, symbol_name):
    result = lsp.definition(file_path, line, column)
    return result is not None and symbol_name in result.text
```

### Option C: Full (Cross-Reference Analysis)

**Goal**: Find all usages, trace data flow  
**Approach**: LSP textDocument/references, workspace/symbol  
**Effort**: High (1 week+)  
**Value**: Full semantic understanding, refactoring support

---

## Recommended Approach: Phased Implementation

### Phase 1: Line Validation (No LSP)

**Deliverables**:
- Enhance `verify_refs.py` to validate `#L<N>` anchors
- Validate `#L<start>-L<end>` ranges
- Report line count mismatches

**Implementation**:
```python
def validate_ref(ref, aliases):
    # ... existing file validation ...
    
    if ref.get("anchor"):
        anchor = ref["anchor"]
        if match := re.match(r'L(\d+)(?:-L(\d+))?', anchor):
            start_line = int(match.group(1))
            end_line = int(match.group(2)) if match.group(2) else start_line
            
            with open(file_path) as f:
                total_lines = sum(1 for _ in f)
            
            if end_line > total_lines:
                return {"status": "line_out_of_range", 
                        "message": f"Line {end_line} > {total_lines}"}
```

**Effort**: 2 hours  
**Platform**: Any (no LSP needed)

### Phase 2: JavaScript/TypeScript LSP

**Deliverables**:
- `tools/lsp_query.py` wrapper for tsserver
- Symbol existence validation for cgm-remote-monitor, oref0
- Integration with verify_refs.py

**Why JS/TS first**:
- Works on Linux (current environment)
- cgm-remote-monitor is high-priority audit target
- tsserver is mature and well-documented

**Implementation**:
```python
# tools/lsp_query.py
import subprocess
import json

class TSServerClient:
    def __init__(self, project_root):
        self.proc = subprocess.Popen(
            ['npx', 'typescript-language-server', '--stdio'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=project_root
        )
    
    def definition(self, file_path, line, column):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": f"file://{file_path}"},
                "position": {"line": line - 1, "character": column}
            }
        }
        # ... send request, parse response ...
```

**Effort**: 1 day  
**Platform**: Any

### Phase 3: Kotlin/Java LSP

**Deliverables**:
- kotlin-language-server integration for AAPS
- Eclipse JDT LS for xDrip (Java)
- Symbol validation for Android projects

**Why second**:
- Linux compatible
- AAPS is complex, has many cross-references
- Java/Kotlin LSP servers are mature

**Effort**: 1-2 days  
**Platform**: Any (needs Gradle for Kotlin)

### Phase 4: Swift LSP (macOS only)

**Deliverables**:
- sourcekit-lsp integration for Loop, Trio, xDrip4iOS
- GitHub Actions workflow for macOS LSP validation
- Fallback to line-only validation on Linux

**Why last**:
- Requires macOS
- Most complex setup (Xcode toolchain)
- CI cost (macOS runners 10x expensive)

**Effort**: 2-3 days  
**Platform**: macOS only

---

## Interface Design

### CLI Interface

```bash
# Line validation only (Phase 1)
python tools/verify_refs.py --validate-lines

# LSP-based symbol check (Phase 2+)
python tools/lsp_query.py definition crm:lib/api3/generic/entries.js:45:10
python tools/lsp_query.py references aaps:core/interfaces/.../Pump.kt:23:5

# Integrated validation
python tools/verify_refs.py --lsp  # Uses LSP where available
```

### Python API

```python
from tools.lsp_query import LSPClient

# Auto-detect language server
client = LSPClient.for_repo("cgm-remote-monitor")

# Query
result = client.definition("lib/api3/generic/entries.js", line=45, column=10)
print(result.target_file, result.target_line)

# Find references
refs = client.references("lib/api3/generic/entries.js", line=45, column=10)
for ref in refs:
    print(f"{ref.file}:{ref.line}")
```

### sdqctl Plugin

```yaml
# .sdqctl/directives.yaml
VERIFY:
  lsp-symbols:
    handler: python tools/verify_refs.py --lsp --json
    description: "Verify references with LSP symbol resolution"
    timeout: 300  # LSP startup is slow
```

---

## Dependencies

### Required Packages

| Package | Purpose | Install |
|---------|---------|---------|
| typescript | tsserver for JS/TS | `npm install -g typescript` |
| typescript-language-server | LSP wrapper | `npm install -g typescript-language-server` |
| kotlin-language-server | Kotlin LSP | Download from GitHub releases |
| eclipse.jdt.ls | Java LSP | Download from Eclipse |
| pyright | Python LSP | `pip install pyright` |
| sourcekit-lsp | Swift LSP | Bundled with Xcode (macOS) |

### Workspace Configuration

Each external repo needs minimal LSP configuration:

```json
// externals/cgm-remote-monitor/jsconfig.json (if missing)
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "checkJs": true
  },
  "include": ["lib/**/*.js", "tests/**/*.js"]
}
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LSP startup latency (5-30s) | High | Medium | Cache server sessions |
| Swift not available on Linux | Certain | High | CI on macOS, fallback locally |
| Kotlin needs Gradle sync | High | Medium | Pre-sync during bootstrap |
| Memory usage (multiple servers) | Medium | Medium | On-demand server start |
| Version drift in LSP servers | Low | Low | Pin versions in workspace |

---

## Success Metrics

| Metric | Current | Phase 1 | Phase 4 |
|--------|---------|---------|---------|
| File existence validation | 92% valid | 92% | 92% |
| Line anchor validation | 0% | 95%+ | 95%+ |
| Symbol verification | 0% | 0% | 80%+ |
| Placeholder resolution | 0% | 50%* | 90%+ |

*Phase 1 can flag `...` placeholders but not resolve them

---

## Timeline

| Phase | Scope | Effort | Prerequisite |
|-------|-------|--------|--------------|
| **Phase 1** | Line validation | 2 hours | None |
| **Phase 2** | JS/TS LSP | 1 day | Phase 1 |
| **Phase 3** | Kotlin/Java LSP | 1-2 days | Phase 2 |
| **Phase 4** | Swift LSP | 2-3 days | macOS CI setup |

**Total**: ~1 week for full implementation

---

## Decision Needed

- [ ] Approve phased approach?
- [ ] Start with Phase 1 (line validation) immediately?
- [ ] Defer Phase 4 (Swift) until macOS CI is justified?

---

## References

- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server)
- [kotlin-language-server](https://github.com/fwcd/kotlin-language-server)
- [sourcekit-lsp](https://github.com/apple/sourcekit-lsp)
- [Cross-Project Testing Plan](cross-project-testing-plan.md) - Platform constraints analysis
