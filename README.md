# Agent Skill Eval — Is That Skill Any Good?

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT-0](https://img.shields.io/badge/license-MIT--0-green.svg)](LICENSE)
[![Tests: 621](https://img.shields.io/badge/tests-621-brightgreen.svg)](tests/)

An evaluation framework for AI Agent Skills ([agentskills.io](https://agentskills.io) standard). Measures safety, quality, reliability, and cost efficiency.

---

## Installation

There are two ways to use this project — pick the one that fits your workflow.

### Option A: CLI Tool (for developers)

Install it, run commands yourself, integrate into CI.

```bash
# Install from source
git clone https://github.com/aws-samples/sample-agent-skill-eval.git
cd sample-agent-skill-eval
pip install -e .

# Now use it
skill-eval audit /path/to/skill
skill-eval report /path/to/skill
```

**When to choose this:** You want to evaluate skills from the command line, integrate into CI/CD pipelines, or run batch evaluations.

### Option B: Agent Skill (for AI agents)

Let your AI agent discover and use skill-eval automatically.

```bash
# Cross-client standard (works with any agent that supports agentskills.io)
cp -r sample-agent-skill-eval ~/.agents/skills/skill-eval

# For Claude Code specifically
cp -r sample-agent-skill-eval ~/.claude/skills/skill-eval
```

Your agent discovers it via `SKILL.md` and knows how to run `skill-eval` commands when you ask things like "audit this skill" or "is this skill safe?"

> **Note:** The CLI tool must be installed first (`pip install -e .`). The Agent Skill is a wrapper that teaches the agent *how* to invoke the CLI.

**When to choose this:** You want your AI coding agent to evaluate skills as part of its workflow — e.g., "check this skill before I install it."

---

## What It Measures

| Dimension | What | How |
|-----------|------|-----|
| **Safety** | Secrets, injection surfaces, unsafe installs, over-privileged permissions | Static analysis (no agent needed) |
| **Quality** | Functional correctness — does the skill actually help? | With-skill vs without-skill comparison |
| **Reliability** | Trigger precision — does the skill activate when it should? | Relevant + irrelevant query testing |
| **Cost Efficiency** | Is the quality gain worth the token cost? | Pareto classification |

Plus: regression detection against versioned baselines, and lifecycle tracking.

---

## Quick Start

```bash
# Is this skill safe?
skill-eval audit /path/to/skill
# Score: 92/100 (Grade: A) — 0 criticals, 2 warnings

# Generate eval scaffolds for a new skill
skill-eval init /path/to/skill
# Created evals/evals.json (3 template cases)
# Created evals/eval_queries.json (6 template queries)

# Full evaluation with unified grade
skill-eval report /path/to/skill
# Unified Score: 88/100 (Grade: B)
# Audit: 92 (×0.40) | Functional: 85 (×0.40) | Trigger: 90 (×0.20)

# Check for regressions after changes
skill-eval snapshot /path/to/skill
skill-eval regression /path/to/skill
# No regressions detected (baseline: 92, current: 94)
```

## All Commands

| Command | What it does | Needs Claude CLI? |
|---------|-------------|:-----------------:|
| `audit` | Security & structure scan — score + grade | No |
| `init` | Generate template `evals.json` + `eval_queries.json` | No |
| `snapshot` | Save current audit as versioned baseline | No |
| `regression` | Compare current audit against baseline | No |
| `lifecycle` | Track skill versions and detect changes | No |
| `functional` | Run eval cases with/without skill, grade assertions | Yes |
| `trigger` | Test skill activation for relevant/irrelevant queries | Yes |
| `compare` | Side-by-side comparison of two skills | Yes |
| `report` | Unified report: audit + functional + trigger — weighted grade | Yes |

### Scoring

Audit starts at 100. Deductions: **critical** −25, **warning** −10, **info** −2.

Grades: A (90+), B (80+), C (70+), D (60+), F (<60).

Unified report weights: audit 40%, functional 40%, trigger 20%.

---

## Scan Scope

By default, `skill-eval audit` only scans **skill-standard directories**: root-level files (SKILL.md, etc.), `scripts/`, and `agents/`. This matches the [agentskills.io](https://agentskills.io) definition of what constitutes a skill's content.

Directories like `tests/`, `examples/`, `references/`, and `docs/` are excluded because they may contain documentation or test fixtures that *describe* security anti-patterns without actually being vulnerable.

Use `--include-all` to scan the entire directory tree:

```bash
# Default: scan skill content only
skill-eval audit /path/to/skill

# Full: scan everything (useful for full repo security review)
skill-eval audit /path/to/skill --include-all
```

### Self-Eval: Why This Matters

Running `skill-eval` on itself demonstrates the difference:

```bash
# Default scan — only skill content (SKILL.md, scripts/)
skill-eval audit .
# Score: 96/100 (Grade: A) — 0 criticals, 0 warnings, 2 infos

# Full scan — includes test fixtures with intentional anti-patterns
skill-eval audit . --include-all
# Score: 0/100 (Grade: F) — 60+ criticals from tests/fixtures/
# That's by design: you need bad examples to test a security scanner
```

---

## Examples

| Example | What you'll learn |
|---------|-------------------|
| [Data Analysis](examples/data-analysis/) | Full lifecycle walkthrough — init, audit, functional, trigger, report |
| [Lifecycle Demo](examples/lifecycle-demo/) | Three-version evolution (F→A→D) showing audit, functional, and regression detection |
| [Golden Dataset](examples/golden-dataset/) | Ground-truth skills for validating the evaluation framework itself |
| [F to A Improvement](examples/f-to-a-improvement/) | Fix a failing skill step by step |
| [Self-Eval](examples/self-eval/) | Default vs `--include-all` scan scope on this repo |
| [Real Skill Audits](examples/real-skill-audits/) | Interpret audit reports for production skills |
| [Golden Eval Templates](examples/golden-evals/) | Write effective eval cases and trigger queries |

---

## Relationship to Anthropic skill-creator

These are complementary tools:

- **skill-creator** helps you _create_ skills (scaffolding, templates, best practices)
- **skill-eval** helps you _evaluate_ skills (security, quality, reliability, cost)

Workflow: create with skill-creator → evaluate with skill-eval → iterate → deploy.

---

## CI/CD

```yaml
# .github/workflows/skill-eval.yml
jobs:
  evaluate:
    uses: aws-samples/sample-agent-skill-eval/.github/workflows/skill-eval.yml@main
    with:
      skill_path: "path/to/your-skill"
      run_functional: true
      run_trigger: true
```

Exit codes: `0` passed, `1` warnings/regressions/failures, `2` critical/error.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR workflow.

## Links

- [agentskills.io](https://agentskills.io) — Agent Skills specification
- [Anthropic Skills](https://github.com/anthropics/skills) — official skill collection
- [OWASP Top 10 for LLMs](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [ClawHub](https://clawhub.com) — Agent Skills marketplace

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
