#!/usr/bin/env python3
"""
LSP Query Tool - TypeScript/JavaScript Semantic Analysis

Communicates with tsserver to provide semantic queries for JS/TS codebases.
Supports symbol lookup, type information, and reference finding.

Usage:
    python tools/lsp_query.py definition <file> <line> <col>
    python tools/lsp_query.py references <file> <line> <col>
    python tools/lsp_query.py type <file> <line> <col>
    python tools/lsp_query.py symbols <file>
    python tools/lsp_query.py --json <command> <args>

Supports: cgm-remote-monitor, oref0, trio-oref codebases
"""

import subprocess
import json
import sys
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

TSSERVER_PATH = "/home/bewest/n/bin/tsserver"


class TSServerClient:
    """Client for communicating with TypeScript Server."""
    
    def __init__(self):
        self.process = None
        self.seq = 0
        
    def start(self):
        """Start tsserver process."""
        self.process = subprocess.Popen(
            [TSSERVER_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )
        # Wait for initial event
        self._read_responses(timeout=1.0)
        
    def stop(self):
        """Stop tsserver process."""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            
    def _send_request(self, command: str, arguments: dict) -> int:
        """Send a request to tsserver (newline-terminated JSON)."""
        self.seq += 1
        request = {
            "seq": self.seq,
            "type": "request",
            "command": command,
            "arguments": arguments
        }
        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        self.process.stdin.flush()
        return self.seq
        
    def _read_responses(self, timeout: float = 3.0) -> List[dict]:
        """Read responses from tsserver (Content-Length framed)."""
        import select
        
        responses = []
        start = time.time()
        
        while time.time() - start < timeout:
            ready, _, _ = select.select([self.process.stdout], [], [], 0.1)
            if not ready:
                continue
                
            header = self.process.stdout.readline().decode()
            if "Content-Length:" in header:
                length = int(header.split(":")[1].strip())
                self.process.stdout.readline()  # blank line
                body = self.process.stdout.read(length).decode()
                try:
                    responses.append(json.loads(body))
                except:
                    pass
                    
        return responses
    
    def _wait_for_response(self, seq: int, timeout: float = 3.0) -> Optional[dict]:
        """Wait for specific response by seq number."""
        responses = self._read_responses(timeout)
        for r in responses:
            if r.get("request_seq") == seq and r.get("type") == "response":
                return r
        return None
        
    def open_file(self, filepath: str) -> bool:
        """Open a file in tsserver."""
        abs_path = str(Path(filepath).resolve())
        self._send_request("open", {"file": abs_path})
        time.sleep(0.3)
        return True
        
    def get_definition(self, filepath: str, line: int, col: int) -> List[dict]:
        """Get definition location for symbol at position."""
        abs_path = str(Path(filepath).resolve())
        seq = self._send_request("definition", {
            "file": abs_path,
            "line": line,
            "offset": col
        })
        
        response = self._wait_for_response(seq)
        if response and response.get("success"):
            return response.get("body", [])
        return []
        
    def get_references(self, filepath: str, line: int, col: int) -> List[dict]:
        """Get all references to symbol at position."""
        abs_path = str(Path(filepath).resolve())
        seq = self._send_request("references", {
            "file": abs_path,
            "line": line,
            "offset": col
        })
        
        response = self._wait_for_response(seq)
        if response and response.get("success"):
            return response.get("body", {}).get("refs", [])
        return []
        
    def get_quickinfo(self, filepath: str, line: int, col: int) -> Optional[dict]:
        """Get type/documentation info for symbol at position."""
        abs_path = str(Path(filepath).resolve())
        seq = self._send_request("quickinfo", {
            "file": abs_path,
            "line": line,
            "offset": col
        })
        
        response = self._wait_for_response(seq)
        if response and response.get("success"):
            return response.get("body")
        return None
        
    def get_nav_tree(self, filepath: str) -> Optional[dict]:
        """Get navigation tree (symbols) for file."""
        abs_path = str(Path(filepath).resolve())
        seq = self._send_request("navtree", {"file": abs_path})
        
        response = self._wait_for_response(seq)
        if response and response.get("success"):
            return response.get("body")
        return None


def extract_symbols(nav_tree: dict, depth: int = 0) -> List[dict]:
    """Recursively extract symbols from navigation tree."""
    symbols = []
    
    if not nav_tree:
        return symbols
        
    kind = nav_tree.get("kind", "")
    name = nav_tree.get("text", "")
    spans = nav_tree.get("spans", [])
    
    if kind and name and kind != "script":
        start = spans[0] if spans else {}
        symbols.append({
            "name": name,
            "kind": kind,
            "line": start.get("start", {}).get("line", 0),
            "depth": depth
        })
    
    for child in nav_tree.get("childItems", []):
        symbols.extend(extract_symbols(child, depth + 1))
        
    return symbols


def format_definition(defs: List[dict], json_output: bool) -> str:
    """Format definition results."""
    if json_output:
        return json.dumps({"definitions": defs}, indent=2)
    
    if not defs:
        return "No definition found"
        
    lines = ["DEFINITIONS:"]
    for d in defs:
        file = d.get("file", "")
        start = d.get("start", {})
        line = start.get("line", 0)
        lines.append(f"  {file}:{line}")
    return "\n".join(lines)


def format_references(refs: List[dict], json_output: bool) -> str:
    """Format reference results."""
    if json_output:
        return json.dumps({"references": refs, "count": len(refs)}, indent=2)
    
    if not refs:
        return "No references found"
        
    lines = [f"REFERENCES ({len(refs)}):"]
    for r in refs[:20]:  # Limit output
        file = r.get("file", "")
        start = r.get("start", {})
        line = start.get("line", 0)
        text = r.get("lineText", "").strip()[:60]
        lines.append(f"  {file}:{line} - {text}")
    if len(refs) > 20:
        lines.append(f"  ... and {len(refs) - 20} more")
    return "\n".join(lines)


def format_quickinfo(info: Optional[dict], json_output: bool) -> str:
    """Format quickinfo results."""
    if json_output:
        return json.dumps({"info": info}, indent=2)
    
    if not info:
        return "No type info found"
        
    kind = info.get("kind", "")
    name = info.get("displayString", "")
    doc = info.get("documentation", "")
    
    lines = ["TYPE INFO:"]
    lines.append(f"  Kind: {kind}")
    lines.append(f"  Type: {name}")
    if doc:
        lines.append(f"  Doc: {doc[:100]}")
    return "\n".join(lines)


def format_symbols(symbols: List[dict], json_output: bool) -> str:
    """Format symbol list."""
    if json_output:
        return json.dumps({"symbols": symbols, "count": len(symbols)}, indent=2)
    
    if not symbols:
        return "No symbols found"
        
    lines = [f"SYMBOLS ({len(symbols)}):"]
    for s in symbols[:50]:  # Limit output
        indent = "  " * (s["depth"] + 1)
        lines.append(f"{indent}{s['kind']}: {s['name']} (L{s['line']})")
    if len(symbols) > 50:
        lines.append(f"  ... and {len(symbols) - 50} more")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LSP Query Tool for TypeScript/JavaScript")
    parser.add_argument("command", choices=["definition", "references", "type", "symbols", "check"],
                        help="Query type")
    parser.add_argument("file", help="File to analyze")
    parser.add_argument("line", nargs="?", type=int, help="Line number (1-based)")
    parser.add_argument("col", nargs="?", type=int, help="Column number (1-based)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    # Validate file exists
    if not Path(args.file).exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
        
    # Check file type
    ext = Path(args.file).suffix.lower()
    if ext not in [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"]:
        print(f"Error: Not a JS/TS file: {args.file}", file=sys.stderr)
        sys.exit(1)
    
    # Quick check mode - just verify tsserver works
    if args.command == "check":
        try:
            client = TSServerClient()
            client.start()
            client.open_file(args.file)
            nav = client.get_nav_tree(args.file)
            client.stop()
            if nav:
                print("✅ tsserver working" if not args.json else json.dumps({"status": "ok"}))
            else:
                print("⚠️ tsserver responded but no data")
        except Exception as e:
            print(f"❌ tsserver error: {e}" if not args.json else json.dumps({"status": "error", "message": str(e)}))
            sys.exit(1)
        return
        
    # Validate line/col for position-based commands
    if args.command in ["definition", "references", "type"]:
        if args.line is None or args.col is None:
            print(f"Error: {args.command} requires line and col arguments", file=sys.stderr)
            sys.exit(1)
    
    # Run query
    client = TSServerClient()
    try:
        client.start()
        client.open_file(args.file)
        
        if args.command == "definition":
            result = client.get_definition(args.file, args.line, args.col)
            print(format_definition(result, args.json))
            
        elif args.command == "references":
            result = client.get_references(args.file, args.line, args.col)
            print(format_references(result, args.json))
            
        elif args.command == "type":
            result = client.get_quickinfo(args.file, args.line, args.col)
            print(format_quickinfo(result, args.json))
            
        elif args.command == "symbols":
            nav = client.get_nav_tree(args.file)
            symbols = extract_symbols(nav)
            print(format_symbols(symbols, args.json))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
