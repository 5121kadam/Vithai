# import_to_postgres.py
import psycopg2
import csv
from urllib.parse import urlparse

# Parse Render's DATABASE_URL (example)
db_url = "postgresql://ganeshdb:ZfTm9fo82DHKV0XDoHvrPTJkTRcy0HgQ@dpg-d1l4c66mcj7s73bpa1e0-a.singapore-postgres.render.com/ganeshdb"
conn = psycopg2.connect(db_url)

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    # Create table if not exists (match your SQLite schema)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_user (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            phone VARCHAR(20) UNIQUE NOT NULL,
            address TEXT NOT NULL,
            email VARCHAR(100) UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)
    
    with open('user_export.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            cur.execute("""
                INSERT INTO app_user (id, name, phone, address, email, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, row)
    
    conn.commit()
    print(f"Successfully imported {cur.rowcount} users")

except Exception as e:
    print(f"Error: {e}")
finally:
    if conn:
        conn.close()