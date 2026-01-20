#!/usr/bin/env python3
"""
Agent Context Provider - Single entry point for AI agents to get workspace context.

Provides comprehensive context for AI coding agents working in the workspace,
including current project state, phase information, relevant files, and
pending work items.

Usage:
    # Get brief workspace context
    python tools/agent_context.py brief

    # Get context for working on a specific file
    python tools/agent_context.py for docs/10-domain/treatments.md

    # Get full workspace context
    python tools/agent_context.py full

    # Get context for a specific topic
    python tools/agent_context.py topic "sync protocol"

    # JSON output for agents
    python tools/agent_context.py brief --json

For AI agents:
    python tools/agent_context.py for mapping/x.md --json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORKSPACE_ROOT = Path(__file__).parent.parent
TOOLS_DIR = WORKSPACE_ROOT / "tools"
DOCS_DIR = WORKSPACE_ROOT / "docs"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
PROJECTS_DIR = WORKSPACE_ROOT / ".projects"

REQ_PATTERN = re.compile(r'\b(REQ-\d{3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')
CODE_REF_PATTERN = re.compile(r'`([a-zA-Z][a-zA-Z0-9_-]{0,15}):([a-zA-Z0-9_./-]+)(?:#(.+))?`')


def run_tool(tool_name: str, args: list = None, json_output: bool = True) -> dict:
    """Run a workspace tool and return result."""
    if args is None:
        args = []
    
    tool_path = TOOLS_DIR / tool_name
    if not tool_path.exists():
        return {"error": f"Tool not found: {tool_name}"}
    
    cmd = [sys.executable, str(tool_path)] + args
    if json_output:
        cmd.append("--json")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if json_output and result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw_output": result.stdout}
        
        return {"raw_output": result.stdout, "error": result.stderr if result.returncode != 0 else None}
    
    except subprocess.TimeoutExpired:
        return {"error": "Command timeout"}
    except Exception as e:
        return {"error": str(e)}


def get_recent_changes() -> list:
    """Get recently modified files."""
    recent = []
    
    search_dirs = [DOCS_DIR, MAPPING_DIR]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for md_file in search_dir.rglob("*.md"):
            if md_file.name.startswith("_"):
                continue
            
            try:
                stat = md_file.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                recent.append({
                    "path": str(md_file.relative_to(WORKSPACE_ROOT)),
                    "modified": mtime.isoformat(),
                    "modified_ago": _time_ago(mtime)
                })
            except Exception:
                pass
    
    recent.sort(key=lambda x: x["modified"], reverse=True)
    return recent[:10]


def _time_ago(dt: datetime) -> str:
    """Human-readable time ago string."""
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    
    if delta.days > 0:
        return f"{delta.days} days ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600} hours ago"
    else:
        return f"{delta.seconds // 60} minutes ago"


def get_brief_context() -> dict:
    """Get brief workspace context."""
    context = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "workspace": "nightscout-alignment-workspace"
    }
    
    phase_summary = run_tool("phase_nav.py", ["summary"])
    if "error" not in phase_summary:
        context["phase_summary"] = {
            "total_documents": phase_summary.get("total_documents", 0),
            "cycle_health": phase_summary.get("cycle_health", "unknown"),
            "phases": {
                k: v.get("count", 0) 
                for k, v in phase_summary.get("phases", {}).items()
            }
        }
    
    project_file = PROJECTS_DIR / "current.json"
    if project_file.exists():
        try:
            project = json.loads(project_file.read_text())
            context["current_project"] = {
                "name": project.get("name"),
                "status": project.get("status"),
                "current_phase": project.get("phases", [])[project.get("current_phase_index", 0)] if project.get("phases") else None
            }
        except Exception:
            pass
    
    context["recent_changes"] = get_recent_changes()[:5]
    
    phase_suggest = run_tool("phase_nav.py", ["suggest"])
    if "suggestions" in phase_suggest:
        context["pending_transitions"] = len(phase_suggest["suggestions"])
        context["top_suggestions"] = phase_suggest["suggestions"][:3]
    
    return context


def get_file_context(file_path: str) -> dict:
    """Get context for working on a specific file."""
    full_path = WORKSPACE_ROOT / file_path
    
    if not full_path.exists():
        return {"error": f"File not found: {file_path}"}
    
    context = {
        "file": file_path,
        "timestamp": datetime.now(tz=timezone.utc).isoformat()
    }
    
    phase_result = run_tool("phase_nav.py", ["current", file_path])
    if "error" not in phase_result:
        context["phase"] = {
            "current": phase_result.get("phase_name"),
            "confidence": phase_result.get("confidence"),
            "next_phase": phase_result.get("next_phase"),
            "signals": phase_result.get("signals", [])
        }
    
    try:
        content = full_path.read_text(errors="ignore")
        context["requirements"] = list(set(REQ_PATTERN.findall(content)))
        context["gaps"] = list(set(GAP_PATTERN.findall(content)))
        context["code_refs"] = [f"{r[0]}:{r[1]}" for r in CODE_REF_PATTERN.findall(content)][:10]
    except Exception:
        pass
    
    spec_result = run_tool("spec_capture.py", ["extract", file_path])
    if "error" not in spec_result:
        context["spec_coverage"] = {
            "total_specs": spec_result.get("total_specs", 0),
            "captured": spec_result.get("captured_count", 0),
            "uncaptured": spec_result.get("uncaptured_count", 0),
            "coverage": spec_result.get("coverage", 1.0)
        }
    
    related_files = find_related_files(file_path)
    if related_files:
        context["related_files"] = related_files
    
    context["suggested_actions"] = generate_suggestions(context)
    
    return context


def find_related_files(file_path: str) -> list:
    """Find files related to the given file."""
    related = []
    full_path = WORKSPACE_ROOT / file_path
    
    if not full_path.exists():
        return related
    
    try:
        content = full_path.read_text(errors="ignore")
    except Exception:
        return related
    
    requirements = set(REQ_PATTERN.findall(content))
    
    if requirements:
        search_dirs = [DOCS_DIR, MAPPING_DIR, TRACEABILITY_DIR]
        
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            
            for md_file in search_dir.rglob("*.md"):
                if str(md_file) == str(full_path):
                    continue
                
                try:
                    other_content = md_file.read_text(errors="ignore")
                    other_reqs = set(REQ_PATTERN.findall(other_content))
                    
                    shared = requirements & other_reqs
                    if shared:
                        related.append({
                            "path": str(md_file.relative_to(WORKSPACE_ROOT)),
                            "shared_requirements": list(shared)
                        })
                except Exception:
                    pass
    
    return related[:5]


def generate_suggestions(context: dict) -> list:
    """Generate action suggestions based on context."""
    suggestions = []
    
    phase = context.get("phase", {})
    if phase.get("next_phase"):
        suggestions.append({
            "action": "phase_transition",
            "description": f"Consider progressing to {phase['next_phase']} phase"
        })
    
    spec_coverage = context.get("spec_coverage", {})
    if spec_coverage.get("uncaptured", 0) > 3:
        suggestions.append({
            "action": "capture_specs",
            "description": f"Capture {spec_coverage['uncaptured']} uncaptured specifications as requirements"
        })
    
    if context.get("gaps"):
        suggestions.append({
            "action": "address_gaps",
            "description": f"Address {len(context['gaps'])} identified gaps: {', '.join(context['gaps'][:3])}"
        })
    
    return suggestions


def get_full_context() -> dict:
    """Get comprehensive workspace context."""
    context = get_brief_context()
    
    drift_result = run_tool("detect_drift.py", ["--stale-only"])
    if "summary" in drift_result:
        context["drift"] = {
            "health": drift_result["summary"].get("health"),
            "stale_count": drift_result["summary"].get("stale_count", 0),
            "broken_refs_count": drift_result["summary"].get("broken_refs_count", 0),
            "stale_documents": drift_result["summary"].get("stale_documents", [])[:5]
        }
    
    spec_result = run_tool("spec_capture.py", ["coverage"])
    if "overall_coverage" in spec_result:
        context["spec_coverage"] = {
            "overall": spec_result.get("overall_coverage", 0),
            "total_specs": spec_result.get("total_specs", 0),
            "captured": spec_result.get("captured_specs", 0),
            "needs_attention": [
                d["path"] for d in spec_result.get("documents_needing_attention", [])[:5]
            ]
        }
    
    context["recent_changes"] = get_recent_changes()
    
    return context


def get_topic_context(topic: str) -> dict:
    """Get context for a specific topic."""
    context = {
        "topic": topic,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "relevant_files": [],
        "requirements": [],
        "gaps": []
    }
    
    topic_lower = topic.lower()
    search_dirs = [DOCS_DIR, MAPPING_DIR]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for md_file in search_dir.rglob("*.md"):
            if md_file.name.startswith("_"):
                continue
            
            try:
                content = md_file.read_text(errors="ignore").lower()
                if topic_lower in content:
                    rel_path = str(md_file.relative_to(WORKSPACE_ROOT))
                    
                    full_content = md_file.read_text(errors="ignore")
                    reqs = REQ_PATTERN.findall(full_content)
                    gaps = GAP_PATTERN.findall(full_content)
                    
                    context["relevant_files"].append({
                        "path": rel_path,
                        "requirements": list(set(reqs)),
                        "gaps": list(set(gaps))
                    })
                    
                    context["requirements"].extend(reqs)
                    context["gaps"].extend(gaps)
            except Exception:
                pass
    
    context["requirements"] = list(set(context["requirements"]))
    context["gaps"] = list(set(context["gaps"]))
    context["relevant_files"] = context["relevant_files"][:15]
    
    return context


def format_brief(context: dict) -> str:
    """Format brief context for display."""
    output = []
    output.append("=" * 70)
    output.append("WORKSPACE CONTEXT")
    output.append("=" * 70)
    
    if "phase_summary" in context:
        ps = context["phase_summary"]
        output.append(f"\nDocuments: {ps.get('total_documents', 0)} | Health: {ps.get('cycle_health', 'unknown')}")
    
    if "current_project" in context:
        cp = context["current_project"]
        output.append(f"Project: {cp.get('name')} ({cp.get('status')})")
        if cp.get("current_phase"):
            output.append(f"  Current Phase: {cp['current_phase']}")
    
    if context.get("pending_transitions"):
        output.append(f"\nPending Transitions: {context['pending_transitions']}")
    
    if context.get("recent_changes"):
        output.append("\nRecent Changes:")
        for change in context["recent_changes"][:5]:
            output.append(f"  - {change['path']} ({change['modified_ago']})")
    
    return "\n".join(output)


def format_file_context(context: dict) -> str:
    """Format file context for display."""
    if "error" in context:
        return f"Error: {context['error']}"
    
    output = []
    output.append("=" * 70)
    output.append(f"CONTEXT FOR: {context['file']}")
    output.append("=" * 70)
    
    if "phase" in context:
        p = context["phase"]
        output.append(f"\nPhase: {p.get('current')} (confidence: {p.get('confidence', 0):.0%})")
        if p.get("next_phase"):
            output.append(f"Next Phase: {p['next_phase']}")
    
    if context.get("requirements"):
        output.append(f"\nRequirements: {', '.join(context['requirements'])}")
    
    if context.get("gaps"):
        output.append(f"Gaps: {', '.join(context['gaps'])}")
    
    if "spec_coverage" in context:
        sc = context["spec_coverage"]
        output.append(f"\nSpec Coverage: {sc.get('coverage', 0):.0%}")
        output.append(f"  Captured: {sc.get('captured', 0)} | Uncaptured: {sc.get('uncaptured', 0)}")
    
    if context.get("related_files"):
        output.append("\nRelated Files:")
        for rf in context["related_files"]:
            output.append(f"  - {rf['path']}")
    
    if context.get("suggested_actions"):
        output.append("\nSuggested Actions:")
        for sa in context["suggested_actions"]:
            output.append(f"  - {sa['description']}")
    
    return "\n".join(output)


def cmd_brief(args, json_output: bool) -> int:
    """Get brief context."""
    context = get_brief_context()
    
    if json_output:
        print(json.dumps(context, indent=2))
    else:
        print(format_brief(context))
    
    return 0


def cmd_for(args, json_output: bool) -> int:
    """Get context for a file."""
    if not args.target:
        print("Error: File path required", file=sys.stderr)
        return 1
    
    context = get_file_context(args.target)
    
    if json_output:
        print(json.dumps(context, indent=2))
    else:
        print(format_file_context(context))
    
    return 0 if "error" not in context else 1


def cmd_full(args, json_output: bool) -> int:
    """Get full context."""
    context = get_full_context()
    
    if json_output:
        print(json.dumps(context, indent=2))
    else:
        print(format_brief(context))
        
        if "drift" in context:
            d = context["drift"]
            print(f"\nDrift: {d.get('health')} - {d.get('stale_count', 0)} stale, {d.get('broken_refs_count', 0)} broken refs")
        
        if "spec_coverage" in context:
            sc = context["spec_coverage"]
            print(f"Spec Coverage: {sc.get('overall', 0):.0%} ({sc.get('captured', 0)}/{sc.get('total_specs', 0)})")
    
    return 0


def cmd_topic(args, json_output: bool) -> int:
    """Get context for a topic."""
    if not args.target:
        print("Error: Topic required", file=sys.stderr)
        return 1
    
    context = get_topic_context(args.target)
    
    if json_output:
        print(json.dumps(context, indent=2))
    else:
        print(f"Topic: {context['topic']}")
        print(f"Relevant Files: {len(context['relevant_files'])}")
        print(f"Requirements: {len(context['requirements'])}")
        print(f"Gaps: {len(context['gaps'])}")
        
        if context["relevant_files"]:
            print("\nFiles:")
            for rf in context["relevant_files"][:10]:
                print(f"  - {rf['path']}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Agent Context Provider - Get workspace context for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  brief           Get brief workspace context
  for <file>      Get context for a specific file
  full            Get comprehensive context
  topic <term>    Get context for a topic

Examples:
  %(prog)s brief
  %(prog)s for docs/10-domain/treatments.md
  %(prog)s topic "sync protocol" --json
"""
    )
    
    parser.add_argument("command", choices=["brief", "for", "full", "topic"],
                        help="Command to run")
    parser.add_argument("target", nargs="?", help="File path or topic")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    
    args = parser.parse_args()
    
    commands = {
        "brief": cmd_brief,
        "for": cmd_for,
        "full": cmd_full,
        "topic": cmd_topic
    }
    
    return commands[args.command](args, args.json)


if __name__ == "__main__":
    sys.exit(main())
