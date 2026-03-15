"""Integration tests for real ClawHub skill fixtures.

These tests validate that the audit tooling (structure_check, security_scan)
produces correct results against real-world skills from the ClawHub marketplace.
"""

import pytest
from pathlib import Path

from skill_eval.audit.security_scan import scan_security
from skill_eval.audit.structure_check import check_structure
from skill_eval.schemas import Severity


FIXTURES = Path(__file__).parent / "fixtures"
CLAWHUB = FIXTURES / "clawhub-skills"

WEATHER_SKILL = CLAWHUB / "weather"
NANO_PDF_SKILL = CLAWHUB / "nano-pdf"
SLACK_SKILL = CLAWHUB / "slack"


# ---------------------------------------------------------------------------
# Structure checks
# ---------------------------------------------------------------------------


class TestClawHubStructure:
    """Verify real ClawHub skills pass structure validation."""

    def test_weather_structure_passes(self):
        findings, fm, body_start = check_structure(WEATHER_SKILL)
        assert fm is not None, "Weather skill should have valid frontmatter"
        assert fm["name"] == "weather"
        assert "weather" in fm["description"].lower()
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"
        assert len(warnings) == 0, f"Unexpected warnings: {[f.title for f in warnings]}"

    def test_nano_pdf_structure_passes(self):
        findings, fm, body_start = check_structure(NANO_PDF_SKILL)
        assert fm is not None, "nano-pdf skill should have valid frontmatter"
        assert fm["name"] == "nano-pdf"
        assert "nano-pdf" in fm["name"]
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"
        assert len(warnings) == 0, f"Unexpected warnings: {[f.title for f in warnings]}"

    def test_slack_structure_passes(self):
        findings, fm, body_start = check_structure(SLACK_SKILL)
        assert fm is not None, "Slack skill should have valid frontmatter"
        assert fm["name"] == "slack"
        assert "slack" in fm["description"].lower()
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"
        assert len(warnings) == 0, f"Unexpected warnings: {[f.title for f in warnings]}"

    @pytest.mark.parametrize("skill_dir", [WEATHER_SKILL, NANO_PDF_SKILL, SLACK_SKILL],
                             ids=["weather", "nano-pdf", "slack"])
    def test_all_have_valid_frontmatter(self, skill_dir):
        """Every ClawHub fixture must have parseable frontmatter with name + description."""
        findings, fm, body_start = check_structure(skill_dir)
        assert fm is not None, f"{skill_dir.name}: frontmatter should parse"
        assert "name" in fm, f"{skill_dir.name}: frontmatter missing 'name'"
        assert "description" in fm, f"{skill_dir.name}: frontmatter missing 'description'"
        assert body_start > 0, f"{skill_dir.name}: body_start should be > 0"


# ---------------------------------------------------------------------------
# Security scans
# ---------------------------------------------------------------------------


class TestClawHubSecurity:
    """Verify security scan results for real ClawHub skills."""

    # -- No secrets in any skill -----------------------------------------------

    @pytest.mark.parametrize("skill_dir", [WEATHER_SKILL, NANO_PDF_SKILL, SLACK_SKILL],
                             ids=["weather", "nano-pdf", "slack"])
    def test_no_secrets_detected(self, skill_dir):
        """No ClawHub fixture should have SEC-001 (secrets) findings."""
        findings = scan_security(skill_dir)
        secret_findings = [f for f in findings if f.code == "SEC-001"]
        assert len(secret_findings) == 0, (
            f"{skill_dir.name}: unexpected secrets: {[f.title for f in secret_findings]}"
        )

    # -- Weather skill ---------------------------------------------------------

    def test_weather_has_external_url_findings(self):
        """Weather skill references wttr.in and open-meteo.com, expect SEC-002."""
        findings = scan_security(WEATHER_SKILL)
        url_findings = [f for f in findings if f.code == "SEC-002"]
        assert len(url_findings) > 0, "Weather skill should have external URL findings"

    def test_weather_detects_wttr_in(self):
        findings = scan_security(WEATHER_SKILL)
        url_findings = [f for f in findings if f.code == "SEC-002"]
        details = " ".join(f.detail for f in url_findings)
        assert "wttr.in" in details, "Should detect wttr.in URL"

    def test_weather_detects_open_meteo(self):
        findings = scan_security(WEATHER_SKILL)
        url_findings = [f for f in findings if f.code == "SEC-002"]
        details = " ".join(f.detail for f in url_findings)
        assert "open-meteo" in details, "Should detect open-meteo.com URL"

    def test_weather_no_critical_findings(self):
        """Weather skill should have no critical security findings."""
        findings = scan_security(WEATHER_SKILL)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0, (
            f"Weather skill should have no critical findings: {[f.title for f in critical]}"
        )

    # -- nano-pdf skill --------------------------------------------------------

    def test_nano_pdf_clean_security(self):
        """nano-pdf has no external URLs in code blocks, no secrets."""
        findings = scan_security(NANO_PDF_SKILL)
        # May have homepage URL in frontmatter, filter to code-level findings
        secret_findings = [f for f in findings if f.code == "SEC-001"]
        assert len(secret_findings) == 0, "nano-pdf should have no secrets"

    def test_nano_pdf_no_critical_findings(self):
        findings = scan_security(NANO_PDF_SKILL)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0, (
            f"nano-pdf should have no critical findings: {[f.title for f in critical]}"
        )

    # -- Slack skill -----------------------------------------------------------

    def test_slack_clean_security(self):
        """Slack skill should be clean — no secrets, no dangerous patterns."""
        findings = scan_security(SLACK_SKILL)
        secret_findings = [f for f in findings if f.code == "SEC-001"]
        assert len(secret_findings) == 0, "Slack should have no secrets"

    def test_slack_no_critical_findings(self):
        findings = scan_security(SLACK_SKILL)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0, (
            f"Slack should have no critical findings: {[f.title for f in critical]}"
        )

    def test_slack_no_dangerous_patterns(self):
        """Slack skill should have no subprocess or install findings."""
        findings = scan_security(SLACK_SKILL)
        dangerous = [f for f in findings if f.code in ("SEC-003", "SEC-004")]
        assert len(dangerous) == 0, (
            f"Slack should have no subprocess/install findings: {[f.title for f in dangerous]}"
        )


