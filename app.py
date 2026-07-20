#!/usr/bin/env python3
"""
Jugendlager Tenero – Wahlsportarten Anmeldung + Einteilung
Flask + SQLite
Pro Slot eigene Sportarten, separate Anmeldung, Auto-Assignment.
Zelt-Priorisierung pro Slot + Slots freischaltbar.
"""

import sqlite3
import os
import csv
import io
import shutil
from datetime import datetime
from urllib.parse import unquote
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, Response, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tenero-wahl-sport-secret")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "daten", "daten.db"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(os.path.dirname(__file__), "backups"))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "tenero2025")
LEITER_CODE = os.environ.get("LEITER_CODE", "lager2025")
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

# ─── Context Processor für Nav-Login-Status ─────────────────
@app.context_processor
def inject_auth_status():
    return {
        "is_admin_logged_in": session.get("admin_logged_in", False),
        "is_leiter_logged_in": session.get("leiter_logged_in", False),
    }


def _log_anmeldung(anmeldung_id, teilnehmer_id, slot_id, action, wahl1_id=None, wahl2_id=None, wahl3_id=None):
    """Loggt eine Änderung an einer Anmeldung."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO anmeldungen_log (anmeldung_id, teilnehmer_id, slot_id, action, wahl1_id, wahl2_id, wahl3_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (anmeldung_id, teilnehmer_id, slot_id, action, wahl1_id, wahl2_id, wahl3_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _create_backup():
    """Erstellt ein Backup der Datenbank mit Zeitstempel."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = os.path.join(BACKUP_DIR, f"daten_{timestamp}.db")
        shutil.copy2(DB_PATH, backup_path)
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
        while len(backups) > 50:
            os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
    except Exception:
        pass


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sportarten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_teilnehmer INTEGER NOT NULL DEFAULT 20
        );

        CREATE TABLE IF NOT EXISTS teilnehmer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vorname TEXT NOT NULL,
            nachname TEXT NOT NULL,
            zelt TEXT NOT NULL,
            erstellt_um TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS slot_sportarten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            sportart_id INTEGER NOT NULL,
            FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
            FOREIGN KEY (sportart_id) REFERENCES sportarten(id) ON DELETE CASCADE,
            UNIQUE(slot_id, sportart_id)
        );

        CREATE TABLE IF NOT EXISTS anmeldungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teilnehmer_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            wahl1_id INTEGER NOT NULL,
            wahl2_id INTEGER NOT NULL,
            wahl3_id INTEGER NOT NULL,
            erstellt_um TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (teilnehmer_id) REFERENCES teilnehmer(id) ON DELETE CASCADE,
            FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
            FOREIGN KEY (wahl1_id) REFERENCES sportarten(id),
            FOREIGN KEY (wahl2_id) REFERENCES sportarten(id),
            FOREIGN KEY (wahl3_id) REFERENCES sportarten(id),
            UNIQUE(teilnehmer_id, slot_id)
        );

        CREATE TABLE IF NOT EXISTS einteilungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            teilnehmer_id INTEGER NOT NULL,
            sportart_id INTEGER NOT NULL,
            FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
            FOREIGN KEY (teilnehmer_id) REFERENCES teilnehmer(id) ON DELETE CASCADE,
            FOREIGN KEY (sportart_id) REFERENCES sportarten(id) ON DELETE CASCADE,
            UNIQUE(slot_id, teilnehmer_id)
        );

        CREATE TABLE IF NOT EXISTS slot_zelt_priorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            zelt_name TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 99,
            FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
            UNIQUE(slot_id, zelt_name)
        );

        CREATE TABLE IF NOT EXISTS anmeldungen_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anmeldung_id INTEGER,
            teilnehmer_id INTEGER NOT NULL,
            slot_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            wahl1_id INTEGER,
            wahl2_id INTEGER,
            wahl3_id INTEGER,
            geaendert_um TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            geaendert_von TEXT NOT NULL DEFAULT 'web'
        );
    """)

    # Migration: slots-Tabelle mit aktiv & reihenfolge
    cursor = conn.execute("PRAGMA table_info(slots)")
    cols = {row["name"] for row in cursor.fetchall()}

    if "name" not in cols:
        # Tabelle existiert noch nicht – komplett anlegen
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                reihenfolge INTEGER NOT NULL,
                aktiv INTEGER NOT NULL DEFAULT 0
            );
        """)
    else:
        if "aktiv" not in cols:
            conn.execute("ALTER TABLE slots ADD COLUMN aktiv INTEGER NOT NULL DEFAULT 0")
        if "reihenfolge" not in cols:
            conn.execute("ALTER TABLE slots ADD COLUMN reihenfolge INTEGER NOT NULL DEFAULT 0")

    # Migration: zusätzliche Sportarten-Spalten
    sport_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sportarten)")}
    for col, coltype in [("treffpunkt_zeit", "TEXT NOT NULL DEFAULT ''"),
                          ("treffpunkt_ort", "TEXT NOT NULL DEFAULT ''"),
                          ("material", "TEXT NOT NULL DEFAULT ''"),
                          ("leitung", "TEXT NOT NULL DEFAULT ''"),
                          ("ausschluss_hauptsportarten", "TEXT NOT NULL DEFAULT ''")]:
        if col not in sport_cols:
            conn.execute(f"ALTER TABLE sportarten ADD COLUMN {col} {coltype}")

    # Migration: zusätzliche Teilnehmer-Spalten
    tn_cols = {row["name"] for row in conn.execute("PRAGMA table_info(teilnehmer)")}
    for col, coltype in [("anrede", "TEXT NOT NULL DEFAULT ''"),
                          ("kommentar", "TEXT NOT NULL DEFAULT ''"),
                          ("schwimmen", "TEXT NOT NULL DEFAULT ''"),
                          ("medikamente", "TEXT NOT NULL DEFAULT ''"),
                          ("hauptsportart", "TEXT NOT NULL DEFAULT ''"),
                          ("geburtsdatum", "TEXT NOT NULL DEFAULT ''"),
                          ("verletzt", "INTEGER NOT NULL DEFAULT 0")]:
        if col not in tn_cols:
            conn.execute(f"ALTER TABLE teilnehmer ADD COLUMN {col} {coltype}")

    # Default-Slots anlegen falls leer
    vorhanden = conn.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
    if vorhanden == 0:
        for i, name in enumerate(["Dienstag", "Mittwoch", "Donnerstag", "Freitag Nachmittag"], 1):
            conn.execute("INSERT INTO slots (name, reihenfolge, aktiv) VALUES (?, ?, ?)",
                        (name, i, 1 if i == 1 else 0))  # Nur Dienstag standardmässig aktiv

    conn.commit()
    conn.close()

# ─── Startseite ────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("anmelden_start"))

# ─── Alte /anmelden-URL umleiten ───────────────────────────────

