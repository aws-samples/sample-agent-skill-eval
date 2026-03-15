"""Tests for skill_eval.init — scaffold generation for skill evaluations."""

import json
import pytest

from skill_eval.init import generate_eval_scaffold, _parse_frontmatter


class TestGenerateEvalScaffold:
    """Test scaffold generation with a well-formed skill directory."""

    def test_generates_evals_and_queries(self, tmp_path):
        """Creates evals.json and eval_queries.json from SKILL.md."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Analyze CSV files\n---\n# My Skill\n"
        )

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 0

        evals_file = skill_dir / "evals" / "evals.json"
        queries_file = skill_dir / "evals" / "eval_queries.json"
        assert evals_file.exists()
        assert queries_file.exists()

        evals = json.loads(evals_file.read_text())
        assert len(evals) == 2
        assert evals[0]["id"] == "my-skill-eval-1"
        assert "my-skill" in evals[0]["prompt"]

        queries = json.loads(queries_file.read_text())
        assert len(queries) == 4
        triggers = [q for q in queries if q["should_trigger"]]
        non_triggers = [q for q in queries if not q["should_trigger"]]
        assert len(triggers) == 2
        assert len(non_triggers) == 2

    def test_uses_description_in_templates(self, tmp_path):
        """Skill description should appear in generated eval content."""
        skill_dir = tmp_path / "csv-tool"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: csv-tool\ndescription: Parse and visualize CSV data\n---\n"
        )

        generate_eval_scaffold(str(skill_dir))

        evals = json.loads((skill_dir / "evals" / "evals.json").read_text())
        assert "Parse and visualize CSV data" in evals[0]["prompt"]

        queries = json.loads((skill_dir / "evals" / "eval_queries.json").read_text())
        assert any("Parse and visualize CSV data" in q["query"] for q in queries)


class TestSkipExistingFiles:
    """Test that existing files are not overwritten."""

    def test_skip_when_evals_exist(self, tmp_path):
        """Does not overwrite evals.json if it already exists."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill\ndescription: test\n---\n")

        evals_dir = skill_dir / "evals"
        evals_dir.mkdir()
        original_content = '[{"id": "original"}]'
        (evals_dir / "evals.json").write_text(original_content)

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 0

        # evals.json should be unchanged
        assert (evals_dir / "evals.json").read_text() == original_content
        # eval_queries.json should be created
        assert (evals_dir / "eval_queries.json").exists()

    def test_skip_when_queries_exist(self, tmp_path):
        """Does not overwrite eval_queries.json if it already exists."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill\ndescription: test\n---\n")

        evals_dir = skill_dir / "evals"
        evals_dir.mkdir()
        original_content = '[{"query": "original", "should_trigger": true}]'
        (evals_dir / "eval_queries.json").write_text(original_content)

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 0

        # eval_queries.json should be unchanged
        assert (evals_dir / "eval_queries.json").read_text() == original_content
        # evals.json should be created
        assert (evals_dir / "evals.json").exists()

    def test_skip_both_existing(self, tmp_path):
        """When both files exist, both are skipped and rc is still 0."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: skill\ndescription: test\n---\n")

        evals_dir = skill_dir / "evals"
        evals_dir.mkdir()
        (evals_dir / "evals.json").write_text("[]")
        (evals_dir / "eval_queries.json").write_text("[]")

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 0
        # Both remain unchanged
        assert (evals_dir / "evals.json").read_text() == "[]"
        assert (evals_dir / "eval_queries.json").read_text() == "[]"


class TestMissingSkillMd:
    """Test behavior when SKILL.md is missing."""

    def test_returns_error_for_missing_skill_md(self, tmp_path):
        """Returns 1 when SKILL.md does not exist."""
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 1

    def test_no_evals_dir_created_on_error(self, tmp_path):
        """The evals/ directory should not be created if SKILL.md is missing."""
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        generate_eval_scaffold(str(skill_dir))
        assert not (skill_dir / "evals").exists()


class TestGeneratedJsonValidity:
    """Test that generated JSON files are valid and well-structured."""

    def test_evals_json_is_valid(self, tmp_path):
        """Generated evals.json should be valid JSON with required fields."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: json-test\ndescription: Test JSON validity\n---\n"
        )

        generate_eval_scaffold(str(skill_dir))

        evals = json.loads((skill_dir / "evals" / "evals.json").read_text())
        assert isinstance(evals, list)
        for case in evals:
            assert "id" in case
            assert "prompt" in case
            assert "assertions" in case
            assert isinstance(case["assertions"], list)
            assert len(case["assertions"]) >= 1

    def test_queries_json_is_valid(self, tmp_path):
        """Generated eval_queries.json should be valid JSON with required fields."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: json-test\ndescription: Test JSON validity\n---\n"
        )

        generate_eval_scaffold(str(skill_dir))

        queries = json.loads((skill_dir / "evals" / "eval_queries.json").read_text())
        assert isinstance(queries, list)
        for q in queries:
            assert "query" in q
            assert "should_trigger" in q
            assert isinstance(q["should_trigger"], bool)

    def test_frontmatter_without_description(self, tmp_path):
        """Falls back gracefully when description is missing from frontmatter."""
        skill_dir = tmp_path / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n# No desc\n")

        rc = generate_eval_scaffold(str(skill_dir))
        assert rc == 0

        evals = json.loads((skill_dir / "evals" / "evals.json").read_text())
        assert len(evals) == 2
        # Should use fallback description
        assert "no-desc" in evals[0]["prompt"]


class TestParseFrontmatter:
    """Test the frontmatter parser directly."""

    def test_parses_name_and_description(self, tmp_path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: "Does cool things"\n---\n'
        )
        fm = _parse_frontmatter(str(skill_dir))
        assert fm["name"] == "my-skill"
        assert fm["description"] == "Does cool things"

    def test_missing_skill_md_raises(self, tmp_path):
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            _parse_frontmatter(str(skill_dir))

    def test_no_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a heading\nNo frontmatter here.\n")
        fm = _parse_frontmatter(str(skill_dir))
        assert fm["name"] == ""
        assert fm["description"] == ""
