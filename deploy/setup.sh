#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║           LibLocker – Raspberry Pi One-Command Setup            ║
# ║                                                                  ║
# ║  Usage (run from inside the project folder):                     ║
# ║    bash deploy/setup.sh                                          ║
# ╚══════════════════════════════════════════════════════════════════╝
set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()      { echo -e "${GREEN}  ✓${NC}  $*"; }
warn()    { echo -e "${YELLOW}  ⚠${NC}  $*"; }
err()     { echo -e "${RED}  ✗${NC}  $*"; exit 1; }
section() { echo -e "\n${BLUE}${BOLD}━━━  $*  ━━━${NC}"; }
ask()     { read -rp "  $* [y/N] " _ans; [[ "${_ans:-n}" =~ ^[Yy]$ ]]; }

# ── Paths (always resolved relative to this script's parent) ──────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"   # project root
APP_USER="liblocker"
VENV_DIR="$APP_DIR/.venv"
# Who actually ran the command (even under sudo)
RUN_AS="${SUDO_USER:-$(whoami)}"

# ── Detect boot config path (Pi OS Bookworm vs older) ────────────
if   [ -f /boot/firmware/config.txt ]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    BOOT_CONFIG="/boot/config.txt"
else
    warn "Cannot find /boot/firmware/config.txt or /boot/config.txt – skipping interface setup"
    BOOT_CONFIG=""
fi

# ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}${BOLD}║          LibLocker — Raspberry Pi Setup                      ║${NC}"
echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Project : ${BOLD}$APP_DIR${NC}"
echo -e "  Run by  : ${BOLD}$RUN_AS${NC}"
echo ""

# ─────────────────────────────────────────────────────────────────
section "0 / Pre-flight checks"

# Must be run with sudo (or as root)
if [ "$EUID" -ne 0 ]; then
    err "This script must be run with sudo:  sudo bash deploy/setup.sh"
fi

# Warn if not a Raspberry Pi (allow continuing)
if ! grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
    warn "This does not appear to be a Raspberry Pi."
    ask "Continue anyway?" || exit 0
fi

ok "Pre-flight checks passed"

# ─────────────────────────────────────────────────────────────────
section "1 / System user '$APP_USER'"

if id "$APP_USER" &>/dev/null; then
    ok "User '$APP_USER' already exists"
else
    useradd --system --create-home --shell /bin/bash "$APP_USER"
    ok "Created system user '$APP_USER'"
fi

# ─────────────────────────────────────────────────────────────────
section "2 / Hardware interfaces (SPI · I2C · Camera)"

enable_config() {
    local param="$1"
    local label="$2"
    if [ -z "$BOOT_CONFIG" ]; then return; fi
    if grep -q "^${param}=off" "$BOOT_CONFIG" 2>/dev/null; then
        sed -i "s/^${param}=off/${param}=on/" "$BOOT_CONFIG"
        ok "$label enabled  (reboot required)"
    elif ! grep -q "^${param}=on" "$BOOT_CONFIG" 2>/dev/null; then
        echo "${param}=on" >> "$BOOT_CONFIG"
        ok "$label enabled  (reboot required)"
    else
        ok "$label already enabled"
    fi
}

enable_config "dtparam=spi"    "SPI (RC522 RFID)"
enable_config "dtparam=i2c_arm" "I2C (MCP23017 relay boards)"
enable_config "start_x"        "Camera"

REBOOT_NEEDED=false
if [ -n "$BOOT_CONFIG" ] && grep -q "(reboot required)" /dev/stdin < <(enable_config "dtparam=spi" "" 2>&1) 2>/dev/null; then
    REBOOT_NEEDED=true
fi

# ─────────────────────────────────────────────────────────────────
section "3 / System packages"

apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    i2c-tools \
    libatlas-base-dev \
    libjpeg-dev libopenjp2-7 \
    nginx \
    git \
    build-essential 2>&1 | grep -E "^(Reading|Building|Get|Hit|Err|Fetched|OK)" || true

ok "System packages installed"

# ─────────────────────────────────────────────────────────────────
section "4 / Hardware group membership"

add_group() {
    local grp="$1"
    local target="$2"
    if getent group "$grp" &>/dev/null; then
        usermod -aG "$grp" "$target" 2>/dev/null && ok "$target → $grp" || true
    else
        warn "Group '$grp' does not exist – skipping"
    fi
}

for TARGET in "$APP_USER" "$RUN_AS"; do
    # gpio / spi  – RC522 RFID reader
    add_group gpio  "$TARGET"
    add_group spi   "$TARGET"
    # i2c         – MCP23017 relay boards
    add_group i2c   "$TARGET"
    # video       – Pi Camera
    add_group video "$TARGET"
done

