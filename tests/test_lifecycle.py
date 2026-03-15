"""Tests for lifecycle management module."""

import json
import shutil
import pytest
from pathlib import Path

from skill_eval.lifecycle import (
    compute_skill_fingerprint,
    detect_changes,
    check_lifecycle,
    save_version,
    list_versions,
    VersionEntry,
    _get_history_path,
    _load_history,
    _save_history,
)
from skill_eval.cli import main


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def clean_good_skill(tmp_path):
    """Create a clean copy of good-skill for lifecycle testing."""
    src = FIXTURES / "good-skill"
    dst = tmp_path / "good-skill"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def minimal_skill(tmp_path):
    """Create a minimal skill directory for testing."""
    skill_dir = tmp_path / "minimal-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: minimal-skill\n"
        "description: A minimal test skill for lifecycle testing. Use when testing.\n"
        "license: MIT\n"
        "---\n\n# Minimal Skill\n\nTest content.\n"
    )
    return skill_dir


class TestComputeFingerprint:
    """Test skill fingerprinting."""

    def test_compute_fingerprint_basic(self, clean_good_skill):
        """Computes fingerprint for a skill directory."""
        result = compute_skill_fingerprint(str(clean_good_skill))
        assert "file_hashes" in result
        assert "fingerprint" in result
        assert isinstance(result["file_hashes"], dict)
        assert isinstance(result["fingerprint"], str)
        assert len(result["fingerprint"]) == 64  # SHA-256 hex digest
        # Should include SKILL.md
        assert "SKILL.md" in result["file_hashes"]

    def test_compute_fingerprint_deterministic(self, clean_good_skill):
        """Same input produces the same hash."""
        result1 = compute_skill_fingerprint(str(clean_good_skill))
        result2 = compute_skill_fingerprint(str(clean_good_skill))
        assert result1["fingerprint"] == result2["fingerprint"]
        assert result1["file_hashes"] == result2["file_hashes"]

    def test_fingerprint_changes_on_modification(self, minimal_skill):
        """Modifying a file changes the fingerprint."""
        fp1 = compute_skill_fingerprint(str(minimal_skill))
        (minimal_skill / "SKILL.md").write_text(
            "---\n"
            "name: minimal-skill\n"
            "description: Updated description for lifecycle testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Minimal Skill\n\nUpdated content.\n"
        )
        fp2 = compute_skill_fingerprint(str(minimal_skill))
        assert fp1["fingerprint"] != fp2["fingerprint"]

    def test_fingerprint_missing_dir(self):
        """Raises FileNotFoundError for nonexistent directory."""
        with pytest.raises(FileNotFoundError):
            compute_skill_fingerprint("/nonexistent/path")

    def test_fingerprint_skips_hidden_and_generated(self, minimal_skill):
        """Hidden files, __pycache__, and lifecycle dirs are excluded."""
        (minimal_skill / ".hidden").write_text("secret")
        pycache = minimal_skill / "__pycache__"
        pycache.mkdir()
        (pycache / "cache.pyc").write_text("bytecode")
        lifecycle_dir = minimal_skill / "evals" / "lifecycle"
        lifecycle_dir.mkdir(parents=True)
        (lifecycle_dir / "history.json").write_text("{}")

        result = compute_skill_fingerprint(str(minimal_skill))
        for rel_path in result["file_hashes"]:
            assert not rel_path.startswith(".")
            assert "__pycache__" not in rel_path
            assert "lifecycle" not in rel_path


class TestDetectChanges:
    """Test change detection."""

    def test_detect_changes_no_baseline(self, minimal_skill):
        """No previous baseline — all files reported as added."""
        result = detect_changes(str(minimal_skill))
        assert result["changed"] is True
        assert len(result["added"]) > 0
        assert "SKILL.md" in result["added"]
        assert result["modified"] == []
        assert result["deleted"] == []
        assert result["baseline_fingerprint"] is None

    def test_detect_changes_no_changes(self, minimal_skill):
        """Unchanged skill after saving a version."""
        save_version(str(minimal_skill), label="v1.0")
        hp = str(_get_history_path(minimal_skill.resolve()))
        result = detect_changes(str(minimal_skill), baseline_path=hp)
        assert result["changed"] is False
        assert result["added"] == []
        assert result["modified"] == []
        assert result["deleted"] == []

    def test_detect_changes_modified(self, minimal_skill):
        """Detect modified SKILL.md."""
        save_version(str(minimal_skill), label="v1.0")
        hp = str(_get_history_path(minimal_skill.resolve()))

        # Modify SKILL.md
        (minimal_skill / "SKILL.md").write_text(
            "---\n"
            "name: minimal-skill\n"
            "description: Modified description for lifecycle testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Minimal Skill\n\nModified.\n"
        )

        result = detect_changes(str(minimal_skill), baseline_path=hp)
        assert result["changed"] is True
        assert "SKILL.md" in result["modified"]

    def test_detect_changes_added_file(self, minimal_skill):
        """Detect new file added."""
        save_version(str(minimal_skill), label="v1.0")
        hp = str(_get_history_path(minimal_skill.resolve()))

        # Add a new file
        scripts_dir = minimal_skill / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "helper.py").write_text("#!/usr/bin/env python3\nprint('hello')\n")

        result = detect_changes(str(minimal_skill), baseline_path=hp)
        assert result["changed"] is True
        assert any("helper.py" in f for f in result["added"])

    def test_detect_changes_deleted_file(self, minimal_skill):
        """Detect file removed."""
        # Add a file, save version, then delete it
        extra = minimal_skill / "extra.txt"
        extra.write_text("temporary")
        save_version(str(minimal_skill), label="v1.0")
        hp = str(_get_history_path(minimal_skill.resolve()))

        extra.unlink()

        result = detect_changes(str(minimal_skill), baseline_path=hp)
        assert result["changed"] is True
        assert "extra.txt" in result["deleted"]


