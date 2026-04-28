"""
GlamDesk – db_manager.py
Interactive CLI to view, add, edit and delete records in glamdesk.db.

Usage:
    uv run python db_manager.py
    python db_manager.py
    python db_manager.py --db /path/to/glamdesk.db
"""

import sqlite3
import os
import sys
import argparse
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── helpers ───────────────────────────────────────────────────────────────────

def get_db_path():
    parser = argparse.ArgumentParser(description="GlamDesk DB Manager")
    parser.add_argument("--db", default=os.getenv("GLAMDESK_DB", "glamdesk.db"),
                        help="Path to glamdesk.db")
    args, _ = parser.parse_known_args()
    return args.db


def get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def clr(text, code):
    codes = {"red": 31, "green": 32, "yellow": 33, "cyan": 36, "bold": 1, "dim": 2}
    return f"\033[{codes.get(code, 0)}m{text}\033[0m"


def header(title):
    print(f"\n{clr('─' * 55, 'dim')}")
    print(f"  {clr(title, 'bold')}")
    print(f"{clr('─' * 55, 'dim')}")


def ok(msg):   print(f"  {clr('✔', 'green')}  {msg}")
def err(msg):  print(f"  {clr('✖', 'red')}  {msg}")
def info(msg): print(f"  {clr('·', 'cyan')}  {msg}")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    val = input(f"  {clr(prompt + suffix + ': ', 'cyan')}").strip()
    return val if val else (str(default) if default is not None else "")


def ask_int(prompt, default=None):
    while True:
        val = ask(prompt, default)
        if val == "" and default is not None:
            return default
        try:
            return int(val)
        except ValueError:
            err("Please enter a whole number.")


def ask_float(prompt, default=None):
    while True:
        val = ask(prompt, default)
        if val == "" and default is not None:
            return default
        try:
            return float(val)
        except ValueError:
            err("Please enter a number.")


def confirm(prompt):
    return ask(prompt + " (y/n)", "n").lower() == "y"


def print_table(rows, cols=None):
    if not rows:
        info("No records found.")
        return
    if cols is None:
        cols = list(rows[0].keys())
    widths = {c: len(str(c)) for c in cols}
    for row in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(row[c] if row[c] is not None else "—")))
    sep = "  ".join("─" * widths[c] for c in cols)
    head = "  ".join(clr(str(c).upper().ljust(widths[c]), "dim") for c in cols)
    print(f"\n  {head}")
    print(f"  {sep}")
    for row in rows:
        line = "  ".join(str(row[c] if row[c] is not None else "—").ljust(widths[c]) for c in cols)
        print(f"  {line}")
    print(f"  {sep}")
    print(f"  {clr(str(len(rows)) + ' row(s)', 'dim')}\n")


# ── APPOINTMENTS ──────────────────────────────────────────────────────────────

def list_appointments(conn):
    header("Appointments")
    rows = conn.execute("""
        SELECT a.id, c.name AS customer, c.phone, s.name AS service,
               COALESCE(st.name, '—') AS stylist,
               a.appt_datetime, a.status,
               CASE a.reminder_sent WHEN 1 THEN 'sent' ELSE 'pending' END AS reminder,
               a.notes
        FROM appointments a
        JOIN customers c  ON c.id = a.customer_id
        JOIN services  s  ON s.id = a.service_id
        LEFT JOIN stylists st ON st.id = a.stylist_id
        ORDER BY a.appt_datetime DESC
    """).fetchall()
    print_table(rows)


def add_appointment(conn):
    header("Add Appointment")
    _pick_customer(conn)
    cid = ask_int("Customer ID")
    _pick_service(conn)
    sid = ask_int("Service ID")
    _pick_stylist(conn)
    stid_raw = ask("Stylist ID (blank = any)", "")
    stid = int(stid_raw) if stid_raw else None
    dt = ask("Date & time (YYYY-MM-DD HH:MM)", datetime.now().strftime("%Y-%m-%d %H:%M"))
    status = ask("Status (booked/cancelled)", "booked")
    notes = ask("Notes (optional)", "")
    try:
        conn.execute(
            "INSERT INTO appointments(customer_id,service_id,stylist_id,appt_datetime,status,notes,reminder_sent) VALUES(?,?,?,?,?,?,0)",
            (cid, sid, stid, dt, status, notes or None)
        )
        conn.commit()
        ok(f"Appointment added for customer #{cid}.")
    except sqlite3.Error as e:
        err(str(e))


