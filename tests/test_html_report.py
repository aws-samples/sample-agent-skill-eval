"""Tests for skill_eval.html_report module."""

import pytest
from skill_eval.html_report import generate_html_report, _grade_color, _pct, _cost_fmt


class TestHelpers:
    """Test helper functions."""

    def test_grade_colors(self):
        assert _grade_color("A") == "#22c55e"
        assert _grade_color("F") == "#ef4444"
        assert _grade_color("?") == "#94a3b8"

    def test_pct(self):
        assert _pct(0.5) == "50.0%"
        assert _pct(1.0) == "100.0%"
        assert _pct(0.0) == "0.0%"

    def test_cost_fmt(self):
        assert _cost_fmt(0.0042) == "$0.0042"
        assert _cost_fmt(1.23) == "$1.23"
        assert _cost_fmt(0) == "$0.0000"


class TestGenerateHtmlReport:
    """Test HTML report generation."""

    @pytest.fixture
    def minimal_report(self):
        return {
            "skill_name": "test-skill",
            "skill_path": "/tmp/test",
            "timestamp": "2026-03-15T11:00:00Z",
            "overall_score": 0.92,
            "overall_grade": "A",
            "passed": True,
            "sections": {},
        }

    @pytest.fixture
    def full_report(self):
        return {
            "skill_name": "pr-naming",
            "skill_path": "/demo",
            "timestamp": "2026-03-15T11:00:00Z",
            "overall_score": 0.86,
            "overall_grade": "B",
            "passed": True,
            "sections": {
                "audit": {
                    "score": 98, "grade": "A", "passed": True,
                    "normalized": 0.98,
                    "critical": 0, "warning": 0, "info": 1,
                    "findings": [
                        {"severity": "INFO", "code": "STR-008",
                         "title": "Dir name mismatch", "file_path": "SKILL.md"},
                    ],
                },
                "functional": {
                    "overall": 0.86, "grade": "B", "passed": True,
                    "scores": {"outcome": 1.0, "process": 1.0,
                               "style": 1.0, "efficiency": 0.44,
                               "overall": 0.86},
                    "cost_efficiency": {
                        "quality_delta": 0.17,
                        "cost_delta_pct": 298.4,
                        "classification": "TRADEOFF",
                        "emoji": "🟡",
                        "description": "Skill improves quality but increases cost",
                    },
                    "estimated_cost": {
                        "total_cost": 3.48,
                        "with_skill_per_run": {"total_cost": 0.46},
                        "without_skill_per_run": {"total_cost": 0.12},
                        "model": "sonnet",
                    },
                },
                "trigger": {
                    "pass_rate": 0.75, "grade": "C", "passed": False,
                    "total_queries": 8,
                    "query_results": [
                        {"passed": True, "query": "Check PR title",
                         "should_trigger": True, "trigger_rate": 1.0},
                        {"passed": False, "query": "Write Python sort",
                         "should_trigger": False, "trigger_rate": 0.5},
                    ],
                },
            },
        }

    def test_returns_valid_html(self, minimal_report):
        html = generate_html_report(minimal_report)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_skill_name(self, minimal_report):
        html = generate_html_report(minimal_report)
        assert "test-skill" in html

    def test_contains_overall_grade(self, minimal_report):
        html = generate_html_report(minimal_report)
        assert ">A<" in html

    def test_contains_passed_status(self, minimal_report):
        html = generate_html_report(minimal_report)
        assert "PASSED" in html

    def test_failed_status(self, minimal_report):
        minimal_report["passed"] = False
        html = generate_html_report(minimal_report)
        assert "FAILED" in html

    def test_audit_section(self, full_report):
        html = generate_html_report(full_report)
        assert "Security Audit" in html
        assert "98/100" in html
        assert "STR-008" in html
        assert "Dir name mismatch" in html

    def test_functional_section(self, full_report):
        html = generate_html_report(full_report)
        assert "Functional Evaluation" in html
        assert "TRADEOFF" in html
        assert "$3.48" in html
        assert "sonnet" in html

    def test_trigger_section(self, full_report):
        html = generate_html_report(full_report)
        assert "Trigger Reliability" in html
        assert "Check PR title" in html
        assert "75.0%" in html

    def test_skipped_sections(self):
        report = {
            "skill_name": "test",
            "skill_path": "/tmp",
            "timestamp": "",
            "overall_score": 0.5,
            "overall_grade": "D",
            "passed": False,
            "sections": {
                "functional": {"skipped": True, "reason": "no evals.json"},
                "trigger": {"skipped": True, "reason": "no queries"},
            },
        }
        html = generate_html_report(report)
        assert "Skipped" in html
        assert "no evals.json" in html

    def test_error_sections(self):
        report = {
            "skill_name": "test",
            "skill_path": "/tmp",
            "timestamp": "",
            "overall_score": 0,
            "overall_grade": "F",
            "passed": False,
            "sections": {
                "audit": {"error": "Something broke"},
            },
        }
        html = generate_html_report(report)
        assert "Something broke" in html

    def test_html_escaping(self):
        report = {
            "skill_name": "<script>alert('xss')</script>",
            "skill_path": "/tmp",
            "timestamp": "",
            "overall_score": 0.5,
            "overall_grade": "D",
            "passed": True,
            "sections": {},
        }
        html = generate_html_report(report)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_github_link_present(self, minimal_report):
        html = generate_html_report(minimal_report)
        assert "aws-samples/sample-agent-skill-eval" in html
