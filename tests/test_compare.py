"""Tests for compare module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from skill_eval.compare import (
    run_compare,
    _load_evals,
    _read_skill_name,
    _aggregate_compare,
    _run_eval_comparison,
    _print_compare_report,
)
from skill_eval.eval_schemas import CompareReport, EvalCase
from skill_eval.agent_runner import AgentNotAvailableError, ClaudeRunner
from skill_eval.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


class TestRunCompareErrors:
    """Test error handling in run_compare."""

    def test_missing_evals_file(self):
        ret = run_compare("/nonexistent/a", "/nonexistent/b")
        assert ret == 2

    def test_invalid_evals_path(self, tmp_path):
        bad_evals = tmp_path / "evals.json"
        bad_evals.write_text("not json")
        ret = run_compare(str(tmp_path), str(tmp_path), evals_path=str(bad_evals))
        assert ret == 2

    def test_empty_evals(self, tmp_path):
        evals = tmp_path / "evals.json"
        evals.write_text("[]")
        ret = run_compare(str(tmp_path), str(tmp_path), evals_path=str(evals))
        assert ret == 2

    def test_no_claude_available(self):
        with patch.object(ClaudeRunner, "check_available",
                          side_effect=AgentNotAvailableError("claude")):
            ret = run_compare(
                str(FIXTURES / "eval-skill"),
                str(FIXTURES / "eval-skill"),
            )
            assert ret == 2


class TestDryRunCompare:
    """Test dry-run mode for compare."""

    def test_dry_run_prints_summary(self, capsys):
        ret = run_compare(
            str(FIXTURES / "eval-skill"),
            str(FIXTURES / "eval-skill"),
            dry_run=True,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "3 eval case(s)" in captured.out
        assert "Estimated invocations: 6" in captured.out  # 3 cases * 1 run * 2 skills

    def test_dry_run_custom_runs(self, capsys):
        ret = run_compare(
            str(FIXTURES / "eval-skill"),
            str(FIXTURES / "eval-skill"),
            runs_per_eval=3,
            dry_run=True,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "Estimated invocations: 18" in captured.out  # 3 * 3 * 2


class TestAggregateCompare:
    """Test comparison aggregation logic."""

    def _make_per_eval(self, a_pass, a_tokens, a_assertions, b_pass, b_tokens, b_assertions):
        return {
            "eval_id": "e1",
            "skill_a": {
                "mean_pass_rate": a_pass,
                "mean_total_tokens": a_tokens,
                "mean_tool_calls": 2,
                "mean_assertions_passed": a_assertions,
            },
            "skill_b": {
                "mean_pass_rate": b_pass,
                "mean_total_tokens": b_tokens,
                "mean_tool_calls": 3,
                "mean_assertions_passed": b_assertions,
            },
        }

    def test_winner_determination_a_wins(self):
        """A wins when it has lower tokens-per-passing-assertion."""
        per_eval = [self._make_per_eval(1.0, 100, 4.0, 1.0, 200, 4.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.winner == "a"

    def test_winner_determination_b_wins(self):
        """B wins when it has lower tokens-per-passing-assertion."""
        per_eval = [self._make_per_eval(1.0, 200, 4.0, 1.0, 100, 4.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.winner == "b"

    def test_tie_within_margin(self):
        """Tie when difference is within 5% margin."""
        per_eval = [self._make_per_eval(1.0, 100, 4.0, 1.0, 102, 4.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.winner == "tie"

    def test_tie_both_zero_assertions(self):
        """Tie when neither skill passes any assertions."""
        per_eval = [self._make_per_eval(0.0, 100, 0.0, 0.0, 200, 0.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.winner == "tie"

    def test_b_wins_when_a_has_zero_assertions(self):
        """B wins when A has no passing assertions but B does."""
        per_eval = [self._make_per_eval(0.0, 100, 0.0, 1.0, 200, 4.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.winner == "b"

    def test_token_efficiency_ratio(self):
        """Token efficiency ratio = b_total / a_total."""
        per_eval = [self._make_per_eval(1.0, 100, 4.0, 1.0, 200, 4.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.summary["token_efficiency_ratio"] == 2.0

    def test_per_eval_rows(self):
        per_eval = [
            self._make_per_eval(0.8, 150, 3.0, 0.9, 180, 3.5),
            self._make_per_eval(1.0, 100, 4.0, 0.5, 120, 2.0),
        ]
        cases = [EvalCase(id="e1", prompt="t1"), EvalCase(id="e2", prompt="t2")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        assert report.eval_count == 2
        assert len(report.per_eval) == 2

    def test_summary_fields(self):
        per_eval = [self._make_per_eval(0.8, 150, 3.0, 0.6, 120, 2.0)]
        cases = [EvalCase(id="e1", prompt="test")]
        report = _aggregate_compare("a", "/a", "b", "/b", cases, per_eval, 1)
        sa = report.summary["skill_a"]
        sb = report.summary["skill_b"]
        assert sa["mean_pass_rate"] == 0.8
        assert sa["mean_total_tokens"] == 150.0
        assert sb["mean_pass_rate"] == 0.6
        assert "tokens_per_passing_assertion" in sa
        assert "tokens_per_passing_assertion" in sb


class TestPrintCompareReport:
    """Test compare report printing."""

    def test_print_report(self, capsys):
        report = CompareReport(
            skill_a_name="alpha",
            skill_a_path="/alpha",
            skill_b_name="beta",
            skill_b_path="/beta",
            eval_count=2,
            runs_per_eval=1,
            per_eval=[
                {"eval_id": "e1",
                 "skill_a": {"mean_pass_rate": 0.8, "mean_total_tokens": 100},
                 "skill_b": {"mean_pass_rate": 0.9, "mean_total_tokens": 150}},
            ],
            summary={
                "skill_a": {
                    "mean_pass_rate": 0.8,
                    "mean_total_tokens": 100,
                    "total_assertions_passed": 3,
                    "tokens_per_passing_assertion": 33.3,
                },
                "skill_b": {
                    "mean_pass_rate": 0.9,
                    "mean_total_tokens": 150,
                    "total_assertions_passed": 4,
                    "tokens_per_passing_assertion": 37.5,
                },
                "token_efficiency_ratio": 1.5,
            },
            winner="alpha",
        )
        _print_compare_report(report)
        captured = capsys.readouterr()
        assert "alpha" in captured.out
        assert "beta" in captured.out
        assert "Skill Comparison Report" in captured.out
        assert "Winner: alpha" in captured.out
        assert "1.50x" in captured.out

    def test_print_report_tie(self, capsys):
        report = CompareReport(
            skill_a_name="a",
            skill_a_path="/a",
            skill_b_name="b",
            skill_b_path="/b",
            eval_count=1,
            runs_per_eval=1,
            per_eval=[],
            summary={
                "skill_a": {
                    "mean_pass_rate": 0.8,
                    "mean_total_tokens": 100,
                    "total_assertions_passed": 3,
                    "tokens_per_passing_assertion": None,
                },
                "skill_b": {
                    "mean_pass_rate": 0.8,
                    "mean_total_tokens": 100,
                    "total_assertions_passed": 3,
                    "tokens_per_passing_assertion": None,
                },
                "token_efficiency_ratio": 1.0,
            },
            winner="tie",
        )
        _print_compare_report(report)
        captured = capsys.readouterr()
        assert "Winner: tie" in captured.out


class TestCLICompare:
    """Test compare command via CLI."""

    def test_compare_dry_run(self, capsys):
        ret = main([
            "compare",
            str(FIXTURES / "eval-skill"),
            str(FIXTURES / "eval-skill"),
            "--dry-run",
        ])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Dry run" in captured.out

    def test_compare_missing_skill(self):
        ret = main(["compare", "/nonexistent/a", "/nonexistent/b"])
        assert ret == 2

    def test_compare_custom_evals(self, capsys):
        evals_file = str(FIXTURES / "eval-skill" / "evals" / "evals.json")
        ret = main([
            "compare",
            str(FIXTURES / "eval-skill"),
            str(FIXTURES / "eval-skill"),
            "--evals", evals_file,
            "--dry-run",
        ])
        assert ret == 0


def _make_stream_json(text, input_tokens=100, output_tokens=50):
    """Build a minimal stream-json string for testing."""
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


class TestRunEvalComparison:
    """Integration tests for _run_eval_comparison with mocked Claude."""

    def _eval_case(self):
        return EvalCase(
            id="test-case",
            prompt="Summarize the CSV file.",
            files=["files/sample.csv"],
            assertions=["contains 'name'", "contains 'age'"],
        )

    def _make_mock_runner(self):
        runner = MagicMock(spec=ClaudeRunner)
        real_runner = ClaudeRunner()
        runner.parse_output.side_effect = real_runner.parse_output
        runner.total_tokens.side_effect = real_runner.total_tokens
        return runner

    def test_run_eval_comparison_basic(self):
        """Both skills pass all assertions."""
        text = "The CSV has columns: name, age, city"
        stream = _make_stream_json(text)
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = (stream, "", 0, 1.0)

        row = _run_eval_comparison(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            runs_per_eval=1,
            timeout=30,
            runner=runner,
        )
        assert row["eval_id"] == "test-case"
        assert row["skill_a"]["mean_pass_rate"] == 1.0
        assert row["skill_b"]["mean_pass_rate"] == 1.0

    def test_run_eval_comparison_skill_a_wins(self):
        """Skill A passes, skill B fails."""
        good = _make_stream_json("Columns: name, age, city")
        bad = _make_stream_json("I cannot read files.")
        runner = self._make_mock_runner()
        # _run_eval_comparison calls _run_single_skill for A then B per run
        runner.run_prompt.side_effect = [
            (good, "", 0, 1.0),  # skill A
            (bad, "", 0, 1.0),   # skill B
        ]

        row = _run_eval_comparison(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            runs_per_eval=1,
            timeout=30,
            runner=runner,
        )
        assert row["skill_a"]["mean_pass_rate"] == 1.0
        assert row["skill_b"]["mean_pass_rate"] == 0.0

    def test_run_eval_comparison_token_fields_present(self):
        """total_tokens computed correctly from input + output."""
        stream = _make_stream_json("name age", input_tokens=300, output_tokens=100)
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = (stream, "", 0, 1.0)

        row = _run_eval_comparison(
            self._eval_case(),
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill",
            FIXTURES / "eval-skill" / "evals",
            runs_per_eval=1,
            timeout=30,
            runner=runner,
        )
        assert row["skill_a"]["mean_total_tokens"] == 400.0
        assert row["skill_b"]["mean_total_tokens"] == 400.0