class TestCheckLifecycle:
    """Test lifecycle check function."""

    def test_check_lifecycle_initial(self, minimal_skill, capsys):
        """First run creates history and returns 0."""
        rc = check_lifecycle(str(minimal_skill))
        assert rc == 0
        captured = capsys.readouterr()
        assert "Initial version recorded" in captured.out

        # History file should now exist
        hp = _get_history_path(minimal_skill.resolve())
        assert hp.is_file()
        history = _load_history(hp)
        assert len(history["versions"]) == 1
        assert history["versions"][0]["label"] == "initial"

    def test_check_lifecycle_no_changes(self, minimal_skill, capsys):
        """Subsequent run with no changes returns 0."""
        check_lifecycle(str(minimal_skill))  # initial
        rc = check_lifecycle(str(minimal_skill))
        assert rc == 0
        captured = capsys.readouterr()
        assert "No changes detected" in captured.out

    def test_check_lifecycle_changes_detected(self, minimal_skill, capsys):
        """Changes trigger warning and return 1."""
        check_lifecycle(str(minimal_skill))  # initial

        # Modify the skill
        (minimal_skill / "SKILL.md").write_text(
            "---\n"
            "name: minimal-skill\n"
            "description: Changed description for lifecycle testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Minimal Skill\n\nChanged.\n"
        )

        rc = check_lifecycle(str(minimal_skill))
        assert rc == 1
        captured = capsys.readouterr()
        assert "Changes detected" in captured.out
        assert "SKILL.md" in captured.out

    def test_check_lifecycle_json_format(self, minimal_skill, capsys):
        """JSON output format works for all states."""
        # Initial
        rc = check_lifecycle(str(minimal_skill), format="json")
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "initial"

        # Unchanged
        rc = check_lifecycle(str(minimal_skill), format="json")
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "unchanged"

        # Changed
        (minimal_skill / "SKILL.md").write_text(
            "---\n"
            "name: minimal-skill\n"
            "description: JSON format test for lifecycle testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Minimal Skill\n\nJSON test.\n"
        )
        rc = check_lifecycle(str(minimal_skill), format="json")
        assert rc == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "changed"
        assert "SKILL.md" in data["modified"]

    def test_check_lifecycle_custom_history_path(self, minimal_skill, tmp_path):
        """Custom history path is respected."""
        custom_hp = str(tmp_path / "custom_history.json")
        rc = check_lifecycle(str(minimal_skill), history_path=custom_hp)
        assert rc == 0
        assert Path(custom_hp).is_file()


class TestSaveVersion:
    """Test version saving."""

    def test_save_version_with_label(self, minimal_skill, capsys):
        """Custom version label is stored."""
        save_version(str(minimal_skill), label="v1.2")
        captured = capsys.readouterr()
        assert "v1.2" in captured.out

        hp = _get_history_path(minimal_skill.resolve())
        history = _load_history(hp)
        assert len(history["versions"]) == 1
        assert history["versions"][0]["label"] == "v1.2"
        assert history["versions"][0]["fingerprint"]
        assert history["versions"][0]["file_hashes"]

    def test_save_version_auto_label(self, minimal_skill):
        """Auto-generated label when none provided."""
        save_version(str(minimal_skill))
        hp = _get_history_path(minimal_skill.resolve())
        history = _load_history(hp)
        assert len(history["versions"]) == 1
        label = history["versions"][0]["label"]
        # Auto label starts with "v" and contains date
        assert label.startswith("v")
        assert len(label) > 5

    def test_save_multiple_versions(self, minimal_skill):
        """Multiple versions accumulate in history."""
        save_version(str(minimal_skill), label="v1.0")
        save_version(str(minimal_skill), label="v1.1")
        save_version(str(minimal_skill), label="v1.2")

        hp = _get_history_path(minimal_skill.resolve())
        history = _load_history(hp)
        assert len(history["versions"]) == 3
        labels = [v["label"] for v in history["versions"]]
        assert labels == ["v1.0", "v1.1", "v1.2"]


