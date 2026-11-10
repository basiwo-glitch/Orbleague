# ORB LEAGUE – autonomer TikTok-Creator

Ein Multi-Agenten-System, das selbstständig Videos für den TikTok-Account **ORB LEAGUE** plant, produziert, prüft, hochlädt, auswertet und daraus lernt. Läuft auf einem eigenen Server, gesteuert über ein Dashboard im Browser (iPhone/iPad-tauglich).

Strategie, 10 bewertete Konzepte und Branding: siehe [STRATEGIE.md](STRATEGIE.md).

## Was das System tut

```
Trend-Agent ─► Creative-Agent ─► Video-Agent (24 Seeds vorab simulieren, spannendsten wählen)
   ▲                                   │
   │                              Script-Agent (Hook + Einblendungen an echte Ereignisse gekoppelt)
   │                                   │
Strategy-Agent ◄─ Analytics-Agent ◄─ Publishing-Agent ◄─ Quality-Agent ◄─ Video-Agent (rendern)
 (Bandit-Lernen)   (Display API)      (Content Posting API)  (13 Prüfungen)
```

Alle Agenten teilen sich eine SQLite-Datenbank. Jeder Schritt speichert seinen Zustand – nach Neustart oder Absturz geht es genau dort weiter (getestet). Fehler landen im Log (Dashboard → Logs) und blockieren nicht den Rest.

| Agent | Aufgabe |
|---|---|
| Trend | Saison-/Event-Kalender, eigene Performance, Fan-Wünsche; optional KI-Twist |
| Creative | Besetzung & Storyline aus der Liga-Tabelle (Champion, Underdog, Rivalen, Rematches) |
| Script | Hook (5 Stile), Ereignis-Einblendungen, Endkarte, Caption + Hashtags; nur wahre Aussagen |
| Video | Physik-Simulation, Seed-Auswahl nach Spannung, Rendering 1080×1920 mit synthetischem Ton |
| Quality | Auflösung, Codec, Länge, Lautstärke, Schwarzbilder, Spannung, Texte, Wiederholungen |
| Publishing | Zeitplan, Upload, Statusabfrage, Retries, Tageslimits |
| Analytics | Aufrufe/Likes/Kommentare/Shares/Follower; Bewertung jedes Videos nach 48 h |
| Strategy | Thompson-Sampling über Formate, Varianten und Hook-Stile; pausiert Schwaches, erfindet neue Varianten, passt die Frequenz an |

Kosten: Rendering läuft auf deinem Server (0 € pro Video). KI ist optional, mit Tagesbudget (Standard 0,50 $). Ohne API-Key arbeitet das System mit eingebauten Vorlagen.

## Einrichtung (einmalig, ca. 45 Minuten + TikTok-Wartezeit)

### 1. TikTok-Account anlegen
In der TikTok-App: neuer Account, Name **ORB LEAGUE**, Handle z. B. `@orbleague` (falls vergeben: `@orb.league`, `@orbleague.tv`), Profilbild `assets/profile.png`, Bio aus STRATEGIE.md.

### 2. Server
Ein kleiner VPS mit Ubuntu 24.04 (2 vCPU, 4 GB RAM reichen; ca. 5–8 €/Monat). Dazu eine (Sub-)Domain, die auf die Server-IP zeigt – kostenlos z. B. über DuckDNS.

```bash
# auf dem Server, als root, im entpackten Projektordner:
bash deploy/install.sh orbleague.deinedomain.de
```
Das Skript installiert ffmpeg, Python-Pakete, Caddy (automatisches HTTPS) und einen systemd-Dienst, der nach Neustarts automatisch weiterläuft. Am Ende zeigt es das Dashboard-Passwort.

Ab jetzt produziert das System bereits Videos (sichtbar im Dashboard), lädt aber noch nichts hoch.

