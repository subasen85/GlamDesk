"""
GlamDesk – reminder_scheduler.py
Runs as a separate process alongside main.py.
Every 60 seconds it checks SQLite for appointments
starting within the next hour and places an outbound
Twilio call for any that haven't been reminded yet.
"""

import sqlite3
import time
import os
from datetime import datetime, timedelta
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# ── Twilio credentials (add these to your .env) ──────────────────────────────
ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER   = os.getenv("TWILIO_FROM_NUMBER")   # e.g. +14155552671
SERVER_URL    = os.getenv("GLAMDESK_SERVER_URL")   # e.g. https://yourngrok.ngrok.io

DB_PATH       = os.getenv("GLAMDESK_DB", "glamdesk.db")
CHECK_INTERVAL = 60   # seconds between polls


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_reminder_column():
    """Add reminder_sent column if it doesn't exist yet."""
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE appointments ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Added reminder_sent column to appointments")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.close()


def fetch_due_appointments():
    """
    Return appointments that:
    - are booked (not cancelled)
    - start between now+55min and now+65min  (±5 min window around the 1-hr mark)
    - have not already had a reminder sent
    """
    now       = datetime.now()
    window_lo = now + timedelta(minutes=55)
    window_hi = now + timedelta(minutes=65)

    conn = get_conn()
    rows = conn.execute("""
        SELECT a.id, a.appt_datetime,
               c.name  AS customer_name,
               c.phone AS customer_phone,
               s.name  AS service_name
        FROM appointments a
        JOIN customers c ON c.id = a.customer_id
        JOIN services  s ON s.id = a.service_id
        WHERE a.status = 'booked'
          AND a.reminder_sent = 0
          AND a.appt_datetime BETWEEN ? AND ?
    """, (
        window_lo.strftime("%Y-%m-%d %H:%M"),
        window_hi.strftime("%Y-%m-%d %H:%M"),
    )).fetchall()
    conn.close()
    return rows


def mark_reminder_sent(appointment_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
        (appointment_id,)
    )
    conn.commit()
    conn.close()


def place_outbound_call(customer_phone: str, appointment_id: int,
                        customer_name: str, service_name: str,
                        appt_datetime: str):
    """
    Ask Twilio to dial the customer.
    When they answer, Twilio hits /outbound-call on our server
    which connects them to the Deepgram voice agent.
    We pass appointment details as query params so the agent
    can greet them by name.
    """
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    # Encode context into the TwiML webhook URL
    from urllib.parse import urlencode
    params = urlencode({
        "appt_id":   appointment_id,
        "name":      customer_name,
        "service":   service_name,
        "appt_time": appt_datetime,
    })
    twiml_url = f"{SERVER_URL}/outbound-call?{params}"

    call = client.calls.create(
        to=f"+91{customer_phone}",   # adjust country code for your region
        from_=FROM_NUMBER,
        url=twiml_url,
        method="GET",
    )

    print(f"  ☎  Outbound call placed → {customer_phone} "
          f"(appt #{appointment_id})  Twilio SID: {call.sid}")
    return call.sid


def run():
    print("🌸 GlamDesk reminder scheduler started")
    add_reminder_column()
    client_ok = bool(ACCOUNT_SID and AUTH_TOKEN and FROM_NUMBER and SERVER_URL)
    if not client_ok:
        print("⚠️  Twilio env vars missing — calls will be skipped (dry-run mode)")

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        due = fetch_due_appointments()

        if due:
            print(f"\n[{now}] Found {len(due)} appointment(s) due for reminder")
            for appt in due:
                print(f"  → Appt #{appt['id']}  {appt['customer_name']} "
                      f"({appt['customer_phone']})  {appt['service_name']}  "
                      f"@ {appt['appt_datetime']}")
                if client_ok:
                    try:
                        place_outbound_call(
                            customer_phone = appt["customer_phone"],
                            appointment_id = appt["id"],
                            customer_name  = appt["customer_name"],
                            service_name   = appt["service_name"],
                            appt_datetime  = appt["appt_datetime"],
                        )
                        mark_reminder_sent(appt["id"])
                    except Exception as e:
                        print(f"  ❌ Call failed for appt #{appt['id']}: {e}")
                else:
                    print(f"  [dry-run] Would call {appt['customer_phone']}")
                    mark_reminder_sent(appt["id"])
        else:
            print(f"[{now}] No reminders due", end="\r")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
