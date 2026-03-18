"""Tests for trigger evaluation module."""

import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from skill_eval.trigger import (
    run_trigger_eval,
    _load_queries,
    _read_skill_name,
    _detect_skill_trigger,
    _detect_skill_trigger_from_parsed,
    _run_trigger_query,
    _build_trigger_report,
    _print_trigger_report,
)
from skill_eval.eval_schemas import TriggerQuery, TriggerQueryResult, TriggerReport
from skill_eval.agent_runner import AgentNotAvailableError, ClaudeRunner


FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadQueries:
    """Test eval_queries.json loading and validation."""

    def test_load_valid_queries(self):
        queries_file = FIXTURES / "eval-skill" / "evals" / "eval_queries.json"
        queries = _load_queries(queries_file)
        assert len(queries) == 4

    def test_load_queries_types(self):
        queries_file = FIXTURES / "eval-skill" / "evals" / "eval_queries.json"
        queries = _load_queries(queries_file)
        should_trigger = [q for q in queries if q.should_trigger]
        should_not = [q for q in queries if not q.should_trigger]
        assert len(should_trigger) == 2
        assert len(should_not) == 2

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            _load_queries(Path("/nonexistent/eval_queries.json"))

    def test_load_invalid_json(self, tmp_path):
        bad_file = tmp_path / "eval_queries.json"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            _load_queries(bad_file)

    def test_load_not_array(self, tmp_path):
        bad_file = tmp_path / "eval_queries.json"
        bad_file.write_text('{"not": "array"}')
        with pytest.raises(ValueError, match="must be a JSON array"):
            _load_queries(bad_file)

    def test_load_missing_required_fields(self, tmp_path):
        bad_file = tmp_path / "eval_queries.json"
        bad_file.write_text('[{"query": "test"}]')
        with pytest.raises(ValueError, match="missing required field"):
            _load_queries(bad_file)

    def test_load_non_object_item(self, tmp_path):
        bad_file = tmp_path / "eval_queries.json"
        bad_file.write_text('["not an object"]')
        with pytest.raises(ValueError, match="must be an object"):
            _load_queries(bad_file)


class TestDetectSkillTrigger:
    """Test skill trigger detection from stream-json output."""

    def test_detect_skill_tool_use(self):
        """Should detect Skill tool invocation."""
        stream = json.dumps({
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "name": "Skill", "input": {}, "id": "1"},
        })
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is True

    def test_detect_read_skill_md(self):
        """Should detect Read of SKILL.md."""
        stream = json.dumps({
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/tmp/eval-skill/SKILL.md"},
                "id": "1",
            },
        })
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is True

    def test_detect_skill_name_in_tool_input(self):
        """Should detect skill name used as a CLI command in Bash."""
        stream = json.dumps({
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "eval-skill --audit ."},
                "id": "1",
            },
        })
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is True

    def test_no_trigger_detected(self):
        """Should return False when skill is not activated."""
        stream = json.dumps({
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "echo hello"},
                "id": "1",
            },
        })
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is False

    def test_detect_in_text_output(self):
        """Should detect skill activation markers in text."""
        stream = json.dumps({
            "type": "result",
            "result": "Using eval-skill to process the data",
        })
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is True

    def test_empty_stream(self):
        """Should handle empty stream gracefully."""
        result = _detect_skill_trigger("", Path("/tmp/eval-skill"))
        assert result is False

    def test_multiline_stream(self):
        """Should handle multiple stream events."""
        lines = [
            json.dumps({"type": "content_block_start", "content_block": {"type": "text"}}),
            json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hello"}}),
            json.dumps({
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "name": "Skill", "input": {}, "id": "2"},
            }),
        ]
        stream = "\n".join(lines)
        result = _detect_skill_trigger(stream, Path("/tmp/eval-skill"))
        assert result is True


