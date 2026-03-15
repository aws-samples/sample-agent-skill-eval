---
name: data-analysis
description: "Analyze CSV and JSON data files to produce summary statistics, detect anomalies, and generate formatted reports. Use when the user asks to summarize data, compute statistics (mean, median, percentiles), find outliers, or produce tabular reports from structured data files. NOT for: image analysis, unstructured text processing, database queries, or real-time streaming data."
---

# Data Analysis Skill

Analyze structured data files (CSV, JSON) and produce clear, actionable reports.

## When to Use

- User asks to "summarize", "analyze", or "describe" a data file
- User wants statistics: row counts, column types, means, medians, distributions
- User needs to find anomalies or outliers in numeric data
- User requests a formatted report or table from raw data

## When NOT to Use

- Unstructured text files (use a text-processing skill instead)
- Database queries (use a database skill)
- Image or binary file analysis
- Real-time or streaming data

## Workflow

1. **Identify the data file** — look for CSV or JSON files in the workspace
2. **Run the analysis script** for deterministic statistics:
   ```bash
   python3 scripts/analyze_csv.py <file.csv>
   ```
3. **Interpret the results** — add context about what the numbers mean
4. **Format the output** — use markdown tables for readability

## Output Format

Always structure your response as:

1. **Overview** — file name, row count, column count
2. **Column Summary** — for each column: type, non-null count, unique values
3. **Statistics** — for numeric columns: min, max, mean, median, std dev
4. **Anomalies** — any outliers (values beyond 2 standard deviations)
5. **Recommendations** — actionable insights based on the data

## Important Notes

- Always report exact numbers, not approximations
- If a CSV has headers, use them as column names
- For large files (>10k rows), report a sample and note the total
- Never modify the source data file
