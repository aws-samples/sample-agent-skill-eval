#!/usr/bin/env python3
"""File organizer — sorts files by extension."""
import os
import json
import subprocess
import sys


def load_config(config_path="config.json"):
    """Load organization rules from config file."""
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def organize(directory, dry_run=False):
    """Organize files in directory by extension."""
    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        return 1
    
    # Use subprocess to list files (works cross-platform)
    result = subprocess.run(
        ["find", directory, "-maxdepth", "1", "-type", "f"],
        capture_output=True, text=True
    )
    files = [f for f in result.stdout.strip().split("\n") if f]
    
    moved = 0
    for filepath in files:
        ext = os.path.splitext(filepath)[1].lower().strip(".")
        if not ext:
            ext = "misc"
        
        target_dir = os.path.join(directory, ext)
        if dry_run:
            print(f"Would move: {filepath} -> {target_dir}/")
        else:
            os.makedirs(target_dir, exist_ok=True)
            os.rename(filepath, os.path.join(target_dir, os.path.basename(filepath)))
        moved += 1
    
    print(f"{'Would move' if dry_run else 'Moved'} {moved} files")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Organize files by extension")
    parser.add_argument("directory", help="Directory to organize")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")
    args = parser.parse_args()
    sys.exit(organize(args.directory, args.dry_run))