# ─────────────────────────────────────────────────────────────────
section "5 / Python virtual environment"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    ok "Virtual environment created at $VENV_DIR"
else
    ok "Virtual environment already exists"
fi

# Activate venv for the rest of setup
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

pip install --quiet --upgrade pip setuptools wheel

# Install project dependencies
echo "  Installing Python packages (this may take a minute)..."
pip install --quiet -r "$APP_DIR/requirements.txt" || \
    warn "Some packages failed – check manually: pip install -r requirements.txt"

# Always ensure gunicorn is present
pip install --quiet gunicorn
ok "Python packages installed  (gunicorn confirmed)"

# ─────────────────────────────────────────────────────────────────
section "6 / Directory layout & permissions"

mkdir -p "$APP_DIR/instance/evidence"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod -R 755 "$APP_DIR"
chmod 750 "$APP_DIR/instance"         # restrict DB directory
chmod 700 "$APP_DIR/instance/evidence" # restrict evidence photos
[ -f "$APP_DIR/.env" ] && chmod 640 "$APP_DIR/.env"

ok "Permissions set"

# ─────────────────────────────────────────────────────────────────
section "7 / Environment configuration (.env)"

if [ -f "$APP_DIR/.env" ]; then
    ok ".env already exists – keeping your existing configuration"
    warn "Remember to set a strong SECRET_KEY and ADMIN_TOKEN if you haven't already"
else
    cat > "$APP_DIR/.env" << 'ENVEOF'
# ===================================================================
# LIBLOCKER CONFIGURATION (.env)
# Edit these values before starting the service.
# ===================================================================

# --- CORE FLASK ---
FLASK_ENV=production
SECRET_KEY=CHANGE-THIS-TO-A-STRONG-RANDOM-VALUE
DATABASE_PATH=instance/liblocker.sqlite
ADMIN_TOKEN=CHANGE-THIS-ADMIN-TOKEN

# --- HARDWARE MODE ---
HARDWARE_MODE=PI
ACTIVE_LOCKER_COUNT=24

# --- LOCKER LEVEL CONFIGURATION ---
UPPER_LEVEL_LOCKERS=1,2,3,4,5,6,13,14,15,16,17,18
LOWER_LEVEL_LOCKERS=7,8,9,10,11,12,19,20,21,22,23,24

# --- RFID CONFIGURATION ---
RFID_READ_TIMEOUT_SECONDS=8
RFID_READ_INTERVAL_SECONDS=0.15
RFID_BACKGROUND_READ_TIMEOUT_SECONDS=0.1
RFID_SCAN_COOLDOWN_SECONDS=2.0
HF_RFID_ENABLED=true

# --- GPIO / RELAY CONTROL ---
GPIO_ACTIVE_HIGH=true
GPIO_PULSE_DURATION=0.5
GPIO_DEPOSIT_OPEN_SECONDS=10
GPIO_RETRIEVE_OPEN_SECONDS=10
GPIO_USE_I2C=true
GPIO_I2C_DRIVER=relay_board
GPIO_I2C_ADDRESS=0x20
GPIO_I2C_BUS=1
# Three MCP23017 modules: 0x20=lockers 1-8, 0x21=lockers 9-16, 0x22=lockers 17-24
GPIO_RELAY_I2C_ADDRESSES=0x20,0x21,0x22

# --- CAMERA ---
CAMERA_ENABLED=true
EVIDENCE_PHOTOS_DIR=instance/evidence
CAMERA_RESOLUTION_W=1280
CAMERA_RESOLUTION_H=720

# --- SESSION MANAGEMENT ---
SESSION_TIMEOUT_MINUTES=120
SESSION_CLEANUP_INTERVAL_SECONDS=300

# --- FEATURE FLAGS ---
ENABLE_SESSION_CLEANUP=true
ENABLE_ERROR_RECOVERY=true
ENABLE_ADMIN_UNLOCK=true
ENVEOF
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    chmod 640 "$APP_DIR/.env"
    ok ".env created – EDIT IT before starting the service"
    warn "Open: nano $APP_DIR/.env   →  set SECRET_KEY and ADMIN_TOKEN"
fi

# ─────────────────────────────────────────────────────────────────
section "8 / Database initialisation"

cd "$APP_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/python3" - << 'PYEOF'
import sys, os
sys.path.insert(0, os.getcwd())
try:
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.db import init_db
        init_db()
    print("  ✓  Database ready")
except Exception as e:
    print(f"  ⚠  DB init warning: {e}")
    print("     Run manually: source .venv/bin/activate && python3 -c \"from app import create_app; app=create_app()\"")
PYEOF

# ─────────────────────────────────────────────────────────────────
section "9 / Systemd service"

SERVICE_FILE="/etc/systemd/system/liblocker.service"

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
    --threads 8 \\
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

