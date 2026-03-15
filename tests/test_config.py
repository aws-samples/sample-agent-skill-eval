"""Tests for skill_eval.config module."""

import pytest
import textwrap
from pathlib import Path

from skill_eval.config import load_config, apply_config, AuditConfig, CustomRule
from skill_eval.schemas import Finding, Severity, Category


@pytest.fixture
def tmp_skill(tmp_path):
    """Create a minimal skill directory."""
    (tmp_path / "SKILL.md").write_text("---\nname: test\n---\nTest skill\n")
    return tmp_path


class TestLoadConfig:
    """Test configuration file loading."""

    def test_no_config_file_returns_empty(self, tmp_skill):
        config = load_config(tmp_skill)
        assert config.ignore == set()
        assert config.severity_overrides == {}
        assert config.safe_domains == set()
        assert config.custom_rules == []
        assert config.min_score == 0

    def test_loads_yaml_config(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text(textwrap.dedent("""\
            audit:
              ignore:
                - STR-008
                - STR-017
              severity_overrides:
                SEC-002: WARNING
              safe_domains:
                - api.internal.example.com
              min_score: 70
        """))
        config = load_config(tmp_skill)
        assert "STR-008" in config.ignore
        assert "STR-017" in config.ignore
        assert config.severity_overrides["SEC-002"] == "WARNING"
        assert "api.internal.example.com" in config.safe_domains
        assert config.min_score == 70

    def test_loads_yml_extension(self, tmp_skill):
        (tmp_skill / ".skilleval.yml").write_text(textwrap.dedent("""\
            audit:
              ignore:
                - SEC-001
        """))
        config = load_config(tmp_skill)
        assert "SEC-001" in config.ignore

    def test_yaml_preferred_over_yml(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text("audit:\n  ignore:\n    - YAML-FILE\n")
        (tmp_skill / ".skilleval.yml").write_text("audit:\n  ignore:\n    - YML-FILE\n")
        config = load_config(tmp_skill)
        assert "YAML-FILE" in config.ignore
        assert "YML-FILE" not in config.ignore

    def test_searches_parent_directories(self, tmp_skill):
        sub = tmp_skill / "sub" / "dir"
        sub.mkdir(parents=True)
        (tmp_skill / ".skilleval.yaml").write_text("audit:\n  ignore:\n    - STR-008\n")
        config = load_config(sub)
        assert "STR-008" in config.ignore

    def test_empty_yaml_returns_empty(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text("")
        config = load_config(tmp_skill)
        assert config.ignore == set()

    def test_invalid_yaml_returns_empty(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text("{{{{invalid yaml")
        config = load_config(tmp_skill)
        assert config.ignore == set()

    def test_non_dict_yaml_returns_empty(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text("- just a list\n")
        config = load_config(tmp_skill)
        assert config.ignore == set()

    def test_invalid_severity_ignored(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text(textwrap.dedent("""\
            audit:
              severity_overrides:
                SEC-001: EXTREME
                SEC-002: warning
        """))
        config = load_config(tmp_skill)
        assert "SEC-001" not in config.severity_overrides  # EXTREME is invalid
        assert config.severity_overrides["SEC-002"] == "WARNING"  # lowercase normalized

    def test_custom_rules(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text(textwrap.dedent("""\
            audit:
              custom_rules:
                - code: CUSTOM-001
                  pattern: "TODO|FIXME"
                  severity: INFO
                  message: "Found TODO/FIXME"
        """))
        config = load_config(tmp_skill)
        assert len(config.custom_rules) == 1
        assert config.custom_rules[0].code == "CUSTOM-001"
        assert config.custom_rules[0].regex.search("TODO: fix this")

    def test_custom_rule_invalid_regex_skipped(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text(textwrap.dedent("""\
            audit:
              custom_rules:
                - code: BAD-001
                  pattern: "[invalid"
                - code: GOOD-001
                  pattern: "hello"
        """))
        config = load_config(tmp_skill)
        # Bad regex skipped, good one kept
        assert len(config.custom_rules) == 1
        assert config.custom_rules[0].code == "GOOD-001"


class TestApplyConfig:
    """Test applying config to findings."""

    def _finding(self, code="SEC-001", severity="CRITICAL", message="test"):
        return Finding(
            code=code,
            severity=Severity(severity),
            category=Category.SECURITY,
            title=message,
            detail=message,
        )

    def test_ignore_removes_findings(self):
        findings = [self._finding("SEC-001"), self._finding("STR-008", "INFO")]
        config = AuditConfig(ignore={"STR-008"})
        result = apply_config(findings, config)
        assert len(result) == 1
        assert result[0].code == "SEC-001"

    def test_severity_override(self):
        findings = [self._finding("SEC-002", "CRITICAL")]
        config = AuditConfig(severity_overrides={"SEC-002": "WARNING"})
        result = apply_config(findings, config)
        assert len(result) == 1
        assert result[0].severity == Severity.WARNING
        assert result[0].code == "SEC-002"

    def test_empty_config_passes_through(self):
        findings = [self._finding("SEC-001"), self._finding("STR-008", "INFO")]
        config = AuditConfig.empty()
        result = apply_config(findings, config)
        assert len(result) == 2

    def test_combined_ignore_and_override(self):
        findings = [
            self._finding("SEC-001", "CRITICAL"),
            self._finding("SEC-002", "CRITICAL"),
            self._finding("STR-008", "INFO"),
        ]
        config = AuditConfig(
            ignore={"STR-008"},
            severity_overrides={"SEC-002": "WARNING"},
        )
        result = apply_config(findings, config)
        assert len(result) == 2
        codes = {f.code: f.severity for f in result}
        assert codes["SEC-001"] == Severity.CRITICAL
        assert codes["SEC-002"] == Severity.WARNING


class TestMinScoreCLI:
    """Test --min-score flag behavior."""

    def test_min_score_from_config(self, tmp_skill):
        """Verify config loads min_score correctly."""
        (tmp_skill / ".skilleval.yaml").write_text("audit:\n  min_score: 80\n")
        config = load_config(tmp_skill)
        assert config.min_score == 80

    def test_min_score_zero_default(self, tmp_skill):
        config = load_config(tmp_skill)
        assert config.min_score == 0

    def test_min_score_non_int_falls_back(self, tmp_skill):
        (tmp_skill / ".skilleval.yaml").write_text("audit:\n  min_score: 'high'\n")
        config = load_config(tmp_skill)
        assert config.min_score == 0
