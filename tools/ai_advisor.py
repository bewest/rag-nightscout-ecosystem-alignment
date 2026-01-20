#!/usr/bin/env python3
"""
AI Advisor - Provides intelligent suggestions for workspace operations.

Uses Replit AI Integrations (Anthropic) to analyze workspace context and provide
actionable recommendations for development cycle progression, drift remediation,
and cross-component work planning.

Usage:
    # Get cycle advice for a document
    python tools/ai_advisor.py analyze docs/10-domain/treatments.md

    # Get suggestions for next steps
    python tools/ai_advisor.py suggest

    # Analyze a topic
    python tools/ai_advisor.py topic "sync protocol"

    # JSON output for agents
    python tools/ai_advisor.py suggest --json

For AI agents:
    python tools/ai_advisor.py analyze file.md --json
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TOOLS_DIR = WORKSPACE_ROOT / "tools"

AI_INTEGRATIONS_ANTHROPIC_API_KEY = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
AI_INTEGRATIONS_ANTHROPIC_BASE_URL = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")


def run_tool(tool_name: str, args: list = None) -> dict:
    """Run a workspace tool and return JSON result."""
    if args is None:
        args = []
    
    tool_path = TOOLS_DIR / tool_name
    if not tool_path.exists():
        return {"error": f"Tool not found: {tool_name}"}
    
    cmd = [sys.executable, str(tool_path)] + args + ["--json"]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw_output": result.stdout}
        
        return {"error": result.stderr}
    
    except Exception as e:
        return {"error": str(e)}


def get_ai_client():
    """Get Anthropic client if available."""
    if not AI_INTEGRATIONS_ANTHROPIC_API_KEY or not AI_INTEGRATIONS_ANTHROPIC_BASE_URL:
        return None
    
    try:
        from anthropic import Anthropic
        return Anthropic(
            api_key=AI_INTEGRATIONS_ANTHROPIC_API_KEY,
            base_url=AI_INTEGRATIONS_ANTHROPIC_BASE_URL
        )
    except ImportError:
        return None


def generate_advice(context: dict, query: str) -> str:
    """Generate AI advice based on context."""
    client = get_ai_client()
    
    if not client:
        return generate_fallback_advice(context, query)
    
    system_prompt = """You are a development cycle advisor for a documentation workspace.
The workspace follows a 5-phase cycle:
1. Source Analysis - Analyze code, document behavior
2. Research & Synthesis - Compare implementations, propose improvements  
3. Knowledge Consolidation - Distill research into stable knowledge
4. Design Guidance - Create implementation guides
5. Decision Making - Formalize via ADRs

