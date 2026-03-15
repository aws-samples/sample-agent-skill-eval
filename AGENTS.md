# AGENTS.md

Security and quality evaluation framework for Agent Skills. Python 3.10+, zero external deps for core audit; Claude CLI required for functional/trigger/compare/report.

## Project Overview

**Dual identity:** This project is both a CLI tool (`skill-eval`) and an Agent Skill (via `SKILL.md`). It evaluates other skills across safety, quality, reliability, and cost efficiency.

**Current state:** 9 commands, 505 tests, zero external dependencies in the core audit path.

**Key docs:**
- `SKILL.md` — Agent Skill manifest (triggers, commands, decision tree)
- `references/cli-reference.md` — Full CLI flag reference
- `references/security-checks.md` — All SEC/STR/PERM codes with OWASP mapping
- `references/security-checklist.md` — Quick-reference security checklist

## File Map

### Core (`skill_eval/`)

| File | Purpose |
|------|---------|
| `cli.py` | CLI entry point (`main()`). Parses args, dispatches to subcommands |
| `schemas.py` | `Finding`, `Severity`, `Category`, `AuditReport` dataclasses; `compute_score()`, `compute_grade()` |
| `eval_schemas.py` | Dataclasses for eval pipeline: `EvalCase`, `AssertionResult`, `GradingResult`, `RunPairResult`, `BenchmarkReport`, `TriggerQuery`, `TriggerQueryResult`, `TriggerReport`, `CompareReport` |
| `report.py` | Text and JSON report formatting for audit results |
| `unified_report.py` | Aggregates audit + functional + trigger -> weighted score (40/40/20) -> unified grade |
| `regression.py` | Baseline snapshots (`Snapshot` dataclass), version history, regression detection |
| `agent_runner.py` | `AgentRunner` ABC + `ClaudeRunner` implementation + `register_runner()`/`get_runner()` factory |
| `_claude.py` | Backward-compat wrapper delegating to `agent_runner`; `check_claude_available()`, `run_claude_prompt()` |
| `functional.py` | Functional eval orchestration: load evals -> run with/without skill -> grade -> `BenchmarkReport` |
| `grading.py` | Deterministic assertion grading (contains, regex, JSON, line count, etc.) + LLM fallback |
| `trigger.py` | Trigger eval: load queries -> run -> detect skill activation via stream-json -> `TriggerReport` |
| `compare.py` | Side-by-side comparison: runs same evals with two skills -> winner by tokens-per-pass |
| `init.py` | Scaffold generator: creates template `evals.json` + `eval_queries.json` from SKILL.md frontmatter |
| `lifecycle.py` | Version tracking and change detection for skills |

### Audit (`skill_eval/audit/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Package init |
| `structure_check.py` | Validates SKILL.md frontmatter, name/description fields, directory conventions (STR-xxx codes) |
| `security_scan.py` | SEC-001-009 detection: secrets, URLs, subprocess, installs, injection, deserialization, dynamic imports, base64, MCP refs |
| `permission_analyzer.py` | PERM-001-005: unscoped Bash, high-risk tools, tool count, sensitive dirs, sudo, absolute paths |

### Tests (`tests/`)

| File | Covers |
|------|--------|
| `test_cli.py` | Full audit pipeline, scoring, grade boundaries, report formatting |
| `test_structure_check.py` | Frontmatter parsing, YAML parser, name/description validation |
| `test_security_scan.py` | All SEC-001-009 patterns with positive and negative cases |
| `test_permission_analyzer.py` | PERM-001-005 detection |
| `test_regression.py` | Snapshots, regression detection, baseline lookup, edge cases |
| `test_eval_schemas.py` | Serialization roundtrips for all eval dataclasses |
| `test_functional.py` | Eval loading, math helpers, benchmark aggregation, dry-run, execute_eval_pair |
| `test_grading.py` | All deterministic graders + LLM fallback mocking |
| `test_trigger.py` | Query loading, trigger detection, report building, token tracking |
| `test_compare.py` | Compare pipeline, aggregation, winner determination |
| `test_init.py` | Scaffold generation, frontmatter parsing, skip-existing logic |
| `test_agent_runner.py` | AgentRunner ABC, ClaudeRunner methods, registry/factory |
| `test_unified_report.py` | Weighted scoring, grade boundaries, bar rendering, skip flags |
| `test_clawhub_fixtures.py` | Real ClawHub skills (weather, nano-pdf, slack) pass structure/security |
| `test_lifecycle.py` | Lifecycle version tracking and change detection |

### Fixtures (`tests/fixtures/`)

| Directory | Purpose |
|-----------|---------|
| `good-skill/` | Clean skill — passes all checks (score 100/A) |
| `bad-skill/` | Every anti-pattern — secrets, eval, pickle, MCP, unscoped Bash |
| `eval-skill/` | Functional eval fixture with `evals/evals.json` and `evals/eval_queries.json` |
| `mcp-skill/` | MCP server reference detection fixture |
| `no-frontmatter/` | Missing YAML frontmatter (error case) |
| `clawhub-skills/weather/` | Real ClawHub weather skill |
| `clawhub-skills/nano-pdf/` | Real ClawHub PDF processing skill |
| `clawhub-skills/slack/` | Real ClawHub Slack integration skill |

