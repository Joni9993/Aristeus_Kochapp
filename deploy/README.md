# Deployment — Aristeus Kochapp

## Übersicht

```
Lokaler Push → GitHub (main) → GitHub Actions → SSH → deploy.sh → Server neu starten
```

**Domain:** `aristeus.bulletodyssey.com`  
**Server-Layout:**
```
/opt/aristeus/
  app/              ← git clone (dieser Repo)
    backend/
      .venv/
      .env          ← Symlink auf /opt/aristeus/.env
    frontend/
    deploy/
  data/
    aristeus.db
    backups/
  frontend/
    dist/           ← npm run build Output (von Caddy serviert)
  .env              ← Secrets (nur root lesbar)
```

---

## Ersteinrichtung (einmalig auf dem Server)

### 0. Voraussetzung: DNS
Füge in deinem Domain-Provider einen **A-Record** hinzu:
```
aristeus.bulletodyssey.com  →  <Server-IP>
```

### 1. Setup-Skript ausführen
```bash
# Auf dem Server als root/jonathan mit sudo:
wget -qO setup-server.sh https://raw.githubusercontent.com/Joni9993/Aristeus_Kochapp/main/deploy/setup-server.sh
chmod +x setup-server.sh
sudo ./setup-server.sh
```

Das Skript installiert alles automatisch (Python 3.11, Node 20, Caddy, systemd-Service).

### 2. OpenRouter API Key eintragen
```bash
sudo nano /opt/aristeus/.env
# OPENROUTER_API_KEY=sk-or-v1-...  eintragen
sudo systemctl restart aristeus-api
```

### 3. GitHub Actions einrichten (Auto-Deploy)

**a) SSH-Deploy-Key generieren (lokal auf Windows):**
```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\aristeus_deploy" -C "aristeus-deploy" -N ""
```

**b) Public Key auf den Server übertragen:**
```bash
# Den Inhalt von ~/.ssh/aristeus_deploy.pub
# auf dem Server zu jonathan's authorized_keys hinzufügen:
cat ~/.ssh/aristeus_deploy.pub | ssh jonathan@<server-ip> "cat >> ~/.ssh/authorized_keys"
```

**c) Passwordlosen sudo für deploy.sh erlauben:**
```bash
sudo visudo -f /etc/sudoers.d/aristeus-deploy
```
Folgendes eintragen:
```
jonathan ALL=(ALL) NOPASSWD: /opt/aristeus/app/deploy/deploy.sh
```

**d) GitHub Secrets setzen:**  
GitHub Repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Wert |
|--------|------|
| `SERVER_HOST` | IP-Adresse deines Servers |
| `SERVER_SSH_KEY` | Inhalt von `~/.ssh/aristeus_deploy` (privater Schlüssel) |

---

## Updates (automatisch nach Setup)

```
git push origin main
```

GitHub Actions SSHt auf den Server und ruft `deploy.sh` auf — kein manuelles Eingreifen.

## Manuelles Deployment

```bash
ssh jonathan@<server-ip>
sudo /opt/aristeus/app/deploy/deploy.sh
```

## Logs

```bash
# Backend-Logs:
sudo journalctl -u aristeus-api -f

# Caddy-Logs:
sudo journalctl -u caddy -f
sudo tail -f /var/log/caddy/aristeus.access.log

# Service-Status:
sudo systemctl status aristeus-api caddy
```

## Datenbank-Backup

```bash
sudo -u aristeus sqlite3 /opt/aristeus/data/aristeus.db ".backup /opt/aristeus/data/backups/aristeus-$(date +%F).db"
```