### 3. TikTok-Entwickler-App (für das Hochladen)
1. Auf developers.tiktok.com mit deinem TikTok-Account anmelden → *Manage apps* → *Connect an app*.
2. Produkte hinzufügen: **Login Kit**, **Content Posting API** (dort *Direct Post* aktivieren) und die Display-API-Scopes.
3. Scopes: `user.info.basic`, `user.info.stats`, `video.list`, `video.upload`, `video.publish`.
4. Redirect URI: `https://DEINE-DOMAIN/auth/callback` · Privacy Policy: `https://DEINE-DOMAIN/privacy` · Terms: `https://DEINE-DOMAIN/terms`
5. Client Key + Secret in `/opt/orbleague/.env` eintragen, dann `systemctl restart orbleague`.
6. Bis TikTok die App freigibt: im **Sandbox**-Bereich deinen eigenen Account als Testnutzer eintragen (Ablauf laut aktueller TikTok-Doku prüfen).
7. Im Dashboard oben auf **TikTok verbinden** tippen und bestätigen. Das Token erneuert sich danach selbst (gültig bis zu 365 Tage).

### 4. Veröffentlichungsmodus wählen (Dashboard → Steuerung)
- **Entwurf in TikTok-App** (Standard, ohne Audit nutzbar): Zur geplanten Zeit landet das Video in deinem TikTok-Posteingang; du fügst die Caption ein (im Dashboard antippen → kopieren) und postest. Ca. 10 Sekunden pro Video.
- **Direkt veröffentlichen**: Vor dem TikTok-Audit landen Videos nur privat („Nur ich“) – gut zum Testen. Für öffentliches Direktposten musst du das Audit beantragen (Demo-Video des Ablaufs, dauert typischerweise Wochen; private Einzelnutzer-Tools können abgelehnt werden). TikTok verlangt außerdem, dass du jeden Post vor der Veröffentlichung siehst und bestätigst – dafür gibt es die Freigabe-Buttons bzw. „Alle fertigen freigeben“. Die Option „Automatisch“ existiert, verstößt aber womöglich gegen die Entwicklerrichtlinien – Nutzung auf eigenes Risiko.

### 5. Optional: Claude API
`ANTHROPIC_API_KEY` in `.env` eintragen → bessere Captions, Strategie-Notizen auf Deutsch, Trend-Twists, neue Spielvarianten. Kosten werden pro Aufruf erfasst und im Dashboard angezeigt.

## Bedienung

- **Übersicht:** Kennzahlen, aktuelle Strategie, nächste Videos mit Vorschau, Wachstumsphasen, Kosten, Stopp-Knopf.
- **Videos:** alle Folgen mit Status, Qualitätsprüfung, Kennzahlen, Freigeben/Ablehnen. Abgelehnte Folgen werden automatisch ersetzt (und aus der Liga-Tabelle zurückgerechnet).
- **Strategie:** was funktioniert (Score je Format/Variante/Hook), Trend-Briefing.
- **Liga:** Tabelle und Charaktere.
- **Steuerung:** Videos pro Tag, Uhrzeiten, Modus, Fan-Wünsche (z. B. häufige Kommentare – die API liefert keine Kommentartexte).
- **Logs:** alles, was die Agenten tun, inkl. Fehlern.

Tipp: Dashboard in Safari öffnen → Teilen → „Zum Home-Bildschirm“ – dann wirkt es wie eine App.

## Ehrliche Grenzen
- **Retention/Wiedergabedauer** liefert die Display API nicht. Das System nutzt Shares- und Kommentarraten als Ersatzsignal. Wer genauer will: Business-Account + TikTok Business API (Erweiterung möglich).
- **Globale Trend-Daten** gibt es für normale Entwickler nicht offiziell; Scraping wäre ein Verstoß gegen die Nutzungsbedingungen.
- **Öffentliches Vollautomatik-Posten** hängt am TikTok-Audit.
- Reichweite ist nicht garantierbar; das System maximiert die Chancen und lernt aus echten Zahlen.

## Lokal testen (ohne TikTok)
```bash
TIKTOK_MOCK=1 python3 tools/e2e_test.py     # plant, rendert 3 Videos, simuliert Upload + Auswertung
TIKTOK_MOCK=1 DASHBOARD_PASSWORD=test python3 -m viralai run   # Dashboard auf :8080
```

## Projektstruktur
```
viralai/render/   formats.py (Physik + Director), episode.py (Bild/Ton), engine.py, audio.py
viralai/agents/   trend, creative, script, video, quality, publishing, analytics, strategy
viralai/          orchestrator.py, web.py (Dashboard), tiktok.py, llm.py, db.py, config.py, brand.py
deploy/           install.sh, orbleague.service, Caddyfile
samples/          die drei Testvideos
```
