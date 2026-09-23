#!/bin/bash
# LibLocker – (Re)install systemd service only
# Run as root:  sudo bash deploy/setup-systemd.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
APP_USER="liblocker"
VENV_DIR="$APP_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/liblocker.service"

[ "$EUID" -ne 0 ] && echo "Run with sudo" && exit 1

echo "Installing liblocker systemd service..."

cat > "$SERVICE_FILE" << SVCEOF
[Unit]
Description=LibLocker RFID Locker Management System
After=network.target

[Service]
Type=exec
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env

ExecStart=$VENV_DIR/bin/gunicorn \\
    --workers 1 \\
    --threads 4 \\
    --bind 127.0.0.1:5000 \\
    --timeout 120 \\
    --access-logfile - \\
    wsgi:app

Restart=on-failure
RestartSec=5
TimeoutStartSec=30
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=liblocker

SupplementaryGroups=gpio spi i2c input video

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable liblocker
echo "✓ Service installed and enabled"
echo ""
read -rp "  Start service now? [y/N] " ans
[[ "${ans:-n}" =~ ^[Yy]$ ]] && systemctl start liblocker && systemctl status liblocker
echo ""
echo "Commands:"
echo "  sudo systemctl start liblocker"
echo "  sudo systemctl status liblocker"
echo "  sudo journalctl -u liblocker -f"