Provide concise, actionable advice based on the workspace context provided.
Focus on:
- What phase the work is in
- What should happen next
- Cross-component dependencies
- Drift and spec coverage issues
"""
    
    context_str = json.dumps(context, indent=2)
    
    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Workspace context:\n{context_str}\n\nQuery: {query}"
            }]
        )
        return message.content[0].text
    except Exception as e:
        return f"AI unavailable: {str(e)}\n\n" + generate_fallback_advice(context, query)


def generate_fallback_advice(context: dict, query: str) -> str:
    """Generate rule-based advice when AI is unavailable."""
    advice = []
    
    if "phase" in context:
        phase = context["phase"]
        phase_name = phase.get("current", "Unknown")
        next_phase = phase.get("next_phase")
        
        advice.append(f"Current Phase: {phase_name}")
        if next_phase:
            advice.append(f"Consider progressing to: {next_phase}")
    
    if "spec_coverage" in context:
        sc = context["spec_coverage"]
        coverage = sc.get("coverage", 1.0)
        uncaptured = sc.get("uncaptured", 0)
        
        if coverage < 0.5:
            advice.append(f"Low spec coverage ({coverage:.0%}). Capture {uncaptured} implicit requirements.")
    
    if "gaps" in context and context["gaps"]:
        advice.append(f"Address {len(context['gaps'])} identified gaps: {', '.join(context['gaps'][:3])}")
    
    if "drift" in context:
        drift = context["drift"]
        if drift.get("stale_count", 0) > 0:
            advice.append(f"{drift['stale_count']} documents have drifted from source - review needed.")
    
    return "\n".join(advice) if advice else "No specific advice - workspace appears healthy."


def analyze_file(file_path: str) -> dict:
    """Analyze a file and provide advice."""
    file_context = run_tool("agent_context.py", ["for", file_path])
    
    if "error" in file_context:
        return {"error": file_context["error"]}
    
    query = f"Analyze this file and suggest next steps: {file_path}"
    advice = generate_advice(file_context, query)
    
    return {
        "file": file_path,
        "context": file_context,
        "advice": advice
    }


def suggest_next_steps() -> dict:
    """Get overall workspace suggestions."""
    brief_context = run_tool("agent_context.py", ["brief"])
    full_context = run_tool("agent_context.py", ["full"])
    
    context = {**brief_context, **full_context}
    
    query = "What are the highest priority next steps for this workspace?"
    advice = generate_advice(context, query)
    
    return {
        "context_summary": {
            "documents": context.get("phase_summary", {}).get("total_documents", 0),
            "health": context.get("phase_summary", {}).get("cycle_health", "unknown"),
            "pending_transitions": context.get("pending_transitions", 0),
            "stale_docs": context.get("drift", {}).get("stale_count", 0),
            "spec_coverage": context.get("spec_coverage", {}).get("overall", 1.0)
        },
        "advice": advice
    }


def analyze_topic(topic: str) -> dict:
    """Analyze a specific topic."""
    topic_context = run_tool("agent_context.py", ["topic", topic])
    
    query = f"Analyze the topic '{topic}' and suggest how to improve coverage and documentation."
    advice = generate_advice(topic_context, query)
    
    return {
        "topic": topic,
        "relevant_files": len(topic_context.get("relevant_files", [])),
        "requirements": topic_context.get("requirements", []),
        "gaps": topic_context.get("gaps", []),
        "advice": advice
    }


def format_result(result: dict) -> str:
    """Format result for display."""
    output = []
    output.append("=" * 70)
    output.append("AI ADVISOR")
    output.append("=" * 70)
    
    if "file" in result:
        output.append(f"\nFile: {result['file']}")
    
    if "topic" in result:
        output.append(f"\nTopic: {result['topic']}")
        output.append(f"Relevant Files: {result['relevant_files']}")
    
    if "context_summary" in result:
        cs = result["context_summary"]
        output.append(f"\nWorkspace: {cs.get('documents', 0)} docs | Health: {cs.get('health', 'unknown')}")
        output.append(f"Pending Transitions: {cs.get('pending_transitions', 0)}")
        output.append(f"Stale Documents: {cs.get('stale_docs', 0)}")
        output.append(f"Spec Coverage: {cs.get('spec_coverage', 0):.0%}")
    
    output.append("\n" + "-" * 70)
    output.append("ADVICE")
    output.append("-" * 70)
    output.append(result.get("advice", "No advice available."))
    
    return "\n".join(output)


def cmd_analyze(args, json_output: bool) -> int:
    """Analyze a file."""
    if not args.target:
        print("Error: File path required", file=sys.stderr)
        return 1
    
    result = analyze_file(args.target)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))
    
    return 0 if "error" not in result else 1


def cmd_suggest(args, json_output: bool) -> int:
    """Get suggestions."""
    result = suggest_next_steps()
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))
    
    return 0


def cmd_topic(args, json_output: bool) -> int:
    """Analyze a topic."""
    if not args.target:
        print("Error: Topic required", file=sys.stderr)
        return 1
    
    result = analyze_topic(args.target)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="AI Advisor - Intelligent workspace suggestions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  analyze <file>   Analyze a file and suggest next steps
  suggest          Get overall workspace suggestions
  topic <term>     Analyze a specific topic

Examples:
  %(prog)s analyze docs/10-domain/treatments.md
  %(prog)s suggest
  %(prog)s topic "sync protocol" --json
"""
    )
    
    parser.add_argument("command", choices=["analyze", "suggest", "topic"],
                        help="Command to run")
    parser.add_argument("target", nargs="?", help="File path or topic")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    
    args = parser.parse_args()
    
    commands = {
        "analyze": cmd_analyze,
        "suggest": cmd_suggest,
        "topic": cmd_topic
    }
    
    return commands[args.command](args, args.json)


if __name__ == "__main__":
    sys.exit(main())
