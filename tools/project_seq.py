#!/usr/bin/env python3
"""
Project Sequencer - Manages multi-component improvement projects.

Tracks progress through component sequences, validates transitions,
and ensures work items are completed in the correct order.

Projects are defined in .project.yaml files with component sequences.

Usage:
    # Show project status
    python tools/project_seq.py status

    # List all projects
    python tools/project_seq.py list

    # Advance to next component
    python tools/project_seq.py advance

    # Create a new project
    python tools/project_seq.py create "Sync Protocol Update"

    # Complete current component
    python tools/project_seq.py complete

    # JSON output for agents
    python tools/project_seq.py status --json

For AI agents:
    python tools/project_seq.py status --json | jq '.current_component'
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORKSPACE_ROOT = Path(__file__).parent.parent
PROJECTS_DIR = WORKSPACE_ROOT / ".projects"
CURRENT_PROJECT_FILE = PROJECTS_DIR / "current.json"

DEFAULT_PHASES = [
    "analysis",
    "research",
    "specification",
    "implementation",
    "verification",
    "documentation"
]


def ensure_projects_dir():
    """Ensure projects directory exists."""
    PROJECTS_DIR.mkdir(exist_ok=True)


def load_current_project() -> Optional[dict]:
    """Load the current active project."""
    if not CURRENT_PROJECT_FILE.exists():
        return None
    
    try:
        return json.loads(CURRENT_PROJECT_FILE.read_text())
    except Exception:
        return None


def save_current_project(project: dict):
    """Save the current project state."""
    ensure_projects_dir()
    CURRENT_PROJECT_FILE.write_text(json.dumps(project, indent=2))


def list_projects() -> list:
    """List all project files."""
    ensure_projects_dir()
    projects = []
    
    for project_file in PROJECTS_DIR.glob("*.json"):
        if project_file.name == "current.json":
            continue
        
        try:
            project = json.loads(project_file.read_text())
            projects.append({
                "id": project_file.stem,
                "name": project.get("name", project_file.stem),
                "status": project.get("status", "unknown"),
                "progress": project.get("progress", 0),
                "created": project.get("created", "unknown")
            })
        except Exception:
            pass
    
    return projects


def create_project(name: str, components: Optional[list] = None, phases: Optional[list] = None) -> dict:
    """Create a new project."""
    ensure_projects_dir()
    
    project_id = name.lower().replace(" ", "-").replace("_", "-")
    project_id = "".join(c for c in project_id if c.isalnum() or c == "-")
    
    if phases is None:
        phases = DEFAULT_PHASES.copy()
    
    if components is None:
        components = []
    
    project = {
        "id": project_id,
        "name": name,
        "status": "active",
        "created": datetime.now(tz=timezone.utc).isoformat(),
        "updated": datetime.now(tz=timezone.utc).isoformat(),
        "phases": phases,
        "components": components,
        "current_component_index": 0,
        "current_phase_index": 0,
        "progress": 0,
        "completed_items": [],
        "history": [
            {
                "action": "created",
                "timestamp": datetime.now(tz=timezone.utc).isoformat()
            }
        ]
    }
    
    project_file = PROJECTS_DIR / f"{project_id}.json"
    project_file.write_text(json.dumps(project, indent=2))
    
    save_current_project(project)
    
    return project


def add_component(project: dict, component: dict) -> dict:
    """Add a component to a project."""
    component_entry = {
        "id": component.get("id", f"comp-{len(project['components']) + 1}"),
        "name": component.get("name", "Unnamed Component"),
        "files": component.get("files", []),
        "dependencies": component.get("dependencies", []),
        "status": "pending",
        "phases_completed": []
    }
    
    project["components"].append(component_entry)
    project["updated"] = datetime.now(tz=timezone.utc).isoformat()
    
    return project


def get_current_state(project: dict) -> dict:
    """Get the current state of a project."""
    if not project:
        return {
            "has_project": False,
            "message": "No active project"
        }
    
    components = project.get("components", [])
    phases = project.get("phases", DEFAULT_PHASES)
    
    current_comp_idx = project.get("current_component_index", 0)
    current_phase_idx = project.get("current_phase_index", 0)
    
    current_component = None
    if components and current_comp_idx < len(components):
        current_component = components[current_comp_idx]
    
    current_phase = None
    if phases and current_phase_idx < len(phases):
        current_phase = phases[current_phase_idx]
    
    total_items = len(components) * len(phases) if components else len(phases)
    completed_items = len(project.get("completed_items", []))
    progress = completed_items / total_items if total_items > 0 else 0
    
    return {
        "has_project": True,
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "status": project.get("status"),
        "current_component": current_component,
        "current_component_index": current_comp_idx,
        "current_phase": current_phase,
        "current_phase_index": current_phase_idx,
        "total_components": len(components),
        "total_phases": len(phases),
        "progress": progress,
        "progress_percent": f"{progress:.0%}",
        "completed_items": completed_items,
        "total_items": total_items,
        "next_action": get_next_action(project)
    }


def get_next_action(project: dict) -> str:
    """Determine the next action for a project."""
    state = project.get("status", "active")
    
    if state == "completed":
        return "Project complete - no further action needed"
    
    components = project.get("components", [])
    phases = project.get("phases", DEFAULT_PHASES)
    
    current_comp_idx = project.get("current_component_index", 0)
    current_phase_idx = project.get("current_phase_index", 0)
    
    if not components:
        if current_phase_idx < len(phases):
            return f"Complete phase: {phases[current_phase_idx]}"
        return "Add components or complete project"
    
    if current_comp_idx < len(components):
        comp = components[current_comp_idx]
        if current_phase_idx < len(phases):
            return f"Complete {phases[current_phase_idx]} for {comp['name']}"
        return f"Advance to next component after {comp['name']}"
    
    return "All components complete - finalize project"


def advance_project(project: dict) -> dict:
    """Advance the project to the next phase or component."""
    phases = project.get("phases", DEFAULT_PHASES)
    components = project.get("components", [])
    
    current_comp_idx = project.get("current_component_index", 0)
    current_phase_idx = project.get("current_phase_index", 0)
    
    completed_item = {
        "component_index": current_comp_idx,
        "phase_index": current_phase_idx,
        "timestamp": datetime.now(tz=timezone.utc).isoformat()
    }
    
    if "completed_items" not in project:
        project["completed_items"] = []
    project["completed_items"].append(completed_item)
    
    if current_phase_idx < len(phases) - 1:
        project["current_phase_index"] = current_phase_idx + 1
        action = f"Advanced to phase: {phases[current_phase_idx + 1]}"
    elif components and current_comp_idx < len(components) - 1:
        project["current_component_index"] = current_comp_idx + 1
        project["current_phase_index"] = 0
        action = f"Advanced to component: {components[current_comp_idx + 1]['name']}"
    else:
        project["status"] = "completed"
        action = "Project completed"
    
    project["updated"] = datetime.now(tz=timezone.utc).isoformat()
    project["history"].append({
        "action": action,
        "timestamp": datetime.now(tz=timezone.utc).isoformat()
    })
    
    project_file = PROJECTS_DIR / f"{project['id']}.json"
    project_file.write_text(json.dumps(project, indent=2))
    save_current_project(project)
    
    return project


def format_status(state: dict) -> str:
    """Format project status for display."""
    if not state.get("has_project"):
        return "No active project.\n\nUse 'project_seq.py create \"Project Name\"' to create one."
    
    output = []
    output.append("=" * 70)
    output.append(f"PROJECT: {state['project_name']}")
    output.append("=" * 70)
    output.append(f"\nStatus: {state['status'].upper()}")
    output.append(f"Progress: {state['progress_percent']} ({state['completed_items']}/{state['total_items']} items)")
    
    if state.get("current_component"):
        output.append(f"\nCurrent Component: {state['current_component']['name']}")
        output.append(f"  Index: {state['current_component_index'] + 1}/{state['total_components']}")
    
    if state.get("current_phase"):
        output.append(f"\nCurrent Phase: {state['current_phase']}")
        output.append(f"  Index: {state['current_phase_index'] + 1}/{state['total_phases']}")
    
    output.append(f"\nNext Action: {state['next_action']}")
    
    return "\n".join(output)


def cmd_status(args, json_output: bool) -> int:
    """Show project status."""
    project = load_current_project()
    state = get_current_state(project)
    
    if json_output:
        print(json.dumps(state, indent=2))
    else:
        print(format_status(state))
    
    return 0


def cmd_list(args, json_output: bool) -> int:
    """List all projects."""
    projects = list_projects()
    
    if json_output:
        print(json.dumps({"projects": projects, "count": len(projects)}, indent=2))
    else:
        if not projects:
            print("No projects found.")
            return 0
        
        print("=" * 70)
        print("PROJECTS")
        print("=" * 70)
        
        for p in projects:
            status_icon = {"active": "▶", "completed": "✓", "paused": "⏸"}.get(p["status"], "○")
            print(f"\n{status_icon} {p['name']} ({p['id']})")
            print(f"  Status: {p['status']} | Progress: {p['progress']:.0%}")
    
    return 0


def cmd_create(args, json_output: bool) -> int:
    """Create a new project."""
    if not args.name:
        print("Error: Project name required", file=sys.stderr)
        return 1
    
    project = create_project(args.name)
    
    if json_output:
        print(json.dumps(project, indent=2))
    else:
        print(f"Created project: {project['name']}")
        print(f"ID: {project['id']}")
        print("\nAdd components with: project_seq.py add-component \"Component Name\"")
    
    return 0


def cmd_advance(args, json_output: bool) -> int:
    """Advance the project."""
    project = load_current_project()
    
    if not project:
        if json_output:
            print(json.dumps({"error": "No active project"}))
        else:
            print("Error: No active project", file=sys.stderr)
        return 1
    
    project = advance_project(project)
    state = get_current_state(project)
    
    if json_output:
        print(json.dumps(state, indent=2))
    else:
        print(f"Advanced project: {project['name']}")
        print(f"Progress: {state['progress_percent']}")
        print(f"Next: {state['next_action']}")
    
    return 0


def cmd_add_component(args, json_output: bool) -> int:
    """Add a component to the current project."""
    project = load_current_project()
    
    if not project:
        if json_output:
            print(json.dumps({"error": "No active project"}))
        else:
            print("Error: No active project", file=sys.stderr)
        return 1
    
    if not args.name:
        print("Error: Component name required", file=sys.stderr)
        return 1
    
    component = {
        "name": args.name,
        "files": args.files.split(",") if args.files else []
    }
    
    project = add_component(project, component)
    
    project_file = PROJECTS_DIR / f"{project['id']}.json"
    project_file.write_text(json.dumps(project, indent=2))
    save_current_project(project)
    
    if json_output:
        print(json.dumps({"added": component, "total_components": len(project["components"])}))
    else:
        print(f"Added component: {component['name']}")
        print(f"Total components: {len(project['components'])}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Project Sequencer - Manage multi-component projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  status            Show current project status
  list              List all projects
  create <name>     Create a new project
  advance           Advance to next phase/component
  add-component     Add a component to current project

Examples:
  %(prog)s status
  %(prog)s create "Sync Protocol Update"
  %(prog)s add-component "Treatment Sync" --files mapping/treatments.md
  %(prog)s advance
"""
    )
    
    parser.add_argument("command", choices=["status", "list", "create", "advance", "add-component"],
                        help="Command to run")
    parser.add_argument("name", nargs="?", help="Project/component name")
    parser.add_argument("--files", help="Comma-separated list of files (for add-component)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    commands = {
        "status": cmd_status,
        "list": cmd_list,
        "create": cmd_create,
        "advance": cmd_advance,
        "add-component": cmd_add_component
    }
    
    return commands[args.command](args, args.json)


if __name__ == "__main__":
    sys.exit(main())
