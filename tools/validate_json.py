#!/usr/bin/env python3
"""
Enhanced JSON Schema Validator - validates JSON artifacts against schemas.

Supports:
- JSON Schema validation (specs/jsonschema/*.schema.json)
- Shape validation (specs/shape/*.shape.json - lightweight format)
- OpenAPI spec validation
- Fixture validation against schemas

Usage:
    # Validate all fixtures
    python tools/validate_json.py

    # Validate specific file
    python tools/validate_json.py --file data.json --schema schema.json

    # Validate fixtures directory
    python tools/validate_json.py --fixtures conformance/scenarios/

    # Check OpenAPI specs
    python tools/validate_json.py --openapi

    # JSON output
    python tools/validate_json.py --json

    # Verbose mode
    python tools/validate_json.py --verbose

For AI agents:
    # Validate before committing
    python tools/validate_json.py --json
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
SPECS_DIR = WORKSPACE_ROOT / "specs"
JSONSCHEMA_DIR = SPECS_DIR / "jsonschema"
SHAPE_DIR = SPECS_DIR / "shape"
OPENAPI_DIR = SPECS_DIR / "openapi"
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"
SCENARIOS_DIR = CONFORMANCE_DIR / "scenarios"

# Try to import jsonschema for full validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Try to import yaml for OpenAPI validation
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class ShapeValidator:
    """Lightweight validator for .shape.json files (no dependencies)."""
    
    def __init__(self, shape_spec):
        self.spec = shape_spec
    
    def validate(self, data):
        """Validate data against shape spec."""
        errors = []
        
        # Check required fields
        for field in self.spec.get("required_fields", []):
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Check enum values
        for field, allowed_values in self.spec.get("enums", {}).items():
            if field in data:
                value = data[field]
                if value not in allowed_values:
                    errors.append(f"Field '{field}' has invalid value '{value}'. Allowed: {allowed_values}")
        
        # Check timestamp fields are strings (basic check)
        for field in self.spec.get("timestamp_fields", []):
            if field in data:
                if not isinstance(data[field], str):
                    errors.append(f"Timestamp field '{field}' must be a string")
        
        # Check reference fields
        for field, ref_target in self.spec.get("reference_fields", {}).items():
            if field in data:
                if not isinstance(data[field], str):
                    errors.append(f"Reference field '{field}' must be a string ID")
        
        # Check nested shapes
        for field, nested_spec in self.spec.get("nested_shapes", {}).items():
            if field in data:
                nested_validator = ShapeValidator(nested_spec)
                nested_errors = nested_validator.validate(data[field])
                errors.extend([f"{field}.{e}" for e in nested_errors])
        
        return errors


def load_json_file(filepath):
    """Load JSON file with error handling."""
    try:
        with open(filepath) as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON syntax error: {e}"
    except Exception as e:
        return None, f"Error reading file: {e}"


def load_yaml_file(filepath):
    """Load YAML file with error handling."""
    if not HAS_YAML:
        return None, "PyYAML not available"
    
    try:
        with open(filepath) as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, f"Error reading YAML: {e}"


def validate_with_jsonschema(data, schema):
    """Validate using jsonschema library."""
    if not HAS_JSONSCHEMA:
        return ["jsonschema library not available - install with: pip install jsonschema"]
    
    try:
        jsonschema.validate(instance=data, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [f"Validation error: {e.message} at {'/'.join(str(p) for p in e.path)}"]
    except jsonschema.SchemaError as e:
        return [f"Schema error: {e.message}"]


def validate_with_shape(data, shape_spec):
    """Validate using lightweight shape spec."""
    validator = ShapeValidator(shape_spec)
    return validator.validate(data)


def validate_openapi_spec(filepath):
    """Validate OpenAPI specification."""
    data, error = load_yaml_file(filepath)
    
    if error:
        return [error]
    
    errors = []
    
    # Basic OpenAPI structure checks
    if not isinstance(data, dict):
        errors.append("OpenAPI spec must be an object")
        return errors
    
    if "openapi" not in data and "swagger" not in data:
        errors.append("Missing 'openapi' or 'swagger' version field")
    
    if "info" not in data:
        errors.append("Missing 'info' section")
    
    if "paths" not in data:
        errors.append("Missing 'paths' section")
    
    # Check paths are valid
    if "paths" in data:
        if not isinstance(data["paths"], dict):
            errors.append("'paths' must be an object")
        else:
            for path, methods in data["paths"].items():
                if not path.startswith("/"):
                    errors.append(f"Path '{path}' must start with '/'")
    
    return errors


def find_schema_for_file(filepath):
    """Try to find appropriate schema for a JSON file."""
    # Check if there's a matching .schema.json file
    schema_file = JSONSCHEMA_DIR / f"{filepath.stem}.schema.json"
    if schema_file.exists():
        return schema_file, "jsonschema"
    
    # Check for shape file
    shape_file = SHAPE_DIR / f"{filepath.stem}.shape.json"
    if shape_file.exists():
        return shape_file, "shape"
    
    # Try to infer from content
    data, _ = load_json_file(filepath)
    if data and isinstance(data, dict):
        # Check for type hints in the data
        if "type" in data:
            type_val = data["type"]
            schema_file = JSONSCHEMA_DIR / f"{type_val}.schema.json"
            if schema_file.exists():
                return schema_file, "jsonschema"
            
            shape_file = SHAPE_DIR / f"{type_val}.shape.json"
            if shape_file.exists():
                return shape_file, "shape"
    
    return None, None


def validate_file(filepath, schema_path=None, schema_type=None):
    """Validate a single JSON file."""
    result = {
        "file": str(filepath.relative_to(WORKSPACE_ROOT)),
        "valid": True,
        "errors": []
    }
    
    # Load the data file
    data, error = load_json_file(filepath)
    if error:
        result["valid"] = False
        result["errors"].append(error)
        return result
    
    # Find or use provided schema
    if schema_path is None:
        schema_path, schema_type = find_schema_for_file(filepath)
    
    if schema_path is None:
        result["warnings"] = ["No schema found for this file"]
        return result
    
    # Load the schema
    schema, error = load_json_file(schema_path)
    if error:
        result["valid"] = False
        result["errors"].append(f"Schema error: {error}")
        return result
    
    # Validate based on schema type
    if schema_type == "jsonschema":
        errors = validate_with_jsonschema(data, schema)
    elif schema_type == "shape":
        errors = validate_with_shape(data, schema)
    else:
        errors = ["Unknown schema type"]
    
    if errors:
        result["valid"] = False
        result["errors"] = errors
    
    return result


def validate_all_fixtures():
    """Validate all fixture files."""
    results = []
    
    if not SCENARIOS_DIR.exists():
        return results
    
    for json_file in SCENARIOS_DIR.rglob("*.json"):
        result = validate_file(json_file)
        results.append(result)
    
    return results


def validate_all_openapi():
    """Validate all OpenAPI specs."""
    results = []
    
    if not OPENAPI_DIR.exists():
        return results
    
    for yaml_file in OPENAPI_DIR.glob("*.yaml"):
        errors = validate_openapi_spec(yaml_file)
        results.append({
            "file": str(yaml_file.relative_to(WORKSPACE_ROOT)),
            "valid": len(errors) == 0,
            "errors": errors
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Validate JSON and YAML files against schemas")
    parser.add_argument("--file", help="Specific file to validate")
    parser.add_argument("--schema", help="Schema file to use")
    parser.add_argument("--fixtures", action="store_true", help="Validate all fixtures")
    parser.add_argument("--openapi", action="store_true", help="Validate OpenAPI specs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    results = []
    
    if args.file:
        filepath = Path(args.file)
        schema_path = Path(args.schema) if args.schema else None
        results = [validate_file(filepath, schema_path)]
    
    elif args.openapi:
        results = validate_all_openapi()
    
    elif args.fixtures:
        results = validate_all_fixtures()
    
    else:
        # Default: validate all
        results = validate_all_fixtures()
        results.extend(validate_all_openapi())
    
    # Output results
    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "valid": sum(1 for r in results if r["valid"]),
            "invalid": sum(1 for r in results if not r["valid"]),
            "results": results
        }
        print(json.dumps(output, indent=2))
    else:
        valid_count = sum(1 for r in results if r["valid"])
        invalid_count = sum(1 for r in results if not r["valid"])
        
        print(f"\nValidation Results: {valid_count} valid, {invalid_count} invalid")
        print("=" * 70)
        
        for result in results:
            if not result["valid"] or args.verbose:
                status = "✓" if result["valid"] else "✗"
                print(f"\n{status} {result['file']}")
                
                if result.get("errors"):
                    for error in result["errors"]:
                        print(f"  ERROR: {error}")
                
                if result.get("warnings"):
                    for warning in result["warnings"]:
                        print(f"  WARNING: {warning}")
        
        if invalid_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
