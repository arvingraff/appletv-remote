#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Apple TV Remote — Raspberry Pi 4 Setup Script
# Run once on your Pi:  bash pi_setup.sh
# ─────────────────────────────────────────────────────────────────
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="/etc/systemd/system/appletv-remote.service"
TUNNEL_SERVICE="/etc/systemd/system/cloudflared-appletv.service"
PORT=9876
PYTHON=python3

echo "────────────────────────────────────────"
echo " Apple TV Remote – Pi Setup"
echo "────────────────────────────────────────"

# ── 1. System packages ────────────────────────────────────────────
echo "[1/5] Installing system packages…"
# Remove any stale cloudflare apt source that may cause update to fail
sudo rm -f /etc/apt/sources.list.d/cloudflared.list /usr/share/keyrings/cloudflare-main.gpg
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv libavahi-compat-libdnssd-dev

# ── 2. Python venv + dependencies ────────────────────────────────
echo "[2/5] Setting up Python virtual environment…"
cd "$REPO_DIR"
$PYTHON -m venv .venv-pi
source .venv-pi/bin/activate
pip install --quiet --upgrade pip
pip install --quiet pyatv flask

# ── 3. Systemd service ────────────────────────────────────────────
echo "[3/5] Installing systemd service…"
PYTHON_BIN="$REPO_DIR/.venv-pi/bin/python"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Apple TV Remote Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
ExecStart=$PYTHON_BIN $REPO_DIR/appletv_server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable appletv-remote.service
sudo systemctl restart appletv-remote.service
echo "   ✅ Service running — check: sudo systemctl status appletv-remote"

# ── 4. Get Pi IP ──────────────────────────────────────────────────
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "────────────────────────────────────────"
echo " ✅ Setup complete!"
echo ""
echo " 📱 iPhone remote (home WiFi only):"
echo "    http://${PI_IP}:${PORT}"
echo ""

# ── 5. Optional: Cloudflare Tunnel (anywhere access) ─────────────
echo "[5/5] Cloudflare Tunnel (optional — lets you use the remote from ANYWHERE)"
read -r -p " Install cloudflared for remote access? [y/N] " CF_ANSWER
if [[ "$CF_ANSWER" =~ ^[Yy]$ ]]; then
    echo "   Installing cloudflared…"
    # Remove any old broken apt sources first
    sudo rm -f /etc/apt/sources.list.d/cloudflared.list /usr/share/keyrings/cloudflare-main.gpg
    ARCH=$(dpkg --print-architecture)
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
    echo "   Downloading from: $CF_URL"
    curl -L --fail "$CF_URL" -o /tmp/cloudflared.deb && sudo dpkg -i /tmp/cloudflared.deb && rm /tmp/cloudflared.deb

    # Create a quick tunnel (no login needed — generates a random URL)
    sudo tee "$TUNNEL_SERVICE" > /dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel for Apple TV Remote
After=appletv-remote.service
Requires=appletv-remote.service

[Service]
Type=simple
User=$USER
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:${PORT} --no-autoupdate
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable cloudflared-appletv.service
    sudo systemctl restart cloudflared-appletv.service

    echo ""
    echo "   ✅ Cloudflare Tunnel started!"
    echo "   Wait ~10s then run this to get your public URL:"
    echo "   sudo journalctl -u cloudflared-appletv -n 30 | grep trycloudflare"
    echo "   It will look like: https://something-random.trycloudflare.com"
    echo ""
    echo "   ⚡ Bookmark that URL and use it from ANYWHERE — no VPN needed!"
fi

echo "────────────────────────────────────────"
echo " Done! Logs: sudo journalctl -u appletv-remote -f"
echo "────────────────────────────────────────"