class TestListVersions:
    """Test version listing."""

    def test_list_versions_empty(self, minimal_skill, capsys):
        """No history prints informative message."""
        list_versions(str(minimal_skill))
        captured = capsys.readouterr()
        assert "No version history found" in captured.out

    def test_list_versions_multiple(self, minimal_skill, capsys):
        """Multiple saved versions are listed."""
        save_version(str(minimal_skill), label="v1.0")
        save_version(str(minimal_skill), label="v2.0")

        # Clear captured output from save_version calls
        capsys.readouterr()

        list_versions(str(minimal_skill))
        captured = capsys.readouterr()
        assert "2 entries" in captured.out
        assert "v1.0" in captured.out
        assert "v2.0" in captured.out


class TestVersionEntry:
    """Test VersionEntry dataclass."""

    def test_to_dict(self):
        entry = VersionEntry(
            timestamp="2025-01-01T00:00:00Z",
            label="v1.0",
            fingerprint="abc123",
            file_hashes={"SKILL.md": "def456"},
            metadata={"skill_path": "/tmp/test"},
        )
        d = entry.to_dict()
        assert d["label"] == "v1.0"
        assert d["fingerprint"] == "abc123"
        assert d["file_hashes"]["SKILL.md"] == "def456"

    def test_from_dict(self):
        data = {
            "timestamp": "2025-01-01T00:00:00Z",
            "label": "v1.0",
            "fingerprint": "abc123",
            "file_hashes": {"SKILL.md": "def456"},
            "metadata": {},
        }
        entry = VersionEntry.from_dict(data)
        assert entry.label == "v1.0"
        assert entry.fingerprint == "abc123"

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "timestamp": "2025-01-01T00:00:00Z",
            "label": "v1.0",
            "fingerprint": "abc123",
            "unknown_field": "should be ignored",
        }
        entry = VersionEntry.from_dict(data)
        assert entry.label == "v1.0"
        assert not hasattr(entry, "unknown_field")

    def test_roundtrip(self):
        original = VersionEntry(
            timestamp="2025-01-01T00:00:00Z",
            label="v1.0",
            fingerprint="abc123",
            file_hashes={"SKILL.md": "def456"},
            metadata={"key": "value"},
        )
        restored = VersionEntry.from_dict(original.to_dict())
        assert restored.label == original.label
        assert restored.fingerprint == original.fingerprint
        assert restored.file_hashes == original.file_hashes


class TestLifecycleCLI:
    """Test CLI integration for lifecycle command."""

    def test_lifecycle_cli_check(self, minimal_skill, capsys):
        """CLI check command works on first run."""
        ret = main(["lifecycle", str(minimal_skill)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "Initial version recorded" in captured.out

    def test_lifecycle_cli_save(self, minimal_skill, capsys):
        """CLI save command stores version."""
        ret = main(["lifecycle", str(minimal_skill), "--save", "--label", "v1.0"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "v1.0" in captured.out

        hp = _get_history_path(minimal_skill.resolve())
        history = _load_history(hp)
        assert len(history["versions"]) == 1

    def test_lifecycle_cli_history(self, minimal_skill, capsys):
        """CLI history command lists versions."""
        # Save a version first
        main(["lifecycle", str(minimal_skill), "--save", "--label", "v1.0"])
        capsys.readouterr()  # clear

        ret = main(["lifecycle", str(minimal_skill), "--history"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "v1.0" in captured.out

    def test_lifecycle_cli_check_detects_changes(self, minimal_skill, capsys):
        """CLI check returns 1 when changes are detected."""
        # Record initial version
        main(["lifecycle", str(minimal_skill)])
        capsys.readouterr()

        # Modify skill
        (minimal_skill / "SKILL.md").write_text(
            "---\n"
            "name: minimal-skill\n"
            "description: CLI test changed description for lifecycle. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Minimal Skill\n\nCLI changed.\n"
        )

        ret = main(["lifecycle", str(minimal_skill)])
        assert ret == 1
        captured = capsys.readouterr()
        assert "Changes detected" in captured.out

    def test_lifecycle_cli_json_format(self, minimal_skill, capsys):
        """CLI --format json produces valid JSON."""
        ret = main(["lifecycle", str(minimal_skill), "--format", "json"])
        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "initial"
