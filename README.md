# Agent Skill Eval — Is That Skill Any Good?

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT-0](https://img.shields.io/badge/license-MIT--0-green.svg)](LICENSE)
[![Tests: 505](https://img.shields.io/badge/tests-505-brightgreen.svg)](tests/)

## What is this?

An evaluation framework for AI Agent Skills (the [agentskills.io](https://agentskills.io) standard).

It measures four dimensions:

- **Safety** — secrets, injection surfaces, unsafe installs, over-privileged permissions
- **Quality** — functional correctness (with-skill vs without-skill)
- **Reliability** — trigger precision (does the skill activate when it should?)
- **Cost Efficiency** — Pareto classification of cost vs quality tradeoffs

Plus: regression detection against versioned baselines, and lifecycle management for tracking skill changes over time.

Works with any skill that follows the Agent Skills format.

## Two ways to use it

### As a CLI tool (for humans)

```bash
pip install -e .
skill-eval audit /path/to/skill
skill-eval report /path/to/skill
```

### As an Agent Skill (for AI agents)

Skills are folders. Copy this repo to your agent's skill directory:

```bash
# Cross-client standard
cp -r agent-skill-evaluation ~/.agents/skills/skill-eval

# Or for Claude Code specifically
cp -r agent-skill-evaluation ~/.claude/skills/skill-eval
```

Your agent will discover it via `SKILL.md` and know how to run `skill-eval` commands.

> **Note:** The CLI tool must be installed first (`pip install -e .`).

## Quick Start

```bash
# Is this skill safe?
skill-eval audit /path/to/skill
# Score: 92/100 (Grade: A) — 0 criticals, 2 warnings

# Full evaluation with unified grade
skill-eval report /path/to/skill
# Unified Score: 88/100 (Grade: B)
# Audit: 92 (×0.40) | Functional: 85 (×0.40) | Trigger: 90 (×0.20)

# Generate eval scaffolds for a new skill
skill-eval init /path/to/skill
# Created evals/evals.json (3 template cases)
# Created evals/eval_queries.json (6 template queries)

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

Audit starts at 100. Deductions: **critical** -25, **warning** -10, **info** -2.

Grades: A (90+), B (80+), C (70+), D (60+), F (<60).

Unified report weights: audit 40%, functional 40%, trigger 20%.

## The Self-Eval Easter Egg

Running `skill-eval` on itself produces Grade F (60 criticals!) because our test fixtures intentionally contain every security anti-pattern we detect — secrets, `pickle.load`, `curl|bash`, `npx -y`. That's by design: you need bad examples to test a security scanner.

```bash
skill-eval audit .
# Score: 0/100 (Grade: F) — 60 criticals from test fixtures
# This proves the scanner works!
```

## Examples

| Example | What you'll learn |
|---------|-------------------|
| [Data Analysis](examples/data-analysis/) | Full lifecycle walkthrough — init, audit, functional, trigger, report |
| [F to A Improvement](examples/f-to-a-improvement/) | Fix a failing skill step by step |
| [Real Skill Audits](examples/real-skill-audits/) | Interpret audit reports for production skills |
| [Golden Eval Templates](examples/golden-evals/) | Write effective eval cases and trigger queries |

## Relationship to Anthropic skill-creator

These are complementary tools:

- **skill-creator** helps you _create_ skills (scaffolding, templates, best practices)
- **skill-eval** helps you _evaluate_ skills (security, quality, reliability, cost)

Workflow: create with skill-creator -> evaluate with skill-eval -> iterate -> deploy.

## CI/CD

```yaml
# .github/workflows/skill-eval.yml
jobs:
  evaluate:
    uses: melanie531/agent-skill-evaluation/.github/workflows/skill-eval.yml@main
    with:
      skill_path: "path/to/your-skill"
      run_functional: true
      run_trigger: true
```

Exit codes: `0` passed, `1` warnings/regressions/failures, `2` critical/error.

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
