"""Tests for skill_eval.cost module."""

import pytest
from skill_eval.cost import (
    estimate_cost,
    format_cost,
    estimate_eval_cost,
    estimate_trigger_cost,
    MODEL_PRICING,
    DEFAULT_MODEL,
)


class TestEstimateCost:
    """Test basic cost estimation."""

    def test_zero_tokens(self):
        result = estimate_cost(0, 0)
        assert result["total_cost"] == 0.0
        assert result["input_cost"] == 0.0
        assert result["output_cost"] == 0.0

    def test_sonnet_pricing(self):
        # 1M input tokens at $3/M = $3.00
        result = estimate_cost(1_000_000, 0, model="sonnet")
        assert result["input_cost"] == 3.0
        assert result["output_cost"] == 0.0
        assert result["total_cost"] == 3.0

    def test_sonnet_output_pricing(self):
        # 1M output tokens at $15/M = $15.00
        result = estimate_cost(0, 1_000_000, model="sonnet")
        assert result["output_cost"] == 15.0

    def test_opus_pricing(self):
        # 1M input at $15/M + 1M output at $75/M = $90
        result = estimate_cost(1_000_000, 1_000_000, model="opus")
        assert result["input_cost"] == 15.0
        assert result["output_cost"] == 75.0
        assert result["total_cost"] == 90.0

    def test_haiku_pricing(self):
        result = estimate_cost(1_000_000, 1_000_000, model="haiku")
        assert result["input_cost"] == 0.8
        assert result["output_cost"] == 4.0
        assert result["total_cost"] == 4.8

    def test_unknown_model_falls_back_to_default(self):
        result = estimate_cost(1_000_000, 0, model="unknown-model-xyz")
        default_result = estimate_cost(1_000_000, 0, model=DEFAULT_MODEL)
        assert result["input_cost"] == default_result["input_cost"]

    def test_realistic_eval_run(self):
        # ~100K input, 500 output (typical single eval run)
        result = estimate_cost(100_000, 500, model="sonnet")
        assert result["total_cost"] > 0
        assert result["total_cost"] < 1.0  # Should be well under $1

    def test_currency_field(self):
        result = estimate_cost(1000, 1000)
        assert result["currency"] == "USD"

    def test_model_field(self):
        result = estimate_cost(1000, 1000, model="opus")
        assert result["model"] == "opus"


class TestFormatCost:
    """Test cost formatting."""

    def test_small_cost(self):
        assert format_cost(0.0042) == "$0.0042"

    def test_larger_cost(self):
        assert format_cost(1.23) == "$1.23"

    def test_zero(self):
        assert format_cost(0) == "$0.0000"

    def test_exactly_one_cent(self):
        assert format_cost(0.01) == "$0.01"

    def test_sub_cent(self):
        assert format_cost(0.005) == "$0.0050"


class TestEstimateEvalCost:
    """Test functional evaluation cost estimation."""

    def test_basic_eval_cost(self):
        result = estimate_eval_cost(
            with_input=100_000,
            with_output=500,
            without_input=20_000,
            without_output=300,
            num_evals=6,
            runs_per_eval=1,
            model="sonnet",
        )
        assert result["total_cost"] > 0
        assert result["total_runs"] == 6
        assert "with_skill_per_run" in result
        assert "without_skill_per_run" in result
        assert result["currency"] == "USD"

    def test_multiple_runs(self):
        single = estimate_eval_cost(
            with_input=100_000, with_output=500,
            without_input=20_000, without_output=300,
            num_evals=6, runs_per_eval=1,
        )
        triple = estimate_eval_cost(
            with_input=100_000, with_output=500,
            without_input=20_000, without_output=300,
            num_evals=6, runs_per_eval=3,
        )
        assert triple["total_runs"] == 18
        assert triple["total_cost"] == pytest.approx(single["total_cost"] * 3, rel=0.01)

    def test_zero_tokens(self):
        result = estimate_eval_cost(
            with_input=0, with_output=0,
            without_input=0, without_output=0,
            num_evals=1, runs_per_eval=1,
        )
        assert result["total_cost"] == 0.0


class TestEstimateTriggerCost:
    """Test trigger evaluation cost estimation."""

    def test_basic_trigger_cost(self):
        result = estimate_trigger_cost(
            mean_input_tokens=50_000,
            mean_output_tokens=200,
            num_queries=8,
            runs_per_query=1,
            model="sonnet",
        )
        assert result["total_cost"] > 0
        assert result["total_runs"] == 8
        assert "per_run" in result

    def test_multiple_runs_per_query(self):
        single = estimate_trigger_cost(
            mean_input_tokens=50_000, mean_output_tokens=200,
            num_queries=8, runs_per_query=1,
        )
        double = estimate_trigger_cost(
            mean_input_tokens=50_000, mean_output_tokens=200,
            num_queries=8, runs_per_query=2,
        )
        assert double["total_runs"] == 16
        assert double["total_cost"] == pytest.approx(single["total_cost"] * 2, rel=0.01)


class TestModelPricing:
    """Test model pricing table."""

    def test_all_models_have_input_and_output(self):
        for model, pricing in MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing input pricing"
            assert "output" in pricing, f"{model} missing output pricing"
            assert pricing["input"] >= 0, f"{model} has negative input price"
            assert pricing["output"] >= 0, f"{model} has negative output price"

    def test_default_model_exists(self):
        assert DEFAULT_MODEL in MODEL_PRICING
