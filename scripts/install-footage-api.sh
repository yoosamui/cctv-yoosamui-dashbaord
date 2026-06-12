#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_TEMPLATE="$PROJECT_DIR/config/footage-api.service"
RUN_USER="${SUDO_USER:-$(id -un)}"
TMP_UNIT="$(mktemp)"

if [ ! -f "$SERVICE_TEMPLATE" ]; then
  echo "Error: missing service template at $SERVICE_TEMPLATE" >&2
  exit 1
fi

trap 'rm -f "$TMP_UNIT"' EXIT

echo "Installing footage-api systemd service..."
echo "  Project dir: $PROJECT_DIR"
echo "  Run as user: $RUN_USER"

sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__RUN_USER__|$RUN_USER|g" \
    "$SERVICE_TEMPLATE" > "$TMP_UNIT"

sudo cp "$TMP_UNIT" /etc/systemd/system/footage-api.service
sudo systemctl daemon-reload
sudo systemctl enable footage-api.service
sudo systemctl restart footage-api.service

echo "Done. Check status with: sudo systemctl status footage-api.service"
echo "Verify the API: curl -s -o /dev/null -w '%{http_code}\\n' 'http://127.0.0.1:8881/api/footage?query=today'"
