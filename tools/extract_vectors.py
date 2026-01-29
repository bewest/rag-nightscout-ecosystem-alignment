#!/usr/bin/env python3
"""
Extract conformance test vectors from AAPS replay test fixtures.

Usage:
    python3 tools/extract_vectors.py [--limit N] [--output DIR]
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Paths
WORKSPACE_ROOT = Path(__file__).parent.parent
AAPS_FIXTURES = WORKSPACE_ROOT / "externals/AndroidAPS/app/src/androidTest/assets/results"
OUTPUT_DIR = WORKSPACE_ROOT / "conformance/vectors"
SCHEMA_PATH = WORKSPACE_ROOT / "conformance/schemas/conformance-vector-v1.json"


def categorize_vector(aaps_data: dict) -> str:
    """Determine category based on algorithm output."""
    output = aaps_data.get("output", {})
    inp = aaps_data.get("input", {})
    
    glucose = inp.get("glucoseStatus", {}).get("glucose", 100)
    rate = output.get("rate", 0)
    smb = output.get("units", 0)  # SMB units field
    cob = output.get("COB", 0)
    meal_cob = inp.get("meal_data", {}).get("mealCOB", 0)
    max_iob = inp.get("profile", {}).get("max_iob", 0)
    iob = output.get("IOB", 0)
    
    # Categorization logic
    if glucose < 70:
        return "low-glucose-suspend"
    if smb and smb > 0:
        return "smb-delivery"
    if meal_cob > 0 or cob > 0:
        return "carb-absorption"
    if iob and max_iob and iob >= max_iob * 0.9:
        return "safety-limits"
    return "basal-adjustment"


def generate_assertions(aaps_data: dict) -> list:
    """Generate semantic assertions from output."""
    assertions = []
    output = aaps_data.get("output", {})
    inp = aaps_data.get("input", {})
    
    rate = output.get("rate")
    basal_rate = inp.get("profile", {}).get("current_basal", 1.0)
    max_basal = inp.get("profile", {}).get("max_basal", 4.0)
    
    if rate is not None:
        if rate == 0:
            assertions.append({"type": "rate_zero"})
        elif basal_rate and rate > basal_rate:
            assertions.append({"type": "rate_increased", "baseline": basal_rate})
        elif basal_rate and rate < basal_rate:
            assertions.append({"type": "rate_decreased", "baseline": basal_rate})
    
    # Check safety limits
    if rate is not None and max_basal:
        assertions.append({
            "type": "safety_limit",
            "field": "rate",
            "max": max_basal
        })
    
    # SMB assertions
    smb = output.get("units", 0)
    if smb and smb > 0:
        assertions.append({"type": "smb_delivered"})
    elif inp.get("microBolusAllowed"):
        assertions.append({"type": "no_smb"})
    
    return assertions


def convert_aaps_to_vector(aaps_data: dict, source_file: str, vector_id: int) -> dict:
    """Convert AAPS replay fixture to conformance vector format."""
    inp = aaps_data.get("input", {})
    output = aaps_data.get("output", {})
    
    glucose_status = inp.get("glucoseStatus", {})
    iob_data = inp.get("iob_data", [{}])
    if isinstance(iob_data, list) and len(iob_data) > 0:
        iob_data = iob_data[0]
    profile = inp.get("profile", {})
    meal_data = inp.get("meal_data", {})
    current_temp = inp.get("currenttemp", {})
    autosens = inp.get("autosens_data", {})
    
    category = categorize_vector(aaps_data)
    
    # Build normalized vector
    vector = {
        "version": "1.0.0",
        "metadata": {
            "id": f"TV-{vector_id:03d}",
            "name": f"AAPS replay {source_file}",
            "category": category,
            "source": f"aaps/replay/{source_file}",
            "description": f"Extracted from AAPS ReplayApsResultsTest fixture",
            "algorithm": aaps_data.get("algorithm", "OpenAPSSMBPlugin")
        },
        "input": {
            "glucoseStatus": {
                "glucose": glucose_status.get("glucose"),
                "glucoseUnit": "mg/dL",
                "delta": glucose_status.get("delta"),
                "shortAvgDelta": glucose_status.get("short_avgdelta"),
                "longAvgDelta": glucose_status.get("long_avgdelta"),
                "timestamp": datetime.fromtimestamp(
                    glucose_status.get("date", 0) / 1000, tz=timezone.utc
                ).isoformat().replace("+00:00", "Z") if glucose_status.get("date") else None,
                "noise": glucose_status.get("noise", 0)
            },
            "iob": {
                "iob": iob_data.get("iob"),
                "basalIob": iob_data.get("basaliob"),
                "bolusIob": iob_data.get("bolussnooze", 0),
                "activity": iob_data.get("activity"),
                "iobWithZeroTemp": iob_data.get("iobWithZeroTemp")
            },
            "profile": {
                "basalRate": profile.get("current_basal", 1.0),
                "sensitivity": profile.get("sens"),
                "carbRatio": profile.get("carb_ratio"),
                "targetLow": profile.get("min_bg"),
                "targetHigh": profile.get("max_bg"),
                "maxIob": profile.get("max_iob"),
                "maxBasal": profile.get("max_basal"),
                "dia": profile.get("dia", 5),
                "maxDailyBasal": profile.get("max_daily_basal")
            },
            "mealData": {
                "carbs": meal_data.get("carbs", 0),
                "cob": meal_data.get("mealCOB", 0),
                "lastCarbTime": meal_data.get("lastCarbTime"),
                "slopeFromMaxDeviation": meal_data.get("slopeFromMaxDeviation"),
                "slopeFromMinDeviation": meal_data.get("slopeFromMinDeviation")
            },
            "currentTemp": {
                "rate": current_temp.get("rate", 0),
                "duration": current_temp.get("duration", 0)
            },
            "autosensData": {
                "ratio": autosens.get("ratio", 1.0)
            },
            "microBolusAllowed": inp.get("microBolusAllowed", False),
            "flatBGsDetected": inp.get("flatBGsDetected", False)
        },
        "expected": {
            "rate": output.get("rate"),
            "duration": output.get("duration"),
            "eventualBG": output.get("eventualBG"),
            "insulinReq": output.get("insulinReq"),
            "cob": output.get("COB"),
            "iob": output.get("IOB")
        },
        "assertions": generate_assertions(aaps_data),
        "originalOutput": output
    }
    
    # Clean None values from expected
    vector["expected"] = {k: v for k, v in vector["expected"].items() if v is not None}
    
    return vector


def validate_vector(vector: dict) -> list:
    """Basic validation of extracted vector."""
    errors = []
    
    # Required fields
    if not vector.get("metadata", {}).get("id"):
        errors.append("Missing metadata.id")
    if not vector.get("input", {}).get("glucoseStatus", {}).get("glucose"):
        errors.append("Missing input.glucoseStatus.glucose")
    if not vector.get("input", {}).get("profile", {}).get("sensitivity"):
        errors.append("Missing input.profile.sensitivity")
    
    return errors


def main():
    parser = argparse.ArgumentParser(description="Extract conformance vectors from AAPS")
    parser.add_argument("--limit", type=int, default=50, help="Max vectors to extract")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output directory")
    parser.add_argument("--validate", action="store_true", help="Validate after extraction")
    args = parser.parse_args()
    
    if not AAPS_FIXTURES.exists():
        print(f"ERROR: AAPS fixtures not found at {AAPS_FIXTURES}")
        print("Run 'make bootstrap' to clone external repos")
        sys.exit(1)
    
    # Get fixture files
    fixture_files = sorted(AAPS_FIXTURES.glob("*.json"))[:args.limit]
    print(f"Found {len(fixture_files)} AAPS fixtures (limit: {args.limit})")
    
    # Track categories for distribution
    category_counts = {}
    extracted = []
    errors_count = 0
    
    for idx, fixture_path in enumerate(fixture_files, start=1):
        try:
            with open(fixture_path) as f:
                aaps_data = json.load(f)
            
            vector = convert_aaps_to_vector(
                aaps_data, 
                fixture_path.stem,
                idx
            )
            
            # Validate
            validation_errors = validate_vector(vector)
            if validation_errors:
                print(f"  WARN {fixture_path.name}: {validation_errors}")
                errors_count += 1
                continue
            
            # Save to category directory
            category = vector["metadata"]["category"]
            category_counts[category] = category_counts.get(category, 0) + 1
            
            out_dir = args.output / category
            out_dir.mkdir(parents=True, exist_ok=True)
            
            out_path = out_dir / f"{vector['metadata']['id']}-{fixture_path.stem}.json"
            with open(out_path, "w") as f:
                json.dump(vector, f, indent=2)
            
            extracted.append(out_path)
            
        except Exception as e:
            print(f"  ERROR {fixture_path.name}: {e}")
            errors_count += 1
    
    # Summary
    print(f"\nExtracted {len(extracted)} vectors ({errors_count} errors)")
    print("\nCategory distribution:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")
    
    print(f"\nOutput: {args.output}")
    
    if args.validate:
        print("\nValidating against schema...")
        try:
            import jsonschema
            with open(SCHEMA_PATH) as f:
                schema = json.load(f)
            
            valid = 0
            for vector_path in extracted:
                with open(vector_path) as f:
                    vector = json.load(f)
                try:
                    jsonschema.validate(vector, schema)
                    valid += 1
                except jsonschema.ValidationError as e:
                    print(f"  INVALID {vector_path.name}: {e.message}")
            
            print(f"Schema validation: {valid}/{len(extracted)} valid")
        except ImportError:
            print("  jsonschema not installed, skipping validation")


if __name__ == "__main__":
    main()
