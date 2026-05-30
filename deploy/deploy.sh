#!/usr/bin/env bash
# Deployment-Skript — wird von GitHub Actions via SSH aufgerufen.
# Run als root: sudo /opt/aristeus/app/deploy/deploy.sh
set -euo pipefail

APP=/opt/aristeus/app
FRONTEND=/opt/aristeus/frontend

echo "--- Deploy $(date '+%Y-%m-%d %H:%M:%S') ---"

echo "[1/5] git pull"
cd "$APP"
runuser -u aristeus -- git pull

# Symlink .env sicherstellen (falls nach git pull verschwunden)
ln -sf /opt/aristeus/.env "$APP/backend/.env"

echo "[2/5] pip install"
cd "$APP/backend"
runuser -u aristeus -- .venv/bin/pip install -e . --quiet

echo "[3/5] alembic upgrade"
runuser -u aristeus -- .venv/bin/alembic upgrade head

echo "[4/5] npm build"
cd "$APP/frontend"
runuser -u aristeus -- npm ci --silent
runuser -u aristeus -- npm run build
cp -r dist/. "$FRONTEND/dist/"
chown -R aristeus:aristeus "$FRONTEND/dist"

echo "[5/5] restart service"
systemctl restart aristeus-api

COMMIT=$(runuser -u aristeus -- git -C "$APP" rev-parse --short HEAD)
echo "--- Done: $COMMIT ---"
