"""
GlamDesk – Salon Receptionist Functions
Replaces pharmacy_functions.py
Uses SQLite instead of hardcoded dicts.
"""

import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = os.getenv("GLAMDESK_DB", "glamdesk.db")


# ──────────────────────────────────────────────
# DB INIT  (run once on startup)
# ──────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and seed demo data if empty."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        phone      TEXT    UNIQUE,
        email      TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS services (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        duration_min INTEGER NOT NULL,
        price        REAL    NOT NULL,
        description  TEXT
    );

    CREATE TABLE IF NOT EXISTS stylists (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        speciality   TEXT,
        working_days TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
        active       INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id   INTEGER REFERENCES customers(id),
        service_id    INTEGER REFERENCES services(id),
        stylist_id    INTEGER REFERENCES stylists(id),
        appt_datetime DATETIME NOT NULL,
        status        TEXT DEFAULT 'booked',
        notes         TEXT,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS faqs (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer   TEXT NOT NULL,
        category TEXT
    );
    """)

    # Seed services
    if c.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO services(name, duration_min, price, description) VALUES (?,?,?,?)",
            [
                ("Haircut & Styling",      45,  799.00, "Precision cut and blow-dry finish"),
                ("Hair Colour (Full)",     120, 2499.00, "Full head colouring with premium dye"),
                ("Highlights",             90,  1899.00, "Foil highlights – partial or full"),
                ("Keratin Treatment",      180, 3999.00, "Smoothing treatment for frizz-free hair"),
                ("Facial – Basic",         60,  999.00, "Deep cleanse, scrub, and moisturise"),
                ("Facial – Advanced",      90,  1799.00, "Includes serum, massage, and mask"),
                ("Manicure",               40,  499.00, "Nail shaping, cuticle care, polish"),
                ("Pedicure",               50,  599.00, "Foot soak, scrub, nail care, polish"),
                ("Eyebrow Threading",      15,  150.00, "Precise brow shaping with thread"),
                ("Head Massage",           30,  499.00, "Relaxing scalp and shoulder massage"),
            ]
        )

    # Seed stylists
    if c.execute("SELECT COUNT(*) FROM stylists").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO stylists(name, speciality, working_days) VALUES (?,?,?)",
            [
                ("Priya",    "Hair colour & cuts",    "Mon,Tue,Wed,Thu,Fri,Sat"),
                ("Kavitha",  "Skincare & facials",    "Tue,Wed,Thu,Fri,Sat"),
                ("Roshini",  "Nail art & manicure",   "Mon,Wed,Fri,Sat"),
                ("Deepika",  "Keratin & treatments",  "Mon,Tue,Thu,Fri,Sat"),
            ]
        )

    # Seed FAQs
    if c.execute("SELECT COUNT(*) FROM faqs").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO faqs(question, answer, category) VALUES (?,?,?)",
            [
                ("What are your working hours?",
                 "We are open Monday to Saturday, 10 AM to 8 PM. Closed on Sundays.",
                 "hours"),
                ("Where are you located?",
                 "We are located at 42 Anna Nagar East, Chennai – 600 040, near the roundtana.",
                 "location"),
                ("Do you take walk-ins?",
                 "Yes, walk-ins are welcome but appointments are recommended to avoid waiting.",
                 "booking"),
                ("What payment methods do you accept?",
                 "We accept cash, UPI, credit and debit cards.",
                 "payment"),
                ("Is parking available?",
                 "Yes, free parking is available in the building compound.",
                 "location"),
                ("Can I reschedule my appointment?",
                 "Yes, please call us at least 2 hours before your appointment to reschedule.",
                 "booking"),
            ]
        )

    conn.commit()
    conn.close()
    print("✅ GlamDesk DB initialised:", DB_PATH)


# ──────────────────────────────────────────────
# FUNCTION 1 – get_service_info
# ──────────────────────────────────────────────

def get_service_info(service_name: str) -> dict:
    """Return price, duration, and description for a named service."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM services WHERE LOWER(name) LIKE ?",
        (f"%{service_name.lower()}%",)
    ).fetchone()
    conn.close()
    if row:
        return {
            "id":           row["id"],
            "name":         row["name"],
            "duration_min": row["duration_min"],
            "price":        row["price"],
            "description":  row["description"],
        }
    return {"error": f"Service '{service_name}' not found. Ask me to list all services."}


