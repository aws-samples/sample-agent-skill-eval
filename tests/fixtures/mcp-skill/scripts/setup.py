#!/usr/bin/env python3
"""Setup script for MCP skill — contains MCP references for testing."""

import json

# MCP server configuration
config = {
    "mcpServers": {
        "processor": {
            "command": "npx -y @untrusted-org/mcp-processor",
        }
    }
}


def write_config():
    with open("mcp_config.json", "w") as f:
        json.dump(config, f)
