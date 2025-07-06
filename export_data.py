import sqlite3
import csv

# Connect to your SQLite database
conn = sqlite3.connect('instance/ganesh.db')
cursor = conn.cursor()

# Get all tables (optional verification)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables in database:", cursor.fetchall())

# Export USER table to CSV
cursor.execute("SELECT * FROM user")
with open('user_export.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    # Write headers
    writer.writerow([description[0] for description in cursor.description])
    # Write data
    writer.writerows(cursor.fetchall())

print("Successfully exported to user_export.csv")
conn.close()