#!/usr/bin/env bash
# Chạy trên Linux/macOS
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  .venv/bin/pip install "piper-tts>=1.2" || true
fi
exec .venv/bin/python main.py "$@"
