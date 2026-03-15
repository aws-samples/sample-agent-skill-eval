"""Tests for eval_schemas module."""

import json
import pytest

from skill_eval.eval_schemas import (
    EvalCase,
    AssertionResult,
    GradingResult,
    RunPairResult,
    BenchmarkReport,
    TriggerQuery,
    TriggerQueryResult,
    TriggerReport,
    CompareReport,
)


class TestEvalCase:
    """Test EvalCase dataclass."""

    def test_to_dict(self):
        ec = EvalCase(
            id="test-1",
            prompt="Do something",
            expected_output="result",
            files=["data.csv"],
            assertions=["contains 'result'"],
        )
        d = ec.to_dict()
        assert d["id"] == "test-1"
        assert d["prompt"] == "Do something"
        assert d["files"] == ["data.csv"]
        assert len(d["assertions"]) == 1

    def test_from_dict(self):
        data = {
            "id": "test-2",
            "prompt": "Analyze this",
            "expected_output": "done",
            "files": [],
            "assertions": ["has at least 1 lines"],
        }
        ec = EvalCase.from_dict(data)
        assert ec.id == "test-2"
        assert ec.prompt == "Analyze this"

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "id": "test-3",
            "prompt": "Hello",
            "unknown_field": "ignored",
        }
        ec = EvalCase.from_dict(data)
        assert ec.id == "test-3"
        assert not hasattr(ec, "unknown_field")

    def test_roundtrip(self):
        ec = EvalCase(
            id="rt-1",
            prompt="Test prompt",
            expected_output="expected",
            files=["a.txt", "b.txt"],
            assertions=["contains 'expected'", "has at least 1 lines"],
        )
        restored = EvalCase.from_dict(ec.to_dict())
        assert restored.id == ec.id
        assert restored.prompt == ec.prompt
        assert restored.files == ec.files
        assert restored.assertions == ec.assertions

    def test_defaults(self):
        ec = EvalCase(id="min", prompt="minimal")
        assert ec.expected_output == ""
        assert ec.files == []
        assert ec.assertions == []


class TestAssertionResult:
    """Test AssertionResult dataclass."""

    def test_to_dict(self):
        ar = AssertionResult(
            text="contains 'hello'",
            passed=True,
            evidence="Substring found",
            method="deterministic",
        )
        d = ar.to_dict()
        assert d["passed"] is True
        assert d["method"] == "deterministic"

    def test_from_dict(self):
        data = {
            "text": "is valid JSON",
            "passed": False,
            "evidence": "Parse error",
            "method": "deterministic",
        }
        ar = AssertionResult.from_dict(data)
        assert ar.text == "is valid JSON"
        assert ar.passed is False

    def test_roundtrip(self):
        ar = AssertionResult(text="test", passed=True, evidence="ok", method="llm")
        restored = AssertionResult.from_dict(ar.to_dict())
        assert restored.text == ar.text
        assert restored.passed == ar.passed
        assert restored.method == ar.method


class TestGradingResult:
    """Test GradingResult dataclass."""

    def test_to_dict(self):
        gr = GradingResult(
            eval_id="eval-1",
            run_index=0,
            assertion_results=[{"text": "test", "passed": True}],
            pass_rate=1.0,
            summary="All passed",
        )
        d = gr.to_dict()
        assert d["eval_id"] == "eval-1"
        assert d["pass_rate"] == 1.0
        assert len(d["assertion_results"]) == 1

    def test_from_dict(self):
        data = {
            "eval_id": "eval-2",
            "run_index": 1,
            "pass_rate": 0.5,
            "summary": "Half passed",
        }
        gr = GradingResult.from_dict(data)
        assert gr.eval_id == "eval-2"
        assert gr.pass_rate == 0.5

    def test_defaults(self):
        gr = GradingResult(eval_id="min", run_index=0)
        assert gr.assertion_results == []
        assert gr.pass_rate == 0.0
        assert gr.execution_metrics == {}
        assert gr.timing == {}
        assert gr.raw_output == ""


