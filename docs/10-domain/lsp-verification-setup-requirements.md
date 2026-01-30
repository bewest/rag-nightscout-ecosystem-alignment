# LSP Verification Setup Requirements

> **Purpose**: Concrete setup requirements for LSP-based claim verification  
> **Parent**: [lsp-integration-proposal.md](../lsp-integration-proposal.md)  
> **Last Updated**: 2026-01-30

## Executive Summary

This document provides actionable setup requirements for each language server needed for claim verification. It extends the LSP integration proposal with concrete installation steps, configuration files, and feasibility assessments.

---

## Quick Reference

| Language | LSP Server | Linux | macOS | Priority | Effort |
|----------|------------|-------|-------|----------|--------|
| JavaScript/TypeScript | tsserver | ✅ Ready | ✅ Ready | P1 | Low |
| Kotlin | kotlin-language-server | ✅ Feasible | ✅ Feasible | P2 | Medium |
| Java | Eclipse JDT LS | ✅ Feasible | ✅ Feasible | P2 | Medium |
| Python | pyright | ✅ Ready | ✅ Ready | P3 | Low |
| Swift | sourcekit-lsp | ⚠️ Limited | ✅ Full | P4 | High |

---

## JavaScript/TypeScript LSP (Priority 1)

### Repositories Covered
- cgm-remote-monitor (~500 JS files)
- oref0 (~50 JS files)
- nightscout-connect (~100 JS/TS files)

### Installation

```bash
# Install TypeScript globally (includes tsserver)
npm install -g typescript

# Install LSP wrapper (optional, for standardized LSP protocol)
npm install -g typescript-language-server

# Verify installation
npx tsc --version
# Expected: Version 5.x.x
```

### Workspace Configuration

Each JS project needs a `jsconfig.json` or `tsconfig.json`:

```json
// externals/cgm-remote-monitor/jsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "moduleResolution": "node",
    "checkJs": true,
    "allowJs": true,
    "noEmit": true
  },
  "include": ["lib/**/*.js", "tests/**/*.js"],
  "exclude": ["node_modules"]
}
```

### LSP Query Example

```python
import subprocess
import json

def query_definition(file_path: str, line: int, column: int) -> dict:
    """Query tsserver for definition location."""
    # Using typescript-language-server in stdio mode
    cmd = [
        "typescript-language-server", "--stdio"
    ]
    
    # Send initialize, then textDocument/definition request
    # Returns: {"uri": "file://...", "range": {"start": {"line": N}}}
    pass  # Implementation requires LSP client library
```

### Feasibility: ✅ HIGH

- tsserver is mature and widely used
- No platform limitations
- Fast startup (~2-3 seconds)
- Memory: ~100-200MB per project

---

## Kotlin LSP (Priority 2)

### Repositories Covered
- AndroidAPS (~3,000 Kotlin files)

### Prerequisites

```bash
# Java 11+ required
java --version
# Expected: openjdk 11.x.x or higher

# Gradle wrapper must be present in AndroidAPS
ls externals/AndroidAPS/gradlew
```

### Installation

```bash
# Download kotlin-language-server
# From: https://github.com/fwcd/kotlin-language-server/releases
wget https://github.com/fwcd/kotlin-language-server/releases/download/1.3.9/server.zip
unzip server.zip -d ~/.local/share/kotlin-language-server

# Add to PATH
export PATH="$HOME/.local/share/kotlin-language-server/bin:$PATH"

# Verify
kotlin-language-server --version
```

### Project Sync Required

```bash
# First-time Gradle sync (can take 5-10 minutes)
cd externals/AndroidAPS
./gradlew --no-daemon :app:dependencies

# This creates .gradle/ cache needed by LSP
```

### Feasibility: ⚠️ MEDIUM

- Requires JVM (adds ~500MB to environment)
- First Gradle sync is slow (5-10 min)
- Subsequent queries are fast (~1-2 seconds)
- Memory: ~500MB-1GB for AndroidAPS

