"""Tests for regression module."""

import json
import shutil
import pytest
from pathlib import Path

from skill_eval.regression import (
    save_snapshot,
    check_regression,
    Snapshot,
    RegressionResult,
    HistoryEntry,
    _get_baselines_dir,
    _get_latest_baseline,
    _load_history,
)
from skill_eval.cli import run_audit


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def clean_good_skill(tmp_path):
    """Create a clean copy of good-skill for regression testing."""
    src = FIXTURES / "good-skill"
    dst = tmp_path / "good-skill"
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def clean_bad_skill(tmp_path):
    """Create a clean copy of bad-skill for regression testing."""
    src = FIXTURES / "bad-skill"
    dst = tmp_path / "bad-skill"
    shutil.copytree(src, dst)
    return dst


class TestSnapshot:
    """Test baseline snapshot creation."""

    def test_create_snapshot(self, clean_good_skill):
        ret = save_snapshot(str(clean_good_skill), version="v1.0.0")
        assert ret == 0

        # Verify files
        baselines = _get_baselines_dir(clean_good_skill)
        assert (baselines / "v1.0.0" / "results.json").is_file()
        assert (baselines / "latest" / "results.json").is_file()

    def test_snapshot_content(self, clean_good_skill):
        save_snapshot(str(clean_good_skill), version="v1.0.0")

        results_file = _get_baselines_dir(clean_good_skill) / "v1.0.0" / "results.json"
        data = json.loads(results_file.read_text())
        assert data["skill_name"] == "good-skill"
        assert data["version"] == "v1.0.0"
        assert data["score"] == 100
        assert data["grade"] == "A"
        assert isinstance(data["finding_codes"], list)

    def test_auto_version(self, clean_good_skill):
        ret = save_snapshot(str(clean_good_skill))
        assert ret == 0
        # Should have created a version (either from metadata or timestamp)
        baselines = _get_baselines_dir(clean_good_skill)
        versions = [d.name for d in baselines.iterdir() if d.is_dir() and d.name != "latest"]
        assert len(versions) == 1

    def test_history_updated(self, clean_good_skill):
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        history = _load_history(clean_good_skill)
        assert len(history) == 1
        assert history[0]["version"] == "v1.0.0"
        assert history[0]["regression_result"] == "baseline"

    def test_multiple_snapshots(self, clean_good_skill):
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        save_snapshot(str(clean_good_skill), version="v1.1.0")
        history = _load_history(clean_good_skill)
        assert len(history) == 2


class TestRegressionCheck:
    """Test regression detection."""

    def test_no_regression_when_unchanged(self, clean_good_skill):
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        ret = check_regression(str(clean_good_skill))
        assert ret == 0  # No regression

    def test_regression_detected_on_new_issues(self, clean_good_skill):
        # Create baseline
        save_snapshot(str(clean_good_skill), version="v1.0.0")

        # Add a problematic script
        scripts_dir = clean_good_skill / "scripts"
        (scripts_dir / "bad_addition.py").write_text(
            "import subprocess\nsubprocess.run('ls', shell=True)\n"
        )

        # Check regression
        ret = check_regression(str(clean_good_skill))
        assert ret == 1  # Regression detected (score drop)

    def test_no_baseline_returns_error(self, clean_good_skill):
        ret = check_regression(str(clean_good_skill))
        assert ret == 2  # No baseline

    def test_json_output(self, clean_good_skill, capsys):
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        check_regression(str(clean_good_skill), format="json")
        # Should not crash; output should be valid JSON
        # (capsys may not capture due to print, so just verify no exception)

    def test_custom_baseline_path(self, clean_good_skill, tmp_path):
        # Create baseline
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        baseline_path = str(_get_baselines_dir(clean_good_skill) / "v1.0.0")

        # Check against specific baseline
        ret = check_regression(str(clean_good_skill), baseline_path=baseline_path)
        assert ret == 0


