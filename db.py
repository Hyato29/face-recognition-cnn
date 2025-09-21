import sqlite3
import os

# Sama seperti di init_db.py
db_folder = 'database'
db_path = os.path.join(db_folder, 'absensi.db')

def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
