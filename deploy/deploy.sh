#!/usr/bin/env bash
# Deployment-Skript — wird von GitHub Actions via SSH aufgerufen.
# Run als root: sudo /opt/aristeus/app/deploy/deploy.sh
set -euo pipefail

APP=/opt/aristeus/app
FRONTEND=/opt/aristeus/frontend
DATA=/opt/aristeus/data

echo "--- Deploy $(date '+%Y-%m-%d %H:%M:%S') ---"

# DB-Sync: falls eine neue DB unter /tmp/aristeus_new.db bereitliegt, wird sie
# vor dem Restart eingespielt. WAL-Dateien werden entfernt damit SQLite sauber startet.
if [ -f /tmp/aristeus_new.db ]; then
    echo "[0/5] DB-Sync: neue aristeus.db einspielen"
    systemctl stop aristeus-api || true
    cp /tmp/aristeus_new.db "$DATA/aristeus.db"
    chown aristeus:aristeus "$DATA/aristeus.db"
    chmod 640 "$DATA/aristeus.db"
    rm -f "$DATA/aristeus.db-shm" "$DATA/aristeus.db-wal" /tmp/aristeus_new.db
    echo "      DB eingespielt."
fi

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
