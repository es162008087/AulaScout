#!/bin/bash
uv run python web/app.py 2>&1 | tee /tmp/web.log
