#!/usr/bin/env python3
"""A sample script that does safe operations."""

import sys
import json
from pathlib import Path


def process(input_path: str) -> dict:
    """Process the input file."""
    data = Path(input_path).read_text()
    return {"status": "ok", "length": len(data)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: process.py <input_file>")
        sys.exit(1)
    result = process(sys.argv[1])
    print(json.dumps(result, indent=2))
