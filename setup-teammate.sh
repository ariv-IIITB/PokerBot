#!/usr/bin/env bash
set -e

echo "=== Setting up Claude Code for PokerBot ==="
echo "Installing Ponytail plugin..."
claude plugin marketplace add DietrichGebert/ponytail 2>/dev/null || true
claude plugin install ponytail@ponytail 2>/dev/null || true

echo "Done! All project skills and agents are already tracked in .claude/."
