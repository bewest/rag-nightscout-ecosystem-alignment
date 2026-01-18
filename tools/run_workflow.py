#!/usr/bin/env python3
"""
Automated Workflow Runner - orchestrates validation and verification workflows.

Runs comprehensive validation workflows for CI/CD pipelines:
- Code reference validation
- Documentation coverage analysis
- Test coverage verification
- Schema validation
- Link checking
- Terminology consistency

Usage:
    # Run full workflow
    python tools/run_workflow.py

    # Run specific workflow
    python tools/run_workflow.py --workflow validation

    # Quick check (fast subset)
    python tools/run_workflow.py --quick

    # JSON output for agents
    python tools/run_workflow.py --json

    # Fail fast on first error
    python tools/run_workflow.py --fail-fast

Workflows:
    validation  - Validate all JSON/YAML files
    verification - Run all static verification tools
    coverage    - Generate coverage reports
    full        - Complete CI/CD pipeline
    quick       - Fast validation subset

For CI/CD:
    python tools/run_workflow.py --json > workflow-report.json
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TOOLS_DIR = WORKSPACE_ROOT / "tools"


class WorkflowRunner:
    """Orchestrates workflow execution."""
    
    def __init__(self, fail_fast=False, verbose=False):
        self.fail_fast = fail_fast
        self.verbose = verbose
        self.results = []
    
    def run_command(self, name, description, command, critical=True):
        """Run a command and track results."""
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"Running: {name}")
            print(f"Description: {description}")
            print(f"Command: {' '.join(command)}")
            print(f"{'=' * 70}\n")
        else:
            print(f"Running {name}...", end=" ", flush=True)
        
        start_time = datetime.now()
        
        try:
            result = subprocess.run(
                command,
                cwd=WORKSPACE_ROOT,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            success = result.returncode == 0
            
            task_result = {
                "name": name,
                "description": description,
                "command": " ".join(command),
                "success": success,
                "duration_seconds": round(duration, 2),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
            self.results.append(task_result)
            
            if self.verbose:
                if result.stdout:
                    print("STDOUT:")
                    print(result.stdout)
                if result.stderr:
                    print("STDERR:")
                    print(result.stderr)
            else:
                print("✓" if success else "✗")
            
            if not success and critical and self.fail_fast:
                print(f"\nFAILURE: {name} failed (exit code {result.returncode})")
                if result.stderr:
                    print(result.stderr)
                sys.exit(1)
            
            return success
        
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            task_result = {
                "name": name,
                "description": description,
                "command": " ".join(command),
                "success": False,
                "duration_seconds": round(duration, 2),
                "error": "Command timeout (300s)"
            }
            self.results.append(task_result)
            
            if not self.verbose:
                print("✗ (timeout)")
            
            if critical and self.fail_fast:
                print(f"\nFAILURE: {name} timed out")
                sys.exit(1)
            
            return False
        
        except Exception as e:
            task_result = {
                "name": name,
                "description": description,
                "command": " ".join(command),
                "success": False,
                "error": str(e)
            }
            self.results.append(task_result)
            
            if not self.verbose:
                print(f"✗ ({e})")
            
            if critical and self.fail_fast:
                print(f"\nFAILURE: {name} raised exception: {e}")
                sys.exit(1)
            
            return False


def run_validation_workflow(runner):
    """Run validation workflow (JSON, YAML, links)."""
    print("\n=== Validation Workflow ===\n")
    
    # JSON Schema validation
    runner.run_command(
        "JSON Validation",
        "Validate JSON fixtures against schemas",
        ["python3", str(TOOLS_DIR / "validate_json.py")],
        critical=False
    )
    
    # Fixture validation (existing tool)
    runner.run_command(
        "Fixture Validation",
        "Validate fixtures against shape specs",
        ["python3", str(TOOLS_DIR / "validate_fixtures.py")],
        critical=False
    )
    
    # Link checking
    runner.run_command(
        "Link Check",
        "Verify markdown links and code references",
        ["python3", str(TOOLS_DIR / "linkcheck.py")],
        critical=False
    )


def run_verification_workflow(runner):
    """Run verification workflow (static analysis)."""
    print("\n=== Verification Workflow ===\n")
    
    # Code reference validation
    runner.run_command(
        "Code References",
        "Verify code references resolve to files",
        ["python3", str(TOOLS_DIR / "verify_refs.py")],
        critical=False
    )
    
    # Coverage analysis
    runner.run_command(
        "Coverage Analysis",
        "Analyze requirement/gap coverage",
        ["python3", str(TOOLS_DIR / "verify_coverage.py")],
        critical=False
    )
    
    # Terminology consistency
    runner.run_command(
        "Terminology Check",
        "Check terminology consistency",
        ["python3", str(TOOLS_DIR / "verify_terminology.py")],
        critical=False
    )
    
    # Assertion tracing
    runner.run_command(
        "Assertion Trace",
        "Trace assertions to requirements",
        ["python3", str(TOOLS_DIR / "verify_assertions.py")],
        critical=False
    )


def run_coverage_workflow(runner):
    """Run coverage workflow (generate reports)."""
    print("\n=== Coverage Workflow ===\n")
    
    # Generate coverage matrix
    runner.run_command(
        "Coverage Matrix",
        "Generate scenario coverage matrix",
        ["python3", str(TOOLS_DIR / "gen_coverage.py")],
        critical=False
    )
    
    # Generate traceability matrix
    runner.run_command(
        "Traceability Matrix",
        "Generate full traceability matrix",
        ["python3", str(TOOLS_DIR / "gen_traceability.py")],
        critical=False
    )
    
    # Generate inventory
    runner.run_command(
        "Inventory",
        "Generate workspace inventory",
        ["python3", str(TOOLS_DIR / "gen_inventory.py")],
        critical=False
    )


def run_quick_workflow(runner):
    """Run quick validation (subset for fast feedback)."""
    print("\n=== Quick Validation ===\n")
    
    # Link checking (fast)
    runner.run_command(
        "Link Check",
        "Verify markdown links",
        ["python3", str(TOOLS_DIR / "linkcheck.py")],
        critical=False
    )
    
    # Code references (fast)
    runner.run_command(
        "Code References",
        "Verify code references",
        ["python3", str(TOOLS_DIR / "verify_refs.py")],
        critical=False
    )
    
    # Python syntax check
    runner.run_command(
        "Python Syntax",
        "Check Python tool syntax",
        ["python3", "-m", "compileall", "tools/"],
        critical=True
    )


def run_full_workflow(runner):
    """Run complete CI/CD workflow."""
    run_validation_workflow(runner)
    run_verification_workflow(runner)
    run_coverage_workflow(runner)
    
    # Python syntax check
    print("\n=== Final Checks ===\n")
    runner.run_command(
        "Python Syntax",
        "Check Python tool syntax",
        ["python3", "-m", "compileall", "tools/"],
        critical=True
    )


def main():
    parser = argparse.ArgumentParser(description="Run automated validation workflows")
    parser.add_argument("--workflow", 
                       choices=["validation", "verification", "coverage", "quick", "full"],
                       default="full",
                       help="Workflow to run")
    parser.add_argument("--fail-fast", action="store_true",
                       help="Stop on first failure")
    parser.add_argument("--json", action="store_true",
                       help="Output JSON report")
    parser.add_argument("--verbose", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    runner = WorkflowRunner(fail_fast=args.fail_fast, verbose=args.verbose)
    
    start_time = datetime.now(timezone.utc)
    
    # Run selected workflow
    if args.workflow == "validation":
        run_validation_workflow(runner)
    elif args.workflow == "verification":
        run_verification_workflow(runner)
    elif args.workflow == "coverage":
        run_coverage_workflow(runner)
    elif args.workflow == "quick":
        run_quick_workflow(runner)
    else:  # full
        run_full_workflow(runner)
    
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()
    
    # Generate summary
    total = len(runner.results)
    passed = sum(1 for r in runner.results if r["success"])
    failed = total - passed
    
    summary = {
        "workflow": args.workflow,
        "timestamp": start_time.isoformat(),
        "duration_seconds": round(duration, 2),
        "total_tasks": total,
        "passed": passed,
        "failed": failed,
        "success": failed == 0,
        "tasks": runner.results
    }
    
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n" + "=" * 70)
        print(f"Workflow: {args.workflow}")
        print(f"Duration: {duration:.2f}s")
        print(f"Tasks: {passed}/{total} passed")
        
        if failed > 0:
            print(f"\nFailed tasks:")
            for result in runner.results:
                if not result["success"]:
                    print(f"  - {result['name']}")
                    if "error" in result:
                        print(f"    Error: {result['error']}")
        
        print("=" * 70)
    
    # Exit with appropriate code
    sys.exit(0 if summary["success"] else 1)


if __name__ == "__main__":
    main()
