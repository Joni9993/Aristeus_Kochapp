#!/usr/bin/env bash
# First-time server setup for Aristeus Kochapp.
# Run as root on a fresh Ubuntu 22.04+ server:
#   wget -qO setup-server.sh https://raw.githubusercontent.com/Joni9993/Aristeus_Kochapp/main/deploy/setup-server.sh
#   chmod +x setup-server.sh && sudo ./setup-server.sh
set -euo pipefail

REPO="https://github.com/Joni9993/Aristeus_Kochapp.git"
APP=/opt/aristeus/app
DATA=/opt/aristeus/data
FRONTEND=/opt/aristeus/frontend

echo "=== 1/8  System packages ==="
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git curl

# Node.js 20 LTS
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -q nodejs
fi

# Caddy
if ! command -v caddy &>/dev/null; then
    apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y -q caddy
fi

echo "=== 2/8  System user 'aristeus' ==="
id aristeus &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin aristeus

echo "=== 3/8  Directory structure ==="
mkdir -p "$DATA/backups" "$FRONTEND/dist"
chown -R aristeus:aristeus /opt/aristeus

echo "=== 4/8  Clone repository ==="
if [ -d "$APP/.git" ]; then
    echo "  Repo already cloned, skipping."
else
    sudo -u aristeus git clone "$REPO" "$APP"
fi

echo "=== 5/8  Python venv + deps ==="
cd "$APP/backend"
if [ ! -d ".venv" ]; then
    sudo -u aristeus python3 -m venv .venv
fi
sudo -u aristeus .venv/bin/pip install --upgrade pip --quiet
sudo -u aristeus .venv/bin/pip install -e . --quiet

echo "=== 6/8  Production .env ==="
if [ ! -f /opt/aristeus/.env ]; then
    cp "$APP/backend/.env.example" /opt/aristeus/.env
    chown root:aristeus /opt/aristeus/.env
    chmod 640 /opt/aristeus/.env
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|change-me-to-a-long-random-string|$SECRET|g" /opt/aristeus/.env
    sed -i "s|APP_ENV=development|APP_ENV=production|g" /opt/aristeus/.env
    sed -i "s|DATABASE_URL=sqlite:///./data/aristeus.db|DATABASE_URL=sqlite:////opt/aristeus/data/aristeus.db|g" /opt/aristeus/.env
    sed -i "s|ALLOWED_ORIGINS=http://localhost:5173|ALLOWED_ORIGINS=https://aristeus.bulletodyssey.com|g" /opt/aristeus/.env
    sed -i "s|PUBLIC_FRONTEND_URL=http://localhost:5173|PUBLIC_FRONTEND_URL=https://aristeus.bulletodyssey.com|g" /opt/aristeus/.env
    echo ""
    echo "  *** WICHTIG: Trage deinen OPENROUTER_API_KEY in /opt/aristeus/.env ein! ***"
    echo "  nano /opt/aristeus/.env"
    echo ""
fi
# Symlink .env into backend dir so pydantic + alembic find it
ln -sf /opt/aristeus/.env "$APP/backend/.env"

echo "=== 7/8  DB migrations ==="
cd "$APP/backend"
sudo -u aristeus .venv/bin/alembic upgrade head

echo "=== 8/8  Frontend build ==="
cd "$APP/frontend"
sudo -u aristeus npm ci --silent
sudo -u aristeus npm run build
cp -r dist/. "$FRONTEND/dist/"
chown -R aristeus:aristeus "$FRONTEND/dist"

echo "=== Systemd service ==="
cp "$APP/deploy/aristeus-api.service.example" /etc/systemd/system/aristeus-api.service
systemctl daemon-reload
systemctl enable --now aristeus-api

echo "=== Caddy ==="
cp "$APP/deploy/Caddyfile.example" /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy

echo ""
echo "========================================"
echo " Setup abgeschlossen!"
echo " DNS A-Record: aristeus.bulletodyssey.com → $(curl -s ifconfig.me)"
echo " Nächster Schritt: OPENROUTER_API_KEY in /opt/aristeus/.env setzen"
echo " Dann: sudo systemctl restart aristeus-api"
echo "========================================"
