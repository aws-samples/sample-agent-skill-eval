"""Unified report aggregating audit, functional, and trigger evaluations.

Runs all applicable evaluation phases on a skill, computes a weighted
overall grade, and outputs a combined report in text or JSON format.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

from skill_eval.cli import run_audit


# ---------------------------------------------------------------------------
# Grading helpers
# ---------------------------------------------------------------------------

def _letter_grade(score: float) -> str:
    """Map a 0-1 score to a letter grade."""
    if score >= 0.9:
        return "A"
    elif score >= 0.8:
        return "B"
    elif score >= 0.7:
        return "C"
    elif score >= 0.6:
        return "D"
    else:
        return "F"


def _bar(value: float, width: int = 10) -> str:
    """Render a value (0-1) as a block bar."""
    filled = round(value * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def compute_weighted_score(
    audit_score: Optional[float],
    functional_score: Optional[float],
    trigger_score: Optional[float],
) -> float:
    """Compute overall 0-1 score from component scores.

    Weights: audit=40%, functional=40%, trigger=20%.
    If a component is None (skipped/unavailable), its weight is
    redistributed equally to the remaining components.
    """
    components: list[tuple[float, float]] = []  # (score, weight)
    if audit_score is not None:
        components.append((audit_score, 0.4))
    if functional_score is not None:
        components.append((functional_score, 0.4))
    if trigger_score is not None:
        components.append((trigger_score, 0.2))

    if not components:
        return 0.0

    total_weight = sum(w for _, w in components)
    # Redistribute: scale each weight proportionally so they sum to 1.0
    return sum(s * (w / total_weight) for s, w in components)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_unified_report(
    skill_path: str,
    format: str = "text",
    output_path: Optional[str] = None,
    include_audit: bool = True,
    include_functional: bool = True,
    include_trigger: bool = True,
    dry_run: bool = False,
    timeout: int = 120,
    agent: str = "claude",
    include_all: bool = False,
) -> int:
    """Run all applicable evaluations and produce a unified report.

    Args:
        skill_path: Path to the skill directory.
        format: Output format ("text" or "json").
        output_path: Path to write report file (default: <skill>/evals/report.json).
        include_audit: Run audit phase (unless False / --skip-audit).
        include_functional: Run functional eval if evals.json exists.
        include_trigger: Run trigger eval if eval_queries.json exists.
        dry_run: Validate inputs without executing agent calls.
        timeout: Timeout per agent invocation in seconds.
        agent: Name of the registered agent runner.
        include_all: If True, audit scans entire directory tree.

    Returns:
        Exit code: 0 = passed, 1 = failed, 2 = error.
    """
    path = Path(skill_path).resolve()
    skill_name = _read_skill_name(path) or path.name

    sections: dict = {}
    audit_norm: Optional[float] = None
    functional_norm: Optional[float] = None
    trigger_norm: Optional[float] = None
    overall_passed = True

    # ---- Audit ----
    if include_audit:
        try:
            report = run_audit(str(path), include_all=include_all)
            audit_norm = report.score / 100.0
            sections["audit"] = {
                "score": report.score,
                "grade": report.grade,
                "passed": report.passed,
                "normalized": round(audit_norm, 4),
                "critical": report.critical_count,
                "warning": report.warning_count,
                "info": report.info_count,
            }
            if not report.passed:
                overall_passed = False
        except Exception as exc:
            print(f"Audit error: {exc}", file=sys.stderr)
            sections["audit"] = {"error": str(exc)}

    # ---- Functional ----
    evals_file = path / "evals" / "evals.json"
    if include_functional and evals_file.is_file():
        try:
            func_result = _run_functional(str(path), dry_run, timeout, agent)
            if func_result is not None:
                functional_norm = func_result["overall"]
                func_section = {
                    "overall": func_result["overall"],
                    "grade": _letter_grade(func_result["overall"]),
                    "passed": func_result["passed"],
                    "scores": func_result.get("scores", {}),
                }
                if "cost_efficiency" in func_result:
                    func_section["cost_efficiency"] = func_result["cost_efficiency"]
                if "estimated_cost" in func_result:
                    func_section["estimated_cost"] = func_result["estimated_cost"]
                sections["functional"] = func_section
                if not func_result["passed"]:
                    overall_passed = False
        except Exception as exc:
            print(f"Functional error: {exc}", file=sys.stderr)
            sections["functional"] = {"error": str(exc)}
    elif include_functional:
        sections["functional"] = {"skipped": True, "reason": "evals/evals.json not found"}

    # ---- Trigger ----
    queries_file = path / "evals" / "eval_queries.json"
    if include_trigger and queries_file.is_file():
        try:
            trigger_result = _run_trigger(str(path), dry_run, timeout, agent)
            if trigger_result is not None:
                trigger_norm = trigger_result["pass_rate"]
                sections["trigger"] = {
                    "pass_rate": trigger_result["pass_rate"],
                    "grade": _letter_grade(trigger_result["pass_rate"]),
                    "passed": trigger_result["passed"],
                    "total_queries": trigger_result.get("total_queries", 0),
                }
                if not trigger_result["passed"]:
                    overall_passed = False
        except Exception as exc:
            print(f"Trigger error: {exc}", file=sys.stderr)
            sections["trigger"] = {"error": str(exc)}
    elif include_trigger:
        sections["trigger"] = {"skipped": True, "reason": "evals/eval_queries.json not found"}

    # ---- Overall grade ----
    overall_score = compute_weighted_score(audit_norm, functional_norm, trigger_norm)
    overall_grade = _letter_grade(overall_score)

    report_data = {
        "skill_name": skill_name,
        "skill_path": str(path),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_score": round(overall_score, 4),
        "overall_grade": overall_grade,
        "passed": overall_passed,
        "sections": sections,
    }

    # ---- Write report file ----
    if output_path:
        out_file = Path(output_path)
    else:
        out_file = path / "evals" / "report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report_data, indent=2))

    # ---- Print ----
    if format == "json":
        print(json.dumps(report_data, indent=2))
    else:
        _print_text_report(report_data)

    return 0 if overall_passed else 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_skill_name(skill_path: Path) -> Optional[str]:
    """Try to read the skill name from SKILL.md frontmatter."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        return None
    try:
        content = skill_md.read_text()
        if content.startswith("---"):
            end = content.index("---", 3)
            fm_text = content[3:end]
            for line in fm_text.splitlines():
                if line.strip().startswith("name:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
    except (ValueError, IndexError):
        pass
    return None


def _run_functional(
    skill_path: str,
    dry_run: bool,
    timeout: int,
    agent: str,
) -> Optional[dict]:
    """Run functional eval and return summary dict, or None on error."""
    from skill_eval.functional import run_functional_eval

    path = Path(skill_path).resolve()
    out_file = path / "evals" / "benchmark.json"

    exit_code = run_functional_eval(
        skill_path,
        dry_run=dry_run,
        timeout=timeout,
        agent=agent,
        output_path=str(out_file),
        format="json",
    )

    if dry_run:
        return {"overall": 0.0, "passed": True, "scores": {}}

    if out_file.is_file():
        data = json.loads(out_file.read_text())
        result = {
            "overall": data.get("scores", {}).get("overall", 0.0),
            "passed": data.get("passed", False),
            "scores": data.get("scores", {}),
        }
        ce = data.get("run_summary", {}).get("cost_efficiency")
        if ce:
            result["cost_efficiency"] = ce
        ec = data.get("run_summary", {}).get("estimated_cost")
        if ec:
            result["estimated_cost"] = ec
        return result
    return None


def _run_trigger(
    skill_path: str,
    dry_run: bool,
    timeout: int,
    agent: str,
) -> Optional[dict]:
    """Run trigger eval and return summary dict, or None on error."""
    from skill_eval.trigger import run_trigger_eval

    path = Path(skill_path).resolve()
    out_file = path / "evals" / "trigger_report.json"

    exit_code = run_trigger_eval(
        skill_path,
        dry_run=dry_run,
        timeout=timeout,
        agent=agent,
        output_path=str(out_file),
        format="json",
    )

    if dry_run:
        return {"pass_rate": 0.0, "passed": True, "total_queries": 0}

    if out_file.is_file():
        data = json.loads(out_file.read_text())
        summary = data.get("summary", {})
        total = summary.get("total_queries", 0)
        passed_count = summary.get("passed", 0)
        pass_rate = passed_count / total if total > 0 else 0.0
        return {
            "pass_rate": round(pass_rate, 4),
            "passed": data.get("passed", False),
            "total_queries": total,
        }
    return None


def _print_text_report(data: dict) -> None:
    """Print a clean text summary of the unified report."""
    w = 43
    sections = data.get("sections", {})

    print()
    print("\u2550" * w)
    print("  Unified Skill Report")
    print("\u2550" * w)
    print(f"  Skill: {data['skill_name']}")
    print(f"  Overall Grade: {data['overall_grade']} ({data['overall_score']:.2f})")
    print("\u2500" * w)

    # Audit
    audit = sections.get("audit", {})
    if "error" not in audit and "skipped" not in audit and audit:
        score = audit["score"]
        grade = audit["grade"]
        norm = audit["normalized"]
        print(f"  Audit:      {score}/100 ({grade})  {_bar(norm)}")

    # Functional
    func = sections.get("functional", {})
    if "error" not in func and "skipped" not in func and func:
        overall = func["overall"]
        grade = func["grade"]
        print(f"  Functional: {overall:.2f}  ({grade})   {_bar(overall)}")
        ce = func.get("cost_efficiency")
        if ce:
            qd = ce["quality_delta"]
            cd = ce["cost_delta_pct"]
            qd_sign = "+" if qd >= 0 else ""
            cd_sign = "+" if cd >= 0 else ""
            print(f"  Cost:       {ce['emoji']} {ce['classification']} (quality {qd_sign}{qd:.2f}, cost {cd_sign}{cd:.1f}%)")
        ec = func.get("estimated_cost")
        if ec and ec.get("total_cost", 0) > 0:
            from skill_eval.cost import format_cost
            print(f"  Est. cost:  {format_cost(ec['total_cost'])} (functional, {ec.get('model', 'sonnet')} pricing)")

    # Trigger
    trigger = sections.get("trigger", {})
    if "error" not in trigger and "skipped" not in trigger and trigger:
        rate = trigger["pass_rate"]
        grade = trigger["grade"]
        print(f"  Trigger:    {rate:.2f}  ({grade})   {_bar(rate)}")

    print("\u2500" * w)

    if data["passed"]:
        print("  Result: PASSED")
    else:
        print("  Result: FAILED")
    print("\u2550" * w)
    print()
