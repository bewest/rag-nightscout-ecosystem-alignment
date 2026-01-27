#!/usr/bin/env python3
"""
Hello World Plugin for sdqctl.

Demonstrates the plugin system end-to-end:
1. Plugin discovery via .sdqctl/directives.yaml
2. Handler execution with exit codes
3. Output capture for workflow integration

Usage:
    sdqctl verify hello-world
    # or in .conv files:
    VERIFY hello-world
"""
import sys
from pathlib import Path


def main() -> int:
    """Run hello world verification."""
    print("🎉 Hello from sdqctl plugin system!")
    print()
    
    # Demonstrate workspace awareness
    cwd = Path.cwd()
    print(f"Working directory: {cwd}")
    
    # Check for ecosystem markers
    markers = [
        ("traceability/", "Traceability artifacts"),
        ("mapping/", "Terminology mappings"),
        ("conformance/", "Conformance reports"),
        ("specs/", "Specification documents"),
    ]
    
    found = []
    for path, desc in markers:
        if (cwd / path).exists():
            found.append(desc)
    
    if found:
        print(f"\nEcosystem directories found: {len(found)}")
        for item in found:
            print(f"  ✓ {item}")
    else:
        print("\n⚠ No ecosystem directories found")
        print("  This plugin expects to run from the ecosystem repo root")
    
    print("\n✅ Plugin verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