class TestBuildTriggerReport:
    """Test trigger report building."""

    def test_all_passed(self):
        results = [
            TriggerQueryResult(query="q1", should_trigger=True, trigger_count=2, run_count=3, trigger_rate=0.67, passed=True),
            TriggerQueryResult(query="q2", should_trigger=False, trigger_count=0, run_count=3, trigger_rate=0.0, passed=True),
        ]
        report = _build_trigger_report("test", "/tmp", results)
        assert report.passed is True
        assert report.summary["passed"] == 2
        assert report.summary["failed"] == 0

    def test_some_failed(self):
        results = [
            TriggerQueryResult(query="q1", should_trigger=True, trigger_count=0, run_count=3, trigger_rate=0.0, passed=False),
            TriggerQueryResult(query="q2", should_trigger=False, trigger_count=0, run_count=3, trigger_rate=0.0, passed=True),
        ]
        report = _build_trigger_report("test", "/tmp", results)
        assert report.passed is False
        assert report.summary["passed"] == 1
        assert report.summary["failed"] == 1

    def test_precision_calculation(self):
        results = [
            TriggerQueryResult(query="q1", should_trigger=True, trigger_count=3, run_count=3, trigger_rate=1.0, passed=True),
            TriggerQueryResult(query="q2", should_trigger=True, trigger_count=1, run_count=3, trigger_rate=0.33, passed=False),
            TriggerQueryResult(query="q3", should_trigger=False, trigger_count=0, run_count=3, trigger_rate=0.0, passed=True),
        ]
        report = _build_trigger_report("test", "/tmp", results)
        assert report.summary["trigger_precision"] == 0.5  # 1 of 2 should-trigger passed
        assert report.summary["no_trigger_precision"] == 1.0


class TestDryRun:
    """Test dry-run mode for trigger eval."""

    def test_dry_run_loads_queries(self, capsys):
        ret = run_trigger_eval(
            str(FIXTURES / "eval-skill"),
            dry_run=True,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "should trigger" in captured.out
        assert "should NOT trigger" in captured.out

    def test_dry_run_missing_queries(self):
        ret = run_trigger_eval(
            str(FIXTURES / "bad-skill"),  # No evals dir
            dry_run=True,
        )
        assert ret == 2


class TestRunTriggerEvalErrorCases:
    """Test error handling in run_trigger_eval."""

    def test_missing_queries_file(self):
        ret = run_trigger_eval("/nonexistent/path")
        assert ret == 2

    def test_invalid_queries_path(self, tmp_path):
        bad_queries = tmp_path / "eval_queries.json"
        bad_queries.write_text("not json")
        ret = run_trigger_eval(str(tmp_path), queries_path=str(bad_queries))
        assert ret == 2

    def test_no_claude_available(self):
        with patch.object(ClaudeRunner, "check_available",
                          side_effect=AgentNotAvailableError("claude")):
            ret = run_trigger_eval(str(FIXTURES / "eval-skill"))
            assert ret == 2


class TestPrintTriggerReport:
    """Test report printing."""

    def test_print_passing_report(self, capsys):
        report = TriggerReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            query_results=[
                {"query": "analyze CSV", "should_trigger": True, "trigger_rate": 0.67, "passed": True},
                {"query": "write a poem", "should_trigger": False, "trigger_rate": 0.0, "passed": True},
            ],
            summary={"total_queries": 2, "passed": 2, "failed": 0,
                      "trigger_precision": 1.0, "no_trigger_precision": 1.0},
            passed=True,
        )
        _print_trigger_report(report)
        captured = capsys.readouterr()
        assert "test-skill" in captured.out
        assert "PASSED" in captured.out
        assert "PASS" in captured.out

    def test_print_failing_report(self, capsys):
        report = TriggerReport(
            skill_name="bad-skill",
            skill_path="/tmp/bad",
            query_results=[
                {"query": "analyze CSV", "should_trigger": True, "trigger_rate": 0.0, "passed": False},
            ],
            summary={"total_queries": 1, "passed": 0, "failed": 1,
                      "trigger_precision": 0.0, "no_trigger_precision": 1.0},
            passed=False,
        )
        _print_trigger_report(report)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out


class TestReadSkillName:
    """Test _read_skill_name helper."""

    def test_read_existing(self):
        name = _read_skill_name(FIXTURES / "eval-skill")
        assert name == "eval-skill"

    def test_read_missing(self, tmp_path):
        name = _read_skill_name(tmp_path)
        assert name is None


