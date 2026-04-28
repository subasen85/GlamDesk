"""
GlamDesk – migrate_add_reminder_sent.py
Run this once to add the reminder_sent column to the appointments table.

Usage:
    python migrate_add_reminder_sent.py
"""

import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("GLAMDESK_DB", "glamdesk.db")


def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"Connected to: {DB_PATH}")

    # ── Step 1: Show current schema before migration ──────────────────────────
    print("\n── BEFORE MIGRATION ──────────────────────────────")
    cursor.execute("PRAGMA table_info(appointments)")
    cols_before = cursor.fetchall()
    print(f"{'cid':<5} {'name':<20} {'type':<15} {'notnull':<10} {'default':<15} {'pk'}")
    print("-" * 70)
    for col in cols_before:
        print(f"{col[0]:<5} {col[1]:<20} {col[2]:<15} {col[3]:<10} {str(col[4]):<15} {col[5]}")

    col_names = [col[1] for col in cols_before]

    # ── Step 2: Add reminder_sent column if it doesn't exist ─────────────────
    if "reminder_sent" in col_names:
        print("\n✅ reminder_sent column already exists — nothing to do.")
    else:
        print("\nAdding reminder_sent column...")
        cursor.execute("""
            ALTER TABLE appointments
            ADD COLUMN reminder_sent INTEGER NOT NULL DEFAULT 0
        """)
        conn.commit()
        print("✅ reminder_sent column added successfully.")

    # ── Step 3: Show schema after migration ───────────────────────────────────
    print("\n── AFTER MIGRATION ───────────────────────────────")
    cursor.execute("PRAGMA table_info(appointments)")
    cols_after = cursor.fetchall()
    print(f"{'cid':<5} {'name':<20} {'type':<15} {'notnull':<10} {'default':<15} {'pk'}")
    print("-" * 70)
    for col in cols_after:
        print(f"{col[0]:<5} {col[1]:<20} {col[2]:<15} {col[3]:<10} {str(col[4]):<15} {col[5]}")

    # ── Step 4: Verify existing rows got the default value ───────────────────
    cursor.execute("SELECT COUNT(*) FROM appointments")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM appointments WHERE reminder_sent = 0")
    unsent = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM appointments WHERE reminder_sent = 1")
    sent = cursor.fetchone()[0]

    print(f"\n── ROW CHECK ─────────────────────────────────────")
    print(f"  Total appointments : {total}")
    print(f"  reminder_sent = 0  : {unsent}  (not yet reminded)")
    print(f"  reminder_sent = 1  : {sent}   (already reminded)")

    conn.close()
    print("\n✅ Migration complete.")


if __name__ == "__main__":
    run_migration()
