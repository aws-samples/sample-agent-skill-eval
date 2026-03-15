"""Tests for grading module — deterministic grading + LLM fallback."""

import json
import pytest
from unittest.mock import patch, MagicMock

from skill_eval.grading import grade_output, _deterministic_grade, _llm_grade
from skill_eval.eval_schemas import AssertionResult


class TestDeterministicContains:
    """Test 'contains X' assertion pattern."""

    def test_contains_found(self):
        result = _deterministic_grade("Hello World", "contains 'Hello'")
        assert result is not None
        assert result.passed is True
        assert result.method == "deterministic"

    def test_contains_not_found(self):
        result = _deterministic_grade("Hello World", "contains 'Goodbye'")
        assert result is not None
        assert result.passed is False

    def test_contains_case_insensitive(self):
        result = _deterministic_grade("Hello World", "contains 'hello'")
        assert result is not None
        assert result.passed is True

    def test_contains_double_quotes(self):
        result = _deterministic_grade("Hello World", 'contains "Hello"')
        assert result is not None
        assert result.passed is True

    def test_contains_no_quotes(self):
        result = _deterministic_grade("Hello World", "contains Hello")
        assert result is not None
        assert result.passed is True


class TestDeterministicDoesNotContain:
    """Test 'does not contain X' assertion pattern."""

    def test_does_not_contain_absent(self):
        result = _deterministic_grade("Hello World", "does not contain 'Goodbye'")
        assert result is not None
        assert result.passed is True

    def test_does_not_contain_present(self):
        result = _deterministic_grade("Hello World", "does not contain 'Hello'")
        assert result is not None
        assert result.passed is False

    def test_does_not_contain_case_insensitive(self):
        result = _deterministic_grade("Error occurred", "does not contain 'error'")
        assert result is not None
        assert result.passed is False

    def test_does_not_contain_no_quotes(self):
        result = _deterministic_grade("Hello World", "does not contain Goodbye")
        assert result is not None
        assert result.passed is True


class TestDeterministicValidJson:
    """Test 'is valid JSON' assertion pattern."""

    def test_valid_json(self):
        result = _deterministic_grade('{"key": "value"}', "is valid JSON")
        assert result is not None
        assert result.passed is True

    def test_invalid_json(self):
        result = _deterministic_grade("not json at all", "is valid JSON")
        assert result is not None
        assert result.passed is False

    def test_valid_json_array(self):
        result = _deterministic_grade("[1, 2, 3]", "is valid json")
        assert result is not None
        assert result.passed is True

    def test_output_is_valid_json(self):
        result = _deterministic_grade('{"a": 1}', "output is valid json")
        assert result is not None
        assert result.passed is True


class TestDeterministicLineCount:
    """Test 'has at least N lines' assertion pattern."""

    def test_has_enough_lines(self):
        result = _deterministic_grade("line1\nline2\nline3", "has at least 2 lines")
        assert result is not None
        assert result.passed is True

    def test_has_exact_lines(self):
        result = _deterministic_grade("line1\nline2", "has at least 2 lines")
        assert result is not None
        assert result.passed is True

    def test_not_enough_lines(self):
        result = _deterministic_grade("one line", "has at least 5 lines")
        assert result is not None
        assert result.passed is False

    def test_singular_line(self):
        result = _deterministic_grade("one line", "has at least 1 line")
        assert result is not None
        assert result.passed is True


class TestDeterministicStartsWith:
    """Test 'starts with X' assertion pattern."""

    def test_starts_with_match(self):
        result = _deterministic_grade("Hello World", "starts with 'Hello'")
        assert result is not None
        assert result.passed is True

    def test_starts_with_no_match(self):
        result = _deterministic_grade("Hello World", "starts with 'World'")
        assert result is not None
        assert result.passed is False

    def test_starts_with_no_quotes(self):
        result = _deterministic_grade("Hello World", "starts with Hello")
        assert result is not None
        assert result.passed is True