def edit_appointment(conn):
    header("Edit Appointment")
    list_appointments(conn)
    aid = ask_int("Appointment ID to edit")
    row = conn.execute("SELECT * FROM appointments WHERE id=?", (aid,)).fetchone()
    if not row:
        err(f"Appointment #{aid} not found.")
        return
    print(f"\n  Editing appointment #{aid}")
    dt      = ask("Date & time", row["appt_datetime"])
    status  = ask("Status (booked/cancelled)", row["status"])
    rem     = ask_int("Reminder sent (0=pending, 1=sent)", row["reminder_sent"])
    notes   = ask("Notes", row["notes"] or "")
    conn.execute(
        "UPDATE appointments SET appt_datetime=?,status=?,reminder_sent=?,notes=? WHERE id=?",
        (dt, status, rem, notes or None, aid)
    )
    conn.commit()
    ok(f"Appointment #{aid} updated.")


def delete_appointment(conn):
    header("Delete Appointment")
    list_appointments(conn)
    aid = ask_int("Appointment ID to delete")
    row = conn.execute("SELECT id FROM appointments WHERE id=?", (aid,)).fetchone()
    if not row:
        err(f"Appointment #{aid} not found.")
        return
    if confirm(f"Delete appointment #{aid}?"):
        conn.execute("DELETE FROM appointments WHERE id=?", (aid,))
        conn.commit()
        ok(f"Appointment #{aid} deleted.")


def reset_reminder(conn):
    header("Reset reminder_sent flag")
    list_appointments(conn)
    choice = ask("Enter appointment ID (or 'all' to reset all)", "")
    if choice.lower() == "all":
        conn.execute("UPDATE appointments SET reminder_sent=0")
        conn.commit()
        ok("All reminder flags reset to 0.")
    else:
        try:
            aid = int(choice)
            conn.execute("UPDATE appointments SET reminder_sent=0 WHERE id=?", (aid,))
            conn.commit()
            ok(f"Appointment #{aid} reminder reset.")
        except ValueError:
            err("Invalid input.")


# ── CUSTOMERS ─────────────────────────────────────────────────────────────────

def _pick_customer(conn):
    rows = conn.execute("SELECT id, name, phone FROM customers ORDER BY name").fetchall()
    print_table(rows, cols=["id", "name", "phone"])


def list_customers(conn):
    header("Customers")
    rows = conn.execute("SELECT * FROM customers ORDER BY id").fetchall()
    print_table(rows)


def add_customer(conn):
    header("Add Customer")
    name  = ask("Full name")
    phone = ask("Phone")
    email = ask("Email (optional)", "")
    if not name:
        err("Name is required.")
        return
    try:
        conn.execute(
            "INSERT INTO customers(name,phone,email) VALUES(?,?,?)",
            (name, phone or None, email or None)
        )
        conn.commit()
        ok(f"Customer '{name}' added.")
    except sqlite3.IntegrityError:
        err(f"Phone '{phone}' already exists.")


def edit_customer(conn):
    header("Edit Customer")
    list_customers(conn)
    cid = ask_int("Customer ID to edit")
    row = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not row:
        err(f"Customer #{cid} not found.")
        return
    name  = ask("Name",  row["name"])
    phone = ask("Phone", row["phone"] or "")
    email = ask("Email", row["email"] or "")
    conn.execute(
        "UPDATE customers SET name=?,phone=?,email=? WHERE id=?",
        (name, phone or None, email or None, cid)
    )
    conn.commit()
    ok(f"Customer #{cid} updated.")


def delete_customer(conn):
    header("Delete Customer")
    list_customers(conn)
    cid = ask_int("Customer ID to delete")
    row = conn.execute("SELECT id FROM customers WHERE id=?", (cid,)).fetchone()
    if not row:
        err(f"Customer #{cid} not found.")
        return
    appts = conn.execute(
        "SELECT COUNT(*) c FROM appointments WHERE customer_id=?", (cid,)
    ).fetchone()["c"]
    if appts:
        err(f"Customer has {appts} appointment(s). Delete those first.")
        return
    if confirm(f"Delete customer #{cid}?"):
        conn.execute("DELETE FROM customers WHERE id=?", (cid,))
        conn.commit()
        ok(f"Customer #{cid} deleted.")


# ── SERVICES ──────────────────────────────────────────────────────────────────

def _pick_service(conn):
    rows = conn.execute("SELECT id, name, duration_min, price FROM services ORDER BY name").fetchall()
    print_table(rows, cols=["id", "name", "duration_min", "price"])


def list_services(conn):
    header("Services")
    rows = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
    print_table(rows)


def add_service(conn):
    header("Add Service")
    name  = ask("Service name")
    dur   = ask_int("Duration (minutes)", 60)
    price = ask_float("Price (₹)", 0)
    desc  = ask("Description (optional)", "")
    if not name:
        err("Name is required.")
        return
    conn.execute(
        "INSERT INTO services(name,duration_min,price,description) VALUES(?,?,?,?)",
        (name, dur, price, desc or None)
    )
    conn.commit()
    ok(f"Service '{name}' added.")


