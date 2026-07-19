# Jugendlager Tenero – Wahlsportarten

Web-App zur Anmeldung und Einteilung von Wahlsportarten im Jugendlager.

## Features

- **Teilnehmer verwalten** – Einmal anlegen, für mehrere Slots anmelden
- **4 Slots** – Dienstag, Mittwoch, Donnerstag, Freitag Nachmittag
- **Pro Slot eigene Sportarten** – Jeder Nachmittag hat sein eigenes Angebot
- **1./2./3. Wahl** – Jeder Teilnehmer wählt pro Slot 3 Präferenzen
- **Zelt-Priorität** – Pro Slot festlegen, welche Zelte bevorzugt werden
- **Auto-Assignment** – Verteilt Plätze nach Priorität + Anmeldezeitpunkt
- **Manuelle Einteilung** – Drag&Drop-ähnliche Dropdowns pro Slot
- **Konflikterkennung** – Zeigt, wer keinen Platz bekommen hat
- **CSV-Export** – Pro Slot, gruppiert nach Sportart
- **Leiter-Ansicht** – Read-only für Betreuer
- **Cross-Check** – Liste hochladen und mit Angemeldeten vergleichen

## Technik

- **Backend:** Python + Flask + SQLite
- **Frontend:** Server-gerenderte Templates (Jinja2)
- **Keine externen Abhängigkeiten** ausser Flask

## Installation

```bash
pip install -r requirements.txt
```

## Start

```bash
# Lokal (Datenbank im Projektverzeichnis)
DB_PATH="./daten/daten.db" \
ADMIN_CODE="mein-admin-code" \
LEITER_CODE="mein-leiter-code" \
python3 app.py

# Mit Docker
docker-compose up -d
```

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `DB_PATH` | `./daten/daten.db` | Pfad zur SQLite-Datenbank |
| `ADMIN_CODE` | `tenero2025` | Admin-Zugangscode |
| `LEITER_CODE` | `lager2025` | Leiter-Zugangscode (read-only) |
| `SECRET_KEY` | `tenero-wahl-sport-secret` | Flask Session-Key |
| `FLASK_DEBUG` | `0` | Debug-Mode (`1` für Entwicklung) |

## Routen

| Route | Beschreibung |
|---|---|
| `/` | Startseite – Übersicht aller Slots |
| `/teilnehmer/neu` | Neuen Teilnehmer anlegen |
| `/anmelden/<tn_id>` | Slot-Auswahl für Teilnehmer |
| `/anmelden/<tn_id>/slot/<id>` | Anmeldung für bestimmten Slot |
| `/admin` | Admin Login |
| `/admin/dashboard` | Admin Dashboard (alle Funktionen) |
| `/admin/zuteilung/<slot_id>` | Zuteilungsübersicht mit Konflikten |
| `/admin/export/<slot_id>` | CSV-Export |
| `/admin/zusammenfassung` | Gesamtübersicht |
| `/admin/crosscheck` | Listen-Vergleich |
| `/leiter` | Leiter Login |
| `/leiter/uebersicht` | Leiter-Ansicht (read-only) |

## Datenbank

Die SQLite-Datenbank (`daten.db`) wird automatisch angelegt mit:

- `slots` – Die 4 Nachmittage (Di–Fr)
- `sportarten` – Verfügbare Sportarten mit Kapazität
- `slot_sportarten` – Welche Sportart an welchem Slot
- `teilnehmer` – Angemeldete Personen
- `anmeldungen` – Anmeldungen pro Slot mit 1./2./3. Wahl
- `einteilungen` – Zuteilungen pro Slot
- `slot_zelt_priorities` – Zelt-Prioritäten pro Slot
