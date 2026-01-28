#!/usr/bin/env python3
"""
Mock Nightscout Server - lightweight HTTP server for offline testing.

Simulates Nightscout API v1/v3 with in-memory storage.
Supports: entries, treatments, devicestatus, profile

Usage:
    python tools/mock_nightscout.py                          # Start on port 5555
    python tools/mock_nightscout.py --port 8080              # Custom port
    python tools/mock_nightscout.py --fixtures conformance/scenarios/treatment-sync/

For conformance testing:
    python tools/mock_nightscout.py &
    python tools/run_conformance.py --nightscout http://localhost:5555
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

yaml: Any = None
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# In-memory storage for all collections
_storage: dict[str, list[dict]] = {
    "entries": [],
    "treatments": [],
    "devicestatus": [],
    "profile": [],
}

# API secret for authentication (optional)
API_SECRET = "mock-api-secret"


def generate_id() -> str:
    """Generate a MongoDB-style ObjectId (simplified)."""
    return uuid.uuid4().hex[:24]


def now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load_fixtures(fixtures_dir: Path) -> None:
    """Load fixture files into storage."""
    if not fixtures_dir.exists():
        print(f"Warning: Fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        return
    
    for filepath in fixtures_dir.glob("*.json"):
        collection = filepath.stem.split("-")[0]  # e.g., "treatments-001.json" -> "treatments"
        if collection in _storage:
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        _storage[collection].extend(data)
                    else:
                        _storage[collection].append(data)
                print(f"Loaded {filepath.name} into {collection}")
            except Exception as e:
                print(f"Error loading {filepath}: {e}", file=sys.stderr)
    
    if YAML_AVAILABLE:
        for filepath in fixtures_dir.glob("*.yaml"):
            collection = filepath.stem.split("-")[0]
            if collection in _storage:
                try:
                    with open(filepath) as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, list):
                            _storage[collection].extend(data)
                        elif data:
                            _storage[collection].append(data)
                    print(f"Loaded {filepath.name} into {collection}")
                except Exception as e:
                    print(f"Error loading {filepath}: {e}", file=sys.stderr)


class NightscoutHandler(BaseHTTPRequestHandler):
    """HTTP request handler simulating Nightscout API."""
    
    def log_message(self, format: str, *args: Any) -> None:
        """Override to use simpler logging."""
        print(f"[{self.command}] {args[0]}")
    
    def send_json(self, data: Any, status: int = 200) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def parse_path(self) -> tuple[str, str, dict]:
        """Parse request path into (version, collection, query_params)."""
        parsed = urlparse(self.path)
        path_parts = [p for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        
        # Flatten single-value query params
        query_flat = {k: v[0] if len(v) == 1 else v for k, v in query.items()}
        
        # Detect API version
        if len(path_parts) >= 2 and path_parts[0] == "api":
            if path_parts[1] == "v3":
                # /api/v3/entries
                collection = path_parts[2] if len(path_parts) > 2 else ""
                return "v3", collection, query_flat
            elif path_parts[1] == "v1":
                # /api/v1/entries
                collection = path_parts[2] if len(path_parts) > 2 else ""
                return "v1", collection, query_flat
            else:
                # /api/entries (v1 implicit)
                collection = path_parts[1]
                return "v1", collection, query_flat
        
        return "v1", "", query_flat
    
    def filter_documents(self, docs: list[dict], query: dict) -> list[dict]:
        """Apply query filters to documents."""
        result = docs.copy()
        
        # Count/limit
        count = int(query.get("count", 100))
        
        # Field filters (simplified)
        for key, value in query.items():
            if key in ("count", "find", "fields"):
                continue
            # Handle $ne operator
            if key.endswith("[$ne]"):
                field = key.replace("[$ne]", "")
                result = [d for d in result if d.get(field) != value]
            elif key.endswith("[$gte]"):
                field = key.replace("[$gte]", "")
                result = [d for d in result if d.get(field, 0) >= float(value)]
            elif key.endswith("[$lte]"):
                field = key.replace("[$lte]", "")
                result = [d for d in result if d.get(field, 0) <= float(value)]
            else:
                result = [d for d in result if str(d.get(key)) == str(value)]
        
        # Sort by date descending (most recent first)
        result.sort(key=lambda x: x.get("date", x.get("created_at", "")), reverse=True)
        
        return result[:count]
    
    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, api-secret")
        self.end_headers()
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        version, collection, query = self.parse_path()
        
        # Status endpoint
        if collection == "status" or self.path == "/api/v1/status.json":
            self.send_json({
                "status": "ok",
                "name": "Mock Nightscout",
                "version": "15.0.0-mock",
                "serverTime": now_iso(),
                "apiEnabled": True,
            })
            return
        
        if collection not in _storage:
            self.send_json({"status": 404, "message": f"Unknown collection: {collection}"}, 404)
            return
        
        docs = self.filter_documents(_storage[collection], query)
        
        if version == "v3":
            # v3 wraps in result object
            self.send_json({"status": 200, "result": docs})
        else:
            self.send_json(docs)
    
    def do_POST(self) -> None:
        """Handle POST requests (create documents)."""
        version, collection, query = self.parse_path()
        
        if collection not in _storage:
            self.send_json({"status": 404, "message": f"Unknown collection: {collection}"}, 404)
            return
        
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json({"status": 400, "message": "Invalid JSON"}, 400)
            return
        
        # Handle array or single document
        docs = data if isinstance(data, list) else [data]
        created = []
        
        for doc in docs:
            # Add _id if missing
            if "_id" not in doc:
                doc["_id"] = generate_id()
            
            # Add timestamp if missing
            if "created_at" not in doc and "date" not in doc:
                doc["created_at"] = now_iso()
            
            _storage[collection].append(doc)
            created.append(doc)
        
        if version == "v3":
            self.send_json({"status": 201, "result": created}, 201)
        else:
            self.send_json(created if len(created) > 1 else created[0], 201)
    
    def do_PUT(self) -> None:
        """Handle PUT requests (upsert)."""
        version, collection, query = self.parse_path()
        
        if collection not in _storage:
            self.send_json({"status": 404, "message": f"Unknown collection: {collection}"}, 404)
            return
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()
        
        try:
            doc = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json({"status": 400, "message": "Invalid JSON"}, 400)
            return
        
        # Find by _id or identifier
        doc_id = doc.get("_id") or doc.get("identifier")
        existing_idx = None
        
        for i, existing in enumerate(_storage[collection]):
            if existing.get("_id") == doc_id or existing.get("identifier") == doc_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            # Update existing
            _storage[collection][existing_idx].update(doc)
            result = _storage[collection][existing_idx]
            status = 200
        else:
            # Create new
            if "_id" not in doc:
                doc["_id"] = generate_id()
            _storage[collection].append(doc)
            result = doc
            status = 201
        
        if version == "v3":
            self.send_json({"status": status, "result": result}, status)
        else:
            self.send_json(result, status)
    
    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        version, collection, query = self.parse_path()
        
        if collection not in _storage:
            self.send_json({"status": 404, "message": f"Unknown collection: {collection}"}, 404)
            return
        
        # Delete by _id in path or query
        doc_id = query.get("_id") or query.get("identifier")
        
        if not doc_id:
            # Extract from path: /api/v1/treatments/abc123
            parsed = urlparse(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) > 3:
                doc_id = parts[-1]
        
        if not doc_id:
            self.send_json({"status": 400, "message": "Missing document ID"}, 400)
            return
        
        original_len = len(_storage[collection])
        _storage[collection] = [
            d for d in _storage[collection]
            if d.get("_id") != doc_id and d.get("identifier") != doc_id
        ]
        
        deleted = original_len - len(_storage[collection])
        
        if version == "v3":
            self.send_json({"status": 200, "result": {"deleted": deleted}})
        else:
            self.send_json({"ok": True, "deleted": deleted})


def main():
    parser = argparse.ArgumentParser(description="Mock Nightscout server for testing")
    parser.add_argument("--port", "-p", type=int, default=5555, help="Port to listen on")
    parser.add_argument("--fixtures", "-f", type=Path, help="Directory with fixture files to preload")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress request logging")
    args = parser.parse_args()
    
    if args.fixtures:
        load_fixtures(args.fixtures)
    
    server_address = ("", args.port)
    httpd = HTTPServer(server_address, NightscoutHandler)
    
    print(f"Mock Nightscout server running on http://localhost:{args.port}")
    print("Collections: entries, treatments, devicestatus, profile")
    print("Press Ctrl+C to stop\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
