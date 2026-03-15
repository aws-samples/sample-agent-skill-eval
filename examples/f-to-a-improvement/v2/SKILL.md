---
name: file-organizer
description: Organizes files
---

# File Organizer

Sorts files into subdirectories by extension.

## Setup

```bash
pip install watchdog
```

## Usage

```bash
python scripts/organize.py /path/to/directory
python scripts/organize.py /path/to/directory --dry-run
```

## Tools

The agent needs these permissions:
- `Read(*)` — Read any file on the system
- `Write(*)` — Write to any location
- `Bash(command)` — Run shell commands
