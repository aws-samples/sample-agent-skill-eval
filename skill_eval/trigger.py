"""Trigger reliability evaluation orchestrator.

Tests whether a skill's description causes the skill to activate (or not)
for a set of queries, measuring trigger precision and recall.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from skill_eval.cost import estimate_trigger_cost, format_cost
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
            signal = _classify_trigger_signal(parsed, skill_path)
            # For should_trigger=false queries, only count strong (tool-based)
            # signals as triggers.  Text-only mentions are too noisy for
            # negative queries — an agent may casually mention a skill name
            # (e.g. "text-summary", "compliance") without intending to use it.
            if query.should_trigger:
                triggered = signal != "none"
            else:
                triggered = signal == "tool"
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

    Returns True if a tool-based signal (strong) or a text-based signal
    (weak) is found.  Use ``_classify_trigger_signal`` when you need to
    distinguish the two.

    Looks for:
    1. Read tool_use referencing SKILL.md
    2. Skill tool_use matching skill name
    3. Bash/shell commands that *execute* skill scripts (not just reference paths)
    4. Any tool explicitly invoking the skill by name
    5. (Weak) Skill name mentioned in text output
    """
    signal = _classify_trigger_signal(parsed, skill_path)
    return signal != "none"


def _classify_trigger_signal(parsed: dict, skill_path: Path) -> str:
    """Classify the strength of a trigger signal.

    Returns:
        "tool"  — strong signal: agent used a tool to activate the skill
                  (Read SKILL.md, Bash script execution, Skill tool, etc.)
        "text"  — weak signal: agent mentioned the skill name in its text
                  output without an explicit tool invocation
        "none"  — no trigger detected
    """
    skill_name = skill_path.name
    skill_md = "SKILL.md"

    # Build script file names from the skill's scripts/ directory
    scripts_dir = skill_path / "scripts"
    script_files: set[str] = set()      # Full filenames: "weather.py"
    script_stems: set[str] = set()      # Stems only: "weather"
    if scripts_dir.is_dir():
        for f in scripts_dir.iterdir():
            if f.is_file():
                script_files.add(f.name)
                script_stems.add(f.stem)

    # Execution patterns for Bash command matching
    # These indicate the script is being *run*, not just referenced in a path
    import re as _re
    _EXEC_PREFIXES = (
        "python3 ", "python ", "bash ", "sh ", "./", "node ",
        "ruby ", "perl ", "php ",
    )

    for tool_call in parsed.get("tool_calls", []):
        name = tool_call.get("name", "")
        input_data = tool_call.get("input", {})

        # Check for Skill tool invocation
        if name.lower() == "skill":
            return "tool"

        # Check for Read of SKILL.md
        if name.lower() == "read":
            file_path = str(input_data.get("file_path", ""))
            if skill_md in file_path:
                return "tool"

        # Check for Bash/shell commands executing skill scripts
        if name.lower() in ("bash", "shell", "terminal"):
            command = str(input_data.get("command", ""))
            command_lower = command.lower()

            # Check 1: Command executes a script file from the skill
            # e.g. "python3 scripts/weather.py --city NYC"
            for script_file in script_files:
                # Must be preceded by an execution context, not just in a path
                if script_file.lower() in command_lower:
                    # Verify it looks like execution, not just ls/cat of a directory
                    for prefix in _EXEC_PREFIXES:
                        if prefix in command_lower:
                            return "tool"
                    # Also match direct script execution: "./scripts/weather.py"
                    if f"scripts/{script_file.lower()}" in command_lower:
                        return "tool"

            # Check 2: Command uses the skill name as a CLI command
            # e.g. "skill-eval audit ." — skill_name is the first token or after pipe
            # Use word boundary to avoid matching paths like examples/data-analysis/
            skill_cmd_pattern = _re.compile(
                r'(?:^|[|;&]\s*)' + _re.escape(skill_name) + r'(?:\s|$)',
                _re.IGNORECASE,
            )
            if skill_cmd_pattern.search(command):
                return "tool"

            # Check 3: Command uses underscore variant as a module
            # e.g. "python3 -m data_analysis --file test.csv"
            underscore_name = skill_name.replace("-", "_")
            module_pattern = _re.compile(
                r'-m\s+' + _re.escape(underscore_name) + r'(?:\s|$|\.|:)',
                _re.IGNORECASE,
            )
            if module_pattern.search(command):
                return "tool"

            # Check 4: Full skill path explicitly in command
            if str(skill_path) in command:
                return "tool"

    # --- Text-based detection (weak signal) ---
    text = parsed.get("text", "")
    text_lower = text.lower()
    skill_name_lower = skill_name.lower()

    # Direct skill references — intentional activation phrases
    if f"skill:{skill_name_lower}" in text_lower or f"using {skill_name_lower}" in text_lower:
        return "text"

    # When skill is injected via --append-system-prompt, the agent may
    # reference the skill by name or mention its scripts/rules without
    # explicitly "activating" it through a tool call.  Detect broader
    # references to the skill name in the output text.
    # Use word-boundary matching to avoid false positives on partial names.
    import re as _re
    # Match skill name as a standalone term (hyphenated names are common)
    skill_word_pattern = _re.compile(
        r'\b' + _re.escape(skill_name_lower) + r'\b',
        _re.IGNORECASE,
    )
    if skill_word_pattern.search(text):
        return "text"

    # Also detect references to skill scripts in the text, using path-level
    # matching (scripts/{filename}) to avoid false positives on common names
    # like "check.py" or "main.py".
    for script_file in script_files:
        if f"scripts/{script_file.lower()}" in text_lower:
            return "text"

    return "none"


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

    # Estimated dollar cost
    if all_totals:
        all_inputs = [r.mean_input_tokens for r in query_results]
        all_outputs = [r.mean_output_tokens for r in query_results]
        mean_in = sum(all_inputs) / len(all_inputs) if all_inputs else 0
        mean_out = sum(all_outputs) / len(all_outputs) if all_outputs else 0
        cost_est = estimate_trigger_cost(
            mean_input_tokens=mean_in,
            mean_output_tokens=mean_out,
            num_queries=total,
            runs_per_query=1,  # already aggregated per query
        )
        summary["estimated_cost"] = cost_est

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
        # Estimated cost
        ec = summary.get("estimated_cost")
        if ec and ec.get("total_cost", 0) > 0:
            print(f"  Estimated cost:      {format_cost(ec['total_cost'])} ({ec.get('model', 'sonnet')} pricing)")
        print(f"{'─' * w}")

    if report.passed:
        print(f"  Result: PASSED")
    else:
        print(f"  Result: FAILED")
    print(f"{'=' * w}\n")
