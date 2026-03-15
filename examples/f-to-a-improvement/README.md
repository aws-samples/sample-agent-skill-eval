# From Grade F to Grade A: A Lifecycle Walkthrough

This example contains three versions of the same skill — a file organizer — showing
how it improves from a failing Grade F to a clean Grade A. Each version is a
runnable skill directory you can audit yourself.

## The Three Stages

```
before/  → 0/100  (Grade F) — Secrets, unsafe installs, over-permissions
v2/      → 76/100 (Grade C) — Security fixed, structure still needs work
after/   → 98/100 (Grade A) — Clean, minimal, well-documented
```

## Try It Yourself

```bash
# Audit each stage
skill-eval audit examples/f-to-a-improvement/before
skill-eval audit examples/f-to-a-improvement/v2
skill-eval audit examples/f-to-a-improvement/after

# Track changes with lifecycle
skill-eval lifecycle examples/f-to-a-improvement/before
skill-eval lifecycle examples/f-to-a-improvement/after

# Compare before vs after
skill-eval compare examples/f-to-a-improvement/before examples/f-to-a-improvement/after
```

## What Changed at Each Stage

### before/ → v2/ (F → C)

| What Was Fixed | Finding | Impact |
|----------------|---------|--------|
| Removed hardcoded API key and password | SEC-001 | -25 each |
| Removed `curl \| bash` install | SEC-004 | -25 |
| Removed `pickle.load()` | SEC-006 | -25 |
| Added proper frontmatter (name, description) | STR-* | -10 each |

**Still remaining in v2:**
- Description too short (STR-011, warning)
- Over-broad permissions: `Read(*)`, `Write(*)`, `Bash(command)` (SEC-005, warning)
- Unpinned `pip install watchdog` (info)

### v2/ → after/ (C → A)

| What Was Fixed | Finding | Impact |
|----------------|---------|--------|
| Expanded description with use-cases | STR-011 | -10 |
| Scoped permissions to target directory only | SEC-005 | -10 |
| Removed unpinned pip install | SEC-004 | info |
| Added `--undo` support and move logging | — | quality |

## Key Lessons

1. **Secrets are the #1 killer.** Four criticals from hardcoded credentials alone bottomed the score.
2. **Permissions matter.** `Bash(*)` and `Read(*)` are warnings — scope them to what's needed.
3. **Description is not decoration.** A one-word description triggers STR-011 and costs 10 points.
4. **You don't need perfection.** 98/A still has 1 info finding (name vs directory mismatch). That's fine.

## Using This as a Golden Test

The `test_golden_dataset.py` test file verifies these scores don't drift:

```python
# before/ should be Grade F (score < 60)
# v2/ should be Grade C (score 70-79)
# after/ should be Grade A (score >= 90)
```

If a code change shifts these scores, the golden test catches it.
