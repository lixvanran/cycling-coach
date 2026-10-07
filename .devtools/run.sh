#!/bin/bash
cd /workspace/cycling-coach
export STATIC_DIR=/workspace/cycling-coach/cycling_coach/static
export WORKSPACE_DIR="$1"
exec ./.venv/bin/python -m uvicorn cycling_coach.api.main:app --host 127.0.0.1 --port "$2"
