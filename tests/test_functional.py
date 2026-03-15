"""Tests for functional evaluation module."""

import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from skill_eval.functional import (
    run_functional_eval,
    _load_evals,
    _read_skill_name,
    _aggregate_benchmark,
    _execute_eval_pair,
    _mean,
    _stddev,
    _compute_efficiency,
    _print_functional_report,
    classify_cost_efficiency,
)
from skill_eval.eval_schemas import (
    EvalCase, GradingResult, RunPairResult, BenchmarkReport,
)
from skill_eval.agent_runner import AgentNotAvailableError, ClaudeRunner


FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadEvals:
    """Test evals.json loading and validation."""

    def test_load_valid_evals(self):
        evals_file = FIXTURES / "eval-skill" / "evals" / "evals.json"
        cases = _load_evals(evals_file)
        assert len(cases) == 3
        assert cases[0].id == "csv-summary"
        assert cases[1].id == "csv-row-count"
        assert cases[2].id == "csv-json-columns"

    def test_load_evals_with_assertions(self):
        evals_file = FIXTURES / "eval-skill" / "evals" / "evals.json"
        cases = _load_evals(evals_file)
        assert len(cases[0].assertions) == 4
        assert "contains 'name'" in cases[0].assertions

    def test_load_evals_with_files(self):
        evals_file = FIXTURES / "eval-skill" / "evals" / "evals.json"
        cases = _load_evals(evals_file)
        assert "files/sample.csv" in cases[0].files

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            _load_evals(Path("/nonexistent/evals.json"))

    def test_load_invalid_json(self, tmp_path):
        bad_file = tmp_path / "evals.json"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            _load_evals(bad_file)

    def test_load_not_array(self, tmp_path):
        bad_file = tmp_path / "evals.json"
        bad_file.write_text('{"not": "array"}')
        with pytest.raises(ValueError, match="must be a JSON array"):
            _load_evals(bad_file)

    def test_load_missing_required_fields(self, tmp_path):
        bad_file = tmp_path / "evals.json"
        bad_file.write_text('[{"id": "test"}]')
        with pytest.raises(ValueError, match="missing required field"):
            _load_evals(bad_file)

    def test_load_non_object_item(self, tmp_path):
        bad_file = tmp_path / "evals.json"
        bad_file.write_text('["not an object"]')
        with pytest.raises(ValueError, match="must be an object"):
            _load_evals(bad_file)


class TestReadSkillName:
    """Test skill name extraction from SKILL.md."""

    def test_read_skill_name(self):
        name = _read_skill_name(FIXTURES / "eval-skill")
        assert name == "eval-skill"

    def test_read_skill_name_good_skill(self):
        name = _read_skill_name(FIXTURES / "good-skill")
        assert name == "good-skill"

    def test_read_skill_name_missing(self, tmp_path):
        name = _read_skill_name(tmp_path)
        assert name is None

    def test_read_skill_name_no_frontmatter(self):
        name = _read_skill_name(FIXTURES / "no-frontmatter")
        assert name is None


class TestMathHelpers:
    """Test _mean and _stddev helpers."""

    def test_mean_normal(self):
        assert _mean([1.0, 2.0, 3.0]) == 2.0

    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_mean_single(self):
        assert _mean([5.0]) == 5.0

    def test_stddev_normal(self):
        std = _stddev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert 2.1 < std < 2.2  # sample stddev ~2.138

    def test_stddev_empty(self):
        assert _stddev([]) == 0.0

    def test_stddev_single(self):
        assert _stddev([5.0]) == 0.0

    def test_stddev_uniform(self):
        assert _stddev([3.0, 3.0, 3.0]) == 0.0


class TestComputeEfficiency:
    """Test efficiency score computation."""

    def test_equal_efficiency(self):
        score = _compute_efficiency([100], [100], [0.8], [0.8])
        assert score == 1.0  # Equal efficiency maps to 1.0 (good)

    def test_better_with_skill(self):
        # Higher pass rate, same tokens -> better efficiency
        score = _compute_efficiency([100], [100], [1.0], [0.5])
        assert score > 0.5

    def test_empty_tokens(self):
        score = _compute_efficiency([], [], [], [])
        assert score == 0.5

    def test_zero_without_pass(self):
        score = _compute_efficiency([100], [100], [0.8], [0.0])
        assert score == 1.0


