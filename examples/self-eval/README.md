# Self-Eval Example

Running `skill-eval` on itself demonstrates how scan scope affects results.

## Default Scan (Skill Content Only)

By default, `skill-eval audit` only scans skill-standard directories:
- Root-level files (SKILL.md, README.md, etc.)
- `scripts/` (executable code)
- `agents/` (agent configurations)

This means `tests/`, `examples/`, `references/`, and `docs/` are **excluded** — they're not part of the skill's executable content.

```bash
cd /path/to/agent-skill-evaluation
skill-eval audit .
```

Expected output:
```
Score: 96/100 (Grade: A) — 0 criticals, 0 warnings, 2 infos
```

The infos are:
- STR-008: directory name `agent-skill-evaluation` doesn't match frontmatter name `skill-eval` (expected for dual-identity project)
- STR-016: README.md present alongside SKILL.md (expected for a project that's both CLI tool and skill)

No security findings — the actual skill code is clean.

## Full Scan (`--include-all`)

Use `--include-all` to scan the entire directory tree:

```bash
skill-eval audit . --include-all
```

Expected output:
```
Score: 0/100 (Grade: F) — 60+ criticals
```

The criticals come from `tests/fixtures/` — intentional security anti-patterns used to test the scanner:
- `tests/fixtures/bad-skill/` contains secrets, `pickle.load`, `curl|bash`, `npx -y`
- `tests/fixtures/mcp-skill/` contains MCP server references

**This is by design.** You need bad examples to test a security scanner. The test fixtures prove the scanner works.

## Why This Matters

If a skill marketplace or CI pipeline uses `skill-eval` to gate skills, the **default scan** correctly evaluates the skill itself — not its test infrastructure. The `--include-all` flag is for full repo security audits where you want to catch everything.

This applies to any skill that has test fixtures: without scoped scanning, a well-tested skill could score poorly because its tests intentionally contain anti-patterns.

## Key Flags

| Flag | Effect |
|------|--------|
| (default) | Scan root files + `scripts/` + `agents/` only |
| `--include-all` | Scan entire directory tree |
| `--ignore SEC-002` | Suppress specific finding codes |
| `--allowlist api.example.com` | Treat domains as safe |
