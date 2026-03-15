"""Shared Claude CLI utilities for functional and trigger evaluation.

Backward-compatibility wrapper — all logic now lives in agent_runner.py.
Existing imports from this module continue to work unchanged.
"""

from __future__ import annotations

from typing import Optional

from skill_eval.agent_runner import (
    AgentNotAvailableError,
    ClaudeRunner,
    get_runner,
)

# Backward-compat alias: callers that import ClaudeNotAvailableError
# still work.
ClaudeNotAvailableError = AgentNotAvailableError

# Singleton runner used by the convenience functions below.
_default_runner = ClaudeRunner()


def check_claude_available() -> None:
    """Verify that the claude CLI is available. Raises AgentNotAvailableError if not."""
    _default_runner.check_available()


def build_cmd_with_skill(prompt: str, skill_path: str) -> list[str]:
    """Build claude CLI argument list for running WITH a skill installed."""
    return _default_runner._build_cmd_with_skill(prompt, skill_path)


def build_cmd_without_skill(prompt: str) -> list[str]:
    """Build claude CLI argument list for running WITHOUT a skill."""
    return _default_runner._build_cmd_without_skill(prompt)


def run_claude_prompt(
    prompt: str,
    skill_path: Optional[str] = None,
    workspace_dir: Optional[str] = None,
    timeout: int = 120,
    output_format: str = "text",
) -> tuple[str, str, int, float]:
    """Invoke `claude -p` and return (stdout, stderr, returncode, elapsed_seconds)."""
    return _default_runner.run_prompt(
        prompt,
        skill_path=skill_path,
        workspace_dir=workspace_dir,
        timeout=timeout,
        output_format=output_format,
    )


def parse_stream_json(raw: str) -> dict:
    """Parse --output-format stream-json output into structured data."""
    return _default_runner.parse_output(raw)


def total_tokens(token_counts: dict) -> int:
    """Return input_tokens + output_tokens as the fairest consumption proxy."""
    return _default_runner.total_tokens(token_counts)
