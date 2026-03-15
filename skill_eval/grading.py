"""Deterministic + LLM assertion grading for functional evaluation.

Assertions are natural-language strings from evals.json.  Deterministic patterns
are tried first; ambiguous assertions fall back to an LLM judge via the claude CLI.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from skill_eval.eval_schemas import AssertionResult


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def grade_output(
    output: str,
    assertions: list[str],
    timeout: int = 60,
) -> tuple[list[AssertionResult], float]:
    """Grade an output string against a list of assertion strings.

    Returns:
        Tuple of (list of AssertionResult, pass_rate as 0.0-1.0).
    """
    results: list[AssertionResult] = []
    deferred: list[str] = []

    for assertion in assertions:
        det = _deterministic_grade(output, assertion)
        if det is not None:
            results.append(det)
        else:
            deferred.append(assertion)

    # Batch LLM grading for remaining assertions
    if deferred:
        llm_results = _llm_grade(output, deferred, timeout=timeout)
        results.extend(llm_results)

    if not results:
        return results, 1.0

    pass_rate = sum(1 for r in results if r.passed) / len(results)
    return results, pass_rate


# ---------------------------------------------------------------------------
# Deterministic grading rules
# ---------------------------------------------------------------------------

def _deterministic_grade(output: str, assertion: str) -> Optional[AssertionResult]:
    """Try to evaluate an assertion deterministically.

    Returns an AssertionResult if a pattern matched, or None to defer to LLM.
    """
    lower = assertion.lower().strip()

    # "contains X" / 'contains "X"'
    m = re.match(r'^contains\s+["\'](.+?)["\']$', lower)
    if not m:
        m = re.match(r'^contains\s+(.+)$', lower)
    if m:
        needle = m.group(1)
        found = needle.lower() in output.lower()
        return AssertionResult(
            text=assertion,
            passed=found,
            evidence=f"Substring {'found' if found else 'not found'}: {needle!r}",
            method="deterministic",
        )

    # "does not contain X" / 'does not contain "X"'
    m = re.match(r'^does not contain\s+["\'](.+?)["\']$', lower)
    if not m:
        m = re.match(r'^does not contain\s+(.+)$', lower)
    if m:
        needle = m.group(1)
        found = needle.lower() in output.lower()
        return AssertionResult(
            text=assertion,
            passed=not found,
            evidence=f"Substring {'found (FAIL)' if found else 'not found (OK)'}: {needle!r}",
            method="deterministic",
        )

    # "is valid JSON" / "is valid json"
    if lower in ("is valid json", "output is valid json"):
        try:
            json.loads(output)
            return AssertionResult(
                text=assertion, passed=True,
                evidence="Output parsed as valid JSON",
                method="deterministic",
            )
        except (json.JSONDecodeError, ValueError) as e:
            return AssertionResult(
                text=assertion, passed=False,
                evidence=f"JSON parse error: {e}",
                method="deterministic",
            )

    # "has at least N lines"
    m = re.match(r'^has at least (\d+) lines?$', lower)
    if m:
        threshold = int(m.group(1))
        count = len(output.splitlines())
        passed = count >= threshold
        return AssertionResult(
            text=assertion, passed=passed,
            evidence=f"Line count: {count} (threshold: {threshold})",
            method="deterministic",
        )

    # "starts with X"
    m = re.match(r'^starts with\s+["\'](.+?)["\']$', lower)
    if not m:
        m = re.match(r'^starts with\s+(.+)$', lower)
    if m:
        prefix = m.group(1)
        passed = output.lower().lstrip().startswith(prefix.lower())
        return AssertionResult(
            text=assertion, passed=passed,
            evidence=f"Output {'starts' if passed else 'does not start'} with: {prefix!r}",
            method="deterministic",
        )

    # "ends with X"
    m = re.match(r'^ends with\s+["\'](.+?)["\']$', lower)
    if not m:
        m = re.match(r'^ends with\s+(.+)$', lower)
    if m:
        suffix = m.group(1)
        passed = output.lower().rstrip().endswith(suffix.lower())
        return AssertionResult(
            text=assertion, passed=passed,
            evidence=f"Output {'ends' if passed else 'does not end'} with: {suffix!r}",
            method="deterministic",
        )

    # "matches regex /X/" or "matches pattern /X/"
    m = re.match(r'^matches\s+(?:regex|pattern)\s+/(.+)/$', assertion.strip())
    if m:
        pattern = m.group(1)
        try:
            found = re.search(pattern, output) is not None
            return AssertionResult(
                text=assertion, passed=found,
                evidence=f"Regex /{pattern}/ {'matched' if found else 'did not match'}",
                method="deterministic",
            )
        except re.error as e:
            return AssertionResult(
                text=assertion, passed=False,
                evidence=f"Invalid regex: {e}",
                method="deterministic",
            )

    # No deterministic match
    return None


# ---------------------------------------------------------------------------
# LLM grading (via claude CLI)
# ---------------------------------------------------------------------------

def _llm_grade(
    output: str,
    assertions: list[str],
    timeout: int = 60,
) -> list[AssertionResult]:
    """Grade ambiguous assertions using the claude CLI as an LLM judge.

    Falls back to passed=False with explanatory evidence if claude is unavailable.
    """
    try:
        from skill_eval._claude import check_claude_available, run_claude_prompt
        check_claude_available()
    except Exception:
        return [
            AssertionResult(
                text=a,
                passed=False,
                evidence="claude CLI not available; cannot evaluate ambiguous assertion",
                method="llm",
            )
            for a in assertions
        ]

    # Build a structured prompt for batch evaluation
    assertions_block = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(assertions))
    # Truncate output to avoid exceeding context limits
    truncated = output[:16000] if len(output) > 16000 else output

    prompt = f"""You are an evaluation judge. Determine whether each assertion is satisfied by the given output.

