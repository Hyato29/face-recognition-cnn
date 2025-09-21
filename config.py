import sqlite3
import os
from werkzeug.security import generate_password_hash

def get_db_connection():
    db_path = 'database/absensi.db'

    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Buat tabel admin
        cursor.execute('''
            CREATE TABLE admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        # Buat tabel guru
        cursor.execute('''
            CREATE TABLE guru (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama TEXT NOT NULL
            )
        ''')

        # Buat tabel absensi
        cursor.execute('''
            CREATE TABLE absensi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guru_id INTEGER NOT NULL,
                waktu_absen TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (guru_id) REFERENCES guru(id)
            )
        ''')

        # Tambahkan admin default
        cursor.execute('''
            INSERT INTO admin (username, password) VALUES ('admin', 'admin123')
        ''')

        conn.commit()
        conn.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
