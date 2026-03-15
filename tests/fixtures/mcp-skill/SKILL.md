---
name: mcp-skill
description: A skill that references external MCP servers for testing SEC-009 detection.
allowed-tools: Bash Read
---

# MCP Skill

This skill connects to external MCP servers for data processing.

## Setup

Configure MCP servers in your settings:

```json
{
  "mcpServers": {
    "data-processor": {
      "command": "npx -y @untrusted-org/mcp-data-tool",
      "args": ["--port", "3000"]
    },
    "analytics": {
      "url": "https://analytics.example.net/sse"
    }
  }
}
```

You can also use the Python MCP config:

```python
mcp_servers = {
    "remote": "https://remote-mcp.example.net/mcp"
}
```

## Usage

1. Start the MCP server
2. Connect to it
3. Use the tools it provides
