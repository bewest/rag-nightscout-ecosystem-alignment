#!/usr/bin/env python3
"""
Workspace CLI - Unified command-line interface for workspace operations.

A single entry point for all workspace operations, designed for both
interactive use and automation/agent workflows.

Usage:
    # Interactive mode
    python tools/workspace_cli.py

    # Specific commands
    python tools/workspace_cli.py status
    python tools/workspace_cli.py validate
    python tools/workspace_cli.py query "sync"
    python tools/workspace_cli.py trace REQ-001
    python tools/workspace_cli.py coverage

    # JSON output for agents
    python tools/workspace_cli.py status --json
    python tools/workspace_cli.py validate --json

Commands:
    status      - Show workspace status
    validate    - Run validation checks
    verify      - Run verification checks
    query       - Search documentation
    trace       - Trace requirement/gap
    coverage    - Generate coverage reports
    inventory   - Generate inventory
    help        - Show help

For AI agents:
    workspace_cli.py status --json | jq '.repos[] | select(.status == "dirty")'
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TOOLS_DIR = WORKSPACE_ROOT / "tools"


class WorkspaceCLI:
    """Unified CLI for workspace operations."""
    
    def __init__(self, json_output=False, verbose=False):
        self.json_output = json_output
        self.verbose = verbose
    
    def run_tool(self, tool_name, args=None):
        """Run a workspace tool."""
        if args is None:
            args = []
        
        tool_path = TOOLS_DIR / tool_name
        if not tool_path.exists():
            return {"error": f"Tool not found: {tool_name}"}
        
        # Use sys.executable for better portability across platforms
        cmd = [sys.executable, str(tool_path)] + args
        
        if self.json_output and "--json" not in args:
            cmd.append("--json")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=WORKSPACE_ROOT,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if self.json_output and result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {
                        "output": result.stdout,
                        "exit_code": result.returncode
                    }
            
            return {
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "exit_code": result.returncode
            }
        
        except subprocess.TimeoutExpired:
            return {"error": "Command timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    def cmd_status(self, args):
        """Show workspace status."""
        return self.run_tool("bootstrap.py", ["status"])
    
    def cmd_validate(self, args):
        """Run validation checks."""
        workflow_args = ["--workflow", "validation"]
        if self.verbose:
            workflow_args.append("--verbose")
        return self.run_tool("run_workflow.py", workflow_args)
    
    def cmd_verify(self, args):
        """Run verification checks."""
        workflow_args = ["--workflow", "verification"]
        if self.verbose:
            workflow_args.append("--verbose")
        return self.run_tool("run_workflow.py", workflow_args)
    
    def cmd_query(self, args):
        """Search documentation."""
        if not args:
            return {"error": "Query term required"}
        
        query_args = ["--search", " ".join(args)]
        return self.run_tool("query_workspace.py", query_args)
    
    def cmd_trace(self, args):
        """Trace requirement or gap."""
        if not args:
            return {"error": "Requirement or gap ID required"}
        
        req_id = args[0].upper()
        
        if req_id.startswith("REQ-"):
            return self.run_tool("query_workspace.py", ["--req", req_id])
        elif req_id.startswith("GAP-"):
            return self.run_tool("query_workspace.py", ["--gap", req_id])
        else:
            return {"error": "ID must start with REQ- or GAP-"}
    
    def cmd_coverage(self, args):
        """Generate coverage reports."""
        return self.run_tool("gen_traceability.py", [])
    
    def cmd_inventory(self, args):
        """Generate workspace inventory."""
        return self.run_tool("gen_inventory.py", [])
    
    def cmd_phase(self, args):
        """Show phase information."""
        if not args:
            return self.run_tool("phase_nav.py", ["summary"])
        
        subcommand = args[0]
        if subcommand == "list":
            return self.run_tool("phase_nav.py", ["list"])
        elif subcommand == "suggest":
            return self.run_tool("phase_nav.py", ["suggest"])
        else:
            return self.run_tool("phase_nav.py", ["current", subcommand])
    
    def cmd_drift(self, args):
        """Check for documentation drift."""
        if args and args[0] == "--stale-only":
            return self.run_tool("detect_drift.py", ["--stale-only"])
        return self.run_tool("detect_drift.py", [])
    
    def cmd_specs(self, args):
        """Spec capture and coverage."""
        if not args:
            return self.run_tool("spec_capture.py", ["coverage"])
        
        subcommand = args[0]
        if subcommand == "scan":
            return self.run_tool("spec_capture.py", ["scan"])
        elif subcommand == "extract" and len(args) > 1:
            return self.run_tool("spec_capture.py", ["extract", args[1]])
        elif subcommand == "verify" and len(args) > 1:
            return self.run_tool("spec_capture.py", ["verify", args[1]])
        else:
            return self.run_tool("spec_capture.py", ["coverage"])
    
    def cmd_project(self, args):
        """Project management."""
        if not args:
            return self.run_tool("project_seq.py", ["status"])
        
        subcommand = args[0]
        if subcommand == "list":
            return self.run_tool("project_seq.py", ["list"])
        elif subcommand == "create" and len(args) > 1:
            return self.run_tool("project_seq.py", ["create", " ".join(args[1:])])
        elif subcommand == "advance":
            return self.run_tool("project_seq.py", ["advance"])
        else:
            return self.run_tool("project_seq.py", ["status"])
    
    def cmd_context(self, args):
        """Get workspace context for AI agents."""
        if not args:
            return self.run_tool("agent_context.py", ["brief"])
        
        subcommand = args[0]
        if subcommand == "full":
            return self.run_tool("agent_context.py", ["full"])
        elif subcommand == "for" and len(args) > 1:
            return self.run_tool("agent_context.py", ["for", args[1]])
        elif subcommand == "topic" and len(args) > 1:
            return self.run_tool("agent_context.py", ["topic", " ".join(args[1:])])
        else:
            return self.run_tool("agent_context.py", ["brief"])
    
    def cmd_advise(self, args):
        """Get AI-powered advice."""
        if not args:
            return self.run_tool("ai_advisor.py", ["suggest"])
        
        subcommand = args[0]
        if subcommand == "analyze" and len(args) > 1:
            return self.run_tool("ai_advisor.py", ["analyze", args[1]])
        elif subcommand == "topic" and len(args) > 1:
            return self.run_tool("ai_advisor.py", ["topic", " ".join(args[1:])])
        else:
            return self.run_tool("ai_advisor.py", ["suggest"])
    
    def cmd_help(self, args):
        """Show help."""
        help_text = """