def edit_service(conn):
    header("Edit Service")
    list_services(conn)
    sid = ask_int("Service ID to edit")
    row = conn.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()
    if not row:
        err(f"Service #{sid} not found.")
        return
    name  = ask("Name",              row["name"])
    dur   = ask_int("Duration (min)", row["duration_min"])
    price = ask_float("Price (₹)",   row["price"])
    desc  = ask("Description",        row["description"] or "")
    conn.execute(
        "UPDATE services SET name=?,duration_min=?,price=?,description=? WHERE id=?",
        (name, dur, price, desc or None, sid)
    )
    conn.commit()
    ok(f"Service #{sid} updated.")


def delete_service(conn):
    header("Delete Service")
    list_services(conn)
    sid = ask_int("Service ID to delete")
    row = conn.execute("SELECT id FROM services WHERE id=?", (sid,)).fetchone()
    if not row:
        err(f"Service #{sid} not found.")
        return
    if confirm(f"Delete service #{sid}?"):
        conn.execute("DELETE FROM services WHERE id=?", (sid,))
        conn.commit()
        ok(f"Service #{sid} deleted.")


# ── STYLISTS ──────────────────────────────────────────────────────────────────

def _pick_stylist(conn):
    rows = conn.execute(
        "SELECT id, name, speciality FROM stylists WHERE active=1 ORDER BY name"
    ).fetchall()
    print_table(rows, cols=["id", "name", "speciality"])


def list_stylists(conn):
    header("Stylists")
    rows = conn.execute("SELECT * FROM stylists ORDER BY id").fetchall()
    print_table(rows)


def add_stylist(conn):
    header("Add Stylist")
    name   = ask("Name")
    spec   = ask("Speciality", "")
    wdays  = ask("Working days", "Mon,Tue,Wed,Thu,Fri,Sat")
    active = ask_int("Active (1=yes, 0=no)", 1)
    if not name:
        err("Name is required.")
        return
    conn.execute(
        "INSERT INTO stylists(name,speciality,working_days,active) VALUES(?,?,?,?)",
        (name, spec or None, wdays, active)
    )
    conn.commit()
    ok(f"Stylist '{name}' added.")


def edit_stylist(conn):
    header("Edit Stylist")
    list_stylists(conn)
    stid = ask_int("Stylist ID to edit")
    row  = conn.execute("SELECT * FROM stylists WHERE id=?", (stid,)).fetchone()
    if not row:
        err(f"Stylist #{stid} not found.")
        return
    name   = ask("Name",         row["name"])
    spec   = ask("Speciality",   row["speciality"] or "")
    wdays  = ask("Working days", row["working_days"] or "")
    active = ask_int("Active (1/0)", row["active"])
    conn.execute(
        "UPDATE stylists SET name=?,speciality=?,working_days=?,active=? WHERE id=?",
        (name, spec or None, wdays, active, stid)
    )
    conn.commit()
    ok(f"Stylist #{stid} updated.")


def delete_stylist(conn):
    header("Delete Stylist")
    list_stylists(conn)
    stid = ask_int("Stylist ID to delete")
    row  = conn.execute("SELECT id FROM stylists WHERE id=?", (stid,)).fetchone()
    if not row:
        err(f"Stylist #{stid} not found.")
        return
    if confirm(f"Delete stylist #{stid}?"):
        conn.execute("DELETE FROM stylists WHERE id=?", (stid,))
        conn.commit()
        ok(f"Stylist #{stid} deleted.")


# ── FAQS ──────────────────────────────────────────────────────────────────────

def list_faqs(conn):
    header("FAQs")
    rows = conn.execute("SELECT * FROM faqs ORDER BY id").fetchall()
    print_table(rows)


def add_faq(conn):
    header("Add FAQ")
    question = ask("Question")
    answer   = ask("Answer")
    category = ask("Category (optional)", "")
    if not question or not answer:
        err("Question and answer are required.")
        return
    conn.execute(
        "INSERT INTO faqs(question,answer,category) VALUES(?,?,?)",
        (question, answer, category or None)
    )
    conn.commit()
    ok("FAQ added.")


def edit_faq(conn):
    header("Edit FAQ")
    list_faqs(conn)
    fid = ask_int("FAQ ID to edit")
    row = conn.execute("SELECT * FROM faqs WHERE id=?", (fid,)).fetchone()
    if not row:
        err(f"FAQ #{fid} not found.")
        return
    question = ask("Question", row["question"])
    answer   = ask("Answer",   row["answer"])
    category = ask("Category", row["category"] or "")
    conn.execute(
        "UPDATE faqs SET question=?,answer=?,category=? WHERE id=?",
        (question, answer, category or None, fid)
    )
    conn.commit()
    ok(f"FAQ #{fid} updated.")


