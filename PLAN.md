# Umbau: Tenero Wahlsportarten → Anmeldung + Einteilung

## Neues Konzept

### Datenmodell
- **sportarten** → bleiben, nur `name` + `max_teilnehmer`
- **slots** → 4 Einträge: Dienstag, Mittwoch, Donnerstag, Freitag Nachmittag
- **teilnehmer** → Vorname, Nachname, Zelt (ihre Gruppe im Lager)
- **wahlen** → pro Teilnehmer 3 Präferenzen (1./2./3. Wahl) auf Sportarten
- **einteilungen** → Admin-Zuteilung: pro Slot + Teilnehmer → eine Sportart

### Anmeldung
- Ein Formular: Vorname + Nachname + Zelt + 1./2./3. Wahl (Dropdowns)
- Keine Beschränkung auf max_teilnehmer mehr (das ergibt bei 4 Slots keinen Sinn)

### Admin
- Übersicht aller Teilnehmer mit Zelten und Präferenzen
- Pro Slot: Tabelle zum Zuteilen (Dropdown pro Teilnehmer)
- Validierung: kein Kind doppelt, keins vergessen
- Zusammenfassung: total angemeldet, pro Slot verteilt
- Cross-Check: Liste hochladen → zeigt wer fehlt
