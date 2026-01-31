# LSP Environment Suitability Check

> **Purpose**: Assess current environment for LSP-based code verification  
> **Date**: 2026-01-31  
> **Source**: LIVE-BACKLOG.md user request

## Executive Summary

| Tool | Status | Readiness |
|------|--------|-----------|
| **Swift/sourcekit-lsp** | ✅ Installed (swiftly 6.2.3) | ⚠️ PATH not sourced, Xcode projects not SPM |
| **Node.js/tsserver** | ✅ Ready | ✅ Fully operational |
| **Java** | ✅ OpenJDK 21 | ⚠️ kotlin-language-server not installed |
| **Python/pyright** | ⚠️ Python ready | ❌ pyright not installed |
| **Tree-sitter** | ❌ Not installed | ✅ cargo available for install |

**Overall Assessment**: **JS/TS verification ready now**. Swift LSP installed but iOS projects require Xcode for full resolution. Tree-sitter is a viable alternative for syntax-level queries.

---

## Detailed Findings

### 1. Swift Toolchain (sourcekit-lsp)

**Status**: ✅ Installed via swiftly

```
Swift version 6.2.3 (swift-6.2.3-RELEASE)
Target: x86_64-unknown-linux-gnu
sourcekit-lsp: AVAILABLE
```

**Location**: `~/.local/share/swiftly/`

**Activation Required**:
```bash
source ~/.local/share/swiftly/env.sh
```

**Limitations**:
- iOS projects (Trio, Loop) use Xcode `.xcodeproj` not Swift Package Manager
- sourcekit-lsp works best with SPM `Package.swift` projects
- No iOS SDK frameworks on Linux (UIKit, HealthKit not available)
- `swift sdk list` shows only `darwin` SDK

**Recommendation**: 
- Use sourcekit-lsp for **syntax queries** and **symbol resolution** in pure Swift code
- Full iOS framework resolution requires macOS + Xcode
- Tree-sitter is better for cross-platform Swift parsing

---

### 2. JavaScript/TypeScript (tsserver)

**Status**: ✅ Fully Operational

```
Node.js: v20.20.0
npm: 10.8.2
tsserver: /home/bewest/n/bin/tsserver
```

**Targets**:
- `externals/cgm-remote-monitor/lib/` (~500 JS files)
- `externals/oref0/lib/` (~50 JS files)
- `externals/Trio/trio-oref/lib/` (~20 JS files)

**Ready for**:
- Symbol lookup (`textDocument/definition`)
- Reference finding (`textDocument/references`)
- Hover information (`textDocument/hover`)
- Diagnostics

**Next Step**: Create `tools/lsp_query.py` wrapper for tsserver protocol

---

### 3. Kotlin/Java

**Status**: ⚠️ Partial

```
Java: OpenJDK 21.0.9
kotlin-language-server: NOT INSTALLED
```

**Installation**:
```bash
# Option 1: Manual download
curl -LO https://github.com/fwcd/kotlin-language-server/releases/latest/download/server.zip
unzip server.zip -d ~/kotlin-language-server

# Option 2: Via SDKMAN
sdk install kotlinc
```

**Challenge**: AAPS/xDrip require Gradle sync before LSP works (~2-5 min first run)

---

### 4. Python

**Status**: ⚠️ Python ready, LSP not installed

```
Python: 3.12.3
pyright: NOT INSTALLED
```

**Installation**:
```bash
pip install pyright
# or
npm install -g pyright
```

**Targets**: `tools/*.py` (~40 files)

---

### 5. Tree-sitter

**Status**: ❌ Not installed, but can be

**Installation Options**:
```bash
# Via cargo (available)
cargo install tree-sitter-cli

# Via npm
npm install -g tree-sitter-cli
```

**Required Language Parsers**:
| Parser | Target Projects |
|--------|-----------------|
| tree-sitter-swift | Trio, Loop, xDrip4iOS, DiaBLE |
| tree-sitter-javascript | cgm-remote-monitor, oref0, trio-oref |
| tree-sitter-kotlin | AAPS |
| tree-sitter-java | xDrip |

