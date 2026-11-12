#!/usr/bin/env bash
# Legt die TikTok-Verifizierungsdatei an:  bash /opt/orbleague/deploy/set-verify.sh <dateiname.txt> "<inhalt>"
set -euo pipefail
NAME="${1:?Dateiname, z.B. tiktokAbC123.txt}"; CONTENT="${2:?Inhalt der Datei in Anführungszeichen}"
[[ "$NAME" =~ ^tiktok[A-Za-z0-9_-]{4,80}\.txt$ ]] || { echo "Ungültiger Dateiname"; exit 1; }
printf '%s' "$CONTENT" > "/opt/orbleague/data/$NAME"
chown orbleague:orbleague "/opt/orbleague/data/$NAME"
echo "Bereit unter: $(grep '^PUBLIC_URL=' /opt/orbleague/.env | cut -d= -f2)/$NAME"