@app.route("/anmelden", methods=["GET", "POST"])
def anmelden_start():
    if request.method == "POST":
        vorname = request.form.get("vorname", "").strip()
        nachname = request.form.get("nachname", "").strip()
        zelt = request.form.get("zelt", "").strip()

        if not vorname or not nachname or not zelt:
            flash("Bitte Vorname, Nachname und Zelt ausfüllen.", "danger")
            return render_template("anmelden.html")

        conn = get_db()
        tn = conn.execute(
            "SELECT id, vorname, nachname, zelt, anrede, kommentar, schwimmen, medikamente, hauptsportart, geburtsdatum "
            "FROM teilnehmer "
            "WHERE LOWER(vorname) = LOWER(?) AND LOWER(nachname) = LOWER(?) AND LOWER(zelt) = LOWER(?)",
            (vorname, nachname, zelt)
        ).fetchone()
        conn.close()

        if tn:
            return redirect(url_for("anmelden_slot_auswahl", tn_id=tn["id"]))
        else:
            flash("❌ Kein Teilnehmer mit diesen Angaben gefunden. Bist du sicher, dass du registriert bist?", "warning")
            return render_template("anmelden.html")

    return render_template("anmelden.html")

# ─── Teilnehmer erstellen (einmalig) ──────────────────────────

@app.route("/teilnehmer/neu", methods=["GET", "POST"])
def teilnehmer_neu():
    if request.method == "POST":
        vorname = request.form.get("vorname", "").strip()
        nachname = request.form.get("nachname", "").strip()
        zelt = request.form.get("zelt", "").strip()
        anrede = request.form.get("anrede", "").strip()
        geburtsdatum = request.form.get("geburtsdatum", "").strip()
        kommentar = request.form.get("kommentar", "").strip()
        schwimmen = request.form.get("schwimmen", "").strip()
        medikamente = request.form.get("medikamente", "").strip()

        if not vorname or not nachname or not zelt:
            flash("Bitte Vorname, Nachname, Geburtsdatum und Zelt ausfüllen.", "danger")
            return render_template("teilnehmer_neu.html")

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO teilnehmer (vorname, nachname, zelt, anrede, geburtsdatum, kommentar, schwimmen, medikamente) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vorname, nachname, zelt, anrede, geburtsdatum, kommentar, schwimmen, medikamente))
            conn.commit()
            tn_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            flash(f"Teilnehmer {vorname} {nachname} angelegt! ✅", "success")
            conn.close()
            return redirect(url_for("anmelden_slot_auswahl", tn_id=tn_id))
        except Exception as e:
            conn.close()
            flash(f"Fehler: {e}", "danger")
            return render_template("teilnehmer_neu.html")

    return render_template("teilnehmer_neu.html")

# ─── API: Teilnehmer-Suche (Auto-Vervollständigung) ──────────

from flask import jsonify

@app.route("/api/teilnehmer/suche")
def api_teilnehmer_suche():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT id, vorname, nachname, zelt, anrede, kommentar, schwimmen, medikamente, hauptsportart, geburtsdatum "
        "FROM teilnehmer "
        "WHERE vorname LIKE ? OR nachname LIKE ? "
        "ORDER BY nachname, vorname LIMIT 15",
        (f"%{q}%", f"%{q}%")
    ).fetchall()
    conn.close()
    return jsonify([{
        "id": r["id"],
        "vorname": r["vorname"],
        "nachname": r["nachname"],
        "zelt": r["zelt"],
        "anrede": r["anrede"],
        "kommentar": r["kommentar"],
        "schwimmen": r["schwimmen"],
        "medikamente": r["medikamente"],
        "hauptsportart": r["hauptsportart"],
        "geburtsdatum": r["geburtsdatum"]
    } for r in rows])

# ─── Slot-Auswahl für Anmeldung ────────────────────────────────

@app.route("/anmelden/<int:tn_id>")
def anmelden_slot_auswahl(tn_id):
    conn = get_db()
    tn = conn.execute("SELECT * FROM teilnehmer WHERE id = ?", (tn_id,)).fetchone()
    if not tn:
        conn.close()
        flash("Teilnehmer nicht gefunden.", "danger")
        return redirect(url_for("index"))

    if tn["verletzt"]:
        conn.close()
        flash("🩹 Du bist als verletzt/krank markiert und kannst dich nicht anmelden. Bitte melde dich bei der Lagerleitung.", "warning")
        return render_template("anmelden_slot_auswahl.html", tn=tn, slots=[], already=set(), slot_sportarten={})

    # NUR aktive Slots anzeigen
    slots = conn.execute("SELECT * FROM slots WHERE aktiv = 1 ORDER BY reihenfolge").fetchall()

    already = set()
    for row in conn.execute("SELECT slot_id FROM anmeldungen WHERE teilnehmer_id = ?", (tn_id,)).fetchall():
        already.add(row["slot_id"])

    slot_sportarten = {}
    for slot in slots:
        rows = conn.execute("""
            SELECT s.id, s.name, s.max_teilnehmer, s.ausschluss_hauptsportarten
            FROM sportarten s
            JOIN slot_sportarten ss ON ss.sportart_id = s.id
            WHERE ss.slot_id = ?
            ORDER BY s.name
        """, (slot["id"],)).fetchall()
        slot_sportarten[slot["id"]] = rows

    conn.close()

    return render_template("anmelden_slot_auswahl.html",
                         tn=tn,
                         slots=slots,
                         already=already,
                         slot_sportarten=slot_sportarten)

# ─── Anmeldung für einen Slot ──────────────────────────────────

