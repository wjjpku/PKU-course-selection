#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec .venv-ocr/bin/python skj包/main.py
