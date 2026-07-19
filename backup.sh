#!/bin/bash
# Stündliches Backup der Tenero-Datenbank
# Installiert als launchd-Job

DB_PATH="/Users/boot/Documents/vibes/jugendlager-tenero/daten/daten.db"
BACKUP_DIR="/Users/boot/Documents/vibes/jugendlager-tenero/backups"
LOG_FILE="/tmp/tenero-backup.log"
TS=$(date '+%Y-%m-%d_%H-%M-%S')

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_DIR/daten_${TS}.db"
    echo "[$TS] ✅ Backup erstellt: daten_${TS}.db" >> "$LOG_FILE"
    
    # Alte Backups löschen (max 200 behalten)
    cd "$BACKUP_DIR" && ls -t daten_*.db 2>/dev/null | tail -n +201 | while read f; do
        rm -f "$BACKUP_DIR/$f"
    done
else
    echo "[$TS] ❌ DB nicht gefunden: $DB_PATH" >> "$LOG_FILE"
fi