class TestAggregateBenchmark:
    """Test benchmark aggregation."""

    def test_basic_aggregation(self):
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=0.2)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.8,
                summary="With skill: 80% assertions passed",
                execution_metrics={"tool_calls": 3, "token_counts": {"input_tokens": 100, "output_tokens": 50}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.6,
                summary="Without skill: 60% assertions passed",
                execution_metrics={"tool_calls": 2, "token_counts": {"input_tokens": 80, "output_tokens": 40}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        assert report.skill_name == "test"
        assert report.eval_count == 1
        assert report.passed is True  # 0.8 >= 0.6 and >= 0.5
        assert "outcome" in report.scores
        assert "overall" in report.scores
        assert report.scores["outcome"] == 0.8

    def test_failing_aggregation(self):
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=-0.3)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.3,
                summary="With skill: 30% assertions passed",
                execution_metrics={"tool_calls": 1, "token_counts": {"input_tokens": 50, "output_tokens": 20}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.6,
                summary="Without skill: 60% assertions passed",
                execution_metrics={"tool_calls": 2, "token_counts": {"input_tokens": 80, "output_tokens": 40}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        assert report.passed is False  # 0.3 < 0.5


class TestDryRun:
    """Test dry-run mode."""

    def test_dry_run_loads_evals(self, capsys):
        ret = run_functional_eval(
            str(FIXTURES / "eval-skill"),
            dry_run=True,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "csv-summary" in captured.out
        assert "csv-row-count" in captured.out

    def test_dry_run_missing_evals(self):
        ret = run_functional_eval(
            str(FIXTURES / "good-skill"),  # No evals dir
            dry_run=True,
        )
        assert ret == 2  # Error: no evals file


class TestRunFunctionalEvalErrorCases:
    """Test error handling in run_functional_eval."""

    def test_missing_evals_file(self):
        ret = run_functional_eval("/nonexistent/path")
        assert ret == 2

    def test_invalid_evals_path(self, tmp_path):
        bad_evals = tmp_path / "evals.json"
        bad_evals.write_text("not json")
        ret = run_functional_eval(str(tmp_path), evals_path=str(bad_evals))
        assert ret == 2

    def test_no_claude_available(self):
        """Should return exit 2 if claude is not on PATH."""
        with patch.object(ClaudeRunner, "check_available",
                          side_effect=AgentNotAvailableError("claude")):
            ret = run_functional_eval(str(FIXTURES / "eval-skill"))
            assert ret == 2


class TestPrintFunctionalReport:
    """Test report printing."""

    def test_print_passing_report(self, capsys):
        report = BenchmarkReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            eval_count=2,
            runs_per_eval=1,
            run_summary={
                "with_skill": {"mean_pass_rate": 0.9},
                "without_skill": {"mean_pass_rate": 0.5},
                "delta": {"pass_rate": 0.4},
            },
            scores={"outcome": 0.9, "process": 0.8, "style": 0.85, "efficiency": 0.7, "overall": 0.8125},
            passed=True,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "test-skill" in captured.out
        assert "PASSED" in captured.out
        assert "Outcome" in captured.out

    def test_print_failing_report(self, capsys):
        report = BenchmarkReport(
            skill_name="bad-skill",
            skill_path="/tmp/bad",
            eval_count=1,
            runs_per_eval=1,
            run_summary={
                "with_skill": {"mean_pass_rate": 0.3},
                "without_skill": {"mean_pass_rate": 0.5},
                "delta": {"pass_rate": -0.2},
            },
            scores={"outcome": 0.3, "process": 0.5, "style": 0.3, "efficiency": 0.4, "overall": 0.375},
            passed=False,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_print_token_section(self, capsys):
        """Token Usage section should appear when token data is available."""
        report = BenchmarkReport(
            skill_name="tok-skill",
            skill_path="/tmp/tok",
            eval_count=1,
            runs_per_eval=1,
            run_summary={
                "with_skill": {
                    "mean_pass_rate": 0.9,
                    "mean_input_tokens": 1200,
                    "mean_output_tokens": 340,
                    "mean_total_tokens": 1540,
                },
                "without_skill": {
                    "mean_pass_rate": 0.5,
                    "mean_input_tokens": 980,
                    "mean_output_tokens": 290,
                    "mean_total_tokens": 1270,
                },
                "delta": {"pass_rate": 0.4, "total_tokens": 270},
            },
            scores={"outcome": 0.9, "process": 0.8, "style": 0.85, "efficiency": 0.7, "overall": 0.8125},
            passed=True,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "Token Usage" in captured.out
        assert "1,540" in captured.out
        assert "1,200" in captured.out
        assert "+270" in captured.out

    def test_print_token_section_hidden_when_zero(self, capsys):
        """Token Usage section should be hidden when all token values are zero."""
        report = BenchmarkReport(
            skill_name="dry-skill",
            skill_path="/tmp/dry",
            eval_count=1,
            runs_per_eval=1,
            run_summary={
                "with_skill": {"mean_pass_rate": 0.9, "mean_total_tokens": 0},
                "without_skill": {"mean_pass_rate": 0.5, "mean_total_tokens": 0},
                "delta": {"pass_rate": 0.4},
            },
            scores={"outcome": 0.9, "process": 0.8, "style": 0.85, "efficiency": 0.7, "overall": 0.8125},
            passed=True,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "Token Usage" not in captured.out


class TestAggregateBenchmarkTokenFields:
    """Test that _aggregate_benchmark populates token fields in run_summary."""

    def test_run_summary_token_fields(self):
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=0.2)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.8,
                summary="With skill: 80% assertions passed",
                execution_metrics={"tool_calls": 3, "token_counts": {"input_tokens": 1200, "output_tokens": 340}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.6,
                summary="Without skill: 60% assertions passed",
                execution_metrics={"tool_calls": 2, "token_counts": {"input_tokens": 980, "output_tokens": 290}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        rs = report.run_summary

        # New token fields present
        assert rs["with_skill"]["mean_input_tokens"] == 1200.0
        assert rs["with_skill"]["mean_output_tokens"] == 340.0
        assert rs["with_skill"]["mean_total_tokens"] == 1540.0
        assert rs["without_skill"]["mean_input_tokens"] == 980.0
        assert rs["without_skill"]["mean_total_tokens"] == 1270.0

        # Delta token fields
        assert rs["delta"]["total_tokens"] == 270.0
        assert rs["delta"]["input_tokens"] == 220.0

        # Backward-compat: mean_tokens (output only) preserved
        assert rs["with_skill"]["mean_tokens"] == 340.0
        assert rs["without_skill"]["mean_tokens"] == 290.0


def _make_stream_json(text: str, input_tokens: int = 100, output_tokens: int = 50) -> str:
    """Build a minimal stream-json string that parse_stream_json can handle."""
    import json as _json
    return _json.dumps({
        "type": "result",
        "result": text,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    })


class TestExecuteEvalPair:
    """Integration tests for _execute_eval_pair with mocked Claude."""

    def _eval_case(self):
        return EvalCase(
            id="test-case",
            prompt="Summarize the CSV file.",
            files=["files/sample.csv"],
            assertions=["contains 'name'", "contains 'age'"],
        )

    def _make_mock_runner(self):
        runner = MagicMock(spec=ClaudeRunner)
        runner.parse_output.side_effect = ClaudeRunner().parse_output
        return runner

    def test_execute_eval_pair_both_pass(self):
        """Both runs pass all assertions → delta == 0."""
        text = "The CSV has columns: name, age, city"
        stream = _make_stream_json(text)
        runner = self._make_mock_runner()
        runner.run_prompt.side_effect = [
            (stream, "", 0, 1.5),  # with-skill
            (stream, "", 0, 1.2),  # without-skill
        ]

        pair, with_g, without_g = _execute_eval_pair(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            run_index=0,
            timeout=30,
            runner=runner,
        )
        assert pair.delta_pass_rate == 0.0
        assert with_g.pass_rate == 1.0
        assert without_g.pass_rate == 1.0

    def test_execute_eval_pair_skill_lifts_output(self):
        """With-skill passes, without-skill fails → positive delta."""
        good = _make_stream_json("Columns: name, age, city")
        bad = _make_stream_json("I cannot read files.")
        runner = self._make_mock_runner()
        runner.run_prompt.side_effect = [
            (good, "", 0, 1.0),   # with-skill
            (bad, "", 0, 1.0),    # without-skill
        ]

        pair, with_g, without_g = _execute_eval_pair(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            run_index=0,
            timeout=30,
            runner=runner,
        )
        assert pair.delta_pass_rate > 0
        assert with_g.pass_rate == 1.0
        assert without_g.pass_rate == 0.0

    def test_execute_eval_pair_grading_result_fields(self):
        """Token counts and timing are populated."""
        stream = _make_stream_json("name age city", input_tokens=200, output_tokens=80)
        runner = self._make_mock_runner()
        runner.run_prompt.side_effect = [
            (stream, "", 0, 2.5),
            (stream, "", 0, 1.8),
        ]

        _, with_g, without_g = _execute_eval_pair(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            run_index=0,
            timeout=30,
            runner=runner,
        )
        assert with_g.execution_metrics["token_counts"]["input_tokens"] == 200
        assert with_g.execution_metrics["token_counts"]["output_tokens"] == 80
        assert with_g.timing["elapsed_seconds"] == 2.5
        assert without_g.timing["elapsed_seconds"] == 1.8

    def test_execute_eval_pair_copies_files_to_workspace(self):
        """runner.run_prompt is called exactly twice (with and without skill)."""
        stream = _make_stream_json("name age")
        runner = self._make_mock_runner()
        runner.run_prompt.side_effect = [
            (stream, "", 0, 1.0),
            (stream, "", 0, 1.0),
        ]

        _execute_eval_pair(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            run_index=0,
            timeout=30,
            runner=runner,
        )
        assert runner.run_prompt.call_count == 2
        # First call should have skill_path set, second should not
        first_kwargs = runner.run_prompt.call_args_list[0].kwargs
        second_kwargs = runner.run_prompt.call_args_list[1].kwargs
        assert first_kwargs.get("skill_path") is not None
        assert second_kwargs.get("skill_path") is None


class TestClassifyCostEfficiency:
    """Test Pareto cost-efficiency classification."""

    def test_pareto_better(self):
        """Quality up, cost down → PARETO_BETTER."""
        result = classify_cost_efficiency(0.20, -15.0)
        assert result["classification"] == "PARETO_BETTER"
        assert result["emoji"] == "\U0001f7e2"
        assert "improves quality while reducing cost" in result["description"]

    def test_pareto_better_zero_quality_negative_cost(self):
        """Quality unchanged, cost down → PARETO_BETTER."""
        result = classify_cost_efficiency(0.0, -5.0)
        assert result["classification"] == "PARETO_BETTER"

    def test_pareto_better_zero_cost(self):
        """Quality up, cost unchanged → PARETO_BETTER."""
        result = classify_cost_efficiency(0.10, 0.0)
        assert result["classification"] == "PARETO_BETTER"

    def test_pareto_better_both_zero(self):
        """quality=0, cost=0 → PARETO_BETTER (quality>=0 AND cost<=0)."""
        result = classify_cost_efficiency(0.0, 0.0)
        assert result["classification"] == "PARETO_BETTER"

    def test_tradeoff(self):
        """Quality up, cost up → TRADEOFF."""
        result = classify_cost_efficiency(0.15, 30.0)
        assert result["classification"] == "TRADEOFF"
        assert result["emoji"] == "\U0001f7e1"
        assert "improves quality but increases cost" in result["description"]

    def test_cheaper_but_weaker(self):
        """Quality down (above threshold), cost down → CHEAPER_BUT_WEAKER."""
        result = classify_cost_efficiency(-0.03, -20.0)
        assert result["classification"] == "CHEAPER_BUT_WEAKER"
        assert result["emoji"] == "\U0001f7e0"
        assert "reduces cost but also reduces quality" in result["description"]

    def test_pareto_worse(self):
        """Quality down (above threshold), cost up → PARETO_WORSE."""
        result = classify_cost_efficiency(-0.02, 10.0)
        assert result["classification"] == "PARETO_WORSE"
        assert result["emoji"] == "\U0001f534"
        assert "increases cost without improving quality" in result["description"]

    def test_reject(self):
        """Quality significantly degraded → REJECT."""
        result = classify_cost_efficiency(-0.10, -20.0)
        assert result["classification"] == "REJECT"
        assert result["emoji"] == "\U0001f534"
        assert "significantly degrades quality" in result["description"]

    def test_reject_at_threshold(self):
        """quality_delta exactly at -0.05 should be REJECT (< threshold)."""
        result = classify_cost_efficiency(-0.05, 0.0)
        assert result["classification"] == "REJECT"

    def test_not_reject_just_above_threshold(self):
        """quality_delta at -0.049 should NOT be REJECT."""
        result = classify_cost_efficiency(-0.049, 0.0)
        assert result["classification"] != "REJECT"

    def test_custom_threshold(self):
        """Custom threshold changes rejection boundary."""
        # -0.08 would not be rejected with default threshold... actually it would.
        # Use a stricter threshold: -0.10
        result = classify_cost_efficiency(-0.08, 5.0, threshold=-0.10)
        assert result["classification"] != "REJECT"
        # But with default threshold (-0.05), it would be rejected
        result2 = classify_cost_efficiency(-0.08, 5.0)
        assert result2["classification"] == "REJECT"

    def test_custom_threshold_rejects(self):
        """Custom threshold=-0.01 rejects smaller degradations."""
        result = classify_cost_efficiency(-0.02, 0.0, threshold=-0.01)
        assert result["classification"] == "REJECT"


class TestCostEfficiencyIntegration:
    """Test cost_efficiency integration into _aggregate_benchmark."""

    def test_aggregate_includes_cost_efficiency(self):
        """cost_efficiency should appear in run_summary when tokens > 0."""
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=0.2)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.8,
                summary="With skill: 80% assertions passed",
                execution_metrics={"tool_calls": 3, "token_counts": {"input_tokens": 1000, "output_tokens": 200}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.6,
                summary="Without skill: 60% assertions passed",
                execution_metrics={"tool_calls": 2, "token_counts": {"input_tokens": 1200, "output_tokens": 300}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        ce = report.run_summary.get("cost_efficiency")
        assert ce is not None
        assert ce["classification"] == "PARETO_BETTER"  # quality +0.2, cost down
        assert ce["quality_delta"] == 0.2
        assert ce["cost_delta_pct"] < 0  # 1200 vs 1500 → cost decreased
        assert "emoji" in ce
        assert "description" in ce

    def test_cost_efficiency_missing_when_without_tokens_zero(self):
        """cost_efficiency should be absent when without-skill tokens are 0."""
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=0.5)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.8,
                summary="With skill: 80% assertions passed",
                execution_metrics={"tool_calls": 1, "token_counts": {"input_tokens": 100, "output_tokens": 50}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.3,
                summary="Without skill: 30% assertions passed",
                execution_metrics={"tool_calls": 1, "token_counts": {"input_tokens": 0, "output_tokens": 0}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        assert "cost_efficiency" not in report.run_summary

    def test_cost_efficiency_tradeoff(self):
        """Quality improves but cost increases → TRADEOFF."""
        cases = [EvalCase(id="t1", prompt="test")]
        pairs = [RunPairResult(eval_id="t1", run_index=0, delta_pass_rate=0.3)]
        gradings = [
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.9,
                summary="With skill: 90% assertions passed",
                execution_metrics={"tool_calls": 5, "token_counts": {"input_tokens": 2000, "output_tokens": 800}},
            ),
            GradingResult(
                eval_id="t1", run_index=0, pass_rate=0.6,
                summary="Without skill: 60% assertions passed",
                execution_metrics={"tool_calls": 2, "token_counts": {"input_tokens": 1000, "output_tokens": 400}},
            ),
        ]
        report = _aggregate_benchmark("test", "/tmp", cases, pairs, gradings, 1)
        ce = report.run_summary["cost_efficiency"]
        assert ce["classification"] == "TRADEOFF"


class TestPrintCostEfficiency:
    """Test Cost Efficiency display in functional report."""

    def test_cost_efficiency_section_in_report(self, capsys):
        """Cost Efficiency section should appear when data is present."""
        report = BenchmarkReport(
            skill_name="ce-skill",
            skill_path="/tmp/ce",
            eval_count=1,
            runs_per_eval=1,
            run_summary={
                "with_skill": {
                    "mean_pass_rate": 0.9,
                    "mean_input_tokens": 1000,
                    "mean_output_tokens": 200,
                    "mean_total_tokens": 1200,
                },
                "without_skill": {
                    "mean_pass_rate": 0.7,
                    "mean_input_tokens": 1200,
                    "mean_output_tokens": 300,
                    "mean_total_tokens": 1500,
                },
                "delta": {"pass_rate": 0.2, "total_tokens": -300},
                "cost_efficiency": {
                    "quality_delta": 0.2,
                    "cost_delta_pct": -20.0,
                    "classification": "PARETO_BETTER",
                    "emoji": "\U0001f7e2",
                    "description": "Skill improves quality while reducing cost",
                },
            },
            scores={"outcome": 0.9, "process": 0.8, "style": 0.9, "efficiency": 0.8, "overall": 0.85},
            passed=True,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "Cost Efficiency:" in captured.out
        assert "PARETO_BETTER" in captured.out
        assert "+0.20" in captured.out
        assert "-20.0%" in captured.out
        assert "Skill improves quality while reducing cost" in captured.out

    def test_cost_efficiency_section_hidden_when_no_data(self, capsys):
        """Cost Efficiency section should not appear when no cost_efficiency data."""
        report = BenchmarkReport(
            skill_name="no-ce-skill",
            skill_path="/tmp/noce",
            eval_count=1,
            runs_per_eval=1,
            run_summary={
                "with_skill": {"mean_pass_rate": 0.9, "mean_total_tokens": 0},
                "without_skill": {"mean_pass_rate": 0.5, "mean_total_tokens": 0},
                "delta": {"pass_rate": 0.4},
            },
            scores={"outcome": 0.9, "process": 0.8, "style": 0.85, "efficiency": 0.7, "overall": 0.8125},
            passed=True,
        )
        _print_functional_report(report)
        captured = capsys.readouterr()
        assert "Cost Efficiency:" not in captured.out
