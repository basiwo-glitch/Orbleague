#!/usr/bin/env bash
# Neue Version holen und neu starten:  bash /opt/orbleague/deploy/update.sh
set -euo pipefail
cd /opt/orbleague
git pull --ff-only
chown -R orbleague:orbleague /opt/orbleague
systemctl restart orbleague
echo "Aktualisiert auf $(git log -1 --format='%h %s')"
