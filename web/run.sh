#!/bin/bash
cd "$(dirname "$0")/.." && uv run python web/app.py 2>&1 | tee /tmp/web.log
