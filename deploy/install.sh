#!/usr/bin/env bash
# Einmal-Installation auf Ubuntu 24.04 (als root ausführen):  bash deploy/install.sh orbleague.deinedomain.de
set -euo pipefail
DOMAIN="${1:?Domain angeben, z.B. orbleague.deinedomain.de}"
apt-get update
apt-get install -y python3 python3-pil python3-numpy ffmpeg caddy
id orbleague >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin orbleague
mkdir -p /opt/orbleague && cp -r . /opt/orbleague/ && chown -R orbleague:orbleague /opt/orbleague
cd /opt/orbleague
[ -f .env ] || { cp .env.example .env; sed -i "s#https://orbleague.deinedomain.de#https://$DOMAIN#" .env;
  sed -i "s#bitte-ein-langes-passwort#$(head -c 18 /dev/urandom | base64 | tr -d '/+=')#" .env; }
chmod 600 .env && chown orbleague:orbleague .env
sed -i "s/^WEB_HOST=.*//" .env; echo "WEB_HOST=127.0.0.1" >> .env
sed "s/orbleague.deinedomain.de/$DOMAIN/" deploy/Caddyfile > /etc/caddy/Caddyfile
cp deploy/orbleague.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now orbleague && systemctl reload caddy
echo; echo "Fertig. Dashboard: https://$DOMAIN  (Benutzer: admin, Passwort steht in /opt/orbleague/.env)"
grep DASHBOARD_PASSWORD /opt/orbleague/.env
