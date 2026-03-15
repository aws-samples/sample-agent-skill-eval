# Phase 2 Review: Regression Gate + CLI Enhancements

**Reviewer**: Claude Opus 4.6
**Date**: 2026-03-12
**Files Reviewed**:
- `skill_eval/regression.py` (NEW)
- `skill_eval/cli.py` (MODIFIED)
- `tests/test_regression.py` (NEW)

**Test results**: 106/106 passing (94 original + 12 new tests added during review)

---

## A. Bugs and Issues

### BUG-1: Finding Key Collision in `check_regression` (FIXED)

**Severity**: Medium
**Location**: `skill_eval/regression.py:268-271` (original line numbers)

`current_finding_keys` was a dict keyed by `"{code}:{file_path}:{line_number}"`. When multiple findings share the same code, file, and line number, later entries silently overwrite earlier ones.

**Reproduction**: A single line like `subprocess.run("ls", shell=True)` triggers two SEC-003 findings (one for `subprocess.run`, one for `shell=True`). Both map to the same key `SEC-003:/path/test.py:3`, so one is dropped. This causes:
- Regression count to be underreported
- `unchanged` count to be incorrect
- Mismatch between `finding_count` in history (from `len(report.findings)`) and the number of items in the regression JSON output

**Fix applied**: Added `title` to the key: `"{code}:{file_path}:{line_number}:{title}"`. This disambiguates findings that share the same code/file/line but have different pattern matches.

### BUG-2: `_get_latest_baseline` Accidentally Correct (FIXED)

**Severity**: Low
**Location**: `skill_eval/regression.py:123-148` (original line numbers)

The function sorted ALL directories in `baselines/` by `st_mtime`, including the `latest/` directory itself. It worked by coincidence because `save_snapshot` always writes `latest/` after the version directory, so `latest/` has the newest mtime.

This would break if:
- A filesystem indexer touches the version directory after `latest/` is written
- Someone manually edits a version directory
- The `latest/` directory is deleted but a version directory remains

**Fix applied**: Now explicitly checks for `baselines/latest/` first. Falls back to mtime-sorted version directories (excluding `latest`) if `latest/` is missing or corrupted.

### ISSUE-3: Thread Safety of `SAFE_DOMAINS` Mutation

**Severity**: Low (single-threaded CLI usage is the norm)
**Location**: `skill_eval/cli.py:36-41` and `skill_eval/cli.py:83-85`

`run_audit()` mutates the module-level `SAFE_DOMAINS` set (imported from `security_scan.py`) by calling `.add()` and `.discard()`. If two audits run concurrently (e.g., via threading or async), one audit's domain additions could leak into another audit, or `.discard()` could remove a domain while another thread is iterating.

**Current risk**: Low. The CLI processes skill paths sequentially in a loop, and the try/finally cleanup restores the set. However:
- The `--allowlist` flag combined with multiple `skill_path` args processes paths in a loop. Each iteration correctly adds/removes from the set, but there's no isolation between iterations. If one audit raises an unexpected exception that bypasses `finally`, the set would be left modified.
- If this library is ever used as a Python API with threading, this would be a race condition.

**Recommendation**: Replace mutation with a local copy pattern:

```python
# Instead of mutating SAFE_DOMAINS:
effective_domains = SAFE_DOMAINS | extra_safe_domains if extra_safe_domains else SAFE_DOMAINS
# Pass effective_domains to scan_security()
```

**Not fixed in this review** - requires changing the `scan_security()` function signature, which is a Phase 1 API change.

### ISSUE-4: `format` Parameter Shadows Python Builtin

**Severity**: Cosmetic
**Location**: `skill_eval/regression.py:225`

`check_regression(format="text")` uses `format` as a parameter name, shadowing the Python builtin `format()`. Not a runtime bug but goes against PEP8 conventions. Consider `output_format` in a future refactor.

---

## B. Test Coverage

### Previously Existing Tests (13 regression tests)

| Scenario | Covered? |
|---|---|
| Create snapshot | Yes |
| Snapshot content validation | Yes |
| Auto version detection | Yes |
| History updates | Yes |
| Multiple snapshots | Yes |
| No regression when unchanged | Yes |
| Regression on new issues | Yes |
| No baseline error | Yes |
| JSON output | Yes |
| Custom baseline path | Yes |
| Snapshot model roundtrip | Yes |
| RegressionResult serialization | Yes |
| Snapshot.from_report | Yes |

### Scenarios NOT Tested (before this review)

| Gap | Risk | Added? |
|---|---|---|
| Finding key collision (same code/file/line) | **High** - silent data loss | **Yes** |
| Score drop within tolerance (no criticals) | Medium - core pass/fail logic | **Yes** |
| Corrupted baseline JSON | Medium - crash risk | **Yes** |
| Invalid custom baseline path | Low - error handling | **Yes** |
| Improvement detection | Medium - reported but not verified | **Yes** |
| Version overwrite (same version saved twice) | Low - data integrity | **Yes** |
| `_get_latest_baseline` prefers "latest" dir | Medium - core logic | **Yes** |
| `_get_latest_baseline` fallback on corrupt "latest" | Medium - resilience | **Yes** |
| `_get_latest_baseline` returns None (no baselines) | Low - base case | **Yes** |
| `_get_latest_baseline` returns None (empty dir) | Low - edge case | **Yes** |
| `Snapshot.from_dict` with extra keys | Low - forwards compat | **Yes** |
| All findings tracked in regression output | **High** - validates collision fix | **Yes** |
| Thread safety of SAFE_DOMAINS | Low (single-threaded) | No (design issue) |
| Concurrent `check_regression` calls | Low | No (design issue) |
| Very large history.json | Low | No |
| Snapshot with unicode skill name | Low | No |

