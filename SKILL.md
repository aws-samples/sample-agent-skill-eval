---
name: skill-eval
description: "Evaluate AI Agent Skills across safety, quality, reliability, and cost efficiency. Audit for security issues (secrets, injection, unsafe installs), test functional correctness with-skill vs without-skill, measure trigger precision, classify cost-efficiency tradeoffs, track version lifecycle, and generate unified grades. Use when evaluating a skill before installing, auditing marketplace skills, proving your skill works with automated tests, setting up CI/CD quality gates, or comparing two skill versions. NOT for: evaluating full agent systems, testing non-skill plugins, runtime performance benchmarking, or monitoring production agent behavior."
---

# Skill Eval — Agent Skill Evaluation Framework

Evaluate Agent Skills across four dimensions: safety (audit), quality (functional), reliability (trigger), and cost efficiency (Pareto classification).

## Quick Start

```bash
skill-eval audit /path/to/skill          # Is it safe?
skill-eval report /path/to/skill         # Full grade (audit + functional + trigger)
skill-eval functional /path/to/skill     # Quality: with-skill vs without-skill
skill-eval trigger /path/to/skill        # Reliability: activation precision
```

## Decision Tree

- **"Is this skill safe?"** → `skill-eval audit <path>`
- **"Full evaluation with grade"** → `skill-eval report <path>`
- **"Write eval cases"** → `skill-eval init <path>`, then edit `evals/`
- **"Compare two versions"** → `skill-eval compare <old> <new>`
- **"Check for regressions"** → `skill-eval snapshot <path>`, then `skill-eval regression <path>`
- **"Track changes"** → `skill-eval lifecycle <path> --save --label v1.0`

## Commands

| Command | Purpose |
|---------|---------|
| `audit` | Security & structure scan (secrets, permissions, spec compliance) |
| `functional` | Quality eval — runs prompts with and without skill, grades output |
| `trigger` | Reliability eval — tests activation precision for relevant/irrelevant queries |
| `report` | Unified grade combining audit (40%) + functional (40%) + trigger (20%) |
| `compare` | Side-by-side comparison of two skills on the same eval cases |
| `snapshot` | Save current audit as regression baseline |
| `regression` | Check for score regressions against baseline |
| `lifecycle` | Version tracking and change detection |
| `init` | Generate eval scaffold from SKILL.md frontmatter |

For detailed flags and examples, see `references/cli-reference.md`.

## Eval File Format

Functional evals (`evals/evals.json`):
```json
[{"id": "case-1", "prompt": "...", "assertions": ["contains 'expected'"], "files": ["files/input.csv"]}]
```

Trigger queries (`evals/eval_queries.json`):
```json
[{"query": "relevant question", "should_trigger": true}, {"query": "unrelated question", "should_trigger": false}]
```

## Scoring

Grades: A (90+), B (80-89), C (70-79), D (60-69), F (<60). Findings deduct: CRITICAL −25, WARNING −10, INFO −2.

For the full security check reference and OWASP mapping, see `references/security-checks.md`.