### Challenges

1. **Gradle sync**: Must run before LSP works
2. **Memory**: Large heap needed for full project
3. **Build variants**: May need to specify debug vs release

---

## Java LSP (Priority 2)

### Repositories Covered
- xDrip (~500 Java files)
- AndroidAPS (mixed Kotlin/Java)

### Installation

```bash
# Download Eclipse JDT Language Server
# From: https://download.eclipse.org/jdtls/milestones/
wget https://download.eclipse.org/jdtls/milestones/1.29.0/jdt-language-server-1.29.0-202310261436.tar.gz
mkdir -p ~/.local/share/jdtls
tar xzf jdt-language-server-*.tar.gz -C ~/.local/share/jdtls

# Launcher script
cat > ~/.local/bin/jdtls << 'EOF'
#!/bin/bash
java \
  -Declipse.application=org.eclipse.jdt.ls.core.id1 \
  -Dosgi.bundles.defaultStartLevel=4 \
  -Declipse.product=org.eclipse.jdt.ls.core.product \
  -jar ~/.local/share/jdtls/plugins/org.eclipse.equinox.launcher_*.jar \
  -configuration ~/.local/share/jdtls/config_linux \
  -data ~/.cache/jdtls-workspace \
  "$@"
EOF
chmod +x ~/.local/bin/jdtls
```

### Feasibility: ✅ HIGH

- Very mature (Eclipse foundation)
- Good Android project support
- Memory: ~300-500MB

---

## Python LSP (Priority 3)

### Repositories Covered
- openaps (~50 Python files)
- tools/ in this workspace

### Installation

```bash
# Pyright (recommended - faster, more accurate)
pip install pyright

# Alternative: pylsp
pip install python-lsp-server

# Verify
pyright --version
```

### Feasibility: ✅ HIGH

- Trivial installation
- Fast startup
- Low memory (~50-100MB)

---

## Swift LSP (Priority 4)

### Repositories Covered
- LoopWorkspace (~3,000 Swift files)
- Trio (~3,000 Swift files)
- xdripswift (~1,500 Swift files)
- DiaBLE (~1,000 Swift files)

### Critical Limitation: Linux Support

**Swift on Linux cannot index iOS projects properly.**

| Framework | Linux | macOS |
|-----------|-------|-------|
| Foundation | ✅ | ✅ |
| UIKit | ❌ | ✅ |
| CoreData | ❌ | ✅ |
| HealthKit | ❌ | ✅ |
| SwiftUI | ❌ | ✅ |

Loop, Trio, xdripswift all depend on UIKit/HealthKit → **Cannot be indexed on Linux**.

### macOS Installation

```bash
# sourcekit-lsp is bundled with Xcode
xcode-select --install

# Verify
xcrun sourcekit-lsp --help

# Or from Swift toolchain
swift --version  # Should show 5.9+
```

### Linux Installation (Limited)

```bash
# Install Swift toolchain
wget https://download.swift.org/swift-5.9.2-release/ubuntu2204/swift-5.9.2-RELEASE/swift-5.9.2-RELEASE-ubuntu22.04.tar.gz
tar xzf swift-5.9.2-RELEASE-ubuntu22.04.tar.gz
export PATH="$PWD/swift-5.9.2-RELEASE-ubuntu22.04/usr/bin:$PATH"

# sourcekit-lsp is included
sourcekit-lsp --help
```

### Feasibility: ⚠️ LOW (Linux) / ✅ HIGH (macOS)

**Linux limitations**:
- Cannot resolve UIKit, HealthKit, CoreData imports
- Will report false "missing module" errors
- Partial indexing only (Foundation-based code)

**Recommendation**: Defer Swift LSP to macOS CI environment or contributor machines.

---

## Phased Implementation Roadmap

### Phase 1: JS/TS LSP (Immediate)

**Scope**: cgm-remote-monitor, oref0, nightscout-connect

