#!/usr/bin/env bash
#
# do_tests.sh - run the full test suite.
#
# Core tests use only the Python standard library.
# Web UI tests additionally need FastAPI/Uvicorn/Jinja2, which live in .venv
# (see README "Running the Web UI"). If no suitable interpreter is found, the
# web tests are skipped with a warning instead of failing the whole run.
#
# Usage:
#   ./do_tests.sh                          # run everything
#   ./do_tests.sh -v                       # extra unittest flags, passed through
#   ./do_tests.sh tests.test_core          # run specific module(s) only
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

CORE_TESTS=(tests.test_core tests.test_concurrency tests.test_protocol tests.test_cluster tests.test_logserver)
WEB_TESTS=(tests.test_web_ui)

PY_CORE="${PY_CORE:-python3}"

# Pick a Python for the web tests: prefer the project venv, else system python3.
pick_web_python() {
  if [[ -x ".venv/bin/python" ]] && .venv/bin/python -c "import fastapi, uvicorn, jinja2, multipart" >/dev/null 2>&1; then
    echo ".venv/bin/python"
  elif "${PY_CORE}" -c "import fastapi, uvicorn, jinja2, multipart" >/dev/null 2>&1; then
    echo "${PY_CORE}"
  fi
}

failed=0

# ---- explicit module(s) provided: run just those --------------------------
if [[ $# -gt 0 && "$1" != -* ]]; then
  if [[ " ${WEB_TESTS[*]} " == *" $1 "* ]]; then
    PY="$(pick_web_python)"
    if [[ -z "${PY}" ]]; then
      echo "SKIPPED: $1 needs fastapi/uvicorn/jinja2/python-multipart."
      echo " Install them with: uv venv .venv && uv pip install -r web/requirements.txt"
      exit 0
    fi
  else
    PY="${PY_CORE}"
  fi
  echo "Running: ${PY} -m unittest $*"
  exec "${PY}" -m unittest "$@"
fi

EXTRA=("$@")   # flags such as -v

# ---- core tests -----------------------------------------------------------
echo "==================================================================="
echo " Core tests (${PY_CORE})"
echo "==================================================================="
if ! "${PY_CORE}" -m unittest "${CORE_TESTS[@]}" "${EXTRA[@]}"; then
  failed=1
fi

# ---- web UI tests ---------------------------------------------------------
echo ""
echo "==================================================================="
echo " Web UI tests"
echo "==================================================================="
PY_WEB="$(pick_web_python)"
if [[ -n "${PY_WEB}" ]]; then
  echo " using: ${PY_WEB}"
  if ! "${PY_WEB}" -m unittest "${WEB_TESTS[@]}" "${EXTRA[@]}"; then
    failed=1
  fi
else
  echo " SKIPPED: no interpreter with fastapi/uvicorn/jinja2/python-multipart found."
  echo " Install the web dependencies to run these tests:"
  echo "   uv venv .venv && uv pip install -r web/requirements.txt"
fi

echo ""
if [[ "${failed}" -eq 0 ]]; then
  echo "All tests passed."
else
  echo "Some tests FAILED."
fi
exit "${failed}"
