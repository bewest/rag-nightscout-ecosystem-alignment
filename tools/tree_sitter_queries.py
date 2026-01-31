#!/usr/bin/env python3
"""
Tree-sitter Query Library for Nightscout Ecosystem Analysis

Provides reusable patterns for extracting code structures across
JavaScript, Swift, Kotlin, and Java codebases.

Usage:
    python tools/tree_sitter_queries.py functions <file>
    python tools/tree_sitter_queries.py classes <file>
    python tools/tree_sitter_queries.py imports <file>
    python tools/tree_sitter_queries.py all <file>
    python tools/tree_sitter_queries.py --json functions <file>
"""

import subprocess
import json
import sys
import re
from pathlib import Path
from typing import Optional

# Query patterns by language and extraction type
QUERIES = {
    "javascript": {
        "functions": """
(function_declaration
  name: (identifier) @name) @func

(method_definition
  name: (property_identifier) @name) @method

(variable_declarator
  name: (identifier) @name
  value: [(function_expression) (arrow_function)]) @func
""",
        "classes": """
(class_declaration
  name: (identifier) @name
  body: (class_body) @body) @class
""",
        "imports": """
(import_statement
  source: (string) @source) @import

(call_expression
  function: (identifier) @func (#eq? @func "require")
  arguments: (arguments (string) @source)) @require
""",
        "exports": """
(export_statement) @export

(assignment_expression
  left: (member_expression
    object: (identifier) @obj (#eq? @obj "module")
    property: (property_identifier) @prop (#eq? @prop "exports"))) @module_exports
"""
    },
    "swift": {
        "functions": """
(function_declaration
  name: (simple_identifier) @name) @func

(init_declaration) @init
""",
        "classes": """
(class_declaration
  name: (type_identifier) @name) @class

(struct_declaration
  name: (type_identifier) @name) @struct

(enum_declaration
  name: (type_identifier) @name) @enum

(protocol_declaration
  name: (type_identifier) @name) @protocol
""",
        "imports": """
(import_declaration
  (identifier) @module) @import
""",
        "properties": """
(property_declaration
  name: (pattern) @name) @property
"""
    },
    "kotlin": {
        "functions": """
(function_declaration
  (simple_identifier) @name) @func
""",
        "classes": """
(class_declaration
  (type_identifier) @name) @class

(object_declaration
  (type_identifier) @name) @object
""",
        "imports": """
(import_header
  (identifier) @module) @import
"""
    },
    "java": {
        "functions": """
(method_declaration
  name: (identifier) @name) @method

(constructor_declaration
  name: (identifier) @name) @constructor
""",
        "classes": """
(class_declaration
  name: (identifier) @name) @class

(interface_declaration
  name: (identifier) @name) @interface

(enum_declaration
  name: (identifier) @name) @enum
""",
        "imports": """
(import_declaration
  (scoped_identifier) @module) @import
"""
    }
}

# File extension to language mapping
EXT_TO_LANG = {
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",  # tree-sitter-typescript extends javascript
    ".tsx": "javascript",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".java": "java"
}

# Kotlin needs explicit path to .so file
KOTLIN_SO = "/tmp/tree-sitter-grammars/node_modules/tree-sitter-kotlin/kotlin.so"


