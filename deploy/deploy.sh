#!/usr/bin/env bash
# deploy.sh — Deploy pond-api to a remote box
# Usage: ./deploy.sh <user@host>
set -euo pipefail

REMOTE="${1:?Usage: $0 <user@host>}"
DEPLOY_DIR="/home/student/pond_panning"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Syncing code to $REMOTE:$DEPLOY_DIR"
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' \
    "$REPO_DIR/" "$REMOTE:$DEPLOY_DIR/"

echo "==> Setting up venv and installing dependencies on remote"
ssh "$REMOTE" bash <<'EOF'
set -euo pipefail
cd /home/student/pond_panning

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
sudo cp /home/student/pond_panning/deploy/pond-api.service /etc/systemd/system/pond-api.service
sudo systemctl daemon-reload
sudo systemctl enable pond-api
sudo systemctl restart pond-api
sleep 2
sudo systemctl status pond-api --no-pager
EOF

echo "==> Smoke test on port 3209"
ssh "$REMOTE" bash <<'EOF'
curl -sf http://127.0.0.1:3209/health && echo "  Health check PASSED" || echo "  Health check FAILED"
EOF

echo "==> Deployment complete! Running on port 3209."
