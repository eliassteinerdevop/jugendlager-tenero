# Jugendlager Tenero – Wahlsportarten

## Kurzanleitung für die Lagerleitung

---

## 1. Zugänge

| Bereich | Link | Code |
|---|---|---|
| **Admin** (alle Funktionen) | `tenero.chruezfalsch.ch/admin` | `tenero2025` |
| **Leiter** (nur anschauen) | `tenero.chruezfalsch.ch/leiter` | `lager2025` |
| **Anmeldung** (für Teilnehmer) | `tenero.chruezfalsch.ch/teilnehmer/neu` | – |

---

## 2. Ablauf

### Schritt 1: Sportarten einrichten
Im Admin-Dashboard unter «Neue Sportart» alle Sportarten anlegen und pro Slot (Tag) zuweisen.

### Schritt 2: Teilnehmer anmelden
Jeder Teilnehmer legt einmal sein Konto an (Name + Zelt) und meldet sich dann pro Nachmittag separat mit 1./2./3. Wahl an.

### Schritt 3: Slots freischalten
Nur **freigeschaltete** Slots werden bei der Anmeldung angezeigt.
- Erst **Dienstag** freischalten → alle melden sich an
- Dann **Mittwoch** freischalten → alle melden sich an
- usw.

### Schritt 4: Einteilung
Pro Slot per **Auto-Assignment** automatisch verteilen (nach Zelt-Priorität + Anmeldezeitpunkt) oder manuell anpassen.

---

## 3. Wichtige Funktionen im Admin

| Funktion | Beschreibung |
|---|---|
| **Slots verwalten** | Slots nach und nach freischalten |
| **Sportarten pro Slot** | Festlegen, was an welchem Tag angeboten wird |
| **Zelt-Prioritäten** | Pro Tag festlegen, welches Zelt Vorrang hat (1 = höchste) |
| **Auto-Assignment** | Verteilt Plätze automatisch nach Priorität + Zeitpunkt |
| **Zuteilung & Export** | Zeigt Konflikte (wer keinen Platz hat) + CSV-Export pro Sportart |
| **Cross-Check** | Liste hochladen und prüfen, wer noch fehlt |

---

## 4. Export pro Sportart

Im Admin auf «Zuteilung & Export» → «CSV exportieren».
Die CSV ist nach Sportarten gruppiert – ideal zum Ausdrucken für die Betreuer.

---

## 5. Datensicherung

Nach jeder Anmeldung wird automatisch ein Backup erstellt:
`/backups/daten_YYYY-MM-TT_HH-MM-SS.db`
(maximal 50 Backups, älteste werden gelöscht)

---

## 6. Hinweise

- Die App ist für den internen Gebrauch im Lager-Netzwerk
- Admin-Code (`tenero2025`) und Leiter-Code (`lager2025`) können bei Bedarf geändert werden
- Keine sensiblen Personen-Daten erfassen (keine Adressen, keine AHV-Nummern)
- Bei Fragen: Entwickler kontaktieren
