---
name: file-organizer
description: |
  Organizes files in a directory by sorting them into subdirectories based on file extension.
  Supports dry-run preview, custom rules via config file, and undo via move log.
  Use when the user asks to organize, sort, or clean up files in a directory.
  NOT for: renaming files, deduplication, or managing cloud storage.
---

# File Organizer

Sorts files into subdirectories by extension. Supports dry-run mode, custom
rules, and undo.

## Usage

```bash
# Preview what would happen
python scripts/organize.py ~/Downloads --dry-run

# Organize files
python scripts/organize.py ~/Downloads

# Undo last organization
python scripts/organize.py ~/Downloads --undo
```

## Permissions

This skill needs access to the target directory only:

- `Read(<target_dir>/*)` — List files in the directory
- `Write(<target_dir>/*)` — Move files into subdirectories
- `Bash(python scripts/organize.py <target_dir> *)` — Run the organizer