class TestRunPairResult:
    """Test RunPairResult dataclass."""

    def test_to_dict(self):
        rp = RunPairResult(
            eval_id="pair-1",
            run_index=0,
            with_skill={"pass_rate": 0.8},
            without_skill={"pass_rate": 0.5},
            delta_pass_rate=0.3,
        )
        d = rp.to_dict()
        assert d["delta_pass_rate"] == 0.3

    def test_roundtrip(self):
        rp = RunPairResult(eval_id="rt", run_index=0, delta_pass_rate=0.1)
        restored = RunPairResult.from_dict(rp.to_dict())
        assert restored.eval_id == rp.eval_id
        assert restored.delta_pass_rate == rp.delta_pass_rate


class TestBenchmarkReport:
    """Test BenchmarkReport dataclass."""

    def test_to_dict_and_json(self):
        br = BenchmarkReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            eval_count=2,
            runs_per_eval=3,
            scores={"outcome": 0.8, "process": 0.7, "style": 0.9, "efficiency": 0.6, "overall": 0.75},
            passed=True,
        )
        d = br.to_dict()
        assert d["skill_name"] == "test-skill"
        assert d["passed"] is True
        assert d["scores"]["overall"] == 0.75

        j = br.to_json()
        parsed = json.loads(j)
        assert parsed["eval_count"] == 2

    def test_from_dict(self):
        data = {
            "skill_name": "restored",
            "skill_path": "/tmp",
            "eval_count": 1,
            "passed": False,
        }
        br = BenchmarkReport.from_dict(data)
        assert br.skill_name == "restored"
        assert br.passed is False

    def test_defaults(self):
        br = BenchmarkReport(skill_name="min", skill_path="/tmp")
        assert br.eval_count == 0
        assert br.runs_per_eval == 1
        assert br.metadata == {}
        assert br.runs == []
        assert br.run_summary == {}
        assert br.scores == {}
        assert br.passed is False


class TestTriggerQuery:
    """Test TriggerQuery dataclass."""

    def test_to_dict(self):
        tq = TriggerQuery(query="analyze CSV", should_trigger=True)
        d = tq.to_dict()
        assert d["query"] == "analyze CSV"
        assert d["should_trigger"] is True

    def test_from_dict(self):
        data = {"query": "write a poem", "should_trigger": False}
        tq = TriggerQuery.from_dict(data)
        assert tq.query == "write a poem"
        assert tq.should_trigger is False

    def test_roundtrip(self):
        tq = TriggerQuery(query="test", should_trigger=True)
        restored = TriggerQuery.from_dict(tq.to_dict())
        assert restored.query == tq.query
        assert restored.should_trigger == tq.should_trigger

    def test_from_dict_ignores_extra(self):
        data = {"query": "q", "should_trigger": True, "extra": "ignored"}
        tq = TriggerQuery.from_dict(data)
        assert tq.query == "q"


class TestTriggerQueryResult:
    """Test TriggerQueryResult dataclass."""

    def test_to_dict(self):
        tqr = TriggerQueryResult(
            query="analyze CSV",
            should_trigger=True,
            trigger_count=2,
            run_count=3,
            trigger_rate=0.6667,
            passed=True,
        )
        d = tqr.to_dict()
        assert d["trigger_count"] == 2
        assert d["passed"] is True

    def test_roundtrip(self):
        tqr = TriggerQueryResult(
            query="test", should_trigger=False,
            trigger_count=0, run_count=3, trigger_rate=0.0, passed=True,
        )
        restored = TriggerQueryResult.from_dict(tqr.to_dict())
        assert restored.query == tqr.query
        assert restored.trigger_rate == tqr.trigger_rate

    def test_defaults(self):
        tqr = TriggerQueryResult(query="q", should_trigger=True)
        assert tqr.trigger_count == 0
        assert tqr.run_count == 0
        assert tqr.trigger_rate == 0.0
        assert tqr.passed is False
        assert tqr.mean_input_tokens == 0.0
        assert tqr.mean_output_tokens == 0.0
        assert tqr.mean_total_tokens == 0.0

    def test_token_fields_serialization(self):
        tqr = TriggerQueryResult(
            query="q", should_trigger=True,
            mean_input_tokens=500.0, mean_output_tokens=200.0, mean_total_tokens=700.0,
        )
        d = tqr.to_dict()
        restored = TriggerQueryResult.from_dict(d)
        assert restored.mean_input_tokens == 500.0
        assert restored.mean_output_tokens == 200.0
        assert restored.mean_total_tokens == 700.0


