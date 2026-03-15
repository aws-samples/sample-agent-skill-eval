"""Token cost estimation for AI model usage.

Provides cost estimation based on model pricing. Supports Claude models
and extensible to other providers.
"""

from __future__ import annotations

# Pricing per 1M tokens (USD) — updated as of March 2025.
# Users can override via --model flag or environment variable.
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic Claude models
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Aliases for convenience
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 15.00, "output": 75.00},
    "haiku": {"input": 0.80, "output": 4.00},
}

# Default model when none specified
DEFAULT_MODEL = "sonnet"


def estimate_cost(
    input_tokens: int | float,
    output_tokens: int | float,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Estimate dollar cost from token counts.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        model: Model name or alias (case-insensitive). Falls back to DEFAULT_MODEL.

    Returns:
        dict with input_cost, output_cost, total_cost (all in USD),
        and model used for estimation.
    """
    model_key = model.lower()
    pricing = MODEL_PRICING.get(model_key, MODEL_PRICING[DEFAULT_MODEL])

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6),
        "model": model_key,
        "currency": "USD",
    }


def format_cost(cost: float) -> str:
    """Format a cost value for display.

    Returns:
        Formatted string like "$0.0042" or "$1.23".
    """
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def estimate_eval_cost(
    with_input: float,
    with_output: float,
    without_input: float,
    without_output: float,
    num_evals: int,
    runs_per_eval: int,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Estimate total cost for a functional evaluation run.

    Args:
        with_input: Mean input tokens per with-skill run.
        with_output: Mean output tokens per with-skill run.
        without_input: Mean input tokens per without-skill run.
        without_output: Mean output tokens per without-skill run.
        num_evals: Number of eval cases.
        runs_per_eval: Number of runs per eval case.
        model: Model name for pricing.

    Returns:
        dict with per_run and total cost breakdowns.
    """
    total_runs = num_evals * runs_per_eval

    with_cost = estimate_cost(with_input, with_output, model)
    without_cost = estimate_cost(without_input, without_output, model)

    # Per-eval cost (one with + one without)
    per_eval_cost = with_cost["total_cost"] + without_cost["total_cost"]

    # Total cost for all runs
    total_cost = per_eval_cost * total_runs

    return {
        "with_skill_per_run": with_cost,
        "without_skill_per_run": without_cost,
        "per_eval_pair": round(per_eval_cost, 6),
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "model": model,
        "currency": "USD",
    }


def estimate_trigger_cost(
    mean_input_tokens: float,
    mean_output_tokens: float,
    num_queries: int,
    runs_per_query: int,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Estimate total cost for a trigger evaluation run.

    Args:
        mean_input_tokens: Mean input tokens per run.
        mean_output_tokens: Mean output tokens per run.
        num_queries: Number of trigger queries.
        runs_per_query: Number of runs per query.
        model: Model name for pricing.

    Returns:
        dict with per_run and total cost breakdowns.
    """
    per_run = estimate_cost(mean_input_tokens, mean_output_tokens, model)
    total_runs = num_queries * runs_per_query
    total_cost = per_run["total_cost"] * total_runs

    return {
        "per_run": per_run,
        "total_runs": total_runs,
        "total_cost": round(total_cost, 4),
        "model": model,
        "currency": "USD",
    }
