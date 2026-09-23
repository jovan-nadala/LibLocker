#!/bin/bash
# LibLocker – (Re)install Nginx reverse proxy only
# Run as root:  sudo bash deploy/setup-nginx.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONF="/etc/nginx/sites-available/liblocker"

[ "$EUID" -ne 0 ] && echo "Run with sudo" && exit 1

command -v nginx &>/dev/null || apt-get install -y nginx

echo "Configuring Nginx for LibLocker..."

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

    location /assets/ {
        alias $APP_DIR/assets/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
    }

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

    location ~ /\.(env|git|venv) { deny all; return 403; }
    location ~ /instance/        { deny all; return 403; }
}
NGINXEOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/liblocker
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl enable nginx && systemctl restart nginx
echo "✓ Nginx configured and restarted"
echo "  Access: http://$(hostname -I | awk '{print $1}')"
