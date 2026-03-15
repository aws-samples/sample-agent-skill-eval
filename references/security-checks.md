# Security Checks Reference

## What It Checks

### Structure (STR-xxx)
- SKILL.md exists with valid YAML frontmatter
- `name` field: format, length, matches directory name
- `description` field: present, adequate length
- Progressive disclosure: SKILL.md size within recommendations
- README.md conflicts

### Security (SEC-xxx)
- **SEC-001**: Hardcoded secrets (API keys, tokens, passwords, private keys, connection strings)
- **SEC-002**: External URLs (data exfiltration risk surface)
- **SEC-003**: Subprocess/shell execution patterns
- **SEC-004**: Unsafe dependency installation (curl|bash, unpinned pip install)
- **SEC-005**: Prompt injection surface in instructions
- **SEC-006**: Unsafe deserialization (pickle, yaml.load without SafeLoader, marshal, shelve)
- **SEC-007**: Dynamic import/code generation (importlib, \_\_import\_\_, compile, types.FunctionType, types.CodeType)
- **SEC-008**: Base64 encoded payloads (critical when combined with eval/exec)
- **SEC-009**: MCP server references (mcpServers config blocks, npx -y external packages, SSE endpoints)

### Permissions (PERM-xxx)
- **PERM-001**: Unrestricted Bash/Shell access
- **PERM-002**: High-risk tool declarations
- **PERM-003**: Excessive number of tools
- **PERM-004**: Instructions referencing sensitive directories, sudo, credentials
- **PERM-005**: Absolute system path references

## Severity Levels

- **CRITICAL**: Must fix. Blocks CI. Score −25 per finding.
- **WARNING**: Should fix. Score −10 per finding.
- **INFO**: Nice to fix. Score −2 per finding.

## Score & Grades

| Grade | Score | Meaning |
|-------|-------|---------|
| A | 90-100 | Excellent — safe to install |
| B | 80-89 | Good — minor issues |
| C | 70-79 | Fair — review findings |
| D | 60-69 | Poor — significant issues |
| F | 0-59 | Fail — do not install without review |

## References

- Read `references/security-checklist.md` for the full OWASP LLM Top 10 mapping
- Based on the [agentskills.io specification](https://agentskills.io/specification)
- Complements [Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) eval
