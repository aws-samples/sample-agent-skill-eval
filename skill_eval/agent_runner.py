"""Agent runner abstraction layer.

Defines the AgentRunner interface and a registry/factory for pluggable agent CLIs.
The default implementation (ClaudeRunner) wraps the existing claude CLI logic.

This module enables support for any agent CLI by implementing the AgentRunner
interface and registering it with register_runner().
"""

from __future__ import annotations

import abc
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class AgentRunner(abc.ABC):
    """Abstract base class for agent CLI runners.

    Subclasses must implement:
      - check_available(): verify the CLI is on PATH or otherwise reachable.
      - run_prompt(): execute a prompt and return raw output.
      - parse_output(): parse raw CLI output into structured data.
      - build_skill_injection_args(): return CLI args to inject a skill.
    """

    @abc.abstractmethod
    def check_available(self) -> None:
        """Verify the agent CLI is available.

        Raises:
            AgentNotAvailableError: if the CLI is not found.
        """

    @abc.abstractmethod
    def run_prompt(
        self,
        prompt: str,
        skill_path: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        timeout: int = 120,
        output_format: str = "text",
    ) -> tuple[str, str, int, float]:
        """Execute a prompt via the agent CLI.

        Args:
            prompt: The prompt to send.
            skill_path: If provided, inject the skill into the invocation.
            workspace_dir: Working directory for the subprocess.
            timeout: Timeout in seconds.
            output_format: "text" or "stream-json".

        Returns:
            Tuple of (stdout, stderr, returncode, elapsed_seconds).
        """

    @abc.abstractmethod
    def parse_output(self, raw: str) -> dict:
        """Parse raw CLI output into structured data.

        Returns a dict with keys:
            - events: list of parsed event objects
            - tool_calls: list of tool_use events (name, input)
            - text: concatenated assistant text content
            - token_counts: dict with input_tokens, output_tokens
        """

    def total_tokens(self, token_counts: dict) -> int:
        """Return total token consumption from a token_counts dict.

        Default: input_tokens + output_tokens (cache tokens excluded).
        """
        return token_counts.get("input_tokens", 0) + token_counts.get("output_tokens", 0)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AgentNotAvailableError(RuntimeError):
    """Raised when an agent CLI is not found on PATH."""

    def __init__(self, agent_name: str = "agent", detail: str = "") -> None:
        msg = f"{agent_name} CLI not found on PATH."
        if detail:
            msg += f" {detail}"
        super().__init__(msg)
        self.agent_name = agent_name


# ---------------------------------------------------------------------------
# ClaudeRunner — default implementation
# ---------------------------------------------------------------------------

