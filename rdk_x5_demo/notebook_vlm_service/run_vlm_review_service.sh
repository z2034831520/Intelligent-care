#!/usr/bin/env bash
set -euo pipefail

source ./.env
python ollama_review_service.py