Workspace CLI - Unified command-line interface

Commands:
  status      Show workspace status
  validate    Run validation checks
  verify      Run verification checks
  query       Search documentation
  trace       Trace requirement/gap
  coverage    Generate coverage reports
  inventory   Generate inventory
  phase       Phase navigation (list, suggest, <file>)
  drift       Check documentation drift
  specs       Spec capture and coverage (scan, extract, verify)
  project     Project management (list, create, advance)
  context     AI agent context (full, for <file>, topic <term>)
  advise      AI-powered advice (analyze <file>, topic <term>)
  help        Show this help

Options:
  --json      Output JSON
  --verbose   Verbose output

Examples:
  workspace_cli.py status
  workspace_cli.py query "authentication"
  workspace_cli.py trace REQ-001
  workspace_cli.py phase suggest
  workspace_cli.py drift --stale-only
  workspace_cli.py context for docs/10-domain/treatments.md
  workspace_cli.py advise
  workspace_cli.py validate --json
"""
        if self.json_output:
            return {"help": help_text}
        else:
            print(help_text)
            return None
    
    def interactive_mode(self):
        """Run interactive command prompt."""
        print("=== Workspace CLI (Interactive Mode) ===")
        print("Type 'help' for available commands, 'exit' to quit")
        print()
        
        while True:
            try:
                cmd_line = input("workspace> ").strip()
                
                if not cmd_line:
                    continue
                
                if cmd_line in ["exit", "quit"]:
                    break
                
                parts = cmd_line.split()
                command = parts[0]
                args = parts[1:]
                
                # Dispatch command
                method_name = f"cmd_{command}"
                if hasattr(self, method_name):
                    result = getattr(self, method_name)(args)
                    
                    if result is not None:
                        if isinstance(result, dict):
                            if "error" in result:
                                print(f"ERROR: {result['error']}")
                            elif "output" in result:
                                print(result["output"])
                            else:
                                print(json.dumps(result, indent=2))
                        else:
                            print(result)
                else:
                    print(f"Unknown command: {command}")
                    print("Type 'help' for available commands")
            
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Workspace CLI - Unified interface for workspace operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  status      Show workspace status
  validate    Run validation checks
  verify      Run verification checks
  query       Search documentation
  trace       Trace requirement/gap
  coverage    Generate coverage reports
  inventory   Generate inventory
  help        Show help

Examples:
  %(prog)s status
  %(prog)s query "authentication"
  %(prog)s trace REQ-001
  %(prog)s validate --json
"""
    )
    
    parser.add_argument("command", nargs="?", help="Command to run")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    cli = WorkspaceCLI(json_output=args.json, verbose=args.verbose)
    
    # Interactive mode if no command
    if not args.command:
        cli.interactive_mode()
        return
    
    # Dispatch command
    method_name = f"cmd_{args.command}"
    if hasattr(cli, method_name):
        result = getattr(cli, method_name)(args.args)
        
        if result is not None:
            if args.json:
                print(json.dumps(result, indent=2))
            elif isinstance(result, dict):
                if "error" in result:
                    print(f"ERROR: {result['error']}", file=sys.stderr)
                    sys.exit(1)
                elif "output" in result:
                    print(result["output"])
                else:
                    print(json.dumps(result, indent=2))
            else:
                print(result)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        print("Run 'workspace_cli.py help' for available commands", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
