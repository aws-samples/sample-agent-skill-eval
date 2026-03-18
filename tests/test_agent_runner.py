"""Tests for skill_eval.agent_runner — AgentRunner abstraction and ClaudeRunner."""

import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from skill_eval.agent_runner import (
    AgentRunner,
    AgentNotAvailableError,
    ClaudeRunner,
    register_runner,
    get_runner,
    _RUNNER_REGISTRY,
)


class TestAgentRunnerAbstract:
    """Test that AgentRunner cannot be instantiated directly."""

    def test_cannot_instantiate(self):
        """AgentRunner is abstract and should raise TypeError on direct instantiation."""
        with pytest.raises(TypeError):
            AgentRunner()

    def test_has_abstract_methods(self):
        """AgentRunner defines the expected abstract methods."""
        abstracts = AgentRunner.__abstractmethods__
        assert "check_available" in abstracts
        assert "run_prompt" in abstracts
        assert "parse_output" in abstracts


class TestClaudeRunnerCheckAvailable:
    """Test ClaudeRunner.check_available() success and failure paths."""

    def test_check_available_success(self):
        """When claude is on PATH, check_available should not raise."""
        runner = ClaudeRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            runner.check_available()  # Should not raise

    def test_check_available_failure(self):
        """When claude is not on PATH, check_available should raise AgentNotAvailableError."""
        runner = ClaudeRunner()
        with patch("shutil.which", return_value=None):
            with pytest.raises(AgentNotAvailableError) as exc_info:
                runner.check_available()
            assert "claude" in str(exc_info.value).lower()
            assert exc_info.value.agent_name == "claude"


class TestClaudeRunnerRunPrompt:
    """Test ClaudeRunner.run_prompt() with mocked subprocess."""

    def test_run_prompt_success(self):
        """Successful subprocess call returns stdout, stderr, rc, elapsed."""
        runner = ClaudeRunner()
        mock_result = MagicMock()
        mock_result.stdout = "Hello from claude"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            stdout, stderr, rc, elapsed = runner.run_prompt("test prompt", timeout=30)

        assert stdout == "Hello from claude"
        assert stderr == ""
        assert rc == 0
        assert elapsed >= 0
        mock_run.assert_called_once()

    def test_run_prompt_with_skill(self, tmp_path):
        """When skill_path is given, --append-system-prompt is used."""
        runner = ClaudeRunner()
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill\nDo things.")

        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            runner.run_prompt("prompt", skill_path=str(skill_dir), timeout=30)

        cmd = mock_run.call_args[0][0]
        assert "--append-system-prompt" in cmd

    def test_run_prompt_timeout(self):
        """TimeoutExpired should be caught and return rc=-1."""
        runner = ClaudeRunner()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 10)):
            stdout, stderr, rc, elapsed = runner.run_prompt("test", timeout=10)

        assert rc == -1
        assert "Timed out" in stderr

    def test_run_prompt_file_not_found(self):
        """FileNotFoundError should be caught and return rc=-1."""
        runner = ClaudeRunner()
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            stdout, stderr, rc, elapsed = runner.run_prompt("test", timeout=10)

        assert rc == -1
        assert "not found" in stderr.lower()

    def test_run_prompt_stream_json_format(self):
        """output_format='stream-json' should add --output-format flag."""
        runner = ClaudeRunner()
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            runner.run_prompt("test", output_format="stream-json", timeout=30)

        cmd = mock_run.call_args[0][0]
        assert "--output-format" in cmd
        assert "stream-json" in cmd


