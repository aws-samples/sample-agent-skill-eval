# Meta-Evaluation Ground Truth

This document defines the expected correct results for skill-eval when evaluating
three target skills. Two annotators (EC2大鳌 + Mac大鳌) review independently.

## Target Skills

### 1. data-analysis (examples/data-analysis/)
- **Audit ground truth**: 98/A, 0 critical, 0 warning, 1 info (STR-016: README alongside SKILL.md)
- **Type**: Functional skill with deterministic script (analyze_csv.py)
- **Key data**: sales.csv has 20 rows, total revenue $86,700, anomaly at row 19 ($15,000)

#### Functional Eval Ground Truth
| Case ID | Correct Behavior | Key Assertions |
|---------|-----------------|----------------|
| summary-stats | Agent reads CSV, reports 20 rows, 5 columns, $86,700 total | All 5 assertions should pass |
| json-output | Agent outputs valid JSON with row_count=20, columns array | All 5 assertions should pass |
| top-products | Widget Pro > Gadget Plus > Basic Widget in revenue order | All 5 assertions should pass (if agent computes correctly) |
| anomaly-detection | Identifies $15,000 value as outlier | OR assertion + 2 LLM assertions |
| region-breakdown | North/South/East/West with revenue totals | 4 contains + 1 LLM assertion |
| script-execution | Runs analyze_csv.py, reports findings | Depends on script access |

#### Trigger Ground Truth
| Query | Should Trigger | Reason |
|-------|---------------|--------|
| "Analyze the sales data in my CSV..." | true | Direct data analysis request |
| "Read this spreadsheet and compute..." | true | Data analysis task |
| "What patterns do you see in Q3..." | true | Revenue pattern analysis |
| "Find outliers in my dataset..." | true | Anomaly detection |
| "How many rows and columns..." | true | CSV metadata query |
| "Write me a poem about autumn" | false | Creative writing, not data |
| "How do I reset my password?" | false | Account management |
| "Deploy my application to production" | false | DevOps task |
| "Can you resize this image..." | false | Image processing |
| "Query the database for all users..." | false | Database query (not CSV analysis) |

### 2. sloppy-weather (examples/golden-dataset/bad-skills/sloppy-weather/)
- **Audit ground truth**: 53/F, 1 critical (SEC-001: hardcoded API key), 2 warnings (STR-011: short description, PERM-002: Bash(*) wildcard), 1 info (STR-008: dir name mismatch)
- **Type**: Poorly written weather skill with security issues

#### Functional Eval Ground Truth
| Case ID | Correct Behavior | Key Assertions |
|---------|-----------------|----------------|
| weather-basic | Agent attempts weather lookup (may fail without real API) | Should mention NYC + weather concepts |
| weather-api-key-concern | Agent identifies hardcoded API key as security risk | Should mention API/key + security concern |

#### Trigger Ground Truth
| Query | Should Trigger | Reason |
|-------|---------------|--------|
| "What's the weather like in Sydney?" | true | Direct weather query |
| "Is it going to rain tomorrow in London?" | true | Weather forecast |
| "Get me the current temperature for Tokyo" | true | Temperature request |
| "Write a Python function to sort a list" | false | Programming task |
| "Help me debug this React component" | false | Debugging task |
| "Summarize this PDF document for me" | false | Document processing |

### 3. good-skill (tests/fixtures/good-skill/)
- **Audit ground truth**: 100/A, 0 findings
- **Type**: Well-structured minimal skill with safe Python script

#### Functional Eval Ground Truth
| Case ID | Correct Behavior | Key Assertions |
|---------|-----------------|----------------|
| process-input | Agent creates test file, runs process.py, gets JSON with status=ok | All 3 assertions should pass |
| describe-skill | Agent reads SKILL.md, reports name/license/purpose | All 3 assertions should pass |

#### Trigger Ground Truth
| Query | Should Trigger | Reason |
|-------|---------------|--------|
| "Process this input file..." | true | Direct skill usage request |
| "Run the test skill on my data" | true | Explicit skill invocation |
| "What's the weather forecast?" | false | Weather, not data processing |
| "Help me write a SQL query" | false | SQL, not file processing |
| "Translate this text to French" | false | Translation task |

## Verification Methodology

### Audit Verification
Run `skill-eval audit <path> --format json` and compare:
- Score matches ground truth ± 0 (deterministic)
- Grade matches exactly
- Finding codes match exactly
- Finding counts match exactly

### Functional Verification
Run `skill-eval functional <path> --runs 1` and check:
- Do deterministic assertions produce correct pass/fail?
- Does the overall pass rate reflect actual agent performance?
- For LLM-graded assertions: does the judge agree with ground truth?

### Trigger Verification
Run `skill-eval trigger <path> --runs 1` and check:
- Precision: of queries that triggered, how many should have?
- Recall: of queries that should trigger, how many did?
- False positive rate
- False negative rate

## Annotator Agreement

Both annotators reviewed this ground truth document.
- EC2大鳌: ✅ (author)
- Mac大鳌: ✅ (reviewed 2026-03-15)
- Disagreements: None — all ground truth values verified against actual audit outputs and test data.
