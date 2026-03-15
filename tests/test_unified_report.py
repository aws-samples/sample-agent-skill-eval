"""Tests for unified report module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from skill_eval.unified_report import (
    run_unified_report,
    compute_weighted_score,
    _letter_grade,
    _bar,
    _print_text_report,
    _read_skill_name,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Grading formula
# ---------------------------------------------------------------------------

class TestComputeWeightedScore:
    """Test the weighted score computation with various component combinations."""

    def test_all_components_perfect(self):
        score = compute_weighted_score(1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_all_components_zero(self):
        score = compute_weighted_score(0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_weights_are_correct(self):
        # audit=40%, functional=40%, trigger=20%
        score = compute_weighted_score(1.0, 0.0, 0.0)
        assert score == pytest.approx(0.4)

    def test_functional_weight(self):
        score = compute_weighted_score(0.0, 1.0, 0.0)
        assert score == pytest.approx(0.4)

    def test_trigger_weight(self):
        score = compute_weighted_score(0.0, 0.0, 1.0)
        assert score == pytest.approx(0.2)

    def test_mixed_scores(self):
        # 0.92*0.4 + 0.75*0.4 + 0.85*0.2 = 0.368 + 0.3 + 0.17 = 0.838
        score = compute_weighted_score(0.92, 0.75, 0.85)
        assert score == pytest.approx(0.838)

    def test_no_components(self):
        score = compute_weighted_score(None, None, None)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Weight redistribution when components are skipped
# ---------------------------------------------------------------------------

class TestWeightRedistribution:
    """Test that weights are redistributed when components are skipped."""

    def test_skip_audit(self):
        # functional(40%) + trigger(20%) -> 60% total
        # Redistributed: functional=40/60=2/3, trigger=20/60=1/3
        score = compute_weighted_score(None, 0.9, 0.6)
        expected = 0.9 * (0.4 / 0.6) + 0.6 * (0.2 / 0.6)
        assert score == pytest.approx(expected)

    def test_skip_functional(self):
        # audit(40%) + trigger(20%) -> 60% total
        score = compute_weighted_score(0.8, None, 1.0)
        expected = 0.8 * (0.4 / 0.6) + 1.0 * (0.2 / 0.6)
        assert score == pytest.approx(expected)

    def test_skip_trigger(self):
        # audit(40%) + functional(40%) -> 80% total
        score = compute_weighted_score(0.9, 0.7, None)
        expected = 0.9 * (0.4 / 0.8) + 0.7 * (0.4 / 0.8)
        assert score == pytest.approx(expected)

    def test_only_audit(self):
        score = compute_weighted_score(0.85, None, None)
        assert score == pytest.approx(0.85)

    def test_only_functional(self):
        score = compute_weighted_score(None, 0.75, None)
        assert score == pytest.approx(0.75)

    def test_only_trigger(self):
        score = compute_weighted_score(None, None, 0.9)
        assert score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Grade mapping boundaries
# ---------------------------------------------------------------------------

class TestLetterGrade:
    """Test grade mapping at exact boundary values."""

    def test_grade_a_at_boundary(self):
        assert _letter_grade(0.9) == "A"

    def test_grade_a_above(self):
        assert _letter_grade(1.0) == "A"

    def test_grade_b_at_boundary(self):
        assert _letter_grade(0.8) == "B"

    def test_grade_b_just_below_a(self):
        assert _letter_grade(0.89999) == "B"

    def test_grade_c_at_boundary(self):
        assert _letter_grade(0.7) == "C"

    def test_grade_c_just_below_b(self):
        assert _letter_grade(0.7999) == "C"

    def test_grade_d_at_boundary(self):
        assert _letter_grade(0.6) == "D"

    def test_grade_d_just_below_c(self):
        assert _letter_grade(0.6999) == "D"

    def test_grade_f_below_d(self):
        assert _letter_grade(0.5999) == "F"

    def test_grade_f_zero(self):
        assert _letter_grade(0.0) == "F"


# ---------------------------------------------------------------------------
# Bar rendering
# ---------------------------------------------------------------------------

class TestBarRendering:
    """Test the visual bar helper."""

    def test_bar_full(self):
        bar = _bar(1.0, width=10)
        assert bar == "\u2588" * 10

    def test_bar_empty(self):
        bar = _bar(0.0, width=10)
        assert bar == "\u2591" * 10

    def test_bar_half(self):
        bar = _bar(0.5, width=10)
        assert bar == "\u2588" * 5 + "\u2591" * 5

    def test_bar_custom_width(self):
        bar = _bar(1.0, width=5)
        assert len(bar) == 5


# ---------------------------------------------------------------------------
# Text output format
# ---------------------------------------------------------------------------

class TestTextOutput:
    """Test the text report output format."""

    def test_text_report_contains_headers(self, capsys):
        data = {
            "skill_name": "weather-skill",
            "skill_path": "/tmp/weather",
            "overall_score": 0.83,
            "overall_grade": "B",
            "passed": True,
            "sections": {
                "audit": {"score": 92, "grade": "A", "passed": True, "normalized": 0.92},
                "functional": {"overall": 0.75, "grade": "C", "passed": True},
                "trigger": {"pass_rate": 0.85, "grade": "B", "passed": True},
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "Unified Skill Report" in captured.out
        assert "weather-skill" in captured.out
        assert "B (0.83)" in captured.out

    def test_text_report_contains_sections(self, capsys):
        data = {
            "skill_name": "test-skill",
            "skill_path": "/tmp/test",
            "overall_score": 0.90,
            "overall_grade": "A",
            "passed": True,
            "sections": {
                "audit": {"score": 95, "grade": "A", "passed": True, "normalized": 0.95},
                "functional": {"overall": 0.88, "grade": "B", "passed": True},
                "trigger": {"pass_rate": 0.90, "grade": "A", "passed": True},
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "Audit:" in captured.out
        assert "Functional:" in captured.out
        assert "Trigger:" in captured.out

    def test_text_report_passed(self, capsys):
        data = {
            "skill_name": "good",
            "skill_path": "/tmp/good",
            "overall_score": 0.95,
            "overall_grade": "A",
            "passed": True,
            "sections": {},
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "PASSED" in captured.out

    def test_text_report_failed(self, capsys):
        data = {
            "skill_name": "bad",
            "skill_path": "/tmp/bad",
            "overall_score": 0.45,
            "overall_grade": "F",
            "passed": False,
            "sections": {},
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_text_report_skipped_sections_not_shown(self, capsys):
        data = {
            "skill_name": "partial",
            "skill_path": "/tmp/partial",
            "overall_score": 0.80,
            "overall_grade": "B",
            "passed": True,
            "sections": {
                "audit": {"score": 80, "grade": "B", "passed": True, "normalized": 0.8},
                "functional": {"skipped": True, "reason": "no evals.json"},
                "trigger": {"skipped": True, "reason": "no eval_queries.json"},
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "Audit:" in captured.out
        # Skipped sections should not have score lines
        assert "Functional:" not in captured.out
        assert "Trigger:" not in captured.out


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

class TestJsonOutput:
    """Test JSON report output."""

    def test_json_output_valid(self, tmp_path, capsys):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\n---\nHello")

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 90
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 1
            mock_report.info_count = 2
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                format="json",
                include_functional=False,
                include_trigger=False,
            )

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["skill_name"] == "test-skill"
        assert data["overall_grade"] in ["A", "B", "C", "D", "F"]
        assert "sections" in data
        assert "audit" in data["sections"]
        assert ret == 0

    def test_json_output_has_required_fields(self, tmp_path, capsys):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nBody")

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 75
            mock_report.grade = "C"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 2
            mock_report.info_count = 5
            mock_audit.return_value = mock_report

            run_unified_report(
                str(skill_dir),
                format="json",
                include_functional=False,
                include_trigger=False,
            )

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        required_keys = {"skill_name", "skill_path", "timestamp", "overall_score",
                         "overall_grade", "passed", "sections"}
        assert required_keys.issubset(data.keys())


# ---------------------------------------------------------------------------
# Mock audit/functional/trigger results
# ---------------------------------------------------------------------------

class TestWithMockResults:
    """Test unified report with mocked sub-evaluations."""

    def _make_skill_dir(self, tmp_path, name="test-skill", evals=True, queries=True):
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\nTest skill.")
        if evals or queries:
            evals_dir = skill_dir / "evals"
            evals_dir.mkdir()
            if evals:
                (evals_dir / "evals.json").write_text(json.dumps([
                    {"id": "t1", "prompt": "test prompt", "assertions": ["contains 'hello'"]}
                ]))
            if queries:
                (evals_dir / "eval_queries.json").write_text(json.dumps([
                    {"query": "test query", "should_trigger": True}
                ]))
        return skill_dir

    def test_audit_only(self, tmp_path):
        skill_dir = self._make_skill_dir(tmp_path, evals=False, queries=False)

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 85
            mock_report.grade = "B"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 1
            mock_report.info_count = 3
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                include_functional=True,
                include_trigger=True,
            )

        assert ret == 0
        report_file = skill_dir / "evals" / "report.json"
        assert report_file.is_file()
        data = json.loads(report_file.read_text())
        # Only audit contributes; score should be 0.85
        assert data["overall_score"] == pytest.approx(0.85)
        assert data["overall_grade"] == "B"

    def test_all_components(self, tmp_path):
        skill_dir = self._make_skill_dir(tmp_path)

        with patch("skill_eval.unified_report.run_audit") as mock_audit, \
             patch("skill_eval.unified_report._run_functional") as mock_func, \
             patch("skill_eval.unified_report._run_trigger") as mock_trigger:

            mock_report = MagicMock()
            mock_report.score = 92
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 0
            mock_report.info_count = 4
            mock_audit.return_value = mock_report

            mock_func.return_value = {"overall": 0.75, "passed": True, "scores": {}}
            mock_trigger.return_value = {"pass_rate": 0.85, "passed": True, "total_queries": 4}

            ret = run_unified_report(str(skill_dir))

        assert ret == 0
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        # 0.92*0.4 + 0.75*0.4 + 0.85*0.2 = 0.368 + 0.3 + 0.17 = 0.838
        assert data["overall_score"] == pytest.approx(0.838)
        assert data["overall_grade"] == "B"

    def test_failed_audit_critical(self, tmp_path):
        skill_dir = self._make_skill_dir(tmp_path, evals=False, queries=False)

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 50
            mock_report.grade = "F"
            mock_report.passed = False
            mock_report.critical_count = 2
            mock_report.warning_count = 0
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            ret = run_unified_report(str(skill_dir))

        assert ret == 1  # Failed due to critical findings
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        assert data["passed"] is False

    def test_functional_fail_propagates(self, tmp_path):
        skill_dir = self._make_skill_dir(tmp_path)

        with patch("skill_eval.unified_report.run_audit") as mock_audit, \
             patch("skill_eval.unified_report._run_functional") as mock_func, \
             patch("skill_eval.unified_report._run_trigger") as mock_trigger:

            mock_report = MagicMock()
            mock_report.score = 100
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 0
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            mock_func.return_value = {"overall": 0.3, "passed": False, "scores": {}}
            mock_trigger.return_value = {"pass_rate": 1.0, "passed": True, "total_queries": 2}

            ret = run_unified_report(str(skill_dir))

        assert ret == 1
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        assert data["passed"] is False


# ---------------------------------------------------------------------------
# Skip flags
# ---------------------------------------------------------------------------

class TestSkipFlags:
    """Test --skip-audit, --skip-functional, --skip-trigger flags."""

    def test_skip_audit(self, tmp_path):
        skill_dir = tmp_path / "skip-audit"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skip-audit\n---\nBody")

        with patch("skill_eval.unified_report._run_functional") as mock_func, \
             patch("skill_eval.unified_report._run_trigger") as mock_trigger:
            # No audit mock — should not be called
            mock_func.return_value = None
            mock_trigger.return_value = None

            ret = run_unified_report(
                str(skill_dir),
                include_audit=False,
                include_functional=False,
                include_trigger=False,
            )

        assert ret == 0  # No components = passed (vacuously)
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        assert "audit" not in data["sections"]

    def test_skip_functional(self, tmp_path):
        skill_dir = tmp_path / "skip-func"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skip-func\n---\nBody")
        evals_dir = skill_dir / "evals"
        evals_dir.mkdir()
        (evals_dir / "evals.json").write_text("[]")

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 90
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 0
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                include_functional=False,
                include_trigger=False,
            )

        assert ret == 0
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        # Functional should not appear as a scored section
        func_section = data["sections"].get("functional", {})
        assert func_section == {}  # not included at all since flag was False

    def test_skip_trigger(self, tmp_path):
        skill_dir = tmp_path / "skip-trig"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skip-trig\n---\nBody")

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 80
            mock_report.grade = "B"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 2
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                include_functional=False,
                include_trigger=False,
            )

        assert ret == 0
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        assert "trigger" not in data["sections"]


# ---------------------------------------------------------------------------
# Skill with no evals/ directory
# ---------------------------------------------------------------------------

class TestNoEvalsDirectory:
    """Test behavior when skill has no evals/ directory."""

    def test_no_evals_dir_audit_only(self, tmp_path):
        skill_dir = tmp_path / "bare-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: bare-skill\n---\nMinimal skill")

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 88
            mock_report.grade = "B"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 1
            mock_report.info_count = 1
            mock_audit.return_value = mock_report

            ret = run_unified_report(str(skill_dir))

        assert ret == 0
        report_file = skill_dir / "evals" / "report.json"
        assert report_file.is_file()  # Created even if evals/ didn't exist
        data = json.loads(report_file.read_text())
        assert data["overall_score"] == pytest.approx(0.88)
        assert data["sections"]["functional"]["skipped"] is True
        assert data["sections"]["trigger"]["skipped"] is True

    def test_no_skill_md(self, tmp_path):
        """Skill directory with no SKILL.md still works (uses dir name)."""
        skill_dir = tmp_path / "unnamed-skill"
        skill_dir.mkdir()

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 70
            mock_report.grade = "C"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 3
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                include_functional=False,
                include_trigger=False,
            )

        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        assert data["skill_name"] == "unnamed-skill"


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

class TestOutputPath:
    """Test custom output path."""

    def test_custom_output_path(self, tmp_path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\nBody")

        custom_out = tmp_path / "custom" / "report.json"

        with patch("skill_eval.unified_report.run_audit") as mock_audit:
            mock_report = MagicMock()
            mock_report.score = 95
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 0
            mock_report.info_count = 1
            mock_audit.return_value = mock_report

            ret = run_unified_report(
                str(skill_dir),
                output_path=str(custom_out),
                include_functional=False,
                include_trigger=False,
            )

        assert ret == 0
        assert custom_out.is_file()
        data = json.loads(custom_out.read_text())
        assert data["skill_name"] == "skill"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestCLIReportSubcommand:
    """Test that the report subcommand is properly wired in cli.py."""

    def test_report_help(self):
        from skill_eval.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main(["report", "--help"])
        assert exc_info.value.code == 0

    def test_report_subcommand_calls_unified_report(self, tmp_path):
        skill_dir = tmp_path / "cli-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: cli-skill\n---\nBody")

        from skill_eval.cli import main

        with patch("skill_eval.unified_report.run_unified_report", return_value=0) as mock_run:
            ret = main(["report", str(skill_dir), "--skip-functional", "--skip-trigger"])

        assert ret == 0
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["include_functional"] is False
        assert call_kwargs[1]["include_trigger"] is False

    def test_report_format_json(self, tmp_path):
        skill_dir = tmp_path / "json-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: json-skill\n---\nBody")

        from skill_eval.cli import main

        with patch("skill_eval.unified_report.run_unified_report", return_value=0) as mock_run:
            main(["report", str(skill_dir), "--format", "json",
                  "--skip-audit", "--skip-functional", "--skip-trigger"])

        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["format"] == "json"
        assert call_kwargs[1]["include_audit"] is False


# ---------------------------------------------------------------------------
# Read skill name helper
# ---------------------------------------------------------------------------

class TestReadSkillName:
    """Test the skill name extraction."""

    def test_reads_name_from_frontmatter(self):
        name = _read_skill_name(FIXTURES / "good-skill")
        assert name == "good-skill"

    def test_returns_none_for_missing(self, tmp_path):
        assert _read_skill_name(tmp_path) is None

    def test_returns_none_for_no_frontmatter(self):
        assert _read_skill_name(FIXTURES / "no-frontmatter") is None


# ---------------------------------------------------------------------------
# Cost-efficiency in unified report
# ---------------------------------------------------------------------------

class TestCostEfficiencyInUnifiedReport:
    """Test cost_efficiency data flows through to unified report text output."""

    def test_cost_efficiency_line_in_text_report(self, capsys):
        """Cost efficiency line should appear after functional score line."""
        data = {
            "skill_name": "ce-skill",
            "skill_path": "/tmp/ce",
            "overall_score": 0.85,
            "overall_grade": "B",
            "passed": True,
            "sections": {
                "functional": {
                    "overall": 0.80,
                    "grade": "B",
                    "passed": True,
                    "scores": {},
                    "cost_efficiency": {
                        "quality_delta": 0.20,
                        "cost_delta_pct": -15.3,
                        "classification": "PARETO_BETTER",
                        "emoji": "\U0001f7e2",
                        "description": "Skill improves quality while reducing cost",
                    },
                },
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "Functional:" in captured.out
        assert "Cost:" in captured.out
        assert "PARETO_BETTER" in captured.out
        assert "+0.20" in captured.out
        assert "-15.3%" in captured.out

    def test_cost_efficiency_line_format(self, capsys):
        """Verify the exact format of the cost efficiency line."""
        data = {
            "skill_name": "fmt-skill",
            "skill_path": "/tmp/fmt",
            "overall_score": 0.70,
            "overall_grade": "C",
            "passed": True,
            "sections": {
                "functional": {
                    "overall": 0.70,
                    "grade": "C",
                    "passed": True,
                    "scores": {},
                    "cost_efficiency": {
                        "quality_delta": -0.03,
                        "cost_delta_pct": 25.0,
                        "classification": "PARETO_WORSE",
                        "emoji": "\U0001f534",
                        "description": "Skill increases cost without improving quality",
                    },
                },
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "PARETO_WORSE" in captured.out
        assert "quality -0.03" in captured.out
        assert "cost +25.0%" in captured.out

    def test_no_cost_efficiency_line_when_absent(self, capsys):
        """Cost line should not appear when cost_efficiency is absent."""
        data = {
            "skill_name": "no-ce",
            "skill_path": "/tmp/noce",
            "overall_score": 0.80,
            "overall_grade": "B",
            "passed": True,
            "sections": {
                "functional": {
                    "overall": 0.80,
                    "grade": "B",
                    "passed": True,
                    "scores": {},
                },
            },
        }
        _print_text_report(data)
        captured = capsys.readouterr()
        assert "Functional:" in captured.out
        assert "Cost:" not in captured.out

    def test_cost_efficiency_flows_through_mock_run(self, tmp_path):
        """Verify cost_efficiency from benchmark.json reaches unified report sections."""
        skill_dir = tmp_path / "flow-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: flow-skill\n---\nBody")
        evals_dir = skill_dir / "evals"
        evals_dir.mkdir()
        (evals_dir / "evals.json").write_text(json.dumps([
            {"id": "t1", "prompt": "test", "assertions": ["contains 'hello'"]}
        ]))

        with patch("skill_eval.unified_report.run_audit") as mock_audit, \
             patch("skill_eval.unified_report._run_functional") as mock_func:

            mock_report = MagicMock()
            mock_report.score = 90
            mock_report.grade = "A"
            mock_report.passed = True
            mock_report.critical_count = 0
            mock_report.warning_count = 0
            mock_report.info_count = 0
            mock_audit.return_value = mock_report

            mock_func.return_value = {
                "overall": 0.80,
                "passed": True,
                "scores": {},
                "cost_efficiency": {
                    "quality_delta": 0.15,
                    "cost_delta_pct": -10.0,
                    "classification": "PARETO_BETTER",
                    "emoji": "\U0001f7e2",
                    "description": "Skill improves quality while reducing cost",
                },
            }

            ret = run_unified_report(
                str(skill_dir),
                format="json",
                include_trigger=False,
            )

        assert ret == 0
        data = json.loads((skill_dir / "evals" / "report.json").read_text())
        func_section = data["sections"]["functional"]
        assert "cost_efficiency" in func_section
        assert func_section["cost_efficiency"]["classification"] == "PARETO_BETTER"