def delete_faq(conn):
    header("Delete FAQ")
    list_faqs(conn)
    fid = ask_int("FAQ ID to delete")
    row = conn.execute("SELECT id FROM faqs WHERE id=?", (fid,)).fetchone()
    if not row:
        err(f"FAQ #{fid} not found.")
        return
    if confirm(f"Delete FAQ #{fid}?"):
        conn.execute("DELETE FROM faqs WHERE id=?", (fid,))
        conn.commit()
        ok(f"FAQ #{fid} deleted.")


# ── STATS ─────────────────────────────────────────────────────────────────────

def show_stats(conn):
    header("Database Stats")
    tables = ["customers", "services", "stylists", "appointments", "faqs"]
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        info(f"{t:<20} {clr(str(count), 'bold')} rows")

    booked    = conn.execute("SELECT COUNT(*) c FROM appointments WHERE status='booked'").fetchone()["c"]
    cancelled = conn.execute("SELECT COUNT(*) c FROM appointments WHERE status='cancelled'").fetchone()["c"]
    reminded  = conn.execute("SELECT COUNT(*) c FROM appointments WHERE reminder_sent=1").fetchone()["c"]
    revenue   = conn.execute(
        "SELECT COALESCE(SUM(s.price),0) v FROM appointments a JOIN services s ON s.id=a.service_id WHERE a.status='booked'"
    ).fetchone()["v"]

    print()
    info(f"Booked appointments  : {clr(str(booked), 'green')}")
    info(f"Cancelled            : {clr(str(cancelled), 'red')}")
    info(f"Reminders sent       : {clr(str(reminded), 'cyan')}")
    info(f"Revenue (booked)     : {clr('₹' + f'{revenue:,.2f}', 'bold')}")
    print()


# ── MENUS ─────────────────────────────────────────────────────────────────────

MENUS = {
    "appointments": [
        ("List all appointments",        list_appointments),
        ("Add appointment",              add_appointment),
        ("Edit appointment",             edit_appointment),
        ("Delete appointment",           delete_appointment),
        ("Reset reminder_sent flag",     reset_reminder),
    ],
    "customers": [
        ("List all customers",           list_customers),
        ("Add customer",                 add_customer),
        ("Edit customer",                edit_customer),
        ("Delete customer",              delete_customer),
    ],
    "services": [
        ("List all services",            list_services),
        ("Add service",                  add_service),
        ("Edit service",                 edit_service),
        ("Delete service",               delete_service),
    ],
    "stylists": [
        ("List all stylists",            list_stylists),
        ("Add stylist",                  add_stylist),
        ("Edit stylist",                 edit_stylist),
        ("Delete stylist",               delete_stylist),
    ],
    "faqs": [
        ("List all FAQs",                list_faqs),
        ("Add FAQ",                      add_faq),
        ("Edit FAQ",                     edit_faq),
        ("Delete FAQ",                   delete_faq),
    ],
}

MAIN_MENU = [
    ("Appointments",   "appointments"),
    ("Customers",      "customers"),
    ("Services",       "services"),
    ("Stylists",       "stylists"),
    ("FAQs",           "faqs"),
    ("Stats",          "stats"),
]


def sub_menu(conn, section):
    items = MENUS[section]
    while True:
        header(section.capitalize())
        for i, (label, _) in enumerate(items, 1):
            print(f"  {clr(str(i), 'cyan')}  {label}")
        print(f"  {clr('0', 'dim')}  Back")
        choice = ask("\nChoice", "0")
        if choice == "0":
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                items[idx][1](conn)
            else:
                err("Invalid choice.")
        except (ValueError, KeyboardInterrupt):
            break


def main_menu(conn):
    while True:
        header("GlamDesk  ·  DB Manager")
        for i, (label, _) in enumerate(MAIN_MENU, 1):
            print(f"  {clr(str(i), 'cyan')}  {label}")
        print(f"  {clr('0', 'dim')}  Exit")
        try:
            choice = ask("\nChoice", "0")
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MAIN_MENU):
                _, section = MAIN_MENU[idx]
                if section == "stats":
                    show_stats(conn)
                else:
                    sub_menu(conn, section)
            else:
                err("Invalid choice.")
        except ValueError:
            err("Enter a number.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db_path = get_db_path()

    if not os.path.exists(db_path):
        err(f"Database not found: {db_path}")
        print(f"  Run salon_functions.py first to create glamdesk.db, or pass --db <path>")
        sys.exit(1)

    conn = get_conn(db_path)
    info(f"Connected to {clr(db_path, 'bold')}")

    try:
        main_menu(conn)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        print(f"\n  {clr('Bye!', 'dim')}\n")
