"""Functional evaluation orchestrator.

Runs eval cases with and without a skill installed, grades outputs,
computes 4-dimension scores (outcome, process, style, efficiency),
and produces a benchmark.json report.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from skill_eval.cost import estimate_eval_cost, format_cost
from skill_eval.eval_schemas import (
    EvalCase, AssertionResult, GradingResult, RunPairResult, BenchmarkReport,
)
from skill_eval.agent_runner import AgentRunner, AgentNotAvailableError, get_runner
from skill_eval.grading import grade_output


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_functional_eval(
    skill_path: str,
    evals_path: Optional[str] = None,
    runs_per_eval: int = 1,
    format: str = "text",
    output_path: Optional[str] = None,
    dry_run: bool = False,
    timeout: int = 120,
    agent: str = "claude",
) -> int:
    """Run functional evaluation on a skill.

    Args:
        skill_path: Path to the skill directory.
        evals_path: Path to evals.json (default: <skill_path>/evals/evals.json).
        runs_per_eval: Number of times to run each eval case.
        format: Output format ("text" or "json").
        output_path: Path to write benchmark.json (default: <skill_path>/evals/benchmark.json).
        dry_run: If True, load and validate evals but do not execute.
        timeout: Timeout per claude invocation in seconds.
        agent: Name of the registered agent runner (default: "claude").

    Returns:
        Exit code: 0 = passed, 1 = failed, 2 = error.
    """
    path = Path(skill_path).resolve()

    # Load evals
    evals_file = Path(evals_path) if evals_path else path / "evals" / "evals.json"
    try:
        eval_cases = _load_evals(evals_file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Error loading evals: {e}", file=sys.stderr)
        return 2

    if not eval_cases:
        print("No eval cases found.", file=sys.stderr)
        return 2

    if dry_run:
        print(f"Dry run: loaded {len(eval_cases)} eval case(s) from {evals_file}")
        for ec in eval_cases:
            print(f"  - {ec.id}: {ec.prompt[:80]}...")
            print(f"    Assertions: {len(ec.assertions)}, Files: {len(ec.files)}")
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

    # Execute eval pairs
    skill_name = path.name
    frontmatter = _read_skill_name(path)
    if frontmatter:
        skill_name = frontmatter

    all_pairs: list[RunPairResult] = []
    all_grading: list[GradingResult] = []
    evals_dir = evals_file.parent

    for eval_case in eval_cases:
        for run_idx in range(runs_per_eval):
            pair, with_grading, without_grading = _execute_eval_pair(
                eval_case, path, evals_dir, run_idx, timeout, runner=runner,
            )
            all_pairs.append(pair)
            all_grading.append(with_grading)
            all_grading.append(without_grading)

    # Aggregate benchmark
    report = _aggregate_benchmark(
        skill_name, str(path), eval_cases, all_pairs, all_grading, runs_per_eval,
    )

    # Write benchmark.json
    out_file = Path(output_path) if output_path else path / "evals" / "benchmark.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report.to_json())

    # Output
    if format == "json":
        print(report.to_json())
    else:
        _print_functional_report(report)

    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# Cost-efficiency Pareto classification
# ---------------------------------------------------------------------------

def classify_cost_efficiency(
    quality_delta: float,
    cost_delta_pct: float,
    threshold: float = -0.05,
) -> dict:
    """Classify the cost-efficiency tradeoff using Pareto dominance.

    Compares quality change (pass rate delta) against cost change (token delta %)
    and returns a classification label, emoji, and description.

    Args:
        quality_delta: Change in pass rate (with_skill - without_skill).
        cost_delta_pct: Percentage change in total tokens
                        ((with - without) / without * 100).
        threshold: Quality degradation threshold below which the skill is
                   rejected regardless of cost.  Default -0.05 (5%).

    Returns:
        Dict with keys: classification, emoji, description.
    """
    if quality_delta <= threshold:
        return {
            "classification": "REJECT",
            "emoji": "\U0001f534",
            "description": "Skill significantly degrades quality",
        }
    if quality_delta >= 0 and cost_delta_pct <= 0:
        return {
            "classification": "PARETO_BETTER",
            "emoji": "\U0001f7e2",
            "description": "Skill improves quality while reducing cost",
        }
    if quality_delta > 0 and cost_delta_pct > 0:
        return {
            "classification": "TRADEOFF",
            "emoji": "\U0001f7e1",
            "description": "Skill improves quality but increases cost",
        }
    if quality_delta <= 0 and cost_delta_pct < 0:
        return {
            "classification": "CHEAPER_BUT_WEAKER",
            "emoji": "\U0001f7e0",
            "description": "Skill reduces cost but also reduces quality",
        }
    # quality_delta <= 0 and cost_delta_pct >= 0
    return {
        "classification": "PARETO_WORSE",
        "emoji": "\U0001f534",
        "description": "Skill increases cost without improving quality",
    }


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


def _execute_eval_pair(
    eval_case: EvalCase,
    skill_path: Path,
    evals_dir: Path,
    run_index: int,
    timeout: int,
    runner: Optional[AgentRunner] = None,
) -> tuple[RunPairResult, GradingResult, GradingResult]:
    """Run an eval case with and without the skill, grade both outputs."""
    if runner is None:
        runner = get_runner("claude")

    # Set up separate workspaces for with-skill and without-skill runs.
    # Using independent workspaces prevents contamination — without-skill
    # should not see skill scripts/SKILL.md that were copied for with-skill.
    with tempfile.TemporaryDirectory(prefix="skill-eval-with-") as with_tmpdir, \
         tempfile.TemporaryDirectory(prefix="skill-eval-without-") as without_tmpdir:
        with_workspace = Path(with_tmpdir)
        without_workspace = Path(without_tmpdir)

        # Copy eval case files into both workspaces
        for ws in (with_workspace, without_workspace):
            for rel_file in eval_case.files:
                src = evals_dir / rel_file
                dst = ws / Path(rel_file).name
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

        # Copy skill resource directories into with-skill workspace only,
        # so the agent can access scripts/, references/, and assets/ as
        # described in SKILL.md.
        if skill_path:
            _skill = Path(skill_path)
            for subdir in ("scripts", "references", "assets"):
                src_dir = _skill / subdir
                if src_dir.is_dir():
                    dst_dir = with_workspace / subdir
                    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
            # Also copy SKILL.md so the agent can read it if needed
            _skill_md = _skill / "SKILL.md"
            if _skill_md.is_file():
                shutil.copy2(_skill_md, with_workspace / "SKILL.md")

        # Run WITH skill
        with_stdout, with_stderr, with_rc, with_elapsed = runner.run_prompt(
            eval_case.prompt,
            skill_path=str(skill_path),
            workspace_dir=str(with_workspace),
            timeout=timeout,
            output_format="stream-json",
        )
        with_parsed = runner.parse_output(with_stdout)

        # Run WITHOUT skill (clean workspace — no skill files)
        without_stdout, without_stderr, without_rc, without_elapsed = runner.run_prompt(
            eval_case.prompt,
            skill_path=None,
            workspace_dir=str(without_workspace),
            timeout=timeout,
            output_format="stream-json",
        )
        without_parsed = runner.parse_output(without_stdout)

    # Grade both outputs
    with_text = with_parsed["text"]
    without_text = without_parsed["text"]

    with_results, with_pass_rate = grade_output(with_text, eval_case.assertions, timeout=timeout)
    without_results, without_pass_rate = grade_output(without_text, eval_case.assertions, timeout=timeout)

    with_grading = GradingResult(
        eval_id=eval_case.id,
        run_index=run_index,
        assertion_results=[r.to_dict() for r in with_results],
        pass_rate=with_pass_rate,
        summary=f"With skill: {with_pass_rate:.0%} assertions passed",
        execution_metrics={
            "tool_calls": len(with_parsed["tool_calls"]),
            "token_counts": with_parsed["token_counts"],
        },
        timing={"elapsed_seconds": with_elapsed},
        raw_output=with_text[:2000],
    )

    without_grading = GradingResult(
        eval_id=eval_case.id,
        run_index=run_index,
        assertion_results=[r.to_dict() for r in without_results],
        pass_rate=without_pass_rate,
        summary=f"Without skill: {without_pass_rate:.0%} assertions passed",
        execution_metrics={
            "tool_calls": len(without_parsed["tool_calls"]),
            "token_counts": without_parsed["token_counts"],
        },
        timing={"elapsed_seconds": without_elapsed},
        raw_output=without_text[:2000],
    )

    pair = RunPairResult(
        eval_id=eval_case.id,
        run_index=run_index,
        with_skill=with_grading.to_dict(),
        without_skill=without_grading.to_dict(),
        delta_pass_rate=with_pass_rate - without_pass_rate,
    )

    return pair, with_grading, without_grading


def _aggregate_benchmark(
    skill_name: str,
    skill_path: str,
    eval_cases: list[EvalCase],
    pairs: list[RunPairResult],
    gradings: list[GradingResult],
    runs_per_eval: int,
) -> BenchmarkReport:
    """Compute aggregated benchmark statistics and 4-dimension scores."""

    with_gradings = [g for g in gradings if "With skill" in g.summary]
    without_gradings = [g for g in gradings if "Without skill" in g.summary]

    # Pass rates
    with_pass_rates = [g.pass_rate for g in with_gradings]
    without_pass_rates = [g.pass_rate for g in without_gradings]

    mean_with = _mean(with_pass_rates)
    mean_without = _mean(without_pass_rates)
    std_with = _stddev(with_pass_rates)
    std_without = _stddev(without_pass_rates)

    # Token counts — output only (backward-compat "mean_tokens")
    with_output_tokens = [
        g.execution_metrics.get("token_counts", {}).get("output_tokens", 0)
        for g in with_gradings
    ]
    without_output_tokens = [
        g.execution_metrics.get("token_counts", {}).get("output_tokens", 0)
        for g in without_gradings
    ]

    # Token counts — input
    with_input_tokens = [
        g.execution_metrics.get("token_counts", {}).get("input_tokens", 0)
        for g in with_gradings
    ]
    without_input_tokens = [
        g.execution_metrics.get("token_counts", {}).get("input_tokens", 0)
        for g in without_gradings
    ]

    # Token counts — total (input + output)
    with_total_tokens = [
        _total_tokens(g.execution_metrics.get("token_counts", {}))
        for g in with_gradings
    ]
    without_total_tokens = [
        _total_tokens(g.execution_metrics.get("token_counts", {}))
        for g in without_gradings
    ]

    # Tool call counts
    with_tools = [g.execution_metrics.get("tool_calls", 0) for g in with_gradings]
    without_tools = [g.execution_metrics.get("tool_calls", 0) for g in without_gradings]

    # 4-dimension scores
    outcome_score = mean_with  # assertion pass rate with skill
    process_score = min(1.0, _mean(with_tools) / max(1, _mean(without_tools))) if without_tools else 1.0
    style_score = mean_with  # Use pass rate as proxy (style assertions are a subset)
    efficiency_score = _compute_efficiency(with_total_tokens, without_total_tokens, with_pass_rates, without_pass_rates)

    # Overall pass: skill must outperform or match no-skill
    passed = mean_with >= mean_without and mean_with >= 0.5

    mean_with_total = _mean(with_total_tokens)
    mean_without_total = _mean(without_total_tokens)

    run_summary = {
        "with_skill": {
            "mean_pass_rate": round(mean_with, 4),
            "stddev_pass_rate": round(std_with, 4),
            "mean_tokens": round(_mean(with_output_tokens), 1),
            "mean_input_tokens": round(_mean(with_input_tokens), 1),
            "mean_output_tokens": round(_mean(with_output_tokens), 1),
            "mean_total_tokens": round(mean_with_total, 1),
            "mean_tool_calls": round(_mean(with_tools), 1),
        },
        "without_skill": {
            "mean_pass_rate": round(mean_without, 4),
            "stddev_pass_rate": round(std_without, 4),
            "mean_tokens": round(_mean(without_output_tokens), 1),
            "mean_input_tokens": round(_mean(without_input_tokens), 1),
            "mean_output_tokens": round(_mean(without_output_tokens), 1),
            "mean_total_tokens": round(mean_without_total, 1),
            "mean_tool_calls": round(_mean(without_tools), 1),
        },
        "delta": {
            "pass_rate": round(mean_with - mean_without, 4),
            "tokens": round(_mean(with_output_tokens) - _mean(without_output_tokens), 1),
            "total_tokens": round(mean_with_total - mean_without_total, 1),
            "input_tokens": round(_mean(with_input_tokens) - _mean(without_input_tokens), 1),
            "tool_calls": round(_mean(with_tools) - _mean(without_tools), 1),
        },
    }

    # Cost-efficiency Pareto classification
    if mean_without_total > 0:
        quality_delta = mean_with - mean_without
        cost_delta_pct = ((mean_with_total - mean_without_total) / mean_without_total) * 100
        ce = classify_cost_efficiency(quality_delta, cost_delta_pct)
        run_summary["cost_efficiency"] = {
            "quality_delta": round(quality_delta, 4),
            "cost_delta_pct": round(cost_delta_pct, 1),
            "classification": ce["classification"],
            "emoji": ce["emoji"],
            "description": ce["description"],
        }

    # Estimated dollar cost
    cost_estimate = estimate_eval_cost(
        with_input=_mean(with_input_tokens),
        with_output=_mean(with_output_tokens),
        without_input=_mean(without_input_tokens),
        without_output=_mean(without_output_tokens),
        num_evals=len(eval_cases),
        runs_per_eval=runs_per_eval,
    )
    run_summary["estimated_cost"] = cost_estimate

    scores = {
        "outcome": round(outcome_score, 4),
        "process": round(process_score, 4),
        "style": round(style_score, 4),
        "efficiency": round(efficiency_score, 4),
        "overall": round((outcome_score + process_score + style_score + efficiency_score) / 4, 4),
    }

    return BenchmarkReport(
        skill_name=skill_name,
        skill_path=skill_path,
        eval_count=len(eval_cases),
        runs_per_eval=runs_per_eval,
        metadata={
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        runs=[p.to_dict() for p in pairs],
        run_summary=run_summary,
        scores=scores,
        passed=passed,
    )


def _compute_efficiency(
    with_tokens: list[int],
    without_tokens: list[int],
    with_pass_rates: list[float],
    without_pass_rates: list[float],
) -> float:
    """Compute efficiency score: higher pass rate per token is better."""
    if not with_tokens or not without_tokens:
        return 0.5

    mean_with_t = _mean(with_tokens) or 1
    mean_without_t = _mean(without_tokens) or 1
    mean_with_p = _mean(with_pass_rates)
    mean_without_p = _mean(without_pass_rates)

    # Efficiency = pass_rate / tokens (normalized)
    with_eff = mean_with_p / mean_with_t
    without_eff = mean_without_p / mean_without_t if mean_without_p > 0 else 0

    if without_eff == 0:
        return 1.0 if with_eff > 0 else 0.5

    ratio = with_eff / without_eff
    # Clamp to [0, 1] range using sigmoid-like transform
    return min(1.0, max(0.0, ratio / (1.0 + ratio) * 2))


def _total_tokens(token_counts: dict) -> int:
    """Return input_tokens + output_tokens (cache tokens excluded)."""
    return token_counts.get("input_tokens", 0) + token_counts.get("output_tokens", 0)


def _mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stddev(values: list[float | int]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _print_functional_report(report: BenchmarkReport) -> None:
    """Print a human-readable functional evaluation report."""
    w = 58

    print(f"\n{'=' * w}")
    print(f"  Functional Evaluation Report")
    print(f"{'=' * w}")
    print(f"  Skill:      {report.skill_name}")
    print(f"  Eval cases: {report.eval_count}")
    print(f"  Runs/eval:  {report.runs_per_eval}")
    print(f"{'─' * w}")

    rs = report.run_summary
    ws = rs.get("with_skill", {})
    wos = rs.get("without_skill", {})
    delta = rs.get("delta", {})

    print(f"  With skill:    {ws.get('mean_pass_rate', 0):.1%} pass rate")
    print(f"  Without skill: {wos.get('mean_pass_rate', 0):.1%} pass rate")
    dp = delta.get("pass_rate", 0)
    sign = "+" if dp >= 0 else ""
    print(f"  Delta:         {sign}{dp:.1%}")
    print(f"{'─' * w}")

    # Token Usage section (skip when all zeros, e.g. dry-run)
    ws_total = ws.get("mean_total_tokens", 0)
    wos_total = wos.get("mean_total_tokens", 0)
    if ws_total or wos_total:
        ws_in = ws.get("mean_input_tokens", 0)
        ws_out = ws.get("mean_output_tokens", 0)
        wos_in = wos.get("mean_input_tokens", 0)
        wos_out = wos.get("mean_output_tokens", 0)
        dt = delta.get("total_tokens", 0)
        dt_sign = "+" if dt >= 0 else ""
        print(f"  Token Usage (mean per run):")
        print(f"    With skill:    {ws_total:,.0f} total  ({ws_in:,.0f} in / {ws_out:,.0f} out)")
        print(f"    Without skill: {wos_total:,.0f} total  ({wos_in:,.0f} in / {wos_out:,.0f} out)")
        print(f"    Delta:         {dt_sign}{dt:,.0f} total")
        print(f"{'─' * w}")

    # Cost Efficiency section
    ce = rs.get("cost_efficiency")
    if ce:
        qd = ce["quality_delta"]
        cd = ce["cost_delta_pct"]
        qd_sign = "+" if qd >= 0 else ""
        cd_sign = "+" if cd >= 0 else ""
        print(f"  Cost Efficiency:")
        print(f"    Classification: {ce['emoji']} {ce['classification']}")
        print(f"    Quality delta:  {qd_sign}{qd:.2f}")
        print(f"    Cost delta:     {cd_sign}{cd:.1f}%")
        print(f"    \u2192 {ce['description']}")
        print(f"{'─' * w}")

    # Estimated Cost section
    ec = rs.get("estimated_cost")
    if ec and ec.get("total_cost", 0) > 0:
        print(f"  Estimated Cost (based on {ec.get('model', 'sonnet')} pricing):")
        print(f"    Total:         {format_cost(ec['total_cost'])}")
        wc = ec.get("with_skill_per_run", {})
        woc = ec.get("without_skill_per_run", {})
        if wc and woc:
            print(f"    With skill:    {format_cost(wc['total_cost'])} per run")
            print(f"    Without skill: {format_cost(woc['total_cost'])} per run")
        print(f"    Runs:          {ec.get('total_runs', 0)} ({report.eval_count} evals \u00d7 {report.runs_per_eval} runs \u00d7 2)")
        print(f"{'─' * w}")

    scores = report.scores
    print(f"  Scores (0-1):")
    print(f"    Outcome:    {scores.get('outcome', 0):.2f}")
    print(f"    Process:    {scores.get('process', 0):.2f}")
    print(f"    Style:      {scores.get('style', 0):.2f}")
    print(f"    Efficiency: {scores.get('efficiency', 0):.2f}")
    print(f"    Overall:    {scores.get('overall', 0):.2f}")
    print(f"{'─' * w}")

    if report.passed:
        print(f"  Result: PASSED")
    else:
        print(f"  Result: FAILED")
    print(f"{'=' * w}\n")
