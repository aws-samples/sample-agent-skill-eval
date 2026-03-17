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


class TestBestPracticeChecks:
    """Test Anthropic best practice checks (STR-018, STR-019, STR-020)."""

    def _make_skill(self, tmp_path, name="test-skill", description="A test skill that does useful things for testing purposes."):
        """Helper: create a minimal valid skill directory with given name/description."""
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"---\nname: {name}\ndescription: \"{description}\"\n---\n\n# Test\n\nInstructions here.\n")
        return skill_dir

    # --- STR-018: Reserved words in name ---

    def test_name_with_claude_reserved_word(self, tmp_path):
        skill_dir = self._make_skill(tmp_path, name="claude-helper", description="Helps with code review and analysis tasks.")
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-018" in codes, "Should flag 'claude' in skill name"

    def test_name_with_anthropic_reserved_word(self, tmp_path):
        skill_dir = self._make_skill(tmp_path, name="anthropic-tools", description="Provides various analysis tools for development.")
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-018" in codes, "Should flag 'anthropic' in skill name"

    def test_name_without_reserved_words(self, tmp_path):
        skill_dir = self._make_skill(tmp_path, name="code-review", description="Reviews code for bugs, security issues, and best practices.")
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-018" not in codes, "Should not flag normal skill name"

    # --- STR-019: XML tags in description ---

    def test_description_with_xml_tags(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="xml-test",
            description="Processes data <important>and generates reports</important>.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-019" in codes, "Should flag XML tags in description"

    def test_description_with_html_tags(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="html-test",
            description="<b>Analyzes</b> code for security vulnerabilities and best practices.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-019" in codes, "Should flag HTML tags in description"

    def test_description_without_xml_tags(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="no-xml-test",
            description="Analyzes code for security vulnerabilities and best practices.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-019" not in codes, "Should not flag clean description"

    # --- STR-020: Third person description ---

    def test_description_first_person(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="first-person-test",
            description="I can help you process Excel files and generate reports.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-020" in codes, "Should flag first-person description"

    def test_description_second_person(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="second-person-test",
            description="You can use this to process Excel files and generate reports.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-020" in codes, "Should flag second-person description"

    def test_description_third_person(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="third-person-test",
            description="Processes Excel files and generates reports. Use when working with spreadsheet data.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-020" not in codes, "Should not flag third-person description"

    def test_description_im_contraction(self, tmp_path):
        skill_dir = self._make_skill(
            tmp_path,
            name="contraction-test",
            description="I'm a helpful skill that processes data files and outputs summaries.",
        )
        findings, fm, _ = check_structure(skill_dir)
        codes = [f.code for f in findings]
        assert "STR-020" in codes, "Should flag I'm contraction"