**Advantages over LSP**:
- No project build required
- Works on any platform
- Fast parsing (~ms per file)
- Query language for pattern matching

**Disadvantages**:
- No semantic analysis (type resolution, imports)
- Query syntax learning curve

---

## LSP vs Tree-sitter Decision Matrix

| Use Case | LSP | Tree-sitter | Recommendation |
|----------|-----|-------------|----------------|
| Symbol definition lookup | ✅ | ❌ | LSP |
| Reference finding | ✅ | ⚠️ (text match) | LSP |
| Function signature extraction | ✅ | ✅ | Either |
| Struct/class field listing | ✅ | ✅ | Either |
| Cross-file type resolution | ✅ | ❌ | LSP |
| iOS framework symbols | ❌ (Linux) | ❌ | macOS only |
| Fast syntax queries | ⚠️ (heavy) | ✅ | Tree-sitter |
| No build required | ❌ | ✅ | Tree-sitter |

**Recommendation**: Use **hybrid approach**:
1. Tree-sitter for syntax-level queries (function names, struct fields)
2. tsserver LSP for JS/TS semantic queries (cgm-remote-monitor)
3. Defer Swift/Kotlin LSP to CI on appropriate platforms

---

## Quick Start Commands

### Activate Swift
```bash
source ~/.local/share/swiftly/env.sh
swift --version
sourcekit-lsp --help
```

### Install Tree-sitter
```bash
cargo install tree-sitter-cli
tree-sitter init-config

# Install Swift parser
git clone https://github.com/alex-pinkus/tree-sitter-swift
cd tree-sitter-swift && tree-sitter generate
```

### Install Python LSP
```bash
pip install pyright
pyright --version
```

### Test tsserver
```bash
cd externals/cgm-remote-monitor
echo '{"seq":1,"type":"request","command":"open","arguments":{"file":"lib/server/app.js"}}' | npx tsserver
```

---

## Backlog Items Generated

### Immediate (Ready Now)

| Item | Priority | Effort | Notes |
|------|----------|--------|-------|
| Create `tools/lsp_query.py` for tsserver | P2 | Medium | JS/TS ready now |
| Add `source swiftly/env.sh` to shell init | P3 | Low | Enable swift in PATH |
| Install pyright for tools/ verification | P3 | Low | `pip install pyright` |

### Short-term (Requires Install)

| Item | Priority | Effort | Notes |
|------|----------|--------|-------|
| Install tree-sitter-cli | P2 | Low | `cargo install tree-sitter-cli` |
| Create tree-sitter query library | P2 | Medium | Patterns for function/struct extraction |
| Install kotlin-language-server | P3 | Medium | For AAPS verification |

### Deferred (Platform Limitations)

| Item | Priority | Notes |
|------|----------|-------|
| Swift LSP for iOS projects | P4 | Requires macOS + Xcode |
| Full AAPS Gradle sync | P4 | Requires ~5min first run |

---

## Environment Setup Script

```bash
#!/bin/bash
# setup-lsp-env.sh

# Swift (already installed via swiftly)
source ~/.local/share/swiftly/env.sh

# Tree-sitter
if ! command -v tree-sitter &> /dev/null; then
    cargo install tree-sitter-cli
fi

# Python LSP
pip install pyright 2>/dev/null || pip install --user pyright

# Verify
echo "=== Environment Check ==="
swift --version 2>/dev/null && echo "✅ Swift ready" || echo "❌ Swift not in PATH"
node --version && echo "✅ Node.js ready"
tree-sitter --version 2>/dev/null && echo "✅ Tree-sitter ready" || echo "⚠️ Tree-sitter not installed"
pyright --version 2>/dev/null && echo "✅ Pyright ready" || echo "⚠️ Pyright not installed"
```

---

## References

- [lsp-verification-setup-requirements.md](lsp-verification-setup-requirements.md) - Full LSP roadmap
- [trio-openaps-bridge-analysis.md](trio-openaps-bridge-analysis.md) - JS bundle locations
- swiftly docs: https://github.com/swiftlang/swiftly
- tree-sitter: https://tree-sitter.github.io/tree-sitter/
