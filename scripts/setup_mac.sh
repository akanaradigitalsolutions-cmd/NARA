#!/usr/bin/env bash
# NARA local setup for macOS (Apple Silicon).
#
# Run this from the repo root AFTER installing Homebrew and the toolchain
# (see the "Quickstart (macOS)" section in README.md). It is idempotent —
# safe to re-run. It sets up the Python environment, installs NARA with the
# vault-memory extra, and pulls the local embedding model.
set -euo pipefail

cd "$(dirname "$0")/.."  # repo root

echo "NARA setup — $(pwd)"
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "✗ 'uv' not found. Install it first:  brew install uv"
  exit 1
fi

echo "→ Creating virtual environment (.venv) with Python 3.12"
uv venv --python 3.12

echo "→ Installing NARA with the [memory] extra (LanceDB + watchdog)"
uv pip install --python .venv/bin/python -e ".[memory]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "→ Created .env from template (no API key needed on a Pro/Max plan)"
fi

if command -v ollama >/dev/null 2>&1; then
  echo "→ Pulling the embedding model (nomic-embed-text)"
  ollama pull nomic-embed-text \
    || echo "  ⚠ couldn't pull — is Ollama running?  Try: brew services start ollama"
else
  echo "⚠ 'ollama' not found. Install it with:  brew install ollama"
fi

cat <<'DONE'

✅ NARA is installed. Next steps:

   1) Point NARA at your Obsidian vault:
        open -e config/nara.yaml      # set vault.path: to your real vault

   2) Activate the environment (do this in each new Terminal tab):
        source .venv/bin/activate

   3) Build the index and try a search:
        python scripts/index_vault.py
        python -m core.memory search "Relaxha pricing"
DONE