class ClaudeRunner(AgentRunner):
    """Agent runner for the Claude Code CLI.

    Wraps the claude CLI via subprocess.  Uses --append-system-prompt to
    inject skill content rather than --plugin-dir (which is not a real
    Claude Code flag).  See Feature 2 notes in this module for rationale.
    """

    CLI_NAME = "claude"

    def check_available(self) -> None:
        """Verify that the claude CLI is available on PATH."""
        if shutil.which(self.CLI_NAME) is None:
            raise AgentNotAvailableError(
                self.CLI_NAME,
                "Install from https://docs.anthropic.com/en/docs/claude-code "
                "or add it to your PATH.",
            )

    # -- Skill injection -----------------------------------------------------
    # Claude Code does NOT have a --plugin-dir flag.  The most portable
    # approach is to use --append-system-prompt to inject the contents of
    # SKILL.md so that the agent has the skill context.  This avoids
    # requiring symlinks into ~/.claude/skills/ and works in ephemeral CI
    # environments.  Each AgentRunner subclass defines its own injection
    # mechanism via _build_cmd_with_skill / _build_cmd_without_skill.
    # -----------------------------------------------------------------------

    def _read_skill_content(self, skill_path: str) -> str:
        """Read SKILL.md content for injection via --append-system-prompt."""
        skill_md = Path(skill_path) / "SKILL.md"
        if skill_md.is_file():
            return skill_md.read_text()
        return ""

    def _build_cmd_with_skill(self, prompt: str, skill_path: str) -> list[str]:
        """Build claude CLI argument list for running WITH a skill installed."""
        skill_content = self._read_skill_content(skill_path)
        cmd = [
            self.CLI_NAME, "-p", prompt,
            "--allowedTools", "Read", "Glob", "Grep", "Bash", "Write", "Edit", "Skill",
        ]
        if skill_content:
            cmd.extend(["--append-system-prompt", skill_content])
        return cmd

    def _build_cmd_without_skill(self, prompt: str) -> list[str]:
        """Build claude CLI argument list for running WITHOUT a skill."""
        return [
            self.CLI_NAME, "-p", prompt,
            "--allowedTools", "Read", "Glob", "Grep", "Bash", "Write", "Edit",
        ]

    def run_prompt(
        self,
        prompt: str,
        skill_path: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        timeout: int = 120,
        output_format: str = "text",
    ) -> tuple[str, str, int, float]:
        """Invoke `claude -p` and return (stdout, stderr, returncode, elapsed_seconds)."""
        if skill_path:
            cmd = self._build_cmd_with_skill(prompt, skill_path)
        else:
            cmd = self._build_cmd_without_skill(prompt)

        if output_format == "stream-json":
            cmd.extend(["--output-format", "stream-json", "--verbose"])

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace_dir,
            )
            elapsed = time.monotonic() - start
            return result.stdout, result.stderr, result.returncode, elapsed
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return "", f"Timed out after {timeout}s", -1, elapsed
        except FileNotFoundError:
            elapsed = time.monotonic() - start
            return "", "claude CLI not found", -1, elapsed

    def parse_output(self, raw: str) -> dict:
        """Parse --output-format stream-json output into structured data."""
        events: list[dict] = []
        tool_calls: list[dict] = []
        text_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cache_read_input_tokens = 0
        cache_creation_input_tokens = 0

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            # --- Extract tool_use events ---

            # Format 1: Anthropic raw API streaming
            if event_type == "content_block_start":
                cb = event.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tool_calls.append({
                        "name": cb.get("name", ""),
                        "input": cb.get("input", {}),
                        "id": cb.get("id", ""),
                    })

            # Format 2: Claude CLI stream-json
            # {"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{...}}]}}
            if event_type == "assistant":
                msg = event.get("message", {})
                for content_block in msg.get("content", []):
                    if content_block.get("type") == "tool_use":
                        tool_calls.append({
                            "name": content_block.get("name", ""),
                            "input": content_block.get("input", {}),
                            "id": content_block.get("id", ""),
                        })
                    elif content_block.get("type") == "text":
                        text_parts.append(content_block.get("text", ""))

            # --- Extract text content ---

            # Format 1: Anthropic raw API streaming
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))

            # Extract token usage from message events
            if event_type in ("message_start", "message_delta"):
                usage = event.get("message", {}).get("usage", {})
                if not usage:
                    usage = event.get("usage", {})
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                cache_read_input_tokens += usage.get("cache_read_input_tokens", 0)
                cache_creation_input_tokens += usage.get("cache_creation_input_tokens", 0)

            # Also check top-level result events (claude CLI format)
            if event_type == "result":
                usage = event.get("usage", {})
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
                cache_read_input_tokens += usage.get("cache_read_input_tokens", 0)
                cache_creation_input_tokens += usage.get("cache_creation_input_tokens", 0)
                # Result text
                result_text = event.get("result", "")
                if result_text and not text_parts:
                    text_parts.append(result_text)

        return {
            "events": events,
            "tool_calls": tool_calls,
            "text": "".join(text_parts),
            "token_counts": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
            },
        }


# ---------------------------------------------------------------------------
# Registry / factory
# ---------------------------------------------------------------------------

_RUNNER_REGISTRY: dict[str, type[AgentRunner]] = {}


def register_runner(name: str, runner_class: type[AgentRunner]) -> None:
    """Register an AgentRunner class under a name.

    Args:
        name: Short name (e.g. "claude", "aider").
        runner_class: Subclass of AgentRunner.
    """
    if not (isinstance(runner_class, type) and issubclass(runner_class, AgentRunner)):
        raise TypeError(f"runner_class must be a subclass of AgentRunner, got {runner_class}")
    _RUNNER_REGISTRY[name] = runner_class


def get_runner(name: str = "claude") -> AgentRunner:
    """Instantiate a registered AgentRunner by name.

    Args:
        name: Runner name (default "claude").

    Returns:
        An instance of the registered runner.

    Raises:
        KeyError: If no runner is registered under the given name.
    """
    if name not in _RUNNER_REGISTRY:
        available = ", ".join(sorted(_RUNNER_REGISTRY)) or "(none)"
        raise KeyError(
            f"No agent runner registered as {name!r}. Available: {available}"
        )
    return _RUNNER_REGISTRY[name]()


# Register the built-in ClaudeRunner
register_runner("claude", ClaudeRunner)