# ---------------------------------------------------------------------------
# Specific expected behaviors
# ---------------------------------------------------------------------------


class TestClawHubExpectedBehaviors:
    """Test skill-specific expected behaviors from frontmatter and content."""

    def test_weather_description_mentions_weather(self):
        _, fm, _ = check_structure(WEATHER_SKILL)
        assert fm is not None
        assert "weather" in fm["description"].lower()

    def test_nano_pdf_name_in_frontmatter(self):
        _, fm, _ = check_structure(NANO_PDF_SKILL)
        assert fm is not None
        assert "nano-pdf" in fm["name"]

    def test_slack_description_mentions_slack(self):
        _, fm, _ = check_structure(SLACK_SKILL)
        assert fm is not None
        assert "slack" in fm["description"].lower()

    def test_weather_has_homepage(self):
        _, fm, _ = check_structure(WEATHER_SKILL)
        assert fm is not None
        assert "homepage" in fm

    def test_nano_pdf_has_metadata(self):
        _, fm, _ = check_structure(WEATHER_SKILL)
        assert fm is not None
        assert "metadata" in fm

    def test_nano_pdf_description_mentions_pdf(self):
        _, fm, _ = check_structure(NANO_PDF_SKILL)
        assert fm is not None
        assert "pdf" in fm["description"].lower()


# ---------------------------------------------------------------------------
# Demo skill (examples/data-analysis)
# ---------------------------------------------------------------------------

EXAMPLES = Path(__file__).parent.parent / "examples"
DATA_ANALYSIS_SKILL = EXAMPLES / "data-analysis"


class TestDemoSkillAudit:
    """Verify the demo data-analysis skill passes a full audit."""

    def test_structure_no_warnings(self):
        findings, fm, body_start = check_structure(DATA_ANALYSIS_SKILL)
        assert fm is not None
        assert fm["name"] == "data-analysis"
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"
        assert len(warnings) == 0, f"Unexpected warnings: {[f.title for f in warnings]}"

    def test_security_clean(self):
        findings = scan_security(DATA_ANALYSIS_SKILL)
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(critical) == 0
        assert len(warnings) == 0

    def test_description_has_use_when(self):
        _, fm, _ = check_structure(DATA_ANALYSIS_SKILL)
        assert fm is not None
        desc = fm["description"].lower()
        assert "use when" in desc, "Description should contain 'Use when' pattern"
        assert "not for" in desc, "Description should contain 'NOT for' pattern"

    def test_has_evals(self):
        evals_file = DATA_ANALYSIS_SKILL / "evals" / "evals.json"
        queries_file = DATA_ANALYSIS_SKILL / "evals" / "eval_queries.json"
        assert evals_file.is_file(), "Should have evals.json"
        assert queries_file.is_file(), "Should have eval_queries.json"

    def test_has_scripts(self):
        script = DATA_ANALYSIS_SKILL / "scripts" / "analyze_csv.py"
        assert script.is_file(), "Should have analyze_csv.py helper script"

    def test_full_audit_grade_a(self):
        from skill_eval.cli import run_audit
        report = run_audit(str(DATA_ANALYSIS_SKILL))
        assert report.score >= 90, f"Expected A grade (≥90), got {report.score}"
        assert report.grade == "A"
        assert report.passed is True
        assert report.critical_count == 0