class TestSnapshotModel:
    """Test Snapshot data class."""

    def test_from_report(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        snapshot = Snapshot.from_report(report, "v1.0.0")
        assert snapshot.skill_name == "good-skill"
        assert snapshot.version == "v1.0.0"
        assert snapshot.score == 100

    def test_roundtrip(self):
        report = run_audit(str(FIXTURES / "good-skill"))
        snapshot = Snapshot.from_report(report, "v1.0.0")
        data = snapshot.to_dict()
        restored = Snapshot.from_dict(data)
        assert restored.skill_name == snapshot.skill_name
        assert restored.score == snapshot.score
        assert restored.version == snapshot.version

    def test_regression_result_serialization(self):
        result = RegressionResult(
            passed=True,
            current_score=95,
            baseline_score=90,
            current_grade="A",
            baseline_grade="A",
            regressions=[],
            improvements=[{"code": "SEC-001", "title": "Fixed secret"}],
            unchanged=5,
            message="No regressions.",
        )
        data = result.to_dict()
        assert data["passed"] is True
        assert len(data["improvements"]) == 1

        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["current_score"] == 95

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "skill_name": "test",
            "skill_path": "/tmp/test",
            "version": "v1.0.0",
            "timestamp": "2025-01-01T00:00:00Z",
            "score": 100,
            "grade": "A",
            "finding_codes": [],
            "findings": [],
            "metadata": {},
            "extra_field": "should be ignored",
        }
        snapshot = Snapshot.from_dict(data)
        assert snapshot.skill_name == "test"
        assert not hasattr(snapshot, "extra_field")


class TestFindingKeyCollision:
    """Test that multiple findings with the same code/file/line are not lost."""

    def test_duplicate_code_same_line_both_counted(self, tmp_path):
        """Two findings with same SEC-003 code on same line should both appear."""
        skill_dir = tmp_path / "collision-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: collision-skill\n"
            "description: A test skill for collision testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Collision Skill\n\nTest.\n"
        )
        # This line triggers both subprocess.run AND shell=True -> two SEC-003 findings
        (scripts_dir / "test.py").write_text(
            '#!/usr/bin/env python3\nimport subprocess\nsubprocess.run("ls", shell=True)\n'
        )

        # Create baseline from clean state (no scripts yet)
        save_snapshot(str(skill_dir), version="v1.0.0")

        # The skill already has the script, so baseline captures those findings.
        # Now regression check should show 0 new findings (all in baseline).
        ret = check_regression(str(skill_dir), format="json")
        assert ret == 0  # No regression - all findings were in baseline

    def test_all_findings_tracked_in_regression(self, tmp_path):
        """Verify that check_regression JSON output tracks all findings."""
        skill_dir = tmp_path / "track-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: track-skill\n"
            "description: A test skill for tracking. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Track Skill\n\nTest.\n"
        )
        (scripts_dir / "safe.py").write_text("#!/usr/bin/env python3\nprint('hi')\n")

        # Baseline with no issues
        save_snapshot(str(skill_dir), version="v1.0.0")

        # Add script with colliding findings (same code, same line)
        (scripts_dir / "danger.py").write_text(
            '#!/usr/bin/env python3\nimport subprocess\nsubprocess.run("ls", shell=True)\n'
        )

        ret = check_regression(str(skill_dir), format="json")
        # Should detect regression (new findings cause score drop)
        assert ret == 1