def detect_language(filepath: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = Path(filepath).suffix.lower()
    return EXT_TO_LANG.get(ext)


def run_tree_sitter_query(filepath: str, query: str, language: str) -> dict:
    """Run tree-sitter query and parse results."""
    # Build command
    cmd = ["tree-sitter", "query"]
    
    # Kotlin needs explicit language path
    if language == "kotlin":
        cmd.extend(["-l", KOTLIN_SO])
    
    # Write query to temp file (tree-sitter query reads from file)
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scm', delete=False) as f:
        f.write(query)
        query_file = f.name
    
    try:
        cmd.extend([query_file, filepath])
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return {"error": result.stderr, "matches": []}
        
        # Parse output
        matches = parse_query_output(result.stdout)
        return {"matches": matches, "count": len(matches)}
    finally:
        Path(query_file).unlink(missing_ok=True)


def parse_query_output(output: str) -> list:
    """Parse tree-sitter query output into structured data."""
    matches = []
    current_match = {}
    
    for line in output.strip().split('\n'):
        if not line.strip():
            if current_match:
                matches.append(current_match)
                current_match = {}
            continue
        
        # Pattern: "  name: `identifier_text`" or capture with location
        # tree-sitter query output format: pattern @capture row:col - row:col `text`
        match = re.match(r'\s*(\w+):\s*\[(\d+),\s*(\d+)\]\s*-\s*\[(\d+),\s*(\d+)\]', line)
        if match:
            capture = match.group(1)
            start_row, start_col = int(match.group(2)), int(match.group(3))
            end_row, end_col = int(match.group(4)), int(match.group(5))
            current_match[capture] = {
                "start": {"row": start_row, "col": start_col},
                "end": {"row": end_row, "col": end_col}
            }
    
    if current_match:
        matches.append(current_match)
    
    return matches


def extract_with_parse(filepath: str, extract_type: str) -> dict:
    """Extract code structures using tree-sitter parse + grep approach."""
    language = detect_language(filepath)
    if not language:
        return {"error": f"Unknown language for {filepath}"}
    
    # Use tree-sitter parse and grep for patterns
    cmd = ["tree-sitter", "parse", filepath]
    if language == "kotlin":
        cmd = ["tree-sitter", "parse", "-l", KOTLIN_SO, filepath]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr}
    
    # Parse the S-expression output
    parse_tree = result.stdout
    
    # Extract based on type
    extractions = []
    
    if extract_type == "functions":
        patterns = [
            # JavaScript/Swift with name: field
            r'\(function_declaration[^)]*name: \((?:identifier|simple_identifier) \[(\d+), (\d+)\] - \[(\d+), (\d+)\]\)',
            r'\(method_definition[^)]*name: \(property_identifier \[(\d+), (\d+)\] - \[(\d+), (\d+)\]\)',
            # Kotlin/Java - just capture the declaration line
            r'\(function_declaration \[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
            r'\(method_declaration \[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
            # init declarations (Swift)
            r'\(init_declaration \[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
        ]
    elif extract_type == "classes":
        patterns = [
            r'\(class_declaration[^)]*name: \((?:identifier|type_identifier) \[(\d+), (\d+)\] - \[(\d+), (\d+)\]\)',
            r'\(struct_declaration[^)]*name: \(type_identifier \[(\d+), (\d+)\] - \[(\d+), (\d+)\]\)',
            r'\(interface_declaration[^)]*name: \(identifier \[(\d+), (\d+)\] - \[(\d+), (\d+)\]\)',
            # Kotlin/Java - just capture the declaration line
            r'\(class_declaration \[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
            r'\(object_declaration \[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
        ]
    elif extract_type == "imports":
        patterns = [
            r'\(import_(?:statement|declaration|header)[^\n]*\[(\d+), (\d+)\] - \[(\d+), (\d+)\]',
        ]
    else:
        patterns = []
    
    # Read file to get actual text
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except:
        lines = []
    
    for pattern in patterns:
        for match in re.finditer(pattern, parse_tree):
            groups = match.groups()
            if len(groups) >= 4:
                start_row = int(groups[0])
                extractions.append({
                    "line": start_row + 1,
                    "text": lines[start_row].strip() if start_row < len(lines) else ""
                })
    
    return {
        "file": filepath,
        "language": language,
        "type": extract_type,
        "extractions": extractions,
        "count": len(extractions)
    }


def extract_all(filepath: str) -> dict:
    """Extract all code structures from a file."""
    language = detect_language(filepath)
    if not language:
        return {"error": f"Unknown language for {filepath}"}
    
    results = {
        "file": filepath,
        "language": language,
        "functions": extract_with_parse(filepath, "functions"),
        "classes": extract_with_parse(filepath, "classes"),
        "imports": extract_with_parse(filepath, "imports")
    }
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tree-sitter query library")
    parser.add_argument("command", choices=["functions", "classes", "imports", "all", "languages"],
                        help="What to extract")
    parser.add_argument("file", nargs="?", help="File to analyze")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    if args.command == "languages":
        output = {
            "supported": list(set(EXT_TO_LANG.values())),
            "extensions": EXT_TO_LANG
        }
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print("Supported languages:")
            for ext, lang in sorted(EXT_TO_LANG.items()):
                print(f"  {ext}: {lang}")
        return
    
    if not args.file:
        print("Error: file required", file=sys.stderr)
        sys.exit(1)
    
    if not Path(args.file).exists():
        print(f"Error: {args.file} not found", file=sys.stderr)
        sys.exit(1)
    
    if args.command == "all":
        result = extract_all(args.file)
    else:
        result = extract_with_parse(args.file, args.command)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        
        if args.command == "all":
            for extract_type in ["functions", "classes", "imports"]:
                data = result.get(extract_type, {})
                extractions = data.get("extractions", [])
                if extractions:
                    print(f"\n{extract_type.upper()} ({len(extractions)}):")
                    for item in extractions[:20]:  # Limit output
                        print(f"  L{item['line']}: {item['text'][:60]}")
        else:
            extractions = result.get("extractions", [])
            print(f"{args.command.upper()} in {args.file} ({len(extractions)} found):")
            for item in extractions:
                print(f"  L{item['line']}: {item['text'][:80]}")


if __name__ == "__main__":
    main()
