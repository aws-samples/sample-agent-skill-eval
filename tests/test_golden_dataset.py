"""Golden dataset tests for the F-to-A lifecycle example.

These tests verify that the three stages of the file-organizer skill
produce expected audit scores. If a code change shifts these scores
unexpectedly, these tests catch it.
"""
import pytest
from pathlib import Path
from skill_eval.cli import run_audit
from skill_eval.schemas import Severity


EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "f-to-a-improvement"


class TestFToALifecycle:
    """Test the three stages of skill improvement."""

    def test_before_is_grade_f(self):
        """before/ should fail with Grade F (criticals present)."""
        report = run_audit(str(EXAMPLES_DIR / "before"))
        assert report.score < 60, f"Expected F (<60), got {report.score}"
        assert report.grade == "F"
        criticals = [f for f in report.findings if f.severity == Severity.CRITICAL]
        assert len(criticals) >= 3, f"Expected >=3 criticals, got {len(criticals)}"

    def test_before_detects_secrets(self):
        """before/ should detect hardcoded secrets."""
        report = run_audit(str(EXAMPLES_DIR / "before"))
        secret_findings = [f for f in report.findings if f.code == "SEC-001"]
        assert len(secret_findings) >= 2, "Should detect at least 2 secrets"

    def test_before_detects_unsafe_install(self):
        """before/ should detect curl|bash pattern."""
        report = run_audit(str(EXAMPLES_DIR / "before"))
        install_findings = [f for f in report.findings if f.code == "SEC-004"]
        assert len(install_findings) >= 1, "Should detect unsafe install"

    def test_v2_is_grade_c(self):
        """v2/ should be Grade C — security fixed, structure needs work."""
        report = run_audit(str(EXAMPLES_DIR / "v2"))
        assert 70 <= report.score < 80, f"Expected C (70-79), got {report.score}"
        assert report.grade == "C"
        criticals = [f for f in report.findings if f.severity == Severity.CRITICAL]
        assert len(criticals) == 0, f"v2 should have 0 criticals, got {len(criticals)}"

    def test_v2_no_secrets(self):
        """v2/ should have no hardcoded secrets."""
        report = run_audit(str(EXAMPLES_DIR / "v2"))
        secret_findings = [f for f in report.findings if f.code == "SEC-001"]
        assert len(secret_findings) == 0, "v2 should have removed all secrets"

    def test_v2_still_has_warnings(self):
        """v2/ should still have warnings (structure/permission issues)."""
        report = run_audit(str(EXAMPLES_DIR / "v2"))
        warnings = [f for f in report.findings if f.severity == Severity.WARNING]
        assert len(warnings) >= 1, "v2 should still have warnings"

    def test_after_is_grade_a(self):
        """after/ should pass with Grade A."""
        report = run_audit(str(EXAMPLES_DIR / "after"))
        assert report.score >= 90, f"Expected A (>=90), got {report.score}"
        assert report.grade == "A"
        criticals = [f for f in report.findings if f.severity == Severity.CRITICAL]
        assert len(criticals) == 0, "after should have 0 criticals"
        warnings = [f for f in report.findings if f.severity == Severity.WARNING]
        assert len(warnings) == 0, "after should have 0 warnings"

    def test_progression_is_monotonic(self):
        """Scores should monotonically increase: before < v2 < after."""
        before = run_audit(str(EXAMPLES_DIR / "before"))
        v2 = run_audit(str(EXAMPLES_DIR / "v2"))
        after = run_audit(str(EXAMPLES_DIR / "after"))
        assert before.score < v2.score < after.score, (
            f"Expected monotonic increase: {before.score} < {v2.score} < {after.score}"
        )


class TestSelfEval:
    """Test that skill-eval's own audit produces expected results."""

    def test_self_eval_default_grade_a(self):
        """skill-eval should score A in default (scoped) mode."""
        repo_root = Path(__file__).parent.parent
        report = run_audit(str(repo_root))
        assert report.score >= 90, f"Self-eval expected A (>=90), got {report.score}"
        assert report.grade == "A"

    def test_self_eval_no_criticals(self):
        """skill-eval should have zero critical findings in default mode."""
        repo_root = Path(__file__).parent.parent
        report = run_audit(str(repo_root))
        criticals = [f for f in report.findings if f.severity == Severity.CRITICAL]
        assert len(criticals) == 0, f"Expected 0 criticals, got {len(criticals)}"

    def test_self_eval_include_all_grade_f(self):
        """skill-eval with --include-all should be Grade F (test fixtures)."""
        repo_root = Path(__file__).parent.parent
        report = run_audit(str(repo_root), include_all=True)
        assert report.score < 60, f"include-all expected F (<60), got {report.score}"
        assert report.grade == "F"
