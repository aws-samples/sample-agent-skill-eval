"""Trigger reliability evaluation orchestrator.

Tests whether a skill's description causes the skill to activate (or not)
for a set of queries, measuring trigger precision and recall.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from skill_eval.eval_schemas import TriggerQuery, TriggerQueryResult, TriggerReport
from skill_eval.agent_runner import AgentRunner, AgentNotAvailableError, get_runner


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_trigger_eval(
    skill_path: str,
    queries_path: Optional[str] = None,
    runs_per_query: int = 3,
    format: str = "text",
    output_path: Optional[str] = None,
    timeout: int = 60,
    dry_run: bool = False,
    agent: str = "claude",
) -> int:
    """Run trigger reliability evaluation on a skill.

    Args:
        skill_path: Path to the skill directory.
        queries_path: Path to eval_queries.json (default: <skill_path>/evals/eval_queries.json).
        runs_per_query: Number of times to run each query.
        format: Output format ("text" or "json").
        output_path: Path to write trigger report.
        timeout: Timeout per claude invocation in seconds.
        dry_run: If True, load and validate queries but do not execute.
        agent: Name of the registered agent runner (default: "claude").

    Returns:
        Exit code: 0 = all passed, 1 = some failed, 2 = error.
    """
    path = Path(skill_path).resolve()

    # Load queries
    queries_file = Path(queries_path) if queries_path else path / "evals" / "eval_queries.json"
    try:
        queries = _load_queries(queries_file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        print(f"Error loading queries: {e}", file=sys.stderr)
        return 2

    if not queries:
        print("No trigger queries found.", file=sys.stderr)
        return 2

    if dry_run:
        print(f"Dry run: loaded {len(queries)} trigger query(ies) from {queries_file}")
        for q in queries:
            label = "should trigger" if q.should_trigger else "should NOT trigger"
            print(f"  - [{label}] {q.query[:80]}")
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

    # Read skill name
    skill_name = _read_skill_name(path) or path.name

    # Run trigger checks
    query_results: list[TriggerQueryResult] = []
    for query in queries:
        result = _run_trigger_query(query, path, runs_per_query, timeout, runner=runner)
        query_results.append(result)

    # Build report
    report = _build_trigger_report(skill_name, str(path), query_results)

    # Write output file
    if output_path:
        out_file = Path(output_path)
    else:
        out_file = path / "evals" / "trigger_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report.to_json())

    # Print
    if format == "json":
        print(report.to_json())
    else:
        _print_trigger_report(report)

    return 0 if report.passed else 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_queries(queries_file: Path) -> list[TriggerQuery]:
    """Load and validate trigger queries from eval_queries.json."""
    if not queries_file.is_file():
        raise FileNotFoundError(f"Queries file not found: {queries_file}")

    data = json.loads(queries_file.read_text())
    if not isinstance(data, list):
        raise ValueError("eval_queries.json must be a JSON array")

    queries = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"eval_queries.json[{i}] must be an object")
        if "query" not in item or "should_trigger" not in item:
            raise ValueError(
                f"eval_queries.json[{i}] missing required field 'query' or 'should_trigger'"
            )
        queries.append(TriggerQuery.from_dict(item))
    return queries


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


def _run_trigger_query(
    query: TriggerQuery,
    skill_path: Path,
    runs: int,
    timeout: int,
    runner: Optional[AgentRunner] = None,
) -> TriggerQueryResult:
    """Run a single trigger query N times and measure activation rate."""
    if runner is None:
        runner = get_runner("claude")

    trigger_count = 0
    all_input_tokens: list[int] = []
    all_output_tokens: list[int] = []

    for _ in range(runs):
        stdout, stderr, rc, elapsed = runner.run_prompt(
            query.query,
            skill_path=str(skill_path),
            timeout=timeout,
            output_format="stream-json",
        )
        if rc == 0 and stdout.strip():
            parsed = runner.parse_output(stdout)
            triggered = _detect_skill_trigger_from_parsed(parsed, skill_path)
            if triggered:
                trigger_count += 1
            tc = parsed["token_counts"]
            all_input_tokens.append(tc.get("input_tokens", 0))
            all_output_tokens.append(tc.get("output_tokens", 0))

    trigger_rate = trigger_count / runs if runs > 0 else 0.0

    # Token means
    mean_in = sum(all_input_tokens) / len(all_input_tokens) if all_input_tokens else 0.0
    mean_out = sum(all_output_tokens) / len(all_output_tokens) if all_output_tokens else 0.0

    # Pass/fail logic:
    # - should_trigger queries: pass if trigger_rate >= 0.5
    # - should_not_trigger queries: pass if trigger_rate < 0.5
    if query.should_trigger:
        passed = trigger_rate >= 0.5
    else:
        passed = trigger_rate < 0.5

    return TriggerQueryResult(
        query=query.query,
        should_trigger=query.should_trigger,
        trigger_count=trigger_count,
        run_count=runs,
        trigger_rate=round(trigger_rate, 4),
        passed=passed,
        mean_input_tokens=round(mean_in, 1),
        mean_output_tokens=round(mean_out, 1),
        mean_total_tokens=round(mean_in + mean_out, 1),
    )


def _detect_skill_trigger_from_parsed(parsed: dict, skill_path: Path) -> bool:
    """Detect whether the skill was activated from pre-parsed stream data.

    Looks for:
    1. Read tool_use referencing SKILL.md
    2. Skill tool_use matching skill name
    3. Any reference to the skill path in tool calls
    """
    skill_name = skill_path.name
    skill_md = "SKILL.md"

    for tool_call in parsed.get("tool_calls", []):
        name = tool_call.get("name", "")
        input_data = tool_call.get("input", {})

        # Check for Skill tool invocation
        if name.lower() == "skill":
            return True

        # Check for Read of SKILL.md
        if name.lower() == "read":
            file_path = str(input_data.get("file_path", ""))
            if skill_md in file_path:
                return True

        # Check for any tool referencing the skill path
        input_str = json.dumps(input_data)
        if skill_name in input_str:
            return True

    # Also check text output for skill activation markers
    text = parsed.get("text", "")
    if f"skill:{skill_name}" in text.lower() or f"using {skill_name}" in text.lower():
        return True

    return False


def _detect_skill_trigger(stream_output: str, skill_path: Path, runner: Optional[AgentRunner] = None) -> bool:
    """Detect whether the skill was activated in stream-json output.

    Thin wrapper around _detect_skill_trigger_from_parsed for backward
    compatibility with existing callers/tests.
    """
    if runner is None:
        runner = get_runner("claude")
    parsed = runner.parse_output(stream_output)
    return _detect_skill_trigger_from_parsed(parsed, skill_path)


def _build_trigger_report(
    skill_name: str,
    skill_path: str,
    query_results: list[TriggerQueryResult],
) -> TriggerReport:
    """Build aggregated trigger report."""
    should_trigger = [r for r in query_results if r.should_trigger]
    should_not_trigger = [r for r in query_results if not r.should_trigger]

    trigger_pass = sum(1 for r in should_trigger if r.passed)
    no_trigger_pass = sum(1 for r in should_not_trigger if r.passed)
    total_pass = trigger_pass + no_trigger_pass
    total = len(query_results)

    all_passed = all(r.passed for r in query_results)

    # Mean total tokens across all queries
    all_totals = [r.mean_total_tokens for r in query_results]
    mean_total_tokens_per_run = (
        round(sum(all_totals) / len(all_totals), 1) if all_totals else 0.0
    )

    summary = {
        "total_queries": total,
        "passed": total_pass,
        "failed": total - total_pass,
        "trigger_precision": round(trigger_pass / len(should_trigger), 4) if should_trigger else 1.0,
        "no_trigger_precision": round(no_trigger_pass / len(should_not_trigger), 4) if should_not_trigger else 1.0,
        "mean_total_tokens_per_run": mean_total_tokens_per_run,
    }

    return TriggerReport(
        skill_name=skill_name,
        skill_path=skill_path,
        query_results=[r.to_dict() for r in query_results],
        summary=summary,
        passed=all_passed,
    )


def _print_trigger_report(report: TriggerReport) -> None:
    """Print a human-readable trigger evaluation report."""
    w = 58

    print(f"\n{'=' * w}")
    print(f"  Trigger Reliability Report")
    print(f"{'=' * w}")
    print(f"  Skill: {report.skill_name}")
    print(f"{'─' * w}")

    summary = report.summary
    print(f"  Queries:    {summary.get('total_queries', 0)}")
    print(f"  Passed:     {summary.get('passed', 0)}")
    print(f"  Failed:     {summary.get('failed', 0)}")
    print(f"  Trigger precision:    {summary.get('trigger_precision', 0):.1%}")
    print(f"  No-trigger precision: {summary.get('no_trigger_precision', 0):.1%}")
    print(f"{'─' * w}")

    for qr in report.query_results:
        status = "PASS" if qr.get("passed") else "FAIL"
        expected = "trigger" if qr.get("should_trigger") else "no-trigger"
        rate = qr.get("trigger_rate", 0)
        query_text = qr.get("query", "")[:50]
        mean_tok = qr.get("mean_total_tokens", 0)
        tok_str = f" mean={mean_tok:.0f} tok" if mean_tok else ""
        print(f"  [{status}] ({expected}) rate={rate:.0%}{tok_str} {query_text}")

    print(f"{'─' * w}")

    # Token summary (omit when all zeros)
    mean_tok_run = summary.get("mean_total_tokens_per_run", 0)
    if mean_tok_run:
        print(f"  Mean tokens per run: {mean_tok_run:,.0f}")
        print(f"{'─' * w}")

    if report.passed:
        print(f"  Result: PASSED")
    else:
        print(f"  Result: FAILED")
    print(f"{'=' * w}\n")
