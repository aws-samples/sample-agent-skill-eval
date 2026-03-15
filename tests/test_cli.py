"""Tests for the CLI and full audit pipeline."""

import io
import json
import pytest
from pathlib import Path

from skill_eval.cli import run_audit, main
from skill_eval.explanations import RULE_EXPLANATIONS, get_explanation
from skill_eval.report import format_text_report, format_json_report
from skill_eval.schemas import (
    AuditReport, Finding, Severity, Category,
    calculate_score, calculate_grade,
)


FIXTURES = Path(__file__).parent / "fixtures"


class TestScoring:
    """Test score calculation and grading."""

    def test_no_findings_score_100(self):
        assert calculate_score([]) == 100

    def test_critical_deducts_25(self):
        findings = [Finding(
            code="T-001", severity=Severity.CRITICAL, category=Category.SECURITY,
            title="test", detail="test",
        )]
        assert calculate_score(findings) == 75

    def test_warning_deducts_10(self):
        findings = [Finding(
            code="T-001", severity=Severity.WARNING, category=Category.SECURITY,
            title="test", detail="test",
        )]
        assert calculate_score(findings) == 90

    def test_info_deducts_2(self):
        findings = [Finding(
            code="T-001", severity=Severity.INFO, category=Category.QUALITY,
            title="test", detail="test",
        )]
        assert calculate_score(findings) == 98

    def test_score_clamps_at_zero(self):
        findings = [Finding(
            code="T-001", severity=Severity.CRITICAL, category=Category.SECURITY,
            title="test", detail="test",
        )] * 10  # 10 criticals = 250 deduction
        assert calculate_score(findings) == 0

    def test_grade_boundaries(self):
        assert calculate_grade(100) == "A"
        assert calculate_grade(90) == "A"
        assert calculate_grade(89) == "B"
        assert calculate_grade(80) == "B"
        assert calculate_grade(79) == "C"
        assert calculate_grade(70) == "C"
        assert calculate_grade(69) == "D"
        assert calculate_grade(60) == "D"
        assert calculate_grade(59) == "F"
        assert calculate_grade(0) == "F"


class TestDataStructures:
    """Test Finding and AuditReport serialization."""

    def test_finding_to_dict(self):
        f = Finding(
            code="SEC-001", severity=Severity.CRITICAL, category=Category.SECURITY,
            title="Test", detail="Detail", file_path="test.py", line_number=42,
            fix="Fix it",
        )
        d = f.to_dict()
        assert d["severity"] == "CRITICAL"
        assert d["category"] == "SECURITY"
        assert d["code"] == "SEC-001"
        assert d["line_number"] == 42

    def test_audit_report_counts(self):
        findings = [
            Finding(code="A", severity=Severity.CRITICAL, category=Category.SECURITY,
                    title="c1", detail="d"),
            Finding(code="B", severity=Severity.WARNING, category=Category.SECURITY,
                    title="w1", detail="d"),
            Finding(code="C", severity=Severity.WARNING, category=Category.SECURITY,
                    title="w2", detail="d"),
            Finding(code="D", severity=Severity.INFO, category=Category.QUALITY,
                    title="i1", detail="d"),
        ]
        report = AuditReport(
            skill_name="test", skill_path="/test", score=55, grade="F",
            findings=findings,
        )
        assert report.critical_count == 1
        assert report.warning_count == 2
        assert report.info_count == 1
        assert report.passed is False

    def test_audit_report_to_dict_has_summary(self):
        report = AuditReport(
            skill_name="test", skill_path="/test", score=100, grade="A",
            findings=[],
        )
        d = report.to_dict()
        assert d["summary"]["total"] == 0
        assert d["passed"] is True

    def test_audit_report_to_json_roundtrip(self):
        f = Finding(code="X", severity=Severity.INFO, category=Category.QUALITY,
                    title="t", detail="d")
        report = AuditReport(
            skill_name="test", skill_path="/test", score=98, grade="A",
            findings=[f],
        )
        parsed = json.loads(report.to_json())
        assert parsed["score"] == 98
        assert len(parsed["findings"]) == 1


