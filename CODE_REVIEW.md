# Code-Review: Jugendlager Tenero – Wahlsportarten

## 🟢 Gut gemacht

| Aspekt | Bewertung |
|---|---|
| **SQL-Parametrisierung** | ✅ Alle Queries mit `?`-Platzhaltern – keine SQL-Injection |
| **DB-Normalisierung** | ✅ Sauberes Schema mit Foreign Keys, ON DELETE CASCADE |
| **Jinja2 Auto-Escaping** | ✅ XSS-Schutz durch Template-Engine |
| **CRUD komplett** | ✅ Anlegen/Löschen für alle Entitäten vorhanden |
| **Funktionstrennung** | ✅ Klare Trennung der Routes |

## 🔴 Sicherheitsprobleme

| Problem | Schwere | Fix |
|---|---|---|
| **Admin-Code hardcoded** (`tenero2025`) | 🔴 Hoch | Muss aus Umgebungsvariable kommen |
| **Debug-Mode aktiv** (`debug=True`) | 🔴 Hoch | Flask-Debugger erlaubt Code-Ausführung |
| **Admin-Code als Query-Parameter** | 🟡 Mittel | Steht in Logs, Browser-Verlauf, Referer-Headern |
| **Kein CSRF-Schutz** | 🟡 Mittel | POST-Endpoints ohne Token |
| **Kein Rate-Limiting** | 🟡 Mittel | Anmeldungen können gespamt werden |
| **Exception-Handling zu breit** | 🟡 Mittel | `except Exception` schluckt zu viel |

## 🟡 Performance & Code-Qualität

| Problem | Details |
|---|---|
| **N+1 Queries** | `admin_dashboard` macht separate Queries pro Slot für Sportarten, Prioritäten, Einteilungen |
| **Imports in Funktionen** | `import csv, io` und `from urllib.parse import unquote` in Funktionskörpern |
| **Keine Session-Verwaltung** | Admin-Status wird nicht in Sessions gespeichert |
| **DB-Verbindung pro Request** | Kein Connection-Pooling (für SQLite vertretbar) |

## 🟡 Fehlende Features

| Feature | Warum wichtig |
|---|---|
| **Kapazität editieren** | Sportart-Kapazität kann nur beim Anlegen gesetzt werden |
| **Anmeldung bearbeiten** | Nur löschen möglich, kein Edit |
| **Teilnehmer suchen** | Bei 150+ TN unübersichtlich |
| **Batch-Export pro Sportart** | CSV hat nur eine Gesamtliste |

## 🔧 Gemachte Optimierungen

- ✅ Admin-Code aus Umgebungsvariable (`ADMIN_CODE`)
- ✅ Debug-Mode deaktiviert für Produktion
- ✅ CSV-Export: pro Sportart gruppiert mit Trennzeilen
- ✅ UI-Redesign: erwachsener, cleaner (Slate-Farben)
- ✅ Performance: DB-Queries optimiert
- ✅ Doku: README.md
