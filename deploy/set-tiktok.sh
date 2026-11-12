#!/usr/bin/env bash
# Trägt TikTok Client Key + Secret in die .env ein (ohne dass sie im Chat landen) und startet neu.
#   bash /opt/orbleague/deploy/set-tiktok.sh
set -euo pipefail
ENV=/opt/orbleague/.env
read -r -p "TikTok Client Key: " KEY
read -r -s -p "TikTok Client Secret (Eingabe unsichtbar): " SECRET; echo
[ -n "$KEY" ] && [ -n "$SECRET" ] || { echo "Abgebrochen: leer."; exit 1; }
sed -i '/^TIKTOK_CLIENT_KEY=/d; /^TIKTOK_CLIENT_SECRET=/d' "$ENV"
printf 'TIKTOK_CLIENT_KEY=%s\nTIKTOK_CLIENT_SECRET=%s\n' "$KEY" "$SECRET" >> "$ENV"
chmod 600 "$ENV"; chown orbleague:orbleague "$ENV"
systemctl restart orbleague
echo "Gespeichert. Jetzt im Dashboard auf 'TikTok verbinden' tippen."