@app.route("/anmelden/<int:tn_id>/slot/<int:slot_id>", methods=["GET", "POST"])
def anmelden_fuer_slot(tn_id, slot_id):
    conn = get_db()
    tn = conn.execute("SELECT * FROM teilnehmer WHERE id = ?", (tn_id,)).fetchone()
    slot = conn.execute("SELECT * FROM slots WHERE id = ? AND aktiv = 1", (slot_id,)).fetchone()

    if not tn or not slot:
        conn.close()
        flash("Teilnehmer oder Slot nicht gefunden (vielleicht noch nicht freigeschaltet).", "danger")
        return redirect(url_for("index"))

    if tn["verletzt"]:
        conn.close()
        flash("🩹 Du bist als verletzt/krank markiert und kannst dich nicht anmelden. Bitte melde dich bei der Lagerleitung.", "danger")
        return redirect(url_for("anmelden_slot_auswahl", tn_id=tn_id))

    existing = conn.execute(
        "SELECT id, wahl1_id, wahl2_id, wahl3_id FROM anmeldungen WHERE teilnehmer_id = ? AND slot_id = ?",
        (tn_id, slot_id)
    ).fetchone()

    sportarten = conn.execute("""
        SELECT s.id, s.name, s.max_teilnehmer, s.ausschluss_hauptsportarten
        FROM sportarten s
        JOIN slot_sportarten ss ON ss.sportart_id = s.id
        WHERE ss.slot_id = ?
        ORDER BY s.name
    """, (slot_id,)).fetchall()

    if not sportarten:
        conn.close()
        flash(f"Für {slot['name']} gibt es noch keine Sportarten.", "warning")
        return redirect(url_for("anmelden_slot_auswahl", tn_id=tn_id))

    if request.method == "POST":
        wahl1 = request.form.get("wahl1", "").strip()
        wahl2 = request.form.get("wahl2", "").strip()
        wahl3 = request.form.get("wahl3", "").strip()

        if not wahl1 or not wahl2 or not wahl3:
            flash("Bitte alle 3 Wahlen ausfüllen.", "warning")
            conn.close()
            return render_template("anmelden_fuer_slot.html", tn=tn, slot=slot, sportarten=sportarten)

        # Prüfen: gleiche Sportart mehrmals gewählt?
        if len({wahl1, wahl2, wahl3}) < 3:
            flash("❌ Du kannst eine Sportart nicht mehrmals wählen. Bitte 3 verschiedene auswählen.", "danger")
            conn.close()
            return render_template("anmelden_fuer_slot.html", tn=tn, slot=slot, sportarten=sportarten)

        # Prüfen ob eine gewählte Sportart die Hauptsportart ausschliesst
        import re
        for label, wahl in [("1. Wahl", wahl1), ("2. Wahl", wahl2), ("3. Wahl", wahl3)]:
            gewaehlte = conn.execute("SELECT * FROM sportarten WHERE id = ?", (int(wahl),)).fetchone()
            if gewaehlte and gewaehlte["ausschluss_hauptsportarten"] and tn["hauptsportart"]:
                ausgeschlossen = [h.strip().lower().rstrip(';,')
                                 for h in re.split(r'[;,]+', gewaehlte["ausschluss_hauptsportarten"])]
                tn_haupt = tn["hauptsportart"].lower()
                for aus in ausgeschlossen:
                    if aus and (aus in tn_haupt or tn_haupt in aus):
                        flash(f"❌ {gewaehlte['name']} ({label}) ist nicht erlaubt für deine Hauptsportart ({tn['hauptsportart']}).", "danger")
                        conn.close()
                        return render_template("anmelden_fuer_slot.html", tn=tn, slot=slot, sportarten=sportarten)

        if existing:
            conn.execute(
                "UPDATE anmeldungen SET wahl1_id=?, wahl2_id=?, wahl3_id=? WHERE id=?",
                (int(wahl1), int(wahl2), int(wahl3), existing["id"])
            )
            _log_anmeldung(existing["id"], tn_id, slot_id, "update", int(wahl1), int(wahl2), int(wahl3))
            flash(f"Anmeldung für {slot['name']} aktualisiert! ✅", "success")
        else:
            conn.execute(
                "INSERT INTO anmeldungen (teilnehmer_id, slot_id, wahl1_id, wahl2_id, wahl3_id) VALUES (?, ?, ?, ?, ?)",
                (tn_id, slot_id, int(wahl1), int(wahl2), int(wahl3))
            )
            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            _log_anmeldung(new_id, tn_id, slot_id, "insert", int(wahl1), int(wahl2), int(wahl3))
            flash(f"Anmeldung für {slot['name']} erfolgreich! ✅", "success")
        conn.commit()
        conn.close()
        _create_backup()
        return redirect(url_for("anmelden_slot_auswahl", tn_id=tn_id))

    conn.close()
    return render_template("anmelden_fuer_slot.html", tn=tn, slot=slot, sportarten=sportarten, existing=existing)

# ─── Anmeldung löschen ─────────────────────────────────────────

@app.route("/anmeldung/loeschen/<int:anmeldung_id>", methods=["POST"])
def anmeldung_loeschen(anmeldung_id):
    code = request.form.get("code", request.args.get("code", ""))
    conn = get_db()
    a = conn.execute("SELECT teilnehmer_id, slot_id, wahl1_id, wahl2_id, wahl3_id FROM anmeldungen WHERE id = ?", (anmeldung_id,)).fetchone()
    if a:
        _log_anmeldung(anmeldung_id, a["teilnehmer_id"], a["slot_id"], "delete", a["wahl1_id"], a["wahl2_id"], a["wahl3_id"])
    conn.execute("DELETE FROM anmeldungen WHERE id = ?", (anmeldung_id,))
    conn.execute("DELETE FROM einteilungen WHERE teilnehmer_id = ? AND slot_id = ?",
                 (a["teilnehmer_id"], a["slot_id"]))
    conn.commit()
    conn.close()
    flash("Anmeldung + Zuteilung gelöscht.", "info")
    if code == ADMIN_CODE:
        return redirect(url_for("admin_dashboard", code=code))
    return redirect(url_for("index"))

# ─── Admin ─────────────────────────────────────────────────────

def _admin_code_from_request():
    return request.args.get("code", request.form.get("code", ""))