# Hardware group access
SupplementaryGroups=gpio spi i2c video

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable liblocker
ok "Systemd service installed and enabled (auto-starts on boot)"

# ─────────────────────────────────────────────────────────────────
section "10 / Nginx reverse proxy"

NGINX_CONF="/etc/nginx/sites-available/liblocker"

cat > "$NGINX_CONF" << NGINXEOF
upstream liblocker_app {
    server 127.0.0.1:5000;
    keepalive 8;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;
    client_max_body_size 10M;

    access_log /var/log/nginx/liblocker-access.log;
    error_log  /var/log/nginx/liblocker-error.log;

    # Static assets served directly by Nginx (faster than Flask).
    # no-cache = revalidate each request so JS/CSS deploys take effect immediately.
    location /assets/ {
        alias $APP_DIR/assets/;
        add_header Cache-Control "no-cache";
        access_log off;
    }

    # All other requests forwarded to Gunicorn
    location / {
        proxy_pass         http://liblocker_app;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_redirect     off;
        proxy_connect_timeout 30s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;
    }

    # Block sensitive files
    location ~ /\.(env|git|venv) { deny all; return 403; }
    location ~ /instance/        { deny all; return 403; }
}
NGINXEOF

# Enable site, disable default
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/liblocker
rm -f /etc/nginx/sites-enabled/default

if nginx -t 2>/dev/null; then
    systemctl enable nginx
    systemctl restart nginx
    ok "Nginx configured and restarted"
else
    warn "Nginx config test failed – run: sudo nginx -t"
fi

# ─────────────────────────────────────────────────────────────────
section "11 / I2C device check (MCP23017)"

if command -v i2cdetect &>/dev/null; then
    echo "  Scanning I2C bus 1 for MCP23017 modules..."
    i2cdetect -y 1 2>/dev/null || warn "I2C scan failed – is I2C enabled and wired?"
else
    warn "i2c-tools not found – cannot scan for MCP23017"
fi

# ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}${BOLD}║                  Setup Complete!                             ║${NC}"
echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}${BOLD}  NEXT STEPS${NC}"
echo ""

NEED_REBOOT=false
if [ -n "$BOOT_CONFIG" ] && grep -q "dtparam=spi=on\|dtparam=i2c_arm=on" "$BOOT_CONFIG" 2>/dev/null; then
    NEED_REBOOT=true
fi

if $NEED_REBOOT; then
echo -e "  ${YELLOW}1.${NC} Reboot (required to activate SPI/I2C):"
echo -e "     ${BOLD}sudo reboot${NC}"
echo ""
fi

echo -e "  ${YELLOW}$( $NEED_REBOOT && echo 2 || echo 1 ).${NC} Edit .env with your secret values:"
echo -e "     ${BOLD}nano $APP_DIR/.env${NC}"
echo -e "     → Set  SECRET_KEY  and  ADMIN_TOKEN"
echo -e "     → Generate: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
echo ""
echo -e "  ${YELLOW}$( $NEED_REBOOT && echo 3 || echo 2 ).${NC} Verify I2C modules (MCP23017 at 0x20, 0x21, 0x22):"
echo -e "     ${BOLD}i2cdetect -y 1${NC}"
echo ""
echo -e "  ${YELLOW}$( $NEED_REBOOT && echo 4 || echo 3 ).${NC} Start the service:"
echo -e "     ${BOLD}sudo systemctl start liblocker${NC}"
echo ""
echo -e "  ${YELLOW}$( $NEED_REBOOT && echo 5 || echo 4 ).${NC} Check service status and logs:"
echo -e "     ${BOLD}sudo systemctl status liblocker${NC}"
echo -e "     ${BOLD}sudo journalctl -u liblocker -f${NC}"
echo ""
echo -e "  ${YELLOW}$( $NEED_REBOOT && echo 6 || echo 5 ).${NC} Access the kiosk:"
echo -e "     ${BOLD}http://$(hostname -I | awk '{print $1}')${NC}"
echo -e "     ${BOLD}http://$(hostname).local${NC}"
echo ""
echo -e "  Admin login:  ${BOLD}http://$(hostname).local/admin${NC}"
echo ""
echo -e "${GREEN}${BOLD}  HARDWARE TEST COMMANDS (run as $RUN_AS after reboot)${NC}"
echo -e "  Test RFID reader  : ${BOLD}source $VENV_DIR/bin/activate && python3 $APP_DIR/scripts/test-rfid.py${NC}"
echo -e "  Test GPIO relay   : ${BOLD}python3 $APP_DIR/scripts/test-gpio.py${NC}"
echo -e "  Test I2C modules  : ${BOLD}i2cdetect -y 1${NC}"
echo ""
