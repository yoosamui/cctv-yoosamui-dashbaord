#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SITE_TEMPLATE="$PROJECT_DIR/config/nginx-cctv-dashboard.conf"
TMP_SITE_CONF="$(mktemp)"

if [ ! -f "$SITE_TEMPLATE" ]; then
  echo "Error: missing Nginx config template at $SITE_TEMPLATE" >&2
  echo "Make sure this repo is checked out in the expected location before running this script." >&2
  exit 1
fi

trap 'rm -f "$TMP_SITE_CONF"' EXIT

echo "Installing Nginx on Raspberry Pi OS..."
sudo apt update
sudo apt install -y nginx

echo "Enabling the site config..."
sed "s|/home/pi/cctv/cctv-dashboard|$PROJECT_DIR|g" "$SITE_TEMPLATE" > "$TMP_SITE_CONF"
sudo cp "$TMP_SITE_CONF" /etc/nginx/sites-available/cctv-dashboard
sudo ln -sf /etc/nginx/sites-available/cctv-dashboard /etc/nginx/sites-enabled/cctv-dashboard

echo "Removing default site if present..."
sudo rm -f /etc/nginx/sites-enabled/default

echo "Testing Nginx config..."
sudo nginx -t

echo "Restarting Nginx..."
sudo systemctl restart nginx
sudo systemctl enable nginx

echo "Dashboard should now be available at: http://127.0.0.1:8880/"
