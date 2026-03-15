#!/usr/bin/env python3
"""Analyze a CSV file and produce summary statistics.

Usage:
    python3 analyze_csv.py <file.csv>

Outputs JSON with:
- row_count, column_count
- columns: list of {name, dtype, non_null, unique_count}
- numeric_stats: {column: {min, max, mean, median, std}}
- anomalies: list of {column, row, value, reason}
"""

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path


def _is_numeric(value: str) -> bool:
    """Check if a string can be parsed as a number."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def _median(values: list[float]) -> float:
    """Compute median of a sorted list."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]


def _stddev(values: list[float]) -> float:
    """Compute population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def analyze(filepath: str) -> dict:
    """Analyze a CSV file and return structured statistics."""
    path = Path(filepath)
    if not path.is_file():
        return {"error": f"File not found: {filepath}"}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {"error": "No headers found in CSV"}

        columns = list(reader.fieldnames)
        rows = list(reader)

    row_count = len(rows)
    column_count = len(columns)

    # Column analysis
    col_info = []
    numeric_cols: dict[str, list[float]] = {}

    for col in columns:
        values = [r[col] for r in rows]
        non_null = [v for v in values if v.strip()]
        unique = set(non_null)

        # Detect type
        numeric_values = [float(v) for v in non_null if _is_numeric(v)]
        if len(numeric_values) > len(non_null) * 0.8:
            dtype = "numeric"
            numeric_cols[col] = numeric_values
        else:
            dtype = "string"

        col_info.append({
            "name": col,
            "dtype": dtype,
            "non_null": len(non_null),
            "unique_count": len(unique),
        })

    # Numeric statistics
    numeric_stats = {}
    for col, vals in numeric_cols.items():
        mean = sum(vals) / len(vals)
        std = _stddev(vals)
        numeric_stats[col] = {
            "min": min(vals),
            "max": max(vals),
            "mean": round(mean, 2),
            "median": round(_median(vals), 2),
            "std": round(std, 2),
        }

    # Anomaly detection (beyond 2 std devs)
    anomalies = []
    for col, vals in numeric_cols.items():
        mean = sum(vals) / len(vals)
        std = _stddev(vals)
        if std == 0:
            continue
        for i, row in enumerate(rows):
            v = row[col]
            if _is_numeric(v):
                fv = float(v)
                if abs(fv - mean) > 2 * std:
                    anomalies.append({
                        "column": col,
                        "row": i + 1,
                        "value": fv,
                        "reason": f"{'above' if fv > mean else 'below'} 2 std devs (mean={mean:.2f}, std={std:.2f})",
                    })

    return {
        "file": str(path.name),
        "row_count": row_count,
        "column_count": column_count,
        "columns": col_info,
        "numeric_stats": numeric_stats,
        "anomalies": anomalies[:20],  # Cap at 20
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_csv.py <file.csv>", file=sys.stderr)
        sys.exit(1)

    result = analyze(sys.argv[1])
    print(json.dumps(result, indent=2))
