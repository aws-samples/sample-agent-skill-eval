#!/usr/bin/env bash
# demo.sh — End-to-end demonstration of all skill-eval commands.
# Runs against built-in test fixtures. No claude CLI dependency.
#
# Usage:
#   bash demo.sh          # from any directory
#   chmod +x demo.sh && ./demo.sh

set -euo pipefail

# ── Color helpers (respect NO_COLOR / pipe detection) ─────────────
if [[ -z "${NO_COLOR:-}" ]] && [[ -t 1 ]]; then
  BOLD="\033[1m"
  CYAN="\033[36m"
  GREEN="\033[32m"
  YELLOW="\033[33m"
  RED="\033[31m"
  RESET="\033[0m"
else
  BOLD="" CYAN="" GREEN="" YELLOW="" RED="" RESET=""
fi

section() {
  echo ""
  echo -e "${BOLD}${CYAN}── $1 ──${RESET}"
  echo ""
}

# ── Directory anchoring ──────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD="${SCRIPT_DIR}/tests/fixtures/good-skill"
BAD="${SCRIPT_DIR}/tests/fixtures/bad-skill"
EVAL="${SCRIPT_DIR}/tests/fixtures/eval-skill"

# ── Preflight check ─────────────────────────────────────────────
if ! python3 -c "import skill_eval" 2>/dev/null; then
  echo -e "${RED}Error: skill_eval module not importable.${RESET}"
  echo "Install with:  pip install -e '${SCRIPT_DIR}'"
  exit 1
fi

# ── Cleanup trap ─────────────────────────────────────────────────
# The snapshot command writes evals/ into the good-skill fixture; remove it on exit.
GOOD_EVALS_EXISTED=false
if [[ -d "${GOOD}/evals" ]]; then
  GOOD_EVALS_EXISTED=true
fi
cleanup() {
  if [[ "${GOOD_EVALS_EXISTED}" == "false" ]]; then
    rm -rf "${GOOD}/evals"
  fi
}
trap cleanup EXIT

# ── 1. Audit good-skill ─────────────────────────────────────────
section "1/7  Audit good-skill (expect Score 100, Grade A)"
python3 -m skill_eval.cli audit "${GOOD}"

# ── 2. Audit bad-skill (verbose) ────────────────────────────────
section "2/7  Audit bad-skill --verbose (expect Score 0, Grade F)"
# bad-skill has critical findings → exit 2 under set -e, so allow failure
python3 -m skill_eval.cli audit "${BAD}" --verbose || true

# ── 3. Snapshot good-skill ──────────────────────────────────────
section "3/7  Snapshot good-skill (save baseline)"
python3 -m skill_eval.cli snapshot "${GOOD}" --version demo

# ── 4. Regression check ────────────────────────────────────────
section "4/7  Regression check good-skill (compare against baseline)"
python3 -m skill_eval.cli regression "${GOOD}"

# ── 5. Functional eval (dry-run) ────────────────────────────────
section "5/7  Functional eval --dry-run (show eval cases)"
python3 -m skill_eval.cli functional "${EVAL}" --dry-run

# ── 6. Trigger eval (dry-run) ──────────────────────────────────
section "6/7  Trigger eval --dry-run (show trigger queries)"
python3 -m skill_eval.cli trigger "${EVAL}" --dry-run

# ── 7. Compare (dry-run) ────────────────────────────────────────
section "7/7  Compare --dry-run (eval-skill vs itself)"
python3 -m skill_eval.cli compare "${EVAL}" "${EVAL}" --dry-run

# ── Done ────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}All 7 demo sections completed successfully.${RESET}"