**Prerequisites**:
```bash
npm install -g typescript typescript-language-server
```

**Effort**: 1 day
**Value**: Covers ~650 JS files across 3 critical repos

### Phase 2: Kotlin/Java LSP (After Phase 1)

**Scope**: AndroidAPS, xDrip

**Prerequisites**:
```bash
# Install JDK 11+
sudo apt install openjdk-11-jdk

# Download kotlin-language-server and jdtls (see above)

# Pre-sync Gradle
cd externals/AndroidAPS && ./gradlew dependencies
```

**Effort**: 2-3 days
**Value**: Covers ~3,500 Kotlin/Java files in AAPS/xDrip

### Phase 3: Python LSP (Parallel with Phase 2)

**Scope**: openaps, tools/

**Prerequisites**:
```bash
pip install pyright
```

**Effort**: 2 hours
**Value**: Enables verification of our own tooling

### Phase 4: Swift LSP (Deferred)

**Scope**: Loop, Trio, xdripswift, DiaBLE

**Prerequisites**:
- macOS CI runner OR
- macOS contributor machine OR
- Accept partial Linux indexing

**Effort**: 2-3 days (primarily CI setup)
**Value**: Covers ~8,500 Swift files but requires platform investment

---

## Memory and Resource Requirements

| Phase | Languages | Memory | Disk | Startup Time |
|-------|-----------|--------|------|--------------|
| Phase 1 | JS/TS | ~200MB | ~50MB | 2-3s |
| Phase 2 | Kotlin/Java | ~1.5GB | ~500MB | 10-30s |
| Phase 3 | Python | ~100MB | ~20MB | 1s |
| Phase 4 | Swift | ~2GB | ~5GB (Xcode) | 5-10s |

**Total (Phases 1-3)**: ~2GB RAM, ~600MB disk

---

## Integration with Existing Tools

### verify_refs.py Enhancement

```python
# Add to tools/verify_refs.py

LSP_SERVERS = {
    '.js': 'typescript-language-server',
    '.ts': 'typescript-language-server',
    '.kt': 'kotlin-language-server',
    '.java': 'jdtls',
    '.py': 'pyright',
    '.swift': 'sourcekit-lsp',
}

def verify_with_lsp(file_path: str, line: int, symbol: str) -> bool:
    """Verify symbol exists at line using LSP."""
    ext = Path(file_path).suffix
    server = LSP_SERVERS.get(ext)
    if not server:
        return None  # Unknown language
    
    # Query LSP for symbol at location
    # Return True if symbol exists, False if not
    pass
```

### Makefile Targets

```makefile
# Add to Makefile

lsp-setup-js:
	npm install -g typescript typescript-language-server

lsp-setup-kotlin:
	./scripts/install-kotlin-lsp.sh
	cd externals/AndroidAPS && ./gradlew dependencies

lsp-setup-python:
	pip install pyright

lsp-verify:
	python tools/verify_refs.py --lsp --json
```

---

## Decision Matrix

| Question | Recommendation |
|----------|----------------|
| Start with which language? | **JS/TS** - lowest friction, covers Nightscout |
| Skip Swift on Linux? | **Yes** - defer to macOS CI |
| Pre-sync Gradle in bootstrap? | **Yes** - add to `make bootstrap` |
| Cache LSP servers? | **Yes** - keep running during session |

---

## Next Steps

1. **Immediate**: Install tsserver, test on cgm-remote-monitor
2. **Week 1**: Implement JS/TS symbol verification in verify_refs.py
3. **Week 2**: Add Kotlin/Java LSP, update bootstrap
4. **Future**: macOS CI for Swift verification

---

## References

- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server)
- [kotlin-language-server](https://github.com/fwcd/kotlin-language-server)
- [Eclipse JDT LS](https://github.com/eclipse/eclipse.jdt.ls)
- [pyright](https://github.com/microsoft/pyright)
- [sourcekit-lsp](https://github.com/apple/sourcekit-lsp)
