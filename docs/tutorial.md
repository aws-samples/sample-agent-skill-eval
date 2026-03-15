# Tutorial

This tutorial has two paths. Pick the one that matches your goal:

- **Path A** — [I want to evaluate a skill](#path-a-evaluating-a-skill) (consumer)
- **Path B** — [I am building a skill](#path-b-building-a-skill) (author)

Both paths use the built-in test fixtures so you can follow along without writing any code.

> **Want the full lifecycle in one walkthrough?** See [`examples/data-analysis/`](../examples/data-analysis/) for a complete, runnable demo that walks through every `skill-eval` command from audit to regression checking.

## Prerequisites

```bash
git clone https://github.com/melanie531/agent-skill-evaluation.git
cd agent-skill-evaluation
pip install -e .
```

Verify the install:

```bash
skill-eval --help
```

---

## Path A: Evaluating a Skill

You found a skill on a marketplace and want to know if it's safe and well-built.

### Step 1: Run an audit

```bash
skill-eval audit tests/fixtures/eval-skill
```

Expected output:

```
══════════════════════════════════════════════════════════
  Agent Skill Security Audit Report
══════════════════════════════════════════════════════════
  Skill:  eval-skill
  Path:   .../tests/fixtures/eval-skill
  Score:  100/100 (Grade: A)
──────────────────────────────────────────────────────────
  ✅ CRITICAL: 0 │ ⚠️  WARNING: 0 │ ℹ️  INFO: 0
──────────────────────────────────────────────────────────
  Result: ✅ PASSED (no critical findings)
══════════════════════════════════════════════════════════
```

This is a clean skill. Now try a bad one:

```bash
skill-eval audit tests/fixtures/bad-skill --verbose
```

You'll see findings like `SEC-001` (hardcoded secrets), `SEC-004` (curl|bash), `SEC-009` (MCP server references), and `PERM-001` (unrestricted Bash access). Each finding includes a severity, a description, and a suggested fix.

### Step 2: Understand the report

The audit report has three parts:

1. **Score & grade** — starts at 100, deducts per finding (CRITICAL: -25, WARNING: -10, INFO: -2). Grade A (90+) through F (<60).
2. **Finding summary** — count of critical/warning/info findings.
3. **Finding details** — each finding shows a code (e.g., `SEC-001`), the file and line, what was found, and how to fix it.

Key decision: a skill with **any CRITICAL findings** fails the audit. Do not install it without reviewing and fixing those issues.

### Step 3: Get the full picture with `report`

The audit only checks safety. For a complete evaluation that also tests functional quality and trigger reliability:

```bash
# Dry-run first to validate eval files exist
skill-eval report tests/fixtures/eval-skill --dry-run
```

For a live run (requires the Claude CLI):

```bash
skill-eval report tests/fixtures/eval-skill
```

The unified report produces a weighted grade: audit (40%) + functional (40%) + trigger (20%).

### Step 4: Suppress known-safe findings

If the skill uses a known-safe API domain, suppress the external URL findings:

```bash
skill-eval audit /path/to/skill --allowlist "api.weather.gov,wttr.in"
```

To suppress specific finding codes:

```bash
skill-eval audit /path/to/skill --ignore "STR-017,SEC-002"
```

### Step 5: Set up CI with GitHub Actions

Gate pull requests on audit results using the reusable workflow:

```yaml
# .github/workflows/skill-check.yml
name: Skill Check
on: [pull_request]

jobs:
  evaluate:
    uses: melanie531/agent-skill-evaluation/.github/workflows/skill-eval.yml@main
    with:
      skill_path: "path/to/your-skill"
      fail_on_warning: true
```

Or run audit directly:

```yaml
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install git+https://github.com/melanie531/agent-skill-evaluation.git
      - run: skill-eval audit ./my-skill --fail-on-warning
```

Exit codes: `0` = pass, `1` = warnings (with `--fail-on-warning`), `2` = critical findings.

---

## Path B: Building a Skill

You're writing a skill and want to set up evaluations.

### Step 1: Create your skill

Your skill needs a `SKILL.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: "Does something useful with data files."
license: MIT
---

# My Skill

Instructions for the agent go here...
```

### Step 2: Scaffold eval files with `init`

```bash
skill-eval init /path/to/my-skill
```

This reads your SKILL.md frontmatter and generates:

```
my-skill/
└── evals/
    ├── evals.json          # Functional eval cases
    └── eval_queries.json   # Trigger queries
```

The generated files contain template content based on your skill's name and description. If the files already exist, `init` skips them.

### Step 3: Customize eval cases

Edit `evals/evals.json` with real test cases. Each eval case has:

```json
[
  {
    "id": "unique-case-id",
    "prompt": "The task to give the agent",
    "expected_output": "Optional reference answer",
    "files": ["files/input.csv"],
    "assertions": [
      "contains 'expected text'",
      "does not contain 'error'",
      "matches regex /pattern/",
      "is valid JSON",
      "starts with '{'",
      "ends with '}'",
      "has at least 3 lines"
    ]
  }
]
```

Edit `evals/eval_queries.json` with trigger queries:

```json
[
  {"query": "A query that should activate my skill", "should_trigger": true},
  {"query": "A query that should NOT activate my skill", "should_trigger": false}
]
```

Aim for at least 2-3 should-trigger and 2-3 should-not-trigger queries.

### Step 4: Validate with dry-run

```bash
# Check eval cases parse correctly
skill-eval functional /path/to/my-skill --dry-run

# Check trigger queries parse correctly
skill-eval trigger /path/to/my-skill --dry-run
```

Dry-run validates the JSON structure without calling any agent CLI — no tokens spent.

### Step 5: Run live evaluations

```bash
# Functional evaluation — runs each case with and without your skill
skill-eval functional /path/to/my-skill --runs 3

# Trigger reliability — checks activation precision
skill-eval trigger /path/to/my-skill --runs 3
```

Functional evaluation runs each prompt twice per run: once with the skill installed and once without. The difference shows the skill's value-add.

Trigger evaluation sends each query multiple times and measures what percentage of runs correctly trigger (or don't trigger) the skill.

### Step 6: Interpret benchmark results

Functional evaluation writes `evals/benchmark.json` with four dimension scores:

- **Outcome** — assertion pass rate (did the agent produce correct output?)
- **Process** — tool usage efficiency (did the agent use tools appropriately?)
- **Style** — formatting quality (is the output well-structured?)
- **Efficiency** — tokens per passing assertion (cost-effectiveness)

Trigger evaluation reports:

- **Trigger rate** per query — what % of runs activated the skill
- **Pass/fail** per query — based on whether trigger rate meets the threshold

### Step 7: Set up CI to gate PRs

Combine audit + functional + trigger in CI:

```yaml
name: Skill Evaluation
on: [pull_request]

jobs:
  evaluate:
    uses: melanie531/agent-skill-evaluation/.github/workflows/skill-eval.yml@main
    with:
      skill_path: "."
      run_functional: true
      run_trigger: true
      fail_on_warning: true
```

This runs all three phases. The workflow outputs `passed`, `grade`, and `score` that you can use in subsequent jobs.

Alternatively, use the unified report command:

```bash
skill-eval report /path/to/my-skill --format json --output evals/report.json
```

### Step 8: Create a baseline and track regressions

Once your skill passes all evaluations:

```bash
# Save the current audit state
skill-eval snapshot /path/to/my-skill --version v1.0.0

# On future PRs, check for regressions
skill-eval regression /path/to/my-skill
```

---

## Built-in Fixtures Reference

The project includes test fixtures you can use for learning:

| Fixture | Path | Purpose |
|---------|------|---------|
| `data-analysis` | `examples/data-analysis/` | **Complete demo**: audit + evals + trigger + lifecycle. Score: 98/A |
| `eval-skill` | `tests/fixtures/eval-skill/` | Clean skill with eval files. Score: 100/A |
| `bad-skill` | `tests/fixtures/bad-skill/` | Intentionally insecure skill. Score: 0/F |

Explore them to understand what good and bad skills look like:

```bash
# Clean skill
skill-eval audit tests/fixtures/eval-skill --verbose

# Insecure skill
skill-eval audit tests/fixtures/bad-skill --verbose
```

## Next Steps

- Read [Core Concepts](concepts.md) for details on scoring, the AgentRunner abstraction, and eval file schemas
- Read [CONTRIBUTING.md](../CONTRIBUTING.md) to contribute new security checks or agent runners
- Check `references/security-checklist.md` for the OWASP LLM Top 10 mapping
