#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/smartroute}"
BRANCH="${BRANCH:-main}"

cd "$APP_DIR"

TMP_WEB_ENV=""
if [ -f web/.env.production ]; then
  TMP_WEB_ENV="$(mktemp)"
  cp web/.env.production "$TMP_WEB_ENV"
fi

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ -n "$TMP_WEB_ENV" ]; then
  cp "$TMP_WEB_ENV" web/.env.production
  rm -f "$TMP_WEB_ENV"
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cd web
npm ci
npm run build
cd ..

sudo systemctl restart smartroute-api
sudo nginx -t
sudo systemctl reload nginx
