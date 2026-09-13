#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y ffmpeg aria2 curl git python3 python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
python -m pip install -r requirements.txt
