#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Remove Python bytecode and generated runtime artifacts
find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

rm -rf data logs
rm -f banking.conf /tmp/banking.tgz
rm -f /tmp/bank.db /tmp/server.log /tmp/banksrv.log /tmp/web.log

# Remove temporary test databases if any
find /tmp -maxdepth 1 -name "t.db" -delete 2>/dev/null || true

if [[ "${1:-}" == "--deep" ]]; then
  rm -rf .venv
  echo "Deep clean complete (virtualenv removed)."
else
  echo "Clean complete."
fi
