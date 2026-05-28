#!/usr/bin/env bash
# Docker無しで aggregator を1回実行する。動作確認用。
set -euo pipefail

cd "$(dirname "$0")/.."

# .env を読み込む
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Docker外実行用に変数を上書き
export WHISKY_CONFIG_DIR="$(pwd)/config"
export WHISKY_DB_PATH="$(pwd)/data/whisky.sqlite"
mkdir -p data

# 依存をローカルvenvに入れる (初回のみ)
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r aggregator/requirements.txt
fi

./.venv/bin/python aggregator/main.py