OUTPUT:
{truncated}

ASSERTIONS:
{assertions_block}

Respond with ONLY a JSON array where each element has:
  {{"index": <1-based>, "passed": true/false, "confidence": 0.0-1.0, "evidence": "brief reason"}}

Here are examples of how to judge assertions:

Example 1 (PASS with high confidence):
  Output: "The weather in Tokyo is 22°C and sunny"
  Assertion: "mentions temperature"
  Result: {{"index": 1, "passed": true, "confidence": 0.95, "evidence": "output explicitly states 22°C"}}

Example 2 (FAIL with high confidence):
  Output: "Here is your CSV summary"
  Assertion: "includes a bar chart"
  Result: {{"index": 1, "passed": false, "confidence": 0.9, "evidence": "output only contains CSV summary, no bar chart"}}

Example 3 (UNCERTAIN - low confidence):
  Output: "The data shows an upward trend with some fluctuations"
  Assertion: "provides statistical analysis"
  Result: {{"index": 1, "passed": true, "confidence": 0.4, "evidence": "mentions trend but lacks formal statistical measures"}}"""

    stdout, stderr, rc, elapsed = run_claude_prompt(
        prompt, timeout=timeout,
    )

    if rc != 0 or not stdout.strip():
        return [
            AssertionResult(
                text=a,
                passed=False,
                evidence=f"LLM grading failed (rc={rc}): {stderr[:200]}",
                method="llm",
            )
            for a in assertions
        ]

    # Parse the JSON response
    try:
        # Try to find a JSON array in the output
        text = stdout.strip()
        # Handle case where output has text before/after JSON
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            parsed = json.loads(text[start:end])
        else:
            raise json.JSONDecodeError("No JSON array found", text, 0)

        results: list[AssertionResult] = []
        for i, assertion in enumerate(assertions):
            # Find matching entry
            entry = next((e for e in parsed if e.get("index") == i + 1), None)
            if entry:
                confidence = float(entry.get("confidence", 1.0))
                results.append(AssertionResult(
                    text=assertion,
                    passed=bool(entry.get("passed", False)),
                    evidence=str(entry.get("evidence", "")),
                    method="llm",
                    confidence=confidence,
                    uncertain=confidence < 0.5,
                ))
            else:
                results.append(AssertionResult(
                    text=assertion,
                    passed=False,
                    evidence="LLM judge did not return result for this assertion",
                    method="llm",
                ))
        return results
    except (json.JSONDecodeError, KeyError, TypeError):
        return [
            AssertionResult(
                text=a,
                passed=False,
                evidence=f"Failed to parse LLM judge response: {stdout[:200]}",
                method="llm",
            )
            for a in assertions
        ]
