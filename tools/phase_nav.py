#!/usr/bin/env python3
"""
Phase Navigator - Tracks document phases and suggests transitions in the engineering cycle.

Understands the 5-phase development cycle:
1. Source Analysis (10-domain, mapping/) - Analyze source code, document behavior
2. Research & Synthesis (60-research/) - Compare implementations, propose improvements
3. Knowledge Consolidation (10-domain/) - Distill research into stable knowledge
4. Design Guidance (30-design/) - Create actionable implementation guides
5. Decision Making (90-decisions/) - Formalize approach via ADRs

Usage:
    # Show phase of a document
    python tools/phase_nav.py current docs/10-domain/treatments.md

    # Show all documents by phase
    python tools/phase_nav.py list

    # Suggest next steps based on recent changes
    python tools/phase_nav.py suggest

    # Show phase transitions needed
    python tools/phase_nav.py transitions

    # JSON output for agents
    python tools/phase_nav.py list --json

For AI agents:
    python tools/phase_nav.py suggest --json | jq '.suggestions[]'
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
DOCS_DIR = WORKSPACE_ROOT / "docs"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
SPECS_DIR = WORKSPACE_ROOT / "specs"
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"

PHASES = {
    "source_analysis": {
        "name": "Source Analysis",
        "order": 1,
        "directories": ["mapping", "docs/10-domain"],
        "indicators": ["code reference", "implementation", "behavior", "source:"],
        "description": "Analyze source code, document actual behavior",
        "next_phase": "research_synthesis"
    },
    "research_synthesis": {
        "name": "Research & Synthesis",
        "order": 2,
        "directories": ["docs/60-research"],
        "indicators": ["proposal", "comparative", "analysis", "alternative"],
        "description": "Compare implementations, identify patterns, propose improvements",
        "next_phase": "knowledge_consolidation"
    },
    "knowledge_consolidation": {
        "name": "Knowledge Consolidation",
        "order": 3,
        "directories": ["docs/10-domain"],
        "indicators": ["deep-dive", "protocol", "glossary", "specification"],
        "description": "Distill research into stable domain knowledge",
        "next_phase": "design_guidance"
    },
    "design_guidance": {
        "name": "Design Guidance",
        "order": 4,
        "directories": ["docs/30-design"],
        "indicators": ["guide", "pattern", "integration", "architecture"],
        "description": "Create actionable implementation guides",
        "next_phase": "decision_making"
    },
    "decision_making": {
        "name": "Decision Making",
        "order": 5,
        "directories": ["docs/90-decisions"],
        "indicators": ["adr-", "decision", "supersedes", "status:"],
        "description": "Formalize approach via Architecture Decision Records",
        "next_phase": None
    }
}

REQ_PATTERN = re.compile(r'\b(REQ-\d{3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')
CODE_REF_PATTERN = re.compile(r'`([a-zA-Z0-9_-]+:[^`]+)`')


def get_file_mtime(path: Path) -> datetime:
    """Get file modification time as datetime."""
    try:
        stat = path.stat()
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.min.replace(tzinfo=timezone.utc)


def detect_phase(file_path: Path) -> dict:
    """Detect the phase of a document based on location and content."""
    relative_path = str(file_path.relative_to(WORKSPACE_ROOT))
    
    detected_phase = None
    confidence = 0.0
    signals = []
    
    for phase_id, phase_info in PHASES.items():
        phase_confidence = 0.0
        phase_signals = []
        
        for dir_pattern in phase_info["directories"]:
            if relative_path.startswith(dir_pattern):
                phase_confidence += 0.5
                phase_signals.append(f"Located in {dir_pattern}")
                break
        
        if file_path.exists() and file_path.suffix == ".md":
            try:
                content = file_path.read_text(errors="ignore").lower()
                for indicator in phase_info["indicators"]:
                    if indicator.lower() in content:
                        phase_confidence += 0.1
                        phase_signals.append(f"Contains '{indicator}'")
            except Exception:
                pass
        
        if phase_confidence > confidence:
            confidence = phase_confidence
            detected_phase = phase_id
            signals = phase_signals
    
    return {
        "phase": detected_phase,
        "phase_name": PHASES[detected_phase]["name"] if detected_phase else "Unknown",
        "confidence": min(confidence, 1.0),
        "signals": signals,
        "next_phase": PHASES[detected_phase]["next_phase"] if detected_phase else None
    }


def get_document_info(file_path: Path) -> dict:
    """Get comprehensive info about a document."""
    relative_path = str(file_path.relative_to(WORKSPACE_ROOT))
    phase_info = detect_phase(file_path)
    mtime = get_file_mtime(file_path)
    
    requirements = []
    gaps = []
    code_refs = []
    
    if file_path.exists() and file_path.suffix == ".md":
        try:
            content = file_path.read_text(errors="ignore")
            requirements = list(set(REQ_PATTERN.findall(content)))
            gaps = list(set(GAP_PATTERN.findall(content)))
            code_refs = list(set(CODE_REF_PATTERN.findall(content)))
        except Exception:
            pass
    
    return {
        "path": relative_path,
        "modified": mtime.isoformat(),
        "modified_ago": _time_ago(mtime),
        "phase": phase_info["phase"],
        "phase_name": phase_info["phase_name"],
        "confidence": phase_info["confidence"],
        "signals": phase_info["signals"],
        "next_phase": phase_info["next_phase"],
        "requirements": requirements,
        "gaps": gaps,
        "code_refs_count": len(code_refs)
    }


def _time_ago(dt: datetime) -> str:
    """Human-readable time ago string."""
    now = datetime.now(tz=timezone.utc)
    delta = now - dt
    
    if delta.days > 30:
        return f"{delta.days // 30} months ago"
    elif delta.days > 0:
        return f"{delta.days} days ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600} hours ago"
    else:
        return f"{delta.seconds // 60} minutes ago"


def list_documents_by_phase() -> dict:
    """List all documents grouped by phase."""
    result = {phase_id: [] for phase_id in PHASES}
    result["unknown"] = []
    
    search_dirs = [
        DOCS_DIR,
        MAPPING_DIR,
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for md_file in search_dir.rglob("*.md"):
            if md_file.name.startswith("_"):
                continue
            
            doc_info = get_document_info(md_file)
            phase = doc_info["phase"] or "unknown"
            result[phase].append(doc_info)
    
    for phase_id in result:
        result[phase_id].sort(key=lambda x: x["modified"], reverse=True)
    
    return result


def suggest_transitions() -> list:
    """Suggest phase transitions based on document state."""
    suggestions = []
    docs_by_phase = list_documents_by_phase()
    
    for phase_id, phase_info in PHASES.items():
        docs = docs_by_phase.get(phase_id, [])
        
        for doc in docs:
            if doc["next_phase"] and doc["confidence"] >= 0.5:
                next_phase_name = PHASES[doc["next_phase"]]["name"]
                
                if doc["gaps"]:
                    suggestions.append({
                        "type": "phase_transition",
                        "priority": "high",
                        "document": doc["path"],
                        "current_phase": phase_info["name"],
                        "suggested_action": f"Document has {len(doc['gaps'])} gaps - consider progressing to {next_phase_name}",
                        "gaps": doc["gaps"]
                    })
                
                if doc["requirements"] and phase_id == "source_analysis":
                    suggestions.append({
                        "type": "phase_transition",
                        "priority": "medium",
                        "document": doc["path"],
                        "current_phase": phase_info["name"],
                        "suggested_action": f"Requirements identified - ready for {next_phase_name}",
                        "requirements": doc["requirements"]
                    })
    
    source_docs = docs_by_phase.get("source_analysis", [])
    research_docs = docs_by_phase.get("research_synthesis", [])
    
    source_modified = {doc["path"]: doc for doc in source_docs}
    
    for research_doc in research_docs:
        try:
            content = (WORKSPACE_ROOT / research_doc["path"]).read_text(errors="ignore")
            for source_path in source_modified:
                if source_path in content or Path(source_path).stem in content:
                    source_info = source_modified[source_path]
                    if source_info["modified"] > research_doc["modified"]:
                        suggestions.append({
                            "type": "update_needed",
                            "priority": "high",
                            "document": research_doc["path"],
                            "current_phase": "Research & Synthesis",
                            "suggested_action": f"Source doc {source_path} updated after this research - review needed",
                            "source_modified": source_info["modified"]
                        })
        except Exception:
            pass
    
    suggestions.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 3))
    
    return suggestions


def get_phase_summary() -> dict:
    """Get summary of documents by phase."""
    docs_by_phase = list_documents_by_phase()
    
    summary = {
        "phases": {},
        "total_documents": 0,
        "cycle_health": "healthy"
    }
    
    for phase_id, phase_info in PHASES.items():
        docs = docs_by_phase.get(phase_id, [])
        summary["phases"][phase_id] = {
            "name": phase_info["name"],
            "order": phase_info["order"],
            "count": len(docs),
            "recent": docs[:3] if docs else []
        }
        summary["total_documents"] += len(docs)
    
    unknown_count = len(docs_by_phase.get("unknown", []))
    if unknown_count > 0:
        summary["unknown_count"] = unknown_count
    
    source_count = len(docs_by_phase.get("source_analysis", []))
    decision_count = len(docs_by_phase.get("decision_making", []))
    
    if source_count > 0 and decision_count == 0:
        summary["cycle_health"] = "early_stage"
    elif decision_count > source_count:
        summary["cycle_health"] = "mature"
    
    return summary


def format_phase_list(docs_by_phase: dict, verbose: bool = False) -> str:
    """Format document list by phase for human display."""
    output = []
    output.append("=" * 70)
    output.append("DOCUMENTS BY PHASE")
    output.append("=" * 70)
    
    for phase_id, phase_info in PHASES.items():
        docs = docs_by_phase.get(phase_id, [])
        output.append(f"\n## {phase_info['order']}. {phase_info['name']} ({len(docs)} docs)")
        output.append(f"   {phase_info['description']}")
        
        if docs:
            for doc in docs[:5 if not verbose else len(docs)]:
                reqs = f" [{', '.join(doc['requirements'][:3])}]" if doc['requirements'] else ""
                output.append(f"   - {doc['path']} ({doc['modified_ago']}){reqs}")
            
            if not verbose and len(docs) > 5:
                output.append(f"   ... and {len(docs) - 5} more")
        else:
            output.append("   (no documents)")
    
    unknown = docs_by_phase.get("unknown", [])
    if unknown:
        output.append(f"\n## Unclassified ({len(unknown)} docs)")
        for doc in unknown[:3]:
            output.append(f"   - {doc['path']}")
    
    return "\n".join(output)


def format_suggestions(suggestions: list) -> str:
    """Format suggestions for human display."""
    if not suggestions:
        return "No transitions suggested - cycle is stable."
    
    output = []
    output.append("=" * 70)
    output.append("SUGGESTED TRANSITIONS")
    output.append("=" * 70)
    
    for i, suggestion in enumerate(suggestions, 1):
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(suggestion.get("priority", "low"), "⚪")
        output.append(f"\n{i}. [{priority_icon} {suggestion.get('priority', 'low').upper()}] {suggestion['document']}")
        output.append(f"   Phase: {suggestion['current_phase']}")
        output.append(f"   Action: {suggestion['suggested_action']}")
    
    return "\n".join(output)


def cmd_current(args, json_output: bool) -> int:
    """Show phase of a specific document."""
    if not args.file:
        print("Error: File path required", file=sys.stderr)
        return 1
    
    file_path = WORKSPACE_ROOT / args.file
    if not file_path.exists():
        if json_output:
            print(json.dumps({"error": f"File not found: {args.file}"}))
        else:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1
    
    doc_info = get_document_info(file_path)
    
    if json_output:
        print(json.dumps(doc_info, indent=2))
    else:
        print(f"File: {doc_info['path']}")
        print(f"Phase: {doc_info['phase_name']} (confidence: {doc_info['confidence']:.0%})")
        print(f"Modified: {doc_info['modified_ago']}")
        if doc_info['next_phase']:
            print(f"Next Phase: {PHASES[doc_info['next_phase']]['name']}")
        if doc_info['signals']:
            print(f"Signals: {', '.join(doc_info['signals'])}")
        if doc_info['requirements']:
            print(f"Requirements: {', '.join(doc_info['requirements'])}")
        if doc_info['gaps']:
            print(f"Gaps: {', '.join(doc_info['gaps'])}")
    
    return 0


def cmd_list(args, json_output: bool) -> int:
    """List all documents by phase."""
    docs_by_phase = list_documents_by_phase()
    
    if json_output:
        print(json.dumps(docs_by_phase, indent=2))
    else:
        print(format_phase_list(docs_by_phase, verbose=args.verbose))
    
    return 0


def cmd_suggest(args, json_output: bool) -> int:
    """Suggest phase transitions."""
    suggestions = suggest_transitions()
    
    if json_output:
        print(json.dumps({"suggestions": suggestions, "count": len(suggestions)}, indent=2))
    else:
        print(format_suggestions(suggestions))
    
    return 0


def cmd_summary(args, json_output: bool) -> int:
    """Show phase summary."""
    summary = get_phase_summary()
    
    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 70)
        print("PHASE SUMMARY")
        print("=" * 70)
        print(f"\nTotal Documents: {summary['total_documents']}")
        print(f"Cycle Health: {summary['cycle_health']}")
        print("\nPhases:")
        for phase_id, phase_data in summary['phases'].items():
            print(f"  {phase_data['order']}. {phase_data['name']}: {phase_data['count']} docs")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Phase Navigator - Track document phases in the engineering cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  current <file>  Show phase of a specific document
  list            List all documents by phase
  suggest         Suggest phase transitions
  summary         Show phase summary

Examples:
  %(prog)s current docs/10-domain/treatments.md
  %(prog)s list --json
  %(prog)s suggest
"""
    )
    
    parser.add_argument("command", choices=["current", "list", "suggest", "summary"],
                        help="Command to run")
    parser.add_argument("file", nargs="?", help="File path (for 'current' command)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    commands = {
        "current": cmd_current,
        "list": cmd_list,
        "suggest": cmd_suggest,
        "summary": cmd_summary
    }
    
    return commands[args.command](args, args.json)


if __name__ == "__main__":
    sys.exit(main())
