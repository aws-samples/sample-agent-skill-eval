# Golden Eval Templates: Writing Effective Evals and Trigger Queries

This guide shows what well-written `evals.json` and `eval_queries.json` look like, using a hypothetical "data-analysis" skill as an example.

## evals.json — Functional Evaluation Cases

Each eval case tests whether the skill produces correct output for a specific prompt. Place this file at `your-skill/evals/evals.json`.

```json
[
  {
    "id": "summary-stats",
    "prompt": "Read sales.csv and output summary statistics: total rows, column names, and the sum of the revenue column.",
    "expected_output": "The file has 50 rows. Columns: date, product, region, revenue. Total revenue: $125,000.",
    "files": ["files/sales.csv"],
    "assertions": [
      "contains 'date'",
      "contains 'revenue'",
      "contains '50'",
      "contains '125'",
      "does not contain 'error'"
    ]
  },
  {
    "id": "json-output",
    "prompt": "Read sales.csv and output ONLY a JSON object with keys 'row_count' (integer) and 'columns' (array of strings). No explanation.",
    "expected_output": "{\"row_count\": 50, \"columns\": [\"date\", \"product\", \"region\", \"revenue\"]}",
    "files": ["files/sales.csv"],
    "assertions": [
      "is valid JSON",
      "starts with '{'",
      "ends with '}'",
      "matches regex /\"row_count\"\\s*:/",
      "contains 'columns'"
    ]
  },
  {
    "id": "top-products",
    "prompt": "Read sales.csv and list the top 3 products by total revenue. Format as a numbered list.",
    "expected_output": "1. Widget Pro — $45,000\n2. Gadget Plus — $38,000\n3. Basic Widget — $22,000",
    "files": ["files/sales.csv"],
    "assertions": [
      "has at least 3 lines",
      "contains 'Widget Pro'",
      "the output lists products in descending order by revenue"
    ]
  }
]
```

### Field reference

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier for the eval case. Use kebab-case. |
| `prompt` | Yes | The exact prompt sent to the agent. Be specific about expected format. |
| `expected_output` | Yes | Ideal output. Used as context by the LLM judge for semantic assertions. |
| `files` | No | Paths to test files (relative to `evals/`). Copied into the agent's workspace. |
| `assertions` | Yes | List of checks to run against the agent's output. |

### Assertion types

Mix deterministic and semantic assertions for robust coverage:

| Pattern | Type | Example |
|---------|------|---------|
| `contains 'text'` | Deterministic | `contains 'revenue'` |
| `does not contain 'text'` | Deterministic | `does not contain 'error'` |
| `is valid JSON` | Deterministic | Parses output as JSON |
| `starts with 'text'` | Deterministic | `starts with '{'` |
| `ends with 'text'` | Deterministic | `ends with '}'` |
| `matches regex /pattern/` | Deterministic | `matches regex /\"row_count\"\s*:/` |
| `has at least N lines` | Deterministic | `has at least 3 lines` |
| Free-form text | Semantic (LLM) | `the output lists products in descending order by revenue` |

**Best practice:** Lead with deterministic assertions (fast, reliable) and add one or two semantic assertions for nuanced checks that regex can't handle.

---

## eval_queries.json — Trigger Reliability Queries

Each query tests whether the skill activates (or correctly stays silent) for a given user message. Place this file at `your-skill/evals/eval_queries.json`.

```json
[
  {
    "query": "Analyze the sales data in my CSV and give me a breakdown by region",
    "should_trigger": true
  },
  {
    "query": "Read this spreadsheet and compute summary statistics",
    "should_trigger": true
  },
  {
    "query": "What patterns do you see in the Q3 revenue numbers?",
    "should_trigger": true
  },
  {
    "query": "Write me a poem about autumn",
    "should_trigger": false
  },
  {
    "query": "How do I reset my password?",
    "should_trigger": false
  }
]
```

### Design guidelines

- **Include 3+ positive queries** (`should_trigger: true`) covering different phrasings of the skill's core use case.
- **Include 2+ negative queries** (`should_trigger: false`) that are clearly outside the skill's scope.
- **Vary the wording** — don't just rephrase the same sentence. Use different vocabulary, specificity levels, and contexts.
- **Avoid ambiguous queries** — a query like "help me with this file" is too vague to have a clear expected trigger behavior.

### What gets measured

Trigger reliability runs each query multiple times and reports a **trigger rate** (0.0–1.0):

- `should_trigger: true` queries should have trigger rate close to **1.0**
- `should_trigger: false` queries should have trigger rate close to **0.0**

The overall trigger score is the percentage of queries that meet their expected behavior. This score counts for **20%** of the unified report grade.
