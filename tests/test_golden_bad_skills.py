"""Golden dataset tests for skill-eval.

Verifies that known skills produce expected audit scores and findings.
These serve as regression tests — if a code change causes score drift,
we want to know about it.

Bad skills represent realistic mistakes (not malicious code).
Good skills are baselines from ClawHub and self-eval.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from skill_eval.cli import run_audit
from skill_eval.schemas import Severity

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
GOLDEN = EXAMPLES / "golden-dataset" / "bad-skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestBadSkillSloppyWeather(unittest.TestCase):
    """sloppy-weather: hardcoded API key, short description."""

    def setUp(self):
        self.report = run_audit(str(GOLDEN / "sloppy-weather"))

    def test_grade_is_f(self):
        self.assertEqual(self.report.grade, "F")

    def test_has_criticals(self):
        self.assertGreater(self.report.critical_count, 0,
                           "Should detect hardcoded API key as critical")

    def test_detects_secret(self):
        codes = [f.code for f in self.report.findings]
        self.assertIn("SEC-001", codes, "Should detect SEC-001 (secret)")

    def test_detects_short_description(self):
        codes = [f.code for f in self.report.findings]
        self.assertIn("STR-011", codes, "Should flag short description")

    def test_score_in_range(self):
        self.assertGreaterEqual(self.report.score, 30)
        self.assertLessEqual(self.report.score, 70)


class TestBadSkillOverPermissioned(unittest.TestCase):
    """over-permissioned: Bash(*), sensitive dirs, sudo."""

    def setUp(self):
        self.report = run_audit(str(GOLDEN / "over-permissioned"))

    def test_grade_is_d_or_f(self):
        self.assertIn(self.report.grade, ("D", "F"))

    def test_detects_unscoped_bash(self):
        codes = [f.code for f in self.report.findings]
        self.assertIn("PERM-001", codes, "Should detect unrestricted Bash(*)")

    def test_detects_sudo(self):
        findings = [f for f in self.report.findings
                    if f.code == "PERM-004" and "sudo" in f.title.lower()]
        self.assertGreater(len(findings), 0, "Should detect sudo reference")

    def test_detects_sensitive_dirs(self):
        findings = [f for f in self.report.findings
                    if f.code == "PERM-004" and "sensitive" in f.title.lower()]
        self.assertGreater(len(findings), 0,
                           "Should detect sensitive directory access")

    def test_score_in_range(self):
        self.assertGreaterEqual(self.report.score, 40)
        self.assertLessEqual(self.report.score, 75)


class TestBadSkillInsecureInstaller(unittest.TestCase):
    """insecure-installer: curl|bash, pickle, npx -y."""

    def setUp(self):
        self.report = run_audit(str(GOLDEN / "insecure-installer"))

    def test_grade_is_f(self):
        self.assertEqual(self.report.grade, "F")

    def test_score_is_very_low(self):
        self.assertLessEqual(self.report.score, 10,
                             "Should score very low due to multiple criticals")

    def test_has_many_criticals(self):
        self.assertGreaterEqual(self.report.critical_count, 4,
                                "Should have multiple critical findings")

    def test_detects_curl_pipe_bash(self):
        findings = [f for f in self.report.findings
                    if f.code == "SEC-004" and "curl" in f.detail.lower()]
        self.assertGreater(len(findings), 0, "Should detect curl|bash")

    def test_detects_pickle(self):
        findings = [f for f in self.report.findings
                    if f.code == "SEC-006"]
        self.assertGreater(len(findings), 0, "Should detect pickle.load")

    def test_detects_npx(self):
        findings = [f for f in self.report.findings
                    if f.code == "SEC-009"]
        self.assertGreater(len(findings), 0, "Should detect npx -y")


class TestBadSkillPoorStructure(unittest.TestCase):
    """poor-structure: no frontmatter, eval() in script."""

    def setUp(self):
        self.report = run_audit(str(GOLDEN / "poor-structure"))

    def test_grade_is_d_or_f(self):
        self.assertIn(self.report.grade, ("D", "F"))

    def test_has_criticals(self):
        self.assertGreater(self.report.critical_count, 0,
                           "Should flag missing frontmatter as critical")

    def test_detects_invalid_frontmatter(self):
        codes = [f.code for f in self.report.findings]
        self.assertIn("STR-004", codes, "Should detect missing/invalid frontmatter")

    def test_score_in_range(self):
        self.assertGreaterEqual(self.report.score, 30)
        self.assertLessEqual(self.report.score, 75)


class TestGoodSkillBaselines(unittest.TestCase):
    """ClawHub skills + self-eval should score high."""

    def test_weather_is_a(self):
        report = run_audit(str(FIXTURES / "clawhub-skills" / "weather"))
        self.assertEqual(report.grade, "A")
        self.assertGreaterEqual(report.score, 85)

    def test_nano_pdf_is_a(self):
        report = run_audit(str(FIXTURES / "clawhub-skills" / "nano-pdf"))
        self.assertEqual(report.grade, "A")
        self.assertGreaterEqual(report.score, 95)

    def test_slack_is_a(self):
        report = run_audit(str(FIXTURES / "clawhub-skills" / "slack"))
        self.assertEqual(report.grade, "A")
        self.assertGreaterEqual(report.score, 95)


class TestGoldenDatasetCoverage(unittest.TestCase):
    """Verify the golden dataset covers diverse finding categories."""

    def test_bad_skills_cover_all_categories(self):
        """Bad skills collectively should trigger SEC, STR, and PERM findings."""
        all_prefixes = set()
        for skill_name in ("sloppy-weather", "over-permissioned",
                           "insecure-installer", "poor-structure"):
            report = run_audit(str(GOLDEN / skill_name))
            for f in report.findings:
                all_prefixes.add(f.code.split("-")[0])  # SEC, STR, PERM

        self.assertIn("SEC", all_prefixes, "Should have security findings")
        self.assertIn("STR", all_prefixes, "Should have structure findings")
        self.assertIn("PERM", all_prefixes, "Should have permission findings")

    def test_bad_skills_cover_multiple_severities(self):
        """Bad skills collectively should produce CRITICAL, WARNING, and INFO."""
        all_severities = set()
        for skill_name in ("sloppy-weather", "over-permissioned",
                           "insecure-installer", "poor-structure"):
            report = run_audit(str(GOLDEN / skill_name))
            for f in report.findings:
                all_severities.add(f.severity)

        self.assertIn(Severity.CRITICAL, all_severities)
        self.assertIn(Severity.WARNING, all_severities)
        self.assertIn(Severity.INFO, all_severities)
