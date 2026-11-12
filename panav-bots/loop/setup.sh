#!/usr/bin/env bash
# run once from the repo root of a fresh checkout
set -e
uv venv --python 3.11 .venv -q
uv pip install -q --python .venv/bin/python numpy scipy pytest
.venv/bin/python --version