class TestDeterministicEndsWith:
    """Test 'ends with X' assertion pattern."""

    def test_ends_with_match(self):
        result = _deterministic_grade("Hello World", "ends with 'World'")
        assert result is not None
        assert result.passed is True

    def test_ends_with_no_match(self):
        result = _deterministic_grade("Hello World", "ends with 'Hello'")
        assert result is not None
        assert result.passed is False

    def test_ends_with_no_quotes(self):
        result = _deterministic_grade("Hello World", "ends with World")
        assert result is not None
        assert result.passed is True


class TestDeterministicRegex:
    """Test 'matches regex /X/' assertion pattern."""

    def test_regex_match(self):
        result = _deterministic_grade("Error code: 404", "matches regex /\\d{3}/")
        assert result is not None
        assert result.passed is True

    def test_regex_no_match(self):
        result = _deterministic_grade("No numbers here", "matches regex /\\d+/")
        assert result is not None
        assert result.passed is False

    def test_regex_pattern_keyword(self):
        result = _deterministic_grade("Hello World", "matches pattern /^Hello/")
        assert result is not None
        assert result.passed is True

    def test_invalid_regex(self):
        result = _deterministic_grade("test", "matches regex /[invalid/")
        assert result is not None
        assert result.passed is False
        assert "Invalid regex" in result.evidence


class TestDeterministicNoMatch:
    """Test that ambiguous assertions return None (deferred to LLM)."""

    def test_ambiguous_assertion(self):
        result = _deterministic_grade("output", "the output is well-formatted and professional")
        assert result is None

    def test_complex_assertion(self):
        result = _deterministic_grade("output", "correctly handles edge cases")
        assert result is None

    def test_semantic_assertion(self):
        result = _deterministic_grade("output", "the summary is accurate")
        assert result is None


class TestGradeOutput:
    """Test the main grade_output entry point."""

    def test_all_deterministic(self):
        output = "Hello World\nLine 2\nLine 3"
        assertions = [
            "contains 'Hello'",
            "has at least 2 lines",
            "does not contain 'error'",
        ]
        results, pass_rate = grade_output(output, assertions)
        assert len(results) == 3
        assert all(r.passed for r in results)
        assert pass_rate == 1.0

    def test_mixed_pass_fail(self):
        output = "Hello"
        assertions = [
            "contains 'Hello'",
            "contains 'Goodbye'",
        ]
        results, pass_rate = grade_output(output, assertions)
        assert len(results) == 2
        assert pass_rate == 0.5

    def test_empty_assertions(self):
        results, pass_rate = grade_output("output", [])
        assert len(results) == 0
        assert pass_rate == 1.0

    def test_all_fail(self):
        output = "abc"
        assertions = [
            "contains 'xyz'",
            "has at least 10 lines",
        ]
        results, pass_rate = grade_output(output, assertions)
        assert pass_rate == 0.0


class TestLlmGradeFallback:
    """Test LLM grading fallback when claude is not available."""

    def test_llm_fallback_no_claude(self):
        """When claude is unavailable, LLM grading should return passed=False."""
        with patch("skill_eval._claude.check_claude_available", side_effect=RuntimeError("not found")):
            results = _llm_grade("output", ["is professional and well-written"])
        assert len(results) == 1
        assert results[0].method == "llm"
        assert results[0].passed is False

    def test_grade_output_with_ambiguous_defers(self):
        """Ambiguous assertions should be deferred to LLM grading."""
        output = "Some output text"
        assertions = [
            "contains 'output'",           # deterministic
            "is professional and clear",    # ambiguous -> LLM
        ]
        results, pass_rate = grade_output(output, assertions)
        assert len(results) == 2
        assert results[0].method == "deterministic"
        assert results[0].passed is True
        # Second result will use LLM (or fallback)
        assert results[1].method == "llm"


