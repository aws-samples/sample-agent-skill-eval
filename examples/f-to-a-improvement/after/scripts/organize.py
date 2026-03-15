#!/usr/bin/env python3
"""File organizer — sorts files by extension with dry-run and undo support."""
import argparse
import json
import os
import sys
from pathlib import Path


LOG_FILE = ".organize_log.json"


def load_config(directory: str) -> dict:
    """Load custom organization rules from config.json if present."""
    config_path = Path(directory) / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {}


def organize(directory: str, dry_run: bool = False) -> int:
    """Organize files in directory by extension.
    
    Args:
        directory: Path to the directory to organize.
        dry_run: If True, only preview changes without moving files.
        
    Returns:
        0 on success, 1 on error.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        print(f"Error: {directory} is not a valid directory", file=sys.stderr)
        return 1

    config = load_config(directory)
    custom_rules = config.get("rules", {})
    
    files = [f for f in dir_path.iterdir() if f.is_file() and f.name != LOG_FILE]
    
    if not files:
        print("No files to organize.")
        return 0
    
    moves = []
    for filepath in sorted(files):
        ext = filepath.suffix.lower().lstrip(".")
        if not ext:
            ext = "misc"
        
        # Apply custom rules if configured
        target_name = custom_rules.get(ext, ext)
        target_dir = dir_path / target_name
        
        if dry_run:
            print(f"  {filepath.name} -> {target_name}/")
        else:
            target_dir.mkdir(exist_ok=True)
            dest = target_dir / filepath.name
            filepath.rename(dest)
            moves.append({"from": str(dest), "to": str(filepath)})
    
    if not dry_run and moves:
        log_path = dir_path / LOG_FILE
        with open(log_path, "w") as f:
            json.dump(moves, f, indent=2)
    
    action = "Would move" if dry_run else "Moved"
    print(f"{action} {len(files)} files into {len(set(f.suffix for f in files))} categories.")
    return 0


def undo(directory: str) -> int:
    """Undo the last organization using the move log."""
    log_path = Path(directory) / LOG_FILE
    if not log_path.exists():
        print("No organization log found. Nothing to undo.", file=sys.stderr)
        return 1
    
    with open(log_path) as f:
        moves = json.load(f)
    
    for move in moves:
        src = Path(move["from"])
        dst = Path(move["to"])
        if src.exists():
            dst.parent.mkdir(exist_ok=True)
            src.rename(dst)
    
    log_path.unlink()
    print(f"Undone {len(moves)} moves.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Organize files by extension")
    parser.add_argument("directory", help="Directory to organize")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without moving files")
    parser.add_argument("--undo", action="store_true",
                        help="Undo the last organization")
    args = parser.parse_args()

    if args.undo:
        return undo(args.directory)
    return organize(args.directory, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