def check_admin():
    if session.get("admin_logged_in"):
        return session.get("admin_code")
    code = _admin_code_from_request()
    if code == ADMIN_CODE:
        session["admin_logged_in"] = True
        session["admin_code"] = code
        return code
    return None

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        code = request.form.get("code", "")
        if code == ADMIN_CODE:
            session["admin_logged_in"] = True
            session["admin_code"] = code
            flash("Admin-Zugang freigeschaltet ✅", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Falscher Admin-Code", "danger")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    sportarten = conn.execute("SELECT * FROM sportarten ORDER BY name").fetchall()
    slots = conn.execute("SELECT * FROM slots ORDER BY reihenfolge").fetchall()

    # Slot-Sportarten
    slot_sportarten = {}
    for slot in slots:
        rows = conn.execute("""
            SELECT s.id, s.name, s.max_teilnehmer FROM sportarten s
            JOIN slot_sportarten ss ON ss.sportart_id = s.id
            WHERE ss.slot_id = ?
            ORDER BY s.name
        """, (slot["id"],)).fetchall()
        slot_sportarten[slot["id"]] = {r["id"]: r["name"] for r in rows}

    # Kapazität pro Slot
    slot_capacity = {}
    for slot in slots:
        total = 0
        belegt = 0
        details = []
        for sid, sname in slot_sportarten[slot["id"]].items():
            row = conn.execute("SELECT max_teilnehmer FROM sportarten WHERE id = ?", (sid,)).fetchone()
            max_tn = row["max_teilnehmer"] if row else 0
            zugeteilt = conn.execute(
                "SELECT COUNT(*) as c FROM einteilungen WHERE slot_id = ? AND sportart_id = ?",
                (slot["id"], sid)
            ).fetchone()["c"]
            total += max_tn
            belegt += zugeteilt
            details.append({"id": sid, "name": sname, "max": max_tn, "belegt": zugeteilt})
        slot_capacity[slot["id"]] = {"total": total, "belegt": belegt, "frei": total - belegt, "details": details}

    # Zelt-Prioritäten pro Slot
    slot_priorities = {}
    for slot in slots:
        rows = conn.execute("""
            SELECT zelt_name, priority FROM slot_zelt_priorities
            WHERE slot_id = ? ORDER BY priority ASC
        """, (slot["id"],)).fetchall()
        slot_priorities[slot["id"]] = [dict(r) for r in rows]

    # Alle vorhandenen Zelte (aus Teilnehmern)
    zelte = [r["zelt"] for r in conn.execute("SELECT DISTINCT zelt FROM teilnehmer ORDER BY zelt").fetchall()]

    teilnehmer = conn.execute("SELECT * FROM teilnehmer ORDER BY zelt, nachname, vorname").fetchall()

    anmeldungen = conn.execute("""
        SELECT a.id, a.teilnehmer_id, a.slot_id, a.erstellt_um,
               a.wahl1_id, a.wahl2_id, a.wahl3_id,
               s1.name as wahl1_name, s2.name as wahl2_name, s3.name as wahl3_name,
               t.vorname, t.nachname, t.zelt,
               sl.name as slot_name, sl.reihenfolge
        FROM anmeldungen a
        JOIN teilnehmer t ON t.id = a.teilnehmer_id
        JOIN slots sl ON sl.id = a.slot_id
        JOIN sportarten s1 ON s1.id = a.wahl1_id
        JOIN sportarten s2 ON s2.id = a.wahl2_id
        JOIN sportarten s3 ON s3.id = a.wahl3_id
        ORDER BY sl.reihenfolge, a.erstellt_um
    """).fetchall()

    einteilungen = {}
    for slot in slots:
        rows = conn.execute("""
            SELECT e.teilnehmer_id, e.sportart_id, s.name as sportart_name
            FROM einteilungen e
            JOIN sportarten s ON s.id = e.sportart_id
            WHERE e.slot_id = ?
        """, (slot["id"],)).fetchall()
        einteilungen[slot["id"]] = {r["teilnehmer_id"]: r for r in rows}

    # Nicht angemeldete pro Slot
    angemeldete_ids_pro_slot = {}
    for slot in slots:
        ids = [r["teilnehmer_id"] for r in conn.execute(
            "SELECT DISTINCT teilnehmer_id FROM anmeldungen WHERE slot_id = ?", (slot["id"],)).fetchall()]
        angemeldete_ids_pro_slot[slot["id"]] = set(ids)

    nicht_angemeldet = {}
    for slot in slots:
        nicht_angemeldet[slot["id"]] = [
            tn for tn in teilnehmer
            if tn["id"] not in angemeldete_ids_pro_slot[slot["id"]]
        ]

    # Lookup: teilnehmer_id -> anmeldung (für Einteilungstabelle)
    anmeldungen_lookup = {a["teilnehmer_id"]: a for a in anmeldungen}

    conn.close()

    return render_template("admin_dashboard.html",
                         sportarten=sportarten,
                         slots=slots,
                         teilnehmer=teilnehmer,
                         anmeldungen=anmeldungen,
                         anmeldungen_lookup=anmeldungen_lookup,
                         slot_sportarten=slot_sportarten,
                         slot_priorities=slot_priorities,
                         zelte=zelte,
                         einteilungen=einteilungen,
                         nicht_angemeldet=nicht_angemeldet,
                         angemeldete_ids_pro_slot=angemeldete_ids_pro_slot,
                         slot_capacity=slot_capacity,
                         code=code)

# ─── Admin: Teilnehmer-Übersicht (eigene Seite) ──────────────

@app.route("/admin/teilnehmer")
def admin_teilnehmer():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    teilnehmer = conn.execute("SELECT * FROM teilnehmer ORDER BY zelt, nachname, vorname").fetchall()
    slots = conn.execute("SELECT * FROM slots ORDER BY reihenfolge").fetchall()
    anmeldungen = conn.execute("""
        SELECT a.id, a.teilnehmer_id, a.slot_id, a.erstellt_um,
               a.wahl1_id, a.wahl2_id, a.wahl3_id,
               s1.name as wahl1_name, s2.name as wahl2_name, s3.name as wahl3_name,
               t.vorname, t.nachname, t.zelt,
               sl.name as slot_name, sl.reihenfolge
        FROM anmeldungen a
        JOIN teilnehmer t ON t.id = a.teilnehmer_id
        JOIN slots sl ON sl.id = a.slot_id
        JOIN sportarten s1 ON s1.id = a.wahl1_id
        JOIN sportarten s2 ON s2.id = a.wahl2_id
        JOIN sportarten s3 ON s3.id = a.wahl3_id
        ORDER BY sl.reihenfolge, a.erstellt_um
    """).fetchall()
    conn.close()

    return render_template("admin_teilnehmer.html",
                         teilnehmer=teilnehmer,
                         slots=slots,
                         anmeldungen=anmeldungen,
                         code=code)

# ─── Admin: Slot aktivieren/deaktivieren ──────────────────────

@app.route("/admin/slot/toggle/<int:slot_id>", methods=["POST"])
def admin_slot_toggle(slot_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if slot:
        neu = 1 - slot["aktiv"]
        conn.execute("UPDATE slots SET aktiv = ? WHERE id = ?", (neu, slot_id))
        conn.commit()
        status = "freigeschaltet 🟢" if neu else "geschlossen 🔴"
        flash(f"Slot '{slot['name']}' ist jetzt {status}", "success")
    conn.close()
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Zelt-Priorität setzen ─────────────────────────────

@app.route("/admin/priority/setzen", methods=["POST"])
def admin_priority_setzen():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    slot_id = int(request.form.get("slot_id", 0))
    zelt_name = request.form.get("zelt_name", "").strip()
    priority = int(request.form.get("priority", 99))

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO slot_zelt_priorities (slot_id, zelt_name, priority)
            VALUES (?, ?, ?)
            ON CONFLICT(slot_id, zelt_name) DO UPDATE SET priority = excluded.priority
        """, (slot_id, zelt_name, priority))
        conn.commit()
        flash(f"Priorität für {zelt_name} gesetzt.", "success")
    except Exception as e:
        flash(f"Fehler: {e}", "danger")
    conn.close()
    return redirect(url_for("admin_dashboard", code=code))

@app.route("/admin/priority/entfernen/<int:slot_id>/<path:zelt_name>", methods=["POST"])
def admin_priority_entfernen(slot_id, zelt_name):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    from urllib.parse import unquote
    zelt_name = unquote(zelt_name)

    conn = get_db()
    conn.execute("DELETE FROM slot_zelt_priorities WHERE slot_id = ? AND zelt_name = ?",
                (slot_id, zelt_name))
    conn.commit()
    conn.close()
    flash(f"Priorität für {zelt_name} entfernt.", "info")
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Slot-Sportarten verwalten ─────────────────────────

@app.route("/admin/slot-sportart/hinzufuegen", methods=["POST"])
def slot_sportart_hinzufuegen():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    slot_id = int(request.form.get("slot_id", 0))
    sportart_id = int(request.form.get("sportart_id", 0))

    conn = get_db()
    try:
        conn.execute("INSERT INTO slot_sportarten (slot_id, sportart_id) VALUES (?, ?)",
                    (slot_id, sportart_id))
        conn.commit()
        flash("Sportart zum Slot hinzugefügt!", "success")
    except sqlite3.IntegrityError:
        flash("Ist bereits zugeordnet.", "warning")
    conn.close()

    return redirect(url_for("admin_dashboard", code=code))

@app.route("/admin/slot-sportart/entfernen/<int:slot_id>/<int:sportart_id>", methods=["POST"])
def slot_sportart_entfernen(slot_id, sportart_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    conn.execute("DELETE FROM slot_sportarten WHERE slot_id = ? AND sportart_id = ?",
                (slot_id, sportart_id))
    conn.commit()
    conn.close()
    flash("Sportart vom Slot entfernt.", "info")
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Einteilung speichern ──────────────────────────────

@app.route("/admin/einteilen", methods=["POST"])
def admin_einteilen():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    slot_id = int(request.form.get("slot_id", 0))
    conn = get_db()
    conn.execute("DELETE FROM einteilungen WHERE slot_id = ?", (slot_id,))

    for key, value in request.form.items():
        if key.startswith("tn_"):
            tn_id = int(key.replace("tn_", ""))
            sportart_id = int(value)
            if sportart_id > 0:
                conn.execute(
                    "INSERT INTO einteilungen (slot_id, teilnehmer_id, sportart_id) VALUES (?, ?, ?)",
                    (slot_id, tn_id, sportart_id)
                )

    conn.commit()
    conn.close()
    flash("Einteilung gespeichert! ✅", "success")
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Auto-Assignment (mit Zelt-Priorität) ──────────────

@app.route("/admin/auto-assign/<int:slot_id>", methods=["POST"])
def admin_auto_assign(slot_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        conn.close()
        flash("Slot nicht gefunden.", "danger")
        return redirect(url_for("admin_dashboard", code=code))

    # Anmeldungen mit Zelt-Priorität: zuerst nach priority (je kleiner desto höher),
    # dann nach Anmeldezeitpunkt
    anmeldungen = conn.execute("""
        SELECT a.*, t.vorname, t.nachname, t.zelt,
               COALESCE(szp.priority, 99) as zelt_priority
        FROM anmeldungen a
        JOIN teilnehmer t ON t.id = a.teilnehmer_id
        LEFT JOIN slot_zelt_priorities szp 
            ON szp.slot_id = a.slot_id AND LOWER(szp.zelt_name) = LOWER(t.zelt)
        WHERE a.slot_id = ? AND t.verletzt = 0
        ORDER BY zelt_priority ASC, a.erstellt_um ASC
    """, (slot_id,)).fetchall()

    if not anmeldungen:
        conn.close()
        flash(f"Keine Anmeldungen für {slot['name']}.", "info")
        return redirect(url_for("admin_dashboard", code=code))

    conn.execute("DELETE FROM einteilungen WHERE slot_id = ?", (slot_id,))

    sportarten_caps = {}
    for row in conn.execute("""
        SELECT ss.sportart_id, s.max_teilnehmer
        FROM slot_sportarten ss
        JOIN sportarten s ON s.id = ss.sportart_id
        WHERE ss.slot_id = ?
    """, (slot_id,)).fetchall():
        sportarten_caps[row["sportart_id"]] = {"max": row["max_teilnehmer"], "belegt": 0}

    zugeteilt = 0
    nicht_zugeteilt = 0

    for a in anmeldungen:
        wahlen = [a["wahl1_id"], a["wahl2_id"], a["wahl3_id"]]
        zugewiesen = None
        for wahl_id in wahlen:
            cap = sportarten_caps.get(wahl_id)
            if cap and cap["belegt"] < cap["max"]:
                zugewiesen = wahl_id
                cap["belegt"] += 1
                break

        if zugewiesen:
            conn.execute(
                "INSERT INTO einteilungen (slot_id, teilnehmer_id, sportart_id) VALUES (?, ?, ?)",
                (slot_id, a["teilnehmer_id"], zugewiesen)
            )
            zugeteilt += 1
        else:
            nicht_zugeteilt += 1

    conn.commit()
    conn.close()

    msg = f"Auto-Assignment für {slot['name']}: {zugeteilt} zugeteilt"
    if nicht_zugeteilt > 0:
        msg += f", {nicht_zugeteilt} ohne Platz (alle Wahlen voll)"
    flash(msg + " ✅", "success")
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Sportarten ────────────────────────────────────────

@app.route("/admin/sportart/neu", methods=["POST"])
def sportart_neu():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    name = request.form.get("name", "").strip()
    max_tn = request.form.get("max_teilnehmer", 20)

    conn = get_db()
    try:
        conn.execute("INSERT INTO sportarten (name, max_teilnehmer) VALUES (?, ?)", (name, int(max_tn)))
        conn.commit()
        flash(f"Sportart '{name}' erstellt!", "success")
    except sqlite3.IntegrityError:
        flash(f"Sportart '{name}' gibt es bereits!", "warning")
    conn.close()

    return redirect(url_for("admin_dashboard", code=code))

@app.route("/admin/sportart/loeschen/<int:sportart_id>", methods=["POST"])
def sportart_loeschen(sportart_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    conn.execute("DELETE FROM slot_sportarten WHERE sportart_id = ?", (sportart_id,))
    conn.execute("DELETE FROM einteilungen WHERE sportart_id = ?", (sportart_id,))
    conn.execute("DELETE FROM anmeldungen WHERE wahl1_id = ? OR wahl2_id = ? OR wahl3_id = ?",
                (sportart_id, sportart_id, sportart_id))
    conn.execute("DELETE FROM sportarten WHERE id = ?", (sportart_id,))
    conn.commit()
    conn.close()
    flash("Sportart gelöscht.", "info")
    return redirect(url_for("admin_dashboard", code=code))

# ─── Export pro Sportart ───────────────────────────────────────

@app.route("/export/sportart/<int:sportart_id>/<int:slot_id>")
def sportart_export(sportart_id, slot_id):
    conn = get_db()
    sport = conn.execute("SELECT * FROM sportarten WHERE id = ?", (sportart_id,)).fetchone()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not sport or not slot:
        conn.close()
        flash("Sportart oder Slot nicht gefunden.", "danger")
        return redirect(url_for("leiter_login"))

    rows = conn.execute("""
        SELECT t.zelt, t.nachname, t.vorname, t.zelt
        FROM einteilungen e
        JOIN teilnehmer t ON t.id = e.teilnehmer_id
        WHERE e.slot_id = ? AND e.sportart_id = ?
        ORDER BY t.zelt, t.nachname
    """, (slot_id, sportart_id)).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f"{sport['name']} – {slot['name']}"])
    if sport["treffpunkt_zeit"] or sport["treffpunkt_ort"] or sport["material"] or sport["leitung"]:
        writer.writerow([f"Zeit: {sport['treffpunkt_zeit']}"])
        writer.writerow([f"Ort: {sport['treffpunkt_ort']}"])
        writer.writerow([f"Material: {sport['material']}"])
        writer.writerow([f"Leitung: {sport['leitung']}"])
        writer.writerow([])
    writer.writerow(["Zelt", "Nachname", "Vorname"])
    for r in rows:
        writer.writerow([r["zelt"], r["nachname"], r["vorname"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={sport['name']}_{slot['name']}.csv"}
    )


# ─── Admin: Sportart bearbeiten ───────────────────────────────

@app.route("/admin/sportart/bearbeiten/<int:sportart_id>", methods=["GET", "POST"])
def sportart_bearbeiten(sportart_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    sport = conn.execute("SELECT * FROM sportarten WHERE id = ?", (sportart_id,)).fetchone()
    if not sport:
        conn.close()
        flash("Sportart nicht gefunden.", "danger")
        return redirect(url_for("admin_dashboard", code=code))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        max_tn = request.form.get("max_teilnehmer", 20)
        treffpunkt_zeit = request.form.get("treffpunkt_zeit", "").strip()
        treffpunkt_ort = request.form.get("treffpunkt_ort", "").strip()
        material = request.form.get("material", "").strip()
        leitung = request.form.get("leitung", "").strip()
        ausschluss = ",".join(request.form.getlist("ausschluss_hauptsportarten"))

        if not name:
            flash("Name darf nicht leer sein.", "danger")
        else:
            conn.execute(
                "UPDATE sportarten SET name=?, max_teilnehmer=?, treffpunkt_zeit=?, treffpunkt_ort=?, material=?, leitung=?, ausschluss_hauptsportarten=? WHERE id=?",
                (name, max_tn, treffpunkt_zeit, treffpunkt_ort, material, leitung, ausschluss, sportart_id))
            conn.commit()
            flash(f"✅ {name} aktualisiert", "success")
            conn.close()
            return redirect(url_for("admin_dashboard", code=code))

    # Verfügbare Hauptsportarten aus Teilnehmern sammeln
    hauptsportarten = []
    for r in conn.execute("SELECT DISTINCT hauptsportart FROM teilnehmer WHERE hauptsportart != '' ORDER BY hauptsportart").fetchall():
        name = r["hauptsportart"].split("(")[0].strip()
        if name and name not in hauptsportarten:
            hauptsportarten.append(name)
    conn.close()
    return render_template("sportart_bearbeiten.html", sport=sport, hauptsportarten=hauptsportarten, code=code)


# ─── Admin: Teilnehmer löschen ────────────────────────────────

@app.route("/admin/teilnehmer/loeschen/<int:tn_id>", methods=["POST"])
def teilnehmer_loeschen(tn_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    conn.execute("DELETE FROM teilnehmer WHERE id = ?", (tn_id,))
    conn.commit()
    conn.close()
    flash("Teilnehmer gelöscht.", "info")
    return redirect(url_for("admin_dashboard", code=code))


# ─── Admin: Teilnehmer bearbeiten ─────────────────────────────

@app.route("/admin/teilnehmer/bearbeiten/<int:tn_id>", methods=["GET", "POST"])
def teilnehmer_bearbeiten(tn_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    tn = conn.execute("SELECT * FROM teilnehmer WHERE id = ?", (tn_id,)).fetchone()
    if not tn:
        conn.close()
        flash("Teilnehmer nicht gefunden.", "danger")
        return redirect(url_for("admin_teilnehmer", code=code))

    if request.method == "POST":
        vorname = request.form.get("vorname", "").strip()
        nachname = request.form.get("nachname", "").strip()
        zelt = request.form.get("zelt", "").strip()
        anrede = request.form.get("anrede", "").strip()
        geburtsdatum = request.form.get("geburtsdatum", "").strip()
        kommentar = request.form.get("kommentar", "").strip()
        schwimmen = request.form.get("schwimmen", "").strip()
        medikamente = request.form.get("medikamente", "").strip()
        hauptsportart = request.form.get("hauptsportart", "").strip()

        if not vorname or not nachname:
            flash("Vorname und Nachname sind Pflicht.", "danger")
            conn.close()
            return render_template("admin_teilnehmer_bearbeiten.html", tn=tn, code=code)

        try:
            conn.execute(
                "UPDATE teilnehmer SET vorname=?, nachname=?, zelt=?, anrede=?, geburtsdatum=?, kommentar=?, schwimmen=?, medikamente=?, hauptsportart=? WHERE id=?",
                (vorname, nachname, zelt, anrede, geburtsdatum, kommentar, schwimmen, medikamente, hauptsportart, tn_id))
            conn.commit()
            flash(f"{vorname} {nachname} aktualisiert ✅", "success")
            conn.close()
            return redirect(url_for("admin_teilnehmer", code=code))
        except Exception as e:
            conn.close()
            flash(f"Fehler: {e}", "danger")

    conn.close()
    return render_template("admin_teilnehmer_bearbeiten.html", tn=tn, code=code)


# ─── Admin: Verletzt markieren ────────────────────────────────

@app.route("/admin/teilnehmer/verletzt/<int:tn_id>", methods=["POST"])
def teilnehmer_verletzt_toggle(tn_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    tn = conn.execute("SELECT verletzt FROM teilnehmer WHERE id = ?", (tn_id,)).fetchone()
    if tn:
        neu = 1 if tn["verletzt"] == 0 else 0
        conn.execute("UPDATE teilnehmer SET verletzt = ? WHERE id = ?", (neu, tn_id))
        conn.commit()
        flash("Status geändert ✅" if neu else "Status zurückgesetzt", "info")
    conn.close()
    return redirect(url_for("admin_dashboard", code=code))

# ─── Admin: Cross-Check ───────────────────────────────────────

@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        conn = get_db()
        anz = 0
        fehler = 0

        # Datei hochgeladen?
        file = request.files.get("csv_file")
        if file and file.filename:
            content = file.read().decode("utf-8-sig")
            lines = content.splitlines()
        else:
            lines = request.form.get("csv_text", "").strip().splitlines()

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # Kopfzeile überspringen
            if i == 0 and ("Anrede" in line or "Vorname" in line):
                continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) < 3:
                # evtl. durch Komma getrennt
                parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                fehler += 1
                continue

            # Spalten: Anrede, Vorname, Name, Geburtsdatum, Kommentar, Schwimmen, Medikamente, Zelt
            anrede = parts[0] if len(parts) > 0 else ""
            vorname = parts[1] if len(parts) > 1 else ""
            nachname = parts[2] if len(parts) > 2 else ""
            geburtsdatum = parts[3] if len(parts) > 3 else ""
            kommentar = parts[4] if len(parts) > 4 else ""
            schwimmen = parts[5] if len(parts) > 5 else ""
            medikamente = parts[6] if len(parts) > 6 else ""
            zelt = parts[7] if len(parts) > 7 else ""

            if not vorname or not nachname or not zelt:
                fehler += 1
                continue

            try:
                conn.execute(
                    "INSERT INTO teilnehmer (vorname, nachname, zelt, anrede, geburtsdatum, kommentar, schwimmen, medikamente) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (vorname, nachname, zelt, anrede, geburtsdatum, kommentar, schwimmen, medikamente))
                anz += 1
            except Exception:
                fehler += 1

        conn.commit()
        conn.close()
        flash(f"✅ {anz} Teilnehmer importiert" + (f", {fehler} Fehler" if fehler else "") + ".", "success" if fehler == 0 else "warning")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_import.html")


@app.route("/admin/crosscheck", methods=["POST"])
def admin_crosscheck():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    registrierte = conn.execute("SELECT nachname, vorname, zelt FROM teilnehmer ORDER BY nachname, vorname").fetchall()
    conn.close()

    registrierte_set = {(r["nachname"].lower(), r["vorname"].lower()) for r in registrierte}

    liste_text = request.form.get("liste", "")
    if "liste_file" in request.files:
        file = request.files["liste_file"]
        if file.filename:
            liste_text = file.read().decode("utf-8", errors="replace")

    erwartet = []
    for zeile in liste_text.strip().split("\n"):
        zeile = zeile.strip()
        if not zeile:
            continue
        parts = zeile.replace("\t", ",").split(",")
        if len(parts) >= 2:
            nachname = parts[0].strip()
            vorname = parts[1].strip()
            zelt = parts[2].strip() if len(parts) >= 3 else ""
            erwartet.append((nachname, vorname, zelt))

    gefunden = []
    fehlen = []
    for nachname, vorname, zelt in erwartet:
        key = (nachname.lower(), vorname.lower())
        if key in registrierte_set:
            gefunden.append((nachname, vorname, zelt))
        else:
            fehlen.append((nachname, vorname, zelt))

    zusaetzlich = []
    erwartet_set = {(e[0].lower(), e[1].lower()) for e in erwartet}
    for r in registrierte:
        if (r["nachname"].lower(), r["vorname"].lower()) not in erwartet_set:
            zusaetzlich.append((r["nachname"], r["vorname"], r["zelt"]))

    flash(f"Cross-Check: {len(gefunden)} gefunden, {len(fehlen)} fehlen, {len(zusaetzlich)} zusätzlich registriert.", "info")
    return render_template("crosscheck.html",
                         code=code,
                         gefunden=gefunden,
                         fehlen=fehlen,
                         zusaetzlich=zusaetzlich,
                         total_erwartet=len(erwartet),
                         total_registriert=len(registrierte))

# ─── Admin: Zuteilungsübersicht pro Slot ──────────────────────

@app.route("/admin/zuteilung/<int:slot_id>")
def admin_zuteilung(slot_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        conn.close()
        flash("Slot nicht gefunden.", "danger")
        return redirect(url_for("admin_dashboard", code=code))

    # Alle Sportarten + zugeteilte TN für diesen Slot
    sport_einteilung = conn.execute("""
        SELECT s.id, s.name, s.max_teilnehmer,
               COUNT(e.id) as zugeteilt
        FROM sportarten s
        JOIN slot_sportarten ss ON ss.sportart_id = s.id AND ss.slot_id = ?
        LEFT JOIN einteilungen e ON e.sportart_id = s.id AND e.slot_id = ?
        GROUP BY s.id
        ORDER BY s.name
    """, (slot_id, slot_id)).fetchall()

    # Detail: welche TN pro Sportart + welche Wahl erfüllt wurde
    sport_detail = {}
    for s in sport_einteilung:
        rows = conn.execute("""
            SELECT t.vorname, t.nachname, t.zelt,
                   CASE
                       WHEN e.sportart_id = a.wahl1_id THEN 1
                       WHEN e.sportart_id = a.wahl2_id THEN 2
                       WHEN e.sportart_id = a.wahl3_id THEN 3
                       ELSE 0
                   END as erfuellte_wahl
            FROM einteilungen e
            JOIN teilnehmer t ON t.id = e.teilnehmer_id
            LEFT JOIN anmeldungen a ON a.teilnehmer_id = t.id AND a.slot_id = e.slot_id
            WHERE e.slot_id = ? AND e.sportart_id = ?
            ORDER BY t.zelt, t.nachname
        """, (slot_id, s["id"])).fetchall()
        sport_detail[s["id"]] = rows

    # Konflikte:
    # 1. Angemeldet aber nicht zugeteilt
    nicht_zugeteilt = conn.execute("""
        SELECT t.vorname, t.nachname, t.zelt,
               s1.name as w1, s2.name as w2, s3.name as w3
        FROM anmeldungen a
        JOIN teilnehmer t ON t.id = a.teilnehmer_id
        JOIN sportarten s1 ON s1.id = a.wahl1_id
        JOIN sportarten s2 ON s2.id = a.wahl2_id
        JOIN sportarten s3 ON s3.id = a.wahl3_id
        LEFT JOIN einteilungen e ON e.teilnehmer_id = t.id AND e.slot_id = a.slot_id
        WHERE a.slot_id = ? AND e.id IS NULL
        ORDER BY t.zelt, t.nachname
    """, (slot_id,)).fetchall()

    # 2. Überbuchungen
    ueberbucht = []
    for s in sport_einteilung:
        if s["zugeteilt"] > s["max_teilnehmer"]:
            ueberbucht.append({
                "name": s["name"],
                "max": s["max_teilnehmer"],
                "zugeteilt": s["zugeteilt"]
            })

    # 3. Gesamtstatistik
    total_angemeldet = conn.execute(
        "SELECT COUNT(*) as cnt FROM anmeldungen WHERE slot_id = ?", (slot_id,)
    ).fetchone()["cnt"]
    total_zugeteilt = conn.execute(
        "SELECT COUNT(*) as cnt FROM einteilungen WHERE slot_id = ?", (slot_id,)
    ).fetchone()["cnt"]

    conn.close()

    return render_template("zuteilung.html",
                         code=code,
                         slot=slot,
                         sport_einteilung=sport_einteilung,
                         sport_detail=sport_detail,
                         nicht_zugeteilt=nicht_zugeteilt,
                         ueberbucht=ueberbucht,
                         total_angemeldet=total_angemeldet,
                         total_zugeteilt=total_zugeteilt)

# ─── Admin: CSV-Export pro Slot (gruppiert nach Sportart) ──────

@app.route("/admin/export/<int:slot_id>")
def admin_export(slot_id):
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        conn.close()
        flash("Slot nicht gefunden.", "danger")
        return redirect(url_for("admin_dashboard", code=code))

    # Sportart-Details (Treffpunkt, Material, Leitung) abrufen
    sport_details = {}
    for r in conn.execute("SELECT id, name, treffpunkt_zeit, treffpunkt_ort, material, leitung FROM sportarten").fetchall():
        sport_details[r["name"]] = r

    rows = conn.execute("""
        SELECT s.name as sportart, s.treffpunkt_zeit, s.treffpunkt_ort, s.material, s.leitung,
               t.zelt, t.nachname, t.vorname
        FROM einteilungen e
        JOIN teilnehmer t ON t.id = e.teilnehmer_id
        JOIN sportarten s ON s.id = e.sportart_id
        LEFT JOIN anmeldungen a ON a.teilnehmer_id = t.id AND a.slot_id = e.slot_id
        WHERE e.slot_id = ?
        ORDER BY s.name, t.zelt, t.nachname
    """, (slot_id,)).fetchall()

    conn.close()

    # Gruppiert nach Sportart ausgeben
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Einteilung: " + slot["name"]])
    writer.writerow([])

    aktuelle_sport = None
    for r in rows:
        if r["sportart"] != aktuelle_sport:
            aktuelle_sport = r["sportart"]
            writer.writerow([])
            writer.writerow(["=== " + aktuelle_sport + " ==="])
            if r["treffpunkt_zeit"] or r["treffpunkt_ort"] or r["material"] or r["leitung"]:
                writer.writerow(["Treffpunkt (Zeit):", r["treffpunkt_zeit"]])
                writer.writerow(["Treffpunkt (Ort):", r["treffpunkt_ort"]])
                writer.writerow(["Material:", r["material"]])
                writer.writerow(["Leitung:", r["leitung"]])
                writer.writerow([])
            writer.writerow(["Zelt", "Nachname", "Vorname"])
        writer.writerow([r["zelt"], r["nachname"], r["vorname"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={slot['name']}_einteilung.csv"}
    )

# ─── Admin: Zuteilung drucken (PDF-Ansicht) ────────────────────

@app.route("/admin/zuteilung/<int:slot_id>/print")
def admin_zuteilung_print(slot_id):
    """Druckansicht für Admin – ohne Medi/Schwimmen/Kommentar"""
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        conn.close()
        flash("Slot nicht gefunden.", "danger")
        return redirect(url_for("admin_dashboard", code=code))

    rows = conn.execute("""
        SELECT s.name as sportart, s.treffpunkt_zeit, s.treffpunkt_ort, s.material, s.leitung,
               t.zelt, t.nachname, t.vorname
        FROM einteilungen e
        JOIN teilnehmer t ON t.id = e.teilnehmer_id
        JOIN sportarten s ON s.id = e.sportart_id
        LEFT JOIN anmeldungen a ON a.teilnehmer_id = t.id AND a.slot_id = e.slot_id
        WHERE e.slot_id = ?
        ORDER BY s.name, t.zelt, t.nachname
    """, (slot_id,)).fetchall()

    conn.close()
    from datetime import datetime
    return render_template("zuteilung_print.html", slot=slot, rows=rows, show_medical=False,
                         generated_at=datetime.now().strftime('%d.%m.%Y %H:%M'))


# ─── Leiter: Zuteilung drucken (PDF-Ansicht mit Medi) ──────────

@app.route("/leiter/zuteilung/<int:slot_id>/print")
def leiter_zuteilung_print(slot_id):
    """Druckansicht für Leiter – MIT Medi/Schwimmen/Kommentar/Hauptsportart"""
    code = check_leiter()
    if not code:
        return redirect(url_for("leiter_login"))

    conn = get_db()
    slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        conn.close()
        flash("Slot nicht gefunden.", "danger")
        return redirect(url_for("leiter_uebersicht"))

    rows = conn.execute("""
        SELECT s.name as sportart, s.treffpunkt_zeit, s.treffpunkt_ort, s.material, s.leitung,
               t.zelt, t.nachname, t.vorname, t.schwimmen, t.medikamente, t.kommentar, t.hauptsportart
        FROM einteilungen e
        JOIN teilnehmer t ON t.id = e.teilnehmer_id
        JOIN sportarten s ON s.id = e.sportart_id
        LEFT JOIN anmeldungen a ON a.teilnehmer_id = t.id AND a.slot_id = e.slot_id
        WHERE e.slot_id = ?
        ORDER BY s.name, t.zelt, t.nachname
    """, (slot_id,)).fetchall()

    conn.close()
    from datetime import datetime
    return render_template("zuteilung_print.html", slot=slot, rows=rows, show_medical=True,
                         generated_at=datetime.now().strftime('%d.%m.%Y %H:%M'))


# ─── Admin: Zusammenfassung ────────────────────────────────────

@app.route("/admin/zusammenfassung")
def admin_zusammenfassung():
    code = check_admin()
    if not code:
        return redirect(url_for("admin_login"))

    conn = get_db()
    total_tn = conn.execute("SELECT COUNT(*) FROM teilnehmer").fetchone()[0]
    total_anm = conn.execute("SELECT COUNT(*) FROM anmeldungen").fetchone()[0]
    slots = conn.execute("SELECT * FROM slots ORDER BY reihenfolge").fetchall()

    slot_stats = []
    for slot in slots:
        anm_count = conn.execute("SELECT COUNT(*) FROM anmeldungen WHERE slot_id = ?", (slot["id"],)).fetchone()[0]
        verteilt = conn.execute("SELECT COUNT(*) FROM einteilungen WHERE slot_id = ?", (slot["id"],)).fetchone()[0]
        unverteilt = anm_count - verteilt
        sport_stats = conn.execute("""
            SELECT s.name, COUNT(e.id) as count
            FROM sportarten s
            JOIN slot_sportarten ss ON ss.sportart_id = s.id AND ss.slot_id = ?
            LEFT JOIN einteilungen e ON e.sportart_id = s.id AND e.slot_id = ?
            GROUP BY s.id ORDER BY s.name
        """, (slot["id"], slot["id"])).fetchall()
        slot_stats.append({
            "slot": slot,
            "anmeldungen": anm_count,
            "verteilt": verteilt,
            "unverteilt": unverteilt,
            "sport_stats": sport_stats
        })

    conn.close()

    return render_template("zusammenfassung.html",
                         code=code,
                         total_tn=total_tn,
                         total_anm=total_anm,
                         slot_stats=slot_stats)

# ─── Leiter-Ansicht (read-only) ─────────────────────────────────

def check_leiter():
    if session.get("leiter_logged_in"):
        return session.get("leiter_code")
    code = request.args.get("code", request.form.get("code", ""))
    if code == LEITER_CODE:
        session["leiter_logged_in"] = True
        session["leiter_code"] = code
        return code
    return None


@app.route("/leiter", methods=["GET", "POST"])
def leiter_login():
    if request.method == "POST":
        code = request.form.get("code", "")
        if code == LEITER_CODE:
            session["leiter_logged_in"] = True
            session["leiter_code"] = code
            flash("Leiter-Zugang freigeschaltet ✅", "success")
            return redirect(url_for("leiter_uebersicht"))
        else:
            flash("Falscher Leiter-Code", "danger")
    return render_template("leiter_login.html")


@app.route("/leiter/uebersicht")
@app.route("/leiter/uebersicht/<int:sportart_id>")
def leiter_uebersicht(sportart_id=None):
    if not check_leiter():
        return redirect(url_for("leiter_login"))

    conn = get_db()
    code = request.args.get("code", "")

    # Alle aktiven Slots mit ihren Sportarten (für die Auswahl)
    slots = conn.execute("SELECT * FROM slots ORDER BY reihenfolge").fetchall()

    slot_sportarten = {}
    for slot in slots:
        rows = conn.execute("""
            SELECT s.id, s.name, s.max_teilnehmer,
                   COUNT(e.id) as zugeteilt,
                   s.treffpunkt_zeit, s.treffpunkt_ort, s.material, s.leitung
            FROM sportarten s
            JOIN slot_sportarten ss ON ss.sportart_id = s.id AND ss.slot_id = ?
            LEFT JOIN einteilungen e ON e.sportart_id = s.id AND e.slot_id = ?
            GROUP BY s.id ORDER BY s.name
        """, (slot["id"], slot["id"])).fetchall()
        slot_sportarten[slot["id"]] = rows

    # Detail-Ansicht für eine bestimmte Sportart
    sport_detail = None
    sport_info = None
    slot_info = None

    if sportart_id:
        sport_info = conn.execute("SELECT * FROM sportarten WHERE id = ?", (sportart_id,)).fetchone()
        if sport_info:
            # In welchem Slot ist diese Sportart?
            slot_row = conn.execute("""
                SELECT sl.* FROM slots sl
                JOIN slot_sportarten ss ON ss.slot_id = sl.id
                WHERE ss.sportart_id = ?
                LIMIT 1
            """, (sportart_id,)).fetchone()
            if slot_row:
                slot_info = slot_row

                # Zugeteilte Teilnehmer mit allen Details
                teilnehmer = conn.execute("""
                    SELECT t.id, t.vorname, t.nachname, t.zelt, t.kommentar, t.schwimmen, t.medikamente,
                           t.anrede, t.geburtsdatum, t.hauptsportart, t.verletzt,
                           CASE
                               WHEN a.id IS NULL THEN NULL
                               WHEN e.sportart_id = a.wahl1_id THEN 1
                               WHEN e.sportart_id = a.wahl2_id THEN 2
                               WHEN e.sportart_id = a.wahl3_id THEN 3
                               ELSE 0
                           END as erfuellte_wahl
                    FROM einteilungen e
                    JOIN teilnehmer t ON t.id = e.teilnehmer_id
                    LEFT JOIN anmeldungen a ON a.teilnehmer_id = t.id AND a.slot_id = e.slot_id
                    WHERE e.slot_id = ? AND e.sportart_id = ?
                    ORDER BY t.zelt, t.nachname
                """, (slot_info["id"], sportart_id)).fetchall()

                # Anzahl zugeteilt
                anzahl_zugeteilt = len(teilnehmer)

                sport_detail = {
                    "teilnehmer": teilnehmer,
                    "anzahl": anzahl_zugeteilt
                }

    conn.close()
    return render_template("leiter_uebersicht.html",
                         slots=slots,
                         slot_sportarten=slot_sportarten,
                         sport_info=sport_info,
                         slot_info=slot_info,
                         sport_detail=sport_detail,
                         code=code)


# ─── Kurzanleitung ─────────────────────────────────────────────

@app.route("/anleitung")
def anleitung():
    return render_template("anleitung.html")


# ─── Start ─────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