# ──────────────────────────────────────────────
# FUNCTION 2 – list_services
# ──────────────────────────────────────────────

def list_services() -> dict:
    """Return all available services with prices."""
    conn = get_conn()
    rows = conn.execute("SELECT name, duration_min, price FROM services ORDER BY id").fetchall()
    conn.close()
    services = [{"name": r["name"], "duration_min": r["duration_min"], "price": r["price"]} for r in rows]
    return {"services": services, "count": len(services)}


# ──────────────────────────────────────────────
# FUNCTION 3 – get_available_slots
# ──────────────────────────────────────────────

def get_available_slots(date_str: str, service_name: str = None) -> dict:
    """
    Return available 1-hour slots for a given date (YYYY-MM-DD).
    Excludes already-booked slots.
    """
    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Please use YYYY-MM-DD, e.g. 2025-06-15"}

    all_slots = ["10:00", "11:00", "12:00", "13:00", "14:00",
                 "15:00", "16:00", "17:00", "18:00", "19:00"]

    conn = get_conn()
    booked = conn.execute(
        "SELECT appt_datetime FROM appointments WHERE DATE(appt_datetime) = ? AND status='booked'",
        (date_str,)
    ).fetchall()
    conn.close()

    booked_times = set()
    for b in booked:
        t = datetime.strptime(b["appt_datetime"], "%Y-%m-%d %H:%M").strftime("%H:%M")
        booked_times.add(t)

    available = [s for s in all_slots if s not in booked_times]

    return {
        "date":      date_str,
        "day":       appt_date.strftime("%A"),
        "available": available,
        "booked":    list(booked_times),
    }


# ──────────────────────────────────────────────
# FUNCTION 4 – book_appointment
# ──────────────────────────────────────────────

def book_appointment(customer_name: str, phone: str,
                     service_name: str, date_str: str,
                     time_str: str, stylist_name: str = None) -> dict:
    """
    Book an appointment.
    Creates customer record if not found.
    Returns appointment id and confirmation details.
    """
    conn = get_conn()

    # Upsert customer
    customer = conn.execute(
        "SELECT id FROM customers WHERE phone = ?", (phone,)
    ).fetchone()
    if customer:
        customer_id = customer["id"]
    else:
        cur = conn.execute(
            "INSERT INTO customers(name, phone) VALUES (?,?)", (customer_name, phone)
        )
        customer_id = cur.lastrowid

    # Resolve service
    service = conn.execute(
        "SELECT * FROM services WHERE LOWER(name) LIKE ?",
        (f"%{service_name.lower()}%",)
    ).fetchone()
    if not service:
        conn.close()
        return {"error": f"Service '{service_name}' not found."}

    # Resolve stylist (optional)
    stylist_id = None
    stylist_display = "Any available stylist"
    if stylist_name:
        stylist = conn.execute(
            "SELECT * FROM stylists WHERE LOWER(name) LIKE ? AND active=1",
            (f"%{stylist_name.lower()}%",)
        ).fetchone()
        if stylist:
            stylist_id = stylist["id"]
            stylist_display = stylist["name"]
        else:
            conn.close()
            return {"error": f"Stylist '{stylist_name}' not found or not available."}

    # Build datetime string
    try:
        appt_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        appt_str = appt_dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        conn.close()
        return {"error": "Invalid date/time format. Use YYYY-MM-DD and HH:MM (24h)."}

    # Check slot availability
    conflict = conn.execute(
        "SELECT id FROM appointments WHERE appt_datetime=? AND status='booked'",
        (appt_str,)
    ).fetchone()
    if conflict:
        conn.close()
        return {"error": f"The slot {time_str} on {date_str} is already booked. Please choose another time."}

    # Insert
    cur = conn.execute(
        """INSERT INTO appointments(customer_id, service_id, stylist_id, appt_datetime, status)
           VALUES (?,?,?,?,?)""",
        (customer_id, service["id"], stylist_id, appt_str, "booked")
    )
    appt_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "appointment_id": appt_id,
        "customer":       customer_name,
        "service":        service["name"],
        "stylist":        stylist_display,
        "date":           appt_dt.strftime("%A, %d %B %Y"),
        "time":           appt_dt.strftime("%I:%M %p"),
        "price":          service["price"],
        "duration_min":   service["duration_min"],
        "message":        f"Appointment #{appt_id} confirmed for {service['name']} on {appt_dt.strftime('%A, %d %B at %I:%M %p')}.",
    }