class TestDetectSkillTriggerFromParsed:
    """Test _detect_skill_trigger_from_parsed with pre-parsed data."""

    def test_detect_skill_tool(self):
        parsed = {
            "tool_calls": [{"name": "Skill", "input": {}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is True

    def test_detect_read_skill_md(self):
        parsed = {
            "tool_calls": [{"name": "Read", "input": {"file_path": "/tmp/eval-skill/SKILL.md"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is True

    def test_no_trigger(self):
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "echo hello"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is False

    def test_empty_parsed(self):
        parsed = {"tool_calls": [], "text": ""}
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is False

    def test_text_marker(self):
        parsed = {
            "tool_calls": [],
            "text": "Using eval-skill to process the data",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is True


class TestBashTriggerDetection:
    """Test Bash/CLI command trigger detection."""

    def test_bash_with_skill_name_in_command(self):
        """Bash command containing skill name should trigger."""
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "skill-eval audit /path/to/skill"}}],
            "text": "",
        }
        # skill name is "skill-eval" which matches the Bash command
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/skill-eval")) is True

    def test_bash_with_script_name(self, tmp_path):
        """Bash command running a skill's script should trigger."""
        skill_dir = tmp_path / "weather-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "weather.py").write_text("# weather script")

        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "python3 scripts/weather.py --city NYC"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True

    def test_bash_with_script_stem(self, tmp_path):
        """Bash command referencing script name without extension should trigger."""
        skill_dir = tmp_path / "data-analysis"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "analyze_csv.py").write_text("# analysis script")

        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "python3 analyze_csv.py sales.csv"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True

    def test_bash_scripts_path_reference(self, tmp_path):
        """Bash command executing a script via scripts/ path should trigger."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "process.py").write_text("# process script")

        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "python3 scripts/process.py input.txt"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True

    def test_bash_unrelated_command_no_trigger(self):
        """Bash command not related to skill should not trigger."""
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "echo hello world"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is False

    def test_bash_skill_name_in_path_no_trigger(self):
        """Bash command with skill name only in a path (not as CLI command) should NOT trigger."""
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "ls examples/data-analysis/"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/data-analysis")) is False

    def test_bash_cat_skill_dir_no_trigger(self):
        """cat/ls of skill directory should NOT trigger (not execution)."""
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "cat eval-skill/data.csv"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/eval-skill")) is False

    def test_bash_with_skill_path_in_command(self, tmp_path):
        """Bash command referencing skill's full path should trigger."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": f"cat {skill_dir}/SKILL.md"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True

    def test_bash_with_hyphenated_skill_name(self):
        """Bash command with underscore variant of hyphenated skill name should trigger."""
        parsed = {
            "tool_calls": [{"name": "Bash", "input": {"command": "python3 -m data_analysis --file test.csv"}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/data-analysis")) is True

    def test_shell_tool_name(self):
        """'Shell' tool name should also be checked."""
        parsed = {
            "tool_calls": [{"name": "Shell", "input": {"command": "skill-eval audit ."}}],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, Path("/tmp/skill-eval")) is True

    def test_multiple_tool_calls_one_triggers(self, tmp_path):
        """If any tool call triggers, result should be True."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.py").write_text("# run")

        parsed = {
            "tool_calls": [
                {"name": "Bash", "input": {"command": "echo hello"}},
                {"name": "Bash", "input": {"command": "python3 scripts/run.py input.txt"}},
            ],
            "text": "",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True


class TestTextTriggerDetection:
    """Test skill name and script reference detection in text output."""

    def test_detect_skill_name_in_text(self):
        """Should detect skill name as a standalone word in text output."""
        parsed = {
            "tool_calls": [],
            "text": "I'll use the acme-compliance checker to validate this document.",
        }
        assert _detect_skill_trigger_from_parsed(
            parsed, Path("/tmp/acme-compliance")
        ) is True

    def test_detect_skill_name_word_boundary(self):
        """Should not match partial words containing the skill name."""
        parsed = {
            "tool_calls": [],
            "text": "This is about non-acme-compliance-related matters.",
        }
        # "acme-compliance" still appears as a word here, so it matches
        assert _detect_skill_trigger_from_parsed(
            parsed, Path("/tmp/acme-compliance")
        ) is True

    def test_no_partial_match(self):
        """Should not match when skill name is only a substring."""
        parsed = {
            "tool_calls": [],
            "text": "The weather is nice today.",
        }
        assert _detect_skill_trigger_from_parsed(
            parsed, Path("/tmp/weather-forecast")
        ) is False

    def test_detect_script_file_in_text(self, tmp_path):
        """Should detect references to skill scripts using path-level matching."""
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "check.py").write_text("#!/usr/bin/env python3\npass")

        parsed = {
            "tool_calls": [],
            "text": "You should run scripts/check.py to validate the document.",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is True

    def test_no_detect_bare_script_name(self, tmp_path):
        """Should NOT trigger on bare script name without scripts/ prefix."""
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "check.py").write_text("pass")

        parsed = {
            "tool_calls": [],
            "text": "Run check.py to validate the document.",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is False

    def test_no_detect_unrelated_text(self, tmp_path):
        """Should not trigger on unrelated text."""
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "check.py").write_text("pass")

        parsed = {
            "tool_calls": [],
            "text": "Here is a summary of the document.",
        }
        assert _detect_skill_trigger_from_parsed(parsed, skill_dir) is False


class TestTriggerQueryResultTokenFields:
    """Test TriggerQueryResult token fields."""

    def test_token_defaults(self):
        tqr = TriggerQueryResult(query="q", should_trigger=True)
        assert tqr.mean_input_tokens == 0.0
        assert tqr.mean_output_tokens == 0.0
        assert tqr.mean_total_tokens == 0.0

    def test_token_fields_in_dict(self):
        tqr = TriggerQueryResult(
            query="q", should_trigger=True,
            mean_input_tokens=500.0, mean_output_tokens=200.0, mean_total_tokens=700.0,
        )
        d = tqr.to_dict()
        assert d["mean_input_tokens"] == 500.0
        assert d["mean_output_tokens"] == 200.0
        assert d["mean_total_tokens"] == 700.0


class TestBuildTriggerReportTokens:
    """Test token data in trigger report."""

    def test_mean_total_tokens_in_summary(self):
        results = [
            TriggerQueryResult(
                query="q1", should_trigger=True, trigger_count=2, run_count=3,
                trigger_rate=0.67, passed=True,
                mean_input_tokens=500.0, mean_output_tokens=200.0, mean_total_tokens=700.0,
            ),
            TriggerQueryResult(
                query="q2", should_trigger=False, trigger_count=0, run_count=3,
                trigger_rate=0.0, passed=True,
                mean_input_tokens=400.0, mean_output_tokens=100.0, mean_total_tokens=500.0,
            ),
        ]
        report = _build_trigger_report("test", "/tmp", results)
        assert report.summary["mean_total_tokens_per_run"] == 600.0  # (700 + 500) / 2

    def test_zero_tokens_in_summary(self):
        results = [
            TriggerQueryResult(query="q1", should_trigger=True, trigger_count=1, run_count=1,
                               trigger_rate=1.0, passed=True),
        ]
        report = _build_trigger_report("test", "/tmp", results)
        assert report.summary["mean_total_tokens_per_run"] == 0.0


class TestPrintTriggerReportTokens:
    """Test token display in trigger report."""

    def test_tokens_shown_in_query_line(self, capsys):
        report = TriggerReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            query_results=[
                {"query": "analyze CSV", "should_trigger": True, "trigger_rate": 0.67,
                 "passed": True, "mean_total_tokens": 700},
            ],
            summary={"total_queries": 1, "passed": 1, "failed": 0,
                      "trigger_precision": 1.0, "no_trigger_precision": 1.0,
                      "mean_total_tokens_per_run": 700},
            passed=True,
        )
        _print_trigger_report(report)
        captured = capsys.readouterr()
        assert "mean=700 tok" in captured.out
        assert "Mean tokens per run: 700" in captured.out

    def test_tokens_hidden_when_zero(self, capsys):
        report = TriggerReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            query_results=[
                {"query": "analyze CSV", "should_trigger": True, "trigger_rate": 0.67,
                 "passed": True, "mean_total_tokens": 0},
            ],
            summary={"total_queries": 1, "passed": 1, "failed": 0,
                      "trigger_precision": 1.0, "no_trigger_precision": 1.0,
                      "mean_total_tokens_per_run": 0},
            passed=True,
        )
        _print_trigger_report(report)
        captured = capsys.readouterr()
        assert "Mean tokens per run" not in captured.out


def _make_trigger_stream(tool_name="Skill", text="", input_tokens=100, output_tokens=50):
    """Build a stream-json string with a tool_use event for trigger detection."""
    import json as _json
    lines = []
    if tool_name:
        lines.append(_json.dumps({
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "name": tool_name, "input": {}, "id": "t1"},
        }))
    lines.append(_json.dumps({
        "type": "result",
        "result": text or "done",
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }))
    return "\n".join(lines)


class TestRunTriggerQuery:
    """Integration tests for _run_trigger_query with mocked Claude."""

    def _make_mock_runner(self):
        runner = MagicMock(spec=ClaudeRunner)
        runner.parse_output.side_effect = ClaudeRunner().parse_output
        return runner

    def test_run_trigger_query_detects_trigger(self):
        """Skill tool_use → trigger_count=1, passed=True."""
        stream = _make_trigger_stream(tool_name="Skill")
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = (stream, "", 0, 1.0)

        query = TriggerQuery(query="Analyze the CSV", should_trigger=True)
        result = _run_trigger_query(query, Path("/tmp/eval-skill"), runs=1, timeout=30, runner=runner)
        assert result.trigger_count == 1
        assert result.passed is True
        assert result.trigger_rate == 1.0

    def test_run_trigger_query_no_trigger_passes_when_expected(self):
        """should_trigger=False, no trigger → passed=True."""
        stream = _make_trigger_stream(tool_name="Bash", text="hello")
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = (stream, "", 0, 1.0)

        query = TriggerQuery(query="Write a haiku", should_trigger=False)
        result = _run_trigger_query(query, Path("/tmp/other-skill"), runs=1, timeout=30, runner=runner)
        assert result.trigger_count == 0
        assert result.passed is True

    def test_run_trigger_query_tracks_tokens(self):
        """Token means populated from stream-json."""
        stream = _make_trigger_stream(tool_name="Skill", input_tokens=500, output_tokens=200)
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = (stream, "", 0, 1.0)

        query = TriggerQuery(query="Process CSV", should_trigger=True)
        result = _run_trigger_query(query, Path("/tmp/eval-skill"), runs=1, timeout=30, runner=runner)
        assert result.mean_input_tokens == 500.0
        assert result.mean_output_tokens == 200.0
        assert result.mean_total_tokens == 700.0

    def test_run_trigger_query_multi_run_averaging(self):
        """3 runs, 2 trigger → rate=0.6667."""
        trigger_stream = _make_trigger_stream(tool_name="Skill")
        no_trigger_stream = _make_trigger_stream(tool_name="Bash", text="no skill")
        runner = self._make_mock_runner()
        runner.run_prompt.side_effect = [
            (trigger_stream, "", 0, 1.0),
            (trigger_stream, "", 0, 1.0),
            (no_trigger_stream, "", 0, 1.0),
        ]

        query = TriggerQuery(query="Analyze CSV", should_trigger=True)
        result = _run_trigger_query(query, Path("/tmp/eval-skill"), runs=3, timeout=30, runner=runner)
        assert result.trigger_count == 2
        assert result.run_count == 3
        assert abs(result.trigger_rate - 0.6667) < 0.01
        assert result.passed is True  # 0.667 >= 0.5

    def test_run_trigger_query_failed_run_skipped(self):
        """rc != 0 → run ignored, trigger stays 0."""
        runner = self._make_mock_runner()
        runner.run_prompt.return_value = ("", "error", 1, 0.5)

        query = TriggerQuery(query="Analyze CSV", should_trigger=True)
        result = _run_trigger_query(query, Path("/tmp/eval-skill"), runs=1, timeout=30, runner=runner)
        assert result.trigger_count == 0
        assert result.mean_total_tokens == 0.0
        # Failed run means trigger_rate = 0/1 = 0.0, which fails for should_trigger
        assert result.passed is False
