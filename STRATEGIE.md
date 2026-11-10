# ORB LEAGUE – Content-Strategie

## 1. Ausgangslage (Recherche, Nov 2026)

- **Was die Plattform belohnt:** Wiedergabe bis zum Ende, Rewatches, Kommentare und Shares. Formate mit offenem Ausgang („Wer gewinnt?“) erzeugen alle vier Signale gleichzeitig: Zuschauer bleiben bis zur Auflösung, tippen vorher in den Kommentaren und schauen erneut, um zu sehen, ob ihr Tipp hätte gewinnen können.
- **Code-generierte Physik-Videos** (Ball-in-Ring, Marble-Races, Pong-Wars) sind seit Jahren eine stabile, international funktionierende Kategorie – sprachunabhängig, „satisfying“, gut automatisierbar. Die Kategorie ist aber voll von anonymen Einzel-Clips ohne Wiedererkennung.
- **Plattformregeln:** TikTok verlangt ein Label für realistisch wirkende KI-Inhalte; reine Code-Animationen ohne realistische Personen/Szenen fallen nach den verfügbaren Leitfäden nicht darunter (im Dashboard trotzdem schaltbar). Massenhaft gleichförmige, „unoriginelle“ Inhalte werden in der Reichweite gedrosselt – deshalb Varianz, Serienlogik und eine Qualitätsprüfung.
- **API-Grenzen (wichtig für die Erwartung):** Über die offizielle Content Posting API posten unauditierte Apps nur privat; öffentliches Direktposten erfordert ein Audit durch TikTok. Die Display API liefert Aufrufe/Likes/Kommentare/Shares und Follower – aber **keine Wiedergabedauer/Retention und keine Kommentartexte**, und es gibt für normale Entwickler keine offizielle Trend-API.

## 2. Zehn Account-Konzepte, bewertet (1–10, höher = besser)

| # | Konzept | Viralität | Wenig Konkurrenz | Automatisierbar | Originalität | Langfr. Wachstum | Σ |
|---|---|---|---|---|---|---|---|
| 1 | **ORB LEAGUE** – Physik-Wettkämpfe mit 8 festen Charakteren, Liga-Tabelle, Rivalitäten, Staffeln | 8 | 6 | 10 | 8 | 9 | **41** |
| 2 | Länder-Pixelkriege mit echten Daten | 8 | 5 | 9 | 6 | 6 | 34 |
| 3 | Kommentar-Abenteuer (Zuschauer entscheiden die Story) | 6 | 8 | 5 | 8 | 7 | 34 |
| 4 | „Satisfying Algorithms“ – Sortier-/Suchalgorithmen mit Sound | 6 | 6 | 10 | 6 | 5 | 33 |
| 5 | Wahrnehmungs-Tests & generierte optische Täuschungen | 7 | 5 | 8 | 6 | 5 | 31 |
| 6 | KI-vs-KI-Debatten (zwei Avatare streiten absurde Fragen) | 6 | 6 | 6 | 7 | 5 | 30 |
| 7 | Absurde Statistiken als Kinetic Typography | 6 | 5 | 8 | 5 | 5 | 29 |
| 8 | 45-Sekunden-Mysteries (KI-Bilder + Stimme) | 8 | 3 | 6 | 5 | 6 | 28 |
| 9 | „Ein Tag als …“ Mikro-Geschichten mit KI-Illustration | 6 | 3 | 6 | 5 | 5 | 25 |
| 10 | 3D-Größenvergleiche „What if …“ | 7 | 3 | 5 | 4 | 5 | 24 |

Ausschlussgründe der Verfolger: #2 erzeugt nationalistische Kommentar-Schlachten (Moderationsrisiko); #3 ist mangels Kommentar-API nicht autonom betreibbar; #8–#10 sind überlaufen, brauchen teure Bild-/Stimmgenerierung und das KI-Label.

## 3. Gewinner: ORB LEAGUE

**Idee:** Eine fortlaufende Sport-Liga für 8 Kugel-Charaktere (BLAZE, CRUSH, VOLT, VENOM, FROST, COBALT, NOVA, CORAL) mit Persönlichkeit. Jede Folge ist ein Wettkampf, den **ausschließlich die Physik entscheidet** – kein Ergebnis ist geskriptet. Siege fließen in eine echte Tabelle (Siege/Niederlagen, Elo), daraus entstehen Champion-, Underdog- und Rivalitäts-Storylines.

**Warum das funktioniert**
- Bewährter Kern (satisfying Simulation, offener Ausgang) + **eigener Serien-Layer** → Grund zu folgen statt nur einmal zu schauen.
- Sprachunabhängig → international.
- 100 % eigene Rechte: Grafik, Animation und Ton werden per Code erzeugt. Keine Stockfootage, keine Fremdmusik.
- Kosten pro Video ≈ 0 (CPU auf dem eigenen Server). KI-Kosten nur für Texte/Strategie, mit Tagesbudget.

**Marke**
- Name: **ORB LEAGUE** · Handle-Kandidaten: `@orbleague`, `@orb.league`, `@orbleague.tv`, `@theorbleague`
- Bio: `8 orbs. 1 league. Zero scripts. 🟠🔵🟣 Physics decides who wins – you pick the next fight 👇`
- Profilbild: `assets/profile.png` (Champion FROST vor den Rivalen BLAZE und NOVA im goldenen Liga-Ring)
- Look: Nachtblau/Violett, Neon-Kugeln mit Gesichtern, Liga-Gold als Akzent, Fonts Inter Black / Poppins
- Zielgruppe: 13–34, international, Fans von Games, Sport-Wetten-Spannung ohne Geld, „satisfying“-Content

**Formate (Start)** – je mit mehreren Varianten, die der Strategy-Agent testet
1. **Escape** – Kugeln springen in einem rotierenden Ring, das Tor öffnet sich nach 3 s; wer zuerst rauskommt, gewinnt.
2. **Clash** – Kampf mit Lebensbalken, kritische Treffer, Power-Ups, Sudden Death mit schrumpfender Arena.
3. **Territory** – Farbkrieg auf einem Raster, Countdown, knappe Prozent-Entscheidungen.

**Retention-Bausteine in jedem Video**
- Bewegung ab Frame 1, Hook-Text in den ersten 0,35 s, Charakter-Namen zum „Pick your orb“.
- Vorab-Simulation von 24 Seeds, Auswahl des spannendsten Laufs (knappes Ende, Führungswechsel, Beinahe-Ausbrüche) – das Ergebnis bleibt echt.
- Einblendungen exakt bei echten Ereignissen („CRITICAL HIT!“, „FINAL TWO“, „SO CLOSE…“).
- Endkarte mit Saison-Bilanz und Frage für Kommentare („Who should fight VOLT next?“).

## 4. Wachstumsplan

| Phase | Ziel | Fokus |
|---|---|---|
| 1 | System läuft, 30 Videos | 3 Videos/Tag, alle Formate & Hook-Stile gleichmäßig testen |
| 2 | 1.000 Follower | Gewinner-Formate häufiger, Staffel-Story („Wer wird Champion von Season 1?“) |
| 3 | 10.000 Follower | Neue Varianten erfolgreicher Formate, Rivalitäts-Serien, Saison-Finale als Event |
| 4 | 100.000 Follower | Neue Formate (Algorithmen-Race, Marble-Run), 3–4 Videos/Tag, Live-Turniere erwägen |
| 5 | International skalieren | Zweitkanäle (YouTube Shorts/Reels mit gleicher Pipeline), Merch der Charaktere |

Die Zahlen sind Ziele, keine Garantien.
