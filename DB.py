import sqlite3

conn = sqlite3.connect("glamdesk.db")
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Tables:", tables)

# Example: view data from first table
#Tables: [('customers',), ('sqlite_sequence',), ('services',), ('stylists',), ('appointments',), ('faqs',)]
table_name = tables[4][0]
print(f"TableName: {table_name}")
cursor.execute(f"SELECT * FROM {table_name} LIMIT 5;")

for row in cursor.fetchall():
    print(row)

conn.close()