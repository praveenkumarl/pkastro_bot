#!/bin/bash
# deploy/install.sh
# Run once on the VPS as picoadmin to install all services.
# Usage: bash deploy/install.sh

set -e

APP_DIR="/home/picoadmin/picobot"
DEPLOY_DIR="$APP_DIR/deploy"

echo "=== PNK Astro Bot — Production Install ==="

# ── 1. Install Python deps ─────────────────────────────────────────────────
echo "[1/6] Installing Python dependencies..."
"$APP_DIR/.venv/bin/pip" install --quiet \
    fastapi uvicorn httpx python-dotenv \
    chromadb pydantic \
    rank-bm25 pymupdf \
    langchain-community langchain-text-splitters langchain-core

# ── 2. Create chroma data directory ────────────────────────────────────────
echo "[2/6] Creating ChromaDB data directory..."
mkdir -p "$APP_DIR/chroma_data"

# ── 3. Install systemd units ───────────────────────────────────────────────
echo "[3/6] Installing systemd units..."
sudo cp "$DEPLOY_DIR/chromadb.service"     /etc/systemd/system/chromadb.service
sudo cp "$DEPLOY_DIR/pnkastro-bot.service" /etc/systemd/system/pnkastro-bot.service
sudo systemctl daemon-reload

# ── 4. Install Nginx config ────────────────────────────────────────────────
echo "[4/6] Installing Nginx config..."
# Install nginx if not present
if ! command -v nginx &>/dev/null; then
    echo "    nginx not found — installing..."
    sudo apt-get update -qq
    sudo apt-get install -y nginx
fi
# Ensure sites-available / sites-enabled directories exist
sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
sudo cp "$DEPLOY_DIR/nginx.conf" /etc/nginx/sites-available/pnkastro-bot
sudo ln -sf /etc/nginx/sites-available/pnkastro-bot /etc/nginx/sites-enabled/pnkastro-bot
# Remove default site if it exists (avoids port 80 conflict)
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx

# ── 5. Enable and start services ───────────────────────────────────────────
echo "[5/6] Enabling services..."
sudo systemctl enable chromadb pnkastro-bot
sudo systemctl start chromadb
sleep 3
sudo systemctl start pnkastro-bot

# ── 6. Install health-check cron ──────────────────────────────────────────
echo "[6/6] Installing health-check cron (every 5 min)..."
CRON_JOB="*/5 * * * * curl -sf http://127.0.0.1:3000/health > /dev/null || sudo systemctl restart pnkastro-bot"
(crontab -l 2>/dev/null | grep -v pnkastro; echo "$CRON_JOB") | crontab -

echo ""
echo "=== Install complete ==="
echo "  Check status  : sudo systemctl status pnkastro-bot chromadb"
echo "  Live logs     : sudo journalctl -fu pnkastro-bot"
echo "  Test endpoint : curl -s http://localhost/health"
