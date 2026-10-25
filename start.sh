#!/bin/bash

cd ~/Downloads/major_proj/newvision
source .venv/bin/activate

python -m uvicorn backend.main:app --host "${NEWVISION_HOST:-0.0.0.0}" --port "${NEWVISION_HTTP_PORT:-8000}"