class TestTriggerReport:
    """Test TriggerReport dataclass."""

    def test_to_dict_and_json(self):
        tr = TriggerReport(
            skill_name="test-skill",
            skill_path="/tmp/test",
            query_results=[{"query": "q", "passed": True}],
            summary={"total_queries": 1, "passed": 1, "failed": 0},
            passed=True,
        )
        d = tr.to_dict()
        assert d["passed"] is True
        assert len(d["query_results"]) == 1

        j = tr.to_json()
        parsed = json.loads(j)
        assert parsed["skill_name"] == "test-skill"

    def test_from_dict(self):
        data = {
            "skill_name": "restored",
            "skill_path": "/tmp",
            "passed": False,
        }
        tr = TriggerReport.from_dict(data)
        assert tr.skill_name == "restored"
        assert tr.passed is False

    def test_defaults(self):
        tr = TriggerReport(skill_name="min", skill_path="/tmp")
        assert tr.query_results == []
        assert tr.summary == {}
        assert tr.passed is False


class TestCompareReport:
    """Test CompareReport dataclass."""

    def test_to_dict_and_json(self):
        cr = CompareReport(
            skill_a_name="skill-a",
            skill_a_path="/tmp/a",
            skill_b_name="skill-b",
            skill_b_path="/tmp/b",
            eval_count=2,
            runs_per_eval=3,
            per_eval=[{"eval_id": "e1"}],
            summary={"token_efficiency_ratio": 1.5},
            winner="skill-a",
        )
        d = cr.to_dict()
        assert d["skill_a_name"] == "skill-a"
        assert d["winner"] == "skill-a"
        assert d["eval_count"] == 2
        assert len(d["per_eval"]) == 1

        j = cr.to_json()
        parsed = json.loads(j)
        assert parsed["skill_b_name"] == "skill-b"

    def test_from_dict(self):
        data = {
            "skill_a_name": "a",
            "skill_a_path": "/a",
            "skill_b_name": "b",
            "skill_b_path": "/b",
            "winner": "tie",
        }
        cr = CompareReport.from_dict(data)
        assert cr.skill_a_name == "a"
        assert cr.winner == "tie"

    def test_defaults(self):
        cr = CompareReport(
            skill_a_name="a", skill_a_path="/a",
            skill_b_name="b", skill_b_path="/b",
        )
        assert cr.eval_count == 0
        assert cr.runs_per_eval == 1
        assert cr.per_eval == []
        assert cr.summary == {}
        assert cr.winner == "tie"

    def test_roundtrip(self):
        cr = CompareReport(
            skill_a_name="alpha",
            skill_a_path="/alpha",
            skill_b_name="beta",
            skill_b_path="/beta",
            eval_count=5,
            runs_per_eval=2,
            per_eval=[{"eval_id": "e1", "skill_a": {}, "skill_b": {}}],
            summary={"token_efficiency_ratio": 0.95},
            winner="beta",
        )
        restored = CompareReport.from_dict(cr.to_dict())
        assert restored.skill_a_name == cr.skill_a_name
        assert restored.skill_b_name == cr.skill_b_name
        assert restored.eval_count == cr.eval_count
        assert restored.winner == cr.winner
        assert restored.per_eval == cr.per_eval