class TestClaudeRunnerParseOutput:
    """Test ClaudeRunner.parse_output() with sample stream-json."""

    def test_parse_text_delta(self):
        """Parse text content from content_block_delta events."""
        runner = ClaudeRunner()
        raw = "\n".join([
            json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello "}}),
            json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "World"}}),
        ])
        result = runner.parse_output(raw)
        assert result["text"] == "Hello World"

    def test_parse_tool_calls(self):
        """Parse tool_use events from content_block_start."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "name": "Read",
                "input": {"file": "test.py"},
                "id": "tool-123",
            },
        })
        result = runner.parse_output(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "Read"
        assert result["tool_calls"][0]["input"] == {"file": "test.py"}

    def test_parse_token_counts_message_start(self):
        """Parse token usage from message_start events."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "message_start",
            "message": {"usage": {"input_tokens": 100, "output_tokens": 50}},
        })
        result = runner.parse_output(raw)
        assert result["token_counts"]["input_tokens"] == 100
        assert result["token_counts"]["output_tokens"] == 50

    def test_parse_token_counts_result_event(self):
        """Parse token usage from result events."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "result",
            "usage": {"input_tokens": 200, "output_tokens": 100},
            "result": "final text",
        })
        result = runner.parse_output(raw)
        assert result["token_counts"]["input_tokens"] == 200
        assert result["token_counts"]["output_tokens"] == 100
        assert result["text"] == "final text"

    def test_parse_empty_input(self):
        """Empty input should return empty results."""
        runner = ClaudeRunner()
        result = runner.parse_output("")
        assert result["events"] == []
        assert result["tool_calls"] == []
        assert result["text"] == ""
        assert result["token_counts"]["input_tokens"] == 0
        assert result["token_counts"]["output_tokens"] == 0

    def test_parse_invalid_json_lines_skipped(self):
        """Non-JSON lines should be silently skipped."""
        runner = ClaudeRunner()
        raw = "not json\n" + json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}})
        result = runner.parse_output(raw)
        assert result["text"] == "ok"
        assert len(result["events"]) == 1

    def test_parse_cache_tokens(self):
        """Cache token fields should be extracted."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "message_start",
            "message": {"usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 10,
            }},
        })
        result = runner.parse_output(raw)
        assert result["token_counts"]["cache_read_input_tokens"] == 30
        assert result["token_counts"]["cache_creation_input_tokens"] == 10


class TestParseClaudeCLIFormat:
    """Test parsing Claude CLI stream-json format (type: assistant/user)."""

    def test_parse_cli_tool_use(self):
        """Parse tool_use from Claude CLI assistant message."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ls -la", "description": "List files"},
                        "id": "toolu_123",
                    }
                ],
            },
        })
        result = runner.parse_output(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "Bash"
        assert result["tool_calls"][0]["input"]["command"] == "ls -la"

    def test_parse_cli_text_content(self):
        """Parse text from Claude CLI assistant message content blocks."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Here are the results:"},
                ],
            },
        })
        result = runner.parse_output(raw)
        assert "Here are the results:" in result["text"]

    def test_parse_cli_mixed_content(self):
        """Parse both tool_use and text from a single assistant message."""
        runner = ClaudeRunner()
        raw = "\n".join([
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me check: "},
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "SKILL.md"},
                            "id": "toolu_456",
                        },
                    ],
                },
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "The file contains..."},
                    ],
                },
            }),
        ])
        result = runner.parse_output(raw)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "Read"
        assert "Let me check:" in result["text"] or "The file contains" in result["text"]

    def test_parse_cli_multiple_tool_calls(self):
        """Parse multiple tool calls across assistant messages."""
        runner = ClaudeRunner()
        raw = "\n".join([
            json.dumps({
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "SKILL.md"}, "id": "t1"},
                ]},
            }),
            json.dumps({
                "type": "user",
                "message": {"content": [
                    {"type": "tool_result", "content": "skill content", "tool_use_id": "t1"},
                ]},
            }),
            json.dumps({
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "skill-eval audit ."}, "id": "t2"},
                ]},
            }),
        ])
        result = runner.parse_output(raw)
        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["name"] == "Read"
        assert result["tool_calls"][1]["name"] == "Bash"

    def test_parse_cli_result_with_tokens(self):
        """Parse result event with token counts from Claude CLI."""
        runner = ClaudeRunner()
        raw = json.dumps({
            "type": "result",
            "result": "Here is the output",
            "usage": {
                "input_tokens": 50000,
                "output_tokens": 500,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        })
        result = runner.parse_output(raw)
        assert result["token_counts"]["input_tokens"] == 50000
        assert result["token_counts"]["output_tokens"] == 500
        assert "Here is the output" in result["text"]

    def test_parse_both_formats_combined(self):
        """Parser handles both API streaming and CLI format in same input."""
        runner = ClaudeRunner()
        raw = "\n".join([
            # API streaming format
            json.dumps({"type": "content_block_start", "content_block": {
                "type": "tool_use", "name": "Read", "input": {}, "id": "api1",
            }}),
            # CLI format
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "echo hi"}, "id": "cli1"},
            ]}}),
        ])
        result = runner.parse_output(raw)
        assert len(result["tool_calls"]) == 2


class TestClaudeRunnerReadSkillContent:
    """Test ClaudeRunner._read_skill_content()."""

    def test_reads_skill_md(self, tmp_path):
        """Should read SKILL.md content from the given directory."""
        runner = ClaudeRunner()
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill\nContent here.")

        content = runner._read_skill_content(str(skill_dir))
        assert content == "# My Skill\nContent here."

    def test_returns_empty_when_missing(self, tmp_path):
        """Should return empty string when SKILL.md doesn't exist."""
        runner = ClaudeRunner()
        content = runner._read_skill_content(str(tmp_path))
        assert content == ""


