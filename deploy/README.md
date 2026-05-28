# Deployment auf dem VPS

Vorlagen — werden auf dem Server angepasst und an die richtigen Pfade kopiert.

## Layout auf dem VPS

```
/opt/aristeus/
  app/                 # git pull dieses Repos (backend/)
    .venv/             # python venv
  frontend/dist/       # Output von `npm run build`
  data/
    aristeus.db
    backups/
  .env                 # secrets, root-only readable
```

## Erste Einrichtung (Skizze)

```bash
# system user
sudo useradd --system --create-home --shell /usr/sbin/nologin aristeus

# code
sudo mkdir -p /opt/aristeus
sudo chown aristeus:aristeus /opt/aristeus
sudo -u aristeus git clone <repo-url> /opt/aristeus/app

# python
cd /opt/aristeus/app/backend
sudo -u aristeus python3.11 -m venv .venv
sudo -u aristeus .venv/bin/pip install -e .

# frontend
cd /opt/aristeus/app/frontend
sudo -u aristeus npm ci
sudo -u aristeus npm run build
sudo cp -r dist /opt/aristeus/frontend/

# secrets
sudo cp /opt/aristeus/app/backend/.env.example /opt/aristeus/.env
sudo chmod 600 /opt/aristeus/.env
sudo nano /opt/aristeus/.env   # set real values

# systemd + caddy
sudo cp deploy/aristeus-api.service.example /etc/systemd/system/aristeus-api.service
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl enable --now aristeus-api
sudo systemctl reload caddy
```

## Updates (zukünftig: ein `deploy.sh`)

```bash
cd /opt/aristeus/app
sudo -u aristeus git pull
cd backend && sudo -u aristeus .venv/bin/pip install -e .
cd ../frontend && sudo -u aristeus npm ci && sudo -u aristeus npm run build
sudo cp -r dist/* /opt/aristeus/frontend/dist/
sudo systemctl restart aristeus-api
```
