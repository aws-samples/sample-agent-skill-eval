"""Regression testing for Agent Skills.

Provides:
- Baseline snapshot saving (capture current audit state)
- Regression detection (compare current vs baseline)
- Assertion levels: hard (must pass), soft (track trend), baseline (must beat no-skill)

Compatible with Anthropic skill-creator's evals.json schema (extended with
level and category fields).
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from skill_eval.schemas import Finding, Severity, AuditReport, calculate_score, calculate_grade
from skill_eval.cli import run_audit
from skill_eval.report import format_text_report


@dataclass
class RegressionResult:
    """Result of a regression check."""
    passed: bool
    current_score: int
    baseline_score: int
    current_grade: str
    baseline_grade: str
    regressions: list[dict] = field(default_factory=list)  # New findings not in baseline
    improvements: list[dict] = field(default_factory=list)  # Baseline findings now gone
    unchanged: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class Snapshot:
    """A baseline snapshot of audit results."""
    skill_name: str
    skill_path: str
    version: str
    timestamp: str
    score: int
    grade: str
    finding_codes: list[str]  # Just the codes for quick comparison
    findings: list[dict]       # Full finding details
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_report(cls, report: AuditReport, version: str) -> "Snapshot":
        return cls(
            skill_name=report.skill_name,
            skill_path=report.skill_path,
            version=version,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            score=report.score,
            grade=report.grade,
            finding_codes=[f.code for f in report.findings],
            findings=[f.to_dict() for f in report.findings],
            metadata=report.metadata,
        )


@dataclass
class HistoryEntry:
    """One entry in the version history."""
    version: str
    timestamp: str
    score: int
    grade: str
    finding_count: int
    critical: int
    warning: int
    info: int
    regression_result: Optional[str] = None  # "passed", "failed", "baseline"


def _get_baselines_dir(skill_path: Path) -> Path:
    """Get the baselines directory for a skill."""
    return skill_path / "evals" / "baselines"


def _get_history_path(skill_path: Path) -> Path:
    """Get the history.json path for a skill."""
    return skill_path / "evals" / "history.json"


def _load_history(skill_path: Path) -> list[dict]:
    """Load version history."""
    history_path = _get_history_path(skill_path)
    if history_path.is_file():
        try:
            return json.loads(history_path.read_text())
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def _save_history(skill_path: Path, history: list[dict]) -> None:
    """Save version history."""
    history_path = _get_history_path(skill_path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2))


def _get_latest_baseline(skill_path: Path) -> Optional[Snapshot]:
    """Load the most recent baseline snapshot."""
    baselines_dir = _get_baselines_dir(skill_path)
    if not baselines_dir.is_dir():
        return None

    # Prefer the explicit "latest" directory (maintained by save_snapshot)
    latest_dir = baselines_dir / "latest"
    if latest_dir.is_dir():
        results_file = latest_dir / "results.json"
        if results_file.is_file():
            try:
                data = json.loads(results_file.read_text())
                return Snapshot.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # Fall through to mtime-based lookup

    # Fallback: find the most recently modified version directory
    versions = sorted(
        [d for d in baselines_dir.iterdir() if d.is_dir() and d.name != "latest"],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not versions:
        return None

    results_file = versions[0] / "results.json"
    if not results_file.is_file():
        return None

    try:
        data = json.loads(results_file.read_text())
        return Snapshot.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def save_snapshot(skill_path: str, version: str | None = None) -> int:
    """Save current audit results as a baseline snapshot.

    Args:
        skill_path: Path to the skill directory
        version: Version label (auto-detected from metadata if not provided)

    Returns:
        Exit code (0 = success)
    """
    path = Path(skill_path).resolve()

    # Run audit
    report = run_audit(str(path))

    # Determine version
    if not version:
        # Try to get from frontmatter metadata
        from skill_eval.audit.structure_check import check_structure
        _, fm, _ = check_structure(path)
        if fm:
            meta = fm.get("metadata", {})
            if isinstance(meta, dict):
                version = meta.get("version", None)
        if not version:
            version = time.strftime("v%Y%m%d-%H%M%S")

    # Create snapshot
    snapshot = Snapshot.from_report(report, version)

    # Save to baselines directory
    baselines_dir = _get_baselines_dir(path)
    version_dir = baselines_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)

    results_file = version_dir / "results.json"
    results_file.write_text(json.dumps(snapshot.to_dict(), indent=2))

    # Also save as "latest" symlink / copy
    latest_dir = baselines_dir / "latest"
    if latest_dir.is_symlink():
        latest_dir.unlink()
    elif latest_dir.is_dir():
        import shutil
        shutil.rmtree(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "results.json").write_text(json.dumps(snapshot.to_dict(), indent=2))

    # Update history
    history = _load_history(path)
    entry = HistoryEntry(
        version=version,
        timestamp=snapshot.timestamp,
        score=report.score,
        grade=report.grade,
        finding_count=len(report.findings),
        critical=report.critical_count,
        warning=report.warning_count,
        info=report.info_count,
        regression_result="baseline",
    )
    history.append(asdict(entry))
    _save_history(path, history)

    print(f"✅ Snapshot saved: {version_dir}")
    print(f"   Score: {report.score}/{report.grade} | "
          f"Findings: {len(report.findings)} "
          f"(C:{report.critical_count} W:{report.warning_count} I:{report.info_count})")

    return 0


def check_regression(
    skill_path: str,
    baseline_path: str | None = None,
    format: str = "text",
) -> int:
    """Check for regressions against a baseline.

    Args:
        skill_path: Path to the skill directory
        baseline_path: Path to baseline results.json (default: evals/baselines/latest/)
        format: Output format

    Returns:
        Exit code (0 = no regression, 1 = regression detected)
    """
    path = Path(skill_path).resolve()

    # Load baseline
    if baseline_path:
        bp = Path(baseline_path)
        if bp.is_dir():
            bp = bp / "results.json"
        try:
            baseline = Snapshot.from_dict(json.loads(bp.read_text()))
        except Exception as e:
            print(f"❌ Cannot load baseline: {e}", file=sys.stderr)
            return 2
    else:
        baseline = _get_latest_baseline(path)
        if baseline is None:
            print("❌ No baseline found. Run 'skill-eval snapshot' first.", file=sys.stderr)
            return 2

    # Run current audit
    report = run_audit(str(path))

    # Compare findings
    baseline_codes = set(baseline.finding_codes)
    current_codes = set(f.code for f in report.findings)

    # Build detailed finding maps for comparison.
    # Use (code, file_path, line_number, title) as key to avoid collisions
    # when multiple findings share the same code/file/line (e.g., SEC-003
    # for both subprocess.run and shell=True on the same line).
    def _finding_key_from_dict(bf: dict) -> str:
        return f"{bf['code']}:{bf.get('file_path', '')}:{bf.get('line_number', '')}:{bf.get('title', '')}"

    def _finding_key_from_obj(f: Finding) -> str:
        return f"{f.code}:{f.file_path or ''}:{f.line_number or ''}:{f.title}"

    baseline_finding_keys = set()
    for bf in baseline.findings:
        baseline_finding_keys.add(_finding_key_from_dict(bf))

    current_finding_keys = {}
    for f in report.findings:
        key = _finding_key_from_obj(f)
        current_finding_keys[key] = f

    # Identify regressions (new findings not in baseline)
    regressions = []
    for key, finding in current_finding_keys.items():
        if key not in baseline_finding_keys:
            regressions.append(finding.to_dict())

    # Identify improvements (baseline findings now resolved)
    improvements = []
    for bf in baseline.findings:
        key = _finding_key_from_dict(bf)
        if key not in current_finding_keys:
            improvements.append(bf)

    unchanged = len(current_finding_keys) - len(regressions)

    # Determine pass/fail
    # Regression = new CRITICAL findings OR score dropped significantly
    new_criticals = [r for r in regressions if r.get("severity") == "CRITICAL"]
    score_dropped = report.score < baseline.score - 5  # 5-point tolerance

    passed = len(new_criticals) == 0 and not score_dropped

    result = RegressionResult(
        passed=passed,
        current_score=report.score,
        baseline_score=baseline.score,
        current_grade=report.grade,
        baseline_grade=baseline.grade,
        regressions=regressions,
        improvements=improvements,
        unchanged=unchanged,
        message=(
            "No regressions detected." if passed
            else f"Regression detected: {len(new_criticals)} new critical findings, "
                 f"score {baseline.score} → {report.score}"
        ),
    )

    # Update history
    version = time.strftime("v%Y%m%d-%H%M%S")
    history = _load_history(path)
    entry = HistoryEntry(
        version=version,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        score=report.score,
        grade=report.grade,
        finding_count=len(report.findings),
        critical=report.critical_count,
        warning=report.warning_count,
        info=report.info_count,
        regression_result="passed" if passed else "failed",
    )
    history.append(asdict(entry))
    _save_history(path, history)

    # Output
    if format == "json":
        print(result.to_json())
    else:
        _print_regression_report(result, baseline)

    return 0 if passed else 1


def _print_regression_report(result: RegressionResult, baseline: Snapshot) -> None:
    """Print a human-readable regression report."""
    w = 58

    print(f"\n{'═' * w}")
    print(f"  Regression Check Report")
    print(f"{'═' * w}")
    print(f"  Baseline: {baseline.version} ({baseline.score}/{baseline.grade})")
    print(f"  Current:  {result.current_score}/{result.current_grade}")

    delta = result.current_score - result.baseline_score
    delta_str = f"+{delta}" if delta >= 0 else str(delta)
    print(f"  Delta:    {delta_str} points")
    print(f"{'─' * w}")

    if result.passed:
        print(f"  Result: ✅ PASSED — {result.message}")
    else:
        print(f"  Result: ❌ FAILED — {result.message}")
    print(f"{'═' * w}\n")

    if result.regressions:
        print(f"  🔴 New findings ({len(result.regressions)}):")
        for r in result.regressions:
            sev = r.get("severity", "?")
            print(f"    [{sev}] {r.get('code', '?')}: {r.get('title', '?')}")
            if r.get("file_path"):
                loc = r["file_path"]
                if r.get("line_number"):
                    loc += f":{r['line_number']}"
                print(f"      File: {loc}")
        print()

    if result.improvements:
        print(f"  ✅ Resolved findings ({len(result.improvements)}):")
        for imp in result.improvements:
            print(f"    [{imp.get('severity', '?')}] {imp.get('code', '?')}: {imp.get('title', '?')}")
        print()

    print(f"  Summary: {len(result.regressions)} new | "
          f"{len(result.improvements)} resolved | "
          f"{result.unchanged} unchanged")