class TestLLMGradingEnhanced:
    """Test enhanced LLM grading: few-shot examples, confidence, uncertain flag, truncation."""

    def test_few_shot_examples_in_prompt(self):
        """Verify that the prompt sent to claude includes the three few-shot examples."""
        captured_prompts = []

        def capture_prompt(prompt, **kwargs):
            captured_prompts.append(prompt)
            response = json.dumps([{"index": 1, "passed": True, "confidence": 0.9, "evidence": "ok"}])
            return (response, "", 0, 1.0)

        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", side_effect=capture_prompt):
                _llm_grade("some output", ["is clear"])

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        # Check all three examples are present
        assert "The weather in Tokyo is 22°C and sunny" in prompt
        assert "mentions temperature" in prompt
        assert "Here is your CSV summary" in prompt
        assert "includes a bar chart" in prompt
        assert "The data shows an upward trend with some fluctuations" in prompt
        assert "provides statistical analysis" in prompt

    def test_confidence_parsing(self):
        """Test that confidence values are correctly parsed from LLM response."""
        mock_response = json.dumps([
            {"index": 1, "passed": True, "confidence": 0.95, "evidence": "clear match"},
            {"index": 2, "passed": False, "confidence": 0.8, "evidence": "not found"},
        ])

        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", return_value=(mock_response, "", 0, 1.0)):
                results = _llm_grade("output", ["assertion 1", "assertion 2"])

        assert results[0].confidence == 0.95
        assert results[0].uncertain is False
        assert results[1].confidence == 0.8
        assert results[1].uncertain is False

    def test_uncertain_marking_low_confidence(self):
        """When confidence < 0.5, the result should be marked as uncertain=True."""
        mock_response = json.dumps([
            {"index": 1, "passed": True, "confidence": 0.3, "evidence": "borderline"},
            {"index": 2, "passed": False, "confidence": 0.49, "evidence": "unclear"},
            {"index": 3, "passed": True, "confidence": 0.5, "evidence": "just above threshold"},
        ])

        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", return_value=(mock_response, "", 0, 1.0)):
                results = _llm_grade("output", ["a1", "a2", "a3"])

        assert results[0].uncertain is True
        assert results[0].passed is True  # passed is not changed
        assert results[1].uncertain is True
        assert results[2].uncertain is False  # 0.5 is NOT < 0.5

    def test_16000_char_truncation(self):
        """Verify output is truncated at 16000 chars, not 8000."""
        captured_prompts = []

        def capture_prompt(prompt, **kwargs):
            captured_prompts.append(prompt)
            response = json.dumps([{"index": 1, "passed": True, "confidence": 0.9, "evidence": "ok"}])
            return (response, "", 0, 1.0)

        long_output = "x" * 20000

        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", side_effect=capture_prompt):
                _llm_grade(long_output, ["is long"])

        prompt = captured_prompts[0]
        # The truncated output should be 16000 chars of 'x', not 8000
        assert "x" * 16000 in prompt
        assert "x" * 16001 not in prompt


class TestLlmGradeWithMock:
    """Test LLM grading with mocked claude CLI."""

    def test_successful_llm_grading(self):
        """Test LLM grading when claude returns valid JSON response."""
        mock_response = json.dumps([
            {"index": 1, "passed": True, "evidence": "output is clear"},
            {"index": 2, "passed": False, "evidence": "format is wrong"},
        ])

        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", return_value=(mock_response, "", 0, 1.5)):
                results = _llm_grade(
                    "Some output",
                    ["is clear and readable", "uses correct formatting"],
                    timeout=30,
                )
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False
        assert results[0].method == "llm"

    def test_llm_grading_parse_failure(self):
        """Test graceful handling of unparseable LLM response."""
        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", return_value=("not json", "", 0, 1.0)):
                results = _llm_grade("output", ["is good"])
        assert len(results) == 1
        assert results[0].passed is False
        assert "Failed to parse" in results[0].evidence

    def test_llm_grading_cli_error(self):
        """Test graceful handling of claude CLI returning non-zero."""
        with patch("skill_eval._claude.check_claude_available"):
            with patch("skill_eval._claude.run_claude_prompt", return_value=("", "error", 1, 0.5)):
                results = _llm_grade("output", ["is good"])
        assert len(results) == 1
        assert results[0].passed is False
        assert "failed" in results[0].evidence.lower()
