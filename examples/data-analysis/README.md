# Data Analysis Skill — End-to-End Lifecycle Walkthrough

This is a complete, runnable example skill. Follow along step by step to see every `skill-eval` command in action.

## What's in This Skill

```
data-analysis/
├── SKILL.md                     # Skill definition (Anthropic standard)
├── scripts/
│   └── analyze_csv.py           # Deterministic analysis helper
├── evals/
│   ├── evals.json               # 6 functional eval cases
│   ├── eval_queries.json        # 10 trigger queries (5 pos + 5 neg)
│   └── files/
│       └── sales.csv            # Sample dataset (20 rows)
└── README.md                    # This file
```

## Prerequisites

```bash
cd agent-skill-evaluation
pip install -e .
skill-eval --help
```

---

## Step 1: Audit the Skill

Check for security issues, structure problems, and permission risks.

```bash
skill-eval audit examples/data-analysis
```

Expected output:

```
══════════════════════════════════════════════════════════
  Agent Skill Security Audit Report
══════════════════════════════════════════════════════════
  Skill:  data-analysis
  Path:   examples/data-analysis
  Score:  98/100 (Grade: A)
──────────────────────────────────────────────────────────
  ✅ CRITICAL: 0 │ ⚠️  WARNING: 0 │ ℹ️  INFO: 1
──────────────────────────────────────────────────────────
  Result: ✅ PASSED (no critical findings)
══════════════════════════════════════════════════════════
```

**What this tells you:** The skill has no secrets, no dangerous patterns, and proper structure. The 1 INFO finding is `STR-016` (README.md alongside SKILL.md) — expected and harmless for a demo.

## Step 2: Validate Eval Cases (Dry Run)

Check that your `evals.json` and `eval_queries.json` are valid before spending tokens.

```bash
# Functional evals
skill-eval functional examples/data-analysis --dry-run

# Trigger queries
skill-eval trigger examples/data-analysis --dry-run
```

Expected output shows 6 eval cases and 10 trigger queries loaded without errors.

**What this tells you:** Your eval files parse correctly, assertions are well-formed, and test files exist.

## Step 3: Run the Unified Report

The unified report runs audit + functional + trigger evaluations and computes a weighted grade.

```bash
# Audit-only (no Claude CLI needed):
skill-eval report examples/data-analysis --skip-functional --skip-trigger

# Full report (requires Claude CLI):
# skill-eval report examples/data-analysis
```

Expected output (audit-only):

```
═══════════════════════════════════════════
  Unified Skill Report
═══════════════════════════════════════════
  Skill: data-analysis
  Overall Grade: A (0.98)
───────────────────────────────────────────
  Audit:      98/100 (A)  █████████▒
───────────────────────────────────────────
  Result: PASSED
═══════════════════════════════════════════
```

**What this tells you:** The overall grade combines audit (40%), functional (40%), and trigger (20%). Skipped components have their weight redistributed.

## Step 4: Save a Baseline Snapshot

Before making changes, save the current audit as a baseline for regression checks.

```bash
skill-eval snapshot examples/data-analysis
```

Expected output:

```
✅ Snapshot saved: examples/data-analysis/evals/baselines/v20260315-...
   Score: 98/A | Findings: 1 (C:0 W:0 I:1)
```

**What this tells you:** You now have a reference point. Any future changes that introduce new findings will be flagged.

## Step 5: Track Versions with Lifecycle

Pin the current state as a named version.

```bash
skill-eval lifecycle examples/data-analysis --save --label v1.0
```

Expected output:

```
Version saved: v1.0 (2cfe7ed02ace...)
```

Check for changes (there should be none):

```bash
skill-eval lifecycle examples/data-analysis
```

Expected output:

```
No changes detected.
```

**What this tells you:** Lifecycle tracking detects when SKILL.md, scripts, or eval files change between versions. Useful for CI/CD.

## Step 6: Make a Change and Detect It

Now simulate a real development cycle. Edit the SKILL.md — for example, add a new capability:

```bash
# Add a line to SKILL.md
echo "" >> examples/data-analysis/SKILL.md
echo "- Support for TSV (tab-separated) files" >> examples/data-analysis/SKILL.md
```

Now check lifecycle again:

```bash
skill-eval lifecycle examples/data-analysis
```

Expected output shows the change was detected:

```
Changes detected since v1.0:
  Modified: SKILL.md
```

## Step 7: Run Regression Check

Verify the change didn't introduce security regressions:

```bash
skill-eval regression examples/data-analysis
```

Expected output:

```
══════════════════════════════════════════════════════════
  Regression Check Report
══════════════════════════════════════════════════════════
  Baseline: v20260315-... (98/A)
  Current:  98/A
  Delta:    +0 points
──────────────────────────────────────────────────────────
  Result: ✅ PASSED — No regressions detected.
══════════════════════════════════════════════════════════
```

**What this tells you:** Your change didn't break the audit score. The skill is still clean.

## Step 8: Try the Analysis Script

The bundled script runs independently of any agent:

```bash
python3 examples/data-analysis/scripts/analyze_csv.py examples/data-analysis/evals/files/sales.csv
```

This outputs JSON with row counts, column stats, and detected anomalies (row 19 has revenue of $15,000 — an outlier).

---

## Command Summary

| Step | Command | What It Tells You |
|------|---------|-------------------|
| 1 | `skill-eval audit <skill>` | Is the skill safe? Any security/structure issues? |
| 2 | `skill-eval functional <skill> --dry-run` | Are the eval cases valid? |
| 2 | `skill-eval trigger <skill> --dry-run` | Are the trigger queries valid? |
| 3 | `skill-eval report <skill>` | Overall grade (audit + functional + trigger) |
| 4 | `skill-eval snapshot <skill>` | Save current audit as regression baseline |
| 5 | `skill-eval lifecycle <skill> --save --label v1` | Pin current state as named version |
| 5 | `skill-eval lifecycle <skill>` | Detect changes since last version |
| 7 | `skill-eval regression <skill>` | Check for audit score regressions |

## What Makes This a Good Skill?

This skill follows the [Anthropic Agent Skills standard](https://agentskills.io):

- **Frontmatter**: `name` and `description` are both present and descriptive
- **Description**: Includes "Use when..." and "NOT for..." patterns for accurate triggering
- **Structure**: `scripts/` for deterministic code, `evals/` for evaluation data
- **Conciseness**: Body instructions are specific without being verbose
- **Degrees of Freedom**: Script handles deterministic stats; agent handles interpretation
- **Eval Coverage**: 6 functional cases × 5 assertions + 10 trigger queries