class TestClaudeRunnerBuildCmd:
    """Test command building methods."""

    def test_build_cmd_with_skill_uses_append_system_prompt(self, tmp_path):
        """_build_cmd_with_skill should use --append-system-prompt, NOT --plugin-dir."""
        runner = ClaudeRunner()
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("skill content")

        cmd = runner._build_cmd_with_skill("test prompt", str(skill_dir))
        assert "--append-system-prompt" in cmd
        assert "--plugin-dir" not in cmd
        # The injected content should include a workspace hint
        idx = cmd.index("--append-system-prompt")
        injected = cmd[idx + 1]
        assert "skill content" in injected
        assert "scripts/" in injected
        assert "claude" == cmd[0]
        assert "-p" in cmd
        assert "test prompt" in cmd

    def test_build_cmd_with_skill_no_skill_tool(self, tmp_path):
        """With-skill command should NOT include the Skill tool (system prompt injection)."""
        runner = ClaudeRunner()
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        cmd = runner._build_cmd_with_skill("prompt", str(skill_dir))
        assert "Skill" not in cmd

    def test_build_cmd_without_skill(self):
        """_build_cmd_without_skill should not include --append-system-prompt or Skill."""
        runner = ClaudeRunner()
        cmd = runner._build_cmd_without_skill("test prompt")
        assert "--append-system-prompt" not in cmd
        assert "Skill" not in cmd
        assert "claude" == cmd[0]
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--allowedTools" in cmd

    def test_build_cmd_with_skill_no_skill_md(self, tmp_path):
        """When SKILL.md is missing, --append-system-prompt should not be added."""
        runner = ClaudeRunner()
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        cmd = runner._build_cmd_with_skill("prompt", str(skill_dir))
        assert "--append-system-prompt" not in cmd


class TestRegistryFactory:
    """Test register_runner() and get_runner() factory."""

    def test_get_runner_claude(self):
        """get_runner('claude') should return a ClaudeRunner instance."""
        runner = get_runner("claude")
        assert isinstance(runner, ClaudeRunner)

    def test_get_runner_default(self):
        """get_runner() without args should default to 'claude'."""
        runner = get_runner()
        assert isinstance(runner, ClaudeRunner)

    def test_get_runner_unknown_raises_key_error(self):
        """get_runner() with unknown name should raise KeyError."""
        with pytest.raises(KeyError, match="no-such-runner"):
            get_runner("no-such-runner")

    def test_register_runner_custom(self):
        """register_runner() should allow registering a custom runner."""
        class DummyRunner(AgentRunner):
            def check_available(self): pass
            def run_prompt(self, prompt, **kw): return ("", "", 0, 0.0)
            def parse_output(self, raw): return {"events": [], "tool_calls": [], "text": "", "token_counts": {}}

        register_runner("dummy-test", DummyRunner)
        try:
            runner = get_runner("dummy-test")
            assert isinstance(runner, DummyRunner)
        finally:
            _RUNNER_REGISTRY.pop("dummy-test", None)

    def test_register_runner_non_agentrunner_raises_type_error(self):
        """register_runner() with a non-AgentRunner class should raise TypeError."""
        with pytest.raises(TypeError):
            register_runner("bad", str)  # type: ignore

    def test_register_runner_with_non_class_raises_type_error(self):
        """register_runner() with a non-class object should raise TypeError."""
        with pytest.raises(TypeError):
            register_runner("bad", "not a class")  # type: ignore


class TestTotalTokens:
    """Test the total_tokens() method."""

    def test_total_tokens_sum(self):
        """total_tokens should sum input_tokens and output_tokens."""
        runner = ClaudeRunner()
        counts = {"input_tokens": 150, "output_tokens": 75}
        assert runner.total_tokens(counts) == 225

    def test_total_tokens_excludes_cache(self):
        """total_tokens should not include cache tokens."""
        runner = ClaudeRunner()
        counts = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 10,
        }
        assert runner.total_tokens(counts) == 150

    def test_total_tokens_empty_dict(self):
        """total_tokens with empty dict should return 0."""
        runner = ClaudeRunner()
        assert runner.total_tokens({}) == 0

    def test_total_tokens_missing_keys(self):
        """total_tokens with missing keys should default to 0."""
        runner = ClaudeRunner()
        assert runner.total_tokens({"input_tokens": 100}) == 100