class TestRunAudit:
    """Test the full audit pipeline."""

    def test_good_skill_high_score(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        assert report.score >= 90, f"Good skill should score >=90, got {report.score}"
        assert report.grade in ("A", "B")
        assert report.passed is True
        assert report.critical_count == 0

    def test_bad_skill_low_score(self):
        report = run_audit(str(FIXTURES / "bad-skill"))
        assert report.score < 50, f"Bad skill should score <50, got {report.score}"
        assert report.passed is False  # Should have critical findings
        assert report.critical_count > 0

    def test_no_frontmatter_fails(self):
        report = run_audit(str(FIXTURES / "no-frontmatter"))
        assert report.passed is False
        assert report.critical_count > 0

    def test_report_json_serializable(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        json_str = report.to_json()
        parsed = json.loads(json_str)
        assert parsed["skill_name"] == "good-skill"
        assert "findings" in parsed
        assert "summary" in parsed

    def test_report_metadata(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        assert "structure_findings" in report.metadata
        assert "security_findings" in report.metadata
        assert "permission_findings" in report.metadata


class TestReportOutput:
    """Test report formatting directly."""

    def test_text_report_contains_skill_name(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        buf = io.StringIO()
        format_text_report(report, file=buf)
        output = buf.getvalue()
        assert "good-skill" in output
        assert "Agent Skill Security Audit Report" in output

    def test_json_report_valid(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        buf = io.StringIO()
        format_json_report(report, file=buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["skill_name"] == "good-skill"
        assert parsed["passed"] is True

    def test_bad_skill_text_report_shows_critical(self):
        report = run_audit(str(FIXTURES / "bad-skill"))
        buf = io.StringIO()
        format_text_report(report, verbose=True, file=buf)
        output = buf.getvalue()
        assert "FAILED" in output


class TestCLI:
    """Test CLI argument handling."""

    def test_audit_good_skill_exits_0(self):
        ret = main(["audit", str(FIXTURES / "good-skill")])
        assert ret == 0

    def test_audit_bad_skill_exit_code(self):
        ret = main(["audit", str(FIXTURES / "bad-skill")])
        assert ret == 2, "Should exit with code 2 for critical findings"

    def test_audit_fail_on_warning(self):
        ret = main(["audit", str(FIXTURES / "good-skill"), "--fail-on-warning"])
        assert ret == 0

    def test_no_command_shows_help(self):
        ret = main([])
        assert ret == 0


class TestExplainFlag:
    """Test --explain flag for educational context."""

    def test_explain_shows_why_it_matters(self):
        """--explain should include 'Why it matters' lines for findings."""
        report = run_audit(str(FIXTURES / "bad-skill"))
        buf = io.StringIO()
        format_text_report(report, verbose=True, explain=True, file=buf)
        output = buf.getvalue()
        assert "Why it matters:" in output

    def test_without_explain_no_why_it_matters(self):
        """Without --explain, 'Why it matters' should NOT appear."""
        report = run_audit(str(FIXTURES / "bad-skill"))
        buf = io.StringIO()
        format_text_report(report, verbose=True, explain=False, file=buf)
        output = buf.getvalue()
        assert "Why it matters:" not in output

    def test_each_sec_code_has_explanation(self):
        """Every SEC-001 through SEC-009 code must have an explanation."""
        for i in range(1, 10):
            code = f"SEC-{i:03d}"
            explanation = get_explanation(code)
            assert explanation is not None, f"Missing explanation for {code}"
            assert len(explanation) > 20, f"Explanation for {code} is too short"

    def test_str_prefix_has_explanation(self):
        """STR-xxx codes should get prefix-based explanations."""
        explanation = get_explanation("STR-001")
        assert explanation is not None
        assert "structure" in explanation.lower() or "frontmatter" in explanation.lower()

    def test_perm_prefix_has_explanation(self):
        """PERM-xxx codes should get prefix-based explanations."""
        explanation = get_explanation("PERM-001")
        assert explanation is not None
        assert "permission" in explanation.lower() or "privilege" in explanation.lower()

    def test_explain_flag_via_cli(self, monkeypatch):
        """--explain flag should work through the CLI entry point."""
        buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        ret = main(["audit", str(FIXTURES / "bad-skill"), "--explain", "--verbose"])
        output = buf.getvalue()
        assert "Why it matters:" in output
