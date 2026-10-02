#!/usr/bin/env bash
# One-time Docker install for Ubuntu/Debian. Needs root:   sudo bash infra/docker/install-docker.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker "${SUDO_USER:-$USER}"
echo "Docker installed. Run 'newgrp docker' (or log out and in) so your user can use it without sudo."
