# CLI Reference

Complete command reference for `skill-eval`.

## `audit` — Security & Quality Audit

```bash
# Basic audit
skill-eval audit /path/to/skill

# JSON output for CI/CD
skill-eval audit /path/to/skill --format json

# Suppress noise
skill-eval audit /path/to/skill \
  --ignore STR-017,SEC-002 \
  --allowlist api.yahoo.com,wttr.in

# Batch audit
skill-eval audit skill1/ skill2/ skill3/ --quiet

# CI mode (fail on warnings)
skill-eval audit /path/to/skill --fail-on-warning

# Full directory scan (includes tests/, examples/, docs/, etc.)
skill-eval audit /path/to/skill --include-all
```

By default, audit scans only skill-standard directories (root files, `scripts/`, `agents/`). Use `--include-all` to scan the entire directory tree.

Exit codes: `0` = passed, `1` = warnings (with `--fail-on-warning`), `2` = critical findings.

## `init` — Generate Eval Scaffolds

```bash
skill-eval init /path/to/skill
```

Reads SKILL.md frontmatter and generates template files in `evals/`:
- `evals/evals.json` — functional eval cases with placeholder prompts and assertions
- `evals/eval_queries.json` — trigger queries with should-trigger/should-not-trigger examples

Skips files that already exist.

## `report` — Unified Evaluation Report

```bash
# Full evaluation (audit + functional + trigger)
skill-eval report /path/to/skill

# JSON output
skill-eval report /path/to/skill --format json

# Skip specific phases
skill-eval report /path/to/skill --skip-functional
skill-eval report /path/to/skill --skip-trigger
skill-eval report /path/to/skill --skip-audit

# Custom output path
skill-eval report /path/to/skill --output results/report.json --format json
```

Runs all applicable evaluation phases, computes a weighted overall score (audit 40%, functional 40%, trigger 20%), and outputs a combined report. Phases without eval files are automatically skipped and their weight redistributed.

## `snapshot` — Save Baseline

```bash
skill-eval snapshot /path/to/skill --version v1.0.0
```

Saves current audit results to `evals/baselines/v1.0.0/` inside the skill directory.

## `regression` — Check for Regressions

```bash
skill-eval regression /path/to/skill
```

Compares current audit against the latest baseline. Fails if new critical findings appear or score drops significantly.

Exit codes: `0` = no regressions, `1` = regression detected, `2` = baseline not found.

## `functional` — Functional Quality Evaluation

```bash
# Dry-run: validate evals.json without calling Claude
skill-eval functional /path/to/skill --dry-run

# Single run per eval case
skill-eval functional /path/to/skill --runs 1

# Multiple runs with JSON output
skill-eval functional /path/to/skill --runs 3 --format json

# Custom evals file and output path
skill-eval functional /path/to/skill --evals custom/evals.json --output results/benchmark.json

# Use a different agent runner
skill-eval functional /path/to/skill --agent claude --runs 1
```

Runs each eval case from `evals/evals.json` with and without the skill installed. Each case has an `id`, `prompt`, optional `files` to copy into the workspace, and `assertions` to grade the output.

Assertion types: `contains`, `does not contain`, `matches regex`, `is valid JSON`, `starts with`, `ends with`, `has at least N lines`, and free-form semantic assertions (graded by LLM).

Exit codes: `0` = skill meets quality bar, `1` = skill underperforms, `2` = error.

## `trigger` — Trigger Reliability Evaluation

```bash
# Dry-run: validate eval_queries.json
skill-eval trigger /path/to/skill --dry-run

# Run each query 3 times
skill-eval trigger /path/to/skill --runs 3

# JSON output
skill-eval trigger /path/to/skill --format json
```

Tests whether the skill activates for relevant queries and stays silent for irrelevant ones. Each query in `evals/eval_queries.json` has a `query` string and `should_trigger` boolean.

Exit codes: `0` = all queries passed, `1` = one or more failed, `2` = error.

## `compare` — Side-by-Side Skill Comparison

```bash
# Dry-run
skill-eval compare /path/to/skill-a /path/to/skill-b --dry-run

# Compare two skills
skill-eval compare /path/to/skill-a /path/to/skill-b --runs 1

# Custom evals and JSON output
skill-eval compare /path/to/skill-a /path/to/skill-b \
  --evals shared/evals.json --format json --output compare-report.json
```

Runs the same eval cases with both skills, compares pass rates and token usage, and determines a winner.

## `lifecycle` — Version Tracking

```bash
# Save current state
skill-eval lifecycle /path/to/skill --save --label v1.0

# Check for changes
skill-eval lifecycle /path/to/skill
```

Detects changes to SKILL.md, scripts, and eval files between saved versions.

## `--agent` Parameter

The `functional`, `trigger`, and `compare` commands accept `--agent <name>` to select which agent CLI to use. Default: `claude`.

Custom runners can be registered via `register_runner("name", YourRunnerClass)` in `skill_eval/agent_runner.py`.
