#!/usr/bin/env python3
"""Setzt alle Kommentare zurück und füllt sie nur aus Zelt-Sheet 'Kommentar'-Spalte."""

import sqlite3, os, openpyxl

BASE = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE, "daten", "daten.db")
XLSX_PATH = os.path.join(BASE, "TN-Liste_Tenero 2026.xlsx")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 1. Alle Kommentare löschen
conn.execute('UPDATE teilnehmer SET kommentar = ""')
print("✅ Alle Kommentare zurückgesetzt")

# 2. Kommentare aus Zelt-Sheet
wb = openpyxl.load_workbook(XLSX_PATH)
ws_z = wb["Einteilung Zelte"]

gefunden = 0
nicht_gefunden = 0

for r in range(6, ws_z.max_row + 1):
    vorname = (ws_z.cell(row=r, column=2).value or "").strip()
    name = (ws_z.cell(row=r, column=3).value or "").strip()
    kommentar = ws_z.cell(row=r, column=7).value
    if not vorname or not name or vorname == "Vorname" or not kommentar:
        continue
    kommentar = str(kommentar).strip()

    # Exakter Match
    c = conn.execute(
        "UPDATE teilnehmer SET kommentar = ? WHERE vorname = ? AND nachname = ?",
        (kommentar, vorname, name)
    )
    if c.rowcount > 0:
        gefunden += 1
        continue

    # Fuzzy: einer der Namen ist im anderen enthalten
    for tn in conn.execute("SELECT id, vorname, nachname FROM teilnehmer").fetchall():
        tv = tn["vorname"].strip().lower()
        tnn = tn["nachname"].strip().lower()
        if (tv in vorname.lower() or vorname.lower() in tv) and \
           (tnn in name.lower() or name.lower() in tnn):
            conn.execute("UPDATE teilnehmer SET kommentar = ? WHERE id = ?", (kommentar, tn["id"]))
            gefunden += 1
            break
    else:
        nicht_gefunden += 1

conn.commit()

print(f"✅ Kommentare gesetzt: {gefunden}")
if nicht_gefunden:
    print(f"❌ Nicht gefunden: {nicht_gefunden}")

print()
c = conn.execute("SELECT vorname, nachname, kommentar FROM teilnehmer WHERE kommentar != ''")
for r in c.fetchall():
    print(f"  {r['vorname']} {r['nachname']}: {r['kommentar']}")

print(f"\nTotal mit Kommentar: {c.rowcount}")
conn.close()
