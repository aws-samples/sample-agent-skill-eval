"""Data structures for functional and trigger evaluation.

Follows existing to_dict()/from_dict() patterns from regression.py.
Compatible with Anthropic skill-creator evals.json/grading.json/benchmark.json formats.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class EvalCase:
    """A single evaluation case loaded from evals/evals.json."""
    id: str
    prompt: str
    expected_output: str = ""
    files: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvalCase":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AssertionResult:
    """Result of grading a single assertion."""
    text: str
    passed: bool
    evidence: str = ""
    method: str = "deterministic"  # "deterministic" or "llm"
    confidence: float = 1.0
    uncertain: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AssertionResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class GradingResult:
    """Per-run grading output matching grading.json format."""
    eval_id: str
    run_index: int
    assertion_results: list[dict] = field(default_factory=list)
    pass_rate: float = 0.0
    summary: str = ""
    execution_metrics: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    raw_output: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GradingResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RunPairResult:
    """Paired with-skill / without-skill results for one eval case run."""
    eval_id: str
    run_index: int
    with_skill: Optional[dict] = None
    without_skill: Optional[dict] = None
    delta_pass_rate: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunPairResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report matching benchmark.json format."""
    skill_name: str
    skill_path: str
    eval_count: int = 0
    runs_per_eval: int = 1
    metadata: dict = field(default_factory=dict)
    runs: list[dict] = field(default_factory=list)
    run_summary: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)  # 4-dimension scores
    passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkReport":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TriggerQuery:
    """A single trigger query loaded from evals/eval_queries.json."""
    query: str
    should_trigger: bool

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TriggerQuery":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TriggerQueryResult:
    """Result of evaluating a single trigger query."""
    query: str
    should_trigger: bool
    trigger_count: int = 0
    run_count: int = 0
    trigger_rate: float = 0.0
    passed: bool = False
    mean_input_tokens: float = 0.0
    mean_output_tokens: float = 0.0
    mean_total_tokens: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TriggerQueryResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TriggerReport:
    """Full trigger evaluation report."""
    skill_name: str
    skill_path: str
    query_results: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "TriggerReport":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CompareReport:
    """Side-by-side comparison report for two skills."""
    skill_a_name: str
    skill_a_path: str
    skill_b_name: str
    skill_b_path: str
    eval_count: int = 0
    runs_per_eval: int = 1
    per_eval: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    winner: str = "tie"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "CompareReport":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