### Config & CI

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, entry point `skill-eval = skill_eval.cli:main`, dev deps |
| `.github/workflows/ci.yml` | Tests on Python 3.10 + 3.12, audit fixtures on push/PR |
| `.github/workflows/skill-eval.yml` | Reusable workflow for external repos |

## Architecture

### Key Design Decisions

- **Zero external dependencies** for the core audit path (audit, init, snapshot, regression, lifecycle). This means any agent can run security checks without installing anything beyond the stdlib.
- **AgentRunner ABC** (`agent_runner.py`) abstracts over CLI-based agents. `ClaudeRunner` is the default; new runners (e.g., for other agent CLIs) can be registered via `register_runner()` and used with `--agent`.
- **Pareto classification** in functional evals classifies cost-efficiency tradeoffs — a skill can be high quality but expensive, or cheap but lower quality.
- **Deterministic grading first** (`grading.py`) — uses contains/regex/JSON checks before falling back to LLM-based grading, keeping evals reproducible and fast.

### Entry Point

`skill_eval/cli.py:main()` -> argparse -> dispatches to subcommand handler.

### Audit Pipeline

```
cli.py:run_audit(path)
  -> structure_check.check_structure(path)     -> [Finding...]
  -> security_scan.scan_skill(path)            -> [Finding...]
  -> permission_analyzer.analyze_permissions(path) -> [Finding...]
  -> schemas.AuditReport(findings)             -> compute_score() -> compute_grade()
  -> report.format_report(report)              -> stdout (text or JSON)
```

### Functional Pipeline

```
functional.py:run_functional_eval(skill_path)
  -> load_evals(evals/evals.json)              -> [EvalCase...]
  -> for each eval, N runs:
      -> agent_runner.run_prompt(prompt, skill=None)   -> baseline output
      -> agent_runner.run_prompt(prompt, skill=path)   -> skill output
      -> grading.grade_output(output, assertions)      -> GradingResult
  -> aggregate_benchmark(results)              -> BenchmarkReport -> benchmark.json
```

### Trigger Pipeline

```
trigger.py:run_trigger_eval(skill_path)
  -> load_queries(evals/eval_queries.json)     -> [TriggerQuery...]
  -> for each query, N runs:
      -> agent_runner.run_prompt(query, skill=path)
      -> detect_skill_trigger(output, skill_name) -> bool
  -> build_trigger_report(results)             -> TriggerReport
```

### Unified Report Pipeline

```
unified_report.py:run_unified_report(skill_path)
  -> run_audit()       -> audit_score (weight 0.40)
  -> run_functional()  -> functional_score (weight 0.40)
  -> run_trigger()     -> trigger_score (weight 0.20)
  -> compute_weighted_score() -> overall grade
```

### Agent Runner Abstraction

```
AgentRunner (ABC)
  |-- check_available() -> bool
  |-- run_prompt(prompt, skill_path?, timeout?) -> (output, tokens)
  +-- parse_output(raw) -> (text, tool_calls, tokens)

ClaudeRunner(AgentRunner)     <- default, wraps `claude` CLI
register_runner(name, cls)    <- add custom runner
get_runner(name="claude")     <- factory
```

## Development Commands

```bash
pip install -e .                               # Install (no dev deps needed)
uv run --with pytest python -m pytest tests/ -q  # Run all 505 tests
pytest tests/test_security_scan.py             # Single module
pytest tests/ --cov=skill_eval                 # With coverage
skill-eval audit tests/fixtures/good-skill     # Smoke test (expect 100/A)
skill-eval audit tests/fixtures/bad-skill      # Expect 0/F
```

## Test Conventions

- Files: `tests/test_<module>.py`
- Style: unittest-style classes with pytest runner
- Fixtures: `tests/fixtures/` (good-skill, bad-skill, eval-skill, mcp-skill, clawhub-skills/)
- All mocked — no external deps needed to run the full suite

## Adding a New Security Rule

1. Add pattern to `skill_eval/audit/security_scan.py` (new `SEC-0XX` code)
2. Add matching content to `tests/fixtures/bad-skill/` (SKILL.md or scripts/)
3. Write tests in `tests/test_security_scan.py`
4. Update SKILL.md "What It Checks" section

## Adding a New Agent Runner

1. Subclass `AgentRunner` in `skill_eval/agent_runner.py`
2. Implement `check_available()`, `run_prompt()`, `parse_output()`
3. Call `register_runner("name", YourRunner)`
4. Use via `--agent name` CLI flag

## Code Style

- Python 3.10+ (use `from __future__ import annotations`)
- Type hints on all public functions
- Docstrings on public functions
- **Zero external dependencies** in core audit module — stdlib only
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `ci:`
- Branch naming: `feat/xxx` or `fix/xxx`