# ──────────────────────────────────────────────
# FUNCTION 5 – lookup_appointment
# ──────────────────────────────────────────────

def lookup_appointment(appointment_id: int) -> dict:
    """Look up an appointment by ID and return all details."""
    conn = get_conn()
    row = conn.execute("""
        SELECT a.id, c.name as customer, s.name as service,
               st.name as stylist, a.appt_datetime, a.status, a.notes,
               s.price, s.duration_min
        FROM appointments a
        JOIN customers c  ON c.id  = a.customer_id
        JOIN services  s  ON s.id  = a.service_id
        LEFT JOIN stylists st ON st.id = a.stylist_id
        WHERE a.id = ?
    """, (appointment_id,)).fetchone()
    conn.close()

    if not row:
        return {"error": f"Appointment #{appointment_id} not found."}

    dt = datetime.strptime(row["appt_datetime"], "%Y-%m-%d %H:%M")
    return {
        "appointment_id": row["id"],
        "customer":       row["customer"],
        "service":        row["service"],
        "stylist":        row["stylist"] or "Not assigned",
        "date":           dt.strftime("%A, %d %B %Y"),
        "time":           dt.strftime("%I:%M %p"),
        "status":         row["status"],
        "price":          row["price"],
        "duration_min":   row["duration_min"],
    }


# ──────────────────────────────────────────────
# FUNCTION 6 – cancel_appointment
# ──────────────────────────────────────────────

def cancel_appointment(appointment_id: int) -> dict:
    """Cancel an existing appointment by ID."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, status FROM appointments WHERE id=?", (appointment_id,)
    ).fetchone()

    if not row:
        conn.close()
        return {"error": f"Appointment #{appointment_id} not found."}

    if row["status"] == "cancelled":
        conn.close()
        return {"error": f"Appointment #{appointment_id} is already cancelled."}

    conn.execute(
        "UPDATE appointments SET status='cancelled' WHERE id=?", (appointment_id,)
    )
    conn.commit()
    conn.close()
    return {
        "appointment_id": appointment_id,
        "status":  "cancelled",
        "message": f"Appointment #{appointment_id} has been successfully cancelled.",
    }


# ──────────────────────────────────────────────
# FUNCTION 7 – get_faq
# ──────────────────────────────────────────────

def get_faq(topic: str) -> dict:
    """Answer a common question about the salon (hours, location, payment, parking, etc.)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT question, answer FROM faqs WHERE LOWER(question) LIKE ? OR LOWER(category) LIKE ?",
        (f"%{topic.lower()}%", f"%{topic.lower()}%")
    ).fetchall()
    conn.close()

    if rows:
        return {
            "results": [{"question": r["question"], "answer": r["answer"]} for r in rows]
        }
    return {
        "answer": "I don't have specific information on that. Please call us directly at +91 98765 43210."
    }


# ──────────────────────────────────────────────
# FUNCTION MAP (mirrors original pattern)
# ──────────────────────────────────────────────

FUNCTION_MAP = {
    "get_service_info":    get_service_info,
    "list_services":       list_services,
    "get_available_slots": get_available_slots,
    "book_appointment":    book_appointment,
    "lookup_appointment":  lookup_appointment,
    "cancel_appointment":  cancel_appointment,
    "get_faq":             get_faq,
}


# ──────────────────────────────────────────────
# Run init on import
# ──────────────────────────────────────────────
init_db()
