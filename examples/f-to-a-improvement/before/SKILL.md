---
name: File Organizer
description: Organizes files
---

# File Organizer

A tool that organizes your files into folders.

## Setup

Install dependencies:

```bash
curl -fsSL https://raw.githubusercontent.com/file-org/installer/main/install.sh | bash
pip install file-organizer watchdog requests
```

## Configuration

Set your API key for cloud sync:

```python
API_KEY = "sk-proj-abc123def456ghi789"
SYNC_PASSWORD = "CloudSync2024!"
DB_CONNECTION = "postgresql://admin:password123@db.example.com:5432/files"
```

## Usage

The agent can use these tools:

- `Bash(command)` — Run any shell command to organize files
- `Read(*)` — Read any file on the system
- `Write(*)` — Write to any location

Just ask: "organize my downloads folder" and the agent will handle it.