### Tests Added (12 new tests)

1. `TestSnapshotModel::test_from_dict_ignores_extra_keys`
2. `TestFindingKeyCollision::test_duplicate_code_same_line_both_counted`
3. `TestFindingKeyCollision::test_all_findings_tracked_in_regression`
4. `TestRegressionEdgeCases::test_score_drop_within_tolerance_passes`
5. `TestRegressionEdgeCases::test_corrupted_baseline_returns_error`
6. `TestRegressionEdgeCases::test_invalid_custom_baseline_path`
7. `TestRegressionEdgeCases::test_improvement_detected`
8. `TestRegressionEdgeCases::test_version_overwrite`
9. `TestGetLatestBaseline::test_prefers_latest_dir`
10. `TestGetLatestBaseline::test_falls_back_to_mtime_when_latest_corrupted`
11. `TestGetLatestBaseline::test_returns_none_when_no_baselines`
12. `TestGetLatestBaseline::test_returns_none_when_empty_baselines_dir`

---

## C. Design Issues

### C1. Finding Comparison Logic

**Before fix**: Used `(code, file_path, line_number)` as the comparison key. This is insufficient because the same code can appear multiple times on the same line (e.g., `SEC-003` for both `subprocess.run` and `shell=True`).

**After fix**: Uses `(code, file_path, line_number, title)` as the key. This is more robust but still has theoretical edge cases:
- If a finding's `title` changes between versions (e.g., wording update in the scanner), it would appear as both a regression and an improvement simultaneously.
- Consider using a hash of `(code, file_path, line_number, title)` or assigning stable finding IDs in a future version.

**Overall**: The comparison logic is now adequate for the current set of scanners. The title-based differentiation correctly handles the known collision case.

### C2. Score-Based Regression Threshold (5 points)

The current threshold is: **fail if score drops by more than 5 points OR any new CRITICAL findings**.

Analysis of the scoring system:
- CRITICAL = -25 points
- WARNING = -10 points
- INFO = -2 points

A 5-point tolerance means:
- **Allows**: Up to 2 new INFO findings (4 points) without failure
- **Catches**: Any single new WARNING (-10 exceeds threshold) or CRITICAL (caught by the explicit critical check)
- **Edge case**: 3 new INFO findings (-6 points) would trigger score-based failure despite being low severity

**Assessment**: The threshold is reasonable for a CI gate. The 5-point tolerance provides slight flexibility for cosmetic findings while catching anything substantive. The dual check (score AND criticals) is a good design - it ensures criticals always fail even if the score arithmetic somehow compensates.

**Suggestion**: Consider making the threshold configurable via CLI flag (`--threshold`) for teams with different risk tolerances.

### C3. Finding Codes vs. Scores

The current system tracks both:
- **Score-based**: Overall quality trend via numeric score
- **Code-based**: `finding_codes` list in snapshots, and detailed finding comparison in regression

This is a good dual approach. The `finding_codes` field in `Snapshot` currently stores just codes (e.g., `["SEC-001", "SEC-003"]`) without deduplication, which is useful for quick comparison. The detailed finding-level comparison in `check_regression` provides the granular diff.

**Recommendation**: The current approach is sufficient. Tracking specific finding codes in addition to scores is valuable for:
- Understanding *what changed*, not just *how much* the score moved
- Allowing targeted suppressions (e.g., "ignore this specific SEC-002 we've accepted")
- Future features like "require finding X to remain resolved"

---

## D. Quick Fixes Applied

### Fix 1: Finding Key Collision (`regression.py`)

Added `title` to the comparison key to prevent dict collisions when multiple findings share the same `(code, file_path, line_number)`.

**Diff summary**:
```python
# Before:
key = f"{f.code}:{f.file_path or ''}:{f.line_number or ''}"

# After:
key = f"{f.code}:{f.file_path or ''}:{f.line_number or ''}:{f.title}"
```

### Fix 2: `_get_latest_baseline` Robustness (`regression.py`)

Changed from mtime-sorting all directories (including `latest/`) to explicitly checking `latest/` first with a fallback to mtime-sorted version directories (excluding `latest/`).

### Fix 3: Added 12 Missing Tests (`test_regression.py`)

Covered finding key collisions, edge cases (tolerance, corruption, improvements), `_get_latest_baseline` behavior, and `Snapshot.from_dict` forward compatibility.

---

## Summary

| Category | Count |
|---|---|
| Bugs found | 2 (both fixed) |
| Design issues noted | 4 (1 fixed, 3 documented) |
| Tests added | 12 |
| Final test count | 106/106 passing |

The Phase 2 regression gate is well-designed overall. The snapshot/compare workflow is intuitive, the CLI integration is clean, and the dual score+finding comparison provides useful CI gate semantics. The two bugs fixed during review (key collision, baseline lookup) were real but unlikely to cause issues in typical single-skill workflows. The thread safety of `SAFE_DOMAINS` should be addressed if the library is used as an API.
