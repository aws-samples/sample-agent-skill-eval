"""Tests for structure_check module."""

import pytest
from pathlib import Path

from skill_eval.audit.structure_check import check_structure, _parse_frontmatter, _simple_yaml_parse
from skill_eval.schemas import Severity


FIXTURES = Path(__file__).parent / "fixtures"


class TestParseFrontmatter:
    """Test YAML frontmatter parsing."""

    def test_valid_frontmatter(self):
        content = "---\nname: test-skill\ndescription: A test skill.\n---\n\n# Body"
        fm, error, body_start = _parse_frontmatter(content)
        assert error is None
        assert fm["name"] == "test-skill"
        assert fm["description"] == "A test skill."
        assert body_start == 4

    def test_missing_opening(self):
        content = "name: test\n---\n"
        fm, error, body_start = _parse_frontmatter(content)
        assert fm is None
        assert "does not start with" in error

    def test_missing_closing(self):
        content = "---\nname: test\n"
        fm, error, body_start = _parse_frontmatter(content)
        assert fm is None
        assert "not closed" in error

    def test_quoted_values(self):
        content = '---\nname: test\ndescription: "A quoted description."\n---\n'
        fm, error, _ = _parse_frontmatter(content)
        assert error is None
        assert fm["description"] == "A quoted description."


class TestSimpleYamlParse:
    """Test the minimal YAML parser."""

    def test_basic_key_value(self):
        result = _simple_yaml_parse("name: my-skill\ndescription: Does things")
        assert result["name"] == "my-skill"
        assert result["description"] == "Does things"

    def test_nested_metadata(self):
        yaml_text = "name: test\nmetadata:\n  author: test-org\n  version: '1.0'"
        result = _simple_yaml_parse(yaml_text)
        assert result["name"] == "test"
        assert isinstance(result["metadata"], dict)
        assert result["metadata"]["author"] == "test-org"

    def test_comments_ignored(self):
        result = _simple_yaml_parse("# A comment\nname: test\n# Another comment")
        assert result["name"] == "test"
        assert len(result) == 1

    def test_empty_input(self):
        result = _simple_yaml_parse("")
        assert result == {}

    def test_only_comments(self):
        result = _simple_yaml_parse("# comment 1\n# comment 2\n")
        assert result == {}

    def test_single_quoted_value(self):
        result = _simple_yaml_parse("name: 'my-skill'")
        assert result["name"] == "my-skill"

    def test_double_quoted_value(self):
        result = _simple_yaml_parse('name: "my-skill"')
        assert result["name"] == "my-skill"

    def test_empty_value(self):
        result = _simple_yaml_parse("name:\n")
        assert result["name"] == ""

    def test_hyphenated_key(self):
        result = _simple_yaml_parse("allowed-tools: Read Write Bash")
        assert result["allowed-tools"] == "Read Write Bash"


class TestCheckStructure:
    """Test full structure check against fixture skills."""

    def test_good_skill(self):
        findings, fm, body_start = check_structure(FIXTURES / "good-skill")
        assert fm is not None
        assert fm["name"] == "good-skill"
        # Good skill should have zero critical/warning findings
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        warnings = [f for f in findings if f.severity == Severity.WARNING]
        assert len(critical) == 0, f"Unexpected critical: {[f.title for f in critical]}"
        assert len(warnings) == 0, f"Unexpected warnings: {[f.title for f in warnings]}"

    def test_bad_skill_name(self):
        findings, fm, _ = check_structure(FIXTURES / "bad-skill")
        codes = [f.code for f in findings]
        # bad-skill has name "Bad_Skill" which violates format
        assert "STR-007" in codes, "Should flag invalid name format"
        # Name doesn't match directory
        assert "STR-008" in codes, "Should flag name/directory mismatch"

    def test_bad_skill_description(self):
        findings, fm, _ = check_structure(FIXTURES / "bad-skill")
        codes = [f.code for f in findings]
        # "Bad." is <20 chars
        assert "STR-011" in codes, "Should flag short description"

    def test_no_frontmatter(self):
        findings, fm, _ = check_structure(FIXTURES / "no-frontmatter")
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0, "Missing frontmatter should be critical"
        assert any(f.code == "STR-004" for f in critical)

    def test_missing_skill_md(self):
        findings, fm, _ = check_structure(FIXTURES / "empty-dir")
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0, "Missing SKILL.md should be critical"
        assert any(f.code == "STR-002" for f in critical)

    def test_nonexistent_path(self):
        findings, fm, _ = check_structure("/nonexistent/path")
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) > 0
        assert any(f.code == "STR-001" for f in critical)

    def test_real_skill_weather(self):
        """Test against a real installed skill."""
        weather_path = Path("/opt/homebrew/lib/node_modules/openclaw/skills/weather")
        if not weather_path.exists():
            pytest.skip("OpenClaw weather skill not installed")
        findings, fm, _ = check_structure(weather_path)
        assert fm is not None
        assert fm["name"] == "weather"
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        assert len(critical) == 0
