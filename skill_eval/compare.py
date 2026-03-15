"""Side-by-side skill comparison.

Runs the same eval cases with two different skills and compares
pass rates, token usage, and tool calls to determine which skill
is more cost-effective.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from skill_eval.eval_schemas import CompareReport, EvalCase
from skill_eval.agent_runner import AgentRunner, AgentNotAvailableError, get_runner
from skill_eval.grading import grade_output


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_compare(
    skill_a_path: str,
    skill_b_path: str,
    evals_path: Optional[str] = None,
    runs_per_eval: int = 1,
    format: str = "text",
    output_path: Optional[str] = None,
    dry_run: bool = False,
    timeout: int = 120,
    agent: str = "claude",
) -> int:
    """Run side-by-side comparison of two skills.

    Args:
        skill_a_path: Path to skill A directory.
        skill_b_path: Path to skill B directory.
        evals_path: Path to evals.json (default: skill_a's evals/evals.json).
        runs_per_eval: Number of times to run each eval case per skill.
        format: Output format ("text" or "json").
        output_path: Path to write comparison report JSON.
        dry_run: If True, load and validate evals but do not execute.
        timeout: Timeout per claude invocation in seconds.
        agent: Name of the registered agent runner (default: "claude").

    Returns:
        Exit code: 0 = success, 2 = error.
    """
    path_a = Path(skill_a_path).resolve()
    path_b = Path(skill_b_path).resolve()

    # Load evals (default: skill A's evals)
    evals_file = Path(evals_path) if evals_path else path_a / "evals" / "evals.json"
    try:
        eval_cases = _load_evals(evals_file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Error loading evals: {e}", file=sys.stderr)
        return 2

    if not eval_cases:
        print("No eval cases found.", file=sys.stderr)
        return 2

    if dry_run:
        invocations = len(eval_cases) * runs_per_eval * 2
        print(f"Dry run: {len(eval_cases)} eval case(s), {runs_per_eval} run(s) each")
        print(f"  Estimated invocations: {invocations} ({invocations // 2} per skill)")
        print(f"  Skill A: {path_a}")
        print(f"  Skill B: {path_b}")
        return 0

    # Resolve runner
    try:
        runner = get_runner(agent)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Check agent availability
    try:
        runner.check_available()
    except AgentNotAvailableError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Read skill names
    name_a = _read_skill_name(path_a) or path_a.name
    name_b = _read_skill_name(path_b) or path_b.name

    # Run comparisons
    per_eval: list[dict] = []
    evals_dir = evals_file.parent

    for eval_case in eval_cases:
        eval_row = _run_eval_comparison(
            eval_case, path_a, path_b, evals_dir, runs_per_eval, timeout,
            runner=runner,
        )
        per_eval.append(eval_row)

    # Aggregate
    report = _aggregate_compare(name_a, str(path_a), name_b, str(path_b),
                                eval_cases, per_eval, runs_per_eval)

    # Write output
    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(report.to_json())

    if format == "json":
        print(report.to_json())
    else:
        _print_compare_report(report)

    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_evals(evals_file: Path) -> list[EvalCase]:
    """Load and validate eval cases from evals.json."""
    if not evals_file.is_file():
        raise FileNotFoundError(f"Evals file not found: {evals_file}")

    data = json.loads(evals_file.read_text())
    if not isinstance(data, list):
        raise ValueError("evals.json must be a JSON array")

    cases = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"evals.json[{i}] must be an object")
        if "id" not in item or "prompt" not in item:
            raise ValueError(f"evals.json[{i}] missing required field 'id' or 'prompt'")
        cases.append(EvalCase.from_dict(item))
    return cases


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


def _run_single_skill(
    eval_case: EvalCase,
    skill_path: Path,
    workspace: Path,
    timeout: int,
    runner: Optional[AgentRunner] = None,
) -> dict:
    """Run one eval case with one skill and return results dict."""
    if runner is None:
        runner = get_runner("claude")

    stdout, stderr, rc, elapsed = runner.run_prompt(
        eval_case.prompt,
        skill_path=str(skill_path),
        workspace_dir=str(workspace),
        timeout=timeout,
        output_format="stream-json",
    )
    parsed = runner.parse_output(stdout)

    text = parsed["text"]
    assertion_results, pass_rate = grade_output(text, eval_case.assertions, timeout=timeout)

    return {
        "pass_rate": pass_rate,
        "assertions_passed": sum(1 for r in assertion_results if r.passed),
        "assertions_total": len(assertion_results),
        "token_counts": parsed["token_counts"],
        "total_tokens": runner.total_tokens(parsed["token_counts"]),
        "tool_calls": len(parsed["tool_calls"]),
        "elapsed_seconds": elapsed,
    }


def _run_eval_comparison(
    eval_case: EvalCase,
    skill_a: Path,
    skill_b: Path,
    evals_dir: Path,
    runs_per_eval: int,
    timeout: int,
    runner: Optional[AgentRunner] = None,
) -> dict:
    """Run one eval case with both skills and return per-eval row."""
    if runner is None:
        runner = get_runner("claude")

    a_results: list[dict] = []
    b_results: list[dict] = []

    for _ in range(runs_per_eval):
        with tempfile.TemporaryDirectory(prefix="skill-compare-") as tmpdir:
            workspace = Path(tmpdir)
            for rel_file in eval_case.files:
                src = evals_dir / rel_file
                dst = workspace / Path(rel_file).name
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

            a_run = _run_single_skill(eval_case, skill_a, workspace, timeout, runner=runner)
            a_results.append(a_run)

        with tempfile.TemporaryDirectory(prefix="skill-compare-") as tmpdir:
            workspace = Path(tmpdir)
            for rel_file in eval_case.files:
                src = evals_dir / rel_file
                dst = workspace / Path(rel_file).name
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

            b_run = _run_single_skill(eval_case, skill_b, workspace, timeout, runner=runner)
            b_results.append(b_run)

    def _avg(values: list) -> float:
        return sum(values) / len(values) if values else 0.0

    a_pass_rate = _avg([r["pass_rate"] for r in a_results])
    b_pass_rate = _avg([r["pass_rate"] for r in b_results])
    a_total_tokens = _avg([r["total_tokens"] for r in a_results])
    b_total_tokens = _avg([r["total_tokens"] for r in b_results])
    a_tool_calls = _avg([r["tool_calls"] for r in a_results])
    b_tool_calls = _avg([r["tool_calls"] for r in b_results])
    a_passed_assertions = _avg([r["assertions_passed"] for r in a_results])
    b_passed_assertions = _avg([r["assertions_passed"] for r in b_results])

    return {
        "eval_id": eval_case.id,
        "skill_a": {
            "mean_pass_rate": round(a_pass_rate, 4),
            "mean_total_tokens": round(a_total_tokens, 1),
            "mean_tool_calls": round(a_tool_calls, 1),
            "mean_assertions_passed": round(a_passed_assertions, 1),
        },
        "skill_b": {
            "mean_pass_rate": round(b_pass_rate, 4),
            "mean_total_tokens": round(b_total_tokens, 1),
            "mean_tool_calls": round(b_tool_calls, 1),
            "mean_assertions_passed": round(b_passed_assertions, 1),
        },
    }


def _aggregate_compare(
    name_a: str,
    path_a: str,
    name_b: str,
    path_b: str,
    eval_cases: list[EvalCase],
    per_eval: list[dict],
    runs_per_eval: int,
) -> CompareReport:
    """Compute summary statistics and determine winner."""
    a_pass_rates = [e["skill_a"]["mean_pass_rate"] for e in per_eval]
    b_pass_rates = [e["skill_b"]["mean_pass_rate"] for e in per_eval]
    a_total_tokens = [e["skill_a"]["mean_total_tokens"] for e in per_eval]
    b_total_tokens = [e["skill_b"]["mean_total_tokens"] for e in per_eval]
    a_assertions = [e["skill_a"]["mean_assertions_passed"] for e in per_eval]
    b_assertions = [e["skill_b"]["mean_assertions_passed"] for e in per_eval]

    def _mean(vals: list) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    overall_a_pass = _mean(a_pass_rates)
    overall_b_pass = _mean(b_pass_rates)
    overall_a_tokens = _mean(a_total_tokens)
    overall_b_tokens = _mean(b_total_tokens)
    overall_a_assertions = sum(a_assertions)
    overall_b_assertions = sum(b_assertions)

    # Token efficiency ratio: b_total / a_total (>1 means A is cheaper)
    token_efficiency_ratio = (
        overall_b_tokens / overall_a_tokens
        if overall_a_tokens > 0 else 0.0
    )

    # Tokens per passing assertion
    a_tppa = overall_a_tokens / overall_a_assertions if overall_a_assertions > 0 else float("inf")
    b_tppa = overall_b_tokens / overall_b_assertions if overall_b_assertions > 0 else float("inf")

    # Winner: lower tokens-per-passing-assertion wins (>5% margin required)
    if a_tppa == float("inf") and b_tppa == float("inf"):
        winner = "tie"
    elif a_tppa == float("inf"):
        winner = name_b
    elif b_tppa == float("inf"):
        winner = name_a
    else:
        ratio = a_tppa / b_tppa if b_tppa > 0 else float("inf")
        if ratio > 1.05:
            winner = name_b  # B has lower tokens per passing assertion
        elif ratio < 1 / 1.05:
            winner = name_a  # A has lower tokens per passing assertion
        else:
            winner = "tie"

    summary = {
        "skill_a": {
            "mean_pass_rate": round(overall_a_pass, 4),
            "mean_total_tokens": round(overall_a_tokens, 1),
            "total_assertions_passed": round(overall_a_assertions, 1),
            "tokens_per_passing_assertion": round(a_tppa, 1) if a_tppa != float("inf") else None,
        },
        "skill_b": {
            "mean_pass_rate": round(overall_b_pass, 4),
            "mean_total_tokens": round(overall_b_tokens, 1),
            "total_assertions_passed": round(overall_b_assertions, 1),
            "tokens_per_passing_assertion": round(b_tppa, 1) if b_tppa != float("inf") else None,
        },
        "token_efficiency_ratio": round(token_efficiency_ratio, 4),
    }

    return CompareReport(
        skill_a_name=name_a,
        skill_a_path=path_a,
        skill_b_name=name_b,
        skill_b_path=path_b,
        eval_count=len(eval_cases),
        runs_per_eval=runs_per_eval,
        per_eval=per_eval,
        summary=summary,
        winner=winner,
    )


def _print_compare_report(report: CompareReport) -> None:
    """Print a human-readable comparison report."""
    w = 58

    print(f"\n{'=' * w}")
    print(f"  Skill Comparison Report")
    print(f"{'=' * w}")
    print(f"  Skill A: {report.skill_a_name}")
    print(f"  Skill B: {report.skill_b_name}")
    print(f"  Eval cases: {report.eval_count}")
    print(f"  Runs/eval:  {report.runs_per_eval}")
    print(f"{'─' * w}")

    s = report.summary
    sa = s.get("skill_a", {})
    sb = s.get("skill_b", {})

    print(f"  {'':20s} {'Skill A':>14s}  {'Skill B':>14s}")
    print(f"  {'Pass rate':20s} {sa.get('mean_pass_rate', 0):>13.1%}  {sb.get('mean_pass_rate', 0):>14.1%}")
    print(f"  {'Total tokens':20s} {sa.get('mean_total_tokens', 0):>13,.0f}  {sb.get('mean_total_tokens', 0):>14,.0f}")

    a_tppa = sa.get("tokens_per_passing_assertion")
    b_tppa = sb.get("tokens_per_passing_assertion")
    a_str = f"{a_tppa:,.0f}" if a_tppa is not None else "N/A"
    b_str = f"{b_tppa:,.0f}" if b_tppa is not None else "N/A"
    print(f"  {'Tokens/pass assert':20s} {a_str:>13s}  {b_str:>14s}")

    ratio = s.get("token_efficiency_ratio", 0)
    print(f"  {'Token ratio (B/A)':20s} {ratio:>13.2f}x")
    print(f"{'─' * w}")

    # Per-eval breakdown
    if report.per_eval:
        print(f"  Per-eval breakdown:")
        for row in report.per_eval:
            eid = row["eval_id"]
            ra = row["skill_a"]
            rb = row["skill_b"]
            print(f"    {eid}: A={ra['mean_pass_rate']:.0%}/{ra['mean_total_tokens']:.0f}tok "
                  f"B={rb['mean_pass_rate']:.0%}/{rb['mean_total_tokens']:.0f}tok")
        print(f"{'─' * w}")

    print(f"  Winner: {report.winner}")
    print(f"{'=' * w}\n")