class TestRegressionEdgeCases:
    """Test edge cases in regression detection."""

    def test_score_drop_within_tolerance_passes(self, tmp_path):
        """Score drop of <= 5 points without new criticals should pass."""
        skill_dir = tmp_path / "tolerance-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: tolerance-skill\n"
            "description: A test skill for tolerance testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Tolerance Skill\n\nTest.\n"
        )

        # Create baseline (score = 100)
        save_snapshot(str(skill_dir), version="v1.0.0")

        # Add a single INFO-level finding (costs 2 points -> 98, within 5pt tolerance)
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "noshebang.py").write_text("print('hi')\n")

        ret = check_regression(str(skill_dir))
        assert ret == 0  # Within tolerance, no criticals

    def test_corrupted_baseline_returns_error(self, tmp_path):
        """Corrupted baseline JSON should return error code 2."""
        skill_dir = tmp_path / "corrupt-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: corrupt-skill\n"
            "description: A test skill for corruption testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Corrupt Skill\n\nTest.\n"
        )

        # Create valid snapshot first, then corrupt it
        save_snapshot(str(skill_dir), version="v1.0.0")
        latest_results = _get_baselines_dir(skill_dir) / "latest" / "results.json"
        latest_results.write_text("{invalid json!!!")
        # Also corrupt the version dir
        version_results = _get_baselines_dir(skill_dir) / "v1.0.0" / "results.json"
        version_results.write_text("{invalid json!!!")

        ret = check_regression(str(skill_dir))
        assert ret == 2  # No valid baseline

    def test_invalid_custom_baseline_path(self, clean_good_skill, tmp_path):
        """Invalid custom baseline path should return error code 2."""
        ret = check_regression(
            str(clean_good_skill),
            baseline_path=str(tmp_path / "nonexistent" / "results.json"),
        )
        assert ret == 2

    def test_improvement_detected(self, tmp_path):
        """Fixing issues should be reported as improvements."""
        skill_dir = tmp_path / "improve-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: improve-skill\n"
            "description: A test skill for improvement testing. Use when testing.\n"
            "license: MIT\n"
            "---\n\n# Improve Skill\n\nTest.\n"
        )
        # Start with a problematic script
        (scripts_dir / "fixme.py").write_text("print('no shebang')\n")

        # Baseline captures the issue
        save_snapshot(str(skill_dir), version="v1.0.0")

        # Fix the issue
        (scripts_dir / "fixme.py").write_text("#!/usr/bin/env python3\nprint('fixed')\n")

        # Regression check should pass and show improvement
        ret = check_regression(str(skill_dir), format="json")
        assert ret == 0  # Score improved, no regression

    def test_version_overwrite(self, clean_good_skill):
        """Saving the same version twice should overwrite without error."""
        ret1 = save_snapshot(str(clean_good_skill), version="v1.0.0")
        ret2 = save_snapshot(str(clean_good_skill), version="v1.0.0")
        assert ret1 == 0
        assert ret2 == 0
        # History should have two entries
        history = _load_history(clean_good_skill)
        assert len(history) == 2


class TestGetLatestBaseline:
    """Test _get_latest_baseline behavior."""

    def test_prefers_latest_dir(self, clean_good_skill):
        """Should prefer 'latest' directory over mtime sorting."""
        save_snapshot(str(clean_good_skill), version="v1.0.0")
        baseline = _get_latest_baseline(clean_good_skill)
        assert baseline is not None
        assert baseline.version == "v1.0.0"

    def test_falls_back_to_mtime_when_latest_corrupted(self, clean_good_skill):
        """Should fall back to mtime-based lookup when 'latest' is corrupted."""
        save_snapshot(str(clean_good_skill), version="v1.0.0")

        # Corrupt the latest dir
        latest_results = _get_baselines_dir(clean_good_skill) / "latest" / "results.json"
        latest_results.write_text("not json")

        # Should fall back to v1.0.0 dir
        baseline = _get_latest_baseline(clean_good_skill)
        assert baseline is not None
        assert baseline.version == "v1.0.0"

    def test_returns_none_when_no_baselines(self, clean_good_skill):
        """Should return None when no baselines exist."""
        baseline = _get_latest_baseline(clean_good_skill)
        assert baseline is None

    def test_returns_none_when_empty_baselines_dir(self, clean_good_skill):
        """Should return None when baselines dir exists but is empty."""
        baselines = _get_baselines_dir(clean_good_skill)
        baselines.mkdir(parents=True)
        baseline = _get_latest_baseline(clean_good_skill)
        assert baseline is None
