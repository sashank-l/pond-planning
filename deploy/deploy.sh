#!/usr/bin/env bash
# deploy.sh — Deploy pond-api to a remote box
# Usage: ./deploy.sh <user@host>
set -euo pipefail

REMOTE="${1:?Usage: $0 <user@host>}"
DEPLOY_DIR="/opt/pond-api"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Syncing code to $REMOTE:$DEPLOY_DIR"
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='contours_1m.kml' \
    "$REPO_DIR/" "$REMOTE:$DEPLOY_DIR/"

echo "==> Setting up venv and installing dependencies on remote"
ssh "$REMOTE" bash <<'EOF'
set -euo pipefail
cd /opt/pond-api

# Set up swap file if not already present (512 MB safety net)
if [ ! -f /swapfile ]; then
  echo "  Creating 512M swap file..."
  fallocate -l 512M /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
fi

# Create venv if not present
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo "  Dependencies installed. Disk usage:"
du -sh .venv/
EOF

echo "==> Installing and restarting systemd service"
ssh "$REMOTE" bash <<'EOF'
set -euo pipefail
cp /opt/pond-api/deploy/pond-api.service /etc/systemd/system/pond-api.service
systemctl daemon-reload
systemctl enable pond-api
systemctl restart pond-api
sleep 2
systemctl status pond-api --no-pager
EOF

echo "==> Smoke test"
ssh "$REMOTE" bash <<'EOF'
curl -sf http://127.0.0.1:8000/health && echo "  Health check PASSED" || echo "  Health check FAILED"
EOF

echo "==> Deployment complete!"
